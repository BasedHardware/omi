use btleplug::{
    api::{Central, Manager as _, Peripheral as _, ScanFilter},
    platform::Manager,
};
pub use omi_firmware_core::ButtonEvent;
use omi_firmware_core::{
    PeripheralState, AUDIO_CODEC_UUID, AUDIO_DATA_UUID, BATTERY_LEVEL_UUID, BATTERY_SERVICE_UUID,
    BUTTON_SERVICE_UUID, BUTTON_TRIGGER_UUID, DEVICE_INFO_SERVICE_UUID, FIRMWARE_REVISION_UUID,
    HARDWARE_REVISION_UUID, MANUFACTURER_NAME_UUID, MODEL_NUMBER_UUID, OMI_SERVICE_UUID,
};
use serde::Serialize;
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Child, ChildStdin, Command, Stdio},
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

    pub fn detect(name: &str) -> Option<Self> {
        let name = name.to_ascii_lowercase();
        if name.contains("devkit") || name == "friend" || name == "super" {
            Some(Self::OmiDevKit)
        } else if name.contains("omi glass") {
            Some(Self::OmiGlass)
        } else if name.contains("omi") {
            Some(Self::Omi)
        } else if name.contains("plaud") {
            Some(Self::Plaud)
        } else if name.contains("bee") {
            Some(Self::Bee)
        } else if name.contains("fieldy") {
            Some(Self::Fieldy)
        } else if name.contains("friend") {
            Some(Self::FriendPendant)
        } else if name.contains("limitless") {
            Some(Self::Limitless)
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

pub fn discover_bluetooth_targets() -> Result<Vec<BluetoothTarget>, String> {
    let runtime = tokio::runtime::Runtime::new().map_err(|error| error.to_string())?;
    let targets = runtime.block_on(async {
        let manager = Manager::new().await.map_err(|error| error.to_string())?;
        let adapter = manager
            .adapters()
            .await
            .map_err(|error| error.to_string())?
            .into_iter()
            .next()
            .ok_or("no Bluetooth adapter available")?;
        adapter
            .start_scan(ScanFilter::default())
            .await
            .map_err(|error| error.to_string())?;
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        let mut targets = Vec::new();
        for peripheral in adapter
            .peripherals()
            .await
            .map_err(|error| error.to_string())?
        {
            let Some(properties) = peripheral
                .properties()
                .await
                .map_err(|error| error.to_string())?
            else {
                continue;
            };
            let name = properties
                .local_name
                .unwrap_or_else(|| "Unnamed peripheral".into());
            targets.push(BluetoothTarget {
                product: Product::detect(&name),
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
    })?;
    let mut catalog = PeripheralCatalog::default();
    catalog.update(targets, 0);
    Ok(catalog.available().cloned().collect())
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
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FirmwareImage {
    pub path: PathBuf,
    pub version: String,
    pub bytes: u64,
}

impl FirmwareImage {
    pub fn validate(path: impl AsRef<Path>) -> Result<Self, String> {
        let path = path.as_ref();
        let bytes = fs::metadata(path).map_err(|error| error.to_string())?.len();
        if bytes < 4 {
            return Err("firmware image is empty".into());
        }
        let prefix = fs::read(path).map_err(|error| error.to_string())?;
        if prefix[..4] != [0x50, 0x4b, 0x03, 0x04] {
            return Err("firmware image must be a ZIP package".into());
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
        Ok(Self {
            path: path.to_owned(),
            version,
            bytes,
        })
    }
}

pub struct FlashSession {
    child: Child,
}

impl FlashSession {
    pub fn start_devkit(image: &FirmwareImage, serial_port: &str) -> Result<Self, String> {
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
        let mut file = fs::File::create(&valid).unwrap();
        file.write_all(&[0x50, 0x4b, 0x03, 0x04, 1]).unwrap();
        let image = FirmwareImage::validate(valid).unwrap();
        assert_eq!(image.version, "3.0.20");
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
