use dioxus::prelude::*;

use crate::app::Db;
use omi_db::unified_search::{SearchResultKind, UnifiedSearchResult};

fn run_search(
    query: &str,
    db: &Signal<Option<Db>>,
    results: &mut Signal<Vec<UnifiedSearchResult>>,
) {
    if query.trim().is_empty() {
        results.set(Vec::new());
        return;
    }
    let db_snap = db.read().clone();
    if let Some(Db(d)) = db_snap {
        match d.search_all(query, 30) {
            Ok(r) => results.set(r),
            Err(e) => {
                tracing::warn!("[SEARCH] Error: {e:#}");
                results.set(Vec::new());
            }
        }
    }
}

#[component]
pub fn SearchPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let mut query = use_signal(String::new);
    let mut results = use_signal(Vec::<UnifiedSearchResult>::new);

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Search Everything" }
            p { class: "page-subtitle", "Search across memories, conversations, screenshots, clipboard, and files." }

            div { class: "search-bar",
                input {
                    class: "search-input",
                    r#type: "text",
                    placeholder: "Search your second brain...",
                    value: "{query}",
                    oninput: move |e| query.set(e.value()),
                    onkeypress: move |e| {
                        if e.key() == Key::Enter {
                            let q = query.read().clone();
                            run_search(&q, &db, &mut results);
                        }
                    },
                }
                button {
                    class: "btn btn-primary",
                    onclick: move |_| {
                        let q = query.read().clone();
                        run_search(&q, &db, &mut results);
                    },
                    "Search"
                }
            }

            div { class: "search-results",
                if results.read().is_empty() && !query.read().is_empty() {
                    p { class: "text-muted", "No results found." }
                }

                for result in results.read().iter() {
                    SearchResultCard { result: result.clone() }
                }
            }
        }
    }
}

#[component]
fn SearchResultCard(result: UnifiedSearchResult) -> Element {
    let (badge, badge_class) = match result.kind {
        SearchResultKind::Memory => ("Memory", "badge-memory"),
        SearchResultKind::Screenshot => ("Screenshot", "badge-screenshot"),
        SearchResultKind::Clipboard => ("Clipboard", "badge-clipboard"),
        SearchResultKind::File => ("File", "badge-file"),
        SearchResultKind::Conversation => ("Conversation", "badge-conversation"),
    };

    let time_str = result.timestamp.format("%b %d %H:%M").to_string();

    rsx! {
        div { class: "search-result-card",
            div { class: "search-result-header",
                span { class: "search-badge {badge_class}", "{badge}" }
                span { class: "search-result-title", "{result.title}" }
                span { class: "search-result-time text-muted", "{time_str}" }
            }
            p { class: "search-result-snippet", "{result.snippet}" }
        }
    }
}
