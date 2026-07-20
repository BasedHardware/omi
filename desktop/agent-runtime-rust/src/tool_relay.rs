use crate::safety::{inspect_tool_call, ToolKind};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;

pub const MANIFEST_VERSION: u64 = 1;
pub const MANIFEST_DIGEST: &str = "omi-rx4-tools@1";

#[derive(Clone)]
pub struct Identity {
    pub invocation_id: String,
    pub owner_id: String,
    pub session_id: String,
    pub run_id: String,
    pub attempt_id: String,
    pub profile_generation: u64,
    pub daemon_boot_epoch: String,
    pub execution_generation: u64,
}
#[derive(Clone)]
struct Pending {
    identity: Identity,
    input_hash: String,
}
pub struct ToolRelay {
    pending: HashMap<String, Pending>,
    completed: HashMap<String, Value>,
}

impl Default for ToolRelay {
    fn default() -> Self {
        Self::new()
    }
}

impl ToolRelay {
    pub fn new() -> Self {
        Self {
            pending: HashMap::new(),
            completed: HashMap::new(),
        }
    }
    #[allow(clippy::too_many_arguments)]
    pub fn dispatch(
        &mut self,
        identity: Identity,
        tool_name: String,
        input: Map<String, Value>,
        surface_kind: String,
        external_ref_kind: Option<String>,
        external_ref_id: Option<String>,
        run_mode: String,
    ) -> Result<Value, String> {
        if self.pending.contains_key(&identity.invocation_id)
            || self.completed.contains_key(&identity.invocation_id)
        {
            return Err("authorized tool invocation is already known".into());
        }
        if let Some(reason) = inspect(&tool_name, &input) {
            return Err(reason);
        }
        let input_hash = hash_input(&input)?;
        self.pending.insert(
            identity.invocation_id.clone(),
            Pending {
                identity: identity.clone(),
                input_hash: input_hash.clone(),
            },
        );
        Ok(
            json!({"type":"authorized_tool_execution","protocolVersion":2,"invocationId":identity.invocation_id,"ownerId":identity.owner_id,"sessionId":identity.session_id,"runId":identity.run_id,"attemptId":identity.attempt_id,"profileGeneration":identity.profile_generation,"manifestVersion":MANIFEST_VERSION,"manifestDigest":MANIFEST_DIGEST,"daemonBootEpoch":identity.daemon_boot_epoch,"executionGeneration":identity.execution_generation,"toolName":tool_name,"input":input,"inputHash":input_hash,"effectClass":"non_idempotent_write","retryPolicy":"never_auto_retry","surfaceKind":surface_kind,"externalRefKind":external_ref_kind,"externalRefId":external_ref_id,"originatingUserText":"","precedingAssistantText":Value::Null,"runMode":run_mode,"chatMode":Value::Null}),
        )
    }
    pub fn complete(&mut self, result: &Map<String, Value>) -> Result<(Value, bool), String> {
        let invocation_id = string(result, "invocationId")?;
        if let Some(existing) = self.completed.get(&invocation_id) {
            return Ok((existing.clone(), true));
        }
        let pending = self
            .pending
            .get(&invocation_id)
            .ok_or_else(|| "authorized tool result is unknown".to_owned())?;
        validate(pending, result)?;
        let outcome = string(result, "outcome")?;
        if outcome != "succeeded" && outcome != "failed" {
            return Err("authorized tool result outcome is invalid".into());
        }
        let result_text = string(result, "result")?;
        let completion =
            json!({"invocationId":invocation_id,"outcome":outcome,"result":result_text});
        self.pending.remove(&invocation_id);
        self.completed.insert(invocation_id, completion.clone());
        Ok((completion, false))
    }
}
fn inspect(name: &str, input: &Map<String, Value>) -> Option<String> {
    let (kind, value) = match name {
        "bash" | "terminal" => (
            ToolKind::Bash,
            input
                .get("command")
                .and_then(Value::as_str)
                .unwrap_or_default(),
        ),
        "write" | "edit" | "edit_diff" => (
            ToolKind::Write,
            input
                .get("path")
                .or_else(|| input.get("filePath"))
                .and_then(Value::as_str)
                .unwrap_or_default(),
        ),
        _ => (ToolKind::Other, ""),
    };
    inspect_tool_call(kind, value).map(|decision| decision.reason.to_owned())
}
fn hash_input(input: &Map<String, Value>) -> Result<String, String> {
    let bytes = serde_json::to_vec(input).map_err(|error| error.to_string())?;
    Ok(format!("sha256:{:x}", Sha256::digest(bytes)))
}
fn string(fields: &Map<String, Value>, key: &str) -> Result<String, String> {
    fields
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| format!("{key} is required"))
}
fn validate(pending: &Pending, result: &Map<String, Value>) -> Result<(), String> {
    let identity = &pending.identity;
    for (key, expected) in [
        ("ownerId", &identity.owner_id),
        ("sessionId", &identity.session_id),
        ("runId", &identity.run_id),
        ("attemptId", &identity.attempt_id),
        ("daemonBootEpoch", &identity.daemon_boot_epoch),
        ("inputHash", &pending.input_hash),
    ] {
        if string(result, key)? != *expected {
            return Err("authorized tool result identity mismatch".into());
        }
    }
    if result.get("profileGeneration").and_then(Value::as_u64) != Some(identity.profile_generation)
        || result.get("manifestVersion").and_then(Value::as_u64) != Some(MANIFEST_VERSION)
        || result.get("executionGeneration").and_then(Value::as_u64)
            != Some(identity.execution_generation)
        || string(result, "manifestDigest")? != MANIFEST_DIGEST
    {
        return Err("authorized tool result identity mismatch".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn blocks_dangerous_then_accepts_exact_idempotent_result() {
        let mut relay = ToolRelay::new();
        let identity = Identity {
            invocation_id: "i".into(),
            owner_id: "o".into(),
            session_id: "s".into(),
            run_id: "r".into(),
            attempt_id: "a".into(),
            profile_generation: 1,
            daemon_boot_epoch: "b".into(),
            execution_generation: 1,
        };
        assert!(relay
            .dispatch(
                identity.clone(),
                "bash".into(),
                serde_json::from_value(json!({"command":"sudo rm -rf /"})).unwrap_or_default(),
                "main_chat".into(),
                None,
                None,
                "act".into()
            )
            .is_err());
        let dispatch = relay
            .dispatch(
                identity,
                "bash".into(),
                serde_json::from_value(json!({"command":"pwd"})).unwrap_or_default(),
                "main_chat".into(),
                None,
                None,
                "act".into(),
            )
            .unwrap_or_else(|error| panic!("dispatch failed: {error}"));
        let mut result = dispatch.as_object().cloned().unwrap_or_default();
        result.insert("type".into(), json!("authorized_tool_execution_result"));
        result.insert("outcome".into(), json!("succeeded"));
        result.insert("result".into(), json!("ok"));
        result.remove("toolName");
        result.remove("input");
        result.remove("effectClass");
        result.remove("retryPolicy");
        result.remove("surfaceKind");
        result.remove("externalRefKind");
        result.remove("externalRefId");
        result.remove("originatingUserText");
        result.remove("precedingAssistantText");
        result.remove("runMode");
        result.remove("chatMode");
        let (_, duplicate) = relay
            .complete(&result)
            .unwrap_or_else(|error| panic!("completion failed: {error}"));
        assert!(!duplicate);
        let (_, duplicate) = relay
            .complete(&result)
            .unwrap_or_else(|error| panic!("repeat completion failed: {error}"));
        assert!(duplicate);
    }
}
