use std::fs;

use keyring::Entry;
use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

const NOTION_SERVICE: &str = "com.omi.desktop.notion";
const NOTION_ACCOUNT: &str = "integration-token";

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ExportMemory {
    pub content: String,
    pub category: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct MemoryExportResult {
    pub canceled: Option<bool>,
    pub count: usize,
    pub location: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NotionExport {
    pub parent_page_id: String,
    pub memories: Vec<ExportMemory>,
}

fn notion_entry() -> Result<Entry, String> {
    Entry::new(NOTION_SERVICE, NOTION_ACCOUNT).map_err(|error| error.to_string())
}

fn parse_dump(dump: &str) -> Vec<String> {
    let mut memories = Vec::new();
    for line in dump.lines().map(clean_line).filter(|line| !line.is_empty()) {
        if line.len() < 3
            || is_scaffolding(&line)
            || memories
                .iter()
                .any(|item: &String| item.eq_ignore_ascii_case(&line))
        {
            continue;
        }
        memories.push(line);
    }
    memories
}

fn clean_line(line: &str) -> String {
    let line = line.trim();
    if line.starts_with("```") || line.starts_with("~~~") {
        return String::new();
    }
    let line = line
        .trim_start_matches(|character: char| {
            matches!(character, '-' | '*' | '•' | '–' | '—' | '#' | '⁃')
                || character.is_ascii_digit()
                || matches!(character, '.' | ')' | ' ')
        })
        .trim();
    line.trim_matches('*').trim_matches('_').trim().to_owned()
}

fn is_scaffolding(line: &str) -> bool {
    let line = line.to_ascii_lowercase();
    [
        "sure",
        "here",
        "below",
        "these are",
        "saved memories",
        "let me know",
        "that's all",
        "thats all",
        "is there anything",
    ]
    .iter()
    .any(|prefix| line.starts_with(prefix))
}

fn markdown(memories: &[ExportMemory]) -> String {
    let date = chrono_like_date();
    let noun = if memories.len() == 1 {
        "memory"
    } else {
        "memories"
    };
    let mut groups = std::collections::BTreeMap::<String, Vec<&ExportMemory>>::new();
    for memory in memories {
        groups
            .entry(
                memory
                    .category
                    .as_deref()
                    .map(str::trim)
                    .filter(|category| !category.is_empty())
                    .unwrap_or("Other")
                    .to_owned(),
            )
            .or_default()
            .push(memory);
    }
    let mut document = format!(
        "# Omi Memories\n\n_Exported {date} · {} {noun}_\n",
        memories.len()
    );
    for (category, entries) in groups {
        document.push_str(&format!("\n## {category}\n\n"));
        for entry in entries {
            document.push_str("- ");
            document.push_str(
                &entry
                    .content
                    .split_whitespace()
                    .collect::<Vec<_>>()
                    .join(" "),
            );
            document.push('\n');
        }
    }
    document
}

fn chrono_like_date() -> String {
    let seconds = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |duration| duration.as_secs());
    let days = seconds / 86_400;
    let z = days as i64 + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let month_index = (5 * doy + 2) / 153;
    let day = doy - (153 * month_index + 2) / 5 + 1;
    let month = month_index + if month_index < 10 { 3 } else { -9 };
    format!(
        "{:04}-{:02}-{:02}",
        year + i64::from(month <= 2),
        month,
        day
    )
}

fn result(path: Option<std::path::PathBuf>, count: usize) -> MemoryExportResult {
    match path {
        Some(path) => MemoryExportResult {
            canceled: None,
            count,
            location: Some(path.to_string_lossy().into_owned()),
        },
        None => MemoryExportResult {
            canceled: Some(true),
            count: 0,
            location: None,
        },
    }
}

#[tauri::command]
pub fn memory_import_parse(dump: String) -> Vec<String> {
    parse_dump(&dump)
}

#[tauri::command]
pub fn memory_export_obsidian(
    app: AppHandle,
    memories: Vec<ExportMemory>,
) -> Result<MemoryExportResult, String> {
    let folder = app
        .dialog()
        .file()
        .set_title("Choose your Obsidian vault folder")
        .blocking_pick_folder()
        .and_then(|path| path.into_path().ok());
    let Some(folder) = folder else {
        return Ok(result(None, memories.len()));
    };
    let file = folder.join("Omi").join("Memories.md");
    let parent = file.parent().expect("Omi export path has a parent");
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    fs::write(&file, markdown(&memories)).map_err(|error| error.to_string())?;
    Ok(result(Some(file), memories.len()))
}

#[tauri::command]
pub fn memory_export_file(
    app: AppHandle,
    memories: Vec<ExportMemory>,
) -> Result<MemoryExportResult, String> {
    let file = app
        .dialog()
        .file()
        .set_title("Export memories")
        .set_file_name("Omi-Memories.md")
        .add_filter("Markdown", &["md"])
        .blocking_save_file()
        .and_then(|path| path.into_path().ok());
    let Some(file) = file else {
        return Ok(result(None, memories.len()));
    };
    fs::write(&file, markdown(&memories)).map_err(|error| error.to_string())?;
    Ok(result(Some(file), memories.len()))
}

#[tauri::command]
pub async fn memory_export_notion(args: NotionExport) -> Result<MemoryExportResult, String> {
    let client = reqwest::Client::new();
    let token = notion_entry()?
        .get_password()
        .map_err(|_| "Notion token is not connected")?;
    let headers = [
        ("Authorization", format!("Bearer {token}")),
        ("Notion-Version", "2022-06-28".to_owned()),
    ];
    let blocks = args
        .memories
        .iter()
        .take(100)
        .map(notion_block)
        .collect::<Vec<_>>();
    let page = client
        .post("https://api.notion.com/v1/pages")
        .headers(headers.iter().fold(
            reqwest::header::HeaderMap::new(),
            |mut map, (name, value)| {
                map.insert(
                    reqwest::header::HeaderName::from_bytes(name.as_bytes())
                        .expect("constant header"),
                    reqwest::header::HeaderValue::from_str(value).expect("valid header value"),
                );
                map
            },
        ))
        .json(&serde_json::json!({
            "parent": { "page_id": args.parent_page_id },
            "properties": { "title": { "title": [{ "text": { "content": "Omi Memories" } }] } },
            "children": blocks
        }))
        .send()
        .await
        .map_err(|error| error.to_string())?;
    if !page.status().is_success() {
        return Err(format!(
            "Notion create failed ({}): {}",
            page.status(),
            page.text().await.unwrap_or_default()
        ));
    }
    let page = page
        .json::<serde_json::Value>()
        .await
        .map_err(|error| error.to_string())?;
    let id = page
        .get("id")
        .and_then(serde_json::Value::as_str)
        .ok_or("Notion response did not include a page id")?;
    for batch in args.memories[100..].chunks(100) {
        let response = client
            .patch(format!("https://api.notion.com/v1/blocks/{id}/children"))
            .headers(headers.iter().fold(reqwest::header::HeaderMap::new(), |mut map, (name, value)| {
                map.insert(reqwest::header::HeaderName::from_bytes(name.as_bytes()).expect("constant header"), reqwest::header::HeaderValue::from_str(value).expect("valid header value"));
                map
            }))
            .json(&serde_json::json!({ "children": batch.iter().map(notion_block).collect::<Vec<_>>() }))
            .send()
            .await
            .map_err(|error| error.to_string())?;
        if !response.status().is_success() {
            return Err(format!(
                "Notion append failed ({}): {}",
                response.status(),
                response.text().await.unwrap_or_default()
            ));
        }
    }
    Ok(MemoryExportResult {
        canceled: None,
        count: args.memories.len(),
        location: Some(
            page.get("url")
                .and_then(serde_json::Value::as_str)
                .map_or_else(
                    || format!("https://notion.so/{}", id.replace('-', "")),
                    ToOwned::to_owned,
                ),
        ),
    })
}

#[tauri::command]
pub fn notion_set_token(token: String) -> Result<(), String> {
    let token = token.trim();
    if token.is_empty() {
        return Err("Notion token is required".into());
    }
    notion_entry()?
        .set_password(token)
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn notion_clear_token() -> Result<(), String> {
    match notion_entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

fn notion_block(memory: &ExportMemory) -> serde_json::Value {
    serde_json::json!({
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": { "rich_text": [{ "type": "text", "text": { "content": memory.content.chars().take(2_000).collect::<String>() } }] }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_deduplicates_memory_dumps() {
        assert_eq!(
            parse_dump("Sure!\n- Has cats\n1. Has cats\n- Prefers Rust"),
            ["Has cats", "Prefers Rust"]
        );
    }

    #[test]
    fn renders_markdown_by_category() {
        assert!(markdown(&[ExportMemory {
            content: "Uses Rust".into(),
            category: Some("Work".into()),
            created_at: None
        }])
        .contains("## Work\n\n- Uses Rust"));
    }
}
