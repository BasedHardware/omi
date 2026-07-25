use btleplug::{
    api::{Central, Manager as _, Peripheral as _, ScanFilter},
    platform::Manager,
};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(i32)]
pub enum ButtonEvent {
    Single = 1,
    Double = 2,
    Long = 3,
    Press = 4,
    Release = 5,
}

impl ButtonEvent {
    pub fn packet(self) -> [u8; 8] {
        let mut packet = [0; 8];
        packet[..4].copy_from_slice(&(self as i32).to_le_bytes());
        packet
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
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

#[derive(Clone, Debug, Eq, PartialEq)]
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
}
