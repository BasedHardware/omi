use dioxus::prelude::*;

use crate::app::Route;
use crate::notification_history::NotificationEntry;
use crate::sidecar::BackendStatus;

#[component]
pub fn Sidebar() -> Element {
    let backend_status: Signal<BackendStatus> = use_context();
    let mut notif_history: Signal<Vec<NotificationEntry>> = use_context();
    let mut notif_open = use_signal(|| false);

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

    let notif_count = notif_history.read().len();

    rsx! {
        nav { class: "sidebar",
            // Brand + notification bell
            div { class: "sidebar-brand",
                span { class: "brand-logo", "O" }
                span { class: "brand-text", "Omi" }
                div { class: "notif-bell-container",
                    button {
                        class: "notif-bell-btn",
                        title: "Notification history",
                        onclick: move |_| {
                            let cur = *notif_open.read();
                            notif_open.set(!cur);
                        },
                        span { "🔔" }
                        if notif_count > 0 {
                            span { class: "notif-badge", "{notif_count}" }
                        }
                    }
                    if *notif_open.read() {
                        div { class: "notif-dropdown",
                            div { class: "notif-dropdown-header",
                                span { "Notifications" }
                                if notif_count > 0 {
                                    button {
                                        class: "notif-clear-btn",
                                        onclick: move |_| {
                                            notif_history.write().clear();
                                        },
                                        "Clear"
                                    }
                                }
                            }
                            if notif_count == 0 {
                                p { class: "notif-empty text-muted", "No notifications yet." }
                            } else {
                                div { class: "notif-list",
                                    for entry in notif_history.read().iter().rev().take(20) {
                                        div { class: "notif-item",
                                            div { class: "notif-item-header",
                                                span { class: "notif-item-title", "{entry.title}" }
                                                span { class: "notif-item-time text-muted", "{entry.time_str()}" }
                                            }
                                            p { class: "notif-item-body", "{entry.body}" }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Navigation links
            div { class: "sidebar-nav",
                Link { to: Route::Dashboard {}, class: "nav-item",
                    span { class: "nav-icon", "H" }
                    span { class: "nav-label", "Dashboard" }
                }
                Link { to: Route::Search {}, class: "nav-item",
                    span { class: "nav-icon", "Q" }
                    span { class: "nav-label", "Search" }
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
