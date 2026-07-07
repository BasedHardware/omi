pub mod scanner;
pub mod protocol;
pub mod connection;

pub use protocol::{BleAudioCodec, DeviceFeatures, DeviceType, AudioFrameAssembler};
pub use scanner::{DiscoveredDevice, scan_for_devices, scan_all_ble, find_device_by_id};
pub use connection::{BleConnection, ConnectionState, DeviceInfo, connect_with_retry, reconnect_loop};
