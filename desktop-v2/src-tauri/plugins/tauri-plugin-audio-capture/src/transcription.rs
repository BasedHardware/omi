//! WebSocket transcription pipeline — Rust port of Swift `TranscriptionService`.
//!
//! Opens a WebSocket to the backend Deepgram proxy, forwards VAD-gated audio
//! as binary frames, parses incoming `Results` messages, and accumulates
//! `TranscriptSegmentRequest` records that are POSTed to
//! `/v1/conversations/from-segments` when the session ends.

use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicI64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use chrono::Utc;
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::Message;
use tokio_util::sync::CancellationToken;

const KEEPALIVE_SECS: u64 = 8;

// ---------------------------------------------------------------------------
// Wire types — match backend `from-segments` schema and Deepgram responses.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct TranscriptSegmentRequest {
    pub text: String,
    pub speaker: String,
    pub speaker_id: i64,
    pub is_user: bool,
    pub person_id: Option<String>,
    pub start: f64,
    pub end: f64,
}

#[derive(Debug, Serialize)]
struct FromSegmentsRequest<'a> {
    transcript_segments: &'a [TranscriptSegmentRequest],
    source: &'a str,
    started_at: String,
    finished_at: String,
    language: &'a str,
    timezone: String,
    input_device_name: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DgWord {
    #[serde(default)]
    start: f64,
    #[serde(default)]
    end: f64,
    #[serde(default)]
    speaker: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct DgAlternative {
    #[serde(default)]
    transcript: String,
    #[serde(default)]
    words: Option<Vec<DgWord>>,
}

#[derive(Debug, Deserialize)]
struct DgChannel {
    #[serde(default)]
    alternatives: Vec<DgAlternative>,
}

#[derive(Debug, Deserialize)]
struct DgResponse {
    #[serde(default)]
    is_final: Option<bool>,
    #[serde(default)]
    channel_index: Option<Vec<i64>>,
    #[serde(default)]
    channel: Option<DgChannel>,
}

// ---------------------------------------------------------------------------
// TranscriptionStream — owns the WS, the audio sender, and the accumulated
// segments. Drop / close() ends the session.
// ---------------------------------------------------------------------------

pub struct TranscriptionStream {
    audio_tx: mpsc::UnboundedSender<Vec<u8>>,
    cancel: CancellationToken,
    writer_task: Option<JoinHandle<()>>,
    reader_task: Option<JoinHandle<()>>,
    keepalive_task: Option<JoinHandle<()>>,
    segments: Arc<Mutex<Vec<TranscriptSegmentRequest>>>,
    /// Unix timestamp (seconds) of the last received Deepgram message. Used
    /// by the consumer's watchdog to detect a silently-dropped WS and
    /// trigger a reconnect.
    last_activity: Arc<AtomicI64>,
    /// Set false when either the reader or writer task exits for any reason
    /// other than a clean cancellation. A dead stream is a reconnect signal.
    alive: Arc<AtomicBool>,
}

/// Live transcript event payload delivered to the renderer for every
/// Deepgram result (interim + final). The UI groups by `speaker` and uses
/// `is_user` to side the bubbles.
#[derive(Debug, Clone)]
pub struct LiveTranscript {
    pub text: String,
    pub is_final: bool,
    pub speaker: String,
    pub speaker_id: i64,
    pub is_user: bool,
    pub start: f64,
    pub end: f64,
}

/// Live transcript callback — called for every Deepgram message with the
/// structured event needed to render speaker-attributed bubbles.
pub type TranscriptCallback = Arc<dyn Fn(LiveTranscript) + Send + Sync>;

impl TranscriptionStream {
    /// Open a WebSocket to the backend Deepgram proxy and start forwarding.
    ///
    /// `language` is a BCP-47 / Deepgram language code (e.g. "en", "pt-BR").
    /// Deepgram's `nova-3` model only supports English; for any other language
    /// we fall back to `nova-2`, which is multilingual.
    pub async fn connect(
        backend_url: &str,
        id_token: &str,
        language: &str,
        on_transcript: Option<TranscriptCallback>,
    ) -> Result<Self, String> {
        let ws_base = backend_url
            .replacen("https://", "wss://", 1)
            .replacen("http://", "ws://", 1);
        let ws_base = ws_base.trim_end_matches('/').to_string();

        let lang = if language.trim().is_empty() { "en" } else { language };
        let model = if lang.eq_ignore_ascii_case("en") {
            "nova-3"
        } else {
            "nova-2"
        };

        let url = format!(
            "{}/v1/proxy/deepgram/ws/v1/listen?model={}&language={}\
             &smart_format=true&punctuate=true&no_delay=true&diarize=true\
             &interim_results=true&endpointing=300&utterance_end_ms=1000\
             &vad_events=true&encoding=linear16&sample_rate=16000\
             &channels=2&multichannel=true",
            ws_base, model, lang
        );

        tracing::info!("[transcription] connecting: {}", url);

        let mut request = url
            .into_client_request()
            .map_err(|e| format!("invalid ws url: {e}"))?;
        request.headers_mut().insert(
            "Authorization",
            format!("Bearer {id_token}")
                .parse()
                .map_err(|e| format!("bad auth header: {e}"))?,
        );

        let (ws, response) = tokio::time::timeout(
            Duration::from_secs(10),
            connect_async(request),
        )
        .await
        .map_err(|_| "ws connect timed out after 10s".to_string())?
        .map_err(|e| format!("ws connect failed: {e}"))?;
        tracing::info!("[transcription] ws connected, status={}", response.status());

        let (mut writer, mut reader) = ws.split();
        let cancel = CancellationToken::new();
        let segments: Arc<Mutex<Vec<TranscriptSegmentRequest>>> = Arc::new(Mutex::new(Vec::new()));
        let (audio_tx, mut audio_rx) = mpsc::unbounded_channel::<Vec<u8>>();
        let (ctrl_tx, mut ctrl_rx) = mpsc::unbounded_channel::<String>();
        let last_activity = Arc::new(AtomicI64::new(Utc::now().timestamp()));
        let alive = Arc::new(AtomicBool::new(true));

        // Writer: drain audio + control messages and send to WS.
        let cancel_w = cancel.clone();
        let alive_w = alive.clone();
        let writer_task = tokio::spawn(async move {
            loop {
                tokio::select! {
                    _ = cancel_w.cancelled() => {
                        tracing::info!("[transcription] writer cancelled");
                        let _ = writer.send(Message::Text("{\"type\":\"CloseStream\"}".into())).await;
                        let _ = writer.close().await;
                        break;
                    }
                    maybe_ctrl = ctrl_rx.recv() => {
                        match maybe_ctrl {
                            Some(text) => {
                                if let Err(e) = writer.send(Message::Text(text.into())).await {
                                    tracing::warn!("[transcription] writer ctrl send error: {}", e);
                                    break;
                                }
                            }
                            None => break,
                        }
                    }
                    maybe_audio = audio_rx.recv() => {
                        match maybe_audio {
                            Some(bytes) => {
                                if let Err(e) = writer.send(Message::Binary(bytes.into())).await {
                                    tracing::warn!("[transcription] writer audio send error: {}", e);
                                    break;
                                }
                            }
                            None => {
                                let _ = writer.send(Message::Text("{\"type\":\"CloseStream\"}".into())).await;
                                let _ = writer.close().await;
                                break;
                            }
                        }
                    }
                }
            }
            // Unclean writer exit (send error or closed peer) flips alive so
            // the consumer's watchdog can reconnect.
            if !cancel_w.is_cancelled() {
                alive_w.store(false, Ordering::Release);
            }
            tracing::info!("[transcription] writer task exiting");
        });

        // Reader: parse incoming messages and accumulate final segments.
        let segments_r = segments.clone();
        let cancel_r = cancel.clone();
        let cb = on_transcript.clone();
        let last_activity_r = last_activity.clone();
        let alive_r = alive.clone();
        let reader_task = tokio::spawn(async move {
            while let Some(msg) = reader.next().await {
                if cancel_r.is_cancelled() {
                    break;
                }
                // Any message (including KeepAlive-ack variants) resets the
                // staleness clock. Done before the match so a surprise
                // binary / unknown type still keeps the connection "alive".
                last_activity_r.store(Utc::now().timestamp(), Ordering::Release);
                match msg {
                    Ok(Message::Text(text)) => {
                        tracing::debug!("[transcription] dg text: {}", &text.chars().take(200).collect::<String>());
                        handle_dg_text(&text, &segments_r, cb.as_ref());
                    }
                    Ok(Message::Binary(bytes)) => {
                        if let Ok(text) = std::str::from_utf8(&bytes) {
                            tracing::debug!("[transcription] dg binary: {}", &text.chars().take(200).collect::<String>());
                            handle_dg_text(text, &segments_r, cb.as_ref());
                        }
                    }
                    Ok(Message::Close(frame)) => {
                        tracing::info!("[transcription] ws closed by peer: {:?}", frame);
                        break;
                    }
                    Ok(_) => {}
                    Err(e) => {
                        tracing::warn!("[transcription] ws read error: {}", e);
                        break;
                    }
                }
            }
            if !cancel_r.is_cancelled() {
                alive_r.store(false, Ordering::Release);
            }
            tracing::info!("[transcription] reader task exiting");
        });

        // Keepalive: send {"type":"KeepAlive"} every 8s.
        let cancel_k = cancel.clone();
        let ctrl_tx_k = ctrl_tx.clone();
        let keepalive_task = tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(KEEPALIVE_SECS));
            interval.tick().await;
            loop {
                tokio::select! {
                    _ = cancel_k.cancelled() => break,
                    _ = interval.tick() => {
                        if ctrl_tx_k.send("{\"type\":\"KeepAlive\"}".to_string()).is_err() {
                            break;
                        }
                    }
                }
            }
            tracing::info!("[transcription] keepalive task exiting");
        });

        Ok(Self {
            audio_tx,
            cancel,
            writer_task: Some(writer_task),
            reader_task: Some(reader_task),
            keepalive_task: Some(keepalive_task),
            segments,
            last_activity,
            alive,
        })
    }

    /// True while both reader and writer tasks are healthy. Flips false on
    /// any unclean exit (peer close, socket error, etc.).
    pub fn is_alive(&self) -> bool {
        self.alive.load(Ordering::Acquire)
    }

    /// Seconds since the reader last observed *any* traffic from Deepgram.
    /// Large values on a quiet call are normal (Deepgram only sends results
    /// on speech + our own KeepAlive-acks), but thresholds of 60–90s
    /// combined with continued audio forwarding indicate a dead WS that
    /// tungstenite hasn't noticed yet.
    pub fn seconds_since_activity(&self) -> i64 {
        Utc::now().timestamp() - self.last_activity.load(Ordering::Acquire)
    }

    /// Forward a chunk of stereo Int16 PCM to Deepgram. Non-blocking.
    pub fn send_audio(&self, bytes: Vec<u8>) {
        let _ = self.audio_tx.send(bytes);
    }

    /// Stop sending audio, wait briefly for final results, return accumulated
    /// segments. After this, the stream is dead.
    pub async fn finish(mut self) -> Vec<TranscriptSegmentRequest> {
        // Cancel everything — writer will send CloseStream + close.
        self.cancel.cancel();
        // Give Deepgram up to 2s to flush finals.
        if let Some(reader) = self.reader_task.take() {
            let _ = tokio::time::timeout(Duration::from_secs(2), reader).await;
        }
        if let Some(writer) = self.writer_task.take() {
            let _ = tokio::time::timeout(Duration::from_millis(500), writer).await;
        }
        if let Some(ka) = self.keepalive_task.take() {
            ka.abort();
        }
        let segs = self.segments.lock().unwrap().clone();
        tracing::info!("[transcription] finished with {} segments", segs.len());
        segs
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Parse a Deepgram JSON message. Always invokes the live-transcript callback
/// (interim or final) so the UI shows real-time text. Final results are also
/// appended to the persistent segment list for the conversation POST.
fn handle_dg_text(
    text: &str,
    segments: &Arc<Mutex<Vec<TranscriptSegmentRequest>>>,
    on_transcript: Option<&TranscriptCallback>,
) {
    let parsed: DgResponse = match serde_json::from_str(text) {
        Ok(p) => p,
        Err(_) => return,
    };

    let Some(channel) = parsed.channel else {
        return;
    };
    let Some(alt) = channel.alternatives.into_iter().next() else {
        return;
    };
    let trimmed = alt.transcript.trim();
    if trimmed.is_empty() {
        return;
    }

    let is_final = matches!(parsed.is_final, Some(true));

    // Channel index 0 = mic (user), 1 = system audio (others).
    let channel_index = parsed
        .channel_index
        .as_ref()
        .and_then(|v| v.first().copied())
        .unwrap_or(0);
    let is_user = channel_index == 0;

    let speaker_id = alt
        .words
        .as_ref()
        .and_then(|w| w.first())
        .and_then(|w| w.speaker)
        .unwrap_or(0);

    let (start, end) = match &alt.words {
        Some(w) if !w.is_empty() => (w.first().unwrap().start, w.last().unwrap().end),
        _ => (0.0, 0.0),
    };

    let speaker = format!("SPEAKER_{}", speaker_id);

    // Live transcript: emit on every result (interim + final) with full
    // speaker attribution so the UI can render bubbles immediately.
    if let Some(cb) = on_transcript {
        cb(LiveTranscript {
            text: trimmed.to_string(),
            is_final,
            speaker: speaker.clone(),
            speaker_id,
            is_user,
            start,
            end,
        });
    }

    if !is_final {
        return;
    }

    let seg = TranscriptSegmentRequest {
        text: alt.transcript,
        speaker,
        speaker_id,
        is_user,
        person_id: None,
        start,
        end,
    };
    segments.lock().unwrap().push(seg);
}

/// POST accumulated segments to `/v1/conversations/from-segments`. Returns
/// the backend conversation id on success.
pub async fn post_conversation(
    backend_url: &str,
    id_token: &str,
    segments: Vec<TranscriptSegmentRequest>,
    started_at: chrono::DateTime<Utc>,
    finished_at: chrono::DateTime<Utc>,
    input_device_name: Option<String>,
    language: &str,
) -> Result<String, String> {
    if segments.is_empty() {
        return Err("no segments to upload".into());
    }

    let timezone = iana_time_zone::get_timezone().unwrap_or_else(|_| "UTC".to_string());
    let lang = if language.trim().is_empty() { "en" } else { language };
    let body = FromSegmentsRequest {
        transcript_segments: &segments,
        source: "desktop",
        started_at: started_at.to_rfc3339(),
        finished_at: finished_at.to_rfc3339(),
        language: lang,
        timezone,
        input_device_name,
    };

    let url = format!(
        "{}/v1/conversations/from-segments",
        backend_url.trim_end_matches('/')
    );

    // Backend LLM pipeline (Gemini conversation summary) can easily take
    // 30–60s for a longer recording; a tight 30s timeout here was a major
    // source of silent "meeting didn't save" failures.
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(180))
        .build()
        .map_err(|e| format!("client build: {e}"))?;

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {id_token}"))
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("post failed: {}", describe_reqwest_error(&e)))?;

    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!("conversation create {}: {}", status, text));
    }

    // Response envelopes vary: some endpoints return the conversation object
    // directly ({ id, ... }), others wrap it ({ conversation: { id, ... } }).
    let backend_id = parse_conversation_id(&text)
        .ok_or_else(|| format!("missing conversation id in response: {text}"))?;

    tracing::info!(
        "[transcription] conversation created (id={}, {} segments)",
        backend_id,
        segments.len()
    );
    Ok(backend_id)
}

/// POST a recorded WAV file to `/v1/conversations/from-audio`. Used when the
/// live-transcription WebSocket was skipped (or produced no segments) — the
/// backend transcribes, diarizes, and summarizes the audio server-side.
/// Returns the backend conversation id on success.
pub async fn upload_audio_conversation(
    backend_url: &str,
    id_token: &str,
    audio_path: &Path,
    started_at: chrono::DateTime<Utc>,
    finished_at: chrono::DateTime<Utc>,
    input_device_name: Option<String>,
    language: &str,
) -> Result<String, String> {
    let bytes = match tokio::fs::read(audio_path).await {
        Ok(b) => b,
        Err(e) => {
            return Err(format!(
                "audio file missing: {}: {}",
                audio_path.display(),
                e
            ));
        }
    };

    let timezone = iana_time_zone::get_timezone().unwrap_or_else(|_| "UTC".to_string());
    let lang = if language.trim().is_empty() { "en" } else { language };
    let filename = audio_path
        .file_name()
        .and_then(|n| n.to_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| "session.wav".to_string());

    let meta = serde_json::json!({
        "source": "desktop",
        "started_at": started_at.to_rfc3339(),
        "finished_at": finished_at.to_rfc3339(),
        "language": lang,
        "timezone": timezone,
        "input_device_name": input_device_name,
    });
    let meta_text = meta.to_string();

    let audio_part = reqwest::multipart::Part::bytes(bytes)
        .file_name(filename)
        .mime_str("audio/wav")
        .map_err(|e| format!("audio part mime: {e}"))?;
    let meta_part = reqwest::multipart::Part::text(meta_text)
        .mime_str("application/json")
        .map_err(|e| format!("meta part mime: {e}"))?;

    let form = reqwest::multipart::Form::new()
        .part("audio", audio_part)
        .part("meta", meta_part);

    let url = format!(
        "{}/v1/conversations/from-audio",
        backend_url.trim_end_matches('/')
    );

    // The backend may take a couple of minutes for a long file (Deepgram
    // transcribe + Gemini summary + Firestore writes), so use a generous
    // timeout here — much longer than the segments path.
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(600))
        .build()
        .map_err(|e| format!("client build: {e}"))?;

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {id_token}"))
        .multipart(form)
        .send()
        .await
        .map_err(|e| format!("post failed: {}", describe_reqwest_error(&e)))?;

    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!("conversation create {}: {}", status, text));
    }

    let backend_id = parse_conversation_id(&text)
        .ok_or_else(|| format!("missing conversation id in response: {text}"))?;

    tracing::info!(
        "[transcription] audio conversation created (id={}, path={})",
        backend_id,
        audio_path.display()
    );
    Ok(backend_id)
}

/// Flatten a reqwest error chain into one line so `tracing::error!` actually
/// tells us *why* it failed (timeout vs connect vs protocol vs body).
/// reqwest's `Display` just says "error sending request for url (...)",
/// which is useless when the real cause is the inner `hyper::Error::Io(...)`.
fn describe_reqwest_error(err: &reqwest::Error) -> String {
    let mut parts: Vec<String> = Vec::new();
    parts.push(err.to_string());
    if err.is_timeout() {
        parts.push("[timeout]".into());
    }
    if err.is_connect() {
        parts.push("[connect]".into());
    }
    if err.is_body() {
        parts.push("[body]".into());
    }
    if err.is_request() {
        parts.push("[request]".into());
    }
    let mut cur: &dyn std::error::Error = err;
    while let Some(src) = cur.source() {
        parts.push(format!("caused by: {src}"));
        cur = src;
    }
    parts.join(" | ")
}

fn parse_conversation_id(body: &str) -> Option<String> {
    let value: serde_json::Value = serde_json::from_str(body).ok()?;
    if let Some(id) = value.get("id").and_then(|v| v.as_str()) {
        return Some(id.to_string());
    }
    value
        .get("conversation")
        .and_then(|c| c.get("id"))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

