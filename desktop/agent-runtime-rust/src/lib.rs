use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use thiserror::Error;

pub mod safety;

pub mod provider_policy;

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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

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
}
