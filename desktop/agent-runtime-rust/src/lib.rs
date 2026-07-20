use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use thiserror::Error;
use tokio::sync::{mpsc, watch, Mutex};
use tokio::task::JoinHandle;

pub mod safety;

pub mod provider_policy;
pub mod tool_relay;

pub const DEFAULT_SUBAGENT_INBOX_CAPACITY: usize = 32;

pub const PROTOCOL_VERSION: u8 = 2;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Message {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(flatten)]
    pub fields: Map<String, Value>,
}

#[derive(Debug, Error)]
pub enum CodecError {
    #[error("JSONL line is not a JSON object")]
    NotObject,
    #[error("JSONL message is missing a string type")]
    MissingType,
    #[error("invalid JSONL: {0}")]
    Json(#[from] serde_json::Error),
}

pub fn parse_line(line: &str) -> Result<Message, CodecError> {
    let value: Value = serde_json::from_str(line)?;
    let Value::Object(mut fields) = value else {
        return Err(CodecError::NotObject);
    };
    let Some(Value::String(kind)) = fields.remove("type") else {
        return Err(CodecError::MissingType);
    };
    Ok(Message { kind, fields })
}

pub fn emit_line(message: &Message) -> Result<String, CodecError> {
    let mut fields = message.fields.clone();
    fields.insert("type".into(), Value::String(message.kind.clone()));
    Ok(serde_json::to_string(&Value::Object(fields))? + "\n")
}

pub fn parse_jsonl(input: &str) -> Result<Vec<Message>, CodecError> {
    input
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(parse_line)
        .collect()
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionMode {
    #[default]
    Fast,
    Deep,
}

pub fn select_execution_mode(prompt: &str, requested: Option<ExecutionMode>) -> ExecutionMode {
    if let Some(requested) = requested {
        return requested;
    }

    let prompt = prompt.to_ascii_lowercase();
    if ["deep mode", "deep work", "go deep", "use deep"]
        .iter()
        .any(|phrase| prompt.contains(phrase))
    {
        return ExecutionMode::Deep;
    }

    if [
        "code",
        "implement",
        "debug",
        "refactor",
        "compile",
        "test",
        "rust",
        "swift",
        "typescript",
        "repository",
        "repo",
        "pull request",
    ]
    .iter()
    .any(|term| prompt.contains(term))
    {
        return ExecutionMode::Deep;
    }

    let tool_requests = [
        "search", "browse", "open", "run", "terminal", "file", "files",
    ]
    .iter()
    .filter(|term| prompt.contains(**term))
    .count();
    let multi_step = prompt.matches("then").count()
        + prompt.matches("after").count()
        + prompt.matches("first").count()
        + prompt.matches("second").count();
    if tool_requests >= 2 || multi_step >= 2 {
        ExecutionMode::Deep
    } else {
        ExecutionMode::Fast
    }
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub struct SubagentId(String);

impl SubagentId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SubagentStatus {
    Running,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, PartialEq)]
pub enum SubagentCompletion {
    Succeeded(Value),
    Failed(String),
    Cancelled,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum SubagentError {
    #[error("subagent {0} does not exist")]
    Unknown(String),
    #[error("subagent {0} is no longer running")]
    NotRunning(String),
    #[error("subagent {0} was already collected")]
    AlreadyCollected(String),
    #[error("subagent inbox capacity must be greater than zero")]
    EmptyInbox,
    #[error("subagent task failed: {0}")]
    Task(String),
    #[error("subagent task panicked or was aborted")]
    Join,
}

pub struct SubagentContext {
    inbox: mpsc::Receiver<Message>,
    cancelled: watch::Receiver<bool>,
}

impl SubagentContext {
    pub async fn receive(&mut self) -> Option<Message> {
        self.inbox.recv().await
    }

    pub async fn cancelled(&mut self) {
        if *self.cancelled.borrow() {
            return;
        }
        while self.cancelled.changed().await.is_ok() {
            if *self.cancelled.borrow() {
                return;
            }
        }
    }

    pub fn is_cancelled(&self) -> bool {
        *self.cancelled.borrow()
    }
}

pub trait SubagentTask: Send + 'static {
    fn run(
        self: Box<Self>,
        context: SubagentContext,
    ) -> Pin<Box<dyn Future<Output = Result<Value, SubagentError>> + Send>>;
}

impl<F, Fut> SubagentTask for F
where
    F: FnOnce(SubagentContext) -> Fut + Send + 'static,
    Fut: Future<Output = Result<Value, SubagentError>> + Send + 'static,
{
    fn run(
        self: Box<Self>,
        context: SubagentContext,
    ) -> Pin<Box<dyn Future<Output = Result<Value, SubagentError>> + Send>> {
        Box::pin((*self)(context))
    }
}

struct SubagentEntry {
    status: SubagentStatus,
    cancel: watch::Sender<bool>,
    inbox: mpsc::Sender<Message>,
    handle: Option<JoinHandle<SubagentCompletion>>,
}

#[derive(Clone)]
pub struct SubagentSupervisor {
    entries: Arc<Mutex<HashMap<SubagentId, SubagentEntry>>>,
    next_id: Arc<AtomicU64>,
    inbox_capacity: usize,
}

impl Default for SubagentSupervisor {
    fn default() -> Self {
        Self::new()
    }
}

impl SubagentSupervisor {
    pub fn new() -> Self {
        Self::with_inbox_capacity(DEFAULT_SUBAGENT_INBOX_CAPACITY)
            .expect("default subagent inbox capacity must be valid")
    }

    pub fn with_inbox_capacity(inbox_capacity: usize) -> Result<Self, SubagentError> {
        if inbox_capacity == 0 {
            return Err(SubagentError::EmptyInbox);
        }
        Ok(Self {
            entries: Arc::new(Mutex::new(HashMap::new())),
            next_id: Arc::new(AtomicU64::new(1)),
            inbox_capacity,
        })
    }

    pub async fn spawn(&self, task: impl SubagentTask) -> SubagentId {
        let id = SubagentId(format!(
            "subagent-{}",
            self.next_id.fetch_add(1, Ordering::Relaxed)
        ));
        let (inbox, inbox_receiver) = mpsc::channel(self.inbox_capacity);
        let (cancel, cancel_receiver) = watch::channel(false);
        self.entries.lock().await.insert(
            id.clone(),
            SubagentEntry {
                status: SubagentStatus::Running,
                cancel: cancel.clone(),
                inbox: inbox.clone(),
                handle: None,
            },
        );
        let entries = Arc::clone(&self.entries);
        let worker_id = id.clone();
        let handle = tokio::spawn(async move {
            let context = SubagentContext {
                inbox: inbox_receiver,
                cancelled: cancel_receiver.clone(),
            };
            let mut cancellation = cancel_receiver;
            let completion = tokio::select! {
                biased;
                _ = wait_for_cancellation(&mut cancellation) => SubagentCompletion::Cancelled,
                result = Box::new(task).run(context) => match result {
                    Ok(value) => SubagentCompletion::Succeeded(value),
                    Err(SubagentError::Task(error)) => SubagentCompletion::Failed(error),
                    Err(error) => SubagentCompletion::Failed(error.to_string()),
                },
            };
            let status = match &completion {
                SubagentCompletion::Succeeded(_) => SubagentStatus::Succeeded,
                SubagentCompletion::Failed(_) => SubagentStatus::Failed,
                SubagentCompletion::Cancelled => SubagentStatus::Cancelled,
            };
            if let Some(entry) = entries.lock().await.get_mut(&worker_id) {
                entry.status = status;
            }
            completion
        });
        self.entries
            .lock()
            .await
            .get_mut(&id)
            .expect("new subagent must be registered before its task starts")
            .handle = Some(handle);
        id
    }

    pub async fn status(&self, id: &SubagentId) -> Result<SubagentStatus, SubagentError> {
        self.entries
            .lock()
            .await
            .get(id)
            .map(|entry| entry.status)
            .ok_or_else(|| SubagentError::Unknown(id.0.clone()))
    }

    pub async fn message(&self, id: &SubagentId, message: Message) -> Result<(), SubagentError> {
        let inbox = {
            let entries = self.entries.lock().await;
            let entry = entries
                .get(id)
                .ok_or_else(|| SubagentError::Unknown(id.0.clone()))?;
            if entry.status != SubagentStatus::Running {
                return Err(SubagentError::NotRunning(id.0.clone()));
            }
            entry.inbox.clone()
        };
        inbox
            .send(message)
            .await
            .map_err(|_| SubagentError::NotRunning(id.0.clone()))
    }

    pub async fn cancel(&self, id: &SubagentId) -> Result<(), SubagentError> {
        let cancel = {
            let entries = self.entries.lock().await;
            let entry = entries
                .get(id)
                .ok_or_else(|| SubagentError::Unknown(id.0.clone()))?;
            if entry.status != SubagentStatus::Running {
                return Err(SubagentError::NotRunning(id.0.clone()));
            }
            entry.cancel.clone()
        };
        cancel
            .send(true)
            .map_err(|_| SubagentError::NotRunning(id.0.clone()))
    }

    pub async fn collect(&self, id: &SubagentId) -> Result<SubagentCompletion, SubagentError> {
        let handle = {
            let mut entries = self.entries.lock().await;
            let entry = entries
                .get_mut(id)
                .ok_or_else(|| SubagentError::Unknown(id.0.clone()))?;
            entry
                .handle
                .take()
                .ok_or_else(|| SubagentError::AlreadyCollected(id.0.clone()))?
        };
        let completion = handle.await.map_err(|_| SubagentError::Join)?;
        self.entries.lock().await.remove(id);
        Ok(completion)
    }
}

async fn wait_for_cancellation(cancelled: &mut watch::Receiver<bool>) {
    if *cancelled.borrow() {
        return;
    }
    while cancelled.changed().await.is_ok() {
        if *cancelled.borrow() {
            return;
        }
    }
    std::future::pending::<()>().await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tokio::sync::oneshot;

    #[test]
    fn round_trips_v2_runtime_shapes() {
        let input = [
            json!({"type":"init","sessionId":"s","agentControlTools":["spawn_agent"],"runtimeVersion":"2","runtimeCapabilities":["tools"]}),
            json!({"type":"text_delta","requestId":"q","text":"hi"}),
            json!({"type":"tool_use","callId":"c","name":"search","input":{"q":"x"}}),
            json!({"type":"external_surface_tool_result","ownerId":"o","sessionId":"s","runId":"r","attemptId":"a","invocationId":"i","ok":true,"result":"ok"}),
            json!({"type":"cancel_ack","accepted":true,"dispatchAttempted":true,"adapterAcknowledged":true}),
            json!({"type":"result","sessionId":"s","text":"done","terminalStatus":"succeeded"}),
            json!({"type":"subagent_status","runId":"r","status":"completed","mode":"act"}),
        ];
        for value in input {
            let parsed = parse_line(&value.to_string()).expect("fixture must parse");
            let emitted = emit_line(&parsed).expect("fixture must emit");
            assert_eq!(
                serde_json::from_str::<Value>(&emitted).expect("fixture must decode"),
                value
            );
        }
    }

    #[test]
    fn rejects_non_envelopes() {
        assert!(matches!(parse_line("[]"), Err(CodecError::NotObject)));
        assert!(matches!(parse_line("{}"), Err(CodecError::MissingType)));
    }

    #[test]
    fn execution_mode_defaults_fast_and_escalates_for_deep_work() {
        assert_eq!(
            select_execution_mode("summarize this", None),
            ExecutionMode::Fast
        );
        assert_eq!(
            select_execution_mode("implement and test the Rust code", None),
            ExecutionMode::Deep
        );
        assert_eq!(
            select_execution_mode("search files then run tests", None),
            ExecutionMode::Deep
        );
        assert_eq!(
            select_execution_mode("small reply", Some(ExecutionMode::Deep)),
            ExecutionMode::Deep
        );
        assert_eq!(
            select_execution_mode("use deep mode for this", Some(ExecutionMode::Fast)),
            ExecutionMode::Fast
        );
    }

    #[tokio::test]
    async fn fast_subagent_can_receive_messages_and_collect_its_result() {
        let supervisor = SubagentSupervisor::new();
        let id = supervisor
            .spawn(|mut context: SubagentContext| async move {
                let message = context.receive().await.expect("message must arrive");
                Ok(message.fields["text"].clone())
            })
            .await;
        assert_eq!(
            supervisor.status(&id).await.expect("subagent must exist"),
            SubagentStatus::Running
        );
        supervisor
            .message(
                &id,
                Message {
                    kind: "subagent_message".into(),
                    fields: Map::from_iter([(String::from("text"), json!("continue"))]),
                },
            )
            .await
            .expect("message must reach running subagent");
        assert_eq!(
            supervisor.collect(&id).await.expect("result must collect"),
            SubagentCompletion::Succeeded(json!("continue"))
        );
    }

    #[tokio::test]
    async fn cancellation_stops_fast_subagent_and_preserves_terminal_result() {
        let supervisor = SubagentSupervisor::new();
        let (started, started_receiver) = oneshot::channel();
        let id = supervisor
            .spawn(move |mut context: SubagentContext| async move {
                started.send(()).expect("test receiver must await start");
                context.cancelled().await;
                Ok(json!("unexpected"))
            })
            .await;
        started_receiver.await.expect("subagent must start");
        supervisor.cancel(&id).await.expect("cancel must dispatch");
        assert_eq!(
            supervisor
                .collect(&id)
                .await
                .expect("cancelled result must collect"),
            SubagentCompletion::Cancelled
        );
    }

    #[tokio::test]
    async fn supervisor_rejects_messages_after_completion_and_invalid_capacity() {
        assert!(matches!(
            SubagentSupervisor::with_inbox_capacity(0),
            Err(SubagentError::EmptyInbox)
        ));
        let supervisor = SubagentSupervisor::new();
        let id = supervisor
            .spawn(|_: SubagentContext| async { Ok(json!(true)) })
            .await;
        assert_eq!(
            supervisor.collect(&id).await.expect("result must collect"),
            SubagentCompletion::Succeeded(json!(true))
        );
        assert_eq!(
            supervisor
                .message(
                    &id,
                    Message {
                        kind: "subagent_message".into(),
                        fields: Map::new(),
                    },
                )
                .await
                .expect_err("removed subagent must not receive messages"),
            SubagentError::Unknown(id.as_str().into())
        );
    }
}
