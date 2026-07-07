use std::sync::Arc;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use btleplug::api::{Characteristic, Peripheral as _};
use btleplug::platform::Peripheral;
use futures_util::StreamExt;
use tokio::sync::{mpsc, watch, Mutex};
use tracing::{info, warn};
use uuid::Uuid;

use crate::protocol::{
    AudioFrameAssembler, BleAudioCodec, DeviceFeatures, DeviceType,
    AUDIO_CODEC_UUID, AUDIO_DATA_STREAM_UUID, BATTERY_LEVEL_UUID, FEATURES_CHAR_UUID,
    FIRMWARE_REVISION_UUID, HARDWARE_REVISION_UUID, MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConnectionState {
    Disconnected,
    Connecting,
    Connected,
    Streaming,
}

#[derive(Debug, Clone)]
pub struct DeviceInfo {
    pub model: String,
    pub firmware: String,
    pub hardware: String,
    pub manufacturer: String,
    pub codec: BleAudioCodec,
    pub features: DeviceFeatures,
    pub battery_level: Option<u8>,
    pub device_type: DeviceType,
}

pub struct BleConnection {
    peripheral: Peripheral,
    device_type: DeviceType,
    state_tx: watch::Sender<ConnectionState>,
    state_rx: watch::Receiver<ConnectionState>,
    device_info: Arc<Mutex<Option<DeviceInfo>>>,
}

impl BleConnection {
    pub fn new(peripheral: Peripheral, device_type: DeviceType) -> Self {
        let (state_tx, state_rx) = watch::channel(ConnectionState::Disconnected);
        Self {
            peripheral,
            device_type,
            state_tx,
            state_rx,
            device_info: Arc::new(Mutex::new(None)),
        }
    }

    pub fn state(&self) -> ConnectionState {
        self.state_rx.borrow().clone()
    }

    pub fn subscribe_state(&self) -> watch::Receiver<ConnectionState> {
        self.state_rx.clone()
    }

    pub async fn device_info(&self) -> Option<DeviceInfo> {
        self.device_info.lock().await.clone()
    }

    pub async fn connect(&self) -> Result<()> {
        let _ = self.state_tx.send(ConnectionState::Connecting);
        info!("[BLE] Connecting to {}...", self.peripheral.id());

        self.peripheral
            .connect()
            .await
            .context("Failed to connect to device")?;

        self.peripheral
            .discover_services()
            .await
            .context("Failed to discover services")?;

        let info = self.read_device_info().await;
        *self.device_info.lock().await = Some(info);

        let _ = self.state_tx.send(ConnectionState::Connected);
        info!("[BLE] Connected and services discovered");
        Ok(())
    }

    pub async fn disconnect(&self) -> Result<()> {
        self.peripheral.disconnect().await.ok();
        let _ = self.state_tx.send(ConnectionState::Disconnected);
        info!("[BLE] Disconnected");
        Ok(())
    }

    pub async fn is_connected(&self) -> bool {
        self.peripheral.is_connected().await.unwrap_or(false)
    }

    pub async fn read_battery(&self) -> Option<u8> {
        let uuid = Uuid::parse_str(BATTERY_LEVEL_UUID).ok()?;
        let char = self.find_characteristic(&uuid)?;
        let data = self.peripheral.read(&char).await.ok()?;
        data.first().copied()
    }

    pub async fn stream_audio(
        &self,
        audio_tx: mpsc::Sender<Vec<u8>>,
        mut stop_rx: watch::Receiver<bool>,
    ) -> Result<()> {
        let info = self
            .device_info
            .lock()
            .await
            .clone()
            .context("Not connected — no device info")?;

        let audio_uuid = Uuid::parse_str(AUDIO_DATA_STREAM_UUID)
            .context("Invalid audio stream UUID")?;

        let audio_char = self
            .find_characteristic(&audio_uuid)
            .context("Audio data stream characteristic not found")?;

        self.peripheral
            .subscribe(&audio_char)
            .await
            .context("Failed to subscribe to audio notifications")?;

        let _ = self.state_tx.send(ConnectionState::Streaming);
        info!("[BLE] Streaming audio, codec={}", info.codec);

        let mut assembler = AudioFrameAssembler::new(info.codec);
        let mut notifications = self
            .peripheral
            .notifications()
            .await
            .context("Failed to get notification stream")?;

        loop {
            tokio::select! {
                biased;

                _ = stop_rx.changed() => {
                    if *stop_rx.borrow() {
                        info!("[BLE] Stop signal received, ending audio stream");
                        break;
                    }
                }

                notification = notifications.next() => {
                    match notification {
                        Some(n) if n.uuid == audio_uuid => {
                            let frames = assembler.process_notification(&n.value);
                            for frame in frames {
                                if audio_tx.send(frame).await.is_err() {
                                    info!("[BLE] Audio receiver dropped, stopping stream");
                                    break;
                                }
                            }
                        }
                        Some(_) => {}
                        None => {
                            warn!("[BLE] Notification stream ended (device disconnected?)");
                            break;
                        }
                    }
                }
            }
        }

        self.peripheral.unsubscribe(&audio_char).await.ok();
        let _ = self.state_tx.send(ConnectionState::Connected);
        info!(
            "[BLE] Audio stream ended. Lost packets: {}",
            assembler.lost_packets()
        );
        Ok(())
    }

    async fn read_device_info(&self) -> DeviceInfo {
        let codec = self.read_codec().await.unwrap_or_else(|| self.device_type.default_codec());
        let features = self.read_features().await.unwrap_or(DeviceFeatures(0));
        let battery_level = self.read_battery().await;

        let model = self.read_string_char(MODEL_NUMBER_UUID).await.unwrap_or_default();
        let firmware = self.read_string_char(FIRMWARE_REVISION_UUID).await.unwrap_or_default();
        let hardware = self.read_string_char(HARDWARE_REVISION_UUID).await.unwrap_or_default();
        let manufacturer = self.read_string_char(MANUFACTURER_NAME_UUID).await.unwrap_or_default();

        info!(
            "[BLE] Device: model={model}, fw={firmware}, hw={hardware}, mfr={manufacturer}, codec={codec}, features=0x{:04X}",
            features.0
        );

        DeviceInfo {
            model,
            firmware,
            hardware,
            manufacturer,
            codec,
            features,
            battery_level,
            device_type: self.device_type.clone(),
        }
    }

    async fn read_codec(&self) -> Option<BleAudioCodec> {
        let uuid = Uuid::parse_str(AUDIO_CODEC_UUID).ok()?;
        let char = self.find_characteristic(&uuid)?;
        let data = self.peripheral.read(&char).await.ok()?;
        let id = *data.first()?;
        let codec = BleAudioCodec::from_id(id);
        if codec.is_none() {
            warn!("[BLE] Unknown codec ID: {id}");
        }
        codec
    }

    async fn read_features(&self) -> Option<DeviceFeatures> {
        let uuid = Uuid::parse_str(FEATURES_CHAR_UUID).ok()?;
        let char = self.find_characteristic(&uuid)?;
        let data = self.peripheral.read(&char).await.ok()?;
        if data.len() >= 2 {
            Some(DeviceFeatures(u16::from_le_bytes([data[0], data[1]])))
        } else if data.len() == 1 {
            Some(DeviceFeatures(data[0] as u16))
        } else {
            None
        }
    }

    async fn read_string_char(&self, uuid_str: &str) -> Option<String> {
        let uuid = Uuid::parse_str(uuid_str).ok()?;
        let char = self.find_characteristic(&uuid)?;
        let data = self.peripheral.read(&char).await.ok()?;
        Some(String::from_utf8_lossy(&data).trim().to_string())
    }

    fn find_characteristic(&self, uuid: &Uuid) -> Option<Characteristic> {
        for service in self.peripheral.services() {
            for char in &service.characteristics {
                if char.uuid == *uuid {
                    return Some(char.clone());
                }
            }
        }
        None
    }
}

// ── Auto-reconnect wrapper ──────────────────────────────────────────────────

pub async fn connect_with_retry(
    peripheral: Peripheral,
    device_type: DeviceType,
    max_retries: u32,
) -> Result<BleConnection> {
    let conn = BleConnection::new(peripheral, device_type);

    for attempt in 1..=max_retries {
        match conn.connect().await {
            Ok(()) => return Ok(conn),
            Err(e) => {
                warn!("[BLE] Connect attempt {attempt}/{max_retries} failed: {e:#}");
                if attempt < max_retries {
                    let backoff = Duration::from_secs(2u64.pow(attempt.min(4)));
                    tokio::time::sleep(backoff).await;
                }
            }
        }
    }

    bail!("Failed to connect after {max_retries} attempts")
}

pub async fn reconnect_loop(
    conn: &BleConnection,
    mut stop_rx: watch::Receiver<bool>,
) {
    loop {
        tokio::select! {
            biased;
            _ = stop_rx.changed() => {
                if *stop_rx.borrow() {
                    return;
                }
            }
            _ = tokio::time::sleep(Duration::from_secs(5)) => {
                if !conn.is_connected().await && conn.state() != ConnectionState::Connecting {
                    info!("[BLE] Connection lost, attempting reconnect...");
                    match conn.connect().await {
                        Ok(()) => info!("[BLE] Reconnected successfully"),
                        Err(e) => warn!("[BLE] Reconnect failed: {e:#}"),
                    }
                }
            }
        }
    }
}
