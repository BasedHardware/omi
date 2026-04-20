//! Cross-platform Bluetooth Low Energy device discovery and pairing.
//!
//! Ports the core discovery/pairing surface of the macOS-only
//! `BluetoothManager.swift` to a cross-platform Rust module backed by the
//! `btleplug` crate. Audio streaming is intentionally out of scope — this is
//! pairing + a Device Settings page only.
//!
//! Events emitted to the frontend (via `tauri::Emitter`):
//!
//! - `bluetooth://device-found` — `{ id, name, rssi, address }` for every
//!   unique peripheral the OS surfaces during a scan.
//! - `bluetooth://connection-state` — `{ id, status, error? }` where
//!   `status` is one of `connecting | connected | disconnected | failed`.
//!
//! Commands (invoked via `@tauri-apps/api/core`'s `invoke`):
//!
//! - `bluetooth_start_scan` — begin scanning, returns `Ok(())` or a
//!   structured error message if no adapter is available.
//! - `bluetooth_stop_scan` — stop the current scan (idempotent).
//! - `bluetooth_connect(id)` — issue a connect request. The connection is
//!   attempted on a background task; progress is reported via events.
//! - `bluetooth_disconnect(id)` — disconnect and drop any tracked peripheral.
//! - `bluetooth_list_connected` — snapshot of currently connected peripherals.
//!
//! All OS-specific differences (permissions, adapter discovery, async
//! streams) are handled by `btleplug`. We do NOT shell out to
//! `bluetoothctl`/`blueutil`/etc. — keeping the module portable across
//! macOS / Linux / Windows is a hard requirement.

use std::collections::HashMap;
use std::sync::Arc;

use btleplug::api::{Central, CentralEvent, Manager as _, Peripheral as _, ScanFilter};
use btleplug::platform::{Adapter, Manager, Peripheral, PeripheralId};
use futures::StreamExt;
use serde::Serialize;
use tauri::{command, AppHandle, Emitter, Manager as TauriManager, State};
use tokio::sync::Mutex;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct DiscoveredDevice {
    /// Stable opaque identifier — `PeripheralId.to_string()`. Callers pass this
    /// back to `connect` / `disconnect`.
    pub id: String,
    pub name: Option<String>,
    pub rssi: Option<i16>,
    /// BLE MAC (Linux / Windows) or anonymized peripheral UUID (macOS). Used
    /// for display, not as a lookup key.
    pub address: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ConnectedDevice {
    pub id: String,
    pub name: Option<String>,
    pub address: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ConnectionStateEvent {
    id: String,
    status: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/// Shared Bluetooth state, registered via `app.manage(...)` in `main.rs`.
///
/// `adapter` is created lazily on first use so we don't touch the Bluetooth
/// stack at startup — on Linux this would spuriously power on the radio or
/// log permission warnings even when the user never opens the Devices page.
pub struct BluetoothState {
    inner: Arc<Mutex<Inner>>,
}

struct Inner {
    manager: Option<Manager>,
    adapter: Option<Adapter>,
    /// Peripherals we've handed out to the frontend (by `PeripheralId.to_string()`).
    /// We need to hang on to them so `connect`/`disconnect` can locate the
    /// `btleplug` object — `PeripheralId` is not round-trippable from a string.
    peripherals: HashMap<String, Peripheral>,
    /// Set when a scan is active so `stop_scan` is idempotent and repeated
    /// `start_scan` calls don't spawn duplicate event-forwarder tasks.
    scanning: bool,
}

impl Default for BluetoothState {
    fn default() -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner {
                manager: None,
                adapter: None,
                peripherals: HashMap::new(),
                scanning: false,
            })),
        }
    }
}

// ---------------------------------------------------------------------------
// Adapter bring-up
// ---------------------------------------------------------------------------

/// Return the first BLE adapter, creating the `Manager` on first access.
/// Surfaces a human-readable error if the OS reports no adapter — e.g.
/// Bluetooth turned off, missing permissions, or running in a VM without
/// a BT radio.
async fn ensure_adapter(inner: &mut Inner) -> Result<Adapter, String> {
    if let Some(adapter) = &inner.adapter {
        return Ok(adapter.clone());
    }

    let manager = match &inner.manager {
        Some(m) => m.clone(),
        None => {
            let m = Manager::new()
                .await
                .map_err(|e| format!("Bluetooth manager unavailable: {}", e))?;
            inner.manager = Some(m.clone());
            m
        }
    };

    let adapters = manager
        .adapters()
        .await
        .map_err(|e| format!("Failed to enumerate Bluetooth adapters: {}", e))?;

    let adapter = adapters.into_iter().next().ok_or_else(|| {
        "No Bluetooth adapter found. Make sure Bluetooth is turned on and the app has permission to use it.".to_string()
    })?;

    inner.adapter = Some(adapter.clone());
    Ok(adapter)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async fn describe_peripheral(peripheral: &Peripheral) -> DiscoveredDevice {
    let id = peripheral.id().to_string();
    let address = peripheral.address().to_string();
    let name = peripheral
        .properties()
        .await
        .ok()
        .flatten()
        .and_then(|p| p.local_name);
    let rssi = peripheral
        .properties()
        .await
        .ok()
        .flatten()
        .and_then(|p| p.rssi);
    DiscoveredDevice {
        id,
        name,
        rssi,
        address,
    }
}

fn emit_connection(app: &AppHandle, id: &str, status: &'static str, error: Option<String>) {
    let payload = ConnectionStateEvent {
        id: id.to_string(),
        status,
        error,
    };
    if let Err(e) = app.emit("bluetooth://connection-state", payload) {
        tracing::warn!("[bluetooth] emit connection-state failed: {}", e);
    }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

#[command]
pub async fn bluetooth_start_scan(
    app: AppHandle,
    state: State<'_, BluetoothState>,
) -> Result<(), String> {
    let inner_arc = state.inner.clone();
    let mut inner = inner_arc.lock().await;

    if inner.scanning {
        tracing::debug!("[bluetooth] scan already active");
        return Ok(());
    }

    let adapter = ensure_adapter(&mut inner).await?;
    let events = adapter
        .events()
        .await
        .map_err(|e| format!("Failed to subscribe to adapter events: {}", e))?;

    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(|e| format!("Failed to start scan: {}", e))?;

    inner.scanning = true;
    drop(inner);

    tracing::info!("[bluetooth] scan started");

    // Forward adapter events to the frontend on a background task. The task
    // lives as long as the event stream — when `stop_scan` is called the
    // adapter drops the subscription and the stream ends, so the task exits.
    let adapter_for_task = adapter.clone();
    let state_for_task = inner_arc.clone();
    let app_for_task = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut events = events;
        while let Some(event) = events.next().await {
            match event {
                CentralEvent::DeviceDiscovered(id)
                | CentralEvent::DeviceUpdated(id) => {
                    if let Ok(peripheral) = adapter_for_task.peripheral(&id).await {
                        let desc = describe_peripheral(&peripheral).await;
                        // Skip unnamed devices — they're almost always background
                        // broadcasts (beacons, Apple Continuity, random BT HID)
                        // and clutter the UI without being useful to pair.
                        if desc.name.as_deref().map(str::is_empty).unwrap_or(true) {
                            continue;
                        }
                        state_for_task
                            .lock()
                            .await
                            .peripherals
                            .insert(desc.id.clone(), peripheral.clone());
                        if let Err(e) = app_for_task.emit("bluetooth://device-found", desc) {
                            tracing::warn!("[bluetooth] emit device-found failed: {}", e);
                        }
                    }
                }
                CentralEvent::DeviceConnected(id) => {
                    emit_connection(&app_for_task, &id.to_string(), "connected", None);
                }
                CentralEvent::DeviceDisconnected(id) => {
                    emit_connection(&app_for_task, &id.to_string(), "disconnected", None);
                }
                _ => {}
            }
        }
        tracing::debug!("[bluetooth] adapter event stream ended");
    });

    Ok(())
}

#[command]
pub async fn bluetooth_stop_scan(state: State<'_, BluetoothState>) -> Result<(), String> {
    let inner_arc = state.inner.clone();
    let mut inner = inner_arc.lock().await;

    if !inner.scanning {
        return Ok(());
    }

    if let Some(adapter) = inner.adapter.clone() {
        if let Err(e) = adapter.stop_scan().await {
            tracing::warn!("[bluetooth] stop_scan failed: {}", e);
        }
    }

    inner.scanning = false;
    tracing::info!("[bluetooth] scan stopped");
    Ok(())
}

#[command]
pub async fn bluetooth_connect(
    app: AppHandle,
    state: State<'_, BluetoothState>,
    id: String,
) -> Result<(), String> {
    let inner_arc = state.inner.clone();
    let peripheral = {
        let inner = inner_arc.lock().await;
        inner
            .peripherals
            .get(&id)
            .cloned()
            .ok_or_else(|| format!("Unknown peripheral id: {}", id))?
    };

    emit_connection(&app, &id, "connecting", None);

    // Run the actual connect on a background task — `btleplug`'s connect can
    // block for several seconds (L2CAP handshake, service discovery) and we
    // don't want to hold the IPC channel open that long.
    let app_for_task = app.clone();
    let id_for_task = id.clone();
    tauri::async_runtime::spawn(async move {
        match peripheral.connect().await {
            Ok(()) => {
                // Verify the connection — some platforms (notably Linux) return
                // Ok() from connect() before the radio-level handshake settles.
                let connected = peripheral.is_connected().await.unwrap_or(false);
                if connected {
                    emit_connection(&app_for_task, &id_for_task, "connected", None);
                } else {
                    emit_connection(
                        &app_for_task,
                        &id_for_task,
                        "failed",
                        Some("Connection did not complete".to_string()),
                    );
                }
            }
            Err(e) => {
                tracing::warn!("[bluetooth] connect({}) failed: {}", id_for_task, e);
                emit_connection(&app_for_task, &id_for_task, "failed", Some(e.to_string()));
            }
        }
    });

    Ok(())
}

#[command]
pub async fn bluetooth_disconnect(
    app: AppHandle,
    state: State<'_, BluetoothState>,
    id: String,
) -> Result<(), String> {
    let inner_arc = state.inner.clone();
    let peripheral = {
        let inner = inner_arc.lock().await;
        inner.peripherals.get(&id).cloned()
    };

    let Some(peripheral) = peripheral else {
        // Not fatal — already gone. Emit `disconnected` so the UI settles.
        emit_connection(&app, &id, "disconnected", None);
        return Ok(());
    };

    if let Err(e) = peripheral.disconnect().await {
        tracing::warn!("[bluetooth] disconnect({}) failed: {}", id, e);
        return Err(format!("Disconnect failed: {}", e));
    }

    emit_connection(&app, &id, "disconnected", None);
    Ok(())
}

#[command]
pub async fn bluetooth_list_connected(
    state: State<'_, BluetoothState>,
) -> Result<Vec<ConnectedDevice>, String> {
    let inner_arc = state.inner.clone();
    let inner = inner_arc.lock().await;

    // Snapshot the tracked peripherals — `is_connected` is async so we can't
    // filter inside the iterator lock. Collect refs first, release the lock.
    let snapshot: Vec<(String, Peripheral)> = inner
        .peripherals
        .iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    drop(inner);

    let mut out = Vec::new();
    for (id, peripheral) in snapshot {
        if peripheral.is_connected().await.unwrap_or(false) {
            let desc = describe_peripheral(&peripheral).await;
            out.push(ConnectedDevice {
                id,
                name: desc.name,
                address: desc.address,
            });
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// Registration helper
// ---------------------------------------------------------------------------

/// Register the shared `BluetoothState` on the app. Call once from `setup()`.
pub fn init(app: &AppHandle) {
    app.manage(BluetoothState::default());
}

// Silence unused-import warnings on platforms where `PeripheralId` is only
// used transitively through btleplug traits.
#[allow(dead_code)]
fn _assert_peripheral_id(_id: PeripheralId) {}
