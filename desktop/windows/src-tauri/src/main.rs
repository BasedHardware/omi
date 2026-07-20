#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{Manager, State};

mod agent_runtime;
mod automation;
mod conversations;
mod insights;
mod integrations;
mod knowledge;
mod listen;
mod memory;
mod native;
mod overlay;
mod rewind;
mod screen_synth;
mod usage;

/// Called by the renderer when Firebase auth resolves (or by local dev harness
/// flows that discover the user after launch). Closes open database handles,
/// migrates anonymous/legacy state into the per-user root, then re-opens stores.
#[tauri::command]
fn set_auth_user(
    uid: String,
    conversation: State<'_, conversations::ConversationStore>,
    rewind: State<'_, rewind::RewindStore>,
    usage: State<'_, usage::UsageStore>,
    insights: State<'_, insights::InsightStore>,
    knowledge: State<'_, knowledge::KnowledgeStore>,
    screen_synth: State<'_, screen_synth::ScreenSynthStore>,
) -> Result<(), String> {
    conversation.close()?;
    rewind.close()?;
    usage.close()?;
    insights.close()?;
    knowledge.close()?;

    native::set_user_id(uid);
    native::migrate_to_current_user().map_err(|error| error.to_string())?;

    let database_file = native::database_file().map_err(|error| error.to_string())?;
    let data_root = native::data_root().map_err(|error| error.to_string())?;

    conversation.reroot(&database_file)?;
    rewind.reroot(&database_file, &data_root)?;
    usage.reroot(&database_file, &data_root)?;
    insights.reroot(&database_file, &data_root)?;
    knowledge.reroot(&database_file)?;
    screen_synth.reroot(&data_root)?;
    Ok(())
}

fn main() {
    native::initialize_user_id();
    if let Err(error) = native::migrate_to_current_user() {
        eprintln!("Omi data migration warning: {error}");
    }

    let store = conversations::ConversationStore::open(
        &native::database_file().expect("failed to resolve Omi database path"),
    )
    .expect("failed to open Omi database");
    let rewind = rewind::RewindStore::open(
        &native::database_file().expect("failed to resolve Omi database path"),
    )
    .expect("failed to open Omi Rewind storage");
    let usage = usage::UsageStore::open(
        &native::database_file().expect("failed to resolve Omi database path"),
    )
    .expect("failed to open Omi usage storage");
    let insights = insights::InsightStore::open(
        &native::database_file().expect("failed to resolve Omi database path"),
    )
    .expect("failed to open Omi insights storage");
    let knowledge = knowledge::KnowledgeStore::open(
        &native::database_file().expect("failed to resolve Omi database path"),
    )
    .expect("failed to open Omi knowledge database");
    let screen_synth =
        screen_synth::ScreenSynthStore::open().expect("failed to open screen synthesis storage");
    tauri::Builder::default()
        .manage(store)
        .manage(rewind)
        .manage(usage)
        .manage(insights)
        .manage(knowledge)
        .manage(screen_synth)
        .manage(listen::ListenSessions::default())
        .manage(overlay::OverlayState::default())
        .manage(integrations::GoogleRuntime::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            app.manage(agent_runtime::AgentRuntimeState::start(
                app.handle().clone(),
            ));
            overlay::register_default(app.handle());
            rewind::start_capture_scheduler(app.handle().clone());
            #[cfg(target_os = "windows")]
            usage::start_monitor(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            set_auth_user,
            automation::automation_capabilities,
            agent_runtime::agent_runtime_dispatch,
            agent_runtime::agent_runtime_request,
            automation::automation_target_window,
            automation::automation_snapshot,
            automation::automation_confirm_run,
            native::database_path,
            insights::insight_get_settings,
            insights::insight_set_settings,
            insights::insight_add,
            insights::insight_recent,
            insights::insight_show,
            insights::insight_dismiss,
            insights::insight_test,
            knowledge::file_index::file_index_scan,
            knowledge::file_index::file_index_status,
            knowledge::file_index::file_index_apps,
            knowledge::file_index::file_index_capabilities,
            knowledge::file_index::kg_file_index_digest,
            knowledge::graph::kg_save_graph,
            knowledge::graph::kg_status,
            usage::app_usage_list,
            knowledge::graph::kg_query_nodes,
            knowledge::graph::kg_search_files,
            knowledge::graph::kg_execute_sql,
            knowledge::graph::local_graph_load,
            knowledge::graph::local_graph_upsert,
            knowledge::graph::local_graph_clear,
            rewind::rewind_frames,
            rewind::rewind_day_bounds,
            rewind::rewind_search,
            rewind::rewind_frame_image,
            rewind::rewind_get_settings,
            rewind::rewind_capture_capability,
            rewind::rewind_request_capture_permission,
            rewind::rewind_capture_now,
            rewind::rewind_set_settings,
            rewind::rewind_prune_now,
            rewind::screen_read_text,
            screen_synth::screen_synth_get_state,
            screen_synth::screen_synth_set_state,
            screen_synth::screen_synth_frames_since,
            screen_synth::screen_synth_advance_watermark,
            screen_synth::screen_synth_record_run,
            usage::usage_list,
            usage::usage_flush,
            usage::usage_get_settings,
            usage::usage_set_settings,
            memory::memory_import_parse,
            memory::memory_export_obsidian,
            memory::memory_export_file,
            memory::memory_export_notion,
            memory::notion_set_token,
            memory::notion_clear_token,
            integrations::google_status,
            integrations::auth_google_sign_in,
            integrations::google_connect,
            integrations::google_disconnect,
            integrations::google_gmail_fetch_new,
            integrations::google_calendar_fetch_new,
            integrations::google_mark_processed,
            integrations::sticky_notes_read,
            conversations::local_conversation_get,
            conversations::local_conversation_list,
            conversations::local_conversation_upsert,
            conversations::local_conversation_delete,
            conversations::local_conversation_update_title,
            listen::listen_start,
            listen::listen_stop,
            listen::listen_feed,
            overlay::overlay_set_enabled,
            overlay::overlay_set_height,
            overlay::overlay_hide,
            overlay::overlay_focus_main,
            overlay::overlay_set_accelerator,
            overlay::overlay_suspend_shortcut,
            overlay::overlay_resume_shortcut,
            overlay::overlay_notify_voice_captured,
            overlay::overlay_notify_asked,
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Omi desktop host");
}
