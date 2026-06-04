use anyhow::{Context, Result};
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use tokio::sync::broadcast;
use tokio::time::{timeout, Duration};
use tokio_tungstenite::tungstenite::Message;

use crate::models::TranscriptSegment;

const DEEPGRAM_WS_URL: &str = "wss://api.deepgram.com/v1/listen";

/// Configuration for the Deepgram streaming session.
#[derive(Debug, Clone)]
pub struct DeepgramConfig {
    pub api_key: String,
    pub language: String,
    pub model: String,
    pub sample_rate: u32,
    pub encoding: String,
    pub channels: u16,
    /// Enable speaker diarization. Set true only for multi-speaker sessions.
    /// Default false — single speaker mode avoids spurious speaker splits.
    pub diarize: bool,
}

impl Default for DeepgramConfig {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            language: "en".into(),
            model: "nova-2".into(),
            sample_rate: 16_000,
            encoding: "linear16".into(),
            channels: 1,
            diarize: false,
        }
    }
}

/// Deepgram real-time transcription response (simplified).
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct DgResponse {
    #[serde(rename = "type")]
    msg_type: Option<String>,
    channel: Option<DgChannel>,
    start: Option<f64>,
    duration: Option<f64>,
    is_final: Option<bool>,
    speech_final: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct DgChannel {
    alternatives: Vec<DgAlternative>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct DgAlternative {
    transcript: String,
    confidence: f64,
    words: Option<Vec<DgWord>>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct DgWord {
    word: String,
    start: f64,
    end: f64,
    confidence: f64,
    speaker: Option<i32>,
}

/// Manages a live Deepgram WebSocket transcription session.
///
/// - Receives raw PCM i16 audio chunks via `audio_rx`
/// - Sends transcript segments via `transcript_tx`
/// - Runs until the audio channel closes or an error occurs
pub async fn run_deepgram_stream(
    config: DeepgramConfig,
    mut audio_rx: broadcast::Receiver<omi_audio::AudioChunk>,
    transcript_tx: broadcast::Sender<TranscriptSegment>,
) -> Result<()> {
    if config.api_key.is_empty() {
        tracing::error!("[TRANSCRIPTION] Deepgram API key is empty — cannot start stream");
        anyhow::bail!("Deepgram API key is empty — set it in Settings");
    }

    let key_preview = &config.api_key[..config.api_key.len().min(8)];
    tracing::info!("[TRANSCRIPTION] Starting Deepgram stream | model={} lang={} rate={} enc={} ch={} key={}...",
        config.model, config.language, config.sample_rate, config.encoding, config.channels, key_preview);

    let diarize_param = if config.diarize { "&diarize=true" } else { "" };
    let url = format!(
        "{}?language={}&model={}&sample_rate={}&encoding={}&channels={}&punctuate=true&interim_results=true&smart_format=true{}",
        DEEPGRAM_WS_URL,
        config.language,
        config.model,
        config.sample_rate,
        config.encoding,
        config.channels,
        diarize_param,
    );
    tracing::info!("[TRANSCRIPTION] WS URL: {} (diarize={})", url, config.diarize);

    let request = tokio_tungstenite::tungstenite::http::Request::builder()
        .uri(&url)
        .header("Authorization", format!("Token {}", config.api_key))
        .header("Host", "api.deepgram.com")
        .header("Connection", "Upgrade")
        .header("Upgrade", "websocket")
        .header("Sec-WebSocket-Version", "13")
        .header("Sec-WebSocket-Key", tokio_tungstenite::tungstenite::handshake::client::generate_key())
        .body(())
        .context("Failed to build WS request")?;

    tracing::info!("[TRANSCRIPTION] Attempting WebSocket connection to Deepgram...");
    let (ws_stream, response) = tokio_tungstenite::connect_async(request)
        .await
        .context("Failed to connect to Deepgram WebSocket")?;

    tracing::info!("[TRANSCRIPTION] Connected to Deepgram! HTTP status={} model={} lang={}",
        response.status(), config.model, config.language);

    let (mut ws_tx, mut ws_rx) = ws_stream.split();

    let tx_clone = transcript_tx.clone();
    let mut segment_counter: u64 = 0;

    // Task: send audio data to Deepgram
    let send_task = tokio::spawn(async move {
        let mut chunk_count: u64 = 0;
        let total_bytes: u64 = 0;
        tracing::info!("[TRANSCRIPTION] Audio send task started, waiting for audio chunks...");
        loop {
            match audio_rx.recv().await {
                Ok(chunk) => {
                    chunk_count += 1;
                    // Convert i16 samples to little-endian bytes
                    let bytes: Vec<u8> = chunk
                        .samples
                        .iter()
                        .flat_map(|s| s.to_le_bytes())
                        .collect();
                    if let Err(e) = ws_tx.send(Message::Binary(bytes)).await {
                        tracing::error!("[TRANSCRIPTION] WS send error after {} chunks: {e}", chunk_count);
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Lagged(n)) => {
                    tracing::warn!("[TRANSCRIPTION] Audio receiver lagged by {n} messages");
                }
                Err(broadcast::error::RecvError::Closed) => {
                    tracing::info!("[TRANSCRIPTION] Audio channel closed after {chunk_count} chunks, sending close frame");
                    let _ = ws_tx.send(Message::Binary(vec![])).await;
                    break;
                }
            }
        }
        tracing::info!("[TRANSCRIPTION] Audio send task finished. Total: {chunk_count} chunks, {total_bytes} bytes");
    });

    let diarize_enabled = config.diarize;

    // Task: receive transcripts from Deepgram
    let recv_task = tokio::spawn(async move {
        let mut msg_count: u64 = 0;
        let mut transcript_count: u64 = 0;
        tracing::info!("[TRANSCRIPTION] Recv task started, listening for Deepgram messages...");
        loop {
            // Use a timeout so we can log if Deepgram goes silent
            let next = timeout(Duration::from_secs(10), ws_rx.next()).await;
            match next {
                Err(_elapsed) => {
                    tracing::warn!("[TRANSCRIPTION] No message from Deepgram for 10s (msg_count={msg_count}, segments={transcript_count}) — connection may be idle or speech not detected");
                    continue;
                }
                Ok(None) => {
                    tracing::warn!("[TRANSCRIPTION] Deepgram WS stream ended (None) after {msg_count} msgs");
                    break;
                }
                Ok(Some(msg)) => match msg {
                Ok(Message::Text(text)) => {
                    msg_count += 1;
                    // Log ALL messages at info so we can see what Deepgram is returning
                    tracing::info!("[TRANSCRIPTION] DG raw #{msg_count}: {}", &text[..text.len().min(500)]);
                    match serde_json::from_str::<DgResponse>(&text) {
                        Ok(resp) => {
                            // Log non-Results messages (errors, metadata, etc.)
                            if let Some(ref t) = resp.msg_type {
                                if t != "Results" {
                                    tracing::warn!("[TRANSCRIPTION] DG non-result type={t}: {}", &text[..text.len().min(400)]);
                                }
                            }
                            if let Some(channel) = resp.channel {
                                if let Some(alt) = channel.alternatives.first() {
                                    if !alt.transcript.is_empty() {
                                        let start = resp.start.unwrap_or(0.0);
                                        let duration = resp.duration.unwrap_or(0.0);
                                        let is_final = resp.is_final.unwrap_or(false);

                                        // Only use diarization speaker IDs when diarize is enabled.
                                        // When off, always speaker=0 to avoid spurious multi-speaker splits.
                                        let speaker = if diarize_enabled {
                                            alt.words
                                                .as_ref()
                                                .and_then(|w| w.first())
                                                .and_then(|w| w.speaker)
                                                .unwrap_or(0)
                                        } else {
                                            0
                                        };

                                        segment_counter += 1;
                                        transcript_count += 1;
                                        let segment = TranscriptSegment {
                                            id: Some(format!("dg-{segment_counter}")),
                                            speaker,
                                            text: alt.transcript.clone(),
                                            start,
                                            end: start + duration,
                                            is_final,
                                        };

                                        tracing::info!(
                                            "[TRANSCRIPTION] >>> Segment #{transcript_count} | final={is_final} | speaker={speaker} | {:.2}s-{:.2}s | \"{}\"",
                                            start, start + duration, alt.transcript
                                        );

                                        let _ = tx_clone.send(segment);
                                    } else {
                                        tracing::info!("[TRANSCRIPTION] Empty transcript (silence/no-speech) in msg #{msg_count} | is_final={:?}", resp.is_final);
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            tracing::warn!("[TRANSCRIPTION] Failed to parse DG JSON: {e} | raw: {}", &text[..text.len().min(400)]);
                        }
                    }
                }
                Ok(Message::Ping(_)) => {
                    tracing::info!("[TRANSCRIPTION] DG sent Ping (msg_count={msg_count})");
                }
                Ok(Message::Pong(_)) => {
                    tracing::info!("[TRANSCRIPTION] DG sent Pong (msg_count={msg_count})");
                }
                Ok(Message::Close(frame)) => {
                    tracing::warn!("[TRANSCRIPTION] Deepgram closed connection after {msg_count} msgs | frame={:?}", frame);
                    break;
                }
                Ok(other) => {
                    tracing::info!("[TRANSCRIPTION] DG other message type: {:?}", other);
                }
                Err(e) => {
                    tracing::error!("[TRANSCRIPTION] WS recv error after {msg_count} msgs: {e}");
                    break;
                }
            }
            }
        }
        tracing::info!("[TRANSCRIPTION] Recv task done. msgs={msg_count} segments={transcript_count}");
    });

    // Wait for either task to finish
    tracing::info!("[TRANSCRIPTION] Both tasks spawned, waiting for completion...");
    tokio::select! {
        _ = send_task => { tracing::info!("[TRANSCRIPTION] Send task finished first"); }
        _ = recv_task => { tracing::info!("[TRANSCRIPTION] Recv task finished first"); }
    }

    tracing::info!("[TRANSCRIPTION] Deepgram stream ended");
    Ok(())
}
