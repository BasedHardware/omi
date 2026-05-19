use dioxus::prelude::*;

use crate::app::Db;
use omi_db::schema::ActionItem;

#[component]
pub fn TasksPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let mut tasks: Signal<Vec<ActionItem>> = use_signal(Vec::new);

    let db_load = db.clone();
    use_effect(move || {
        if let Some(Db(ref d)) = *db_load.read() {
            match d.list_action_items(200) {
                Ok(t) => tasks.set(t),
                Err(e) => tracing::error!("[TASKS] load failed: {e}"),
            }
        }
    });

    let incomplete = tasks.read().iter().filter(|t| !t.completed).count();
    let total = tasks.read().len();

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Tasks" }
            p { class: "page-subtitle",
                "{incomplete} open · {total} total"
            }

            if tasks.read().is_empty() {
                div { class: "empty-state",
                    p { "No tasks yet." }
                    p { class: "text-muted", "Record conversations and Omi will automatically extract action items." }
                }
            } else {
                div { class: "tasks-list",
                    for task in tasks.read().iter() {
                        {
                            let task_id = task.id.clone();
                            let is_done = task.completed;
                            let db2 = db.clone();

                            rsx! {
                                div {
                                    key: "{task_id}",
                                    class: if is_done { "task-item completed" } else { "task-item" },
                                    label { class: "task-label",
                                        input {
                                            r#type: "checkbox",
                                            checked: is_done,
                                            onchange: move |_| {
                                                if let Some(Db(ref d)) = *db2.read() {
                                                    match d.toggle_action_item(&task_id) {
                                                        Ok(_) => {
                                                            // Reload
                                                            if let Ok(t) = d.list_action_items(200) {
                                                                tasks.set(t);
                                                            }
                                                        }
                                                        Err(e) => tracing::error!("[TASKS] toggle failed: {e}"),
                                                    }
                                                }
                                            },
                                        }
                                        span { class: "task-text", "{task.content}" }
                                    }
                                    span { class: "task-date text-muted",
                                        "{task.created_at.format(\"%b %d\")}"
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
