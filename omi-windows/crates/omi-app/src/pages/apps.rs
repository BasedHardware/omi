use dioxus::prelude::*;
use crate::config::AppConfig;
use crate::app::Db;
use crate::google_calendar::sync_google_calendar;

#[derive(Clone, Debug, PartialEq)]
enum SyncStatus {
    Idle,
    Syncing,
    Success { memories: usize, tasks: usize },
    Error(String),
}

#[component]
pub fn AppsPage() -> Element {
    let config = use_context::<Signal<AppConfig>>();
    let db_opt = use_context::<Signal<Option<Db>>>();
    
    let sync_status = use_signal(|| SyncStatus::Idle);

    let on_sync_click = move |_| {
        let db_sig = db_opt.clone();
        let cfg_sig = config.clone();
        let mut status = sync_status.clone();
        
        status.set(SyncStatus::Syncing);
        
        spawn(async move {
            let db_snap = db_sig.read().clone();
            if let Some(Db(d)) = db_snap {
                let cfg = cfg_sig.read().clone();
                match sync_google_calendar(&d, &cfg).await {
                    Ok((m_count, t_count)) => {
                        status.set(SyncStatus::Success { memories: m_count, tasks: t_count });
                    }
                    Err(e) => {
                        status.set(SyncStatus::Error(e.to_string()));
                    }
                }
            } else {
                status.set(SyncStatus::Error("Database is not available.".to_string()));
            }
        });
    };

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Apps & Integrations" }
            p { class: "page-subtitle", "Browse and manage your local integrations." }

            div { class: "card-grid",
                div { class: "card",
                    h3 { "Slack" }
                    p { class: "text-muted", "Send conversation summaries to Slack channels." }
                }
                div { class: "card",
                    h3 { "GitHub" }
                    p { class: "text-muted", "Create issues from action items." }
                }
                div { class: "card",
                    h3 { "Notion" }
                    p { class: "text-muted", "Export memories and notes to Notion." }
                }
                div { class: "card",
                    style: "display: flex; flex-direction: column; justify-content: space-between; min-height: 200px;",
                    div {
                        h3 { "Google Calendar" }
                        p { class: "text-muted", style: "margin-bottom: 12px;", "Automatically extract important events and tasks from your Google Calendar." }
                    }
                    div {
                        match &*sync_status.read() {
                            SyncStatus::Idle => rsx! {
                                button {
                                    class: "btn btn-primary",
                                    onclick: on_sync_click,
                                    "Sync Calendar"
                                }
                            },
                            SyncStatus::Syncing => rsx! {
                                button {
                                    class: "btn btn-secondary",
                                    disabled: true,
                                    "Syncing..."
                                }
                            },
                            SyncStatus::Success { memories, tasks } => rsx! {
                                div {
                                    p { style: "color: var(--success); font-weight: 500; font-size: 13px; margin-bottom: 8px;",
                                        "✓ Sync completed successfully!"
                                    }
                                    p { class: "text-muted", style: "font-size: 12px; margin-bottom: 8px;",
                                        "Added {memories} memories and {tasks} tasks."
                                    }
                                    button {
                                        class: "btn btn-secondary",
                                        onclick: on_sync_click,
                                        "Sync Again"
                                    }
                                }
                            },
                            SyncStatus::Error(err_msg) => rsx! {
                                div {
                                    p { style: "color: var(--error); font-weight: 500; font-size: 13px; margin-bottom: 8px;",
                                        "✗ Sync failed"
                                    }
                                    p { class: "text-muted", style: "font-size: 11px; margin-bottom: 8px; max-width: 220px; word-wrap: break-word;",
                                        "{err_msg}"
                                    }
                                    button {
                                        class: "btn btn-primary",
                                        onclick: on_sync_click,
                                        "Retry Sync"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
