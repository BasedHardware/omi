//! Omi device BLE protocol helpers. See `sdks/device/PROTOCOL.md`.

pub const SERVICE_UUID: &str = "19b10000-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_DATA_UUID: &str = "19b10001-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_CODEC_UUID: &str = "19b10002-e8f2-537e-4f6c-d104768a1214";
pub const BATTERY_SERVICE_UUID: &str = "0000180f-0000-1000-8000-00805f9b34fb";
pub const BATTERY_LEVEL_UUID: &str = "00002a19-0000-1000-8000-00805f9b34fb";

pub const PACKET_HEADER_BYTES: usize = 3;
pub const PCM_SAMPLE_RATE_HZ: u32 = 16_000;
pub const OPUS_FRAME_SAMPLES: usize = 960;
pub const PCM_CHANNELS: u8 = 1;

/// Strip the 3-byte Omi audio packet header.
pub fn strip_packet_header(packet: &[u8]) -> &[u8] {
    if packet.len() <= PACKET_HEADER_BYTES {
        &[]
    } else {
        &packet[PACKET_HEADER_BYTES..]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_header() {
        assert!(strip_packet_header(&[1, 2]).is_empty());
        assert_eq!(strip_packet_header(&[0, 0, 0, 9, 8]), &[9, 8]);
    }
}
