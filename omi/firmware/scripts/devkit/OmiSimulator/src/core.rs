use btleplug::{
    api::{Central, CentralEvent, CharPropFlags, Manager as _, Peripheral as _, ScanFilter},
    platform::{Manager, Peripheral},
};
use futures::StreamExt;
pub use omi_firmware_core::ButtonEvent;
use omi_firmware_core::{
    PeripheralState, AUDIO_DATA_UUID, BATTERY_LEVEL_UUID, BATTERY_SERVICE_UUID,
    BUTTON_SERVICE_UUID, BUTTON_TRIGGER_UUID, DEVICE_INFO_SERVICE_UUID, FIRMWARE_REVISION_UUID,
    HARDWARE_REVISION_UUID, MANUFACTURER_NAME_UUID, MODEL_NUMBER_UUID, OMI_SERVICE_UUID,
};
use serde::Serialize;
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, Command, Output, Stdio},
    time::Duration,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Product {
    Omi,
    OmiDevKit,
    OmiGlass,
    AppleWatch,
    Plaud,
    Bee,
    Fieldy,
    FriendPendant,
    Limitless,
    RayBanMeta,
}

impl Product {
    pub const ALL: [Self; 10] = [
        Self::Omi,
        Self::OmiDevKit,
        Self::OmiGlass,
        Self::AppleWatch,
        Self::Plaud,
        Self::Bee,
        Self::Fieldy,
        Self::FriendPendant,
        Self::Limitless,
        Self::RayBanMeta,
    ];

    pub fn name(self) -> &'static str {
        match self {
            Self::Omi => "Omi",
            Self::OmiDevKit => "Omi DevKit",
            Self::OmiGlass => "Omi Glass",
            Self::AppleWatch => "Apple Watch",
            Self::Plaud => "Plaud Note",
            Self::Bee => "Bee",
            Self::Fieldy => "Fieldy",
            Self::FriendPendant => "Friend Pendant",
            Self::Limitless => "Limitless",
            Self::RayBanMeta => "Ray-Ban Meta",
        }
    }

    pub fn capabilities(self) -> Capabilities {
        match self {
            Self::Omi | Self::OmiDevKit => Capabilities {
                button: true,
                audio: true,
                battery: true,
                device_info: true,
                settings: true,
                storage: true,
                flash: self == Self::OmiDevKit,
            },
            Self::OmiGlass => Capabilities {
                button: false,
                audio: true,
                battery: true,
                device_info: true,
                settings: false,
                storage: false,
                flash: false,
            },
            _ => Capabilities::default(),
        }
    }

    pub fn detect(name: &str, services: &[String]) -> Option<Self> {
        let name = name.to_ascii_lowercase();
        let has_service = |uuid: &str| {
            services
                .iter()
                .any(|service| service.eq_ignore_ascii_case(uuid))
        };
        if name.contains("devkit") || name == "friend" || name == "super" {
            Some(Self::OmiDevKit)
        } else if name.contains("omi glass") {
            Some(Self::OmiGlass)
        } else if name.contains("plaud") {
            Some(Self::Plaud)
        } else if name.contains("bee") {
            Some(Self::Bee)
        } else if name == "compass"
            || name == "fieldy"
            || has_service("4fafc201-1fb5-459e-8fcc-c5c9c331914b")
        {
            Some(Self::Fieldy)
        } else if name.starts_with("friend_") || has_service("1a3fd0e7-b1f3-ac9e-2e49-b647b2c4f8da")
        {
            Some(Self::FriendPendant)
        } else if name.contains("limitless")
            || name.contains("pendant")
            || has_service("632de001-604c-446b-a80f-7963e950f3fb")
        {
            Some(Self::Limitless)
        } else if has_service("19b10000-e8f2-537e-4f6c-d104768a1214") {
            Some(Self::Omi)
        } else if name.contains("ray-ban") || name.contains("rayban") {
            Some(Self::RayBanMeta)
        } else {
            None
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize)]
pub struct Capabilities {
    pub button: bool,
    pub audio: bool,
    pub battery: bool,
    pub device_info: bool,
    pub settings: bool,
    pub storage: bool,
    pub flash: bool,
}

impl Capabilities {
    pub fn summary(self) -> String {
        [
            ("BUTTON", self.button),
            ("AUDIO", self.audio),
            ("BATTERY", self.battery),
            ("INFO", self.device_info),
            ("SETTINGS", self.settings),
            ("STORAGE", self.storage),
            ("FLASH", self.flash),
        ]
        .into_iter()
        .map(|(name, enabled)| format!("{name} {}", if enabled { "READY" } else { "N/A" }))
        .collect::<Vec<_>>()
        .join("  ·  ")
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct BluetoothTarget {
    pub name: String,
    pub address: String,
    pub product: Option<Product>,
    pub rssi: Option<i16>,
    pub connected: bool,
    pub available: bool,
}

pub trait BluetoothScanner {
    fn scan(&self) -> Result<Vec<BluetoothTarget>, String>;
}

pub struct SystemBluetoothScanner;

impl BluetoothScanner for SystemBluetoothScanner {
    fn scan(&self) -> Result<Vec<BluetoothTarget>, String> {
        let runtime = tokio::runtime::Runtime::new().map_err(|error| error.to_string())?;
        runtime.block_on(async {
            let manager = Manager::new().await.map_err(|error| error.to_string())?;
            let adapter = manager
                .adapters()
                .await
                .map_err(|error| error.to_string())?
                .into_iter()
                .next()
                .ok_or("no Bluetooth adapter available")?;
            let mut events = adapter.events().await.map_err(|error| error.to_string())?;
            adapter
                .start_scan(ScanFilter::default())
                .await
                .map_err(|error| error.to_string())?;
            let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(2);
            let mut seen = Vec::new();
            while let Ok(Some(event)) = tokio::time::timeout_at(deadline, events.next()).await {
                let id = match event {
                    CentralEvent::DeviceDiscovered(id) | CentralEvent::DeviceUpdated(id) => id,
                    _ => continue,
                };
                if !seen.contains(&id) {
                    seen.push(id);
                }
            }
            let mut targets = Vec::new();
            for id in seen {
                let peripheral = adapter
                    .peripheral(&id)
                    .await
                    .map_err(|error| error.to_string())?;
                let Some(properties) = peripheral
                    .properties()
                    .await
                    .map_err(|error| error.to_string())?
                else {
                    continue;
                };
                let services = properties
                    .services
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>();
                let name = properties
                    .local_name
                    .unwrap_or_else(|| "Unnamed peripheral".into());
                let product = Product::detect(&name, &services);
                if product.is_none() {
                    continue;
                }
                targets.push(BluetoothTarget {
                    product,
                    name,
                    address: peripheral.id().to_string(),
                    rssi: properties.rssi,
                    connected: peripheral
                        .is_connected()
                        .await
                        .map_err(|error| error.to_string())?,
                    available: true,
                });
            }
            adapter
                .stop_scan()
                .await
                .map_err(|error| error.to_string())?;
            targets.sort_by(|left, right| left.name.cmp(&right.name));
            Ok::<_, String>(targets)
        })
    }
}

pub fn discover_bluetooth_targets() -> Result<Vec<BluetoothTarget>, String> {
    discover_bluetooth_targets_with(&SystemBluetoothScanner)
}

pub fn discover_bluetooth_targets_with(
    scanner: &impl BluetoothScanner,
) -> Result<Vec<BluetoothTarget>, String> {
    scanner.scan()
}

pub fn set_bluetooth_connection(id: &str, connect: bool) -> Result<(), String> {
    let runtime = tokio::runtime::Runtime::new().map_err(|error| error.to_string())?;
    runtime.block_on(async {
        let manager = Manager::new().await.map_err(|error| error.to_string())?;
        let adapter = manager
            .adapters()
            .await
            .map_err(|error| error.to_string())?
            .into_iter()
            .next()
            .ok_or("no Bluetooth adapter available")?;
        let peripheral = adapter
            .peripherals()
            .await
            .map_err(|error| error.to_string())?
            .into_iter()
            .find(|peripheral| peripheral.id().to_string() == id)
            .ok_or("selected peripheral is no longer available")?;
        if connect {
            peripheral.connect().await
        } else {
            peripheral.disconnect().await
        }
        .map_err(|error| error.to_string())
    })
}

pub fn read_button_event(id: &str) -> Result<ButtonEvent, String> {
    let runtime = tokio::runtime::Runtime::new().map_err(|error| error.to_string())?;
    runtime.block_on(async {
        let manager = Manager::new().await.map_err(|error| error.to_string())?;
        let adapter = manager
            .adapters()
            .await
            .map_err(|error| error.to_string())?
            .into_iter()
            .next()
            .ok_or("no Bluetooth adapter available")?;
        let peripheral = adapter
            .peripherals()
            .await
            .map_err(|error| error.to_string())?
            .into_iter()
            .find(|peripheral| peripheral.id().to_string() == id)
            .ok_or("selected peripheral is no longer available")?;
        if !peripheral
            .is_connected()
            .await
            .map_err(|error| error.to_string())?
        {
            peripheral
                .connect()
                .await
                .map_err(|error| error.to_string())?;
        }
        peripheral
            .discover_services()
            .await
            .map_err(|error| error.to_string())?;
        let characteristic = peripheral
            .characteristics()
            .into_iter()
            .find(|characteristic| {
                characteristic.uuid.to_string() == "23ba7925-0000-1000-7450-346eac492e92"
            })
            .ok_or("selected product does not expose the Omi button characteristic")?;
        let value = peripheral
            .read(&characteristic)
            .await
            .map_err(|error| error.to_string())?;
        ButtonEvent::decode(&value).map_err(str::to_owned)
    })
}

const BUTTON_UUID: &str = "23ba7925-0000-1000-7450-346eac492e92";
const BATTERY_UUID: &str = "00002a19-0000-1000-8000-00805f9b34fb";
const MODEL_UUID: &str = "00002a24-0000-1000-8000-00805f9b34fb";
const SERIAL_UUID: &str = "00002a25-0000-1000-8000-00805f9b34fb";
const FIRMWARE_UUID: &str = "00002a26-0000-1000-8000-00805f9b34fb";
const HARDWARE_UUID: &str = "00002a27-0000-1000-8000-00805f9b34fb";
const MANUFACTURER_UUID: &str = "00002a29-0000-1000-8000-00805f9b34fb";
const AUDIO_CODEC_UUID: &str = "19b10002-e8f2-537e-4f6c-d104768a1214";
const DIM_RATIO_UUID: &str = "19b10011-e8f2-537e-4f6c-d104768a1214";
const MIC_GAIN_UUID: &str = "19b10012-e8f2-537e-4f6c-d104768a1214";
const CHARGING_UUID: &str = "19b10013-e8f2-537e-4f6c-d104768a1214";
const STORAGE_CONTROL_UUID: &str = "30295782-4301-eabd-2904-2849adfeae43";
const SMP_SERVICE_UUID: &str = "8d53dc1d-1db7-4cd3-868b-8a527460aa84";

async fn selected_peripheral(id: &str) -> Result<Peripheral, String> {
    let manager = Manager::new().await.map_err(|error| error.to_string())?;
    let adapter = manager
        .adapters()
        .await
        .map_err(|error| error.to_string())?
        .into_iter()
        .next()
        .ok_or("no Bluetooth adapter available")?;
    let peripheral = adapter
        .peripherals()
        .await
        .map_err(|error| error.to_string())?
        .into_iter()
        .find(|peripheral| peripheral.id().to_string() == id)
        .ok_or("selected peripheral is no longer available")?;
    if !peripheral
        .is_connected()
        .await
        .map_err(|error| error.to_string())?
    {
        peripheral
            .connect()
            .await
            .map_err(|error| error.to_string())?;
    }
    peripheral
        .discover_services()
        .await
        .map_err(|error| error.to_string())?;
    Ok(peripheral)
}

#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub struct DeviceDiagnostics {
    pub services: Vec<String>,
    pub battery_percent: Option<u8>,
    pub model: Option<String>,
    pub serial_number: Option<String>,
    pub firmware_revision: Option<String>,
    pub hardware_revision: Option<String>,
    pub manufacturer: Option<String>,
    pub audio_codec: Option<Vec<u8>>,
    pub dim_ratio: Option<Vec<u8>>,
    pub microphone_gain: Option<Vec<u8>>,
    pub charging_status: Option<Vec<u8>>,
    pub storage_status: Option<Vec<u8>>,
    pub button_notifications: bool,
    pub smp: bool,
}

pub fn probe_device(id: &str) -> Result<DeviceDiagnostics, String> {
    let runtime = tokio::runtime::Runtime::new().map_err(|error| error.to_string())?;
    runtime.block_on(async {
        let peripheral = selected_peripheral(id).await?;
        let characteristics = peripheral.characteristics();
        let mut diagnostics = DeviceDiagnostics {
            services: peripheral
                .services()
                .iter()
                .map(|service| service.uuid.to_string())
                .collect(),
            ..DeviceDiagnostics::default()
        };
        diagnostics.services.sort();
        diagnostics.smp = diagnostics
            .services
            .iter()
            .any(|uuid| uuid == SMP_SERVICE_UUID);
        diagnostics.button_notifications = characteristics.iter().any(|characteristic| {
            characteristic.uuid.to_string() == BUTTON_UUID
                && characteristic.properties.contains(CharPropFlags::NOTIFY)
        });
        for (uuid, destination) in [
            (AUDIO_CODEC_UUID, &mut diagnostics.audio_codec),
            (DIM_RATIO_UUID, &mut diagnostics.dim_ratio),
            (MIC_GAIN_UUID, &mut diagnostics.microphone_gain),
            (CHARGING_UUID, &mut diagnostics.charging_status),
            (STORAGE_CONTROL_UUID, &mut diagnostics.storage_status),
        ] {
            if let Some(characteristic) = characteristics
                .iter()
                .find(|characteristic| characteristic.uuid.to_string() == uuid)
            {
                *destination = peripheral.read(characteristic).await.ok();
            }
        }
        for (uuid, destination) in [
            (MODEL_UUID, &mut diagnostics.model),
            (SERIAL_UUID, &mut diagnostics.serial_number),
            (FIRMWARE_UUID, &mut diagnostics.firmware_revision),
            (HARDWARE_UUID, &mut diagnostics.hardware_revision),
            (MANUFACTURER_UUID, &mut diagnostics.manufacturer),
        ] {
            if let Some(characteristic) = characteristics
                .iter()
                .find(|characteristic| characteristic.uuid.to_string() == uuid)
            {
                *destination = peripheral
                    .read(characteristic)
                    .await
                    .ok()
                    .and_then(|value| String::from_utf8(value).ok());
            }
        }
        if let Some(characteristic) = characteristics
            .iter()
            .find(|characteristic| characteristic.uuid.to_string() == BATTERY_UUID)
        {
            diagnostics.battery_percent = peripheral
                .read(characteristic)
                .await
                .ok()
                .and_then(|value| value.first().copied());
        }
        Ok(diagnostics)
    })
}

pub fn monitor_button_events(id: &str, seconds: u64) -> Result<Vec<ButtonEvent>, String> {
    let runtime = tokio::runtime::Runtime::new().map_err(|error| error.to_string())?;
    runtime.block_on(async {
        let peripheral = selected_peripheral(id).await?;
        let characteristic = peripheral
            .characteristics()
            .into_iter()
            .find(|characteristic| characteristic.uuid.to_string() == BUTTON_UUID)
            .ok_or("selected product does not expose the Omi button characteristic")?;
        if !characteristic.properties.contains(CharPropFlags::NOTIFY) {
            return Err("Omi button characteristic does not support notifications".into());
        }
        peripheral
            .subscribe(&characteristic)
            .await
            .map_err(|error| error.to_string())?;
        let mut notifications = peripheral
            .notifications()
            .await
            .map_err(|error| error.to_string())?;
        let deadline = tokio::time::Instant::now() + Duration::from_secs(seconds);
        let mut events = Vec::new();
        while let Ok(Some(notification)) =
            tokio::time::timeout_at(deadline, notifications.next()).await
        {
            if notification.uuid == characteristic.uuid {
                events.push(ButtonEvent::decode(&notification.value).map_err(str::to_owned)?);
            }
        }
        peripheral
            .unsubscribe(&characteristic)
            .await
            .map_err(|error| error.to_string())?;
        Ok(events)
    })
}

#[derive(Default)]
pub struct PeripheralCatalog {
    targets: Vec<(BluetoothTarget, u64)>,
}

impl PeripheralCatalog {
    pub fn update(&mut self, scan: Vec<BluetoothTarget>, now: u64) {
        for target in scan {
            if let Some((known, seen)) = self
                .targets
                .iter_mut()
                .find(|(known, _)| known.address == target.address)
            {
                *known = target;
                *seen = now;
            } else {
                self.targets.push((target, now));
            }
        }
        for (target, seen) in &mut self.targets {
            target.available = *seen == now;
        }
        self.targets
            .retain(|(_, seen)| now.saturating_sub(*seen) <= 2);
    }

    pub fn available(&self) -> impl Iterator<Item = &BluetoothTarget> {
        self.targets
            .iter()
            .filter(|(target, _)| target.available)
            .map(|(target, _)| target)
    }

    pub fn find(&self, address: &str) -> Option<&BluetoothTarget> {
        self.targets
            .iter()
            .map(|(target, _)| target)
            .find(|target| target.address == address)
    }

    pub fn targets_mut(&mut self) -> impl Iterator<Item = &mut BluetoothTarget> {
        self.targets.iter_mut().map(|(target, _)| target)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FirmwareImage {
    pub path: PathBuf,
    pub version: String,
    pub bytes: u64,
    pub product: Product,
    pub hardware: String,
    pub artifacts: Vec<String>,
}

impl FirmwareImage {
    pub fn validate(path: impl AsRef<Path>) -> Result<Self, String> {
        let path = path.as_ref();
        let bytes = fs::metadata(path).map_err(|error| error.to_string())?.len();
        if bytes < 4 {
            return Err("firmware image is empty".into());
        }
        let file = fs::File::open(path).map_err(|error| error.to_string())?;
        let mut archive =
            zip::ZipArchive::new(file).map_err(|error| format!("invalid firmware ZIP: {error}"))?;
        let mut artifacts = Vec::new();
        let mut manifest = None;
        for index in 0..archive.len() {
            let mut entry = archive.by_index(index).map_err(|error| error.to_string())?;
            let name = entry.name().to_owned();
            if name.to_ascii_lowercase().contains("manifest") && name.ends_with(".json") {
                let mut contents = String::new();
                entry
                    .read_to_string(&mut contents)
                    .map_err(|error| error.to_string())?;
                manifest = Some(
                    serde_json::from_str::<serde_json::Value>(&contents)
                        .map_err(|error| format!("invalid firmware manifest: {error}"))?,
                );
            }
            artifacts.push(name);
        }
        if artifacts.is_empty() {
            return Err("firmware ZIP contains no artifacts".into());
        }
        let name = path
            .file_stem()
            .and_then(|name| name.to_str())
            .ok_or("firmware image has no valid file name")?;
        let version = name
            .split(['v', '_'])
            .find(|part| {
                part.chars()
                    .next()
                    .is_some_and(|char| char.is_ascii_digit())
            })
            .unwrap_or("unknown")
            .to_owned();
        let lower_name = name.to_ascii_lowercase();
        let (product, hardware) = if lower_name.contains("cv1") {
            (Product::Omi, "nRF5340")
        } else if lower_name.contains("devkit") || lower_name.contains("xiao") {
            (Product::OmiDevKit, "nRF52840")
        } else {
            return Err("firmware file name must identify Omi CV1 or Omi DevKit".into());
        };
        let manifest = manifest.ok_or("firmware ZIP has no JSON manifest")?;
        let mut referenced = Vec::new();
        collect_firmware_references(&manifest, &mut referenced);
        if referenced.is_empty() {
            return Err("firmware manifest references no programmable images".into());
        }
        for reference in referenced {
            if !artifacts.iter().any(|artifact| {
                artifact == &reference
                    || Path::new(artifact).file_name() == Path::new(&reference).file_name()
            }) {
                return Err(format!(
                    "firmware manifest references missing artifact {reference}"
                ));
            }
        }
        Ok(Self {
            path: path.to_owned(),
            version,
            bytes,
            product,
            hardware: hardware.into(),
            artifacts,
        })
    }
}

fn collect_firmware_references(value: &serde_json::Value, references: &mut Vec<String>) {
    match value {
        serde_json::Value::Array(values) => {
            for value in values {
                collect_firmware_references(value, references);
            }
        }
        serde_json::Value::Object(values) => {
            for value in values.values() {
                collect_firmware_references(value, references);
            }
        }
        serde_json::Value::String(value)
            if [".bin", ".hex", ".dat"]
                .iter()
                .any(|extension| value.to_ascii_lowercase().ends_with(extension)) =>
        {
            references.push(value.clone());
        }
        _ => {}
    }
}

pub fn nrfutil_devices(controller: Option<&str>) -> Result<serde_json::Value, String> {
    let mut command = Command::new("nrfutil");
    command.args(["--json", "device", "list"]);
    if let Some(controller) = controller {
        command.args(["--serial-number", controller]);
    }
    command_json(command, "nrfutil device list")
}

pub fn nrfutil_program(
    firmware: impl AsRef<Path>,
    controller: &str,
) -> Result<serde_json::Value, String> {
    if controller.is_empty() {
        return Err("a Nordic controller serial number is required".into());
    }
    let firmware = firmware.as_ref();
    if !firmware.is_file() {
        return Err("Nordic firmware path is not a file".into());
    }
    let mut program = Command::new("nrfutil");
    program
        .args(["--json", "device", "program", "--firmware"])
        .arg(firmware)
        .args([
            "--options",
            "verify=VERIFY_READ",
            "--serial-number",
            controller,
        ]);
    let result = command_json(program, "nrfutil device program")?;
    let mut reset = Command::new("nrfutil");
    reset.args(["--json", "device", "reset", "--serial-number", controller]);
    command_json(reset, "nrfutil device reset")?;
    Ok(result)
}

pub fn mcumgr_image(image: impl AsRef<Path>, connection: &str, reset: bool) -> Result<(), String> {
    if connection.is_empty() {
        return Err("an mcumgr connection string is required".into());
    }
    let image = image.as_ref();
    if image.extension().and_then(|value| value.to_str()) != Some("bin") {
        return Err("mcumgr requires a signed MCUboot .bin image, not a DFU ZIP".into());
    }
    let status = Command::new("mcumgr")
        .args([
            "--conntype",
            "ble",
            "--connstring",
            connection,
            "image",
            "upload",
            "-e",
        ])
        .arg(image)
        .status()
        .map_err(|error| format!("could not start mcumgr: {error}"))?;
    if !status.success() {
        return Err("mcumgr image upload failed".into());
    }
    if reset {
        let status = Command::new("mcumgr")
            .args(["--conntype", "ble", "--connstring", connection, "reset"])
            .status()
            .map_err(|error| format!("could not reset with mcumgr: {error}"))?;
        if !status.success() {
            return Err("mcumgr reset failed".into());
        }
    }
    Ok(())
}

fn command_json(mut command: Command, operation: &str) -> Result<serde_json::Value, String> {
    let Output {
        status,
        stdout,
        stderr,
    } = command
        .output()
        .map_err(|error| format!("could not start {operation}: {error}"))?;
    if !status.success() {
        return Err(format!(
            "{operation} failed: {}",
            String::from_utf8_lossy(&stderr).trim()
        ));
    }
    let text = String::from_utf8(stdout).map_err(|error| error.to_string())?;
    serde_json::from_str(&text).or_else(|_| {
        let values = text
            .lines()
            .filter(|line| !line.trim().is_empty())
            .map(serde_json::from_str)
            .collect::<Result<Vec<serde_json::Value>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(serde_json::Value::Array(values))
    })
}

pub struct FlashSession {
    child: Child,
}

impl FlashSession {
    pub fn start_devkit(image: &FirmwareImage, serial_port: &str) -> Result<Self, String> {
        if image.product != Product::OmiDevKit {
            return Err("selected firmware is not an Omi DevKit package".into());
        }
        if serial_port.is_empty() {
            return Err("a serial port is required for DevKit flashing".into());
        }
        let child = Command::new("adafruit-nrfutil")
            .args(["dfu", "serial", "--package"])
            .arg(&image.path)
            .args(["--port", serial_port, "-b", "115200"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("could not start adafruit-nrfutil: {error}"))?;
        Ok(Self { child })
    }

    pub fn poll(&mut self) -> Result<Option<bool>, String> {
        self.child
            .try_wait()
            .map(|status| status.map(|status| status.success()))
            .map_err(|error| error.to_string())
    }

    pub fn cancel(&mut self) -> Result<(), String> {
        self.child.kill().map_err(|error| error.to_string())
    }
}

impl Drop for FlashSession {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

#[derive(Serialize)]
struct PeripheralCharacteristic {
    uuid: &'static str,
    properties: &'static [&'static str],
    value: Vec<u8>,
}

#[derive(Serialize)]
struct PeripheralService {
    uuid: &'static str,
    primary: bool,
    characteristics: Vec<PeripheralCharacteristic>,
}

#[derive(Serialize)]
struct PeripheralConfig {
    name: &'static str,
    #[serde(rename = "advertisedServices")]
    advertised_services: [&'static str; 2],
    services: Vec<PeripheralService>,
}

pub struct PeripheralSimulator {
    child: Child,
    input: Option<ChildStdin>,
    state: PeripheralState,
}

impl PeripheralSimulator {
    pub fn start() -> Result<Self, String> {
        if !cfg!(target_os = "macos") {
            return Err("BLE peripheral simulation requires macOS CoreBluetooth".into());
        }
        let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
        let source = manifest.join("native/macos/OmiPeripheral.swift");
        let plist = manifest.join("native/macos/Info.plist");
        let binary = manifest.join("target/omi-peripheral");
        fs::create_dir_all(binary.parent().ok_or("invalid peripheral binary path")?)
            .map_err(|error| error.to_string())?;
        let status = Command::new("swiftc")
            .arg(&source)
            .args(["-o"])
            .arg(&binary)
            .args(["-framework", "CoreBluetooth", "-framework", "Foundation"])
            .args(["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT"])
            .args(["-Xlinker", "__info_plist", "-Xlinker"])
            .arg(&plist)
            .status()
            .map_err(|error| format!("could not run swiftc: {error}"))?;
        if !status.success() {
            return Err("swiftc could not build the CoreBluetooth peripheral".into());
        }
        let mut child = Command::new(binary)
            .stdin(Stdio::piped())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| format!("could not start CoreBluetooth peripheral: {error}"))?;
        let mut input = child
            .stdin
            .take()
            .ok_or("peripheral stdin is unavailable")?;
        writeln!(
            input,
            "{}",
            serde_json::to_string(&peripheral_config()).map_err(|error| error.to_string())?
        )
        .map_err(|error| error.to_string())?;
        Ok(Self {
            child,
            input: Some(input),
            state: PeripheralState::default(),
        })
    }

    pub fn button(&mut self, event: ButtonEvent) -> Result<(), String> {
        let packet = self.state.apply_button(event);
        self.update(BUTTON_TRIGGER_UUID, &packet)
    }

    pub fn battery(&mut self, level: u8) -> Result<(), String> {
        let packet = self.state.set_battery(level).map_err(str::to_owned)?;
        self.update(BATTERY_LEVEL_UUID, &packet)
    }

    pub fn audio(&mut self, packet: &[u8]) -> Result<(), String> {
        if packet.is_empty() {
            return Err("audio packet cannot be empty".into());
        }
        self.update(AUDIO_DATA_UUID, packet)
    }

    pub fn status(&self) -> (bool, bool, u8) {
        (
            self.state.button.powered,
            self.state.button.pressed,
            self.state.battery,
        )
    }

    pub fn wait(mut self) -> Result<bool, String> {
        self.input.take();
        self.child
            .wait()
            .map(|status| status.success())
            .map_err(|error| error.to_string())
    }

    fn update(&mut self, uuid: &str, value: &[u8]) -> Result<(), String> {
        writeln!(
            self.input.as_mut().ok_or("peripheral input is closed")?,
            "{}",
            serde_json::json!({"uuid": uuid, "value": value})
        )
        .map_err(|error| error.to_string())
    }
}

impl Drop for PeripheralSimulator {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

fn peripheral_config() -> PeripheralConfig {
    PeripheralConfig {
        name: "Omi Emulator",
        advertised_services: [OMI_SERVICE_UUID, BUTTON_SERVICE_UUID],
        services: vec![
            PeripheralService {
                uuid: OMI_SERVICE_UUID,
                primary: true,
                characteristics: vec![
                    characteristic(AUDIO_DATA_UUID, &["notify"], Vec::new()),
                    characteristic(AUDIO_CODEC_UUID, &["read"], vec![20]),
                ],
            },
            PeripheralService {
                uuid: BUTTON_SERVICE_UUID,
                primary: true,
                characteristics: vec![characteristic(
                    BUTTON_TRIGGER_UUID,
                    &["read", "notify"],
                    ButtonEvent::Release.packet().to_vec(),
                )],
            },
            PeripheralService {
                uuid: BATTERY_SERVICE_UUID,
                primary: true,
                characteristics: vec![characteristic(
                    BATTERY_LEVEL_UUID,
                    &["read", "notify"],
                    vec![100],
                )],
            },
            PeripheralService {
                uuid: DEVICE_INFO_SERVICE_UUID,
                primary: true,
                characteristics: vec![
                    characteristic(MODEL_NUMBER_UUID, &["read"], b"Omi Emulator".to_vec()),
                    characteristic(
                        FIRMWARE_REVISION_UUID,
                        &["read"],
                        b"3.0.0-emulator".to_vec(),
                    ),
                    characteristic(HARDWARE_REVISION_UUID, &["read"], b"rust-macos".to_vec()),
                    characteristic(
                        MANUFACTURER_NAME_UUID,
                        &["read"],
                        b"Based Hardware".to_vec(),
                    ),
                ],
            },
        ],
    }
}

fn characteristic(
    uuid: &'static str,
    properties: &'static [&'static str],
    value: Vec<u8>,
) -> PeripheralCharacteristic {
    PeripheralCharacteristic {
        uuid,
        properties,
        value,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn product_contracts_and_button_wire_values_match_the_app_and_firmware() {
        assert_eq!(Product::ALL.len(), 10);
        assert!(Product::Omi.capabilities().button);
        assert!(Product::OmiDevKit.capabilities().flash);
        assert_eq!(ButtonEvent::Press.packet(), [4, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Release.packet(), [5, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Single.packet(), [1, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Double.packet(), [2, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Long.packet(), [3, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(
            ButtonEvent::decode(&ButtonEvent::Double.packet()).unwrap(),
            ButtonEvent::Double
        );
        assert!(ButtonEvent::decode(&[6, 0, 0, 0]).is_err());
        assert_eq!(
            Product::detect("Unknown", &["19b10000-e8f2-537e-4f6c-d104768a1214".into()]),
            Some(Product::Omi)
        );
        assert_eq!(Product::detect("Omi", &[]), None);
        assert_eq!(
            Product::detect("Unknown", &["1a3fd0e7-b1f3-ac9e-2e49-b647b2c4f8da".into()]),
            Some(Product::FriendPendant)
        );
    }

    #[test]
    fn scanner_seam_returns_only_its_current_advertisements() {
        struct Scanner;
        impl BluetoothScanner for Scanner {
            fn scan(&self) -> Result<Vec<BluetoothTarget>, String> {
                Ok(vec![BluetoothTarget {
                    name: "Omi".into(),
                    address: "current".into(),
                    product: Some(Product::Omi),
                    rssi: Some(-40),
                    connected: false,
                    available: true,
                }])
            }
        }

        let targets = discover_bluetooth_targets_with(&Scanner).unwrap();
        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].address, "current");
    }

    #[test]
    fn dropdown_catalog_contains_only_scanned_targets_and_expires_stale_entries() {
        let mut catalog = PeripheralCatalog::default();
        assert_eq!(catalog.available().count(), 0);
        catalog.update(
            vec![BluetoothTarget {
                name: "Omi".into(),
                address: "AA".into(),
                product: Some(Product::Omi),
                rssi: Some(-42),
                connected: false,
                available: true,
            }],
            1,
        );
        assert_eq!(catalog.available().count(), 1);
        catalog.update(Vec::new(), 2);
        assert_eq!(catalog.available().count(), 0);
        catalog.update(Vec::new(), 4);
        assert!(catalog.targets.is_empty());
    }

    #[test]
    fn firmware_validation_rejects_non_zip_data_and_reads_a_version() {
        let directory = tempfile::tempdir().unwrap();
        let invalid = directory.path().join("firmware.bin");
        fs::write(&invalid, b"nope").unwrap();
        assert!(FirmwareImage::validate(invalid).is_err());

        let valid = directory.path().join("Omi_CV1_OTA_v3.0.20.zip");
        let file = fs::File::create(&valid).unwrap();
        let mut zip = zip::ZipWriter::new(file);
        zip.start_file("app_update.bin", zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(b"firmware").unwrap();
        zip.start_file("manifest.json", zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(br#"{"files":[{"file":"app_update.bin"}]}"#)
            .unwrap();
        zip.finish().unwrap();
        let image = FirmwareImage::validate(valid).unwrap();
        assert_eq!(image.version, "3.0.20");
        assert_eq!(image.product, Product::Omi);
        assert_eq!(image.hardware, "nRF5340");
        assert!(FlashSession::start_devkit(&image, "/dev/null").is_err());
    }

    #[test]
    fn firmware_validation_rejects_unknown_products_and_empty_archives() {
        let directory = tempfile::tempdir().unwrap();
        let unknown = directory.path().join("firmware.zip");
        let file = fs::File::create(&unknown).unwrap();
        zip::ZipWriter::new(file).finish().unwrap();
        assert!(FirmwareImage::validate(unknown).is_err());
    }

    #[test]
    fn peripheral_profile_matches_production_discovery_and_gatt_contracts() {
        let config = serde_json::to_value(peripheral_config()).unwrap();
        assert_eq!(config["advertisedServices"][0], OMI_SERVICE_UUID);
        assert_eq!(config["advertisedServices"][1], BUTTON_SERVICE_UUID);
        assert!(config["services"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|service| service["characteristics"].as_array().unwrap())
            .any(|characteristic| characteristic["uuid"] == BATTERY_LEVEL_UUID));
        assert!(config["services"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|service| service["characteristics"].as_array().unwrap())
            .any(|characteristic| characteristic["uuid"] == BUTTON_TRIGGER_UUID));
    }
}
