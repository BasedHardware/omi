/// TTS Engine — local voice synthesis without requiring Firebase auth.
///
/// Primary path:  OpenAI tts-1  →  MP3 bytes  →  write temp file  →  rodio playback
/// Fallback path: return Err so the caller can delegate to JS window.speak()
///
/// Usage:
///   match tts_engine::speak_text("Hello world", &cfg).await {
///       Ok(()) => { /* audio played */ }
///       Err(_) => { /* try JS path */ }
///   }

use anyhow::{bail, Context, Result};
use std::io::Write;
use tracing::{info, warn};

use crate::config::AppConfig;

/// Speak `text` aloud using OpenAI TTS (or Google TTS fallback).
///
/// Blocks the current thread briefly during `rodio` sink playback (sink.sleep_until_end).
pub async fn speak_text(text: &str, cfg: &AppConfig) -> Result<()> {
    if text.trim().is_empty() {
        return Ok(());
    }

    let api_key = cfg.openai_api_key.trim().to_string();
    let mp3_bytes = if !api_key.is_empty() {
        let voice = if cfg.openai_tts_voice.is_empty() {
            "alloy".to_string()
        } else {
            cfg.openai_tts_voice.clone()
        };

        info!("[TTS] Synthesizing {} chars with voice={voice} (OpenAI)", text.len());

        // ── 1a. Call OpenAI TTS ────────────────────────────────────────────────────
        let client = reqwest::Client::new();
        let body = serde_json::json!({
            "model": "tts-1",
            "input": text,
            "voice": voice,
            "response_format": "mp3"
        });

        let response = client
            .post("https://api.openai.com/v1/audio/speech")
            .bearer_auth(&api_key)
            .json(&body)
            .send()
            .await
            .context("OpenAI TTS request failed")?;

        if !response.status().is_success() {
            let status = response.status();
            let err_text = response.text().await.unwrap_or_default();
            bail!("OpenAI TTS HTTP {status}: {err_text}");
        }

        response.bytes().await.context("Failed to read TTS response bytes")?
    } else {
        info!("[TTS] Synthesizing {} chars using Google TTS fallback", text.len());
        // ── 1b. Call Google Translate TTS ──────────────────────────────────────────
        let client = reqwest::Client::new();
        let safe_text = text.chars().take(200).collect::<String>();
        let encoded = urlencoding::encode(&safe_text);
        let url = format!("https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en&q={}", encoded);

        let response = client
            .get(&url)
            .send()
            .await
            .context("Google TTS request failed")?;

        if !response.status().is_success() {
            let status = response.status();
            let err_text = response.text().await.unwrap_or_default();
            bail!("Google TTS HTTP {status}: {err_text}");
        }

        response.bytes().await.context("Failed to read Google TTS response bytes")?
    };

    info!("[TTS] Received {} bytes of MP3 audio", mp3_bytes.len());

    // ── 2. Write to a temp file so rodio can decode ───────────────────────────
    let mut tmp = tempfile::Builder::new()
        .suffix(".mp3")
        .tempfile()
        .context("Failed to create temp file for TTS")?;
    tmp.write_all(&mp3_bytes).context("Failed to write TTS bytes")?;
    let tmp_path = tmp.path().to_path_buf();

    // ── 3. Play via rodio (spawn_blocking to keep async clean) ────────────────
    tokio::task::spawn_blocking(move || -> Result<()> {
        let (_stream, stream_handle) = rodio::OutputStream::try_default()
            .context("Failed to open audio output stream")?;
        let sink = rodio::Sink::try_new(&stream_handle)
            .context("Failed to create audio sink")?;

        let file = std::fs::File::open(&tmp_path)
            .context("Failed to open TTS temp file")?;
        let buf_reader = std::io::BufReader::new(file);
        let source = rodio::Decoder::new(buf_reader)
            .context("Failed to decode MP3")?;

        sink.append(source);
        sink.sleep_until_end(); // blocks until playback complete
        info!("[TTS] Playback finished");
        Ok(())
    })
    .await
    .context("TTS spawn_blocking panicked")?
    .context("TTS playback error")
}

/// Check if TTS is available based on current config.
pub fn is_available(_cfg: &AppConfig) -> bool {
    true // We have Google TTS fallback
}

/// Speak text in a fire-and-forget tokio task.
/// Errors are logged, not propagated. Use this for non-critical narration.
pub fn speak_detached(text: String, cfg: AppConfig) {
    tokio::spawn(async move {
        match speak_text(&text, &cfg).await {
            Ok(()) => {}
            Err(e) => warn!("[TTS] speak_detached error: {e:#}"),
        }
    });
}
