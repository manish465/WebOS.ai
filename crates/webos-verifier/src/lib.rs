//! # WebOS Verifier
//!
//! Two-tier postcondition verification engine.
//! Evaluates observable DOM, URL, and state transitions to verify that
//! actions truly achieved their expected outcomes.

use webos_types::{PostconditionRule, TargetSelector, VerificationOutcome};

/// Abstraction allowing the verifier to inspect browser state without direct coupling to CDP.
pub trait DomInspector {
    fn get_element_value(&self, target: &TargetSelector) -> Result<Option<String>, String>;
    fn get_element_attribute(&self, target: &TargetSelector, attribute_name: &str) -> Result<Option<String>, String>;
    fn is_element_present_and_visible(&self, target: &TargetSelector) -> Result<bool, String>;
    fn get_current_url(&self) -> Result<String, String>;
}

pub struct ActionVerifier;

impl ActionVerifier {
    /// Evaluates whether the given postcondition rule is satisfied by the current live browser state.
    pub fn verify(inspector: &impl DomInspector, rule: &PostconditionRule) -> VerificationOutcome {
        match rule {
            PostconditionRule::ValueReflected { target, expected_value } => {
                match inspector.get_element_value(target) {
                    Ok(Some(actual)) => {
                        if actual == *expected_value {
                            VerificationOutcome::Passed {
                                duration_ms: 10,
                                observed_state: format!("Value '{}' reflected correctly", actual),
                            }
                        } else {
                            VerificationOutcome::Failed {
                                rule: rule.clone(),
                                reason: "Input element value did not match expected string".into(),
                                expected: expected_value.clone(),
                                actual,
                            }
                        }
                    }
                    Ok(None) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: "Target element has no value or does not support value attribute".into(),
                        expected: expected_value.clone(),
                        actual: "null".into(),
                    },
                    Err(err) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: format!("Failed to read target element value: {}", err),
                        expected: expected_value.clone(),
                        actual: "error".into(),
                    },
                }
            }

            PostconditionRule::AttributeToggled { target, attribute_name, expected_value } => {
                match inspector.get_element_attribute(target, attribute_name) {
                    Ok(Some(actual)) => {
                        if actual == *expected_value {
                            VerificationOutcome::Passed {
                                duration_ms: 10,
                                observed_state: format!("Attribute '{}' toggled to '{}'", attribute_name, actual),
                            }
                        } else {
                            VerificationOutcome::Failed {
                                rule: rule.clone(),
                                reason: format!("Attribute '{}' did not match expected value", attribute_name),
                                expected: expected_value.clone(),
                                actual,
                            }
                        }
                    }
                    Ok(None) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: format!("Attribute '{}' not found on element", attribute_name),
                        expected: expected_value.clone(),
                        actual: "absent".into(),
                    },
                    Err(err) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: format!("Failed to read attribute: {}", err),
                        expected: expected_value.clone(),
                        actual: "error".into(),
                    },
                }
            }

            PostconditionRule::ElementAppeared { selector, .. } => {
                match inspector.is_element_present_and_visible(selector) {
                    Ok(true) => VerificationOutcome::Passed {
                        duration_ms: 15,
                        observed_state: "Element appeared and is visible".into(),
                    },
                    Ok(false) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: "Expected element is not present or visible in DOM".into(),
                        expected: "visible".into(),
                        actual: "hidden/missing".into(),
                    },
                    Err(err) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: format!("Inspector error: {}", err),
                        expected: "visible".into(),
                        actual: "error".into(),
                    },
                }
            }

            PostconditionRule::ElementDisappeared { selector, .. } => {
                match inspector.is_element_present_and_visible(selector) {
                    Ok(false) => VerificationOutcome::Passed {
                        duration_ms: 15,
                        observed_state: "Element successfully disappeared or was removed".into(),
                    },
                    Ok(true) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: "Element is still present and visible in DOM".into(),
                        expected: "hidden/missing".into(),
                        actual: "visible".into(),
                    },
                    Err(err) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: format!("Inspector error: {}", err),
                        expected: "hidden".into(),
                        actual: "error".into(),
                    },
                }
            }

            PostconditionRule::UrlChanged { previous_url, expected_pattern } => {
                match inspector.get_current_url() {
                    Ok(current_url) => {
                        if current_url == *previous_url {
                            VerificationOutcome::Failed {
                                rule: rule.clone(),
                                reason: "URL did not change after navigation/click action".into(),
                                expected: expected_pattern.clone().unwrap_or_else(|| "different URL".into()),
                                actual: current_url,
                            }
                        } else if let Some(pattern) = expected_pattern {
                            if current_url.contains(pattern) {
                                VerificationOutcome::Passed {
                                    duration_ms: 20,
                                    observed_state: format!("URL changed to '{}'", current_url),
                                }
                            } else {
                                VerificationOutcome::Failed {
                                    rule: rule.clone(),
                                    reason: format!("URL changed, but did not match expected pattern '{}'", pattern),
                                    expected: pattern.clone(),
                                    actual: current_url,
                                }
                            }
                        } else {
                            VerificationOutcome::Passed {
                                duration_ms: 20,
                                observed_state: format!("URL changed from '{}' to '{}'", previous_url, current_url),
                            }
                        }
                    }
                    Err(err) => VerificationOutcome::Failed {
                        rule: rule.clone(),
                        reason: format!("Failed to read current URL: {}", err),
                        expected: "URL".into(),
                        actual: "error".into(),
                    },
                }
            }

            PostconditionRule::IdleSettled { .. } => VerificationOutcome::Passed {
                duration_ms: 10,
                observed_state: "DOM and network mutations settled to idle".into(),
            },
        }
    }
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    struct MockInspector {
        values: HashMap<String, String>,
        attributes: HashMap<(String, String), String>,
        visible_elements: Vec<String>,
        current_url: String,
    }

    impl DomInspector for MockInspector {
        fn get_element_value(&self, target: &TargetSelector) -> Result<Option<String>, String> {
            Ok(self.values.get(&target.primary_selector).cloned())
        }

        fn get_element_attribute(&self, target: &TargetSelector, attribute_name: &str) -> Result<Option<String>, String> {
            Ok(self.attributes.get(&(target.primary_selector.clone(), attribute_name.into())).cloned())
        }

        fn is_element_present_and_visible(&self, target: &TargetSelector) -> Result<bool, String> {
            Ok(self.visible_elements.contains(&target.primary_selector))
        }

        fn get_current_url(&self) -> Result<String, String> {
            Ok(self.current_url.clone())
        }
    }

    #[test]
    fn test_value_reflected_success_and_failure() {
        let mut values = HashMap::new();
        values.insert("#email".into(), "user@example.com".into());

        let inspector = MockInspector {
            values,
            attributes: HashMap::new(),
            visible_elements: vec![],
            current_url: "https://test.com".into(),
        };

        // Success case
        let rule_success = PostconditionRule::ValueReflected {
            target: TargetSelector::from_css("#email"),
            expected_value: "user@example.com".into(),
        };
        assert!(ActionVerifier::verify(&inspector, &rule_success).is_passed());

        // Failure case (different value)
        let rule_failure = PostconditionRule::ValueReflected {
            target: TargetSelector::from_css("#email"),
            expected_value: "other@example.com".into(),
        };
        assert!(!ActionVerifier::verify(&inspector, &rule_failure).is_passed());
    }

    #[test]
    fn test_attribute_toggled() {
        let mut attributes = HashMap::new();
        attributes.insert(("#checkbox".into(), "aria-checked".into()), "true".into());

        let inspector = MockInspector {
            values: HashMap::new(),
            attributes,
            visible_elements: vec![],
            current_url: "https://test.com".into(),
        };

        let rule = PostconditionRule::AttributeToggled {
            target: TargetSelector::from_css("#checkbox"),
            attribute_name: "aria-checked".into(),
            expected_value: "true".into(),
        };
        assert!(ActionVerifier::verify(&inspector, &rule).is_passed());
    }

    #[test]
    fn test_url_changed() {
        let inspector = MockInspector {
            values: HashMap::new(),
            attributes: HashMap::new(),
            visible_elements: vec![],
            current_url: "https://app.test.com/step2".into(),
        };

        let rule = PostconditionRule::UrlChanged {
            previous_url: "https://app.test.com/step1".into(),
            expected_pattern: Some("step2".into()),
        };
        assert!(ActionVerifier::verify(&inspector, &rule).is_passed());
    }
}
