//! Minimal rx4 (tschk/rotary) library host used to smoke-test agent-driven
//! verification slices against this monorepo.
//!
//! Upstream comes from the environment so no provider is hardcoded:
//!   RX4_SMOKE_BASE_URL  OpenAI-compatible base URL (required)
//!   RX4_SMOKE_API_KEY   bearer key for that endpoint (required)
//!   RX4_SMOKE_MODEL     model id (default: glm-5.3-flash)
//!
//! Usage: rx4-smoke "<prompt>"
//!
//! The agent runs with the builtin tool loadout, the default workspace_write
//! policy, a workspace sandbox, and an always-allow approver, so only run it
//! on checkouts you are willing to let it touch.

use std::sync::Arc;

use rx4::provider::OpenAIProvider;
use rx4::{register_builtin_tools, Agent, Event, Scope, ToolRegistry};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let base_url = std::env::var("RX4_SMOKE_BASE_URL").expect("RX4_SMOKE_BASE_URL must be set");
    let key = std::env::var("RX4_SMOKE_API_KEY").expect("RX4_SMOKE_API_KEY must be set");
    let model = std::env::var("RX4_SMOKE_MODEL").unwrap_or_else(|_| "glm-5.3-flash".into());
    let prompt = std::env::args().nth(1).expect("usage: rx4-smoke <prompt>");

    let mut agent = Agent::new();
    let tools = ToolRegistry::new();
    register_builtin_tools(&tools);
    agent.set_tools(tools);
    agent.set_scope(Scope::Coding);
    agent.set_model(&model);
    agent.set_provider(Arc::new(OpenAIProvider::with_base_url(
        &base_url,
        key,
        "rx4-smoke",
        "rx4-smoke upstream",
    )));
    agent.set_approver(Arc::new(rx4::permissions::AlwaysAllow));

    let workspace = agent.workspace_root.clone();
    agent.set_sandbox(Arc::new(rx4::SandboxManager::new(
        rx4::SandboxProfile::Workspace,
        workspace,
    )));

    agent.subscribe(|event| match event {
        Event::MessageDelta { delta } => print!("{delta}"),
        Event::ToolCall(call) => println!("\n[tool call] {}", call.name),
        Event::ToolExecutionEnd(result) => println!("[tool done] error={}", result.is_error),
        Event::TurnEnded { turn, .. } => println!("\n[turn {turn} done]"),
        Event::Error(message) => eprintln!("\n[error] {message}"),
        _ => {}
    });

    agent.prompt(&prompt).await?;
    println!("\ntotal cost (USD): {:.6}", agent.total_cost());
    Ok(())
}
