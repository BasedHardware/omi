#![forbid(unsafe_code)]

use std::{error::Error, fmt};

pub const OMI_SERVICE: &str = "19b10000-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_DATA_CHARACTERISTIC: &str = "19b10001-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_CODEC_CHARACTERISTIC: &str = "19b10002-e8f2-537e-4f6c-d104768a1214";
pub const BUTTON_SERVICE: &str = "23ba7924-0000-1000-7450-346eac492e92";
pub const BUTTON_TRIGGER_CHARACTERISTIC: &str = "23ba7925-0000-1000-7450-346eac492e92";
pub const STORAGE_SERVICE: &str = "30295780-4301-eabd-2904-2849adfeae43";
pub const STORAGE_CONTROL_CHARACTERISTIC: &str = "30295781-4301-eabd-2904-2849adfeae43";
pub const STORAGE_STATUS_CHARACTERISTIC: &str = "30295782-4301-eabd-2904-2849adfeae43";
pub const TIME_SYNC_SERVICE: &str = "19b10030-e8f2-537e-4f6c-d104768a1214";
pub const TIME_SYNC_WRITE_CHARACTERISTIC: &str = "19b10031-e8f2-537e-4f6c-d104768a1214";
pub const TIME_SYNC_READ_CHARACTERISTIC: &str = "19b10032-e8f2-537e-4f6c-d104768a1214";
pub const BATTERY_SERVICE: &str = "0000180f-0000-1000-8000-00805f9b34fb";
pub const BATTERY_LEVEL_CHARACTERISTIC: &str = "00002a19-0000-1000-8000-00805f9b34fb";

pub const RING_RECORD_SIZE: usize = 444;
pub const RING_AUDIO_PAYLOAD_SIZE: usize = 440;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Advertisement {
    pub id: String,
    pub name: Option<String>,
    pub rssi: Option<i16>,
    pub service_uuids: Vec<String>,
}

impl Advertisement {
    pub fn is_omi(&self) -> bool {
        self.service_uuids
            .iter()
            .any(|uuid| uuid.eq_ignore_ascii_case(OMI_SERVICE))
    }
}

pub trait BleConnection {
    type Error: Error + Send + Sync + 'static;

    fn read(&mut self, service: &str, characteristic: &str) -> Result<Vec<u8>, Self::Error>;
    fn write(
        &mut self,
        service: &str,
        characteristic: &str,
        value: &[u8],
    ) -> Result<(), Self::Error>;
    fn subscribe(&mut self, service: &str, characteristic: &str) -> Result<(), Self::Error>;
}

pub trait BleAdapter {
    type Connection: BleConnection;
    type Error: Error + Send + Sync + 'static;

    fn discover(&mut self, service: &str) -> Result<Vec<Advertisement>, Self::Error>;
    fn connect(&mut self, id: &str) -> Result<Self::Connection, Self::Error>;
}

pub fn discover_omi<A: BleAdapter>(adapter: &mut A) -> Result<Vec<Advertisement>, A::Error> {
    adapter
        .discover(OMI_SERVICE)
        .map(|devices| devices.into_iter().filter(Advertisement::is_omi).collect())
}

pub fn connect_omi<A: BleAdapter>(
    adapter: &mut A,
    id: &str,
) -> Result<Device<A::Connection>, A::Error> {
    adapter.connect(id).map(Device::new)
}

pub struct Device<C> {
    connection: C,
}

impl<C> Device<C> {
    pub fn new(connection: C) -> Self {
        Self { connection }
    }

    pub fn into_inner(self) -> C {
        self.connection
    }
}

impl<C: BleConnection> Device<C> {
    pub fn sync_time(&mut self, epoch_seconds: u32) -> Result<(), OmiError<C::Error>> {
        self.write(
            TIME_SYNC_SERVICE,
            TIME_SYNC_WRITE_CHARACTERISTIC,
            &epoch_seconds.to_le_bytes(),
        )
    }

    pub fn battery_level(&mut self) -> Result<u8, OmiError<C::Error>> {
        let value = self.read(BATTERY_SERVICE, BATTERY_LEVEL_CHARACTERISTIC)?;
        value.first().copied().ok_or(
            ProtocolError::Truncated {
                message: "battery level",
                expected: 1,
                actual: 0,
            }
            .into(),
        )
    }

    pub fn audio_codec(&mut self) -> Result<AudioCodec, OmiError<C::Error>> {
        let value = self.read(OMI_SERVICE, AUDIO_CODEC_CHARACTERISTIC)?;
        let id = value.first().copied().ok_or(ProtocolError::Truncated {
            message: "audio codec",
            expected: 1,
            actual: 0,
        })?;
        Ok(AudioCodec::from_id(id))
    }

    pub fn subscribe_audio(&mut self) -> Result<(), OmiError<C::Error>> {
        self.subscribe(OMI_SERVICE, AUDIO_DATA_CHARACTERISTIC)
    }

    pub fn subscribe_button(&mut self) -> Result<(), OmiError<C::Error>> {
        self.subscribe(BUTTON_SERVICE, BUTTON_TRIGGER_CHARACTERISTIC)
    }

    pub fn ring_status(&mut self) -> Result<RingStatus, OmiError<C::Error>> {
        RingStatus::decode(&self.read(STORAGE_SERVICE, STORAGE_STATUS_CHARACTERISTIC)?)
            .map_err(Into::into)
    }

    pub fn send_ring_command(&mut self, command: RingCommand) -> Result<(), OmiError<C::Error>> {
        self.write(
            STORAGE_SERVICE,
            STORAGE_CONTROL_CHARACTERISTIC,
            &command.encode(),
        )
    }

    pub fn subscribe_ring_control(&mut self) -> Result<(), OmiError<C::Error>> {
        self.subscribe(STORAGE_SERVICE, STORAGE_CONTROL_CHARACTERISTIC)
    }

    fn read(&mut self, service: &str, characteristic: &str) -> Result<Vec<u8>, OmiError<C::Error>> {
        self.connection
            .read(service, characteristic)
            .map_err(OmiError::Transport)
    }

    fn write(
        &mut self,
        service: &str,
        characteristic: &str,
        value: &[u8],
    ) -> Result<(), OmiError<C::Error>> {
        self.connection
            .write(service, characteristic, value)
            .map_err(OmiError::Transport)
    }

    fn subscribe(&mut self, service: &str, characteristic: &str) -> Result<(), OmiError<C::Error>> {
        self.connection
            .subscribe(service, characteristic)
            .map_err(OmiError::Transport)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AudioCodec {
    Pcm8,
    Opus,
    OpusFs320,
    Unknown(u8),
}

impl AudioCodec {
    pub const fn from_id(id: u8) -> Self {
        match id {
            1 => Self::Pcm8,
            20 => Self::Opus,
            21 => Self::OpusFs320,
            other => Self::Unknown(other),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RingStatus {
    pub used_bytes: u32,
    pub unread_packets: u32,
    pub free_bytes: u32,
    pub rtc_valid: bool,
}

impl RingStatus {
    pub fn decode(value: &[u8]) -> Result<Self, ProtocolError> {
        require(value, 16, "ring status")?;
        Ok(Self {
            used_bytes: little_u32(&value[0..4]),
            unread_packets: little_u32(&value[4..8]),
            free_bytes: little_u32(&value[8..12]),
            rtc_valid: little_u32(&value[12..16]) != 0,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RingInfo {
    pub read_sequence: u64,
    pub write_sequence: u64,
    pub capacity_packets: u32,
    pub dropped_packets: u64,
    pub packet_size: u16,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RingDone {
    pub status: u8,
    pub next_sequence: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RingReadBegin {
    pub start_sequence: u64,
    pub packet_count: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RingNotification {
    Ack { status: u8 },
    Info(RingInfo),
    Data(Vec<u8>),
    Done(RingDone),
    ReadBegin(RingReadBegin),
}

impl RingNotification {
    pub fn decode(value: &[u8]) -> Result<Self, ProtocolError> {
        let opcode = *value.first().ok_or(ProtocolError::Truncated {
            message: "ring notification",
            expected: 1,
            actual: 0,
        })?;
        match opcode {
            0x01 => {
                require(value, 2, "ring ACK")?;
                Ok(Self::Ack { status: value[1] })
            }
            0x02 => {
                require(value, 31, "ring INFO")?;
                Ok(Self::Info(RingInfo {
                    read_sequence: big_u64(&value[1..9]),
                    write_sequence: big_u64(&value[9..17]),
                    capacity_packets: big_u32(&value[17..21]),
                    dropped_packets: big_u64(&value[21..29]),
                    packet_size: big_u16(&value[29..31]),
                }))
            }
            0x03 => Ok(Self::Data(value[1..].to_vec())),
            0x04 => {
                require(value, 10, "ring DONE")?;
                Ok(Self::Done(RingDone {
                    status: value[1],
                    next_sequence: big_u64(&value[2..10]),
                }))
            }
            0x05 => {
                require(value, 13, "ring READ_BEGIN")?;
                Ok(Self::ReadBegin(RingReadBegin {
                    start_sequence: big_u64(&value[1..9]),
                    packet_count: big_u32(&value[9..13]),
                }))
            }
            other => Err(ProtocolError::UnknownRingOpcode(other)),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RingCommand {
    Info,
    Read {
        start_sequence: u64,
        packet_count: Option<u32>,
    },
    Advance {
        next_sequence: u64,
    },
    Clear,
    Stop,
}

impl RingCommand {
    pub fn encode(self) -> Vec<u8> {
        match self {
            Self::Info => vec![0x10],
            Self::Read {
                start_sequence,
                packet_count,
            } => {
                let mut value =
                    Vec::with_capacity(if packet_count.filter(|count| *count > 0).is_some() {
                        13
                    } else {
                        9
                    });
                value.push(0x11);
                value.extend(start_sequence.to_be_bytes());
                if let Some(count) = packet_count.filter(|count| *count > 0) {
                    value.extend(count.to_be_bytes());
                }
                value
            }
            Self::Advance { next_sequence } => {
                let mut value = vec![0x12];
                value.extend(next_sequence.to_be_bytes());
                value
            }
            Self::Clear => vec![0x13],
            Self::Stop => vec![0x03],
        }
    }
}

#[derive(Default)]
pub struct RingRecordReassembler {
    pending: Vec<u8>,
}

impl RingRecordReassembler {
    pub fn push(&mut self, data: &[u8]) -> Vec<[u8; RING_RECORD_SIZE]> {
        self.pending.extend_from_slice(data);
        let complete = self.pending.len() / RING_RECORD_SIZE;
        let mut records = Vec::with_capacity(complete);
        for _ in 0..complete {
            let mut record = [0; RING_RECORD_SIZE];
            record.copy_from_slice(&self.pending[..RING_RECORD_SIZE]);
            self.pending.drain(..RING_RECORD_SIZE);
            records.push(record);
        }
        records
    }

    pub fn pending_len(&self) -> usize {
        self.pending.len()
    }
}

pub fn record_timestamp(record: &[u8; RING_RECORD_SIZE]) -> u32 {
    big_u32(&record[..4])
}

pub fn audio_frames(payload: &[u8]) -> Vec<&[u8]> {
    let mut frames = Vec::new();
    let mut offset = 0;
    while offset + 1 < payload.len() {
        let size = payload[offset] as usize;
        if size == 0 {
            offset += 1;
        } else if offset + 1 + size >= payload.len() {
            break;
        } else {
            frames.push(&payload[offset + 1..offset + 1 + size]);
            offset += size + 1;
        }
    }
    frames
}

#[derive(Debug)]
pub enum OmiError<E> {
    Transport(E),
    Protocol(ProtocolError),
}

impl<E: fmt::Display> fmt::Display for OmiError<E> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(error) => write!(formatter, "BLE transport error: {error}"),
            Self::Protocol(error) => error.fmt(formatter),
        }
    }
}

impl<E: Error + 'static> Error for OmiError<E> {}

impl<E> From<ProtocolError> for OmiError<E> {
    fn from(error: ProtocolError) -> Self {
        Self::Protocol(error)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ProtocolError {
    Truncated {
        message: &'static str,
        expected: usize,
        actual: usize,
    },
    UnknownRingOpcode(u8),
}

impl fmt::Display for ProtocolError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Truncated {
                message,
                expected,
                actual,
            } => write!(
                formatter,
                "{message} is truncated: expected at least {expected} bytes, got {actual}"
            ),
            Self::UnknownRingOpcode(opcode) => {
                write!(formatter, "unknown ring notification opcode: {opcode:#04x}")
            }
        }
    }
}

impl Error for ProtocolError {}

fn require(value: &[u8], expected: usize, message: &'static str) -> Result<(), ProtocolError> {
    if value.len() < expected {
        return Err(ProtocolError::Truncated {
            message,
            expected,
            actual: value.len(),
        });
    }
    Ok(())
}

fn little_u32(value: &[u8]) -> u32 {
    u32::from_le_bytes(value.try_into().expect("fixed-size slice"))
}

fn big_u16(value: &[u8]) -> u16 {
    u16::from_be_bytes(value.try_into().expect("fixed-size slice"))
}

fn big_u32(value: &[u8]) -> u32 {
    u32::from_be_bytes(value.try_into().expect("fixed-size slice"))
}

fn big_u64(value: &[u8]) -> u64 {
    u64::from_be_bytes(value.try_into().expect("fixed-size slice"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug)]
    struct TestError;

    impl fmt::Display for TestError {
        fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            formatter.write_str("test transport error")
        }
    }

    impl Error for TestError {}

    struct TestConnection {
        read_value: Vec<u8>,
        writes: Vec<(String, String, Vec<u8>)>,
    }

    impl BleConnection for TestConnection {
        type Error = TestError;

        fn read(&mut self, _: &str, _: &str) -> Result<Vec<u8>, Self::Error> {
            Ok(self.read_value.clone())
        }

        fn write(
            &mut self,
            service: &str,
            characteristic: &str,
            value: &[u8],
        ) -> Result<(), Self::Error> {
            self.writes
                .push((service.into(), characteristic.into(), value.into()));
            Ok(())
        }

        fn subscribe(&mut self, _: &str, _: &str) -> Result<(), Self::Error> {
            Ok(())
        }
    }

    #[test]
    fn recognizes_advertisements_with_the_firmware_audio_service() {
        let omi = Advertisement {
            id: "omi".into(),
            name: Some("Omi".into()),
            rssi: Some(-42),
            service_uuids: vec![OMI_SERVICE.to_ascii_uppercase()],
        };
        assert!(omi.is_omi());
    }

    #[test]
    fn preserves_time_sync_endianness_and_codec_ids() {
        assert_eq!(1234_u32.to_le_bytes(), [0xd2, 0x04, 0x00, 0x00]);
        assert_eq!(AudioCodec::from_id(20), AudioCodec::Opus);
        assert_eq!(AudioCodec::from_id(99), AudioCodec::Unknown(99));
    }

    #[test]
    fn device_commands_use_the_firmware_gatt_contract() {
        let connection = TestConnection {
            read_value: vec![20],
            writes: Vec::new(),
        };
        let mut device = Device::new(connection);
        device.sync_time(1234).unwrap();
        assert_eq!(device.audio_codec().unwrap(), AudioCodec::Opus);
        device.send_ring_command(RingCommand::Info).unwrap();
        let connection = device.into_inner();
        assert_eq!(
            connection.writes,
            vec![
                (
                    TIME_SYNC_SERVICE.into(),
                    TIME_SYNC_WRITE_CHARACTERISTIC.into(),
                    vec![0xd2, 0x04, 0x00, 0x00],
                ),
                (
                    STORAGE_SERVICE.into(),
                    STORAGE_CONTROL_CHARACTERISTIC.into(),
                    vec![0x10],
                ),
            ]
        );
    }

    #[test]
    fn decodes_ring_status_and_notifications() {
        let status = RingStatus::decode(&[1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0]).unwrap();
        assert_eq!(
            status,
            RingStatus {
                used_bytes: 1,
                unread_packets: 2,
                free_bytes: 3,
                rtc_valid: true
            }
        );
        let notification = RingNotification::decode(&[0x04, 0, 0, 0, 0, 0, 0, 0, 0, 9]).unwrap();
        assert_eq!(
            notification,
            RingNotification::Done(RingDone {
                status: 0,
                next_sequence: 9
            })
        );
    }

    #[test]
    fn encodes_ring_commands_and_reassembles_unaligned_records() {
        assert_eq!(
            RingCommand::Read {
                start_sequence: 4,
                packet_count: Some(2)
            }
            .encode(),
            vec![0x11, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 2]
        );
        let mut reassembler = RingRecordReassembler::default();
        assert!(reassembler.push(&[1; 400]).is_empty());
        assert_eq!(reassembler.push(&[2; 44]).len(), 1);
        assert_eq!(reassembler.pending_len(), 0);
    }

    #[test]
    fn stops_audio_payload_at_the_firmware_boundary() {
        let mut payload = vec![0; RING_AUDIO_PAYLOAD_SIZE];
        payload[0] = 2;
        payload[1..3].copy_from_slice(&[7, 8]);
        payload[RING_AUDIO_PAYLOAD_SIZE - 2] = 2;
        assert_eq!(audio_frames(&payload), vec![&[7, 8][..]]);
    }

    #[test]
    fn rejects_a_frame_ending_at_the_payload_boundary() {
        let mut payload = vec![0; RING_AUDIO_PAYLOAD_SIZE];
        payload[RING_AUDIO_PAYLOAD_SIZE - 3] = 2;
        payload[RING_AUDIO_PAYLOAD_SIZE - 2..].copy_from_slice(&[7, 8]);
        assert!(audio_frames(&payload).is_empty());
    }
}
