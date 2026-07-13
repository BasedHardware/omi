use std::sync::Arc;

use dioxus::prelude::*;

use crate::agent_runtime::{AgentRuntime, AgentEvent}; // AgentStatus used via runtime.status()
use crate::auth::AuthStatus;
use crate::components::sidebar::Sidebar;
use crate::components::floating_bar::FloatingBar;
use crate::config::AppConfig;
use crate::hotkey::HotkeyAction;
use crate::pages;
use crate::proactive::{ProactiveEngine, ProactiveEvent};
use crate::recording::{LiveTranscript, RecordingStatus};
use crate::recording::StopRecording;
use crate::sidecar::BackendStatus;
use crate::tray::TrayAction;

/// Wrapper so `omi_db::Database` can be provided as Dioxus context (needs Clone).
#[derive(Clone)]
pub struct Db(pub omi_db::Database);

/// Top-level route enum — each variant maps to a sidebar nav item.
#[derive(Debug, Clone, Routable, PartialEq)]
#[rustfmt::skip]
pub enum Route {
    #[layout(AppLayout)]
        #[route("/")]
        Dashboard {},
        #[route("/search")]
        Search {},
        #[route("/agent")]
        Agent {},
        #[route("/chat")]
        Chat {},
        #[route("/conversations")]
        Conversations {},
        #[route("/memories")]
        Memories {},
        #[route("/tasks")]
        Tasks {},
        #[route("/rewind")]
        Rewind {},
        #[route("/apps")]
        Apps {},
        #[route("/focus")]
        Focus {},
        #[route("/persona")]
        Persona {},
        #[route("/settings")]
        Settings {},
}

/// The root application component.
#[component]
pub fn App() -> Element {
    // Load persisted config
    let config = use_signal(|| AppConfig::load());

    // Determine initial auth status from saved token
    let initial_auth = {
        let cfg = config.read();
        if cfg.is_authenticated() {
            AuthStatus::SignedIn {
                email: cfg.user_email.clone(),
                name: cfg.user_display_name.clone(),
            }
        } else {
            AuthStatus::SignedOut
        }
    };
    let auth_status = use_signal(|| initial_auth);

    // Backend sidecar health
    let mut backend_status = use_signal(|| BackendStatus::Starting);

    // Recording state
    let recording_status = use_signal(|| RecordingStatus::Idle);
    let live_transcript = use_signal(LiveTranscript::default);
    // Global stop handle for active recording (kept in app context so UI unmounts don't drop it)
    let stop_handle: Signal<Option<StopRecording>> = use_signal(|| None);

    // Floating control bar visibility
    let floating_bar_visible: Signal<bool> = use_signal(|| false);

    // Open local SQLite DB (log error but don't crash the app)
    let db = use_signal(|| {
        match omi_db::Database::open() {
            Ok(d) => {
                tracing::info!("[DB] Opened successfully");
                Some(Db(d))
            }
            Err(e) => {
                tracing::error!("[DB] Failed to open: {e}");
                None
            }
        }
    });

// ── Agent runtime (M9) ───────────────────────────────────────────────────────────────
    let runtime = use_signal(|| AgentRuntime::new());

    // Proactive suggestion engine + shared suggestion list
    let (proactive_engine, proactive_rx) = ProactiveEngine::new();
    let proactive_engine = Arc::new(proactive_engine);
    let proactive_engine_signal = use_signal(|| proactive_engine.clone());
    let suggestions: Signal<Vec<crate::proactive::Suggestion>> = use_signal(Vec::new);
    // Prompt pre-filled from tapped suggestion pill (consumed by AgentPage)
    let suggestion_prompt: Signal<Option<String>> = use_signal(|| None);

    let continuous_voice_mode = use_signal(|| false);
    let voice_history = use_signal(Vec::<(String, String)>::new);

    let start_rec = {
        let mut stop_h = stop_handle.clone();
        let rec_status = recording_status.clone();
        let live_t = live_transcript.clone();
        let cfg_hk = config.clone();
        let db_hk = db.clone();
        let proactive_hk = proactive_engine_signal.clone();
        
        move || {
            if matches!(*rec_status.peek(), RecordingStatus::Recording { .. }) {
                return;
            }
            let api_key = cfg_hk.read().deepgram_api_key.clone();
            let diarize = cfg_hk.read().diarize_speakers;
            let cfg = cfg_hk.read().clone();
            let db_val = db_hk.read().clone();
            let mut status = rec_status.clone();
            let mut transcript = live_t.clone();
            let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
            stop_h.set(Some(StopRecording::new(stop_tx)));
            let pe = Some(proactive_hk.peek().clone());
            spawn(async move {
                crate::recording::start_recording_with_proactive(
                    api_key, diarize, db_val, cfg,
                    stop_rx, &mut status, &mut transcript, pe,
                )
                .await;
            });
        }
    };

    let ptt_active = use_signal(|| false);
    let agent_query_pending = use_signal(|| false);
    let notification_history: Signal<Vec<crate::notification_history::NotificationEntry>> = use_signal(Vec::new);

    // Provide all as global context
    use_context_provider(|| config);
    use_context_provider(|| auth_status);
    use_context_provider(|| backend_status);
    use_context_provider(|| recording_status);
    use_context_provider(|| live_transcript);
    use_context_provider(|| stop_handle);
    use_context_provider(|| db);
    use_context_provider(|| floating_bar_visible);
    use_context_provider(|| runtime);
    use_context_provider(|| proactive_engine_signal);
    use_context_provider(|| suggestions);
    use_context_provider(|| suggestion_prompt);
    use_context_provider(|| continuous_voice_mode);
    use_context_provider(|| ptt_active);
    use_context_provider(|| voice_history);
    use_context_provider(|| notification_history);

    // ── Hotkey + tray listeners (use_hook = called once on mount) ───────────────
    {
        let mut fbar = floating_bar_visible.clone();
        let mut stop_h = stop_handle.clone();
        let rec_status = recording_status.clone();
        let live_t = live_transcript.clone();
        let cfg_hk = config.clone();
        let db_hk = db.clone();
        let proactive_hk = proactive_engine.clone();
        let mut cvm = continuous_voice_mode.clone();
        let mut ptt = ptt_active.clone();
        let mut aq_pending = agent_query_pending.clone();

        use_hook(move || {
            let (hk_tx, mut hk_rx) = tokio::sync::broadcast::channel::<HotkeyAction>(8);
            let (tray_tx, mut tray_rx) = tokio::sync::broadcast::channel::<TrayAction>(8);

            crate::hotkey::start_listener(hk_tx);
            crate::tray::start_listener(tray_tx);

            // Bridge hotkey events → Dioxus signals
            spawn(async move {
                loop {
                    match hk_rx.recv().await {
                        Ok(HotkeyAction::ToggleBar) => {
                            let cur = *fbar.peek();
                            fbar.set(!cur);
                        }
                        Ok(HotkeyAction::StartRecord) => {
                            if !matches!(*rec_status.peek(), RecordingStatus::Recording { .. }) {
                                cvm.set(false); // Make sure continuous mode is false for PTT
                                let api_key = cfg_hk.read().deepgram_api_key.clone();
                                let diarize = cfg_hk.read().diarize_speakers;
                                let cfg = cfg_hk.read().clone();
                                let db_val = db_hk.read().clone();
                                let mut status = rec_status.clone();
                                let mut transcript = live_t.clone();
                                let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
                                stop_h.set(Some(StopRecording::new(stop_tx)));
                                let pe = Some(proactive_hk.clone());
                                spawn(async move {
                                    crate::recording::start_recording_with_proactive(
                                        api_key, diarize, db_val, cfg,
                                        stop_rx, &mut status, &mut transcript, pe,
                                    )
                                    .await;
                                });
                            }
                        }
                        Ok(HotkeyAction::StopRecord) => {
                            if matches!(*rec_status.peek(), RecordingStatus::Recording { .. }) {
                                if let Some(handle) = stop_h.write().take() {
                                    handle.stop();
                                }
                            }
                        }
                        Ok(HotkeyAction::ToggleVoiceChat) => {
                            let cur = *cvm.peek();
                            tracing::info!("[APP] Toggled Voice Chat Mode: {}", !cur);
                            cvm.set(!cur);
                        }
                        Ok(HotkeyAction::PttPressed) => {
                            if !*ptt.read() {
                                ptt.set(true);
                                cvm.set(false); // Disable Voice Chat Mode
                                
                                if !matches!(*rec_status.peek(), RecordingStatus::Recording { .. }) {
                                    tracing::info!("[APP] PTT Pressed: starting recording");
                                    let api_key = cfg_hk.read().deepgram_api_key.clone();
                                    let diarize = cfg_hk.read().diarize_speakers;
                                    let cfg = cfg_hk.read().clone();
                                    let db_val = db_hk.read().clone();
                                    let mut status = rec_status.clone();
                                    let mut transcript = live_t.clone();
                                    let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
                                    stop_h.set(Some(StopRecording::new(stop_tx)));
                                    let pe = Some(proactive_hk.clone());
                                    spawn(async move {
                                        crate::recording::start_recording_with_proactive(
                                            api_key, diarize, db_val, cfg,
                                            stop_rx, &mut status, &mut transcript, pe,
                                        )
                                        .await;
                                    });
                                }
                            }
                        }
                        Ok(HotkeyAction::PttReleased) => {
                            if *ptt.read() {
                                tracing::info!("[APP] PTT Released: stopping recording to query agent");
                                ptt.set(false);
                                // Queue an agent query, then stop recording
                                aq_pending.set(true);
                                if let Some(handle) = stop_h.write().take() {
                                    handle.stop();
                                }
                            }
                        }
                        Err(_) => break,
                    }
                }
            });

            // Bridge tray events → Dioxus actions
            spawn(async move {
                loop {
                    match tray_rx.recv().await {
                        Ok(TrayAction::OpenWindow) => {
                            tracing::info!("[TRAY] Open window requested");
                        }
                        Ok(TrayAction::Quit) => {
                            tracing::info!("[TRAY] Quit requested from tray");
                            std::process::exit(0);
                        }
                        Ok(TrayAction::ToggleRecord) => {}
                        Err(_) => break,
                    }
                }
            });
        });
    }

    // ── Start agent runtime if enabled ───────────────────────────────────────────────
    let proactive_engine_for_effect = proactive_engine.clone();
    use_hook(move || {
        let cfg = config.read().clone();
        // Initialize native Agent Runtime
        if cfg.agent_enabled {
            // We no longer spawn Node.js! All execution paths route through `agent_runtime.query_native()`.
            // Just leaving this scope so existing config bindings remain clean.
            tracing::info!("[AGENT] Native Rust Agent Runtime initialized.");
        }

        // Proactive engine: consume events → update suggestions signal
        let pe_arc = proactive_engine.clone();
        let _db_for_proactive = db.clone();
        let cfg_for_proactive = config.read().clone();
        let tick_mins = cfg_for_proactive.proactive_tick_mins;

        // Spawn tick task
        {
            let db_snap = db.read().clone();
            if let Some(Db(ref d)) = db_snap {
                crate::proactive::spawn_tick_task(
                    pe_arc.clone(),
                    d.clone(),
                    cfg_for_proactive.clone(),
                    tick_mins,
                );
            }
        }

        // Consume ProactiveEvent → update suggestions signal
        let mut sug_sig = suggestions.clone();
        let mut rx = proactive_rx;
        let cfg_for_notif = config.clone();
        let db_notif = db.clone();
        let mut nh_sig = notification_history.clone();
        spawn(async move {
            loop {
                match rx.recv().await {
                    Ok(ProactiveEvent::NewSuggestion(s)) => {
                        // Send Windows Toast notification for every suggestion
                        let notif_cfg = cfg_for_notif.read().clone();
                        if notif_cfg.proactive_toast_notifications {
                            crate::notifications::send_suggestion(&s.text, s.priority);
                        }
                        // Record to notification history
                        {
                            let db_val = db_notif.read().clone();
                            crate::notification_history::record_and_push(
                                &db_val, nh_sig, "Omi Suggestion", &s.text, s.priority,
                            );
                        }

                        let mut list = sug_sig.read().clone();
                        // Evict expired and keep max 5
                        list.retain(|x: &crate::proactive::Suggestion| !x.is_expired());
                        // Deduplicate: remove any existing suggestion with the exact same text
                        list.retain(|x| x.text != s.text);
                        list.push(s);
                        list.sort_by(|a, b| b.priority.cmp(&a.priority));
                        list.truncate(5);
                        sug_sig.set(list);
                    }
                    Ok(ProactiveEvent::Dismiss(id)) => {
                        let mut list = sug_sig.read().clone();
                        list.retain(|x| x.id != id);
                        sug_sig.set(list);
                    }
                    Ok(ProactiveEvent::ClearAll) => sug_sig.set(Vec::new()),
                    Err(_) => break,
                }
            }
        });

    });

    // Load notification history from DB
    {
        let mut nh = notification_history.clone();
        let db_snap = db.clone();
        use_effect(move || {
            let db_val = db_snap.read().clone();
            crate::notification_history::load_from_db(&db_val, nh);
        });
    }

    // Kick off the sidecar health poller once
    use_effect(move || {
        spawn(async move {
            crate::sidecar::poll_backend_health(&mut backend_status).await;
        });
    });

    // Kick off periodic screen capture if enabled in config (runs once on mount)
    let capture_started = use_signal(|| false);
    let ctx_watcher_started = use_signal(|| false);
    let clipboard_started = use_signal(|| false);
    let file_indexer_started = use_signal(|| false);
    let recap_started = use_signal(|| false);
    let tracker_started = use_signal(|| false);
    use_effect(move || {
        let cfg = config.read().clone();
        let db_snap = db.read().clone();
        tracing::info!("[APP] screen_capture_enabled={} capture_interval={}s",
            cfg.screen_capture_enabled, cfg.capture_interval_secs);
        if cfg.screen_capture_enabled && !*capture_started.read() {
            if let Some(Db(d)) = db_snap.clone() {
                let interval_secs = cfg.capture_interval_secs.max(1);
                tracing::info!("[APP] Spawning screen capture task (every {interval_secs}s)");
                capture_started.clone().set(true);
                spawn(async move {
                    crate::capture::run_capture_task(d, interval_secs, cfg).await;
                });
            } else {
                tracing::warn!("[APP] Screen capture enabled but DB not open");
            }
        }

        // Spawn context watcher alongside capture (if not already started)
        if !*ctx_watcher_started.read() {
            if let Some(Db(d)) = db_snap.clone() {
                ctx_watcher_started.clone().set(true);
                let pe = proactive_engine_for_effect.clone();
                let _cfg_for_watcher = config.read().clone();
                let db_for_watcher = d.clone();
                tracing::info!("[APP] Spawning context watcher task");
                spawn(async move {
                    crate::context_watcher::run_context_watcher(
                        db_for_watcher,
                        (*pe).clone(),
                        move || crate::config::AppConfig::load(),
                    )
                    .await;
                });
            }
        }

        // Spawn clipboard watcher
        if !*clipboard_started.read() {
            if let Some(Db(d)) = db_snap.clone() {
                clipboard_started.clone().set(true);
                tracing::info!("[APP] Spawning clipboard watcher task");
                spawn(async move {
                    crate::clipboard_watcher::run_clipboard_watcher(
                        d,
                        move || crate::config::AppConfig::load(),
                    )
                    .await;
                });
            }
        }

        // Spawn file indexer
        if !*file_indexer_started.read() {
            if let Some(Db(d)) = db_snap.clone() {
                file_indexer_started.clone().set(true);
                tracing::info!("[APP] Spawning file indexer task");
                spawn(async move {
                    crate::file_indexer::run_file_indexer(
                        d,
                        move || crate::config::AppConfig::load(),
                    )
                    .await;
                });
            }
        }

        // Spawn daily recap scheduler
        if !*recap_started.read() {
            if let Some(Db(d)) = db_snap.clone() {
                recap_started.clone().set(true);
                tracing::info!("[APP] Spawning daily recap scheduler");
                spawn(async move {
                    crate::daily_recap::run_daily_recap_scheduler(
                        d,
                        move || crate::config::AppConfig::load(),
                    )
                    .await;
                });
            }
        }

        // Spawn app usage tracker
        if !*tracker_started.read() {
            if let Some(Db(d)) = db_snap {
                tracker_started.clone().set(true);
                tracing::info!("[APP] Spawning app usage tracker");
                spawn(async move {
                    crate::app_tracker::run_app_tracker_with_db(
                        d,
                        move || crate::config::AppConfig::load(),
                    )
                    .await;
                });
            }
        }
    });


    // ── Create thread-safe channels for secondary window synchronization ──────
    let (
        recording_status_tx,
        suggestions_tx,
        config_tx,
        _agent_event_tx,
        props_for_character
    ) = use_hook(|| {
        let (recording_status_tx, recording_status_rx) = tokio::sync::watch::channel(RecordingStatus::Idle);
        let (suggestions_tx, suggestions_rx) = tokio::sync::watch::channel(Vec::<crate::proactive::Suggestion>::new());
        let (config_tx, config_rx) = tokio::sync::watch::channel(AppConfig::load());
        let (agent_event_tx, _agent_event_rx) = tokio::sync::broadcast::channel(256);
        let (character_action_tx, mut character_action_rx) = tokio::sync::mpsc::unbounded_channel::<crate::components::character_window::CharacterAction>();

        // Forward agent_runtime events -> character window agent_event_tx
        let rt = runtime.clone();
        let agent_event_tx_clone = agent_event_tx.clone();
        let mut vh_agent = voice_history.clone();
        spawn(async move {
            let mut rx = rt.read().subscribe();
            loop {
                match rx.recv().await {
                    Ok(event) => {
                        if let AgentEvent::Result { ref text, .. } = event {
                            let mut h = vh_agent.read().clone();
                            h.push(("assistant".into(), text.clone()));
                            vh_agent.set(h);
                        }
                        let _ = agent_event_tx_clone.send(event);
                    }
                    Err(_) => {
                        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                        rx = rt.read().subscribe();
                    }
                }
            }
        });

        // Listen for actions from character window and mutate main state
        let mut stop_h_action = stop_handle.clone();
        let mut cvm_action = continuous_voice_mode.clone();
        let mut vh_action = voice_history.clone();
        let mut start_rec_action = start_rec.clone();
        let mut sp = suggestion_prompt.clone();
        let rt_action = runtime.clone();
        let cfg_action = config.clone();
        
        let mut last_toggle = std::time::Instant::now() - std::time::Duration::from_secs(5);
        spawn(async move {
            while let Some(action) = character_action_rx.recv().await {
                match action {
                    crate::components::character_window::CharacterAction::ToggleRecord => {
                        let now = std::time::Instant::now();
                        if now.duration_since(last_toggle) < std::time::Duration::from_millis(1500) {
                            tracing::warn!("[APP] Ignoring rapid record toggle click");
                            continue;
                        }
                        last_toggle = now;

                        if *cvm_action.read() {
                            cvm_action.set(false);
                            let _ = dioxus::prelude::document::eval("if (window.cancelSpeech) window.cancelSpeech();");
                            if let Some(handle) = stop_h_action.write().take() {
                                handle.stop();
                            }
                        } else {
                            cvm_action.set(true);
                            vh_action.set(Vec::new());
                            start_rec_action();
                        }
                    }
                    crate::components::character_window::CharacterAction::SuggestionAction(prompt_text) => {
                        if prompt_text.starts_with("HITL_CONFIRM:") {
                            let thread_id = prompt_text.replace("HITL_CONFIRM:", "");
                            let rt = rt_action.clone();
                            let current_cfg = cfg_action.read().clone();
                            spawn(async move {
                                let _ = rt.read().confirm_mcp_hitl(&thread_id, "confirm", &current_cfg).await;
                            });
                        } else if prompt_text.starts_with("HITL_REJECT:") {
                            let thread_id = prompt_text.replace("HITL_REJECT:", "");
                            let rt = rt_action.clone();
                            let current_cfg = cfg_action.read().clone();
                            spawn(async move {
                                let _ = rt.read().confirm_mcp_hitl(&thread_id, "reject", &current_cfg).await;
                            });
                        } else {
                            sp.set(Some(prompt_text));
                        }
                    }
                    crate::components::character_window::CharacterAction::SpeechFinished => {
                        if *cvm_action.read() {
                            tracing::info!("[APP] Continuous voice mode: speech finished. Restarting recording.");
                            start_rec_action();
                        }
                    }
                }
            }
        });

        let props = crate::components::character_window::CharacterOverlayProps {
            recording_status_rx,
            suggestions_rx,
            config_rx,
            agent_event_tx: agent_event_tx.clone(),
            character_action_tx,
        };

        (
            recording_status_tx,
            suggestions_tx,
            config_tx,
            agent_event_tx,
            props
        )
    });

    // Keep channels synchronized with signals using local effects
    let recording_status_tx_clone = recording_status_tx.clone();
    use_effect(move || {
        let status = recording_status.read().clone();
        let _ = recording_status_tx_clone.send(status);
    });

    let suggestions_tx_clone = suggestions_tx.clone();
    use_effect(move || {
        let list = suggestions.read().clone();
        let _ = suggestions_tx_clone.send(list);
    });

    let config_tx_clone = config_tx.clone();
    use_effect(move || {
        let cfg = config.read().clone();
        let _ = config_tx_clone.send(cfg);
    });

    // ── Spawn character overlay window once on mount ──────────────────────────
    let has_spawned_character = use_signal(|| false);
    let props_for_spawn = props_for_character.clone();
    use_effect(move || {
        if !*has_spawned_character.read() {
            has_spawned_character.clone().set(true);

            let desktop = dioxus::desktop::window();
            
            // Build secondary window config
            #[allow(unused_mut)]
            let mut builder = dioxus::desktop::tao::window::WindowBuilder::new()
                .with_title("Omi Character")
                .with_decorations(false)     // borderless
                .with_transparent(true)      // transparent background
                .with_always_on_top(true)    // always-on-top overlay
                .with_resizable(false)
                .with_inner_size(dioxus::desktop::tao::dpi::LogicalSize::new(180.0, 180.0));

            #[cfg(target_os = "windows")]
            {
                use dioxus::desktop::tao::platform::windows::WindowBuilderExtWindows;
                builder = builder.with_skip_taskbar(true).with_undecorated_shadow(false);
            }

            // Position in the bottom-right corner of the primary monitor
            if let Some(monitor) = desktop.primary_monitor() {
                let size = monitor.size();
                let scale = monitor.scale_factor();
                let win_width = (180.0 * scale) as u32;
                let win_height = (180.0 * scale) as u32;
                
                // Bottom-right corner offset
                let x = size.width.saturating_sub(win_width).saturating_sub((20.0 * scale) as u32);
                let y = size.height.saturating_sub(win_height).saturating_sub((60.0 * scale) as u32);
                
                builder = builder.with_position(dioxus::desktop::tao::dpi::PhysicalPosition::new(x as i32, y as i32));
            }

            let character_cfg = dioxus::desktop::Config::new()
                .with_background_color((0, 0, 0, 0))
                .with_custom_head(r#"<style>html, body, #main { background-color: transparent !important; background: transparent !important; overflow: hidden; margin: 0; padding: 0; }</style>"#.to_string())
                .with_window(builder);

            desktop.new_window(
                VirtualDom::new_with_props(crate::components::character_window::CharacterOverlay, props_for_spawn.clone()),
                character_cfg
            );
            tracing::info!("[APP] Spawned proactive character overlay window.");
        }
    });

    // Silence detection: watch live_transcript for changes
    let live_t = live_transcript.clone();
    let mut stop_h_silence = stop_handle.clone();
    let cvm_silence = continuous_voice_mode.clone();
    use_effect(move || {
        if !*cvm_silence.read() {
            return;
        }
        let segments = live_t.read().segments.clone();
        if let Some(last_seg) = segments.last() {
            if last_seg.speech_final {
                tracing::info!("[SILENCE] speech_final detected. Stopping recording to query Agent.");
                if let Some(handle) = stop_h_silence.write().take() {
                    handle.stop();
                }
            }
        }
    });

    // Handle recording transition -> query Agent
    let rec_status = recording_status.clone();
    let live_t_agent = live_transcript.clone();
    let cvm_agent = continuous_voice_mode.clone();
    let mut aq_pending = agent_query_pending.clone();
    let mut vh_agent = voice_history.clone();
    let rt_agent = runtime.clone();
    let cfg_agent = config.clone();
    let db_agent = db.clone();
    let start_rec_agent = start_rec.clone();
    let mut prev_was_recording = use_signal(|| false);

    use_effect(move || {
        let status = rec_status.read().clone();
        let was_rec = *prev_was_recording.peek();
        let is_rec = matches!(status, RecordingStatus::Recording { .. });
        prev_was_recording.set(is_rec);

        if was_rec && !is_rec && (*cvm_agent.read() || *aq_pending.read()) {
            aq_pending.set(false);

            let user_text: String = live_t_agent.read().segments.iter()
                .filter(|s| s.is_final)
                .map(|s| s.text.as_str())
                .collect::<Vec<_>>()
                .join(" ");

            let user_text = user_text.trim().to_string();
            if user_text.is_empty() {
                tracing::info!("[APP] User text empty. Auto-restarting if in continuous mode.");
                let cvm_clone = cvm_agent.clone();
                let mut start_rec_clone = start_rec_agent.clone();
                spawn(async move {
                    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                    if *cvm_clone.read() {
                        start_rec_clone();
                    }
                });
                return;
            }

            tracing::info!("[APP] Continuous mode: user said \"{}\". Triggering Agent query.", user_text);

            let mut h = vh_agent.read().clone();
            h.push(("user".into(), user_text));
            vh_agent.set(h.clone());

            let rt_clone = rt_agent.read().clone();
            let cfg_val = cfg_agent.read().clone();
            let db_snap = db_agent.read().clone();

            spawn(async move {
                let mut ctx = String::new();
                if let Some(Db(ref d)) = db_snap {
                    let memories = d.get_memories_text(10).unwrap_or_default();
                    let recent = d.get_recent_context(3).unwrap_or_default();
                    if !recent.is_empty() {
                        ctx.push_str("## Recent Conversations\n");
                        for (ts, title, text) in &recent {
                            ctx.push_str(&format!("[{ts}] {title}: {text}\n"));
                        }
                    }
                    if !memories.is_empty() {
                        ctx.push_str("## Long-term Memories\n");
                        ctx.push_str(&memories);
                    }
                    if let Ok(clips) = d.list_clipboard_entries(10) {
                        if !clips.is_empty() {
                            ctx.push_str("\n## Recent Clipboard\n");
                            for c in &clips {
                                let preview = if c.content.len() > 120 { &c.content[..120] } else { &c.content };
                                ctx.push_str(&format!("[{}] ({}) {}\n", c.captured_at.format("%H:%M"), c.content_type, preview));
                            }
                        }
                    }
                    if let Ok(files) = d.list_recent_files(15) {
                        if !files.is_empty() {
                            ctx.push_str("\n## Recent Files\n");
                            for f in &files {
                                ctx.push_str(&format!("{} ({})\n", f.file_path, f.extension.as_deref().unwrap_or("?")));
                            }
                        }
                    }
                }

                let system = format!(
                    "You are Omi, a proactive AI assistant running on the user's Windows computer.\n\
                    Be concise, precise, and helpful. Use context below when relevant.\n\
                    When listing items use plain text, not markdown (the UI renders plain text).\n\n\
                    {ctx}"
                );

                if let Err(e) = rt_clone.query_native(h, &system, true, &cfg_val).await {
                    tracing::error!("[APP] Continuous mode agent query failed: {e}");
                }
            });
        }
    });

    rsx! {
        Router::<Route> {}
    }
}

/// Shared layout: sidebar on the left, page content on the right.
#[component]
fn AppLayout() -> Element {
    rsx! {
        div { class: "app-layout",
            Sidebar {}
            main { class: "app-content",
                Outlet::<Route> {}
            }
            // Floating control bar — always in DOM, shown/hidden via CSS class
            FloatingBar {}
        }
    }
}

// ── Page components (thin wrappers delegating to pages module) ──────────

#[component]
fn Dashboard() -> Element {
    pages::dashboard::DashboardPage()
}

#[component]
fn Chat() -> Element {
    pages::chat::ChatPage()
}

#[component]
fn Conversations() -> Element {
    pages::conversations::ConversationsPage()
}

#[component]
fn Memories() -> Element {
    pages::memories::MemoriesPage()
}

#[component]
fn Tasks() -> Element {
    pages::tasks::TasksPage()
}

#[component]
fn Rewind() -> Element {
    pages::rewind::RewindPage()
}

#[component]
fn Agent() -> Element {
    rsx! { pages::agent::AgentPage {} }
}

#[component]
fn Apps() -> Element {
    pages::apps::AppsPage()
}

#[component]
fn Focus() -> Element {
    pages::focus::FocusPage()
}

#[component]
fn Persona() -> Element {
    pages::persona::PersonaPage()
}

#[component]
fn Search() -> Element {
    pages::search::SearchPage()
}

#[component]
fn Settings() -> Element {
    pages::settings::SettingsPage()
}
