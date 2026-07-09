// Microphone input capture via cpal

use anyhow::{Context, Result};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::SampleFormat;
use std::sync::Arc;
use tokio::sync::broadcast;

use crate::{AudioChunk, SAMPLE_RATE};

/// Lists available input (microphone) devices.
pub fn list_input_devices() -> Result<Vec<String>> {
    let host = cpal::default_host();
    let devices: Vec<String> = host
        .input_devices()
        .context("Failed to enumerate input devices")?
        .filter_map(|d| d.name().ok())
        .collect();
    Ok(devices)
}

/// Start capturing audio from the default or preferred microphone.
///
/// Uses the device's preferred config and resamples to 16kHz mono internally.
/// Returns a handle that keeps the stream alive. Drop it to stop capture.
pub fn start_mic_capture(
    tx: broadcast::Sender<AudioChunk>,
    preferred_device: Option<&str>,
) -> Result<MicStream> {
    start_mic_capture_with_gain(tx, preferred_device, 1.0)
}

pub fn start_mic_capture_with_gain(
    tx: broadcast::Sender<AudioChunk>,
    preferred_device: Option<&str>,
    gain: f32,
) -> Result<MicStream> {
    let host = cpal::default_host();
    let device = if let Some(name) = preferred_device {
        if name.is_empty() {
            host.default_input_device()
                .context("No default input device available")?
        } else {
            let mut found = None;
            if let Ok(devices) = host.input_devices() {
                for d in devices {
                    if let Ok(n) = d.name() {
                        if n == name {
                            found = Some(d);
                            break;
                        }
                    }
                }
            }
            if let Some(d) = found {
                d
            } else {
                tracing::warn!("[MIC] Preferred input device '{}' not found, falling back to default", name);
                host.default_input_device().context("No default input device available")?
            }
        }
    } else {
        host.default_input_device()
            .context("No default input device available")?
    };

    let device_name = device.name().unwrap_or_else(|_| "unknown".into());
    tracing::info!("Using input device: {device_name}");

    // Use the device's default config — don't force a specific sample rate
    let default_config = device
        .default_input_config()
        .context("Failed to get default input config")?;

    let sample_format = default_config.sample_format();
    let config: cpal::StreamConfig = default_config.into();
    let device_rate = config.sample_rate.0;
    let device_channels = config.channels as usize;

    tracing::info!(
        "Mic native config: {}Hz, {} channels, {:?}",
        device_rate, device_channels, sample_format
    );

    let err_fn = |err: cpal::StreamError| {
        tracing::error!("[MIC] Stream error: {err}");
    };

    let stream = match sample_format {
        SampleFormat::F32 => {
            let tx = tx.clone();
            device.build_input_stream(
                &config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    let mut max_input = 0.0f32;
                    for &s in data {
                        let abs = s.abs();
                        if abs > max_input {
                            max_input = abs;
                        }
                    }
                    if max_input > 0.00001 {
                        tracing::debug!("[MIC] Raw callback max float: {}", max_input);
                    }

                    let mono = downmix_to_mono_f32(data, device_channels);

                    // Auto-gain: compute RMS and boost to target level
                    let rms = if mono.is_empty() {
                        0.0
                    } else {
                        let sum_sq: f32 = mono.iter().map(|s| s * s).sum();
                        (sum_sq / mono.len() as f32).sqrt()
                    };

                    // Target RMS ~0.05 (comfortable speech level for Deepgram)
                    let auto_gain = if rms > 0.000001 {
                        let target_rms = 0.05;
                        let computed = target_rms / rms;
                        // Clamp auto-gain between 1x and 5000x, then apply user gain as a ceiling
                        computed.clamp(1.0, gain.max(1.0) * 100.0)
                    } else {
                        gain.max(1.0)
                    };

                    let boosted: Vec<f32> = mono.iter().map(|&s| (s * auto_gain).clamp(-1.0, 1.0)).collect();
                    let mut max_mono = 0.0f32;
                    for &s in &boosted {
                        let abs = s.abs();
                        if abs > max_mono {
                            max_mono = abs;
                        }
                    }
                    if max_mono > 0.001 {
                        tracing::debug!("[MIC] Mono max after AGC (gain={auto_gain:.0}x rms={rms:.6}): {max_mono:.4}");
                    }

                    let resampled = resample_f32(&boosted, device_rate, SAMPLE_RATE);
                    let samples: Vec<i16> = resampled
                        .iter()
                        .map(|&s| (s.clamp(-1.0, 1.0) * i16::MAX as f32) as i16)
                        .collect();
                    if !samples.is_empty() {
                        let _ = tx.send(AudioChunk {
                            samples,
                            sample_rate: SAMPLE_RATE,
                        });
                    }
                },
                err_fn,
                None,
            )?
        }
        SampleFormat::I16 => {
            let tx = tx.clone();
            device.build_input_stream(
                &config,
                move |data: &[i16], _: &cpal::InputCallbackInfo| {
                    // Convert to f32 for resampling
                    let f32_data: Vec<f32> = data
                        .iter()
                        .map(|&s| s as f32 / i16::MAX as f32)
                        .collect();
                    let mono = downmix_to_mono_f32(&f32_data, device_channels);
                    let rms = if mono.is_empty() {
                        0.0
                    } else {
                        let sum_sq: f32 = mono.iter().map(|s| s * s).sum();
                        (sum_sq / mono.len() as f32).sqrt()
                    };
                    let auto_gain = if rms > 0.000001 {
                        let target_rms = 0.05;
                        let computed = target_rms / rms;
                        computed.clamp(1.0, gain.max(1.0) * 100.0)
                    } else {
                        gain.max(1.0)
                    };
                    let boosted: Vec<f32> = mono.iter().map(|&s| (s * auto_gain).clamp(-1.0, 1.0)).collect();
                    let resampled = resample_f32(&boosted, device_rate, SAMPLE_RATE);
                    let samples: Vec<i16> = resampled
                        .iter()
                        .map(|&s| (s.clamp(-1.0, 1.0) * i16::MAX as f32) as i16)
                        .collect();
                    if !samples.is_empty() {
                        let _ = tx.send(AudioChunk {
                            samples,
                            sample_rate: SAMPLE_RATE,
                        });
                    }
                },
                err_fn,
                None,
            )?
        }
        _ => {
            anyhow::bail!("Unsupported sample format: {sample_format:?}");
        }
    };

    stream.play().context("Failed to start mic stream")?;
    tracing::info!("[MIC] Capture started | device='{}' | native={}Hz {}ch {:?} → target={}Hz mono",
        device_name, device_rate, device_channels, sample_format, SAMPLE_RATE);

    Ok(MicStream {
        _stream: Arc::new(stream),
        device_name,
    })
}

/// Downmix multi-channel f32 audio to mono by taking the first channel.
/// This avoids phase cancellation issues common when averaging stereo arrays.
fn downmix_to_mono_f32(data: &[f32], channels: usize) -> Vec<f32> {
    if channels == 1 {
        return data.to_vec();
    }
    data.chunks(channels)
        .map(|frame| frame[0])
        .collect()
}

/// Simple linear resampling from `from_rate` to `to_rate`.
fn resample_f32(data: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate || data.is_empty() {
        return data.to_vec();
    }
    let ratio = from_rate as f64 / to_rate as f64;
    let out_len = (data.len() as f64 / ratio) as usize;
    let mut output = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let src_idx = i as f64 * ratio;
        let idx = src_idx as usize;
        let frac = src_idx - idx as f64;
        let sample = if idx + 1 < data.len() {
            data[idx] as f64 * (1.0 - frac) + data[idx + 1] as f64 * frac
        } else {
            data[idx] as f64
        };
        output.push(sample as f32);
    }
    output
}

/// Handle that keeps the mic stream alive. Drop to stop capture.
pub struct MicStream {
    _stream: Arc<cpal::Stream>,
    device_name: String,
}

impl MicStream {
    pub fn device_name(&self) -> &str {
        &self.device_name
    }
}
