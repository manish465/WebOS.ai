//! # WebOS Types
//!
//! Core typed data models, actions, perception schemas, policy contracts,
//! and verification definitions for WebOS.ai.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use thiserror::Error;

// ----------------------------------------------------------------------------
// Action Primitives
// ----------------------------------------------------------------------------

/// The canonical action enum representing every permitted browser operation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "action_type", content = "payload")]
pub enum BrowserAction {
    Click(ClickAction),
    Fill(FillAction),
    Select(SelectAction),
    Upload(UploadAction),
    Scroll(ScrollAction),
    Navigate(NavigateAction),
    Wait(WaitAction),
}

/// Precise element locator combining selector with semantic and spatial fallback anchors.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TargetSelector {
    /// Primary DOM selector (CSS or XPath)
    pub primary_selector: String,
    /// Accessibility Role (e.g., "button", "combobox", "textbox")
    pub accessible_role: Option<String>,
    /// Accessible Name computed by browser accessibility engine
    pub accessible_name: Option<String>,
    /// Semantic label or text proximity anchor
    pub text_anchor: Option<String>,
    /// Viewport bounding box at perception time
    pub bounding_box: Option<BoundingBox>,
}

impl TargetSelector {
    pub fn from_css(selector: impl Into<String>) -> Self {
        Self {
            primary_selector: selector.into(),
            accessible_role: None,
            accessible_name: None,
            text_anchor: None,
            bounding_box: None,
        }
    }

    pub fn with_role_and_name(mut self, role: impl Into<String>, name: impl Into<String>) -> Self {
        self.accessible_role = Some(role.into());
        self.accessible_name = Some(name.into());
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ClickAction {
    pub target: TargetSelector,
    pub click_count: u32,
    pub button: MouseButton,
    pub modifiers: Vec<ModifierKey>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FillAction {
    pub target: TargetSelector,
    /// The string to be typed into the element
    pub value: String,
    /// Flag indicating whether the value is sensitive (redacted in flight logs)
    pub is_secret: bool,
    /// Whether to clear the field before entering text
    pub clear_first: bool,
    /// Emulated keystroke delay in milliseconds
    pub typing_delay_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SelectAction {
    pub target: TargetSelector,
    pub option_value: Option<String>,
    pub option_text: Option<String>,
    pub option_index: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UploadAction {
    pub target: TargetSelector,
    pub file_path: PathBuf,
    pub mime_type: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScrollAction {
    pub direction: ScrollDirection,
    pub distance_px: i32,
    pub target: Option<TargetSelector>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NavigateAction {
    pub url: String,
    pub timeout_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WaitAction {
    pub duration_ms: u64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum MouseButton {
    Left,
    Right,
    Middle,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ModifierKey {
    Alt,
    Control,
    Meta,
    Shift,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ScrollDirection {
    Up,
    Down,
    Left,
    Right,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct BoundingBox {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

// ----------------------------------------------------------------------------
// Perception & Page Snapshot
// ----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PageSnapshot {
    pub session_id: String,
    pub url: String,
    pub title: String,
    pub timestamp_ms: u64,
    pub viewport_width: u32,
    pub viewport_height: u32,
    /// Extracted and ranked interactive controls
    pub controls: Vec<FormControlEvidence>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FormControlEvidence {
    /// Unique runtime element index for this snapshot
    pub control_id: String,
    pub selector: TargetSelector,
    pub tag_name: String,
    pub input_type: Option<String>,
    pub role: String,
    pub name: String,
    pub placeholder: Option<String>,
    pub is_required: bool,
    pub is_disabled: bool,
    pub is_readonly: bool,
    pub current_value: Option<String>,
    /// Available options for select/combobox/radio controls
    pub options: Vec<ControlOption>,
    /// Contextual text from parent fieldset or section header
    pub section_heading: Option<String>,
    /// Nearest visual label elements
    pub nearby_labels: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ControlOption {
    pub value: String,
    pub text: String,
    pub is_selected: bool,
}

// ----------------------------------------------------------------------------
// Policy Engine Contracts
// ----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyRequest {
    pub run_id: String,
    pub action: BrowserAction,
    pub target_evidence: Option<FormControlEvidence>,
    pub domain: String,
    pub is_dry_run: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum PolicyDecision {
    /// Action is authorized to execute immediately
    Permitted,
    /// Action requires explicit human approval on the desktop HUD
    RequiresUserConfirmation {
        reason: ConfirmationReason,
        description: String,
        suggested_action: BrowserAction,
    },
    /// Action is prohibited by safety policy
    Blocked {
        violation: PolicyViolation,
        explanation: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ConfirmationReason {
    IrreversibleSubmitAction,
    FinancialTransaction,
    SensitiveDataEntry,
    AmbiguousFieldMatch,
    RateLimitTriggered,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PolicyViolation {
    ForbiddenDomain,
    DisallowedFileExtension,
    UnsanitizedPIIToCloud,
    DestructiveScriptDetected,
    ExecutionTimeoutExceeded,
}

// ----------------------------------------------------------------------------
// Postcondition Verification Protocol
// ----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum PostconditionRule {
    /// Value entered into an input must be reflected in the DOM
    ValueReflected {
        target: TargetSelector,
        expected_value: String,
    },
    /// Attribute must reflect expected state (e.g., aria-checked="true")
    AttributeToggled {
        target: TargetSelector,
        attribute_name: String,
        expected_value: String,
    },
    /// Element must become visible or present in DOM
    ElementAppeared {
        selector: TargetSelector,
        timeout_ms: u64,
    },
    /// Element must be removed or hidden
    ElementDisappeared {
        selector: TargetSelector,
        timeout_ms: u64,
    },
    /// Page URL must change or match pattern
    UrlChanged {
        previous_url: String,
        expected_pattern: Option<String>,
    },
    /// Network and DOM mutations must settle to idle
    IdleSettled {
        min_idle_ms: u64,
        max_wait_ms: u64,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum VerificationOutcome {
    Passed {
        duration_ms: u64,
        observed_state: String,
    },
    Failed {
        rule: PostconditionRule,
        reason: String,
        expected: String,
        actual: String,
    },
    Timeout {
        rule: PostconditionRule,
        elapsed_ms: u64,
    },
}

impl VerificationOutcome {
    pub fn is_passed(&self) -> bool {
        matches!(self, VerificationOutcome::Passed { .. })
    }
}

// ----------------------------------------------------------------------------
// Plugin Interface Contracts
// ----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginManifest {
    pub id: String,
    pub name: String,
    pub version: String,
    pub supported_domains: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum FieldResolution {
    /// Value resolved from verified candidate profile
    ResolvedValue {
        value: String,
        is_secret: bool,
        provenance: String,
    },
    /// Explicit rule to leave this field empty or decline
    IntentionalBlank {
        reason: String,
    },
    /// Field requires human intervention
    NeedsUserAnswer {
        question_prompt: String,
        options: Vec<String>,
    },
    /// Plugin has no resolution; falls back to generic runtime classifier
    Unresolved,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionExecutionReceipt {
    pub action: BrowserAction,
    pub outcome: VerificationOutcome,
    pub duration_ms: u64,
    pub timestamp_utc: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowPlan {
    pub plan_id: String,
    pub domain: String,
    pub steps: Vec<WorkflowStep>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowStep {
    pub step_index: u32,
    pub description: String,
    pub action: BrowserAction,
    pub expected_verification: PostconditionRule,
}

// ----------------------------------------------------------------------------
// Flight Recorder & Telemetry
// ----------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlightRecordEvent {
    pub event_id: String,
    pub run_id: String,
    pub step_index: u32,
    pub timestamp_utc: String,
    pub domain: String,
    pub page_url: String,
    pub action: BrowserAction,
    pub target_evidence: Option<FormControlEvidence>,
    pub policy_decision: PolicyDecision,
    pub execution_duration_ms: u64,
    pub verification_outcome: VerificationOutcome,
    pub model_metadata: Option<ModelInvocationMetadata>,
    pub screenshot_path: Option<String>,
    pub error_details: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelInvocationMetadata {
    pub provider: String,
    pub model_id: String,
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
    pub latency_ms: u64,
    pub cache_hit: bool,
}

// ----------------------------------------------------------------------------
// Core Error Definitions
// ----------------------------------------------------------------------------

#[derive(Error, Debug)]
pub enum WebOSError {
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("Browser driver error: {0}")]
    Browser(String),

    #[error("Policy violation: {0}")]
    Policy(String),

    #[error("Postcondition verification failed: {0}")]
    Verification(String),

    #[error("Storage error: {0}")]
    Storage(String),

    #[error("Model intelligence error: {0}")]
    Model(String),

    #[error("Plugin error: {0}")]
    Plugin(String),

    #[error("Internal error: {0}")]
    Internal(String),
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_browser_action_json_roundtrip() {
        let action = BrowserAction::Fill(FillAction {
            target: TargetSelector::from_css("#email-field").with_role_and_name("textbox", "Email Address"),
            value: "candidate@example.com".into(),
            is_secret: false,
            clear_first: true,
            typing_delay_ms: Some(25),
        });

        let serialized = serde_json::to_string(&action).expect("Must serialize");
        let deserialized: BrowserAction = serde_json::from_str(&serialized).expect("Must deserialize");

        assert_eq!(action, deserialized);
    }

    #[test]
    fn test_policy_decision_json_roundtrip() {
        let decision = PolicyDecision::RequiresUserConfirmation {
            reason: ConfirmationReason::IrreversibleSubmitAction,
            description: "Submit application button clicked".into(),
            suggested_action: BrowserAction::Click(ClickAction {
                target: TargetSelector::from_css("button[type='submit']"),
                click_count: 1,
                button: MouseButton::Left,
                modifiers: vec![],
            }),
        };

        let serialized = serde_json::to_string(&decision).expect("Must serialize");
        let deserialized: PolicyDecision = serde_json::from_str(&serialized).expect("Must deserialize");

        assert_eq!(decision, deserialized);
    }

    #[test]
    fn test_verification_outcome() {
        let passed = VerificationOutcome::Passed {
            duration_ms: 45,
            observed_state: "Value reflected in DOM".into(),
        };
        assert!(passed.is_passed());

        let failed = VerificationOutcome::Failed {
            rule: PostconditionRule::ValueReflected {
                target: TargetSelector::from_css("#phone"),
                expected_value: "1234567890".into(),
            },
            reason: "Field value remained empty".into(),
            expected: "1234567890".into(),
            actual: "".into(),
        };
        assert!(!failed.is_passed());
    }
}
