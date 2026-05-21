use dioxus::prelude::*;

use crate::app::Db;
use crate::config::AppConfig;
use omi_db::schema::Memory;

// ── Category helpers ──────────────────────────────────────────────────────────

const CATEGORIES: &[(&str, &str)] = &[
    ("all",          "All"),
    ("fact",         "Facts"),
    ("preference",   "Preferences"),
    ("decision",     "Decisions"),
    ("commitment",   "Commitments"),
    ("relationship", "Relationships"),
    ("technical",    "Technical"),
    ("screenshot",   "Screen"),
    ("other",        "Other"),
];

fn category_color(cat: &str) -> &'static str {
    match cat {
        "fact"         => "mem-cat-fact",
        "preference"   => "mem-cat-preference",
        "decision"     => "mem-cat-decision",
        "commitment"   => "mem-cat-commitment",
        "relationship" => "mem-cat-relationship",
        "technical"    => "mem-cat-technical",
        "screenshot"   => "mem-cat-screenshot",
        _              => "mem-cat-other",
    }
}

#[component]
pub fn MemoriesPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let config: Signal<AppConfig> = use_context();

    let mut memories: Signal<Vec<Memory>> = use_signal(Vec::new);
    let mut search = use_signal(String::new);
    let mut active_cat = use_signal(|| "all".to_string());
    let is_deduping = use_signal(|| false);

    // Load on mount
    let db_load = db.clone();
    use_effect(move || {
        if let Some(Db(ref d)) = *db_load.read() {
            match d.list_memories(500) {
                Ok(m) => memories.set(m),
                Err(e) => tracing::error!("[MEMORIES] load failed: {e}"),
            }
        }
    });

    let mut reload = move || {
        if let Some(Db(ref d)) = *db.read() {
            if let Ok(m) = d.list_memories(500) { memories.set(m); }
        }
    };

    // Derived state
    let q = search.read().to_lowercase();
    let cat = active_cat.read().clone();

    let filtered: Vec<Memory> = memories.read().iter()
        .filter(|m| {
            let cat_match = cat == "all"
                || m.category.as_deref().unwrap_or("other") == cat.as_str();
            let q_match = q.is_empty() || m.content.to_lowercase().contains(&q);
            cat_match && q_match
        })
        .cloned()
        .collect();

    // Count per category for pills
    let counts = {
        let mut map: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
        for m in memories.read().iter() {
            *map.entry(m.category.as_deref().unwrap_or("other").to_string()).or_insert(0) += 1;
        }
        map
    };
    let total = memories.read().len();

    rsx! {
        div { class: "page page-memories",

            div { class: "memories-header",
                div {
                    h1 { class: "page-title", "Memories" }
                    p { class: "page-subtitle",
                        "{total} stored · {filtered.len()} shown"
                    }
                }
                div { class: "memories-header-actions",
                    button { class: "btn btn-secondary", onclick: move |_| reload(), "↻ Refresh" }
                    if *is_deduping.read() {
                        button { class: "btn btn-secondary", disabled: true, "Deduplicating…" }
                    } else {
                        button {
                            class: "btn btn-secondary",
                            title: "Use LLM to identify and remove near-duplicate memories",
                            onclick: move |_| {
                                let db_val = db.read().clone();
                                let cfg = config.read().clone();
                                let mut deduping = is_deduping.clone();
                                let mut mems = memories.clone();
                                spawn(async move {
                                    deduping.set(true);
                                    if let Some(Db(ref d)) = db_val {
                                        match crate::llm::deduplicate_memories(d, &cfg).await {
                                            Ok(removed) => {
                                                tracing::info!("[MEMORIES] Dedup removed {removed} memories");
                                                if let Ok(m) = d.list_memories(500) { mems.set(m); }
                                            }
                                            Err(e) => tracing::error!("[MEMORIES] Dedup failed: {e}"),
                                        }
                                    }
                                    deduping.set(false);
                                });
                            },
                            "✦ Deduplicate"
                        }
                    }
                }
            }

            div { class: "search-bar",
                input {
                    class: "search-input",
                    r#type: "text",
                    placeholder: "Search memories…",
                    value: "{search}",
                    oninput: move |e| search.set(e.value()),
                }
            }

            // Category filter pills
            div { class: "mem-category-filters",
                for (slug, label) in CATEGORIES {
                    {
                        let slug_str = slug.to_string();
                        let is_active = *slug == cat.as_str();
                        let count = if *slug == "all" { total } else { counts.get(*slug).copied().unwrap_or(0) };
                        if *slug == "all" || count > 0 {
                            rsx! {
                                button {
                                    key: "{slug_str}",
                                    class: if is_active { "mem-filter-pill active" } else { "mem-filter-pill" },
                                    onclick: { let s = slug_str.clone(); move |_| active_cat.set(s.clone()) },
                                    "{label}"
                                    span { class: "mem-filter-count", "{count}" }
                                }
                            }
                        } else {
                            rsx! { }
                        }
                    }
                }
            }

            // Memory list
            if filtered.is_empty() {
                div { class: "empty-state",
                    p { if q.is_empty() && cat == "all" { "No memories yet." } else { "No memories match this filter." } }
                    if q.is_empty() && cat == "all" {
                        p { class: "text-muted",
                            "Omi extracts only specific, durable facts — you'll see fewer but higher-quality memories."
                        }
                    }
                }
            } else {
                div { class: "memories-list",
                    for mem in filtered.clone() {
                        {
                            let mem_id = mem.id.clone();
                            let cat_slug = mem.category.clone().unwrap_or_else(|| "other".to_string());
                            let cat_class = category_color(&cat_slug);
                            let time_str = mem.created_at.format("%b %d · %H:%M").to_string();
                            let db2 = db.clone();
                            let mut mems_sig = memories.clone();

                            rsx! {
                                div { class: "memory-card", key: "{mem_id}",
                                    div { class: "memory-card-accent {cat_class}" }
                                    div { class: "memory-card-body",
                                        div { class: "memory-meta",
                                            span { class: "memory-category-badge {cat_class}", "{cat_slug}" }
                                            span { class: "memory-date text-muted", "{time_str}" }
                                        }
                                        p { class: "memory-content", "{mem.content}" }
                                    }
                                    button {
                                        class: "mem-delete-btn",
                                        title: "Delete",
                                        onclick: move |_| {
                                            if let Some(Db(ref d)) = *db2.read() {
                                                if d.delete_memory(&mem_id).is_ok() {
                                                    if let Ok(m) = d.list_memories(500) {
                                                        mems_sig.set(m);
                                                    }
                                                }
                                            }
                                        },
                                        "✕"
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
