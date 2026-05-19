// System audio capture via WASAPI loopback (cpal)

use anyhow::{Context, Result};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, SampleRate, StreamConfig};
use std::sync::Arc;
use tokio::sync::broadcast;

use crate::{AudioChunk, SAMPLE_RATE};

/// Start capturing system audio via WASAPI loopback.
///
/// On Windows, cpal's WASAPI host supports output device loopback capture.
/// This captures all system audio playing through the default output device.
pub fn start_loopback_capture(
    tx: broadcast::Sender<AudioChunk>,
) -> Result<LoopbackStream> {
    let host = cpal::default_host();

    // Use default output device for loopback
    let device = host
        .default_output_device()
        .context("No default output device for loopback")?;

    let device_name = device.name().unwrap_or_else(|_| "unknown".into());
    tracing::info!("Loopback device: {device_name}");

    let default_config = device.default_output_config()
        .context("Failed to get default output config")?;

    let native_rate = default_config.sample_rate().0;
    let native_channels = default_config.channels();
    tracing::info!("Loopback native format: {native_rate}Hz, {native_channels}ch, {:?}", default_config.sample_format());

    let config = StreamConfig {
        channels: native_channels,
        sample_rate: SampleRate(native_rate),
        buffer_size: cpal::BufferSize::Default,
    };

    let err_fn = |err: cpal::StreamError| {
        tracing::error!("Loopback stream error: {err}");
    };

    let target_rate = SAMPLE_RATE;
    let ch = native_channels as usize;

    let stream = match default_config.sample_format() {
        SampleFormat::F32 => {
            let tx = tx.clone();
            device.build_input_stream(
                &config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    let mono = downmix_and_resample_f32(data, ch, native_rate, target_rate);
                    let _ = tx.send(AudioChunk {
                        samples: mono,
                        sample_rate: target_rate,
                    });
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
                    let mono = downmix_and_resample_i16(data, ch, native_rate, target_rate);
                    let _ = tx.send(AudioChunk {
                        samples: mono,
                        sample_rate: target_rate,
                    });
                },
                err_fn,
                None,
            )?
        }
        _ => anyhow::bail!("Unsupported sample format: {:?}", default_config.sample_format()),
    };

    stream.play().context("Failed to start loopback stream")?;
    tracing::info!("Loopback capture started");

    Ok(LoopbackStream {
        _stream: Arc::new(stream),
        device_name,
    })
}

/// Downmix multi-channel f32 to mono i16 and resample to target rate.
fn downmix_and_resample_f32(data: &[f32], channels: usize, src_rate: u32, dst_rate: u32) -> Vec<i16> {
    // Downmix to mono
    let mono_f32: Vec<f32> = data
        .chunks(channels)
        .map(|frame| {
            let sum: f32 = frame.iter().sum();
            sum / channels as f32
        })
        .collect();

    // Simple linear resample if rates differ
    let mono_i16: Vec<i16> = if src_rate == dst_rate {
        mono_f32.iter().map(|&s| (s.clamp(-1.0, 1.0) * i16::MAX as f32) as i16).collect()
    } else {
        let ratio = dst_rate as f64 / src_rate as f64;
        let out_len = (mono_f32.len() as f64 * ratio) as usize;
        (0..out_len)
            .map(|i| {
                let src_idx = i as f64 / ratio;
                let idx = src_idx as usize;
                let frac = src_idx - idx as f64;
                let s0 = mono_f32.get(idx).copied().unwrap_or(0.0);
                let s1 = mono_f32.get(idx + 1).copied().unwrap_or(s0);
                let s = s0 + (s1 - s0) * frac as f32;
                (s.clamp(-1.0, 1.0) * i16::MAX as f32) as i16
            })
            .collect()
    };

    mono_i16
}

/// Downmix multi-channel i16 to mono i16 and resample to target rate.
fn downmix_and_resample_i16(data: &[i16], channels: usize, src_rate: u32, dst_rate: u32) -> Vec<i16> {
    let mono: Vec<i16> = data
        .chunks(channels)
        .map(|frame| {
            let sum: i32 = frame.iter().map(|&s| s as i32).sum();
            (sum / channels as i32) as i16
        })
        .collect();

    if src_rate == dst_rate {
        return mono;
    }

    let ratio = dst_rate as f64 / src_rate as f64;
    let out_len = (mono.len() as f64 * ratio) as usize;
    (0..out_len)
        .map(|i| {
            let src_idx = i as f64 / ratio;
            let idx = src_idx as usize;
            let frac = src_idx - idx as f64;
            let s0 = mono.get(idx).copied().unwrap_or(0) as f64;
            let s1 = mono.get(idx + 1).copied().unwrap_or(s0 as i16) as f64;
            (s0 + (s1 - s0) * frac) as i16
        })
        .collect()
}

/// Handle that keeps the loopback stream alive.
pub struct LoopbackStream {
    _stream: Arc<cpal::Stream>,
    device_name: String,
}

impl LoopbackStream {
    pub fn device_name(&self) -> &str {
        &self.device_name
    }
}
