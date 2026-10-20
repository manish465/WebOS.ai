//! # WebOS Storage
//!
//! SQLite-backed durable flight recorder, learned automation mappings,
//! and exact model response cache.

use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::{Arc, Mutex};
use thiserror::Error;
use uuid::Uuid;
use webos_types::{FlightRecordEvent, WebOSError};

#[derive(Error, Debug)]
pub enum StorageError {
    #[error("SQLite error: {0}")]
    Sqlite(#[from] rusqlite::Error),

    #[error("JSON serialization error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Database lock contention error")]
    LockError,

    #[error("Entity not found: {0}")]
    NotFound(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LearnedFieldMapping {
    pub id: String,
    pub domain_pattern: String,
    pub field_role: String,
    pub normalized_label: String,
    pub section_context: Option<String>,
    pub profile_key: String,
    pub verification_count: u32,
    pub last_verified_at: i64,
}

#[derive(Clone)]
pub struct StorageEngine {
    conn: Arc<Mutex<Connection>>,
}

impl StorageEngine {
    /// Opens or creates a SQLite database at the specified path.
    pub fn open(path: impl AsRef<Path>) -> Result<Self, StorageError> {
        let conn = Connection::open(path)?;
        let engine = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        engine.run_migrations()?;
        Ok(engine)
    }

    /// Creates an in-memory SQLite database, primarily for testing.
    pub fn new_in_memory() -> Result<Self, StorageError> {
        let conn = Connection::open_in_memory()?;
        let engine = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        engine.run_migrations()?;
        Ok(engine)
    }

    /// Initializes and applies database schemas with WAL mode enabled.
    fn run_migrations(&self) -> Result<(), StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;

        // WAL mode for concurrent fast reads and writes
        conn.execute_batch("PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;")?;

        conn.execute_batch(
            r#"
            -- Flight Recorder Audit Events
            CREATE TABLE IF NOT EXISTS flight_records (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                timestamp_utc TEXT NOT NULL,
                domain TEXT NOT NULL,
                page_url TEXT NOT NULL,
                action_json TEXT NOT NULL,
                target_evidence_json TEXT,
                policy_decision_json TEXT NOT NULL,
                execution_duration_ms INTEGER NOT NULL,
                verification_outcome_json TEXT NOT NULL,
                model_metadata_json TEXT,
                screenshot_path TEXT,
                error_details TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_flight_run_id ON flight_records(run_id);
            CREATE INDEX IF NOT EXISTS idx_flight_domain ON flight_records(domain);

            -- Learned Field Mappings (Bypass LLM calls)
            CREATE TABLE IF NOT EXISTS learned_field_mappings (
                id TEXT PRIMARY KEY,
                domain_pattern TEXT NOT NULL,
                field_role TEXT NOT NULL,
                normalized_label TEXT NOT NULL,
                section_context TEXT,
                profile_key TEXT NOT NULL,
                verification_count INTEGER DEFAULT 1,
                last_verified_at INTEGER NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_mappings_lookup 
                ON learned_field_mappings(domain_pattern, field_role, normalized_label);

            -- Exact Model Response Cache
            CREATE TABLE IF NOT EXISTS cached_model_responses (
                cache_key TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                response_json TEXT NOT NULL,
                model_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 1
            );
            "#,
        )?;

        Ok(())
    }

    // ------------------------------------------------------------------------
    // Flight Recorder Operations
    // ------------------------------------------------------------------------

    pub fn insert_flight_record(&self, event: &FlightRecordEvent) -> Result<(), StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;

        let action_json = serde_json::to_string(&event.action)?;
        let evidence_json = event
            .target_evidence
            .as_ref()
            .map(serde_json::to_string)
            .transpose()?;
        let policy_json = serde_json::to_string(&event.policy_decision)?;
        let verification_json = serde_json::to_string(&event.verification_outcome)?;
        let model_json = event
            .model_metadata
            .as_ref()
            .map(serde_json::to_string)
            .transpose()?;

        conn.execute(
            r#"
            INSERT INTO flight_records (
                event_id, run_id, step_index, timestamp_utc, domain, page_url,
                action_json, target_evidence_json, policy_decision_json,
                execution_duration_ms, verification_outcome_json,
                model_metadata_json, screenshot_path, error_details
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)
            "#,
            params![
                event.event_id,
                event.run_id,
                event.step_index,
                event.timestamp_utc,
                event.domain,
                event.page_url,
                action_json,
                evidence_json,
                policy_json,
                event.execution_duration_ms,
                verification_json,
                model_json,
                event.screenshot_path,
                event.error_details,
            ],
        )?;

        Ok(())
    }

    pub fn get_flight_records_for_run(&self, run_id: &str) -> Result<Vec<FlightRecordEvent>, StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;

        let mut stmt = conn.prepare(
            r#"
            SELECT event_id, run_id, step_index, timestamp_utc, domain, page_url,
                   action_json, target_evidence_json, policy_decision_json,
                   execution_duration_ms, verification_outcome_json,
                   model_metadata_json, screenshot_path, error_details
            FROM flight_records
            WHERE run_id = ?1
            ORDER BY step_index ASC
            "#,
        )?;

        let rows = stmt.query_map(params![run_id], |row| {
            let action_str: String = row.get(6)?;
            let evidence_str: Option<String> = row.get(7)?;
            let policy_str: String = row.get(8)?;
            let verification_str: String = row.get(10)?;
            let model_str: Option<String> = row.get(11)?;

            Ok((
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                action_str,
                evidence_str,
                policy_str,
                row.get(9)?,
                verification_str,
                model_str,
                row.get(12)?,
                row.get(13)?,
            ))
        })?;

        let mut events = Vec::new();
        for r in rows {
            let (
                event_id,
                run_id,
                step_index,
                timestamp_utc,
                domain,
                page_url,
                action_str,
                evidence_str,
                policy_str,
                execution_duration_ms,
                verification_str,
                model_str,
                screenshot_path,
                error_details,
            ) = r?;

            events.push(FlightRecordEvent {
                event_id,
                run_id,
                step_index,
                timestamp_utc,
                domain,
                page_url,
                action: serde_json::from_str(&action_str)?,
                target_evidence: evidence_str
                    .as_deref()
                    .map(serde_json::from_str)
                    .transpose()?,
                policy_decision: serde_json::from_str(&policy_str)?,
                execution_duration_ms,
                verification_outcome: serde_json::from_str(&verification_str)?,
                model_metadata: model_str
                    .as_deref()
                    .map(serde_json::from_str)
                    .transpose()?,
                screenshot_path,
                error_details,
            });
        }

        Ok(events)
    }

    // ------------------------------------------------------------------------
    // Learned Field Mappings (Tier 2 Cache)
    // ------------------------------------------------------------------------

    pub fn save_learned_mapping(
        &self,
        domain_pattern: &str,
        field_role: &str,
        normalized_label: &str,
        section_context: Option<&str>,
        profile_key: &str,
    ) -> Result<LearnedFieldMapping, StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;
        let now = Utc::now().timestamp();

        let id = Uuid::new_v4().to_string();

        conn.execute(
            r#"
            INSERT INTO learned_field_mappings (
                id, domain_pattern, field_role, normalized_label,
                section_context, profile_key, verification_count, last_verified_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, ?7)
            ON CONFLICT(domain_pattern, field_role, normalized_label) DO UPDATE SET
                verification_count = verification_count + 1,
                last_verified_at = excluded.last_verified_at,
                profile_key = excluded.profile_key,
                section_context = COALESCE(excluded.section_context, section_context)
            "#,
            params![
                id,
                domain_pattern,
                field_role,
                normalized_label,
                section_context,
                profile_key,
                now,
            ],
        )?;

        Ok(LearnedFieldMapping {
            id,
            domain_pattern: domain_pattern.into(),
            field_role: field_role.into(),
            normalized_label: normalized_label.into(),
            section_context: section_context.map(Into::into),
            profile_key: profile_key.into(),
            verification_count: 1,
            last_verified_at: now,
        })
    }

    pub fn find_learned_mapping(
        &self,
        domain: &str,
        field_role: &str,
        normalized_label: &str,
    ) -> Result<Option<LearnedFieldMapping>, StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;

        let mut stmt = conn.prepare(
            r#"
            SELECT id, domain_pattern, field_role, normalized_label, section_context,
                   profile_key, verification_count, last_verified_at
            FROM learned_field_mappings
            WHERE (?1 LIKE domain_pattern OR domain_pattern = ?1)
              AND field_role = ?2
              AND normalized_label = ?3
            ORDER BY verification_count DESC
            LIMIT 1
            "#,
        )?;

        let mapping = stmt
            .query_row(params![domain, field_role, normalized_label], |row| {
                Ok(LearnedFieldMapping {
                    id: row.get(0)?,
                    domain_pattern: row.get(1)?,
                    field_role: row.get(2)?,
                    normalized_label: row.get(3)?,
                    section_context: row.get(4)?,
                    profile_key: row.get(5)?,
                    verification_count: row.get(6)?,
                    last_verified_at: row.get(7)?,
                })
            })
            .optional()?;

        Ok(mapping)
    }

    // ------------------------------------------------------------------------
    // Exact Response Cache (Tier 1 Cache)
    // ------------------------------------------------------------------------

    pub fn get_cached_response(&self, cache_key: &str) -> Result<Option<String>, StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;

        let mut stmt = conn.prepare(
            r#"
            UPDATE cached_model_responses
            SET hit_count = hit_count + 1
            WHERE cache_key = ?1;
            SELECT response_json FROM cached_model_responses WHERE cache_key = ?1;
            "#,
        )?;

        let res: Option<String> = conn
            .query_row(
                "SELECT response_json FROM cached_model_responses WHERE cache_key = ?1",
                params![cache_key],
                |row| row.get(0),
            )
            .optional()?;

        if res.is_some() {
            let _ = conn.execute(
                "UPDATE cached_model_responses SET hit_count = hit_count + 1 WHERE cache_key = ?1",
                params![cache_key],
            );
        }

        Ok(res)
    }

    pub fn save_cached_response(
        &self,
        cache_key: &str,
        task_type: &str,
        response_json: &str,
        model_id: &str,
    ) -> Result<(), StorageError> {
        let conn = self.conn.lock().map_err(|_| StorageError::LockError)?;
        let now = Utc::now().timestamp();

        conn.execute(
            r#"
            INSERT INTO cached_model_responses (
                cache_key, task_type, response_json, model_id, created_at, hit_count
            ) VALUES (?1, ?2, ?3, ?4, ?5, 1)
            ON CONFLICT(cache_key) DO UPDATE SET
                hit_count = hit_count + 1,
                response_json = excluded.response_json
            "#,
            params![cache_key, task_type, response_json, model_id, now],
        )?;

        Ok(())
    }
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use webos_types::{
        BrowserAction, ClickAction, MouseButton, PolicyDecision, PostconditionRule, TargetSelector,
        VerificationOutcome,
    };

    #[test]
    fn test_sqlite_in_memory_migrations() {
        let engine = StorageEngine::new_in_memory().expect("Must initialize in-memory DB");

        // Insert and read back learned mapping
        let mapping = engine
            .save_learned_mapping(
                "*.myworkdayjobs.com",
                "textbox",
                "years of experience",
                Some("Work History"),
                "candidate.experience.total_years",
            )
            .expect("Must save mapping");

        assert_eq!(mapping.profile_key, "candidate.experience.total_years");

        // Find mapping matching specific workday subdomain
        let found = engine
            .find_learned_mapping(
                "company.myworkdayjobs.com",
                "textbox",
                "years of experience",
            )
            .expect("Must query mapping")
            .expect("Must find matching mapping");

        assert_eq!(found.profile_key, "candidate.experience.total_years");
    }

    #[test]
    fn test_flight_recorder_event_roundtrip() {
        let engine = StorageEngine::new_in_memory().expect("Must initialize in-memory DB");

        let event = FlightRecordEvent {
            event_id: "evt-001".into(),
            run_id: "run-abc".into(),
            step_index: 1,
            timestamp_utc: Utc::now().to_rfc3339(),
            domain: "greenhouse.io".into(),
            page_url: "https://greenhouse.io/job/123".into(),
            action: BrowserAction::Click(ClickAction {
                target: TargetSelector::from_css("button.next"),
                click_count: 1,
                button: MouseButton::Left,
                modifiers: vec![],
            }),
            target_evidence: None,
            policy_decision: PolicyDecision::Permitted,
            execution_duration_ms: 120,
            verification_outcome: VerificationOutcome::Passed {
                duration_ms: 50,
                observed_state: "Next step loaded".into(),
            },
            model_metadata: None,
            screenshot_path: None,
            error_details: None,
        };

        engine.insert_flight_record(&event).expect("Must insert event");

        let retrieved = engine
            .get_flight_records_for_run("run-abc")
            .expect("Must retrieve events");

        assert_eq!(retrieved.len(), 1);
        assert_eq!(retrieved[0].event_id, "evt-001");
        assert_eq!(retrieved[0].domain, "greenhouse.io");
    }

    #[test]
    fn test_exact_response_cache() {
        let engine = StorageEngine::new_in_memory().expect("Must initialize in-memory DB");

        let cache_key = "sha256_abcdef123456";
        let task_type = "classify_form_field";
        let response_json = r#"{"category":"years_experience","profile_key":"exp.years"}"#;

        assert!(engine.get_cached_response(cache_key).unwrap().is_none());

        engine
            .save_cached_response(cache_key, task_type, response_json, "gemini-1.5-flash")
            .unwrap();

        let cached = engine
            .get_cached_response(cache_key)
            .unwrap()
            .expect("Must be cached");
        assert_eq!(cached, response_json);
    }
}
