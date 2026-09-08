//! Best-effort mic capture → 8 kHz mono PCM16 frames for the audio notify characteristic.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use tokio::sync::mpsc;

use crate::ble::BleCommand;

pub struct AudioCapture {
    recording: Arc<AtomicBool>,
    _stream: Option<cpal::Stream>,
}

impl AudioCapture {
    pub fn new(cmd_tx: mpsc::UnboundedSender<BleCommand>) -> Self {
        let recording = Arc::new(AtomicBool::new(false));
        let stream = match build_stream(recording.clone(), cmd_tx) {
            Ok(s) => {
                if let Err(e) = s.play() {
                    log::warn!("audio stream play failed: {e}");
                }
                Some(s)
            }
            Err(e) => {
                log::warn!("mic capture unavailable: {e}");
                None
            }
        };
        Self {
            recording,
            _stream: stream,
        }
    }

    pub fn set_recording(&self, on: bool) {
        self.recording.store(on, Ordering::Relaxed);
    }

    pub fn is_recording(&self) -> bool {
        self.recording.load(Ordering::Relaxed)
    }

    pub fn available(&self) -> bool {
        self._stream.is_some()
    }
}

fn build_stream(
    recording: Arc<AtomicBool>,
    cmd_tx: mpsc::UnboundedSender<BleCommand>,
) -> Result<cpal::Stream, Box<dyn std::error::Error>> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or("no default input device")?;
    let config = device.default_input_config()?;
    let sample_rate = config.sample_rate().0 as f32;
    let channels = config.channels() as usize;
    let target_rate = 8000.0_f32;
    let mut phase = 0.0_f32;
    let step = target_rate / sample_rate;
    let mut out_buf: Vec<i16> = Vec::with_capacity(160);

    let err_fn = |e| log::error!("audio stream error: {e}");

    let stream = match config.sample_format() {
        cpal::SampleFormat::F32 => device.build_input_stream(
            &config.into(),
            move |data: &[f32], _| {
                if !recording.load(Ordering::Relaxed) {
                    return;
                }
                let mut i = 0usize;
                while i + channels <= data.len() {
                    let sample = data[i]; // ch0
                    phase += step;
                    if phase >= 1.0 {
                        phase -= 1.0;
                        let pcm = (sample.clamp(-1.0, 1.0) * 32767.0) as i16;
                        out_buf.push(pcm);
                        if out_buf.len() >= 160 {
                            let bytes: Vec<u8> = out_buf
                                .drain(..160)
                                .flat_map(|s| s.to_le_bytes())
                                .collect();
                            let _ = cmd_tx.send(BleCommand::WriteAudio(bytes));
                        }
                    }
                    i += channels;
                }
            },
            err_fn,
            None,
        )?,
        cpal::SampleFormat::I16 => device.build_input_stream(
            &config.into(),
            move |data: &[i16], _| {
                if !recording.load(Ordering::Relaxed) {
                    return;
                }
                let mut i = 0usize;
                while i + channels <= data.len() {
                    let sample = data[i];
                    phase += step;
                    if phase >= 1.0 {
                        phase -= 1.0;
                        out_buf.push(sample);
                        if out_buf.len() >= 160 {
                            let bytes: Vec<u8> = out_buf
                                .drain(..160)
                                .flat_map(|s| s.to_le_bytes())
                                .collect();
                            let _ = cmd_tx.send(BleCommand::WriteAudio(bytes));
                        }
                    }
                    i += channels;
                }
            },
            err_fn,
            None,
        )?,
        other => return Err(format!("unsupported sample format: {other:?}").into()),
    };

    Ok(stream)
}
