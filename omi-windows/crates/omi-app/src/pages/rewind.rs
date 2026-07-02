use dioxus::prelude::*;

use crate::app::Db;
use crate::config::AppConfig;
use omi_db::schema::Screenshot;

// ── Child component: one thumbnail card ──────────────────────────────────────

#[component]
fn RewindThumb(shot: Screenshot, is_selected: bool, on_click: EventHandler<Screenshot>) -> Element {
    let time_str = shot.captured_at.format("%H:%M:%S").to_string();
    let title_short = shot.window_title.clone().unwrap_or_default();
    let title_short = if title_short.len() > 30 {
        format!("{}…", &title_short[..30])
    } else {
        title_short
    };
    let path = shot.thumbnail_path.clone();
    let cls = if is_selected { "rewind-thumb rewind-thumb-selected" } else { "rewind-thumb" };

    rsx! {
        div {
            class: "{cls}",
            onclick: move |_| on_click.call(shot.clone()),
            if let Some(ref p) = path {
                img {
                    class: "rewind-thumb-img",
                    src: "{p}",
                    alt: "Screenshot",
                }
            } else {
                div { class: "rewind-thumb-placeholder", "📷" }
            }
            div { class: "rewind-thumb-meta",
                span { "{time_str}" }
                if !title_short.is_empty() {
                    span { class: "text-muted", "{title_short}" }
                }
            }
        }
    }
}

// ── Detail panel component ────────────────────────────────────────────────────

#[component]
fn RewindDetail(shot: Screenshot, on_close: EventHandler<()>) -> Element {
    let time_str = shot.captured_at.format("%b %d %H:%M:%S").to_string();
    let path = shot.thumbnail_path.clone();
    let ocr = shot.ocr_text.clone();
    let title = shot.window_title.clone();
    let app = shot.app_name.clone();
    let cfg: Signal<AppConfig> = use_context();
    let db: Signal<Option<crate::app::Db>> = use_context();

    let has_video = cfg.read().video_chunk_encoding_enabled;

    rsx! {
        div { class: "rewind-detail",
            div { class: "rewind-detail-header",
                span { class: "text-muted", "{time_str}" }
                if let Some(ref a) = app {
                    span { class: "badge", "{a}" }
                }
                if let Some(t) = title {
                    span { class: "rewind-window-title", "{t}" }
                }
                button {
                    class: "btn btn-secondary",
                    onclick: move |_| on_close.call(()),
                    "Close"
                }
            }
            if let Some(p) = path {
                img {
                    class: "rewind-screenshot",
                    src: "{p}",
                    alt: "Screenshot",
                }
            }
            if let Some(text) = ocr {
                div { class: "rewind-ocr",
                    h4 { "Detected Text" }
                    pre { class: "ocr-text", "{text}" }
                }
            }
            // Actions
            div { class: "rewind-actions",
                button {
                    class: "btn btn-primary",
                    onclick: move |_| {
                        let cfg = cfg.read().clone();
                        let db_val = db.read().clone();
                        let shot_clone = shot.clone();
                        spawn(async move {
                            let items = vec![(
                                shot_clone.captured_at.to_rfc3339(),
                                shot_clone.window_title.clone().unwrap_or_default(),
                                shot_clone.ocr_text.clone().unwrap_or_default(),
                            )];
                            match crate::llm::summarize_ocr_snippets(&cfg, items).await {
                                Ok(summary) => {
                                    if !summary.is_empty() {
                                        if let Some(crate::app::Db(ref d)) = db_val {
                                            if let Err(e) = d.insert_memory(None, &summary, Some("screenshot")) {
                                                tracing::error!("[REWIND] Failed to save memory: {e}");
                                            } else {
                                                tracing::info!("[REWIND] Saved screenshot summary as memory");
                                            }
                                        }
                                    }
                                }
                                Err(e) => tracing::error!("[REWIND] OCR summarization error: {e}"),
                            }
                        });
                    },
                    "Summarize & Save"
                }
                if has_video {
                    button {
                        class: "btn btn-secondary",
                        title: "Open video recording in default player",
                        onclick: move |_| {
                            let videos_dir = std::env::var("APPDATA")
                                .map(|b| std::path::PathBuf::from(b).join("omi").join("videos"))
                                .unwrap_or_default();
                            if videos_dir.exists() {
                                let _ = std::process::Command::new("explorer").arg(videos_dir).spawn();
                            }
                        },
                        "Open Videos Folder"
                    }
                }
            }
        }
    }
}

// ── Main page ─────────────────────────────────────────────────────────────────

#[component]
pub fn RewindPage() -> Element {
    let db: Signal<Option<Db>> = use_context();
    let config: Signal<AppConfig> = use_context();

    let mut screenshots: Signal<Vec<Screenshot>> = use_signal(Vec::new);
    let mut search_query = use_signal(String::new);
    let mut selected: Signal<Option<Screenshot>> = use_signal(|| None);
    let mut scrubber_idx = use_signal(|| 0);
    let mut app_filter = use_signal(String::new);
    let mut available_apps = use_signal(Vec::<String>::new);

    let capture_enabled = config.read().screen_capture_enabled;

    // Auto-refresh every 5s to pick up new frames from the capture task
    let db_refresh = db.clone();
    use_effect(move || {
        let db_snap = db_refresh.read().clone();
        spawn(async move {
            loop {
                if let Some(Db(ref d)) = db_snap {
                    match d.list_screenshots(200) {
                        Ok(shots) => {
                            let mut apps: Vec<String> = shots
                                .iter()
                                .filter_map(|s| s.app_name.clone())
                                .collect::<std::collections::HashSet<_>>()
                                .into_iter()
                                .collect();
                            apps.sort();
                            available_apps.set(apps);
                            screenshots.set(shots);
                        }
                        Err(e) => tracing::error!("[REWIND] load failed: {e}"),
                    }
                }
                tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
            }
        });
    });

    // Synchronize selected and scrubber_idx
    use_effect(move || {
        let shots = screenshots.read();
        if !shots.is_empty() {
            if selected.read().is_none() {
                selected.set(Some(shots[0].clone()));
                scrubber_idx.set(0);
            } else if let Some(ref sel) = *selected.read() {
                if let Some(idx) = shots.iter().position(|s| s.id == sel.id) {
                    if *scrubber_idx.peek() != idx {
                        scrubber_idx.set(idx);
                    }
                }
            }
        } else {
            selected.set(None);
            scrubber_idx.set(0);
        }
    });

    // Filter screenshots by app
    let filtered_shots: Vec<Screenshot> = {
        let filter = app_filter.read().clone();
        if filter.is_empty() {
            screenshots.read().clone()
        } else {
            screenshots
                .read()
                .iter()
                .filter(|s| s.app_name.as_deref() == Some(filter.as_str()))
                .cloned()
                .collect()
        }
    };

    // Search handler
    let mut do_search = move || {
        let q = search_query.read().trim().to_string();
        if let Some(Db(ref d)) = *db.read() {
            let result = if q.is_empty() {
                d.list_screenshots(200)
            } else {
                d.search_screenshots(&q, 200)
            };
            match result {
                Ok(shots) => screenshots.set(shots),
                Err(e) => tracing::error!("[REWIND] search failed: {e}"),
            }
        }
    };

    rsx! {
        div {
            class: "page",
            tabindex: "0",
            onkeydown: move |e| {
                let shots = screenshots.read();
                if shots.is_empty() { return; }
                let max_idx = shots.len().saturating_sub(1);
                let cur = *scrubber_idx.peek();
                match e.key() {
                    Key::ArrowLeft | Key::ArrowUp => {
                        if cur > 0 {
                            let new_idx = cur - 1;
                            scrubber_idx.set(new_idx);
                            if let Some(shot) = shots.get(new_idx) {
                                selected.set(Some(shot.clone()));
                            }
                        }
                    }
                    Key::ArrowRight | Key::ArrowDown => {
                        if cur < max_idx {
                            let new_idx = cur + 1;
                            scrubber_idx.set(new_idx);
                            if let Some(shot) = shots.get(new_idx) {
                                selected.set(Some(shot.clone()));
                            }
                        }
                    }
                    Key::Escape => {
                        selected.set(None);
                    }
                    _ => {}
                }
            },

            h1 { class: "page-title", "Rewind" }

            if !capture_enabled {
                div { class: "empty-state",
                    p { "Screen capture is disabled." }
                    p { class: "text-muted", "Enable it in Settings → Screen Capture." }
                }
            } else {
                // Search bar + app filter
                div { class: "search-bar",
                    input {
                        class: "search-input",
                        r#type: "text",
                        placeholder: "Search by text on screen...",
                        value: "{search_query}",
                        oninput: move |e| search_query.set(e.value()),
                        onkeypress: move |e| {
                            if e.key() == Key::Enter {
                                do_search();
                            }
                        },
                    }
                    select {
                        class: "settings-input",
                        style: "max-width: 180px;",
                        value: "{app_filter}",
                        onchange: move |e| app_filter.set(e.value()),
                        option { value: "", "All Apps" }
                        for a in available_apps.read().iter() {
                            option { value: "{a}", "{a}" }
                        }
                    }
                    button {
                        class: "btn btn-secondary",
                        onclick: move |_| do_search(),
                        "Search"
                    }
                }

                // Interactive Timeline & Filmstrip Scrubber
                if !filtered_shots.is_empty() {
                    {
                        let max_idx = filtered_shots.len().saturating_sub(1);
                        let current_time = if let Some(ref s) = *selected.read() {
                            s.captured_at.format("%H:%M:%S").to_string()
                        } else {
                            "00:00:00".to_string()
                        };

                        rsx! {
                            div { class: "rewind-timeline-container",
                                div { class: "timeline-scrubber-row",
                                    input {
                                        class: "timeline-slider",
                                        r#type: "range",
                                        min: "0",
                                        max: "{max_idx}",
                                        value: "{scrubber_idx}",
                                        oninput: move |e| {
                                            let idx: usize = e.value().parse().unwrap_or(0);
                                            scrubber_idx.set(idx);
                                            if let Some(shot) = screenshots.read().get(idx) {
                                                selected.set(Some(shot.clone()));
                                            }
                                        }
                                    }
                                    span { class: "timeline-time", "{current_time}" }
                                    span { class: "text-muted", style: "font-size: 11px;",
                                        "{filtered_shots.len()} frames · Arrow keys to navigate"
                                    }
                                }

                                div { class: "rewind-filmstrip",
                                    for (i, shot) in filtered_shots.iter().enumerate() {
                                        {
                                            let is_sel = Some(&shot.id) == selected.read().as_ref().map(|s| &s.id);
                                            let shot_clone = shot.clone();
                                            let time_label = shot.captured_at.format("%H:%M").to_string();
                                            rsx! {
                                                div {
                                                    class: if is_sel { "filmstrip-thumb selected" } else { "filmstrip-thumb" },
                                                    onclick: move |_| {
                                                        selected.set(Some(shot_clone.clone()));
                                                        scrubber_idx.set(i);
                                                    },
                                                    if let Some(ref p) = shot.thumbnail_path {
                                                        img { class: "filmstrip-img", src: "{p}" }
                                                    } else {
                                                        div { class: "rewind-thumb-placeholder", "📷" }
                                                    }
                                                    span { class: "filmstrip-time", "{time_label}" }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Detail panel for selected screenshot
                if let Some(shot) = selected.read().clone() {
                    RewindDetail {
                        shot: shot,
                        on_close: move |_| selected.set(None),
                    }
                }

                // Timeline grid
                if filtered_shots.is_empty() {
                    div { class: "empty-state",
                        if app_filter.read().is_empty() {
                            p { "No screenshots yet." }
                            p { class: "text-muted",
                                "Screen capture is running — first frame will appear shortly."
                            }
                        } else {
                            p { "No screenshots for this app." }
                            p { class: "text-muted", "Try selecting a different app or \"All Apps\"." }
                        }
                    }
                } else {
                    div { class: "rewind-grid",
                        for shot in filtered_shots.iter() {
                            {
                                let is_sel = Some(&shot.id) == selected.read().as_ref().map(|s| &s.id);
                                rsx! {
                                    RewindThumb {
                                        key: "{shot.id}",
                                        shot: shot.clone(),
                                        is_selected: is_sel,
                                        on_click: move |s: Screenshot| selected.set(Some(s)),
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
