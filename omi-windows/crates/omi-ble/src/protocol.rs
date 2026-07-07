use std::fmt;

// ── Omi Main Service ─────────────────────────────────────────────────────────

pub const OMI_SERVICE_UUID: &str = "19B10000-E8F2-537E-4F6C-D104768A1214";
pub const AUDIO_DATA_STREAM_UUID: &str = "19B10001-E8F2-537E-4F6C-D104768A1214";
pub const AUDIO_CODEC_UUID: &str = "19B10002-E8F2-537E-4F6C-D104768A1214";
pub const IMAGE_DATA_STREAM_UUID: &str = "19B10005-E8F2-537E-4F6C-D104768A1214";
pub const IMAGE_CAPTURE_CONTROL_UUID: &str = "19B10006-E8F2-537E-4F6C-D104768A1214";

// ── Settings Service ─────────────────────────────────────────────────────────

pub const SETTINGS_SERVICE_UUID: &str = "19B10010-E8F2-537E-4F6C-D104768A1214";
pub const DIM_RATIO_UUID: &str = "19B10011-E8F2-537E-4F6C-D104768A1214";
pub const MIC_GAIN_UUID: &str = "19B10012-E8F2-537E-4F6C-D104768A1214";

// ── Features Service ─────────────────────────────────────────────────────────

pub const FEATURES_SERVICE_UUID: &str = "19B10020-E8F2-537E-4F6C-D104768A1214";
pub const FEATURES_CHAR_UUID: &str = "19B10021-E8F2-537E-4F6C-D104768A1214";

// ── Button Service ───────────────────────────────────────────────────────────

pub const BUTTON_SERVICE_UUID: &str = "23BA7924-0000-1000-7450-346EAC492E92";
pub const BUTTON_TRIGGER_UUID: &str = "23BA7925-0000-1000-7450-346EAC492E92";

// ── Storage Service ──────────────────────────────────────────────────────────

pub const STORAGE_SERVICE_UUID: &str = "30295780-4301-EABD-2904-2849ADFEAE43";
pub const STORAGE_DATA_UUID: &str = "30295781-4301-EABD-2904-2849ADFEAE43";
pub const STORAGE_CONTROL_UUID: &str = "30295782-4301-EABD-2904-2849ADFEAE43";
pub const STORAGE_WIFI_UUID: &str = "30295783-4301-EABD-2904-2849ADFEAE43";

// ── Accelerometer Service ────────────────────────────────────────────────────

pub const ACCEL_SERVICE_UUID: &str = "32403790-0000-1000-7450-BF445E5829A2";
pub const ACCEL_DATA_UUID: &str = "32403791-0000-1000-7450-BF445E5829A2";

// ── Battery Service (standard BLE) ───────────────────────────────────────────

pub const BATTERY_SERVICE_UUID: &str = "0000180F-0000-1000-8000-00805F9B34FB";
pub const BATTERY_LEVEL_UUID: &str = "00002A19-0000-1000-8000-00805F9B34FB";

// ── Speaker / Haptic Service ─────────────────────────────────────────────────

pub const SPEAKER_SERVICE_UUID: &str = "CAB1AB95-2EA5-4F4D-BB56-874B72CFC984";
pub const SPEAKER_DATA_UUID: &str = "CAB1AB96-2EA5-4F4D-BB56-874B72CFC984";

// ── Device Information Service (standard BLE) ────────────────────────────────

pub const DEVICE_INFO_SERVICE_UUID: &str = "0000180A-0000-1000-8000-00805F9B34FB";
pub const MODEL_NUMBER_UUID: &str = "00002A24-0000-1000-8000-00805F9B34FB";
pub const FIRMWARE_REVISION_UUID: &str = "00002A26-0000-1000-8000-00805F9B34FB";
pub const HARDWARE_REVISION_UUID: &str = "00002A27-0000-1000-8000-00805F9B34FB";
pub const MANUFACTURER_NAME_UUID: &str = "00002A29-0000-1000-8000-00805F9B34FB";

// ── Image Capture Commands ───────────────────────────────────────────────────

pub const IMAGE_CAPTURE_START: u8 = 0x05;
pub const IMAGE_CAPTURE_STOP: u8 = 0x00;
pub const IMAGE_CAPTURE_SINGLE: u8 = 0xFF;

// ── Feature Bitmask ──────────────────────────────────────────────────────────

pub const FEATURE_SPEAKER: u16 = 1 << 0;
pub const FEATURE_ACCELEROMETER: u16 = 1 << 1;
pub const FEATURE_BUTTON: u16 = 1 << 2;
pub const FEATURE_BATTERY: u16 = 1 << 3;
pub const FEATURE_OFFLINE_STORAGE: u16 = 1 << 6;
pub const FEATURE_WIFI: u16 = 1 << 9;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DeviceFeatures(pub u16);

impl DeviceFeatures {
    pub fn has_speaker(self) -> bool { self.0 & FEATURE_SPEAKER != 0 }
    pub fn has_accelerometer(self) -> bool { self.0 & FEATURE_ACCELEROMETER != 0 }
    pub fn has_button(self) -> bool { self.0 & FEATURE_BUTTON != 0 }
    pub fn has_battery(self) -> bool { self.0 & FEATURE_BATTERY != 0 }
    pub fn has_offline_storage(self) -> bool { self.0 & FEATURE_OFFLINE_STORAGE != 0 }
    pub fn has_wifi(self) -> bool { self.0 & FEATURE_WIFI != 0 }
}

// ── Audio Codec ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BleAudioCodec {
    Pcm16,
    Pcm8,
    MuLaw16,
    MuLaw8,
    Opus,
    OpusFS320,
    Aac,
    Lc3,
}

impl BleAudioCodec {
    pub fn from_id(id: u8) -> Option<Self> {
        match id {
            0 => Some(Self::Pcm16),
            1 => Some(Self::Pcm8),
            10 => Some(Self::MuLaw16),
            11 => Some(Self::MuLaw8),
            20 => Some(Self::Opus),
            21 => Some(Self::OpusFS320),
            22 => Some(Self::Aac),
            23 => Some(Self::Lc3),
            _ => None,
        }
    }

    pub fn id(self) -> u8 {
        match self {
            Self::Pcm16 => 0,
            Self::Pcm8 => 1,
            Self::MuLaw16 => 10,
            Self::MuLaw8 => 11,
            Self::Opus => 20,
            Self::OpusFS320 => 21,
            Self::Aac => 22,
            Self::Lc3 => 23,
        }
    }

    pub fn frame_size_bytes(self) -> usize {
        match self {
            Self::Opus => 80,
            Self::OpusFS320 => 160,
            Self::Lc3 => 30,
            Self::Pcm16 => 320,
            Self::Pcm8 => 160,
            Self::MuLaw16 => 320,
            Self::MuLaw8 => 160,
            Self::Aac => 0,
        }
    }

    pub fn sample_rate(self) -> u32 {
        16000
    }

    pub fn uses_packet_header(self) -> bool {
        matches!(self, Self::Pcm16 | Self::Pcm8 | Self::MuLaw16 | Self::MuLaw8 | Self::Opus)
    }
}

impl fmt::Display for BleAudioCodec {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Pcm16 => write!(f, "PCM 16-bit"),
            Self::Pcm8 => write!(f, "PCM 8-bit"),
            Self::MuLaw16 => write!(f, "μ-law 16-bit"),
            Self::MuLaw8 => write!(f, "μ-law 8-bit"),
            Self::Opus => write!(f, "Opus (10ms)"),
            Self::OpusFS320 => write!(f, "Opus (20ms)"),
            Self::Aac => write!(f, "AAC"),
            Self::Lc3 => write!(f, "LC3"),
        }
    }
}

// ── Device Type Detection ────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DeviceType {
    Omi,
    OpenGlass,
    FriendPendant,
    Frame,
    Plaud,
    Bee,
    Fieldy,
    Limitless,
    Unknown,
}

impl DeviceType {
    pub fn from_name(name: &str) -> Self {
        let lower = name.to_lowercase();
        if lower.starts_with("friend") || lower.starts_with("omi") || lower.starts_with("openglass") {
            if lower.contains("openglass") {
                Self::OpenGlass
            } else {
                Self::Omi
            }
        } else if lower.contains("frame") {
            Self::Frame
        } else if lower.contains("plaud") {
            Self::Plaud
        } else if lower.contains("bee") {
            Self::Bee
        } else if lower.contains("fieldy") {
            Self::Fieldy
        } else if lower.contains("limitless") || lower.contains("pendant") {
            Self::FriendPendant
        } else {
            Self::Unknown
        }
    }

    pub fn default_codec(&self) -> BleAudioCodec {
        match self {
            Self::Omi | Self::OpenGlass => BleAudioCodec::Opus,
            Self::Plaud | Self::Limitless | Self::Fieldy => BleAudioCodec::OpusFS320,
            Self::Bee => BleAudioCodec::Aac,
            Self::FriendPendant => BleAudioCodec::Lc3,
            Self::Frame => BleAudioCodec::Pcm16,
            Self::Unknown => BleAudioCodec::Opus,
        }
    }
}

impl fmt::Display for DeviceType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Omi => write!(f, "Omi"),
            Self::OpenGlass => write!(f, "OpenGlass"),
            Self::FriendPendant => write!(f, "Friend Pendant"),
            Self::Frame => write!(f, "Frame"),
            Self::Plaud => write!(f, "PLAUD"),
            Self::Bee => write!(f, "Bee"),
            Self::Fieldy => write!(f, "Fieldy"),
            Self::Limitless => write!(f, "Limitless"),
            Self::Unknown => write!(f, "Unknown"),
        }
    }
}

// ── Audio Packet Reassembly ──────────────────────────────────────────────────

pub struct AudioFrameAssembler {
    codec: BleAudioCodec,
    buffer: Vec<u8>,
    last_packet_index: Option<u16>,
    lost_packets: u64,
}

impl AudioFrameAssembler {
    pub fn new(codec: BleAudioCodec) -> Self {
        Self {
            codec,
            buffer: Vec::with_capacity(512),
            last_packet_index: None,
            lost_packets: 0,
        }
    }

    pub fn lost_packets(&self) -> u64 {
        self.lost_packets
    }

    pub fn process_notification(&mut self, data: &[u8]) -> Vec<Vec<u8>> {
        if self.codec.uses_packet_header() {
            self.process_with_header(data)
        } else {
            self.process_fixed_frames(data)
        }
    }

    fn process_with_header(&mut self, data: &[u8]) -> Vec<Vec<u8>> {
        if data.len() < 3 {
            return Vec::new();
        }

        let packet_index = u16::from_le_bytes([data[0], data[1]]);
        let frame_id = data[2];
        let content = &data[3..];

        if let Some(last) = self.last_packet_index {
            let expected = last.wrapping_add(1);
            if packet_index != expected {
                self.lost_packets += 1;
                tracing::trace!("[BLE] Packet gap: expected {expected}, got {packet_index}");
            }
        }
        self.last_packet_index = Some(packet_index);

        let mut frames = Vec::new();
        let frame_size = self.codec.frame_size_bytes();

        if frame_id == 0 {
            if !self.buffer.is_empty() && frame_size > 0 && self.buffer.len() >= frame_size {
                frames.push(self.buffer.clone());
            }
            self.buffer.clear();
        }

        self.buffer.extend_from_slice(content);

        if frame_size > 0 {
            while self.buffer.len() >= frame_size {
                let frame: Vec<u8> = self.buffer.drain(..frame_size).collect();
                frames.push(frame);
            }
        }

        frames
    }

    fn process_fixed_frames(&mut self, data: &[u8]) -> Vec<Vec<u8>> {
        let frame_size = self.codec.frame_size_bytes();
        if frame_size == 0 {
            return vec![data.to_vec()];
        }

        self.buffer.extend_from_slice(data);
        let mut frames = Vec::new();
        while self.buffer.len() >= frame_size {
            let frame: Vec<u8> = self.buffer.drain(..frame_size).collect();
            frames.push(frame);
        }
        frames
    }
}
