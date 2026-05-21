use dioxus::prelude::*;

use crate::app::Route;
use crate::sidecar::BackendStatus;

#[component]
pub fn Sidebar() -> Element {
    let backend_status: Signal<BackendStatus> = use_context();

    let status_class = match *backend_status.read() {
        BackendStatus::Starting => "status-starting",
        BackendStatus::Connected => "status-connected",
        BackendStatus::Error(_) => "status-error",
    };

    let status_text = match &*backend_status.read() {
        BackendStatus::Starting => "Backend starting...".to_string(),
        BackendStatus::Connected => "Backend connected".to_string(),
        BackendStatus::Error(e) => format!("Backend error: {e}"),
    };

    rsx! {
        nav { class: "sidebar",
            // Brand
            div { class: "sidebar-brand",
                span { class: "brand-logo", "O" }
                span { class: "brand-text", "Omi" }
            }

            // Navigation links
            div { class: "sidebar-nav",
                Link { to: Route::Dashboard {}, class: "nav-item",
                    span { class: "nav-icon", "H" }
                    span { class: "nav-label", "Dashboard" }
                }
                Link { to: Route::Agent {}, class: "nav-item",
                    span { class: "nav-icon", "Ω" }
                    span { class: "nav-label", "Agent" }
                }
                Link { to: Route::Chat {}, class: "nav-item",
                    span { class: "nav-icon", "C" }
                    span { class: "nav-label", "Chat" }
                }
                Link { to: Route::Conversations {}, class: "nav-item",
                    span { class: "nav-icon", "V" }
                    span { class: "nav-label", "Conversations" }
                }
                Link { to: Route::Memories {}, class: "nav-item",
                    span { class: "nav-icon", "M" }
                    span { class: "nav-label", "Memories" }
                }
                Link { to: Route::Tasks {}, class: "nav-item",
                    span { class: "nav-icon", "T" }
                    span { class: "nav-label", "Tasks" }
                }
                Link { to: Route::Rewind {}, class: "nav-item",
                    span { class: "nav-icon", "R" }
                    span { class: "nav-label", "Rewind" }
                }
                Link { to: Route::Apps {}, class: "nav-item",
                    span { class: "nav-icon", "A" }
                    span { class: "nav-label", "Apps" }
                }
                Link { to: Route::Focus {}, class: "nav-item",
                    span { class: "nav-icon", "F" }
                    span { class: "nav-label", "Focus" }
                }
                Link { to: Route::Persona {}, class: "nav-item",
                    span { class: "nav-icon", "P" }
                    span { class: "nav-label", "Persona" }
                }
                Link { to: Route::Settings {}, class: "nav-item",
                    span { class: "nav-icon", "S" }
                    span { class: "nav-label", "Settings" }
                }
            }

            // Backend status indicator
            div { class: "sidebar-footer",
                div { class: "backend-status {status_class}",
                    span { class: "status-dot" }
                    span { class: "status-text", "{status_text}" }
                }
            }
        }
    }
}
