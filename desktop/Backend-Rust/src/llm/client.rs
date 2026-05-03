// LLM Client - Gemini API integration
// Port from Python backend (llm.py)

use serde::de::DeserializeOwned;

/// Attempt to repair truncated JSON from Gemini and deserialize it.
/// Gemini sometimes hits max_output_tokens and returns incomplete JSON.
/// This tries progressively more aggressive repairs:
/// 1. Parse as-is
/// 2. Close open strings and add missing braces/brackets
fn parse_or_repair_json<T: DeserializeOwned>(response: &str, label: &str) -> Result<T, String> {
    // 1. Try parsing as-is
    if let Ok(result) = serde_json::from_str::<T>(response) {
        return Ok(result);
    }

    // 2. Try closing truncated JSON by balancing braces/brackets
    let trimmed = response.trim();
    if !trimmed.is_empty() {
        // Count open/close delimiters
        let mut in_string = false;
        let mut escape_next = false;
        let mut stack: Vec<char> = Vec::new();
        let mut last_was_string_content = false;

        for ch in trimmed.chars() {
            if escape_next {
                escape_next = false;
                continue;
            }
            if ch == '\\' && in_string {
                escape_next = true;
                continue;
            }
            if ch == '"' {
                in_string = !in_string;
                last_was_string_content = false;
                continue;
            }
            if in_string {
                last_was_string_content = true;
                continue;
            }
            last_was_string_content = false;
            match ch {
                '{' => stack.push('}'),
                '[' => stack.push(']'),
                '}' | ']' => { stack.pop(); }
                _ => {}
            }
        }

        // Build repair suffix
        let mut suffix = String::new();

        // If we ended inside a string, close it
        if in_string {
            suffix.push('"');
        }

        // Close any open braces/brackets in reverse order
        for closer in stack.iter().rev() {
            suffix.push(*closer);
        }

        if !suffix.is_empty() {
            let repaired = format!("{}{}", trimmed, suffix);
            if let Ok(result) = serde_json::from_str::<T>(&repaired) {
                tracing::info!("Repaired truncated {} JSON (added {:?})", label, suffix);
                return Ok(result);
            }
        }
    }

    Err(format!(
        "Failed to parse {} response: {} - {}",
        label,
        serde_json::from_str::<serde_json::Value>(response)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_else(|| "type mismatch".to_string()),
        response
    ))
}

