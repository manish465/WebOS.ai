//! # WebOS Core Runtime
//!
//! Orchestrator coordinating perception, policy evaluation, action execution,
//! postcondition verification, model intelligence routing, and flight recording.

use chrono::Utc;
use std::sync::Arc;
use uuid::Uuid;
use webos_browser::BrowserAdapter;
use webos_model::{ClassifyFormFieldTask, ModelIntelligenceManager};
use webos_plugin_sdk::PluginRegistry;
use webos_policy::PolicyEngine;
use webos_storage::StorageEngine;
use webos_types::{
    BrowserAction, FillAction, FlightRecordEvent, FormControlEvidence, PageSnapshot,
    PolicyDecision, PolicyRequest, PostconditionRule, VerificationOutcome, WebOSError,
};

pub struct AutomationOrchestrator {
    adapter: Arc<tokio::sync::Mutex<dyn BrowserAdapter>>,
    policy: Arc<PolicyEngine>,
    storage: StorageEngine,
    models: Arc<ModelIntelligenceManager>,
    plugins: Arc<PluginRegistry>,
}

impl AutomationOrchestrator {
    pub fn new(
        adapter: Arc<tokio::sync::Mutex<dyn BrowserAdapter>>,
        policy: Arc<PolicyEngine>,
        storage: StorageEngine,
        models: Arc<ModelIntelligenceManager>,
        plugins: Arc<PluginRegistry>,
    ) -> Self {
        Self {
            adapter,
            policy,
            storage,
            models,
            plugins,
        }
    }

    /// Primary execution flow: Inspects active page, identifies known or unknown fields,
    /// authorizes actions, executes with verified postconditions, and updates learned mappings.
    pub async fn run_form_fill_flow(
        &self,
        run_id: &str,
        domain: &str,
    ) -> Result<Vec<FlightRecordEvent>, WebOSError> {
        let mut events = Vec::new();

        // 1. Capture Page Perception Snapshot (Zero tokens)
        let adapter = self.adapter.lock().await;
        let snapshot: PageSnapshot = adapter.capture_snapshot().await?;
        drop(adapter);

        // 2. Check for active domain plugin (e.g. WorkKnightBot)
        let active_plugin = self.plugins.find_active_plugin(&snapshot).await;

        let mut step_index = 0;

        for control in &snapshot.controls {
            step_index += 1;

            // 3. Resolve field: Check learned mappings in SQLite first (0 tokens, < 1ms)
            let mut resolved_value: Option<String> = None;

            if let Ok(Some(mapping)) = self.storage.find_learned_mapping(domain, &control.role, &control.name) {
                // Resolved from Tier-2 learned mappings
                resolved_value = Some(format!("ValFor:{}", mapping.profile_key));
            } else if let Some(plugin) = &active_plugin {
                // Check if plugin resolves field from Candidate Dossier
                if let Ok(webos_types::FieldResolution::ResolvedValue { value, .. }) = plugin.resolve_field(control).await {
                    resolved_value = Some(value);
                }
            }

            // 4. If unknown, invoke Model Intelligence Layer with canonical task
            if resolved_value.is_none() {
                let task = ClassifyFormFieldTask {
                    task: "classify_form_field".into(),
                    version: "1.0".into(),
                    field_label: control.name.clone(),
                    tag_name: control.tag_name.clone(),
                    input_type: control.input_type.clone(),
                    role: control.role.clone(),
                    section: control.section_heading.clone(),
                    options: control.options.iter().map(|o| o.text.clone()).collect(),
                };

                if let Ok(classified) = self.models.classify_field(&task) {
                    if let Some(profile_key) = classified.suggested_profile_key {
                        resolved_value = Some(format!("ValFor:{}", profile_key));
                        // Learn mapping for subsequent encounters
                        let _ = self.storage.save_learned_mapping(
                            domain,
                            &control.role,
                            &control.name,
                            control.section_heading.as_deref(),
                            &profile_key,
                        );
                    }
                }
            }

            let value_to_type = match resolved_value {
                Some(v) => v,
                None => continue, // Skip unresolvable fields
            };

            // 5. Construct Typed Browser Action
            let action = BrowserAction::Fill(FillAction {
                target: control.selector.clone(),
                value: value_to_type.clone(),
                is_secret: false,
                clear_first: true,
                typing_delay_ms: Some(20),
            });

            // 6. Policy Engine Authorization Gate
            let policy_req = PolicyRequest {
                run_id: run_id.into(),
                action: action.clone(),
                target_evidence: Some(control.clone()),
                domain: domain.into(),
                is_dry_run: false,
            };

            let policy_decision = self.policy.evaluate(&policy_req);

            if let PolicyDecision::Blocked { violation, explanation } = &policy_decision {
                tracing::warn!("Action blocked by policy: {:?} - {}", violation, explanation);
                continue;
            }

            // 7. Execute Permitted Action via Browser Adapter
            let adapter = self.adapter.lock().await;
            let receipt = adapter.execute_action(&action).await?;

            // 8. Verify Postcondition (Tier-1 deterministic check)
            let verification_rule = PostconditionRule::ValueReflected {
                target: control.selector.clone(),
                expected_value: value_to_type.clone(),
            };
            let outcome = adapter.verify_state(&verification_rule).await?;
            drop(adapter);

            // 9. Notify plugin of successful action
            if let Some(plugin) = &active_plugin {
                let _ = plugin.on_action_verified(&receipt).await;
            }

            // 10. Record Flight Audit Event to SQLite
            let event = FlightRecordEvent {
                event_id: Uuid::new_v4().to_string(),
                run_id: run_id.into(),
                step_index,
                timestamp_utc: Utc::now().to_rfc3339(),
                domain: domain.into(),
                page_url: snapshot.url.clone(),
                action,
                target_evidence: Some(control.clone()),
                policy_decision,
                execution_duration_ms: receipt.duration_ms,
                verification_outcome: outcome,
                model_metadata: None,
                screenshot_path: None,
                error_details: None,
            };

            let _ = self.storage.insert_flight_record(&event);
            events.push(event);
        }

        Ok(events)
    }
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use webos_adapter_ext::{ExtensionAdapter, ExtensionConfig};
    use webos_policy::PolicyEngineConfig;
    use webos_types::TargetSelector;

    #[tokio::test]
    async fn test_orchestrator_pipeline_flow() {
        let storage = StorageEngine::new_in_memory().unwrap();
        let models = Arc::new(ModelIntelligenceManager::new(storage.clone()));
        let policy = Arc::new(PolicyEngine::new(PolicyEngineConfig::default()));
        let plugins = Arc::new(PluginRegistry::new());

        let config = ExtensionConfig::new_random("test_ext");
        let adapter = Arc::new(tokio::sync::Mutex::new(ExtensionAdapter::new(config)));

        let orchestrator = AutomationOrchestrator::new(
            adapter,
            policy,
            storage.clone(),
            models,
            plugins,
        );

        // Pre-populate learned mapping in SQLite
        storage
            .save_learned_mapping(
                "careers.test.com",
                "textbox",
                "Email",
                None,
                "candidate.email",
            )
            .unwrap();

        let events = orchestrator
            .run_form_fill_flow("run-123", "careers.test.com")
            .await
            .expect("Orchestrator flow must succeed");

        // The mock snapshot has 0 controls by default, so events count is 0
        assert_eq!(events.len(), 0);
    }
}
