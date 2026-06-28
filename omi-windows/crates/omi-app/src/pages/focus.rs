use dioxus::prelude::*;

use crate::app::Db;
use crate::config::AppConfig;
use omi_db::schema::{DailyRecap, Goal};

#[component]
pub fn FocusPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let cfg: Signal<AppConfig> = use_context();
    let mut goals = use_signal(Vec::<Goal>::new);
    let mut recaps = use_signal(Vec::<DailyRecap>::new);
    let mut new_goal_text = use_signal(String::new);
    let mut generating_recap = use_signal(|| false);
    let mut stats_conversations = use_signal(|| 0i64);
    let mut stats_memories = use_signal(|| 0i64);
    let mut stats_screenshots = use_signal(|| 0i64);
    let mut stats_tasks = use_signal(|| 0i64);
    let mut stats_clipboard = use_signal(|| 0i64);
    let mut stats_apps = use_signal(|| 0usize);

    use_effect(move || {
        let db_snap = db.read().clone();
        if let Some(Db(d)) = db_snap {
            if let Ok(g) = d.list_goals(None) {
                goals.set(g);
            }
            if let Ok(r) = d.list_recaps(7) {
                recaps.set(r);
            }
            if let Ok(s) = d.get_today_stats() {
                stats_conversations.set(s.conversations);
                stats_memories.set(s.memories);
                stats_screenshots.set(s.screenshots);
                stats_tasks.set(s.tasks_completed);
                stats_clipboard.set(s.clipboard_items);
                stats_apps.set(s.apps_used.len());
            }
        }
    });

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Focus & Goals" }
            p { class: "page-subtitle", "Track your goals and review daily recaps." }

            div { class: "stats-grid",
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_conversations}" }
                    span { class: "stat-label text-muted", "Conversations" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_memories}" }
                    span { class: "stat-label text-muted", "Memories" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_screenshots}" }
                    span { class: "stat-label text-muted", "Screenshots" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_tasks}" }
                    span { class: "stat-label text-muted", "Tasks Done" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_clipboard}" }
                    span { class: "stat-label text-muted", "Clipboard" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_apps}" }
                    span { class: "stat-label text-muted", "Apps Used" }
                }
            }

            div { class: "section",
                h2 { class: "section-title", "Goals" }

                div { class: "goal-input-row",
                    input {
                        class: "search-input",
                        r#type: "text",
                        placeholder: "Add a new goal...",
                        value: "{new_goal_text}",
                        oninput: move |e| new_goal_text.set(e.value()),
                        onkeypress: move |e| {
                            if e.key() == Key::Enter {
                                let text = new_goal_text.read().clone();
                                if !text.trim().is_empty() {
                                    let db_snap = db.read().clone();
                                    if let Some(Db(d)) = db_snap {
                                        if d.insert_goal(text.trim()).is_ok() {
                                            new_goal_text.set(String::new());
                                            if let Ok(g) = d.list_goals(None) {
                                                goals.set(g);
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                    button {
                        class: "btn btn-primary",
                        onclick: move |_| {
                            let text = new_goal_text.read().clone();
                            if !text.trim().is_empty() {
                                let db_snap = db.read().clone();
                                if let Some(Db(d)) = db_snap {
                                    if d.insert_goal(text.trim()).is_ok() {
                                        new_goal_text.set(String::new());
                                        if let Ok(g) = d.list_goals(None) {
                                            goals.set(g);
                                        }
                                    }
                                }
                            }
                        },
                        "Add Goal"
                    }
                }

                div { class: "goals-list",
                    for goal in goals.read().iter() {
                        GoalCard {
                            goal: goal.clone(),
                            db: db,
                            goals_signal: goals,
                        }
                    }
                    if goals.read().is_empty() {
                        p { class: "text-muted", "No goals set. Add one above!" }
                    }
                }
            }

            div { class: "section",
                div { class: "section-title-row",
                    h2 { class: "section-title", "Daily Recaps" }
                    button {
                        class: "btn btn-small",
                        disabled: *generating_recap.read(),
                        onclick: move |_| {
                            let db_snap = db.read().clone();
                            let current_cfg = cfg.read().clone();
                            generating_recap.set(true);
                            spawn(async move {
                                if let Some(Db(d)) = db_snap {
                                    crate::daily_recap::generate_daily_recap(&d, &current_cfg).await;
                                    if let Ok(r) = d.list_recaps(7) {
                                        recaps.set(r);
                                    }
                                }
                                generating_recap.set(false);
                            });
                        },
                        if *generating_recap.read() {
                            "Generating..."
                        } else {
                            "Generate Now"
                        }
                    }
                }

                div { class: "recaps-list",
                    for recap in recaps.read().iter() {
                        RecapCard { recap: recap.clone() }
                    }
                    if recaps.read().is_empty() {
                        p { class: "text-muted", "No daily recaps yet. Click 'Generate Now' or wait for the auto-recap." }
                    }
                }
            }
        }
    }
}

#[component]
fn GoalCard(
    goal: Goal,
    db: Signal<Option<Db>>,
    mut goals_signal: Signal<Vec<Goal>>,
) -> Element {
    let is_completed = goal.status == "completed";
    let progress = goal.progress_pct;
    let goal_id = goal.id.clone();
    let goal_id_done = goal.id.clone();
    let goal_id_del = goal.id.clone();

    rsx! {
        div { class: if is_completed { "goal-card completed" } else { "goal-card" },
            div { class: "goal-content",
                span { class: "goal-text", "{goal.content}" }
                div { class: "goal-actions",
                    if !is_completed {
                        button {
                            class: "btn btn-tiny",
                            onclick: move |_| {
                                let db_snap = db.read().clone();
                                let gid = goal_id.clone();
                                if let Some(Db(d)) = db_snap {
                                    let _ = d.update_goal_progress(&gid, progress + 25);
                                    if let Ok(g) = d.list_goals(None) {
                                        goals_signal.set(g);
                                    }
                                }
                            },
                            "+25%"
                        }
                        button {
                            class: "btn btn-tiny btn-success",
                            onclick: move |_| {
                                let db_snap = db.read().clone();
                                let gid = goal_id_done.clone();
                                if let Some(Db(d)) = db_snap {
                                    let _ = d.update_goal_progress(&gid, 100);
                                    if let Ok(g) = d.list_goals(None) {
                                        goals_signal.set(g);
                                    }
                                }
                            },
                            "Done"
                        }
                    }
                    button {
                        class: "btn btn-tiny btn-danger",
                        onclick: move |_| {
                            let db_snap = db.read().clone();
                            let gid = goal_id_del.clone();
                            if let Some(Db(d)) = db_snap {
                                let _ = d.delete_goal(&gid);
                                if let Ok(g) = d.list_goals(None) {
                                    goals_signal.set(g);
                                }
                            }
                        },
                        "x"
                    }
                }
            }
            div { class: "progress-bar-container",
                div {
                    class: "progress-bar-fill",
                    style: "width: {progress}%",
                }
            }
        }
    }
}

#[component]
fn RecapCard(recap: DailyRecap) -> Element {
    let mut expanded = use_signal(|| false);

    rsx! {
        div { class: "recap-card",
            div {
                class: "recap-header",
                onclick: move |_| {
                    let cur = *expanded.read();
                    expanded.set(!cur);
                },
                span { class: "recap-date", "{recap.date}" }
                span { class: "recap-toggle", if *expanded.read() { "v" } else { ">" } }
            }
            if *expanded.read() {
                div { class: "recap-body",
                    p { "{recap.summary}" }
                }
            }
        }
    }
}
