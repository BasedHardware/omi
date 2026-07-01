use dioxus::prelude::*;

use crate::app::Db;
use crate::config::AppConfig;
use crate::google_calendar::sync_google_calendar;
use crate::knowledge::KnowledgeResource;

#[derive(Clone, Debug, PartialEq)]
enum SyncStatus {
    Idle,
    Syncing,
    Success { memories: usize, tasks: usize },
    Error(String),
}

#[derive(Clone, Debug, PartialEq)]
enum KbStatus {
    Idle,
    Uploading,
    Searching,
    UploadDone(String),
    SearchResults(Vec<String>),
    Error(String),
}

fn file_type_icon(ft: Option<&str>) -> &'static str {
    match ft {
        Some("pdf") => "📄",
        Some("txt") | Some("text") => "📝",
        Some("md") | Some("markdown") => "📋",
        Some("csv") => "📊",
        Some("json") => "{ }",
        Some("docx") | Some("doc") => "📃",
        _ => "📎",
    }
}

#[component]
pub fn AppsPage() -> Element {
    let config = use_context::<Signal<AppConfig>>();
    let db_opt = use_context::<Signal<Option<Db>>>();
    let mut sync_status = use_signal(|| SyncStatus::Idle);
    let mut kb_status = use_signal(|| KbStatus::Idle);
    let mut kb_query = use_signal(String::new);
    let mut kb_resources = use_signal(Vec::<KnowledgeResource>::new);
    let mut upload_path = use_signal(String::new);
    let mut drop_active = use_signal(|| false);
    let mut selected_doc = use_signal(|| Option::<KnowledgeResource>::None);
    let mut doc_chunks = use_signal(Vec::<String>::new);

    use_effect(move || {
        let cfg = config.read().clone();
        if cfg.mcp_enabled {
            spawn(async move {
                if let Ok(res) = crate::knowledge::list_resources(&cfg).await {
                    kb_resources.set(res);
                }
            });
        }
    });

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Apps & Integrations" }
            p { class: "page-subtitle", "Connect your tools and extend Omi's powers." }

            // ── Knowledge Base ─────────────────────────────────────────
            div { class: "section",
                h2 { class: "section-title", "Knowledge Base" }
                p { class: "text-muted", style: "margin-bottom: 16px;",
                    "Upload documents (PDF, TXT, MD) and ask questions about them. Powered by RAG semantic search."
                }

                // Drop zone + Upload
                div {
                    class: if *drop_active.read() { "kb-dropzone kb-dropzone-active" } else { "kb-dropzone" },
                    ondragover: move |e| {
                        e.prevent_default();
                        drop_active.set(true);
                    },
                    ondragleave: move |_| {
                        drop_active.set(false);
                    },
                    // Note: Dioxus webview ondrop with file data requires platform support.
                    // Fallback to manual path input.

                    if *drop_active.read() {
                        p { class: "kb-drop-text", "Drop files here to upload" }
                    } else {
                        div { class: "kb-upload-row",
                            input {
                                class: "search-input",
                                r#type: "text",
                                placeholder: "Paste file path to upload (e.g. C:\\docs\\proposal.pdf)",
                                value: "{upload_path}",
                                oninput: move |e| upload_path.set(e.value()),
                            }
                            button {
                                class: "btn btn-primary",
                                disabled: upload_path.read().trim().is_empty() || matches!(*kb_status.read(), KbStatus::Uploading),
                                onclick: move |_| {
                                    let path = upload_path.read().trim().to_string();
                                    if path.is_empty() { return; }
                                    let cfg = config.read().clone();
                                    kb_status.set(KbStatus::Uploading);
                                    spawn(async move {
                                        match crate::knowledge::upload_document(&path, &cfg).await {
                                            Ok(name) => {
                                                kb_status.set(KbStatus::UploadDone(name));
                                                upload_path.set(String::new());
                                                if let Ok(res) = crate::knowledge::list_resources(&cfg).await {
                                                    kb_resources.set(res);
                                                }
                                            }
                                            Err(e) => kb_status.set(KbStatus::Error(format!("{e:#}"))),
                                        }
                                    });
                                },
                                if matches!(*kb_status.read(), KbStatus::Uploading) { "Uploading..." } else { "Upload" }
                            }
                        }
                    }
                }

                // Upload progress bar
                if matches!(*kb_status.read(), KbStatus::Uploading) {
                    div { class: "kb-progress-bar-container",
                        div { class: "kb-progress-bar" }
                    }
                }

                // Search
                div { class: "kb-search-row",
                    input {
                        class: "search-input",
                        r#type: "text",
                        placeholder: "Ask a question about your documents...",
                        value: "{kb_query}",
                        oninput: move |e| kb_query.set(e.value()),
                        onkeypress: move |e| {
                            if e.key() == Key::Enter {
                                let q = kb_query.read().clone();
                                if q.trim().is_empty() { return; }
                                let cfg = config.read().clone();
                                kb_status.set(KbStatus::Searching);
                                spawn(async move {
                                    match crate::knowledge::search_knowledge(&q, &cfg).await {
                                        Ok(results) => {
                                            let texts: Vec<String> = results.iter().map(|r| {
                                                let src = r.source.as_deref().unwrap_or("doc");
                                                format!("[{src}] {}", r.content)
                                            }).collect();
                                            kb_status.set(KbStatus::SearchResults(texts));
                                        }
                                        Err(e) => kb_status.set(KbStatus::Error(format!("{e:#}"))),
                                    }
                                });
                            }
                        },
                    }
                    button {
                        class: "btn btn-secondary",
                        disabled: kb_query.read().trim().is_empty(),
                        onclick: move |_| {
                            let q = kb_query.read().clone();
                            if q.trim().is_empty() { return; }
                            let cfg = config.read().clone();
                            kb_status.set(KbStatus::Searching);
                            spawn(async move {
                                match crate::knowledge::search_knowledge(&q, &cfg).await {
                                    Ok(results) => {
                                        let texts: Vec<String> = results.iter().map(|r| {
                                            let src = r.source.as_deref().unwrap_or("doc");
                                            format!("[{src}] {}", r.content)
                                        }).collect();
                                        kb_status.set(KbStatus::SearchResults(texts));
                                    }
                                    Err(e) => kb_status.set(KbStatus::Error(format!("{e:#}"))),
                                }
                            });
                        },
                        "Search"
                    }
                }

                // Status / results
                match &*kb_status.read() {
                    KbStatus::Idle => rsx! {},
                    KbStatus::Uploading => rsx! {},
                    KbStatus::Searching => rsx! { p { class: "text-muted", "Searching..." } },
                    KbStatus::UploadDone(name) => rsx! {
                        p { class: "text-success", "Uploaded: {name}" }
                    },
                    KbStatus::SearchResults(results) => rsx! {
                        div { class: "kb-results",
                            if results.is_empty() {
                                p { class: "text-muted", "No results found." }
                            }
                            for (i, result) in results.iter().enumerate() {
                                div { class: "kb-result-card",
                                    span { class: "kb-result-idx", "{i+1}." }
                                    span { "{result}" }
                                }
                            }
                        }
                    },
                    KbStatus::Error(e) => rsx! {
                        p { class: "text-error", "Error: {e}" }
                    },
                }

                // Indexed documents list
                if !kb_resources.read().is_empty() {
                    div { class: "kb-resources",
                        h3 { "Indexed Documents" }
                        for res in kb_resources.read().iter() {
                            {
                                let icon = file_type_icon(res.file_type.as_deref());
                                let res_clone = res.clone();
                                rsx! {
                                    div {
                                        class: "kb-resource-row",
                                        onclick: move |_| {
                                            let r = res_clone.clone();
                                            let cfg = config.read().clone();
                                            selected_doc.set(Some(r.clone()));
                                            doc_chunks.set(Vec::new());
                                            spawn(async move {
                                                if let Ok(chunks) = crate::knowledge::get_document_chunks(&r.id, &cfg).await {
                                                    doc_chunks.set(chunks);
                                                }
                                            });
                                        },
                                        span { class: "kb-file-icon", "{icon}" }
                                        span { class: "kb-resource-name", "{res.name}" }
                                        span { class: "text-muted kb-resource-type",
                                            "{res.file_type.as_deref().unwrap_or(\"?\")}"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Document preview panel
                if let Some(doc) = selected_doc.read().as_ref() {
                    div { class: "kb-preview",
                        div { class: "kb-preview-header",
                            h3 { "{doc.name}" }
                            button {
                                class: "btn btn-secondary btn-sm",
                                onclick: move |_| selected_doc.set(None),
                                "Close"
                            }
                        }
                        if doc_chunks.read().is_empty() {
                            p { class: "text-muted", "Loading chunks..." }
                        } else {
                            div { class: "kb-chunks",
                                for (i, chunk) in doc_chunks.read().iter().enumerate() {
                                    div { class: "kb-chunk-card",
                                        span { class: "kb-chunk-idx text-muted", "Chunk {i+1}" }
                                        p { "{chunk}" }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Integrations Grid ──────────────────────────────────────
            div { class: "section",
                h2 { class: "section-title", "Integrations" }
                div { class: "card-grid",
                    div { class: "card",
                        style: "display: flex; flex-direction: column; justify-content: space-between; min-height: 180px;",
                        div {
                            h3 { "Google Calendar" }
                            p { class: "text-muted", "Extract events and tasks from your calendar." }
                        }
                        div {
                            match &*sync_status.read() {
                                SyncStatus::Idle => rsx! {
                                    button {
                                        class: "btn btn-primary",
                                        onclick: move |_| {
                                            let db_sig = db_opt.clone();
                                            let cfg_sig = config.clone();
                                            sync_status.set(SyncStatus::Syncing);
                                            spawn(async move {
                                                let db_snap = db_sig.read().clone();
                                                if let Some(Db(d)) = db_snap {
                                                    let cfg = cfg_sig.read().clone();
                                                    match sync_google_calendar(&d, &cfg).await {
                                                        Ok((m, t)) => sync_status.set(SyncStatus::Success { memories: m, tasks: t }),
                                                        Err(e) => sync_status.set(SyncStatus::Error(e.to_string())),
                                                    }
                                                }
                                            });
                                        },
                                        "Sync Calendar"
                                    }
                                },
                                SyncStatus::Syncing => rsx! {
                                    button { class: "btn btn-secondary", disabled: true, "Syncing..." }
                                },
                                SyncStatus::Success { memories, tasks } => rsx! {
                                    p { class: "text-success", style: "font-size: 13px;",
                                        "Synced: {memories} memories, {tasks} tasks"
                                    }
                                },
                                SyncStatus::Error(e) => rsx! {
                                    p { class: "text-error", style: "font-size: 12px;", "{e}" }
                                },
                            }
                        }
                    }

                    div { class: "card",
                        h3 { "Google MCP Tools" }
                        p { class: "text-muted", "Gmail, Calendar, Drive access via MCP bridge." }
                        p { class: "text-muted", style: "font-size: 12px; margin-top: 8px;",
                            if config.read().mcp_enabled { "Status: Enabled" } else { "Status: Disabled (enable in Settings)" }
                        }
                    }

                    div { class: "card",
                        h3 { "Slack" }
                        p { class: "text-muted", "Send conversation summaries to Slack channels." }
                        span { class: "text-muted", style: "font-size: 11px;", "Coming soon" }
                    }

                    div { class: "card",
                        h3 { "GitHub" }
                        p { class: "text-muted", "Create issues from action items." }
                        span { class: "text-muted", style: "font-size: 11px;", "Coming soon" }
                    }

                    div { class: "card",
                        h3 { "Notion" }
                        p { class: "text-muted", "Export memories and notes to Notion." }
                        span { class: "text-muted", style: "font-size: 11px;", "Coming soon" }
                    }
                }
            }
        }
    }
}
