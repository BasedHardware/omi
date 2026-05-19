use dioxus::prelude::*;

use crate::auth::AuthStatus;
use crate::components::sidebar::Sidebar;
use crate::config::AppConfig;
use crate::pages;
use crate::recording::{LiveTranscript, RecordingStatus};
use crate::sidecar::BackendStatus;

/// Top-level route enum — each variant maps to a sidebar nav item.
#[derive(Debug, Clone, Routable, PartialEq)]
#[rustfmt::skip]
pub enum Route {
    #[layout(AppLayout)]
        #[route("/")]
        Dashboard {},
        #[route("/chat")]
        Chat {},
        #[route("/conversations")]
        Conversations {},
        #[route("/memories")]
        Memories {},
        #[route("/tasks")]
        Tasks {},
        #[route("/rewind")]
        Rewind {},
        #[route("/apps")]
        Apps {},
        #[route("/focus")]
        Focus {},
        #[route("/persona")]
        Persona {},
        #[route("/settings")]
        Settings {},
}

/// The root application component.
#[component]
pub fn App() -> Element {
    // Load persisted config
    let config = use_signal(|| AppConfig::load());

    // Determine initial auth status from saved token
    let initial_auth = {
        let cfg = config.read();
        if cfg.is_authenticated() {
            AuthStatus::SignedIn {
                email: cfg.user_email.clone(),
                name: cfg.user_display_name.clone(),
            }
        } else {
            AuthStatus::SignedOut
        }
    };
    let auth_status = use_signal(|| initial_auth);

    // Backend sidecar health
    let mut backend_status = use_signal(|| BackendStatus::Starting);

    // Recording state
    let recording_status = use_signal(|| RecordingStatus::Idle);
    let live_transcript = use_signal(LiveTranscript::default);

    // Provide all as global context
    use_context_provider(|| config);
    use_context_provider(|| auth_status);
    use_context_provider(|| backend_status);
    use_context_provider(|| recording_status);
    use_context_provider(|| live_transcript);

    // Kick off the sidecar health poller once
    use_effect(move || {
        spawn(async move {
            crate::sidecar::poll_backend_health(&mut backend_status).await;
        });
    });

    rsx! {
        Router::<Route> {}
    }
}

/// Shared layout: sidebar on the left, page content on the right.
#[component]
fn AppLayout() -> Element {
    rsx! {
        div { class: "app-layout",
            Sidebar {}
            main { class: "app-content",
                Outlet::<Route> {}
            }
        }
    }
}

// ── Page components (thin wrappers delegating to pages module) ──────────

#[component]
fn Dashboard() -> Element {
    pages::dashboard::DashboardPage()
}

#[component]
fn Chat() -> Element {
    pages::chat::ChatPage()
}

#[component]
fn Conversations() -> Element {
    pages::conversations::ConversationsPage()
}

#[component]
fn Memories() -> Element {
    pages::memories::MemoriesPage()
}

#[component]
fn Tasks() -> Element {
    pages::tasks::TasksPage()
}

#[component]
fn Rewind() -> Element {
    pages::rewind::RewindPage()
}

#[component]
fn Apps() -> Element {
    pages::apps::AppsPage()
}

#[component]
fn Focus() -> Element {
    pages::focus::FocusPage()
}

#[component]
fn Persona() -> Element {
    pages::persona::PersonaPage()
}

#[component]
fn Settings() -> Element {
    pages::settings::SettingsPage()
}
