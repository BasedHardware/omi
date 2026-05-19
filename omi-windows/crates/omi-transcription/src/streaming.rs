use anyhow::{Context, Result};
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use tokio::sync::broadcast;
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
        anyhow::bail!("Deepgram API key is empty — set it in Settings");
    }

    let url = format!(
        "{}?language={}&model={}&sample_rate={}&encoding={}&channels={}&punctuate=true&interim_results=true&diarize=true&smart_format=true",
        DEEPGRAM_WS_URL,
        config.language,
        config.model,
        config.sample_rate,
        config.encoding,
        config.channels,
    );

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

    let (ws_stream, _response) = tokio_tungstenite::connect_async(request)
        .await
        .context("Failed to connect to Deepgram WebSocket")?;

    tracing::info!("Connected to Deepgram (model={}, lang={})", config.model, config.language);

    let (mut ws_tx, mut ws_rx) = ws_stream.split();

    let tx_clone = transcript_tx.clone();
    let mut segment_counter: u64 = 0;

    // Task: send audio data to Deepgram
    let send_task = tokio::spawn(async move {
        loop {
            match audio_rx.recv().await {
                Ok(chunk) => {
                    // Convert i16 samples to little-endian bytes
                    let bytes: Vec<u8> = chunk
                        .samples
                        .iter()
                        .flat_map(|s| s.to_le_bytes())
                        .collect();
                    if let Err(e) = ws_tx.send(Message::Binary(bytes)).await {
                        tracing::error!("WS send error: {e}");
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Lagged(n)) => {
                    tracing::warn!("Audio receiver lagged by {n} messages");
                }
                Err(broadcast::error::RecvError::Closed) => {
                    // Send close frame to Deepgram
                    let _ = ws_tx.send(Message::Binary(vec![])).await;
                    break;
                }
            }
        }
    });

    // Task: receive transcripts from Deepgram
    let recv_task = tokio::spawn(async move {
        while let Some(msg) = ws_rx.next().await {
            match msg {
                Ok(Message::Text(text)) => {
                    match serde_json::from_str::<DgResponse>(&text) {
                        Ok(resp) => {
                            if let Some(channel) = resp.channel {
                                if let Some(alt) = channel.alternatives.first() {
                                    if !alt.transcript.is_empty() {
                                        let start = resp.start.unwrap_or(0.0);
                                        let duration = resp.duration.unwrap_or(0.0);
                                        let is_final = resp.is_final.unwrap_or(false);

                                        // Get speaker from first word if diarization is on
                                        let speaker = alt
                                            .words
                                            .as_ref()
                                            .and_then(|w| w.first())
                                            .and_then(|w| w.speaker)
                                            .unwrap_or(0);

                                        segment_counter += 1;
                                        let segment = TranscriptSegment {
                                            id: Some(format!("dg-{segment_counter}")),
                                            speaker,
                                            text: alt.transcript.clone(),
                                            start,
                                            end: start + duration,
                                            is_final,
                                        };

                                        let _ = tx_clone.send(segment);
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            tracing::debug!("Failed to parse DG response: {e}");
                        }
                    }
                }
                Ok(Message::Close(_)) => {
                    tracing::info!("Deepgram closed connection");
                    break;
                }
                Err(e) => {
                    tracing::error!("WS recv error: {e}");
                    break;
                }
                _ => {}
            }
        }
    });

    // Wait for either task to finish
    tokio::select! {
        _ = send_task => {}
        _ = recv_task => {}
    }

    tracing::info!("Deepgram stream ended");
    Ok(())
}
