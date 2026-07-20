use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
};

use base64::{engine::general_purpose, Engine};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};

const LISTEN_EVENT: &str = "omi://listen-message";
const LISTEN_URL: &str = "wss://api.omi.me/v4/listen";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ListenStartArgs {
    pub session_id: String,
    #[serde(rename = "source")]
    pub _source: ListenSource,
    pub token: String,
    pub device_id_hash: String,
    pub language: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ListenSource {
    Mic,
    System,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct BackendSegment {
    pub id: Option<String>,
    pub text: String,
    pub speaker: Option<String>,
    pub speaker_id: Option<u64>,
    pub is_user: bool,
    pub person_id: Option<String>,
    pub start: f64,
    pub end: f64,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ListenEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub raw: Value,
}

#[derive(Clone, Debug, Serialize)]
#[serde(
    tag = "kind",
    rename_all = "snake_case",
    rename_all_fields = "camelCase"
)]
pub enum ListenMessage {
    Connected {
        session_id: String,
    },
    Segments {
        session_id: String,
        segments: Vec<BackendSegment>,
    },
    Event {
        session_id: String,
        event: ListenEvent,
    },
    Error {
        session_id: String,
        message: String,
        fatal: bool,
    },
    Closed {
        session_id: String,
        code: u16,
        reason: String,
    },
}

enum ListenControl {
    Audio(Vec<u8>),
    Stop,
}

struct Session {
    token: u64,
    sender: mpsc::Sender<ListenControl>,
}

pub struct ListenSessions {
    next_token: AtomicU64,
    sessions: Mutex<HashMap<String, Session>>,
}

impl Default for ListenSessions {
    fn default() -> Self {
        Self {
            next_token: AtomicU64::new(0),
            sessions: Mutex::new(HashMap::new()),
        }
    }
}

impl ListenSessions {
    fn replace(
        &self,
        session_id: String,
        sender: mpsc::Sender<ListenControl>,
    ) -> Result<(u64, Option<mpsc::Sender<ListenControl>>), String> {
        let token = self.next_token.fetch_add(1, Ordering::Relaxed);
        let previous = self
            .sessions
            .lock()
            .map_err(|error| error.to_string())?
            .insert(session_id, Session { token, sender });
        Ok((token, previous.map(|session| session.sender)))
    }

    fn send(&self, session_id: &str, control: ListenControl) -> Result<(), String> {
        let sender = self
            .sessions
            .lock()
            .map_err(|error| error.to_string())?
            .get(session_id)
            .map(|session| session.sender.clone());
        if let Some(sender) = sender {
            match sender.try_send(control) {
                Ok(()) | Err(mpsc::error::TrySendError::Closed(_)) => Ok(()),
                Err(mpsc::error::TrySendError::Full(_)) => Ok(()),
            }
        } else {
            Ok(())
        }
    }

    fn remove_if(&self, session_id: &str, token: u64) {
        let Ok(mut sessions) = self.sessions.lock() else {
            return;
        };
        if sessions
            .get(session_id)
            .is_some_and(|session| session.token == token)
        {
            sessions.remove(session_id);
        }
    }
}

fn platform_header() -> &'static str {
    #[cfg(target_os = "windows")]
    {
        "windows"
    }
    #[cfg(target_os = "macos")]
    {
        "macos"
    }
    #[cfg(target_os = "linux")]
    {
        "linux"
    }
}

fn endpoint(language: &str, uid: Option<&str>) -> String {
    let mut query = url::form_urlencoded::Serializer::new(String::new());
    query.append_pair(
        "language",
        if language.is_empty() { "en" } else { language },
    );
    query.append_pair("sample_rate", "16000");
    query.append_pair("codec", "pcm16");
    query.append_pair("channels", "1");
    query.append_pair("include_speech_profile", "true");
    query.append_pair("source", "desktop");
    query.append_pair("speaker_auto_assign", "enabled");
    if let Some(uid) = uid.filter(|uid| !uid.is_empty()) {
        query.append_pair("uid", uid);
    }
    format!("{LISTEN_URL}?{}", query.finish())
}

fn token_uid(token: &str) -> Option<String> {
    let encoded = token.split('.').nth(1)?;
    let bytes = general_purpose::URL_SAFE_NO_PAD
        .decode(encoded)
        .or_else(|_| general_purpose::URL_SAFE.decode(encoded))
        .ok()?;
    let payload: Value = serde_json::from_slice(&bytes).ok()?;
    payload
        .get("user_id")
        .or_else(|| payload.get("sub"))?
        .as_str()
        .map(ToOwned::to_owned)
}

fn request(
    args: &ListenStartArgs,
) -> Result<tokio_tungstenite::tungstenite::http::Request<()>, String> {
    tokio_tungstenite::tungstenite::http::Request::builder()
        .uri(endpoint(&args.language, token_uid(&args.token).as_deref()))
        .header("Authorization", format!("Bearer {}", args.token))
        .header("X-App-Platform", platform_header())
        .header("X-Device-Id-Hash", &args.device_id_hash)
        .body(())
        .map_err(|error| error.to_string())
}

fn emit(app: &AppHandle, label: &str, message: ListenMessage) {
    let _ = app.emit_to(label, LISTEN_EVENT, message);
}

fn decode_message(session_id: &str, text: &str) -> Option<ListenMessage> {
    let text = text.trim();
    if text.is_empty() || text == "ping" {
        return None;
    }
    let value: Value = serde_json::from_str(text).ok()?;
    if let Some(segments) = value.as_array() {
        return serde_json::from_value::<Vec<BackendSegment>>(Value::Array(segments.clone()))
            .ok()
            .map(|segments| ListenMessage::Segments {
                session_id: session_id.to_owned(),
                segments,
            });
    }
    let event_type = value.get("type")?.as_str()?.to_owned();
    Some(ListenMessage::Event {
        session_id: session_id.to_owned(),
        event: ListenEvent {
            event_type,
            raw: value,
        },
    })
}

#[tauri::command]
pub fn listen_start(
    app: AppHandle,
    window: WebviewWindow,
    args: ListenStartArgs,
    sessions: State<'_, ListenSessions>,
) -> Result<(), String> {
    let (sender, mut receiver) = mpsc::channel(32);
    let session_id = args.session_id.clone();
    let request = request(&args)?;
    let (token, previous) = sessions.replace(session_id.clone(), sender)?;
    if let Some(previous) = previous {
        let _ = previous.try_send(ListenControl::Stop);
    }
    let app_handle = app.clone();
    let owner_label = window.label().to_owned();
    tauri::async_runtime::spawn(async move {
        let socket = match connect_async(request).await {
            Ok((socket, _)) => socket,
            Err(error) => {
                emit(
                    &app_handle,
                    &owner_label,
                    ListenMessage::Error {
                        session_id: session_id.clone(),
                        message: error.to_string(),
                        fatal: true,
                    },
                );
                app_handle
                    .state::<ListenSessions>()
                    .remove_if(&session_id, token);
                return;
            }
        };
        emit(
            &app_handle,
            &owner_label,
            ListenMessage::Connected {
                session_id: session_id.clone(),
            },
        );
        let (mut writer, mut reader) = socket.split();
        let mut closed = None;
        loop {
            tokio::select! {
                control = receiver.recv() => match control {
                    Some(ListenControl::Audio(pcm)) => {
                        if let Err(error) = writer.send(Message::Binary(pcm.into())).await {
                            emit(&app_handle, &owner_label, ListenMessage::Error { session_id: session_id.clone(), message: error.to_string(), fatal: false });
                            closed = Some((1006, error.to_string()));
                            break;
                        }
                    }
                    Some(ListenControl::Stop) | None => {
                        let _ = writer.close().await;
                        break;
                    }
                },
                message = reader.next() => match message {
                    Some(Ok(Message::Text(text))) => {
                        if let Some(message) = decode_message(&session_id, &text) {
                            emit(&app_handle, &owner_label, message);
                        }
                    }
                    Some(Ok(Message::Ping(payload))) => {
                        if let Err(error) = writer.send(Message::Pong(payload)).await {
                            emit(&app_handle, &owner_label, ListenMessage::Error { session_id: session_id.clone(), message: error.to_string(), fatal: false });
                            closed = Some((1006, error.to_string()));
                            break;
                        }
                    }
                    Some(Ok(Message::Close(frame))) => {
                        closed = Some(frame.map_or((1005, String::new()), |frame| (frame.code.into(), frame.reason.to_string())));
                        break;
                    }
                    Some(Ok(_)) => {}
                    Some(Err(error)) => {
                        emit(&app_handle, &owner_label, ListenMessage::Error { session_id: session_id.clone(), message: error.to_string(), fatal: false });
                        closed = Some((1006, error.to_string()));
                        break;
                    }
                    None => {
                        closed = Some((1005, String::new()));
                        break;
                    }
                }
            }
        }
        if let Some((code, reason)) = closed {
            emit(
                &app_handle,
                &owner_label,
                ListenMessage::Closed {
                    session_id: session_id.clone(),
                    code,
                    reason,
                },
            );
        }
        app_handle
            .state::<ListenSessions>()
            .remove_if(&session_id, token);
    });
    Ok(())
}

#[tauri::command]
pub fn listen_stop(session_id: String, sessions: State<'_, ListenSessions>) -> Result<(), String> {
    sessions.send(&session_id, ListenControl::Stop)
}

#[tauri::command]
pub fn listen_feed(
    session_id: String,
    pcm: Vec<u8>,
    sessions: State<'_, ListenSessions>,
) -> Result<(), String> {
    sessions.send(&session_id, ListenControl::Audio(pcm))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_the_existing_listen_endpoint_and_headers() {
        let args = ListenStartArgs {
            session_id: "session".into(),
            _source: ListenSource::Mic,
            token: "header.eyJ1c2VyX2lkIjoidXNlciJ9.signature".into(),
            device_id_hash: "deadbeef".into(),
            language: "en-US".into(),
        };
        let request = request(&args).unwrap();
        assert_eq!(request.uri().path(), "/v4/listen");
        assert!(request.uri().query().unwrap().contains("uid=user"));
        assert_eq!(
            request.headers()["authorization"],
            "Bearer header.eyJ1c2VyX2lkIjoidXNlciJ9.signature"
        );
        assert_eq!(request.headers()["x-device-id-hash"], "deadbeef");
    }

    #[test]
    fn forwards_segment_batches_and_typed_events() {
        let segments = decode_message(
            "session",
            r#"[{"text":"hello","is_user":true,"start":0,"end":1}]"#,
        );
        assert!(matches!(segments, Some(ListenMessage::Segments { .. })));
        let event = decode_message("session", r#"{"type":"memory_creating"}"#);
        assert!(matches!(event, Some(ListenMessage::Event { .. })));
    }
}
