use std::{path::PathBuf, process::Stdio, time::Duration};

use serde::Serialize;
use serde_json::{json, Value};
use tauri::AppHandle;
#[cfg(target_os = "windows")]
use tauri::Manager;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    process::Command,
    time::timeout,
};

const HELLO: u8 = 3;
const SNAPSHOT: u8 = 1;
const STEP: u8 = 2;
const TIMEOUT: Duration = Duration::from_secs(8);
const BLOCKED_WINDOWS: [&str; 7] = [
    "windows security",
    "user account control",
    "sign in",
    "lock screen",
    "credential",
    "task manager",
    "omi for windows",
];
const NAMED_KEYS: [&str; 12] = [
    "ENTER",
    "TAB",
    "ESC",
    "BACKSPACE",
    "DELETE",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "HOME",
    "END",
    "SPACE",
];

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AutomationCapabilities {
    supported: bool,
    reason: Option<String>,
}

#[tauri::command]
pub fn automation_capabilities(app: AppHandle) -> AutomationCapabilities {
    match helper_path(&app) {
        Ok(_) => AutomationCapabilities {
            supported: false,
            reason: Some("Desktop automation target tracking is unavailable".into()),
        },
        Err(reason) => AutomationCapabilities {
            supported: false,
            reason: Some(reason),
        },
    }
}

#[tauri::command]
pub async fn automation_target_window() -> Result<Option<String>, String> {
    unsupported()
}

#[tauri::command]
pub async fn automation_snapshot(
    app: AppHandle,
    window_handle: Option<String>,
) -> Result<Value, String> {
    let payload = json!({ "windowHandle": window_handle.unwrap_or_default() });
    let mut responses = request(&app, &[(SNAPSHOT, payload)]).await?;
    responses
        .pop()
        .ok_or_else(|| "automation helper returned no snapshot".into())
}

#[tauri::command]
pub async fn automation_confirm_run(
    app: AppHandle,
    plan: Value,
) -> Result<AutomationRunResult, String> {
    validate_plan(&plan)?;
    let message = dialog_message(&plan)?;
    let dialog_app = app.clone();
    let approved = tokio::task::spawn_blocking(move || {
        dialog_app
            .dialog()
            .message(message)
            .title("Omi — approve action")
            .buttons(MessageDialogButtons::OkCancelCustom(
                "Approve & run".into(),
                "Cancel".into(),
            ))
            .blocking_show()
    })
    .await
    .map_err(|error| error.to_string())?;
    if !approved {
        return Ok(AutomationRunResult {
            ok: false,
            canceled: Some(true),
            message: None,
        });
    }
    let steps = plan
        .get("steps")
        .and_then(Value::as_array)
        .ok_or_else(|| "steps must be an array".to_string())?;
    let requests = steps
        .iter()
        .cloned()
        .map(|step| (STEP, step))
        .collect::<Vec<_>>();
    let responses = request(&app, &requests).await?;
    for (index, response) in responses.into_iter().enumerate() {
        if response.get("ok").and_then(Value::as_bool) != Some(true) {
            return Ok(AutomationRunResult {
                ok: false,
                canceled: None,
                message: Some(
                    response
                        .get("message")
                        .and_then(Value::as_str)
                        .map(str::to_owned)
                        .unwrap_or_else(|| format!("step {} failed", index + 1)),
                ),
            });
        }
    }
    Ok(AutomationRunResult {
        ok: true,
        canceled: None,
        message: None,
    })
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AutomationRunResult {
    ok: bool,
    canceled: Option<bool>,
    message: Option<String>,
}

fn helper_path(app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(target_os = "windows")]
    {
        if std::env::var_os("OMI_AUTOMATION").as_deref() == Some(std::ffi::OsStr::new("0")) {
            return Err("Desktop automation is disabled in this build".into());
        }
        let resource = app
            .path()
            .resource_dir()
            .map_err(|error| error.to_string())?
            .join("win-automation-helper")
            .join("win-automation-helper.exe");
        let development = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../resources/win-automation-helper/win-automation-helper.exe");
        [resource, development]
            .into_iter()
            .find(|path| path.is_file())
            .ok_or_else(|| "Windows UI Automation helper is unavailable".into())
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = app;
        Err("Desktop automation is only supported on Windows".into())
    }
}

async fn request(app: &AppHandle, requests: &[(u8, Value)]) -> Result<Vec<Value>, String> {
    let helper = helper_path(app)?;
    let mut child = Command::new(helper)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    let mut input = child
        .stdin
        .take()
        .ok_or_else(|| "automation helper stdin is unavailable".to_string())?;
    let mut output = child
        .stdout
        .take()
        .ok_or_else(|| "automation helper stdout is unavailable".to_string())?;
    let mut frames = Vec::with_capacity(requests.len() + 1);
    frames.push((HELLO, json!({})));
    frames.extend_from_slice(requests);
    for (opcode, payload) in &frames {
        let bytes = serde_json::to_vec(payload).map_err(|error| error.to_string())?;
        let length =
            u32::try_from(bytes.len() + 1).map_err(|_| "automation request is too large")?;
        input
            .write_all(&length.to_le_bytes())
            .await
            .map_err(|error| error.to_string())?;
        input
            .write_all(&[*opcode])
            .await
            .map_err(|error| error.to_string())?;
        input
            .write_all(&bytes)
            .await
            .map_err(|error| error.to_string())?;
    }
    input.shutdown().await.map_err(|error| error.to_string())?;
    let mut responses = Vec::with_capacity(frames.len());
    for _ in &frames {
        responses.push(
            timeout(TIMEOUT, read_frame(&mut output))
                .await
                .map_err(|_| "automation helper timed out")??,
        );
    }
    timeout(TIMEOUT, child.wait())
        .await
        .map_err(|_| "automation helper did not exit")?
        .map_err(|error| error.to_string())?;
    let hello = responses.remove(0);
    if hello.get("protocolVersion").and_then(Value::as_i64) != Some(1) {
        return Err("Windows UI Automation helper protocol mismatch".into());
    }
    Ok(responses)
}

async fn read_frame(output: &mut tokio::process::ChildStdout) -> Result<Value, String> {
    let mut header = [0; 4];
    output
        .read_exact(&mut header)
        .await
        .map_err(|error| error.to_string())?;
    let length = u32::from_le_bytes(header);
    let length = usize::try_from(length).map_err(|_| "automation response is too large")?;
    let mut body = vec![0; length];
    output
        .read_exact(&mut body)
        .await
        .map_err(|error| error.to_string())?;
    serde_json::from_slice(&body).map_err(|error| error.to_string())
}

fn unsupported<T>() -> Result<T, String> {
    Err(
        "Desktop automation target tracking is unavailable until the Windows helper is active"
            .into(),
    )
}

fn validate_plan(plan: &Value) -> Result<(), String> {
    let target = string(plan, "targetWindow")?;
    if BLOCKED_WINDOWS
        .iter()
        .any(|blocked| target.to_lowercase().contains(blocked))
    {
        return Err(format!("target window \"{target}\" is blocklisted"));
    }
    let steps = plan
        .get("steps")
        .and_then(Value::as_array)
        .ok_or_else(|| "steps must be an array".to_string())?;
    if steps.is_empty() {
        return Err("steps must not be empty".into());
    }
    for (index, step) in steps.iter().enumerate() {
        validate_step(step).map_err(|error| format!("step {index}: {error}"))?;
    }
    Ok(())
}

fn validate_step(step: &Value) -> Result<(), String> {
    match string(step, "type")? {
        "focus_window" => non_empty(step, "windowRef"),
        "invoke_element" | "select_item" | "toggle" => non_empty(step, "elementRef"),
        "set_value" => {
            non_empty(step, "elementRef")?;
            non_empty(step, "value")
        }
        "wait_for" => {
            non_empty(step, "elementRef")?;
            let timeout = step
                .get("timeoutMs")
                .and_then(Value::as_i64)
                .ok_or_else(|| "timeoutMs must be a number".to_string())?;
            (1..=7_000)
                .contains(&timeout)
                .then_some(())
                .ok_or_else(|| "timeoutMs out of range".into())
        }
        "send_keys" => validate_keys(string(step, "keys")?),
        "click" => non_empty(step, "elementRef"),
        other => Err(format!("unknown step type {other}")),
    }
}

fn validate_keys(keys: &str) -> Result<(), String> {
    if keys.trim().is_empty() {
        return Err("keys is empty".into());
    }
    if keys.contains(['^', '%', '+', '#']) {
        return Err("modifier chords are not allowed".into());
    }
    let mut rest = keys;
    while let Some(start) = rest.find('{') {
        let end = rest[start + 1..]
            .find('}')
            .ok_or_else(|| "unbalanced braces in keys".to_string())?
            + start
            + 1;
        let key = &rest[start + 1..end];
        if !NAMED_KEYS.contains(&key) {
            return Err(format!("named key {{{key}}} not allowed"));
        }
        rest = &rest[end + 1..];
    }
    (!rest.contains('}'))
        .then_some(())
        .ok_or_else(|| "unbalanced braces in keys".into())
}

fn non_empty(value: &Value, field: &str) -> Result<(), String> {
    (!string(value, field)?.trim().is_empty())
        .then_some(())
        .ok_or_else(|| format!("{field} is empty"))
}

fn string<'a>(value: &'a Value, field: &str) -> Result<&'a str, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{field} must be a string"))
}

fn dialog_message(plan: &Value) -> Result<String, String> {
    let target = string(plan, "targetWindow")?;
    let summary = string(plan, "summary")?;
    let details = plan
        .get("steps")
        .and_then(Value::as_array)
        .ok_or_else(|| "steps must be an array".to_string())?
        .iter()
        .enumerate()
        .map(|(index, step)| {
            describe_step(step).map(|description| format!("{}. {description}", index + 1))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join("\n");
    Ok(format!("{summary}\n\nIn \"{target}\":\n\n{details}"))
}

fn describe_step(step: &Value) -> Result<&'static str, String> {
    match string(step, "type")? {
        "focus_window" => Ok("Bring the target window to the front"),
        "set_value" => Ok("Type text"),
        "send_keys" => Ok("Press keys"),
        "invoke_element" | "click" => Ok("Click an element"),
        "select_item" => Ok("Select an item"),
        "toggle" => Ok("Change a setting"),
        "wait_for" => Ok("Wait for an element"),
        other => Err(format!("unknown step type {other}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_blocked_targets_and_modifier_chords() {
        assert!(validate_plan(&json!({ "targetWindow": "Windows Security", "steps": [{ "type": "click", "elementRef": "a:ok" }] })).is_err());
        assert!(validate_plan(
            &json!({ "targetWindow": "Mail", "steps": [{ "type": "send_keys", "keys": "^r" }] })
        )
        .is_err());
    }

    #[test]
    fn accepts_a_safe_plan() {
        assert!(validate_plan(&json!({ "targetWindow": "Mail", "steps": [{ "type": "focus_window", "windowRef": "42" }, { "type": "send_keys", "keys": "hello{ENTER}" }] })).is_ok());
    }
}
