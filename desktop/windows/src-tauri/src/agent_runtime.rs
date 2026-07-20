use std::{
    collections::HashMap,
    env,
    sync::{Arc, Mutex},
    time::Duration,
};

use omi_agent_runtime::{parse_line, Message};
use serde_json::Value;
use tauri::{AppHandle, Emitter};
use tokio::sync::{mpsc, oneshot};

const EVENT: &str = "omi://agent-runtime";
const MANAGED_API_BASE_URL: &str = "https://api.omi.me/v2";

fn managed_api_base_url(configured: Option<String>) -> String {
    configured
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| MANAGED_API_BASE_URL.to_owned())
}

fn event_payload(message: Message) -> Value {
    let mut payload = message.fields;
    payload.insert("type".into(), Value::String(message.kind));
    Value::Object(payload)
}

pub struct AgentRuntimeState {
    input: mpsc::UnboundedSender<Message>,
    replies: Arc<Mutex<HashMap<String, oneshot::Sender<Value>>>>,
    startup_error: Arc<Mutex<Option<String>>>,
}

impl AgentRuntimeState {
    pub fn start(app: AppHandle) -> Self {
        let (input, input_receiver) = mpsc::unbounded_channel();
        let (output, mut output_receiver) = mpsc::unbounded_channel();
        let replies = Arc::new(Mutex::new(HashMap::<String, oneshot::Sender<Value>>::new()));
        let base_url = managed_api_base_url(env::var("OMI_API_BASE_URL").ok());

        let bundle_id = app.config().identifier.clone();
        if let Ok(data_root) = crate::native::data_root() {
            let state_dir = data_root.join("AgentRuntime").join(&bundle_id);
            let artifacts_dir = data_root.join("Artifacts").join(&bundle_id);
            let _ = std::fs::create_dir_all(&state_dir);
            let _ = std::fs::create_dir_all(&artifacts_dir);
            env::set_var("OMI_AGENT_STATE_DIR", state_dir);
            env::set_var("OMI_AGENT_ARTIFACTS_DIR", artifacts_dir);
        }

        let startup_error = Arc::new(Mutex::new(None));
        let startup_error_for_runtime = Arc::clone(&startup_error);
        let startup_output = output.clone();
        tauri::async_runtime::spawn(async move {
            if let Err(error) =
                omi_agent_runtime::host::run_in_process(Some(base_url), input_receiver, output)
                    .await
            {
                *startup_error_for_runtime
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(error.clone());
                let mut fields = serde_json::Map::new();
                fields.insert("message".into(), Value::String(error.clone()));
                fields.insert(
                    "failure".into(),
                    serde_json::json!({
                        "code": "runtime_startup_failed",
                        "failureCode": "runtime_startup_failed",
                        "userMessage": "Omi's agent runtime could not start. Please restart Omi and try again."
                    }),
                );
                if startup_output
                    .send(Message {
                        kind: "error".into(),
                        fields,
                    })
                    .is_err()
                {
                    eprintln!("agent runtime startup failure could not be delivered: {error}");
                }
            }
        });
        let waiting_replies = Arc::clone(&replies);
        tauri::async_runtime::spawn(async move {
            while let Some(message) = output_receiver.recv().await {
                let payload = event_payload(message);
                if let Some(request_id) = payload.get("requestId").and_then(Value::as_str) {
                    if let Some(reply) = waiting_replies
                        .lock()
                        .unwrap_or_else(|error| error.into_inner())
                        .remove(request_id)
                    {
                        if reply.send(payload.clone()).is_err() {
                            eprintln!(
                                "agent runtime reply receiver dropped for request {request_id}"
                            );
                        }
                    }
                }
                if let Err(error) = app.emit(EVENT, payload) {
                    eprintln!("agent runtime event delivery failed: {error}");
                }
            }
        });
        Self {
            input,
            replies,
            startup_error,
        }
    }

    fn dispatch(&self, payload: Value) -> Result<(), String> {
        if let Some(error) = self
            .startup_error
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
        {
            return Err(format!("agent runtime failed to start: {error}"));
        }
        let line = serde_json::to_string(&payload).map_err(|error| error.to_string())?;
        let message = parse_line(&line).map_err(|error| error.to_string())?;
        self.input
            .send(message)
            .map_err(|_| "agent runtime is unavailable".to_owned())
    }

    async fn request(&self, payload: Value) -> Result<Value, String> {
        let request_id = payload
            .get("requestId")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| "agent runtime requestId is required".to_owned())?
            .to_owned();
        let (reply, receive) = oneshot::channel();
        self.replies
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .insert(request_id.clone(), reply);
        if let Err(error) = self.dispatch(payload) {
            self.replies
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .remove(&request_id);
            return Err(error);
        }
        match tokio::time::timeout(Duration::from_secs(15), receive).await {
            Ok(Ok(reply)) => Ok(reply),
            Ok(Err(_)) => Err("agent runtime reply channel closed".to_owned()),
            Err(_) => {
                self.replies
                    .lock()
                    .unwrap_or_else(|error| error.into_inner())
                    .remove(&request_id);
                Err("agent runtime did not reply".to_owned())
            }
        }
    }
}

#[tauri::command]
pub fn agent_runtime_dispatch(
    state: tauri::State<'_, AgentRuntimeState>,
    payload: Value,
) -> Result<(), String> {
    state.dispatch(payload)
}

#[tauri::command]
pub async fn agent_runtime_request(
    state: tauri::State<'_, AgentRuntimeState>,
    payload: Value,
) -> Result<Value, String> {
    state.request(payload).await
}

#[cfg(test)]
mod tests {
    use serde_json::{json, Map};

    #[test]
    fn preserves_the_runtime_jsonl_event_envelope() {
        let mut fields = Map::new();
        fields.insert("delta".into(), json!("hello"));
        assert_eq!(
            super::event_payload(super::Message {
                kind: "agent_delta".into(),
                fields,
            }),
            json!({"type":"agent_delta","delta":"hello"})
        );
    }

    #[test]
    fn uses_the_managed_api_for_packaged_builds() {
        assert_eq!(super::managed_api_base_url(None), "https://api.omi.me/v2");
        assert_eq!(
            super::managed_api_base_url(Some("https://example.test/v2".into())),
            "https://example.test/v2"
        );
    }
}
