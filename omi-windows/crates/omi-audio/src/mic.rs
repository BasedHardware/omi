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

/// Start capturing audio from the default microphone.
///
/// Uses the device's preferred config and resamples to 16kHz mono internally.
/// Returns a handle that keeps the stream alive. Drop it to stop capture.
pub fn start_mic_capture(
    tx: broadcast::Sender<AudioChunk>,
) -> Result<MicStream> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .context("No default input device available")?;

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
                    let mono = downmix_to_mono_f32(data, device_channels);
                    let resampled = resample_f32(&mono, device_rate, SAMPLE_RATE);
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
                    let resampled = resample_f32(&mono, device_rate, SAMPLE_RATE);
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

/// Downmix multi-channel f32 audio to mono by averaging channels.
fn downmix_to_mono_f32(data: &[f32], channels: usize) -> Vec<f32> {
    if channels == 1 {
        return data.to_vec();
    }
    data.chunks(channels)
        .map(|frame| frame.iter().sum::<f32>() / channels as f32)
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
