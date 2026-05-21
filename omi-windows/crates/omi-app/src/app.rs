use std::sync::Arc;

use dioxus::prelude::*;

use crate::agent_runtime::AgentRuntime; // AgentStatus used via runtime.status()
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

    // ── Hotkey + tray listeners (use_hook = called once on mount) ───────────────
    {
        let mut fbar = floating_bar_visible.clone();
        let mut stop_h = stop_handle.clone();
        let rec_status = recording_status.clone();
        let live_t = live_transcript.clone();
        let cfg_hk = config.clone();
        let db_hk = db.clone();
        let proactive_hk = proactive_engine.clone();

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
                        Ok(HotkeyAction::ToggleRecord) => {
                            if matches!(*rec_status.peek(), RecordingStatus::Recording { .. }) {
                                if let Some(handle) = stop_h.write().take() {
                                    handle.stop();
                                }
                            } else {
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
    use_hook(move || {
        let cfg = config.read().clone();
        if cfg.agent_enabled {
            let rt = runtime.read().clone();
            let node = if cfg.node_path.is_empty() {
                crate::agent_runtime::find_node()
            } else {
                Some(cfg.node_path.clone())
            };
            let script = if cfg.agent_script_path.is_empty() {
                crate::agent_runtime::find_agent_script()
            } else {
                Some(cfg.agent_script_path.clone())
            };
            let model = {
                let (_, _, m) = crate::llm::resolve_llm_endpoint(&cfg);
                m
            };
            if let (Some(n), Some(s)) = (node, script) {
                spawn(async move {
                    if let Err(e) = rt.start(&n, &s, Some(&model)).await {
                        tracing::error!("[AGENT] Failed to start: {e}");
                    }
                });
            } else {
                tracing::warn!("[AGENT] agent_enabled=true but Node.js or agent script not found");
            }
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
        spawn(async move {
            loop {
                match rx.recv().await {
                    Ok(ProactiveEvent::NewSuggestion(s)) => {
                        let mut list = sug_sig.read().clone();
                        // Evict expired and keep max 5
                        list.retain(|x: &crate::proactive::Suggestion| !x.is_expired());
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

    // Kick off the sidecar health poller once
    use_effect(move || {
        spawn(async move {
            crate::sidecar::poll_backend_health(&mut backend_status).await;
        });
    });

    // Kick off periodic screen capture if enabled in config (runs once on mount)
    let capture_started = use_signal(|| false);
    use_effect(move || {
        let cfg = config.read().clone();
        let db_snap = db.read().clone();
        tracing::info!("[APP] screen_capture_enabled={} capture_interval={}s",
            cfg.screen_capture_enabled, cfg.capture_interval_secs);
        if cfg.screen_capture_enabled && !*capture_started.read() {
            if let Some(Db(d)) = db_snap {
                let interval_secs = cfg.capture_interval_secs.max(1);
                tracing::info!("[APP] Spawning screen capture task (every {interval_secs}s)");
                capture_started.clone().set(true);
                spawn(async move {
                    crate::capture::run_capture_task(d, interval_secs, cfg).await;
                });
            } else {
                tracing::warn!("[APP] Screen capture enabled but DB not open");
            }
        } else if !cfg.screen_capture_enabled {
            tracing::info!("[APP] Screen capture is DISABLED in config — enable in Settings");
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
fn Settings() -> Element {
    pages::settings::SettingsPage()
}
