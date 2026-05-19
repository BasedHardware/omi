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

    let filtered: Vec<Memory> = {
        let q = search.read().to_lowercase();
        memories.read().iter()
            .filter(|m| q.is_empty() || m.content.to_lowercase().contains(&q))
            .cloned()
            .collect()
    };

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

            if filtered.is_empty() {
                div { class: "empty-state",
                    p { "No memories yet." }
                    p { class: "text-muted", "Record conversations and Omi will automatically extract important facts." }
                }
            } else {
                div { class: "memories-list",
                    for mem in filtered.iter() {
                        div { class: "memory-card",
                            key: "{mem.id}",
                            div { class: "memory-header",
                                if let Some(ref cat) = mem.category {
                                    span { class: "memory-category", "{cat}" }
                                }
                                span { class: "memory-date",
                                    "{mem.created_at.format(\"%b %d\")}"
                                }
                            }
                            p { class: "memory-content", "{mem.content}" }
                        }
                    }
                }
            }
        }
    }
}
