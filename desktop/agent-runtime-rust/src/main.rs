use omi_agent_runtime::provider_policy::ManagedTransport;
use omi_agent_runtime::{
    emit_line, parse_line, select_execution_mode, ExecutionMode, Message, PROTOCOL_VERSION,
};
use rx4::{Agent, Event};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::env;
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::{mpsc, watch};

const RUNTIME_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone)]
struct ManagedCredentials {
    owner_id: String,
    bearer_token: String,
}

struct Runtime {
    managed_base_url: Option<String>,
    credentials: Option<ManagedCredentials>,
    running: HashMap<String, watch::Sender<bool>>,
    output: mpsc::UnboundedSender<Message>,
    completed: mpsc::UnboundedSender<String>,
}

impl Runtime {
    fn new(
        managed_base_url: Option<String>,
        output: mpsc::UnboundedSender<Message>,
        completed: mpsc::UnboundedSender<String>,
    ) -> Self {
        Self {
            managed_base_url,
            credentials: None,
            running: HashMap::new(),
            output,
            completed,
        }
    }

    fn emit(&self, kind: &str, fields: Map<String, Value>) {
        let _ = self.output.send(Message {
            kind: kind.into(),
            fields,
        });
    }

    fn handle(&mut self, input: Message) {
        match input.kind.as_str() {
            "refresh_token" => self.refresh_token(input.fields),
            "query" => self.query(input.fields),
            "interrupt" => self.interrupt(input.fields),
            "stop" => self.stop(),
            _ => {}
        }
    }

    fn refresh_token(&mut self, fields: Map<String, Value>) {
        let Some(owner_id) = string_field(&fields, "ownerId") else {
            return;
        };
        let Some(bearer_token) = string_field(&fields, "token") else {
            return;
        };
        self.credentials = Some(ManagedCredentials {
            owner_id,
            bearer_token,
        });
    }

    fn query(&mut self, fields: Map<String, Value>) {
        let request_id = string_field(&fields, "requestId");
        let client_id = string_field(&fields, "clientId");
        let session_id = string_field(&fields, "sessionId");
        let prompt = string_field(&fields, "prompt");
        let Some((request_id, client_id, session_id, prompt)) =
            request_id.zip(client_id).zip(session_id).zip(prompt).map(
                |(((request_id, client_id), session_id), prompt)| {
                    (request_id, client_id, session_id, prompt)
                },
            )
        else {
            self.emit_error(
                None,
                None,
                "invalid_request",
                "query requires requestId, clientId, sessionId, and prompt",
            );
            return;
        };

        let Some(base_url) = self.managed_base_url.clone() else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "provider_setup_needed",
                "Omi managed transport is not configured",
            );
            return;
        };
        let Some(credentials) = self.credentials.clone() else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "provider_setup_needed",
                "Omi managed credentials are required",
            );
            return;
        };
        if string_field(&fields, "ownerId").as_deref() != Some(credentials.owner_id.as_str()) {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "authentication",
                "query owner does not match the configured Omi managed credentials",
            );
            return;
        }
        if self.running.contains_key(&request_id) {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "query requestId is already running",
            );
            return;
        }

        let requested_mode = fields
            .get("agentMode")
            .or_else(|| fields.get("executionMode"))
            .and_then(Value::as_str)
            .and_then(|mode| match mode {
                "fast" => Some(ExecutionMode::Fast),
                "deep" => Some(ExecutionMode::Deep),
                _ => None,
            });
        let execution_mode = select_execution_mode(&prompt, requested_mode);
        let model = string_field(&fields, "modelProfile").unwrap_or_else(|| match execution_mode {
            ExecutionMode::Fast => "omi-fast".into(),
            ExecutionMode::Deep => "omi-deep".into(),
        });
        let (cancel, mut cancelled) = watch::channel(false);
        self.running.insert(request_id.clone(), cancel);
        let output = self.output.clone();
        let completed = self.completed.clone();
        tokio::spawn(async move {
            let transport = ManagedTransport::new(base_url, credentials.bearer_token);
            let Ok(transport) = transport else {
                send_error(
                    &output,
                    &request_id,
                    &client_id,
                    "provider_setup_needed",
                    "Omi managed transport is not configured",
                );
                let _ = completed.send(request_id);
                return;
            };
            let mut agent = Agent::new();
            agent.set_model(model);
            agent.set_provider(std::sync::Arc::new(transport.provider()));
            let events = output.clone();
            let event_request_id = request_id.clone();
            let event_client_id = client_id.clone();
            agent.subscribe(move |event| {
                if let Some(message) = map_agent_event(event, &event_request_id, &event_client_id) {
                    let _ = events.send(message);
                }
            });
            let text = Arc::new(Mutex::new(String::new()));
            let collected_text = Arc::clone(&text);
            let prompt_run = async {
                agent.subscribe(move |event| {
                    if let Event::MessageDelta { delta } = event {
                        if let Ok(mut text) = collected_text.lock() {
                            text.push_str(delta);
                        }
                    }
                });
                agent.prompt(&prompt).await
            };
            tokio::pin!(prompt_run);
            tokio::select! {
                result = &mut prompt_run => match result {
                    Ok(()) => {
                        let text = text.lock().map(|text| text.clone()).unwrap_or_default();
                        send_result(&output, &request_id, &client_id, &session_id, &text, "succeeded")
                    }
                    Err(error) => send_error(&output, &request_id, &client_id, "transport_interruption", &error.to_string()),
                },
                changed = cancelled.changed() => {
                    if changed.is_ok() && *cancelled.borrow() {
                        send_result(&output, &request_id, &client_id, &session_id, "", "cancelled");
                    }
                }
            }
            let _ = completed.send(request_id);
        });
    }

    fn interrupt(&mut self, fields: Map<String, Value>) {
        let request_id = string_field(&fields, "requestId");
        let accepted = request_id
            .as_deref()
            .and_then(|request_id| self.running.get(request_id))
            .is_some_and(|cancel| cancel.send(true).is_ok());
        self.emit(
            "cancel_ack",
            envelope(
                request_id.as_deref(),
                fields.get("clientId").and_then(Value::as_str),
                json!({"accepted": accepted, "dispatchAttempted": accepted, "adapterAcknowledged": accepted}),
            ),
        );
    }

    fn stop(&mut self) {
        for cancel in self.running.values() {
            let _ = cancel.send(true);
        }
        self.emit(
            "cancel_ack",
            envelope(
                None,
                None,
                json!({"accepted": true, "dispatchAttempted": true, "adapterAcknowledged": true}),
            ),
        );
    }

    fn emit_error(
        &self,
        request_id: Option<String>,
        client_id: Option<String>,
        failure_code: &str,
        message: &str,
    ) {
        send_error(
            &self.output,
            request_id.as_deref().unwrap_or_default(),
            client_id.as_deref().unwrap_or_default(),
            failure_code,
            message,
        );
    }
}

fn map_agent_event(event: &Event, request_id: &str, client_id: &str) -> Option<Message> {
    match event {
        Event::MessageDelta { delta } => Some(Message {
            kind: "text_delta".into(),
            fields: envelope(Some(request_id), Some(client_id), json!({"text": delta})),
        }),
        Event::ToolCall(call) => {
            let input =
                serde_json::from_str::<Map<String, Value>>(&call.arguments).unwrap_or_default();
            Some(Message {
                kind: "tool_use".into(),
                fields: envelope(
                    Some(request_id),
                    Some(client_id),
                    json!({"callId": call.id, "name": call.name, "input": input}),
                ),
            })
        }
        Event::Error(message) => Some(Message {
            kind: "error".into(),
            fields: envelope(
                Some(request_id),
                Some(client_id),
                json!({"message": message, "failure": {"code": "transport_interruption", "failureCode": "transport_interruption", "userMessage": message}}),
            ),
        }),
        _ => None,
    }
}

fn send_result(
    output: &mpsc::UnboundedSender<Message>,
    request_id: &str,
    client_id: &str,
    session_id: &str,
    text: &str,
    terminal_status: &str,
) {
    let _ = output.send(Message {
        kind: "result".into(),
        fields: envelope(
            Some(request_id),
            Some(client_id),
            json!({"sessionId": session_id, "text": text, "terminalStatus": terminal_status}),
        ),
    });
}

fn send_error(
    output: &mpsc::UnboundedSender<Message>,
    request_id: &str,
    client_id: &str,
    failure_code: &str,
    message: &str,
) {
    let _ = output.send(Message {
        kind: "error".into(),
        fields: envelope(
            (!request_id.is_empty()).then_some(request_id),
            (!client_id.is_empty()).then_some(client_id),
            json!({"message": message, "failure": {"code": failure_code, "failureCode": failure_code, "userMessage": message}}),
        ),
    });
}

fn envelope(request_id: Option<&str>, client_id: Option<&str>, extra: Value) -> Map<String, Value> {
    let mut fields = extra.as_object().cloned().unwrap_or_default();
    fields.insert("protocolVersion".into(), json!(PROTOCOL_VERSION));
    if let Some(request_id) = request_id {
        fields.insert("requestId".into(), json!(request_id));
    }
    if let Some(client_id) = client_id {
        fields.insert("clientId".into(), json!(client_id));
    }
    fields
}

fn string_field(fields: &Map<String, Value>, name: &str) -> Option<String> {
    fields
        .get(name)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToOwned::to_owned)
}

#[tokio::main]
async fn main() {
    let (output, mut output_receiver) = mpsc::unbounded_channel();
    let (completed, mut completed_receiver) = mpsc::unbounded_channel();
    let mut runtime = Runtime::new(env::var("OMI_API_BASE_URL").ok(), output, completed);
    runtime.emit(
        "init",
        envelope(
            None,
            None,
            json!({"sessionId": "", "agentControlTools": [], "runtimeVersion": RUNTIME_VERSION, "runtimeCapabilities": ["journal_import_remote_turn", "runtime_adapter_availability"], "runtimeAdapterIds": ["rx4"]}),
        ),
    );
    let stdin = BufReader::new(tokio::io::stdin());
    let mut lines = stdin.lines();
    let mut stdout = tokio::io::stdout();
    loop {
        tokio::select! {
            line = lines.next_line() => match line {
                Ok(Some(line)) if !line.trim().is_empty() => {
                    if let Ok(message) = parse_line(&line) {
                        runtime.handle(message);
                    }
                }
                Ok(Some(_)) => {}
                Ok(None) | Err(_) => break,
            },
            Some(request_id) = completed_receiver.recv() => {
                runtime.running.remove(&request_id);
            },
            Some(message) = output_receiver.recv() => {
                if let Ok(line) = emit_line(&message) {
                    if stdout.write_all(line.as_bytes()).await.is_err() || stdout.flush().await.is_err() {
                        break;
                    }
                }
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn agent_events_keep_the_swift_jsonl_shapes() {
        let text = map_agent_event(
            &Event::MessageDelta {
                delta: "hello".into(),
            },
            "request",
            "client",
        )
        .expect("text delta must map");
        assert_eq!(text.kind, "text_delta");
        assert_eq!(text.fields["text"], "hello");
        let tool = map_agent_event(
            &Event::ToolCall(rx4::ToolCall {
                id: "tool".into(),
                name: "search".into(),
                arguments: r#"{"q":"omi"}"#.into(),
            }),
            "request",
            "client",
        )
        .expect("tool call must map");
        assert_eq!(tool.kind, "tool_use");
        assert_eq!(tool.fields["input"]["q"], "omi");
    }

    #[tokio::test]
    async fn rejects_query_without_omi_managed_credentials() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = Runtime::new(Some("https://api.omi.me/v2".into()), output, completed);
        runtime.handle(parse_line(r#"{"type":"query","requestId":"r","clientId":"c","sessionId":"s","ownerId":"o","prompt":"hello"}"#).expect("fixture must parse"));
        let error = receiver.recv().await.expect("query must reject");
        assert_eq!(error.kind, "error");
        assert_eq!(
            error.fields["failure"]["failureCode"],
            "provider_setup_needed"
        );
    }

    #[tokio::test]
    async fn interrupt_emits_existing_cancel_ack_shape() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = Runtime::new(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"interrupt","requestId":"r","clientId":"c"}"#)
                .expect("fixture must parse"),
        );
        let ack = receiver.recv().await.expect("interrupt must acknowledge");
        assert_eq!(ack.kind, "cancel_ack");
        assert_eq!(ack.fields["accepted"], false);
        assert_eq!(ack.fields["protocolVersion"], PROTOCOL_VERSION);
    }
}
