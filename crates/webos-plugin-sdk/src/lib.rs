//! # WebOS Plugin SDK
//!
//! Standard trait definitions and runtime contracts for external domain plugins
//! (such as WorkKnightBot) to integrate cleanly with the WebOS.ai engine.

use async_trait::async_trait;
use std::sync::Arc;
use webos_types::{
    ActionExecutionReceipt, FieldResolution, FormControlEvidence, PageSnapshot,
    PluginManifest, WebOSError, WorkflowPlan,
};

#[async_trait]
pub trait WebOSPlugin: Send + Sync {
    /// Returns the metadata manifest of the domain plugin.
    fn manifest(&self) -> PluginManifest;

    /// Evaluates whether the plugin should activate for the given page snapshot.
    async fn should_activate(&self, snapshot: &PageSnapshot) -> bool;

    /// Generates a proposed workflow plan for the detected form or wizard.
    async fn propose_plan(&self, snapshot: &PageSnapshot) -> Result<Option<WorkflowPlan>, WebOSError>;

    /// Resolves an individual form field against candidate data or domain rules.
    async fn resolve_field(&self, field: &FormControlEvidence) -> Result<FieldResolution, WebOSError>;

    /// Hook invoked after an action has been successfully verified on the live page.
    async fn on_action_verified(&self, receipt: &ActionExecutionReceipt) -> Result<(), WebOSError>;
}

/// Registry managing active domain plugins during an automation session.
#[derive(Default)]
pub struct PluginRegistry {
    plugins: Vec<Arc<dyn WebOSPlugin>>,
}

impl PluginRegistry {
    pub fn new() -> Self {
        Self { plugins: Vec::new() }
    }

    pub fn register(&mut self, plugin: Arc<dyn WebOSPlugin>) {
        self.plugins.push(plugin);
    }

    /// Finds the first registered plugin that activates for the target snapshot.
    pub async fn find_active_plugin(&self, snapshot: &PageSnapshot) -> Option<Arc<dyn WebOSPlugin>> {
        for plugin in &self.plugins {
            if plugin.should_activate(snapshot).await {
                return Some(plugin.clone());
            }
        }
        None
    }
}

// ----------------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use webos_types::{TargetSelector};

    struct MockJobPlugin;

    #[async_trait]
    impl WebOSPlugin for MockJobPlugin {
        fn manifest(&self) -> PluginManifest {
            PluginManifest {
                id: "workknightbot".into(),
                name: "WorkKnightBot".into(),
                version: "1.0.0".into(),
                supported_domains: vec!["myworkdayjobs.com".into()],
            }
        }

        async fn should_activate(&self, snapshot: &PageSnapshot) -> bool {
            snapshot.url.contains("myworkdayjobs.com")
        }

        async fn propose_plan(&self, _snapshot: &PageSnapshot) -> Result<Option<WorkflowPlan>, WebOSError> {
            Ok(None)
        }

        async fn resolve_field(&self, field: &FormControlEvidence) -> Result<FieldResolution, WebOSError> {
            if field.name.to_lowercase().contains("first name") {
                Ok(FieldResolution::ResolvedValue {
                    value: "Alex".into(),
                    is_secret: false,
                    provenance: "dossier.personal.first_name".into(),
                })
            } else {
                Ok(FieldResolution::Unresolved)
            }
        }

        async fn on_action_verified(&self, _receipt: &ActionExecutionReceipt) -> Result<(), WebOSError> {
            Ok(())
        }
    }

    #[tokio::test]
    async fn test_plugin_registration_and_activation() {
        let mut registry = PluginRegistry::new();
        registry.register(Arc::new(MockJobPlugin));

        let snapshot = PageSnapshot {
            session_id: "s1".into(),
            url: "https://company.myworkdayjobs.com/apply".into(),
            title: "Job Application".into(),
            timestamp_ms: 0,
            viewport_width: 1920,
            viewport_height: 1080,
            controls: vec![],
        };

        let active = registry.find_active_plugin(&snapshot).await;
        assert!(active.is_some());
        let plugin = active.unwrap();
        assert_eq!(plugin.manifest().id, "workknightbot");

        let field = FormControlEvidence {
            control_id: "c1".into(),
            selector: TargetSelector::from_css("#fname"),
            tag_name: "input".into(),
            input_type: Some("text".into()),
            role: "textbox".into(),
            name: "First Name".into(),
            placeholder: None,
            is_required: true,
            is_disabled: false,
            is_readonly: false,
            current_value: None,
            options: vec![],
            section_heading: None,
            nearby_labels: vec![],
        };

        let res = plugin.resolve_field(&field).await.expect("Must resolve field");
        match res {
            FieldResolution::ResolvedValue { value, .. } => assert_eq!(value, "Alex"),
            _ => panic!("Expected resolved value"),
        }
    }
}
