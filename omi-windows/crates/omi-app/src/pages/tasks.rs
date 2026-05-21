use dioxus::prelude::*;

use crate::app::Db;
use omi_db::schema::ActionItem;

#[derive(Debug, Clone, PartialEq)]
enum TaskFilter { All, Open, Done }

#[component]
pub fn TasksPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let mut tasks: Signal<Vec<ActionItem>> = use_signal(Vec::new);
    let mut search = use_signal(String::new);
    let mut filter = use_signal(|| TaskFilter::Open);

    let db_load = db.clone();
    use_effect(move || {
        if let Some(Db(ref d)) = *db_load.read() {
            match d.list_action_items(500) {
                Ok(t) => tasks.set(t),
                Err(e) => tracing::error!("[TASKS] load failed: {e}"),
            }
        }
    });

    let mut reload = move || {
        if let Some(Db(ref d)) = *db.read() {
            if let Ok(t) = d.list_action_items(500) { tasks.set(t); }
        }
    };

    let q = search.read().to_lowercase();
    let f = filter.read().clone();

    let filtered: Vec<ActionItem> = tasks.read().iter()
        .filter(|t| {
            let filter_match = match f {
                TaskFilter::All  => true,
                TaskFilter::Open => !t.completed,
                TaskFilter::Done => t.completed,
            };
            let q_match = q.is_empty() || t.content.to_lowercase().contains(&q);
            filter_match && q_match
        })
        .cloned()
        .collect();

    let open_count = tasks.read().iter().filter(|t| !t.completed).count();
    let done_count = tasks.read().iter().filter(|t| t.completed).count();
    let total = tasks.read().len();

    rsx! {
        div { class: "page page-tasks",

            // ── Header ──────────────────────────────────────────────────────────
            div { class: "tasks-header",
                div {
                    h1 { class: "page-title", "Tasks" }
                    p { class: "page-subtitle",
                        "{open_count} open · {done_count} done · {total} total"
                    }
                }
                div { class: "tasks-header-actions",
                    button { class: "btn btn-secondary", onclick: move |_| reload(), "↻ Refresh" }
                    if done_count > 0 {
                        button {
                            class: "btn btn-secondary",
                            title: "Remove all completed tasks",
                            onclick: move |_| {
                                if let Some(Db(ref d)) = *db.read() {
                                    match d.delete_completed_action_items() {
                                        Ok(n) => {
                                            tracing::info!("[TASKS] Deleted {n} completed tasks");
                                            if let Ok(t) = d.list_action_items(500) { tasks.set(t); }
                                        }
                                        Err(e) => tracing::error!("[TASKS] bulk delete failed: {e}"),
                                    }
                                }
                            },
                            "✕ Clear done"
                        }
                    }
                }
            }

            // ── Search ───────────────────────────────────────────────────────────
            div { class: "search-bar",
                input {
                    class: "search-input",
                    r#type: "text",
                    placeholder: "Search tasks…",
                    value: "{search}",
                    oninput: move |e| search.set(e.value()),
                }
            }

            // ── Filter tabs ──────────────────────────────────────────────────────
            div { class: "task-filter-tabs",
                button {
                    class: if f == TaskFilter::Open { "task-tab active" } else { "task-tab" },
                    onclick: move |_| filter.set(TaskFilter::Open),
                    "Open"
                    span { class: "task-tab-count", "{open_count}" }
                }
                button {
                    class: if f == TaskFilter::All { "task-tab active" } else { "task-tab" },
                    onclick: move |_| filter.set(TaskFilter::All),
                    "All"
                    span { class: "task-tab-count", "{total}" }
                }
                button {
                    class: if f == TaskFilter::Done { "task-tab active" } else { "task-tab" },
                    onclick: move |_| filter.set(TaskFilter::Done),
                    "Done"
                    span { class: "task-tab-count", "{done_count}" }
                }
            }

            // ── Task list ────────────────────────────────────────────────────────
            if filtered.is_empty() {
                div { class: "empty-state",
                    p {
                        if total == 0 {
                            "No tasks yet."
                        } else {
                            "No tasks match this filter."
                        }
                    }
                    if total == 0 {
                        p { class: "text-muted",
                            "Record conversations — Omi extracts specific, actionable tasks the user explicitly committed to."
                        }
                    }
                }
            } else {
                div { class: "tasks-list",
                    for task in filtered.clone() {
                        {
                            let task_id_toggle = task.id.clone();
                            let task_id_delete = task.id.clone();
                            let is_done = task.completed;
                            let date_str = task.created_at.format("%b %d").to_string();
                            let db_toggle = db.clone();
                            let db_delete = db.clone();
                            let mut tasks_toggle = tasks.clone();
                            let mut tasks_delete = tasks.clone();

                            rsx! {
                                div {
                                    key: "{task_id_toggle}",
                                    class: if is_done { "task-item task-done" } else { "task-item" },
                                    label { class: "task-check-label",
                                        input {
                                            r#type: "checkbox",
                                            checked: is_done,
                                            onchange: move |_| {
                                                if let Some(Db(ref d)) = *db_toggle.read() {
                                                    if d.toggle_action_item(&task_id_toggle).is_ok() {
                                                        if let Ok(t) = d.list_action_items(500) {
                                                            tasks_toggle.set(t);
                                                        }
                                                    }
                                                }
                                            },
                                        }
                                        span {
                                            class: if is_done { "task-text task-text-done" } else { "task-text" },
                                            "{task.content}"
                                        }
                                    }
                                    div { class: "task-meta",
                                        span { class: "task-date text-muted", "{date_str}" }
                                        button {
                                            class: "task-delete-btn",
                                            title: "Delete task",
                                            onclick: move |_| {
                                                if let Some(Db(ref d)) = *db_delete.read() {
                                                    if d.delete_action_item(&task_id_delete).is_ok() {
                                                        if let Ok(t) = d.list_action_items(500) {
                                                            tasks_delete.set(t);
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
}
