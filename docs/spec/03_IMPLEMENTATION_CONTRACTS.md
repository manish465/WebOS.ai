# WebOS.ai — Implementation Contracts Specification
**Document Version:** 1.0.0  
**Status:** SPECIFICATION_LOCKED  
**Scope:** Action Primitives, Perception Schema, Policy Contracts, Verification Protocol, Plugin Interface, Telemetry Events  

---

## 1. Typed Browser Action Primitives

All actions executed on browser targets must be strictly typed Rust data structures serialized over IPC as JSON. **Arbitrary script evaluation (`eval`, raw JS strings) is strictly banned.**

```rust
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

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
    /// Emulated keystroke delay in milliseconds (defaults to human-like distribution)
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
pub enum MouseButton { Left, Right, Middle }

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ModifierKey { Alt, Control, Meta, Shift }

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ScrollDirection { Up, Down, Left, Right }

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct BoundingBox {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}
```

---

## 2. Perception & Page Snapshot Schema

Perception extracts an indexed, zero-token structural representation of all visible interactive elements:

```rust
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
```

---

## 3. Policy Authorization Contract

Every action must be vetted by the Policy Engine prior to dispatch to any browser adapter:

```rust
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
```

---

## 4. Postcondition Verification Protocol

An action is considered successful **only when its explicit postcondition is verified on the live page**, never simply because the command finished dispatching.

```rust
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
```

---

## 5. Plugin Interface Contract (WorkKnightBot Specification)

Domain plugins (including WorkKnightBot) interact with WebOS.ai via the `WebOSPlugin` trait:

```rust
#[async_trait]
pub trait WebOSPlugin: Send + Sync {
    /// Unique identifier and metadata of the domain plugin
    fn manifest(&self) -> PluginManifest;

    /// Evaluates whether the plugin activates for the given page snapshot
    async fn should_activate(&self, snapshot: &PageSnapshot) -> bool;

    /// Generates a proposed workflow plan for the detected form/wizard
    async fn propose_plan(&self, snapshot: &PageSnapshot) -> Result<Option<WorkflowPlan>, PluginError>;

    /// Resolves an individual form field against candidate data or domain rules
    async fn resolve_field(
        &self, 
        field: &FormControlEvidence, 
        context: &WorkflowContext
    ) -> Result<FieldResolution, PluginError>;

    /// Hook invoked after an action has been executed and verified
    async fn on_action_verified(&self, receipt: &ActionExecutionReceipt) -> Result<(), PluginError>;

    /// Hook invoked when an action fails verification or hits a recovery condition
    async fn on_action_failed(&self, failure: &ActionFailureContext) -> Result<RecoveryAction, PluginError>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginManifest {
    pub id: String,
    pub name: String,
    pub version: String,
    pub supported_domains: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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
```

---

## 6. Flight Recorder & Telemetry Event Schema

Every operation appends a structured event to the local SQLite audit log:

```rust
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
    /// Path to scrubbed screenshot file (only on error or explicit milestone)
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
```
