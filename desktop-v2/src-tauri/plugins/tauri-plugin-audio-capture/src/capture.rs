use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleFormat, Stream, StreamConfig};
use tokio::sync::mpsc;
use tracing;

use crate::models::{AudioDevice, AudioLevel, CaptureConfig};

/// Enumerate all input audio devices on the system.
pub fn list_audio_devices() -> Vec<AudioDevice> {
    let host = cpal::default_host();

    let default_input_name = host
        .default_input_device()
        .and_then(|d| d.name().ok());

    let mut devices = Vec::new();

    if let Ok(input_devices) = host.input_devices() {
        for device in input_devices {
            let name = match device.name() {
                Ok(n) => n,
                Err(e) => {
                    tracing::warn!("Failed to get device name: {}", e);
                    continue;
                }
            };

            let is_default = default_input_name
                .as_ref()
                .map(|d| d == &name)
                .unwrap_or(false);

            devices.push(AudioDevice {
                id: name.clone(),
                name,
                is_default,
                is_input: true,
            });
        }
    }

    devices
}

/// Resolve the cpal `Device` for the given config.
/// If `device_id` is `None`, the default input device is used.
fn resolve_device(device_id: &Option<String>) -> Result<Device, String> {
    let host = cpal::default_host();

    match device_id {
        Some(id) => {
            let input_devices = host
                .input_devices()
                .map_err(|e| format!("Failed to enumerate input devices: {}", e))?;

            for device in input_devices {
                if let Ok(name) = device.name() {
                    if name == *id {
                        return Ok(device);
                    }
                }
            }
            Err(format!("Device not found: {}", id))
        }
        None => host
            .default_input_device()
            .ok_or_else(|| "No default input device available".to_string()),
    }
}

/// Compute RMS and peak from a buffer of i16 samples.
pub fn get_audio_level(samples: &[i16]) -> AudioLevel {
    if samples.is_empty() {
        return AudioLevel { rms: 0.0, peak: 0.0 };
    }

    let max_val = i16::MAX as f64;
    let mut sum_sq: f64 = 0.0;
    let mut peak: f64 = 0.0;

    for &s in samples {
        let normalised = (s as f64) / max_val;
        sum_sq += normalised * normalised;
        let abs = normalised.abs();
        if abs > peak {
            peak = abs;
        }
    }

    let rms = (sum_sq / samples.len() as f64).sqrt();

    AudioLevel {
        rms: rms as f32,
        peak: peak as f32,
    }
}

/// Linearly resample a mono buffer from `from_rate` to `to_rate`.
fn resample_linear(input: &[i16], from_rate: u32, to_rate: u32) -> Vec<i16> {
    if from_rate == to_rate || input.is_empty() {
        return input.to_vec();
    }

    let ratio = from_rate as f64 / to_rate as f64;
    let output_len = ((input.len() as f64) / ratio).ceil() as usize;
    let mut output = Vec::with_capacity(output_len);

    for i in 0..output_len {
        let src_idx = i as f64 * ratio;
        let idx_floor = src_idx.floor() as usize;
        let frac = src_idx - idx_floor as f64;

        let sample = if idx_floor + 1 < input.len() {
            let a = input[idx_floor] as f64;
            let b = input[idx_floor + 1] as f64;
            (a + frac * (b - a)) as i16
        } else if idx_floor < input.len() {
            input[idx_floor]
        } else {
            0
        };

        output.push(sample);
    }

    output
}

/// Mix multi-channel interleaved samples down to mono by averaging channels.
fn mix_to_mono(samples: &[i16], channels: u16) -> Vec<i16> {
    if channels <= 1 {
        return samples.to_vec();
    }

    let ch = channels as usize;
    let frame_count = samples.len() / ch;
    let mut mono = Vec::with_capacity(frame_count);

    for frame in 0..frame_count {
        let offset = frame * ch;
        let mut sum: i32 = 0;
        for c in 0..ch {
            sum += samples[offset + c] as i32;
        }
        mono.push((sum / ch as i32) as i16);
    }

    mono
}

/// Wrapper around `cpal::Stream` to allow sending across threads.
///
/// `cpal::Stream` is `!Send` because some platform backends use thread-local
/// state. On Linux (ALSA) this is not actually the case, and even on other
/// platforms we only ever hold the stream behind a `Mutex` and never move it
/// across threads — we just need the *type* to satisfy Tauri's `Send + Sync`
/// bounds on managed state.
struct SendStream(#[allow(dead_code)] Stream);

// SAFETY: The Stream is stored behind a Mutex and only accessed from one
// thread at a time. We never actually move it — we only drop it in place.
unsafe impl Send for SendStream {}
unsafe impl Sync for SendStream {}

/// Handle that keeps the cpal stream alive.  Dropping it stops the stream.
pub struct CaptureHandle {
    /// The cpal stream — must be kept alive.
    _stream: SendStream,
    pub device_name: String,
    pub sample_rate: u32,
}

/// Start capturing audio from the device described by `config`.
///
/// Audio is converted to 16 kHz mono i16 PCM and sent as `Vec<i16>` chunks
/// through the provided `mpsc::Sender`.
pub fn start_capture(
    config: CaptureConfig,
    tx: mpsc::UnboundedSender<Vec<i16>>,
) -> Result<CaptureHandle, String> {
    let device = resolve_device(&config.device_id)?;
    let device_name = device.name().unwrap_or_else(|_| "unknown".into());

    // Pick a supported input config, preferring i16 format.
    let supported = device
        .supported_input_configs()
        .map_err(|e| format!("Failed to query supported configs: {}", e))?;

    let mut chosen: Option<cpal::SupportedStreamConfig> = None;

    for cfg in supported {
        // Prefer I16 to avoid conversion, but accept F32 too.
        if cfg.sample_format() == SampleFormat::I16 || cfg.sample_format() == SampleFormat::F32 {
            // Try to pick a config whose range includes our target rate.
            let target = cpal::SampleRate(config.sample_rate);
            if cfg.min_sample_rate() <= target && target <= cfg.max_sample_rate() {
                chosen = Some(cfg.with_sample_rate(target));
                break;
            }
            // Otherwise just take the max rate and resample later.
            if chosen.is_none() {
                chosen = Some(cfg.with_max_sample_rate());
            }
        }
    }

    let supported_config =
        chosen.ok_or_else(|| "No suitable input configuration found".to_string())?;

    let device_sample_rate = supported_config.sample_rate().0;
    let device_channels = supported_config.channels();
    let sample_format = supported_config.sample_format();
    let target_rate = config.sample_rate;

    let stream_config: StreamConfig = supported_config.into();

    tracing::info!(
        "Starting capture: device={}, format={:?}, rate={}, channels={}, target_rate={}",
        device_name,
        sample_format,
        device_sample_rate,
        device_channels,
        target_rate
    );

    let err_callback = |err: cpal::StreamError| {
        tracing::warn!("Audio stream error (device may have disconnected): {}", err);
    };

    let stream = match sample_format {
        SampleFormat::I16 => {
            let tx = tx.clone();
            device.build_input_stream(
                &stream_config,
                move |data: &[i16], _: &cpal::InputCallbackInfo| {
                    let mono = mix_to_mono(data, device_channels);
                    let resampled = resample_linear(&mono, device_sample_rate, target_rate);
                    // If the receiver has been dropped, just discard.
                    let _ = tx.send(resampled);
                },
                err_callback,
                None,
            )
        }
        SampleFormat::F32 => {
            let tx = tx.clone();
            device.build_input_stream(
                &stream_config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    // Convert f32 [-1.0, 1.0] to i16.
                    let i16_samples: Vec<i16> = data
                        .iter()
                        .map(|&s| {
                            let clamped = s.clamp(-1.0, 1.0);
                            (clamped * i16::MAX as f32) as i16
                        })
                        .collect();
                    let mono = mix_to_mono(&i16_samples, device_channels);
                    let resampled = resample_linear(&mono, device_sample_rate, target_rate);
                    let _ = tx.send(resampled);
                },
                err_callback,
                None,
            )
        }
        other => {
            return Err(format!("Unsupported sample format: {:?}", other));
        }
    }
    .map_err(|e| format!("Failed to build input stream: {}", e))?;

    stream
        .play()
        .map_err(|e| format!("Failed to start stream: {}", e))?;

    Ok(CaptureHandle {
        _stream: SendStream(stream),
        device_name,
        sample_rate: target_rate,
    })
}
