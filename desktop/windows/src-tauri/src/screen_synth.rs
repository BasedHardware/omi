use std::{fs, path::PathBuf, sync::Mutex};

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::{native, rewind::RewindStore};

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenSynthState {
    enabled: bool,
    watermark_ts: i64,
    last_run_at: Option<i64>,
    last_count: i64,
    denylist: Vec<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenSynthPatch {
    enabled: Option<bool>,
    watermark_ts: Option<i64>,
    last_run_at: Option<Option<i64>>,
    last_count: Option<i64>,
    denylist: Option<Vec<String>>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenSynthRun {
    last_run_at: i64,
    last_count: i64,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenFrameLite {
    ts: i64,
    app: String,
    window_title: String,
    process_name: String,
    ocr_text: String,
}

pub struct ScreenSynthStore {
    state: Mutex<ScreenSynthState>,
    path: PathBuf,
}
impl ScreenSynthStore {
    pub fn open() -> Result<Self, String> {
        let path = native::data_root()
            .map_err(|error| error.to_string())?
            .join("screen-synth.json");
        let state = fs::read(&path)
            .ok()
            .and_then(|bytes| serde_json::from_slice(&bytes).ok())
            .unwrap_or_default();
        Ok(Self {
            state: Mutex::new(state),
            path,
        })
    }
    fn get(&self) -> Result<ScreenSynthState, String> {
        self.state
            .lock()
            .map(|state| state.clone())
            .map_err(|error| error.to_string())
    }
    fn update(&self, patch: ScreenSynthPatch) -> Result<ScreenSynthState, String> {
        let mut state = self.state.lock().map_err(|error| error.to_string())?;
        if let Some(value) = patch.enabled {
            state.enabled = value;
        }
        if let Some(value) = patch.watermark_ts {
            state.watermark_ts = value.max(0);
        }
        if let Some(value) = patch.last_run_at {
            state.last_run_at = value;
        }
        if let Some(value) = patch.last_count {
            state.last_count = value.max(0);
        }
        if let Some(value) = patch.denylist {
            state.denylist = value;
        }
        fs::write(
            &self.path,
            serde_json::to_vec(&*state).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())?;
        Ok(state.clone())
    }
}
#[tauri::command]
pub fn screen_synth_get_state(
    store: State<'_, ScreenSynthStore>,
) -> Result<ScreenSynthState, String> {
    store.get()
}
#[tauri::command]
pub fn screen_synth_set_state(
    patch: ScreenSynthPatch,
    store: State<'_, ScreenSynthStore>,
) -> Result<ScreenSynthState, String> {
    store.update(patch)
}
#[tauri::command]
pub fn screen_synth_frames_since(
    store: State<'_, ScreenSynthStore>,
    rewind: State<'_, RewindStore>,
) -> Result<Vec<ScreenFrameLite>, String> {
    Ok(rewind
        .list(store.get()?.watermark_ts.saturating_add(1), now_ms())?
        .into_iter()
        .map(|frame| ScreenFrameLite {
            ts: frame.ts,
            app: frame.app,
            window_title: frame.window_title,
            process_name: frame.process_name,
            ocr_text: frame.ocr_text,
        })
        .collect())
}
#[tauri::command]
pub fn screen_synth_advance_watermark(
    ts: i64,
    store: State<'_, ScreenSynthStore>,
) -> Result<(), String> {
    let state = store.get()?;
    if ts > state.watermark_ts {
        store.update(ScreenSynthPatch {
            enabled: None,
            watermark_ts: Some(ts),
            last_run_at: None,
            last_count: None,
            denylist: None,
        })?;
    }
    Ok(())
}
#[tauri::command]
pub fn screen_synth_record_run(
    run: ScreenSynthRun,
    store: State<'_, ScreenSynthStore>,
) -> Result<ScreenSynthState, String> {
    store.update(ScreenSynthPatch {
        enabled: None,
        watermark_ts: None,
        last_run_at: Some(Some(run.last_run_at)),
        last_count: Some(run.last_count),
        denylist: None,
    })
}
fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |value| value.as_millis().try_into().unwrap_or(i64::MAX))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_opted_out() {
        assert!(!ScreenSynthState::default().enabled);
    }
}
