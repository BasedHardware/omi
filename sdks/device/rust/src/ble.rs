//! Optional BLE transport via `btleplug` (feature `ble`).
//!
//! Needs a local adapter + OS Bluetooth permission. Scan/listen are async.

use std::time::Duration;

use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures_util::stream::StreamExt;
use thiserror::Error;
use tokio::time;
use uuid::Uuid;

use crate::{strip_packet_header, AUDIO_DATA_UUID, SERVICE_UUID};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeviceInfo {
    pub id: String,
    pub name: String,
    pub rssi: Option<i16>,
}

#[derive(Debug, Error)]
pub enum BleError {
    #[error("bluetooth: {0}")]
    Bluetooth(#[from] btleplug::Error),
    #[error("no bluetooth adapter")]
    NoAdapter,
    #[error("device not found: {0}")]
    DeviceNotFound(String),
    #[error("characteristic not found: {0}")]
    CharacteristicNotFound(String),
    #[error("invalid uuid: {0}")]
    InvalidUuid(#[from] uuid::Error),
}

async fn first_adapter() -> Result<Adapter, BleError> {
    let manager = Manager::new().await?;
    let mut adapters = manager.adapters().await?;
    adapters.pop().ok_or(BleError::NoAdapter)
}

async fn device_info(peripheral: &Peripheral) -> DeviceInfo {
    let id = peripheral.id().to_string();
    let props = peripheral.properties().await.ok().flatten();
    let name = props
        .as_ref()
        .and_then(|p| p.local_name.clone())
        .unwrap_or_default();
    let rssi = props.as_ref().and_then(|p| p.rssi);
    DeviceInfo { id, name, rssi }
}

/// Scan for nearby BLE peripherals for `timeout`.
pub async fn scan(timeout: Duration) -> Result<Vec<DeviceInfo>, BleError> {
    let adapter = first_adapter().await?;
    // Prefer Omi service filter when advertising includes it; still collect all hits.
    let service = Uuid::parse_str(SERVICE_UUID)?;
    adapter
        .start_scan(ScanFilter {
            services: vec![service],
        })
        .await?;
    time::sleep(timeout).await;
    let peripherals = adapter.peripherals().await?;
    let mut out = Vec::with_capacity(peripherals.len());
    for p in peripherals {
        out.push(device_info(&p).await);
    }
    let _ = adapter.stop_scan().await;
    Ok(out)
}

async fn find_peripheral(adapter: &Adapter, device_id: &str) -> Result<Peripheral, BleError> {
    for p in adapter.peripherals().await? {
        if p.id().to_string() == device_id {
            return Ok(p);
        }
        if let Ok(Some(props)) = p.properties().await {
            if props.address.to_string() == device_id {
                return Ok(p);
            }
        }
    }
    Err(BleError::DeviceNotFound(device_id.to_string()))
}

/// Connect to `device_id` and invoke `on_packet` for each raw audio notify payload.
///
/// Runs until the notification stream ends or an error occurs.
pub async fn listen<F>(device_id: &str, mut on_packet: F) -> Result<(), BleError>
where
    F: FnMut(Vec<u8>) + Send,
{
    let adapter = first_adapter().await?;
    // Brief scan so the target appears in the adapter cache when not already known.
    adapter.start_scan(ScanFilter::default()).await?;
    time::sleep(Duration::from_secs(2)).await;
    let peripheral = find_peripheral(&adapter, device_id).await?;
    let _ = adapter.stop_scan().await;

    if !peripheral.is_connected().await? {
        peripheral.connect().await?;
    }
    peripheral.discover_services().await?;

    let audio_uuid = Uuid::parse_str(AUDIO_DATA_UUID)?;
    let characteristic = peripheral
        .characteristics()
        .into_iter()
        .find(|c| c.uuid == audio_uuid)
        .ok_or_else(|| BleError::CharacteristicNotFound(AUDIO_DATA_UUID.to_string()))?;

    peripheral.subscribe(&characteristic).await?;
    let mut notifications = peripheral.notifications().await?;
    while let Some(data) = notifications.next().await {
        if data.uuid == audio_uuid {
            on_packet(data.value);
        }
    }
    Ok(())
}

/// Like [`listen`], but strips the 3-byte Omi packet header before the callback.
pub async fn listen_payload<F>(device_id: &str, mut on_payload: F) -> Result<(), BleError>
where
    F: FnMut(Vec<u8>) + Send,
{
    listen(device_id, move |packet| {
        let payload = strip_packet_header(&packet);
        if !payload.is_empty() {
            on_payload(payload.to_vec());
        }
    })
    .await
}
