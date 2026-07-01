use std::collections::HashSet;
use dioxus::prelude::*;

use crate::app::{Db, Route};
use omi_db::unified_search::{SearchResultKind, UnifiedSearchResult};

#[component]
pub fn SearchPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let nav = use_navigator();

    let mut query = use_signal(String::new);
    let mut results = use_signal(Vec::<UnifiedSearchResult>::new);
    let mut enabled_sources = use_signal(|| SearchResultKind::all_local());
    let mut selected_idx = use_signal(|| Option::<usize>::None);
    let mut debounce_gen = use_signal(|| 0u64);

    // Debounced search: fires 300ms after last keystroke
    let db_search = db.clone();
    use_effect(move || {
        let gen = *debounce_gen.read();
        let q = query.read().clone();
        let sources = enabled_sources.read().clone();
        let db_ref = db_search.clone();

        spawn(async move {
            tokio::time::sleep(tokio::time::Duration::from_millis(300)).await;
            if *debounce_gen.peek() != gen {
                return;
            }
            if q.trim().is_empty() {
                results.set(Vec::new());
                return;
            }
            let db_snap = db_ref.read().clone();
            if let Some(Db(d)) = db_snap {
                match d.search_filtered(&q, 30, &sources) {
                    Ok(r) => results.set(r),
                    Err(e) => {
                        tracing::warn!("[SEARCH] Error: {e:#}");
                        results.set(Vec::new());
                    }
                }
            }
        });
    });

    let result_count = results.read().len();

    // Group results by kind for section headers
    let grouped = {
        let r = results.read();
        let mut groups: Vec<(SearchResultKind, Vec<UnifiedSearchResult>)> = Vec::new();
        for result in r.iter() {
            if let Some(g) = groups.iter_mut().find(|(k, _)| *k == result.kind) {
                g.1.push(result.clone());
            } else {
                groups.push((result.kind.clone(), vec![result.clone()]));
            }
        }
        groups
    };

    let all_sources = vec![
        SearchResultKind::Memory,
        SearchResultKind::Screenshot,
        SearchResultKind::Clipboard,
        SearchResultKind::File,
        SearchResultKind::Conversation,
    ];

    rsx! {
        div {
            class: "page",
            tabindex: "0",
            onkeydown: move |e| {
                let count = results.read().len();
                if count == 0 { return; }
                match e.key() {
                    Key::ArrowDown => {
                        let cur = *selected_idx.read();
                        let next = cur.map(|i| (i + 1).min(count - 1)).unwrap_or(0);
                        selected_idx.set(Some(next));
                    }
                    Key::ArrowUp => {
                        let cur = *selected_idx.read();
                        let next = cur.map(|i| i.saturating_sub(1)).unwrap_or(0);
                        selected_idx.set(Some(next));
                    }
                    Key::Enter => {
                        if let Some(idx) = *selected_idx.read() {
                            if let Some(result) = results.read().get(idx) {
                                navigate_to_result(&nav, result);
                            }
                        }
                    }
                    _ => {}
                }
            },

            h1 { class: "page-title", "Search Everything" }
            p { class: "page-subtitle", "Search across memories, conversations, screenshots, clipboard, and files." }

            div { class: "search-bar",
                input {
                    class: "search-input",
                    r#type: "text",
                    placeholder: "Start typing to search your second brain...",
                    value: "{query}",
                    oninput: move |e| {
                        query.set(e.value());
                        selected_idx.set(None);
                        debounce_gen.set(debounce_gen() + 1);
                    },
                }
            }

            // Source filter chips
            div { class: "search-filters",
                for source in all_sources.iter() {
                    {
                        let s = source.clone();
                        let s2 = source.clone();
                        let active = enabled_sources.read().contains(&s);
                        let label = s.label();
                        let chip_class = if active {
                            format!("search-filter-chip search-filter-chip-active badge-{}", label.to_lowercase())
                        } else {
                            "search-filter-chip".to_string()
                        };

                        rsx! {
                            button {
                                class: "{chip_class}",
                                onclick: move |_| {
                                    let mut sources = enabled_sources.write();
                                    let s3 = s2.clone();
                                    if sources.contains(&s3) {
                                        if sources.len() > 1 {
                                            sources.remove(&s3);
                                        }
                                    } else {
                                        sources.insert(s3);
                                    }
                                    drop(sources);
                                    debounce_gen.set(debounce_gen() + 1);
                                },
                                "{label}"
                            }
                        }
                    }
                }
            }

            if !query.read().is_empty() {
                {
                    let suffix = if result_count != 1 { "s" } else { "" };
                    rsx! {
                        p { class: "search-count text-muted",
                            "Found {result_count} result{suffix}"
                        }
                    }
                }
            }

            div { class: "search-results",
                if results.read().is_empty() && !query.read().is_empty() {
                    p { class: "text-muted", "No results found." }
                }

                {
                    let mut flat_idx = 0usize;
                    rsx! {
                        for (kind, items) in grouped.iter() {
                            div { class: "search-group",
                                h3 { class: "search-group-header",
                                    "{kind.label()} ({items.len()})"
                                }
                                for item in items.iter() {
                                    {
                                        let current_idx = flat_idx;
                                        flat_idx += 1;
                                        let is_selected = *selected_idx.read() == Some(current_idx);
                                        let item_clone = item.clone();
                                        rsx! {
                                            SearchResultCard {
                                                result: item.clone(),
                                                selected: is_selected,
                                                onclick: move |_| {
                                                    navigate_to_result(&nav, &item_clone);
                                                },
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

fn navigate_to_result(nav: &Navigator, result: &UnifiedSearchResult) {
    match result.kind {
        SearchResultKind::Memory => { nav.push(Route::Memories {}); }
        SearchResultKind::Screenshot => { nav.push(Route::Rewind {}); }
        SearchResultKind::Conversation => { nav.push(Route::Conversations {}); }
        SearchResultKind::File => {
            #[cfg(target_os = "windows")]
            {
                let _ = std::process::Command::new("explorer")
                    .arg("/select,")
                    .arg(&result.snippet)
                    .spawn();
            }
        }
        SearchResultKind::Clipboard | SearchResultKind::KnowledgeBase => {}
    }
}

#[component]
fn SearchResultCard(result: UnifiedSearchResult, selected: bool, onclick: EventHandler<MouseEvent>) -> Element {
    let badge_class = format!("badge-{}", result.kind.label().to_lowercase());
    let label = result.kind.label();
    let time_str = result.timestamp.format("%b %d %H:%M").to_string();
    let card_class = if selected {
        "search-result-card search-result-card-selected"
    } else {
        "search-result-card"
    };
    let score_str = format!("{:.1}", result.score);

    rsx! {
        div {
            class: "{card_class}",
            onclick: move |e| onclick.call(e),
            div { class: "search-result-header",
                span { class: "search-badge {badge_class}", "{label}" }
                span { class: "search-result-title", "{result.title}" }
                span { class: "search-result-score text-muted", "⬆{score_str}" }
                span { class: "search-result-time text-muted", "{time_str}" }
            }
            p { class: "search-result-snippet", "{result.snippet}" }
        }
    }
}
