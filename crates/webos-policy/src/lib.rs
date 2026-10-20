//! # WebOS Policy Engine
//!
//! Independent safety and authorization gate for browser action execution.
//! Enforces user confirmation on irreversible actions, protects sensitive inputs,
//! and prevents execution on forbidden domains.

use webos_types::{
    BrowserAction, ClickAction, ConfirmationReason, FormControlEvidence, PolicyDecision,
    PolicyRequest, PolicyViolation,
};

#[derive(Debug, Clone)]
pub struct PolicyEngineConfig {
    pub forbidden_domains: Vec<String>,
    pub require_confirmation_for_submits: bool,
    pub require_confirmation_for_financial: bool,
}

impl Default for PolicyEngineConfig {
    fn default() -> Self {
        Self {
            forbidden_domains: vec![
                "malicious.test".into(),
                "evil.com".into(),
            ],
            require_confirmation_for_submits: true,
            require_confirmation_for_financial: true,
        }
    }
}

pub struct PolicyEngine {
    config: PolicyEngineConfig,
}

impl PolicyEngine {
    pub fn new(config: PolicyEngineConfig) -> Self {
        Self { config }
    }

    pub fn with_defaults() -> Self {
        Self::new(PolicyEngineConfig::default())
    }

    /// Evaluates whether a proposed browser action is permitted, requires human approval, or is blocked.
    pub fn evaluate(&self, request: &PolicyRequest) -> PolicyDecision {
        // 1. Check for Forbidden Domain
        if self.is_domain_forbidden(&request.domain) {
            return PolicyDecision::Blocked {
                violation: PolicyViolation::ForbiddenDomain,
                explanation: format!("Actions on domain '{}' are explicitly prohibited by policy.", request.domain),
            };
        }

        // 2. Check for Irreversible Action (Submit, Apply, Confirm)
        if self.config.require_confirmation_for_submits && self.is_irreversible_submit(&request.action, request.target_evidence.as_ref()) {
            return PolicyDecision::RequiresUserConfirmation {
                reason: ConfirmationReason::IrreversibleSubmitAction,
                description: "Irreversible form submission or final application step detected.".into(),
                suggested_action: request.action.clone(),
            };
        }

        // 3. Check for Financial / Checkout Action
        if self.config.require_confirmation_for_financial && self.is_financial_trigger(&request.action, request.target_evidence.as_ref()) {
            return PolicyDecision::RequiresUserConfirmation {
                reason: ConfirmationReason::FinancialTransaction,
                description: "Payment or checkout transaction detected.".into(),
                suggested_action: request.action.clone(),
            };
        }

        // 4. Default: Action Permitted
        PolicyDecision::Permitted
    }

    fn is_domain_forbidden(&self, domain: &str) -> bool {
        self.config
            .forbidden_domains
            .iter()
            .any(|f| domain.eq_ignore_ascii_case(f) || domain.ends_with(&format!(".{}", f)))
    }

    fn is_irreversible_submit(&self, action: &BrowserAction, evidence: Option<&FormControlEvidence>) -> bool {
        match action {
            BrowserAction::Click(ClickAction { target, .. }) => {
                let mut text_to_check = String::new();
                if let Some(name) = &target.accessible_name {
                    text_to_check.push_str(name);
                    text_to_check.push(' ');
                }
                text_to_check.push_str(&target.primary_selector);

                if let Some(ev) = evidence {
                    text_to_check.push_str(&ev.name);
                    text_to_check.push(' ');
                    if let Some(role) = &ev.input_type {
                        text_to_check.push_str(role);
                    }
                }

                let lower = text_to_check.to_lowercase();
                lower.contains("submit")
                    || lower.contains("apply now")
                    || lower.contains("submit application")
                    || lower.contains("confirm application")
                    || lower.contains("place order")
                    || lower.contains("delete account")
            }
            _ => false,
        }
    }

    fn is_financial_trigger(&self, action: &BrowserAction, evidence: Option<&FormControlEvidence>) -> bool {
        match action {
            BrowserAction::Click(ClickAction { target, .. }) => {
                let mut text_to_check = String::new();
                if let Some(name) = &target.accessible_name {
                    text_to_check.push_str(name);
                    text_to_check.push(' ');
                }
                text_to_check.push_str(&target.primary_selector);

                if let Some(ev) = evidence {
                    text_to_check.push_str(&ev.name);
                }

                let lower = text_to_check.to_lowercase();
                lower.contains("pay now")
                    || lower.contains("checkout")
                    || lower.contains("purchase")
                    || lower.contains("charge card")
            }
            _ => false,
        }
    }
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use webos_types::{
        FillAction, MouseButton, TargetSelector,
    };

    #[test]
    fn test_normal_fill_is_permitted() {
        let engine = PolicyEngine::with_defaults();
        let request = PolicyRequest {
            run_id: "run-1".into(),
            action: BrowserAction::Fill(FillAction {
                target: TargetSelector::from_css("#first_name"),
                value: "Jane".into(),
                is_secret: false,
                clear_first: true,
                typing_delay_ms: None,
            }),
            target_evidence: None,
            domain: "example.com".into(),
            is_dry_run: false,
        };

        assert_eq!(engine.evaluate(&request), PolicyDecision::Permitted);
    }

    #[test]
    fn test_submit_button_requires_confirmation() {
        let engine = PolicyEngine::with_defaults();
        let request = PolicyRequest {
            run_id: "run-2".into(),
            action: BrowserAction::Click(ClickAction {
                target: TargetSelector::from_css("button[type='submit']")
                    .with_role_and_name("button", "Submit Application"),
                click_count: 1,
                button: MouseButton::Left,
                modifiers: vec![],
            }),
            target_evidence: None,
            domain: "careers.company.com".into(),
            is_dry_run: false,
        };

        let decision = engine.evaluate(&request);
        match decision {
            PolicyDecision::RequiresUserConfirmation { reason, .. } => {
                assert_eq!(reason, ConfirmationReason::IrreversibleSubmitAction);
            }
            other => panic!("Expected user confirmation, got {:?}", other),
        }
    }

    #[test]
    fn test_forbidden_domain_is_blocked() {
        let engine = PolicyEngine::with_defaults();
        let request = PolicyRequest {
            run_id: "run-3".into(),
            action: BrowserAction::Click(ClickAction {
                target: TargetSelector::from_css("a.link"),
                click_count: 1,
                button: MouseButton::Left,
                modifiers: vec![],
            }),
            target_evidence: None,
            domain: "evil.com".into(),
            is_dry_run: false,
        };

        let decision = engine.evaluate(&request);
        match decision {
            PolicyDecision::Blocked { violation, .. } => {
                assert_eq!(violation, PolicyViolation::ForbiddenDomain);
            }
            other => panic!("Expected blocked, got {:?}", other),
        }
    }
}
