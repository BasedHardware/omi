//! Omi Devkit BLE GATT peripheral — local CoreBluetooth (via ble-peripheral-rust).
//! Not an HTTP/API host. Advertises audio service UUID for RN v5 discovery.

use std::sync::atomic::{AtomicBool, AtomicU16, AtomicU8, Ordering};
use std::sync::Arc;

use ble_peripheral_rust::gatt::characteristic::Characteristic;
use ble_peripheral_rust::gatt::peripheral_event::{
    PeripheralEvent, ReadRequestResponse, RequestResponse, WriteRequestResponse,
};
use ble_peripheral_rust::gatt::properties::{AttributePermission, CharacteristicProperty};
use ble_peripheral_rust::gatt::service::Service;
use ble_peripheral_rust::uuid::ShortUuid;
use ble_peripheral_rust::{Peripheral, PeripheralImpl};
use tokio::sync::{mpsc, watch};
use uuid::Uuid;

/// Audio service — RN v5 discovery filter.
pub const AUDIO_SERVICE: &str = "19B10000-E8F2-537E-4F6C-D104768A1214";
const AUDIO_CHAR: &str = "19B10001-E8F2-537E-4F6C-D104768A1214";
const AUDIO_CODEC_CHAR: &str = "19B10002-E8F2-537E-4F6C-D104768A1214";

const DIS_SERVICE: u16 = 0x180A;
const MODEL_NUMBER: u16 = 0x2A24;
const SERIAL_NUMBER: u16 = 0x2A25;
const FIRMWARE_REV: u16 = 0x2A26;
const HARDWARE_REV: u16 = 0x2A27;
const MANUFACTURER: u16 = 0x2A29;

const BATTERY_SERVICE: u16 = 0x180F;
const BATTERY_LEVEL: u16 = 0x2A19;

const FEATURES_SERVICE: &str = "19B10020-E8F2-537E-4F6C-D104768A1214";
const FEATURES_CHAR: &str = "19B10021-E8F2-537E-4F6C-D104768A1214";
/// bit2=button(4), bit7=led(128), bit8=micGain(256) → 388
const FEATURES_MASK: u32 = 4 | (1 << 7) | (1 << 8);

const BUTTON_SERVICE: &str = "23ba7924-0000-1000-7450-346eac492e92";
const BUTTON_CHAR: &str = "23ba7925-0000-1000-7450-346eac492e92";

const SETTINGS_SERVICE: &str = "19B10010-E8F2-537E-4F6C-D104768A1214";
const LED_CHAR: &str = "19B10011-E8F2-537E-4F6C-D104768A1214";
const MIC_GAIN_CHAR: &str = "19B10012-E8F2-537E-4F6C-D104768A1214";
const CHARGING_CHAR: &str = "19B10013-E8F2-537E-4F6C-D104768A1214";

const LOCAL_NAME: &str = "Omi Devkit";

fn uuid_str(s: &str) -> Uuid {
    Uuid::parse_str(s).expect("valid UUID")
}

fn uuid_short(u: u16) -> Uuid {
    Uuid::from_short(u)
}

fn read_char(uuid: Uuid, value: Option<Vec<u8>>) -> Characteristic {
    Characteristic {
        uuid,
        properties: vec![CharacteristicProperty::Read],
        permissions: vec![AttributePermission::Readable],
        value,
        descriptors: vec![],
    }
}

fn notify_char(uuid: Uuid) -> Characteristic {
    Characteristic {
        uuid,
        properties: vec![CharacteristicProperty::Notify],
        permissions: vec![AttributePermission::Readable],
        value: None,
        descriptors: vec![],
    }
}

fn read_notify_char(uuid: Uuid) -> Characteristic {
    Characteristic {
        uuid,
        properties: vec![
            CharacteristicProperty::Read,
            CharacteristicProperty::Notify,
        ],
        permissions: vec![AttributePermission::Readable],
        value: None,
        descriptors: vec![],
    }
}

fn read_write_char(uuid: Uuid) -> Characteristic {
    Characteristic {
        uuid,
        properties: vec![
            CharacteristicProperty::Read,
            CharacteristicProperty::Write,
        ],
        permissions: vec![
            AttributePermission::Readable,
            AttributePermission::Writeable,
        ],
        value: None,
        descriptors: vec![],
    }
}

/// Shared sim state mutated from UI and BLE event loop.
#[derive(Clone)]
pub struct BleState {
    pub battery: Arc<AtomicU8>,
    pub charging: Arc<AtomicBool>,
    pub led: Arc<AtomicU8>,
    pub mic_gain: Arc<AtomicU8>,
    pub packet_counter: Arc<AtomicU16>,
    pub advertising: Arc<AtomicBool>,
    pub status: watch::Sender<String>,
}

impl BleState {
    pub fn new() -> (Self, watch::Receiver<String>) {
        let (tx, rx) = watch::channel("starting…".to_string());
        (
            Self {
                battery: Arc::new(AtomicU8::new(87)),
                charging: Arc::new(AtomicBool::new(false)),
                led: Arc::new(AtomicU8::new(50)),
                mic_gain: Arc::new(AtomicU8::new(4)),
                packet_counter: Arc::new(AtomicU16::new(0)),
                advertising: Arc::new(AtomicBool::new(false)),
                status: tx,
            },
            rx,
        )
    }

    pub fn set_status(&self, s: impl Into<String>) {
        let _ = self.status.send(s.into());
    }
}

/// Commands from the GPUI UI into the BLE task.
#[derive(Debug, Clone)]
pub enum BleCommand {
    SetBattery(u8),
    SetCharging(bool),
    FireDoublePress,
    WriteAudio(Vec<u8>),
    Shutdown,
}

pub fn spawn_ble(state: BleState) -> mpsc::UnboundedSender<BleCommand> {
    let (cmd_tx, cmd_rx) = mpsc::unbounded_channel();
    std::thread::Builder::new()
        .name("omi-ble".into())
        .spawn(move || {
            let rt = tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .build()
                .expect("tokio runtime");
            rt.block_on(ble_main(state, cmd_rx));
        })
        .expect("spawn ble thread");
    cmd_tx
}

async fn ble_main(state: BleState, mut cmd_rx: mpsc::UnboundedReceiver<BleCommand>) {
    let (event_tx, mut event_rx) = mpsc::channel::<PeripheralEvent>(256);

    let mut peripheral = match Peripheral::new(event_tx).await {
        Ok(p) => p,
        Err(e) => {
            state.set_status(format!("BLE init failed: {e}"));
            log::error!("Peripheral::new failed: {e}");
            return;
        }
    };

    // Drain events on a side task with shared state
    let state_ev = state.clone();
    tokio::spawn(async move {
        while let Some(ev) = event_rx.recv().await {
            handle_event(ev, &state_ev);
        }
    });

    // Wait for powered on
    state.set_status("waiting for Bluetooth powered on…");
    loop {
        match peripheral.is_powered().await {
            Ok(true) => break,
            Ok(false) => tokio::time::sleep(std::time::Duration::from_millis(200)).await,
            Err(e) => {
                state.set_status(format!("BLE power check failed: {e}"));
                log::error!("is_powered: {e}");
                return;
            }
        }
    }

    if let Err(e) = add_all_services(&mut peripheral).await {
        state.set_status(format!("add services failed: {e}"));
        log::error!("add services: {e}");
        return;
    }

    let audio_uuid = uuid_str(AUDIO_SERVICE);
    if let Err(e) = peripheral
        .start_advertising(LOCAL_NAME, &[audio_uuid])
        .await
    {
        state.set_status(format!("advertise failed: {e}"));
        log::error!("start_advertising: {e}");
        return;
    }

    state.advertising.store(true, Ordering::Relaxed);
    state.set_status(format!("advertising as {LOCAL_NAME}"));
    log::info!("Advertising as {LOCAL_NAME}");

    // Command loop
    while let Some(cmd) = cmd_rx.recv().await {
        match cmd {
            BleCommand::Shutdown => break,
            BleCommand::SetBattery(level) => {
                let level = level.min(100);
                state.battery.store(level, Ordering::Relaxed);
                let _ = peripheral
                    .update_characteristic(uuid_short(BATTERY_LEVEL), vec![level])
                    .await;
            }
            BleCommand::SetCharging(on) => {
                state.charging.store(on, Ordering::Relaxed);
                let _ = peripheral
                    .update_characteristic(uuid_str(CHARGING_CHAR), vec![if on { 1 } else { 0 }])
                    .await;
            }
            BleCommand::FireDoublePress => {
                let payload = vec![2, 0, 0, 0, 0, 0, 0, 0];
                match peripheral
                    .update_characteristic(uuid_str(BUTTON_CHAR), payload)
                    .await
                {
                    Ok(()) => log::info!("Button double-press notified"),
                    Err(e) => log::warn!("Button double-press failed: {e}"),
                }
            }
            BleCommand::WriteAudio(pcm) => {
                let counter = state.packet_counter.fetch_add(1, Ordering::Relaxed);
                let mut packet = Vec::with_capacity(3 + pcm.len());
                packet.extend_from_slice(&counter.to_le_bytes());
                packet.push(0);
                packet.extend_from_slice(&pcm);
                let _ = peripheral
                    .update_characteristic(uuid_str(AUDIO_CHAR), packet)
                    .await;
            }
        }
    }

    state.advertising.store(false, Ordering::Relaxed);
    state.set_status("BLE stopped");
}

async fn add_all_services(
    peripheral: &mut Peripheral,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Audio
    peripheral
        .add_service(&Service {
            uuid: uuid_str(AUDIO_SERVICE),
            primary: true,
            characteristics: vec![
                notify_char(uuid_str(AUDIO_CHAR)),
                read_char(uuid_str(AUDIO_CODEC_CHAR), Some(vec![0])), // PCM16
            ],
        })
        .await?;

    // Device Information
    peripheral
        .add_service(&Service {
            uuid: uuid_short(DIS_SERVICE),
            primary: true,
            characteristics: vec![
                read_char(uuid_short(MODEL_NUMBER), Some(b"Omi Devkit".to_vec())),
                read_char(uuid_short(FIRMWARE_REV), Some(b"sim-1.0.0".to_vec())),
                read_char(uuid_short(HARDWARE_REV), Some(b"mac-simulator".to_vec())),
                read_char(uuid_short(MANUFACTURER), Some(b"Based Hardware".to_vec())),
                read_char(uuid_short(SERIAL_NUMBER), Some(b"OMI-SIM-0001".to_vec())),
            ],
        })
        .await?;

    // Battery
    peripheral
        .add_service(&Service {
            uuid: uuid_short(BATTERY_SERVICE),
            primary: true,
            characteristics: vec![read_notify_char(uuid_short(BATTERY_LEVEL))],
        })
        .await?;

    // Features
    peripheral
        .add_service(&Service {
            uuid: uuid_str(FEATURES_SERVICE),
            primary: true,
            characteristics: vec![read_char(
                uuid_str(FEATURES_CHAR),
                Some(FEATURES_MASK.to_le_bytes().to_vec()),
            )],
        })
        .await?;

    // Button
    peripheral
        .add_service(&Service {
            uuid: uuid_str(BUTTON_SERVICE),
            primary: true,
            characteristics: vec![notify_char(uuid_str(BUTTON_CHAR))],
        })
        .await?;

    // Settings
    peripheral
        .add_service(&Service {
            uuid: uuid_str(SETTINGS_SERVICE),
            primary: true,
            characteristics: vec![
                read_write_char(uuid_str(LED_CHAR)),
                read_write_char(uuid_str(MIC_GAIN_CHAR)),
                read_notify_char(uuid_str(CHARGING_CHAR)),
            ],
        })
        .await?;

    Ok(())
}

fn handle_event(event: PeripheralEvent, state: &BleState) {
    match event {
        PeripheralEvent::StateUpdate { is_powered } => {
            log::info!("BLE power: {is_powered:?}");
            if is_powered {
                state.set_status(format!("Bluetooth powered; advertising={}", state.advertising.load(Ordering::Relaxed)));
            } else {
                state.set_status("Bluetooth powered off");
            }
        }
        PeripheralEvent::CharacteristicSubscriptionUpdate {
            request,
            subscribed,
        } => {
            log::info!(
                "Subscription {} on {}",
                if subscribed { "on" } else { "off" },
                request.characteristic
            );
        }
        PeripheralEvent::ReadRequest {
            request,
            offset,
            responder,
        } => {
            let uuid = request.characteristic;
            let value = read_value(uuid, state);
            let response = match value {
                Some(bytes) if (offset as usize) <= bytes.len() => ReadRequestResponse {
                    value: bytes[offset as usize..].to_vec(),
                    response: RequestResponse::Success,
                },
                Some(_) => ReadRequestResponse {
                    value: vec![],
                    response: RequestResponse::InvalidOffset,
                },
                None => ReadRequestResponse {
                    value: vec![],
                    response: RequestResponse::InvalidHandle,
                },
            };
            let _ = responder.send(response);
        }
        PeripheralEvent::WriteRequest {
            request,
            offset: _,
            value,
            responder,
        } => {
            let uuid = request.characteristic;
            let ok = if uuid == uuid_str(LED_CHAR) {
                if let Some(&v) = value.first() {
                    if v <= 100 {
                        state.led.store(v, Ordering::Relaxed);
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            } else if uuid == uuid_str(MIC_GAIN_CHAR) {
                if let Some(&v) = value.first() {
                    if v <= 8 {
                        state.mic_gain.store(v, Ordering::Relaxed);
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            } else {
                false
            };
            let _ = responder.send(WriteRequestResponse {
                response: if ok {
                    RequestResponse::Success
                } else {
                    RequestResponse::RequestNotSupported
                },
            });
        }
    }
}

fn read_value(uuid: Uuid, state: &BleState) -> Option<Vec<u8>> {
    if uuid == uuid_str(AUDIO_CODEC_CHAR) {
        Some(vec![0])
    } else if uuid == uuid_short(BATTERY_LEVEL) {
        Some(vec![state.battery.load(Ordering::Relaxed)])
    } else if uuid == uuid_str(FEATURES_CHAR) {
        Some(FEATURES_MASK.to_le_bytes().to_vec())
    } else if uuid == uuid_str(LED_CHAR) {
        Some(vec![state.led.load(Ordering::Relaxed)])
    } else if uuid == uuid_str(MIC_GAIN_CHAR) {
        Some(vec![state.mic_gain.load(Ordering::Relaxed)])
    } else if uuid == uuid_str(CHARGING_CHAR) {
        Some(vec![
            if state.charging.load(Ordering::Relaxed) {
                1
            } else {
                0
            },
        ])
    } else if uuid == uuid_short(MODEL_NUMBER) {
        Some(b"Omi Devkit".to_vec())
    } else if uuid == uuid_short(FIRMWARE_REV) {
        Some(b"sim-1.0.0".to_vec())
    } else if uuid == uuid_short(HARDWARE_REV) {
        Some(b"mac-simulator".to_vec())
    } else if uuid == uuid_short(MANUFACTURER) {
        Some(b"Based Hardware".to_vec())
    } else if uuid == uuid_short(SERIAL_NUMBER) {
        Some(b"OMI-SIM-0001".to_vec())
    } else {
        None
    }
}
