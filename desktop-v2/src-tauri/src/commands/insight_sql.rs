//! Read-only SQL execution against the Rewind screenshots database for the
//! InsightAssistant. Mirrors the safe surface defined in Swift's
//! `ChatToolExecutor.executeSQL`, but scoped to SELECT-only queries against
//! the `screenshots` table.
//!
//! Opened in read-only mode on every call (no shared mutable state). The
//! screenshots DB is written to by the screen-capture plugin — we don't
//! want to race with inserts or accidentally hold a write lock.
//!
//! Safe surface:
//! - SELECT only, max 500 chars
//! - blocked keywords: INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/DETACH/
//!   PRAGMA/VACUUM/REPLACE/UNION/JOIN/WITH
//! - no multi-statement (`;` followed by non-whitespace)
//! - only the `screenshots` table
//! - auto-append `LIMIT 50` if no LIMIT
//! - `busy_timeout = 5000`
//! - ocr_text cells truncated to 200 chars
//! - payload capped at 8 KB

use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use tauri::{command, AppHandle, Manager};

const MAX_QUERY_LEN: usize = 500;
const MAX_PAYLOAD_BYTES: usize = 8 * 1024;
const OCR_TRUNCATE: usize = 200;
const DEFAULT_LIMIT: i64 = 50;

/// Blocked keywords. Case-insensitive, matched at word boundaries.
/// `WITH` is matched specifically as a CTE opener (`WITH ` with trailing
/// space) so we don't reject `GROUP_CONCAT` or other unrelated tokens.
const BLOCKED_WORDS: &[&str] = &[
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REPLACE", "UNION", "JOIN",
];

#[derive(Debug, Serialize)]
struct SqlResponse {
    columns: Vec<String>,
    rows: Vec<Vec<serde_json::Value>>,
    truncated: bool,
}

fn word_boundary_contains(upper: &str, word: &str) -> bool {
    let bytes = upper.as_bytes();
    let wbytes = word.as_bytes();
    let mut i = 0;
    while let Some(pos) = upper[i..].find(word) {
        let start = i + pos;
        let end = start + wbytes.len();
        let before_ok = start == 0 || !is_word_char(bytes[start - 1]);
        let after_ok = end >= bytes.len() || !is_word_char(bytes[end]);
        if before_ok && after_ok {
            return true;
        }
        i = start + 1;
        if i >= upper.len() {
            break;
        }
    }
    false
}

fn is_word_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// Reject multi-statement queries: a `;` followed by any non-whitespace.
fn has_multiple_statements(query: &str) -> bool {
    let mut seen_semi = false;
    for ch in query.chars() {
        if seen_semi {
            if !ch.is_whitespace() {
                return true;
            }
        } else if ch == ';' {
            seen_semi = true;
        }
    }
    false
}

/// Extract table names following `FROM` and reject anything that isn't
/// `screenshots`. Subqueries nest `FROM screenshots` too, which is fine.
fn references_only_screenshots(upper: &str) -> bool {
    let bytes = upper.as_bytes();
    let mut i = 0;
    while let Some(pos) = upper[i..].find("FROM") {
        let start = i + pos;
        let end = start + 4;
        let before_ok = start == 0 || !is_word_char(bytes[start - 1]);
        let after_ok = end < bytes.len() && !is_word_char(bytes[end]);
        if before_ok && after_ok {
            // Skip whitespace after FROM
            let mut j = end;
            while j < bytes.len() && bytes[j].is_ascii_whitespace() {
                j += 1;
            }
            // Read the table token (alphanumeric + underscore)
            let tok_start = j;
            while j < bytes.len() && (is_word_char(bytes[j]) || bytes[j] == b'.') {
                j += 1;
            }
            let token = &upper[tok_start..j];
            if !token.is_empty() && token != "SCREENSHOTS" {
                return false;
            }
        }
        i = start + 1;
        if i >= upper.len() {
            break;
        }
    }
    true
}

fn append_limit_if_missing(query: &str) -> String {
    let upper = query.to_uppercase();
    if word_boundary_contains(&upper, "LIMIT") {
        return query.to_string();
    }
    let trimmed = query.trim_end_matches(|c: char| c.is_whitespace() || c == ';');
    format!("{} LIMIT {}", trimmed, DEFAULT_LIMIT)
}

fn rewind_db_path(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir: {}", e))?;
    Ok(data_dir.join("rewind").join("rewind.db"))
}

fn value_to_json(value: rusqlite::types::ValueRef<'_>, column: &str) -> serde_json::Value {
    use rusqlite::types::ValueRef;
    match value {
        ValueRef::Null => serde_json::Value::Null,
        ValueRef::Integer(i) => serde_json::Value::from(i),
        ValueRef::Real(f) => serde_json::json!(f),
        ValueRef::Text(t) => {
            let s = String::from_utf8_lossy(t).to_string();
            let capped = if column.eq_ignore_ascii_case("ocr_text") && s.len() > OCR_TRUNCATE {
                format!("{}...", &s[..OCR_TRUNCATE])
            } else {
                s
            };
            serde_json::Value::String(capped)
        }
        ValueRef::Blob(b) => serde_json::Value::String(format!("<{} bytes>", b.len())),
    }
}

#[command]
pub async fn execute_insight_sql(app: AppHandle, query: String) -> Result<String, String> {
    let trimmed = query.trim().to_string();
    if trimmed.is_empty() {
        return Ok("REJECTED: empty query".into());
    }
    if trimmed.len() > MAX_QUERY_LEN {
        return Ok(format!(
            "REJECTED: query exceeds {} chars (got {})",
            MAX_QUERY_LEN,
            trimmed.len()
        ));
    }
    let upper = trimmed.to_uppercase();
    if !upper.starts_with("SELECT") {
        return Ok("REJECTED: only SELECT queries are allowed".into());
    }
    for kw in BLOCKED_WORDS {
        if word_boundary_contains(&upper, kw) {
            return Ok(format!("REJECTED: keyword '{}' is not allowed", kw));
        }
    }
    // Specifically reject CTE (`WITH `). A space-suffixed check avoids false
    // positives on function names that happen to contain "WITH".
    if upper.contains("WITH ") {
        // Ensure the match is at a word boundary to avoid false positives.
        let bytes = upper.as_bytes();
        let mut i = 0;
        while let Some(pos) = upper[i..].find("WITH ") {
            let start = i + pos;
            let before_ok = start == 0 || !is_word_char(bytes[start - 1]);
            if before_ok {
                return Ok("REJECTED: keyword 'WITH' is not allowed".into());
            }
            i = start + 1;
        }
    }
    if has_multiple_statements(&trimmed) {
        return Ok("REJECTED: multi-statement queries are not allowed".into());
    }
    if !references_only_screenshots(&upper) {
        return Ok("REJECTED: only the 'screenshots' table is allowed".into());
    }

    let final_query = append_limit_if_missing(&trimmed);
    let db_path = rewind_db_path(&app)?;

    let result = tokio::task::spawn_blocking(move || -> Result<SqlResponse, String> {
        let flags = OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX;
        let conn = Connection::open_with_flags(&db_path, flags)
            .map_err(|e| format!("open rewind.db: {}", e))?;
        conn.busy_timeout(std::time::Duration::from_millis(5_000))
            .map_err(|e| format!("busy_timeout: {}", e))?;

        let mut stmt = conn
            .prepare(&final_query)
            .map_err(|e| format!("prepare: {}", e))?;
        let columns: Vec<String> = stmt.column_names().iter().map(|s| s.to_string()).collect();
        let col_count = columns.len();

        let mut rows_out: Vec<Vec<serde_json::Value>> = Vec::new();
        let mut rows = stmt.query([]).map_err(|e| format!("query: {}", e))?;
        while let Some(row) = rows.next().map_err(|e| format!("row: {}", e))? {
            let mut record = Vec::with_capacity(col_count);
            for idx in 0..col_count {
                let vref = row
                    .get_ref(idx)
                    .map_err(|e| format!("get_ref {}: {}", idx, e))?;
                record.push(value_to_json(vref, &columns[idx]));
            }
            rows_out.push(record);
        }

        Ok(SqlResponse {
            columns,
            rows: rows_out,
            truncated: false,
        })
    })
    .await
    .map_err(|e| format!("insight_sql task panicked: {}", e))??;

    let serialized = serde_json::to_string(&result)
        .map_err(|e| format!("serialize: {}", e))?;

    if serialized.len() > MAX_PAYLOAD_BYTES {
        // Truncate rows until payload fits; keep at least the columns header.
        let mut truncated = SqlResponse {
            columns: result.columns,
            rows: Vec::new(),
            truncated: true,
        };
        for row in result.rows.into_iter() {
            truncated.rows.push(row);
            let candidate = serde_json::to_string(&truncated)
                .map_err(|e| format!("serialize: {}", e))?;
            if candidate.len() > MAX_PAYLOAD_BYTES {
                truncated.rows.pop();
                break;
            }
        }
        let mut out = serde_json::to_string(&truncated)
            .map_err(|e| format!("serialize: {}", e))?;
        out.push_str("...truncated");
        return Ok(out);
    }

    Ok(serialized)
}
