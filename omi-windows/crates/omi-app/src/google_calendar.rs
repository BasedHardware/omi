use std::ptr;
use std::ffi::c_void;
use std::path::{Path, PathBuf};
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Nonce,
};
use sha1::{Sha1, Digest};

// ── Windows DPAPI FFI ─────────────────────────────────────────────────────────

#[allow(non_snake_case)]
#[repr(C)]
struct DATA_BLOB {
    cbData: u32,
    pbData: *mut u8,
}

#[link(name = "crypt32")]
extern "system" {
    fn CryptUnprotectData(
        pDataIn: *mut DATA_BLOB,
        ppszDataDescr: *mut *mut u16,
        pOptionalEntropy: *mut DATA_BLOB,
        pvReserved: *mut c_void,
        pPromptStruct: *mut c_void,
        dwFlags: u32,
        pDataOut: *mut DATA_BLOB,
    ) -> i32;
}

#[link(name = "kernel32")]
extern "system" {
    fn LocalFree(hMem: *mut c_void) -> *mut c_void;
}

fn dpapi_decrypt(encrypted: &[u8]) -> Result<Vec<u8>> {
    let mut data_in = DATA_BLOB {
        cbData: encrypted.len() as u32,
        pbData: encrypted.as_ptr() as *mut u8,
    };
    let mut data_out = DATA_BLOB {
        cbData: 0,
        pbData: ptr::null_mut(),
    };
    unsafe {
        let success = CryptUnprotectData(
            &mut data_in,
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
            0,
            &mut data_out,
        );
        if success == 0 {
            return Err(anyhow::anyhow!(
                "CryptUnprotectData failed. OS Error: {}",
                std::io::Error::last_os_error()
            ));
        }
        let bytes = std::slice::from_raw_parts(data_out.pbData, data_out.cbData as usize).to_vec();
        LocalFree(data_out.pbData as *mut c_void);
        Ok(bytes)
    }
}

// ── Master Key & Cookie Extraction ────────────────────────────────────────────

#[derive(Deserialize)]
struct LocalStateOsCrypt {
    encrypted_key: String,
}

#[derive(Deserialize)]
struct LocalStateJson {
    os_crypt: LocalStateOsCrypt,
}

fn get_master_key(local_state_path: &Path) -> Result<Vec<u8>> {
    let content = std::fs::read_to_string(local_state_path)
        .context("Failed to read Local State file")?;
    let state: LocalStateJson = serde_json::from_str(&content)
        .context("Failed to parse Local State JSON")?;
    
    use base64::{Engine as _, engine::general_purpose::STANDARD};
    let decoded_key = STANDARD.decode(&state.os_crypt.encrypted_key)
        .context("Failed to base64 decode encrypted_key")?;
    
    if !decoded_key.starts_with(b"DPAPI") {
        return Err(anyhow::anyhow!("Encrypted key does not start with 'DPAPI'"));
    }
    
    let encrypted_bytes = &decoded_key[5..];
    let decrypted_key = dpapi_decrypt(encrypted_bytes)?;
    Ok(decrypted_key)
}

fn decrypt_cookie_value(encrypted_value: &[u8], master_key: &[u8]) -> Result<String> {
    if encrypted_value.len() < 3 + 12 {
        return Err(anyhow::anyhow!("Encrypted value too short"));
    }
    let prefix = &encrypted_value[0..3];
    if prefix != b"v10" && prefix != b"v11" {
        return Err(anyhow::anyhow!("Unsupported cookie prefix: {:?}", prefix));
    }
    let iv = &encrypted_value[3..15];
    let ciphertext = &encrypted_value[15..];
    
    let key = aes_gcm::Key::<Aes256Gcm>::from_slice(master_key);
    let cipher = Aes256Gcm::new(key);
    let nonce = Nonce::from_slice(iv);
    
    let decrypted_bytes = cipher
        .decrypt(nonce, ciphertext)
        .map_err(|e| anyhow::anyhow!("AES-GCM decryption failed: {}", e))?;
    
    let val = String::from_utf8(decrypted_bytes)?;
    Ok(val)
}

#[derive(Debug)]
struct GoogleCookies {
    sapisid: String,
    sid: Option<String>,
    hsid: Option<String>,
    ssid: Option<String>,
    apisid: Option<String>,
}

fn get_google_cookies(cookies_path: &Path, master_key: &[u8]) -> Result<GoogleCookies> {
    // Copy to temporary file to bypass file lock if browser is running
    let temp_dir = std::env::temp_dir();
    let temp_path = temp_dir.join(format!("omi_cookies_{}.db", uuid::Uuid::new_v4()));
    std::fs::copy(cookies_path, &temp_path)
        .context("Failed to copy cookies database to temp file")?;
        
    let cookies = {
        let conn = rusqlite::Connection::open(&temp_path)
            .context("Failed to open temp cookies SQLite database")?;
            
        let mut stmt = conn.prepare(
            "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%google.com'"
        )?;
        
        let mut sapisid = None;
        let mut sid = None;
        let mut hsid = None;
        let mut ssid = None;
        let mut apisid = None;
        
        let mut rows = stmt.query([])?;
        while let Some(row) = rows.next()? {
            let name: String = row.get(0)?;
            let encrypted_value: Vec<u8> = row.get(1)?;
            
            if let Ok(decrypted) = decrypt_cookie_value(&encrypted_value, master_key) {
                match name.as_str() {
                    "SAPISID" => sapisid = Some(decrypted),
                    "SID" => sid = Some(decrypted),
                    "HSID" => hsid = Some(decrypted),
                    "SSID" => ssid = Some(decrypted),
                    "APISID" => apisid = Some(decrypted),
                    _ => {}
                }
            }
        }
        
        let sapisid = sapisid.ok_or_else(|| anyhow::anyhow!("SAPISID cookie not found"))?;
        
        GoogleCookies {
            sapisid,
            sid,
            hsid,
            ssid,
            apisid,
        }
    };
    
    // Clean up temp file
    let _ = std::fs::remove_file(&temp_path);
    
    Ok(cookies)
}

fn find_browser_paths(browser_name: &str) -> Option<(PathBuf, PathBuf)> {
    let user_profile = std::env::var("USERPROFILE").ok()?;
    let path = PathBuf::from(user_profile);
    
    match browser_name {
        "chrome" => {
            let base = path.join("AppData\\Local\\Google\\Chrome\\User Data");
            let local_state = base.join("Local State");
            let cookies = base.join("Default\\Network\\Cookies");
            Some((local_state, cookies))
        }
        "edge" => {
            let base = path.join("AppData\\Local\\Microsoft\\Edge\\User Data");
            let local_state = base.join("Local State");
            let cookies = base.join("Default\\Network\\Cookies");
            Some((local_state, cookies))
        }
        "brave" => {
            let base = path.join("AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data");
            let local_state = base.join("Local State");
            let cookies = base.join("Default\\Network\\Cookies");
            Some((local_state, cookies))
        }
        _ => None,
    }
}

fn extract_google_cookies() -> Result<GoogleCookies> {
    let browsers = ["chrome", "edge", "brave"];
    let mut last_err = anyhow::anyhow!("No browser paths found");
    
    for browser in &browsers {
        if let Some((local_state_path, cookies_path)) = find_browser_paths(browser) {
            if local_state_path.exists() && cookies_path.exists() {
                match get_master_key(&local_state_path) {
                    Ok(master_key) => {
                        match get_google_cookies(&cookies_path, &master_key) {
                            Ok(cookies) => {
                                tracing::info!("[CALENDAR] Extracted cookies from {}", browser);
                                return Ok(cookies);
                            }
                            Err(e) => {
                                last_err = anyhow::anyhow!("Failed to read cookies from {}: {}", browser, e);
                            }
                        }
                    }
                    Err(e) => {
                        last_err = anyhow::anyhow!("Failed to decrypt master key for {}: {}", browser, e);
                    }
                }
            }
        }
    }
    Err(last_err)
}

// ── Google Calendar API Integration ───────────────────────────────────────────

#[derive(Deserialize, Debug)]
struct CalendarEventsResponse {
    items: Option<Vec<CalendarEvent>>,
}

#[derive(Deserialize, Serialize, Debug, Clone)]
pub struct CalendarEvent {
    pub summary: Option<String>,
    pub description: Option<String>,
    pub start: Option<EventTime>,
    #[serde(rename = "end")]
    pub end_time: Option<EventTime>,
}

#[derive(Deserialize, Serialize, Debug, Clone)]
pub struct EventTime {
    #[serde(rename = "dateTime")]
    pub date_time: Option<String>,
    pub date: Option<String>,
}

pub fn compute_sapisid_hash(sapisid: &str, origin: &str) -> String {
    let timestamp_secs = chrono::Utc::now().timestamp();
    let sapisid_hash_input = format!("{} {} {}", timestamp_secs, sapisid, origin);
    
    let mut hasher = Sha1::new();
    hasher.update(sapisid_hash_input.as_bytes());
    let result = hasher.finalize();
    let signature = result.iter().map(|b| format!("{:02x}", b)).collect::<String>();
    
    format!("{}_{}", timestamp_secs, signature)
}

pub async fn fetch_calendar_events() -> Result<Vec<CalendarEvent>> {
    let cookies = extract_google_cookies()?;
    let origin = "https://calendar.google.com";
    let hash = compute_sapisid_hash(&cookies.sapisid, origin);
    
    let now = chrono::Utc::now();
    let three_days_seconds = 3 * 24 * 3600;
    let seven_days_seconds = 7 * 24 * 3600;
    let time_min = (now - chrono::Duration::seconds(three_days_seconds)).to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    let time_max = (now + chrono::Duration::seconds(seven_days_seconds)).to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    
    let url = format!(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin={}&timeMax={}&singleEvents=true&orderBy=startTime",
        urlencoding::encode(&time_min),
        urlencoding::encode(&time_max)
    );
    
    let mut cookie_header = format!("SAPISID={}", cookies.sapisid);
    if let Some(ref sid) = cookies.sid {
        cookie_header.push_str(&format!("; SID={}", sid));
    }
    if let Some(ref hsid) = cookies.hsid {
        cookie_header.push_str(&format!("; HSID={}", hsid));
    }
    if let Some(ref ssid) = cookies.ssid {
        cookie_header.push_str(&format!("; SSID={}", ssid));
    }
    if let Some(ref apisid) = cookies.apisid {
        cookie_header.push_str(&format!("; APISID={}", apisid));
    }
    
    let client = reqwest::Client::new();
    let resp = client.get(&url)
        .header("Authorization", format!("SAPISIDHASH {}", hash))
        .header("Cookie", cookie_header)
        .header("Origin", origin)
        .header("Referer", "https://calendar.google.com/")
        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        .send()
        .await
        .context("Failed to send request to Google Calendar API")?;
        
    let status = resp.status();
    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(anyhow::anyhow!("Google Calendar API returned error {}: {}", status, body));
    }
    
    let data: CalendarEventsResponse = resp.json()
        .await
        .context("Failed to parse Google Calendar API JSON response")?;
        
    Ok(data.items.unwrap_or_default())
}

// ── LLM Synthesis & DB Integration ────────────────────────────────────────────

#[derive(Deserialize, Serialize, Debug)]
struct LlmSyncResponse {
    memories: Vec<LlmSyncMemory>,
    action_items: Vec<String>,
}

#[derive(Deserialize, Serialize, Debug)]
struct LlmSyncMemory {
    content: String,
    category: Option<String>,
}

pub async fn sync_google_calendar(
    db: &omi_db::Database,
    cfg: &crate::config::AppConfig,
) -> Result<(usize, usize)> {
    tracing::info!("[CALENDAR] Fetching calendar events...");
    let events = fetch_calendar_events().await?;
    
    if events.is_empty() {
        tracing::info!("[CALENDAR] No calendar events found in range.");
        return Ok((0, 0));
    }
    
    let mut events_text = String::new();
    for event in &events {
        let summary = event.summary.as_deref().unwrap_or("Untitled Event");
        let desc = event.description.as_deref().unwrap_or("No description");
        let start = event.start.as_ref()
            .and_then(|s| s.date_time.as_ref().or(s.date.as_ref()))
            .map(|s| s.as_str())
            .unwrap_or("Unknown Time");
        events_text.push_str(&format!(
            "Event: {}\nTime: {}\nDescription: {}\n\n",
            summary, start, desc
        ));
    }
    
    tracing::info!(
        "[CALENDAR] Found {} events. Querying LLM for memory/task extraction...",
        events.len()
    );
    
    let system_prompt = "You are Omi, a background calendar synchronization agent.\n\
        Analyze the user's upcoming Google Calendar events and extract key memories (important events, facts, relationships to remember) and action items (specific tasks, preparation work, or follow-ups).\n\
        Provide output strictly as a JSON object with this schema:\n\
        {\n\
          \"memories\": [\n\
            { \"content\": \"Memory content here\", \"category\": \"calendar\" }\n\
          ],\n\
          \"action_items\": [\n\
            \"Action item description here\"\n\
          ]\n\
        }\n\
        Do not include any other text, markdown blocks, or formatting. Output only valid JSON.";
        
    let user_prompt = format!("Here are my calendar events:\n\n{}", events_text);
    
    let messages = vec![
        crate::llm::LlmMessage {
            role: "system".into(),
            content: system_prompt.into(),
        },
        crate::llm::LlmMessage {
            role: "user".into(),
            content: user_prompt.into(),
        },
    ];
    
    let response = crate::llm::complete_for(cfg, crate::llm::LlmUseCase::Background, messages, None).await?;
    
    let clean_response = if let Some(start_idx) = response.find('{') {
        if let Some(end_idx) = response.rfind('}') {
            &response[start_idx..=end_idx]
        } else {
            &response
        }
    } else {
        &response
    };
    
    let sync_res: LlmSyncResponse = serde_json::from_str(clean_response)
        .context("Failed to parse LLM sync output as JSON")?;
        
    let mut memories_added = 0;
    for mem in sync_res.memories {
        let content = mem.content.trim();
        if content.is_empty() {
            continue;
        }
        let similar = db.find_similar_memories(content, 0.7)?;
        if similar.is_empty() {
            db.insert_memory(None, content, Some(mem.category.as_deref().unwrap_or("calendar")))?;
            memories_added += 1;
        }
    }
    
    let mut tasks_added = 0;
    for item in sync_res.action_items {
        let content = item.trim();
        if content.is_empty() {
            continue;
        }
        if !db.has_similar_action_item(content, 0.7)? {
            db.insert_action_item(None, content)?;
            tasks_added += 1;
        }
    }
    
    tracing::info!(
        "[CALENDAR] Sync complete. Added {} memories and {} tasks.",
        memories_added,
        tasks_added
    );
    
    Ok((memories_added, tasks_added))
}
