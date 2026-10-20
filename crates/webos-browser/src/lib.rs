//! # WebOS Browser Abstraction
//!
//! Unified `BrowserAdapter` trait and zero-token perception pipeline.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use webos_types::{
    ActionExecutionReceipt, BrowserAction, FormControlEvidence, PageSnapshot,
    PostconditionRule, VerificationOutcome, WebOSError,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionContext {
    pub session_id: String,
    pub browser_type: String,
    pub target_url: String,
}

/// Unified trait implemented by both the Chrome Extension Adapter and Dedicated Playwright Adapter.
#[async_trait]
pub trait BrowserAdapter: Send + Sync {
    /// Attaches to the target browser session or tab.
    async fn attach(&mut self, session_id: &str) -> Result<SessionContext, WebOSError>;

    /// Captures a zero-token perception snapshot of active interactive controls on the page.
    async fn capture_snapshot(&self) -> Result<PageSnapshot, WebOSError>;

    /// Executes a typed, policy-authorized action primitive with human-like emulation.
    async fn execute_action(&self, action: &BrowserAction) -> Result<ActionExecutionReceipt, WebOSError>;

    /// Verifies observable postconditions directly on the live page.
    async fn verify_state(&self, rule: &PostconditionRule) -> Result<VerificationOutcome, WebOSError>;

    /// Detaches from the target session.
    async fn detach(&mut self) -> Result<(), WebOSError>;
}

/// Zero-token perception filters to prune raw DOM / AX trees down to 20-35 relevant controls.
pub struct PerceptionPruner;

impl PerceptionPruner {
    /// Evaluates whether an element should be retained in the perception snapshot.
    pub fn is_interactive_control(role: &str, tag_name: &str, is_visible: bool) -> bool {
        if !is_visible {
            return false;
        }

        let interactive_roles = [
            "button",
            "textbox",
            "searchbox",
            "spinbutton",
            "combobox",
            "checkbox",
            "radio",
            "link",
            "menuitem",
            "tab",
        ];

        let interactive_tags = ["input", "button", "select", "textarea", "a"];

        interactive_roles.contains(&role.to_lowercase().as_str())
            || interactive_tags.contains(&tag_name.to_lowercase().as_str())
    }

    /// Ranks controls based on position, relevance, and required status.
    pub fn rank_controls(mut controls: Vec<FormControlEvidence>) -> Vec<FormControlEvidence> {
        controls.sort_by(|a, b| {
            // Prioritize required controls first
            match (a.is_required, b.is_required) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => {
                    // Then by vertical position on screen if bounding box is known
                    let ya = a.selector.bounding_box.map(|bb| bb.y).unwrap_or(0.0);
                    let yb = b.selector.bounding_box.map(|bb| bb.y).unwrap_or(0.0);
                    ya.partial_cmp(&yb).unwrap_or(std::cmp::Ordering::Equal)
                }
            }
        });
        controls
    }
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use webos_types::{BoundingBox, TargetSelector};

    #[test]
    fn test_perception_filter() {
        assert!(PerceptionPruner::is_interactive_control("button", "button", true));
        assert!(PerceptionPruner::is_interactive_control("textbox", "input", true));
        assert!(!PerceptionPruner::is_interactive_control("generic", "div", true));
        assert!(!PerceptionPruner::is_interactive_control("button", "button", false)); // hidden
    }

    #[test]
    fn test_ranking_required_first() {
        let control1 = FormControlEvidence {
            control_id: "c1".into(),
            selector: TargetSelector::from_css("#optional").with_role_and_name("textbox", "Optional"),
            tag_name: "input".into(),
            input_type: Some("text".into()),
            role: "textbox".into(),
            name: "Optional".into(),
            placeholder: None,
            is_required: false,
            is_disabled: false,
            is_readonly: false,
            current_value: None,
            options: vec![],
            section_heading: None,
            nearby_labels: vec![],
        };

        let mut control2 = control1.clone();
        control2.control_id = "c2".into();
        control2.is_required = true;
        control2.selector.bounding_box = Some(BoundingBox { x: 0.0, y: 100.0, width: 100.0, height: 20.0 });

        let ranked = PerceptionPruner::rank_controls(vec![control1, control2]);
        assert_eq!(ranked[0].control_id, "c2"); // Required comes first
    }
}
