//! Local OpenAI-compat proxy for ChatGPT Codex `/backend-api/codex/responses`.

use std::{
    fs, io,
    net::SocketAddr,
    path::{Path, PathBuf},
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use axum::{
    body::Body,
    extract::{Json, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use reqwest::header::{HeaderMap, HeaderName, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::net::TcpListener;
use tokio::sync::Mutex;

const DEFAULT_PORT: u16 = 10531;
const CODEX_RESPONSES_URL: &str = "https://chatgpt.com/backend-api/codex/responses";
const OPENAI_AUTH_TOKEN_URL: &str = "https://auth.openai.com/oauth/token";
const OAUTH_CLIENT_ID: &str = "app_EMoamEEZ73f0CkXaXp7hrann";
const DEFAULT_INSTRUCTIONS: &str = "You are a helpful assistant.";

#[derive(Clone, Deserialize)]
struct AuthCore {
    access_token: String,
    account_id: String,
    #[serde(default)]
    refresh_token: Option<String>,
}

impl AuthCore {
    fn from_doc(doc: &Value) -> Result<Self, String> {
        if doc.get("access_token").is_some() {
            return serde_json::from_value(doc.clone()).map_err(|e| e.to_string());
        }
        if let Some(tokens) = doc.get("tokens") {
            return serde_json::from_value(tokens.clone()).map_err(|e| e.to_string());
        }
        Err("missing access_token (expected top-level or tokens.access_token)".into())
    }
}

struct AuthDisk {
    path: PathBuf,
    doc: Value,
}

struct AppState {
    http: reqwest::Client,
    auth: Mutex<AuthDisk>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let auth_path = default_auth_path()?;
    let doc = load_auth_doc(&auth_path)?;
    AuthCore::from_doc(&doc).map_err(|e| format!("invalid {}: {}", auth_path.display(), e))?;

    let port = std::env::var("OMI_CODEX_PROXY_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_PORT);

    let state = Arc::new(AppState {
        http: reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .user_agent(format!("omi-codex-proxy/{}", env!("CARGO_PKG_VERSION")))
            .build()?,
        auth: Mutex::new(AuthDisk {
            path: auth_path.clone(),
            doc,
        }),
    });

    let app = Router::new()
        .route("/health", get(health_ok))
        .route("/v1/chat/completions", post(chat_completions))
        .with_state(state.clone());

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let listener = TcpListener::bind(addr).await?;
    println!(
        "omi-codex-proxy listening on http://{}",
        listener.local_addr()?
    );
    println!("auth file {}", auth_path.display());

    axum::serve(listener, app).await?;
    Ok(())
}

async fn health_ok() -> &'static str {
    "ok"
}

async fn chat_completions(State(state): State<Arc<AppState>>, Json(body): Json<Value>) -> Response {
    if body.get("stream").and_then(|v| v.as_bool()) == Some(true) {
        return json_error(
            StatusCode::NOT_IMPLEMENTED,
            "stream=true is not implemented; send non-stream chat/completions.",
        )
        .into_response();
    }

    let upstream_payload = match codex_payload_from_openai_chat(&body) {
        Ok(v) => v,
        Err(msg) => return json_error(StatusCode::BAD_REQUEST, &msg).into_response(),
    };

    let requested_model_hint = body
        .get("model")
        .and_then(|m| m.as_str())
        .unwrap_or("")
        .to_owned();

    match invoke_codex(&state, &upstream_payload, requested_model_hint).await {
        Ok(resp) => resp,
        Err(msg) => json_error(StatusCode::INTERNAL_SERVER_ERROR, &msg).into_response(),
    }
}

async fn invoke_codex(
    state: &AppState,
    upstream_payload: &Value,
    requested_model_hint: String,
) -> Result<Response, String> {
    let bytes = encode_codex_request(upstream_payload)?;

    let mut refreshed = false;
    loop {
        let hdrs = {
            let g = state.auth.lock().await;
            let core = AuthCore::from_doc(&g.doc)?;
            codex_headers(&core)?
        };

        let upstream = state
            .http
            .post(CODEX_RESPONSES_URL)
            .headers(hdrs.clone())
            .header(CONTENT_TYPE, HeaderValue::from_static("application/json"))
            .header(header::ACCEPT, HeaderValue::from_static("text/event-stream"))
            .body(bytes.clone())
            .send()
            .await
            .map_err(|e| e.to_string())?;

        let status = upstream.status();
        let upstream_bytes = upstream.bytes().await.map_err(|e| e.to_string())?;

        if status.as_u16() == 401 {
            let has_refresh_token = {
                let g = state.auth.lock().await;
                AuthCore::from_doc(&g.doc)?
                    .refresh_token
                    .as_ref()
                    .map(|t| !t.is_empty())
                    .unwrap_or(false)
            };

            let should_retry = !refreshed && has_refresh_token;

            if should_retry {
                let refresh_token_owned = {
                    let g = state.auth.lock().await;
                    AuthCore::from_doc(&g.doc)?
                        .refresh_token
                        .filter(|t| !t.is_empty())
                        .ok_or_else(|| {
                            "refresh_token vanished between checks — cannot refresh access token"
                                .to_string()
                        })?
                };

                let refresh_envelope =
                    oauth_refresh_access_token(&state.http, refresh_token_owned).await?;

                {
                    let mut g = state.auth.lock().await;
                    apply_refresh_to_doc(&mut *g, refresh_envelope)?;
                }

                refreshed = true;
                continue;
            }
        }

        if !status.is_success() {
            return Ok((status, Body::from(upstream_bytes)).into_response());
        }

        let sse_body = String::from_utf8(upstream_bytes.to_vec())
            .map_err(|e| format!("upstream SSE is not valid UTF-8: {e}"))?;
        let assistant_text = collect_text_from_codex_sse(&sse_body)?;
        if assistant_text.trim().is_empty() {
            return Err("upstream SSE contained no assistant text".into());
        }

        let openai_completion = json!({
            "id": new_chat_completion_id(),
            "object": "chat.completion",
            "created": unix_secs(),
            "model": if requested_model_hint.trim().is_empty() { Value::Null } else { Value::String(requested_model_hint.clone()) },
            "choices": [{
              "index": 0,
              "message": { "role": "assistant", "content": assistant_text },
              "logprobs": null,
              "finish_reason": "stop",
            }],
            "usage": Value::Null,
        });
        return Ok(JsonResponse {
            status: StatusCode::OK,
            json: openai_completion,
        }
        .into_response());
    }
}

fn encode_codex_request(payload: &Value) -> Result<Vec<u8>, String> {
    serde_json::to_vec(payload).map_err(|e| e.to_string())
}

#[derive(Clone)]
struct JsonResponse {
    status: StatusCode,
    json: Value,
}

impl IntoResponse for JsonResponse {
    fn into_response(self) -> Response {
        let body = serde_json::to_vec(&self.json).unwrap_or_else(|_| {
            br#"{"error":{"message":"failed to serialize upstream json envelope","type":"omi_codex_proxy_error"}}"#.to_vec()
        });

        Response::builder()
            .status(self.status)
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(body))
            .unwrap()
    }
}

fn json_error(status: StatusCode, message: impl AsRef<str>) -> JsonResponse {
    JsonResponse {
        status,
        json: json!({
          "error": {
            "message": message.as_ref(),
            "type": "omi_codex_proxy_error",
          },
        }),
    }
}

#[derive(Debug, Deserialize)]
struct RefreshEnvelope {
    access_token: Option<String>,
    refresh_token: Option<String>,
}

async fn oauth_refresh_access_token(
    http: &reqwest::Client,
    refresh_token: String,
) -> Result<RefreshEnvelope, String> {
    let response = http
        .post(OPENAI_AUTH_TOKEN_URL)
        .header(
            CONTENT_TYPE,
            HeaderValue::from_static("application/x-www-form-urlencoded"),
        )
        .form(&[
            ("grant_type", "refresh_token"),
            ("refresh_token", refresh_token.as_str()),
            ("client_id", OAUTH_CLIENT_ID),
        ])
        .send()
        .await
        .map_err(|e| format!("oauth refresh transport error: {e}"))?;

    let status = response.status();
    let body_text = response
        .text()
        .await
        .map_err(|e| format!("oauth refresh read error: {e}"))?;

    if !status.is_success() {
        return Err(format!(
            "oauth refresh failed ({status}): {body_text}",
            status = status,
            body_text = body_text
        ));
    }

    let env: RefreshEnvelope = serde_json::from_str(&body_text)
        .map_err(|e| format!("oauth refresh json decode error ({e}): {body_text}"))?;

    Ok(env)
}

fn apply_refresh_to_doc(disk: &mut AuthDisk, mut env: RefreshEnvelope) -> Result<(), String> {
    let new_access = env
        .access_token
        .take()
        .filter(|t| !t.is_empty())
        .ok_or_else(|| "oauth refresh succeeded but omitted access_token".to_string())?;

    if disk.doc.get("tokens").map(|t| t.is_object()).unwrap_or(false) {
        if let Some(tokens) = disk.doc.get_mut("tokens").and_then(Value::as_object_mut) {
            tokens.insert("access_token".to_string(), Value::String(new_access));
            if let Some(new_refresh) = env.refresh_token.take().filter(|t| !t.is_empty()) {
                tokens.insert("refresh_token".to_string(), Value::String(new_refresh));
            }
        }
    } else {
        disk.doc["access_token"] = Value::String(new_access);
        if let Some(new_refresh) = env.refresh_token.take().filter(|t| !t.is_empty()) {
            disk.doc["refresh_token"] = Value::String(new_refresh);
        }
    }

    persist_auth(&disk.path, &disk.doc)?;
    println!(
        "oauth: refreshed access_token (persisted {})",
        disk.path.display()
    );
    Ok(())
}

fn codex_headers(core: &AuthCore) -> Result<HeaderMap, String> {
    let mut map = HeaderMap::new();
    let bearer = HeaderValue::from_str(format!("Bearer {}", core.access_token).as_str())
        .map_err(|e| e.to_string())?;
    map.insert(AUTHORIZATION, bearer);
    map.insert(
        HeaderName::from_static("chatgpt-account-id"),
        HeaderValue::from_str(&core.account_id).map_err(|e| e.to_string())?,
    );
    map.insert(
        HeaderName::from_static("originator"),
        HeaderValue::from_static("pi"),
    );
    Ok(map)
}

fn default_auth_path() -> Result<PathBuf, io::Error> {
    if let Ok(codex_home) = std::env::var("CODEX_HOME") {
        let trimmed = codex_home.trim();
        if !trimmed.is_empty() {
            return Ok(PathBuf::from(trimmed).join("auth.json"));
        }
    }
    let home = std::env::var_os("HOME")
        .filter(|v| !v.is_empty())
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::NotFound,
                "HOME is not set; cannot resolve ~/.codex/auth.json",
            )
        })?;
    Ok(PathBuf::from(home).join(".codex").join("auth.json"))
}

fn load_auth_doc(path: &Path) -> Result<Value, String> {
    let raw = fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_json::from_str(&raw).map_err(|e| format!("parse {}: {e}", path.display()))
}

fn persist_auth(path: &Path, doc: &Value) -> Result<(), String> {
    let serialized =
        serde_json::to_vec_pretty(doc).map_err(|e| format!("serialize auth doc: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("write {}: {e}", path.display()))
}

fn codex_payload_from_openai_chat(openai_body: &Value) -> Result<Value, String> {
    let model = openai_body
        .get("model")
        .and_then(|m| m.as_str())
        .filter(|s| !s.trim().is_empty())
        .unwrap_or("gpt-5.4");

    let messages = openai_body
        .get("messages")
        .and_then(Value::as_array)
        .ok_or_else(|| "missing array `messages`".to_string())?;

    if messages.is_empty() {
        return Err("`messages` must be non-empty".into());
    }

    let mut instructions_parts = Vec::new();
    let mut input_items = Vec::new();

    for (idx, msg) in messages.iter().enumerate() {
        let role = msg
            .get("role")
            .and_then(|r| r.as_str())
            .ok_or_else(|| format!("messages[{idx}].role missing"))?;

        if role == "system" {
            if let Some(text) = message_content_as_string(msg.get("content").unwrap_or(&Value::Null))?
            {
                if !text.is_empty() {
                    instructions_parts.push(text);
                }
            }
            continue;
        }

        let content_parts =
            normalize_message_content(msg.get("content").unwrap_or(&Value::Null), role)?;
        let parts_array = content_parts.as_array().cloned().unwrap_or_default();
        if parts_array.is_empty() {
            continue;
        }
        input_items.push(json!({
            "type": "message",
            "role": role,
            "content": parts_array,
        }));
    }

    if input_items.is_empty() {
        return Err("`messages` must include at least one non-system message".into());
    }

    let instructions = if instructions_parts.is_empty() {
        DEFAULT_INSTRUCTIONS.to_string()
    } else {
        instructions_parts.join("\n")
    };

    Ok(json!({
        "model": model,
        "store": false,
        "stream": true,
        "instructions": instructions,
        "input": input_items,
        "text": { "verbosity": "medium" },
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "auto",
        "parallel_tool_calls": true,
    }))
}

fn message_content_as_string(raw: &Value) -> Result<Option<String>, String> {
    Ok(match raw {
        Value::String(s) => Some(s.clone()),
        Value::Array(items) => {
            let mut out = String::new();
            for it in items {
                if let Some(t) = it.get("text").and_then(Value::as_str) {
                    out.push_str(t);
                }
            }
            if out.is_empty() {
                None
            } else {
                Some(out)
            }
        }
        Value::Null => None,
        other => Err(format!(
            "unsupported message content type `{}` — expected string or array",
            serde_json::to_string(other).unwrap_or_else(|_| "unknown".into())
        ))?,
    })
}

fn collect_text_from_codex_sse(body: &str) -> Result<String, String> {
    let mut text = String::new();
    for line in body.lines() {
        let data = line
            .strip_prefix("data:")
            .map(str::trim)
            .filter(|s| !s.is_empty() && *s != "[DONE]");
        let Some(data) = data else {
            continue;
        };

        let event: Value =
            serde_json::from_str(data).map_err(|e| format!("invalid SSE data json: {e}"))?;
        match event.get("type").and_then(Value::as_str) {
            Some("response.output_text.delta") => {
                if let Some(delta) = event.get("delta").and_then(Value::as_str) {
                    text.push_str(delta);
                }
            }
            Some("response.output_text.done") => {
                if text.is_empty() {
                    if let Some(done) = event.get("text").and_then(Value::as_str) {
                        text.push_str(done);
                    }
                }
            }
            Some("error") => {
                let message = event
                    .pointer("/error/message")
                    .and_then(Value::as_str)
                    .or_else(|| event.get("message").and_then(Value::as_str))
                    .unwrap_or("Codex backend returned an error event");
                return Err(message.to_string());
            }
            _ => {}
        }
    }

    Ok(text)
}

fn normalize_message_content(raw: &Value, role: &str) -> Result<Value, String> {
    let text_type = if role == "assistant" {
        "output_text"
    } else {
        "input_text"
    };
    Ok(match raw {
        Value::String(s) => json!([
            {"type": text_type, "text": s},
        ]),
        Value::Array(parts) => {
            if parts.is_empty() {
                Value::Array(vec![])
            } else {
                Value::Array(
                    parts
                        .iter()
                        .map(|part| normalize_content_part(part, text_type))
                        .collect(),
                )
            }
        }
        Value::Null => Value::Array(vec![json!({ "type": text_type, "text": "" })]),
        other => Err(format!(
            "unsupported message content type `{}` — expected string or array",
            serde_json::to_string(other).unwrap_or_else(|_| "unknown".into())
        ))?,
    })
}

fn normalize_content_part(part: &Value, default_type: &str) -> Value {
    match part {
        Value::Object(map) => {
            let mut out = map.clone();
            if !out.contains_key("type") {
                out.insert("type".to_string(), Value::String(default_type.to_string()));
            } else if let Some(Value::String(kind)) = out.get("type") {
                if kind == "text" {
                    out.insert("type".to_string(), Value::String(default_type.to_string()));
                }
            }
            Value::Object(out)
        }
        Value::String(s) => json!({ "type": default_type, "text": s }),
        other => other.clone(),
    }
}

fn codex_body_to_chat_completion(model_fallback: &str, bytes: &[u8]) -> Result<Value, String> {
    let v: Value = serde_json::from_slice(bytes).map_err(|e| format!("upstream json: {e}"))?;

    if v.get("choices").is_some() {
        let mut enriched = v;
        if enriched.get("id").and_then(Value::as_str).is_none()
            || enriched.get("id") == Some(&Value::Null)
        {
            enriched["id"] = Value::String(new_chat_completion_id());
        }
        if enriched.get("object").and_then(Value::as_str).is_none()
            || enriched.get("object") == Some(&Value::Null)
        {
            enriched["object"] = Value::from("chat.completion");
        }
        if enriched.get("created").and_then(Value::as_i64).is_none()
            || enriched.get("created") == Some(&Value::Null)
        {
            enriched["created"] = Value::Number(unix_secs().into());
        }
        Ok(enriched)
    } else {
        let text = extract_assistant_text(&v)
            .ok_or_else(|| serde_json::to_string(&v).unwrap_or_else(|_| "(unprintable)".into()))?;
        let model = chat_model_choice(&v, model_fallback)?;
        Ok(json!({
            "id": new_chat_completion_id(),
            "object": "chat.completion",
            "created": unix_secs(),
            "model": model,
            "choices": [{
              "index": 0,
              "message": { "role": "assistant", "content": text},
              "logprobs": null,
              "finish_reason": infer_finish_reason(&v),
            }],
            "usage": v.get("usage").cloned().unwrap_or(Value::Null),
        }))
    }
}

fn infer_finish_reason(v: &Value) -> Value {
    v.pointer("/choices/0/finish_reason")
        .cloned()
        .unwrap_or_else(|| Value::from("stop"))
}

fn chat_model_choice(v: &Value, fallback: &str) -> Result<Value, String> {
    if let Some(m) = v
        .get("model")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
    {
        return Ok(Value::String(m.to_owned()));
    }
    if !fallback.trim().is_empty() {
        return Ok(Value::String(fallback.to_owned()));
    }
    Err("upstream response missing model and original request lacked model hint".into())
}

fn new_chat_completion_id() -> String {
    format!("chatcmpl-{}", now_millis())
}

fn unix_secs() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

/// Best-effort assistant text extractor for Responses-style payloads (`output`, etc.).
fn extract_assistant_text(v: &Value) -> Option<String> {
    if let Some(Value::Array(choices)) = v.get("choices") {
        if let Some(first) = choices.first() {
            let text = openai_choice_text(first);
            if text.is_some() {
                return text;
            }
        }
    }

    if let Some(output) = v.get("output") {
        if let Some(text) = flatten_output_chunks(output) {
            return Some(text);
        }
    }

    let mut chunks = Vec::new();
    visit_collect_output_text(v, &mut chunks);
    if chunks.is_empty() {
        None
    } else {
        Some(chunks.join(""))
    }
}

fn openai_choice_text(choice: &Value) -> Option<String> {
    let msg = choice.get("message")?;
    extract_message_content_as_string(msg)
}

fn extract_message_content_as_string(msg: &Value) -> Option<String> {
    match msg.get("content") {
        Some(Value::String(s)) => Some(s.clone()),
        Some(Value::Array(items)) => {
            let mut out = String::new();
            for it in items {
                if let Some(t) = it.get("text").and_then(Value::as_str) {
                    out.push_str(t);
                } else if let Some(inner) = it.get("content").and_then(Value::as_str) {
                    out.push_str(inner);
                }
            }
            if !out.is_empty() {
                Some(out)
            } else {
                None
            }
        }
        Some(Value::Null) | None => None,
        _ => None,
    }
}

fn flatten_output_chunks(outputs: &Value) -> Option<String> {
    let mut combined = Vec::new();
    if let Value::Array(items) = outputs {
        for item in items {
            visit_collect_output_text(item, &mut combined);
        }
    } else {
        visit_collect_output_text(outputs, &mut combined);
    }

    (!combined.is_empty()).then(|| combined.join(""))
}

fn push_output_text_piece(map: &serde_json::Map<String, Value>, bucket: &mut Vec<String>) {
    if map.get("type").and_then(Value::as_str) != Some("output_text") {
        return;
    }
    let Some(raw) = map.get("text").and_then(Value::as_str) else {
        return;
    };
    let trimmed = raw.trim();
    if !trimmed.is_empty() {
        bucket.push(trimmed.to_owned());
    }
}

fn visit_collect_output_text(v: &Value, bucket: &mut Vec<String>) {
    match v {
        Value::Object(map) => {
            push_output_text_piece(map, bucket);
            for child in map.values() {
                visit_collect_output_text(child, bucket);
            }
        }
        Value::Array(items) => {
            for item in items {
                visit_collect_output_text(item, bucket);
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_openai_messages_to_codex_input() {
        let openai = json!({
            "model": "gpt-test",
            "messages": [
                {"role":"system","content":"You are helpful."},
                {"role":"user","content":[{"type":"input_text","text":"hi"}]},
                {"role":"assistant","content":"Hello!"},
                {"role":"user","content":"again"}
            ]
        });
        let out = codex_payload_from_openai_chat(&openai).expect("mapping");
        assert_eq!(out["instructions"], json!("You are helpful."));
        assert_eq!(out["stream"], json!(true));
        assert_eq!(out["input"].as_array().unwrap().len(), 3);
        assert_eq!(out["input"][0]["type"], json!("message"));
        assert_eq!(out["input"][0]["role"], json!("user"));
        assert_eq!(
            out["input"][0]["content"],
            json!([{"type":"input_text","text":"hi"}])
        );
        assert_eq!(
            out["input"][1]["content"],
            json!([{"type":"output_text","text":"Hello!"}])
        );
        assert_eq!(
            out["input"][2]["content"],
            json!([{"type":"input_text","text":"again"}])
        );
    }

    #[test]
    fn maps_responses_like_output_message() {
        let upstream = json!({
          "model": "gpt-output",
          "output": [{
            "type": "message",
            "role": "assistant",
            "content": [
              {"type": "output_text", "text": "Hello"}
            ]
          }]
        });

        let out =
            codex_body_to_chat_completion("", &serde_json::to_vec(&upstream).unwrap()).unwrap();
        assert_eq!(
            out["choices"][0]["message"]["content"],
            Value::from("Hello")
        );
        assert_eq!(out["model"], Value::from("gpt-output"));
    }
}
