use omi_device::{
    AudioCodec, BleConnection, Device, OmiError, ProtocolError, AUDIO_CODEC_CHARACTERISTIC,
    OMI_SERVICE,
};

struct CodecRead(Vec<u8>);

impl BleConnection for CodecRead {
    type Error = std::io::Error;

    fn read(&mut self, service: &str, characteristic: &str) -> Result<Vec<u8>, Self::Error> {
        assert_eq!(service, OMI_SERVICE);
        assert_eq!(characteristic, AUDIO_CODEC_CHARACTERISTIC);
        Ok(self.0.clone())
    }

    fn write(&mut self, _: &str, _: &str, _: &[u8]) -> Result<(), Self::Error> {
        panic!("reading a codec must not write to the device")
    }

    fn subscribe(&mut self, _: &str, _: &str) -> Result<(), Self::Error> {
        panic!("reading a codec must not subscribe to notifications")
    }
}

fn read_codec(bytes: &[u8]) -> Result<AudioCodec, OmiError<std::io::Error>> {
    Device::new(CodecRead(bytes.to_vec())).audio_codec()
}

#[test]
fn protocol_defined_pcm16_is_recognized() {
    // The shared device protocol assigns codec ID 0 to PCM 16-bit audio.
    assert_eq!(read_codec(&[0]).unwrap(), AudioCodec::Pcm16);
}

#[test]
fn other_documented_codec_ids_keep_their_meaning() {
    for (id, expected) in [
        (1, AudioCodec::Pcm8),
        (20, AudioCodec::Opus),
        (21, AudioCodec::OpusFs320),
    ] {
        assert_eq!(read_codec(&[id]).unwrap(), expected);
    }
}

#[test]
fn unknown_codec_ids_are_preserved() {
    assert_eq!(read_codec(&[99]).unwrap(), AudioCodec::Unknown(99));
}

#[test]
fn empty_codec_read_keeps_the_protocol_error() {
    assert!(matches!(
        read_codec(&[]),
        Err(OmiError::Protocol(ProtocolError::Truncated {
            message: "audio codec",
            expected: 1,
            actual: 0,
        }))
    ));
}
