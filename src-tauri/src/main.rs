//! WebOS.ai Desktop Control Plane
//! Main entrypoint orchestrating local storage, policy enforcement,
//! browser adapters, and the desktop control loop.

use std::sync::Arc;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;
use webos_adapter_ext::{ExtensionAdapter, ExtensionConfig};
use webos_core::AutomationOrchestrator;
use webos_model::ModelIntelligenceManager;
use webos_plugin_sdk::PluginRegistry;
use webos_policy::{PolicyEngine, PolicyEngineConfig};
use webos_storage::StorageEngine;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 1. Initialize structured logging
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .finish();
    tracing::subscriber::set_global_default(subscriber)
        .expect("Failed to initialize tracing subscriber");

    info!("Starting WebOS.ai Desktop Control Plane (v2.0.0)...");

    // 2. Initialize durable local storage (SQLite with WAL mode)
    let db_path = std::env::current_dir()?.join("webos_runtime.db");
    let storage = StorageEngine::open(&db_path)?;
    info!("SQLite storage initialized at: {:?}", db_path);

    // 3. Initialize policy engine & safety gates
    let policy_config = PolicyEngineConfig::default();
    let policy = Arc::new(PolicyEngine::new(policy_config));
    info!("Policy engine safety gates active (irreversible actions require user confirmation).");

    // 4. Initialize model intelligence subsystem
    let models = Arc::new(ModelIntelligenceManager::new(storage.clone()));
    info!("Model intelligence subsystem ready (exact response cache & quota tracking).");

    // 5. Initialize plugin registry
    let plugins = Arc::new(PluginRegistry::new());

    // 6. Bootstrap extension adapter with ephemeral 256-bit bearer token
    let ext_config = ExtensionConfig::new_random("webos_companion");
    info!("Generated ephemeral session token for browser extension bridge: {}", ext_config.session_token);
    let adapter = Arc::new(tokio::sync::Mutex::new(ExtensionAdapter::new(ext_config)));

    // 7. Instantiate core automation orchestrator
    let orchestrator = AutomationOrchestrator::new(
        adapter,
        policy,
        storage,
        models,
        plugins,
    );

    info!("WebOS.ai Orchestrator ready. Awaiting browser automation trigger (Fill Form / Copilot)...");

    // Keep control plane running
    tokio::signal::ctrl_c().await?;
    info!("Shutting down WebOS.ai Desktop Control Plane.");

    Ok(())
}
