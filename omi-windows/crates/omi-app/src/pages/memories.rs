use dioxus::prelude::*;

use crate::app::Db;
use omi_db::schema::Memory;

#[component]
pub fn MemoriesPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let mut memories: Signal<Vec<Memory>> = use_signal(Vec::new);
    let mut search = use_signal(String::new);

    // Load on mount
    let db_load = db.clone();
    use_effect(move || {
        if let Some(Db(ref d)) = *db_load.read() {
            match d.list_memories(200) {
                Ok(m) => memories.set(m),
                Err(e) => tracing::error!("[MEMORIES] load failed: {e}"),
            }
        }
    });

    // Refresh helper
    let mut refresh = move || {
        if let Some(Db(ref d)) = *db.read() {
            match d.list_memories(200) {
                Ok(m) => memories.set(m),
                Err(e) => tracing::error!("[MEMORIES] refresh failed: {e}"),
            }
        }
    };
    let q = search.read().to_lowercase();
    // Whether any memory matches the current filter
    let has_any = memories.read().iter().any(|m| q.is_empty() || m.content.to_lowercase().contains(&q));

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Memories" }
            p { class: "page-subtitle",
                "{memories.read().len()} memories extracted from your conversations."
            }

            div { class: "search-bar",
                input {
                    class: "search-input",
                    r#type: "text",
                    placeholder: "Filter memories...",
                    value: "{search}",
                    oninput: move |e| search.set(e.value()),
                }
            }

            div { class: "memories-controls",
                button { class: "btn btn-secondary", onclick: move |_| refresh(), "Refresh" }
            }

            if !has_any {
                div { class: "empty-state",
                    p { "No memories yet." }
                    p { class: "text-muted", "Record conversations and Omi will automatically extract important facts." }
                }
            } else {
                div { class: "memories-list",
                    for mem in memories.read().iter() {
                        if q.is_empty() || mem.content.to_lowercase().contains(&q) {
                            {
                                let mem_clone = mem.clone();
                                let db2 = db.clone();
                                let time_str = mem_clone.created_at.format("%b %d").to_string();
                                rsx! {
                                    div { class: "memory-card",
                                        key: "{mem_clone.id}",
                                        div { class: "memory-header",
                                            if let Some(ref cat) = mem_clone.category {
                                                span { class: "memory-category", "{cat}" }
                                            }
                                            span { class: "memory-date",
                                                "{time_str}"
                                            }
                                        }
                                        p { class: "memory-content", "{mem_clone.content}" }
                                        div { class: "memory-actions",
                                            button {
                                                class: "btn btn-secondary",
                                                onclick: move |_| {
                                                    let id = mem_clone.id.clone();
                                                    if let Some(Db(ref d)) = *db2.read() {
                                                        if let Err(e) = d.delete_memory(&id) {
                                                            tracing::error!("[MEMORIES] delete failed: {e}");
                                                        } else {
                                                            // reload
                                                            if let Ok(m) = d.list_memories(200) {
                                                                memories.set(m);
                                                            }
                                                        }
                                                    }
                                                },
                                                "Delete"
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
    }
}
