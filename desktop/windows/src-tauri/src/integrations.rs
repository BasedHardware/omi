use std::{
    collections::{BTreeMap, HashSet},
    fs,
    sync::Mutex,
};

use crate::native;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use keyring::Entry;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;
use time::{
    format_description::well_known::Rfc3339, Date, Month, OffsetDateTime, PrimitiveDateTime, Time,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    time::{timeout, Duration},
};

const KEYRING_SERVICE: &str = "com.omi.desktop.google";
const KEYRING_ACCOUNT: &str = "refresh-token";
const AUTH_URL: &str = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL: &str = "https://oauth2.googleapis.com/token";
const GMAIL_URL: &str = "https://gmail.googleapis.com/gmail/v1/users/me";
const CALENDAR_URL: &str = "https://www.googleapis.com/calendar/v3";
const OMI_AUTH_URL: &str = "https://api.omi.me/v1/auth/authorize";
const OMI_TOKEN_URL: &str = "https://api.omi.me/v1/auth/token";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GoogleStatus {
    pub connected: bool,
    pub email: Option<String>,
    pub last_sync_at: Option<i64>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct GmailItem {
    pub id: String,
    pub subject: String,
    pub from: String,
    pub snippet: String,
    #[serde(rename = "internalDateMs")]
    pub internal_date_ms: i64,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CalendarItem {
    pub id: String,
    pub title: String,
    pub start_ms: i64,
    pub end_ms: i64,
    pub location: Option<String>,
    pub description: Option<String>,
    pub updated_ms: i64,
}
#[derive(Clone, Debug, Serialize)]
pub struct FetchResult<T> {
    pub ok: bool,
    pub items: Vec<T>,
    pub error: Option<String>,
}
#[derive(Clone, Debug, Serialize)]
pub struct StickyNotesResult {
    pub available: bool,
    pub notes: Vec<serde_json::Value>,
    pub error: Option<String>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
struct Grant {
    refresh_token: String,
    email: String,
}
#[derive(Clone, Debug, Deserialize)]
struct Token {
    access_token: String,
    refresh_token: Option<String>,
    expires_in: i64,
}
#[derive(Deserialize)]
struct DesktopAuthToken {
    custom_token: String,
}
pub struct GoogleRuntime(Mutex<Option<(String, i64)>>);
impl Default for GoogleRuntime {
    fn default() -> Self {
        Self(Mutex::new(None))
    }
}

fn entry() -> Result<Entry, String> {
    Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|error| error.to_string())
}
fn grant() -> Result<Option<Grant>, String> {
    match entry()?.get_password() {
        Ok(value) => serde_json::from_str(&value)
            .map(Some)
            .map_err(|error| format!("invalid saved Google connection: {error}")),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(format!("could not read saved Google connection: {error}")),
    }
}
fn client_id() -> Result<String, String> {
    std::env::var("OMI_GOOGLE_CLIENT_ID")
        .or_else(|_| std::env::var("GOOGLE_CLIENT_ID"))
        .map_err(|_| "Google OAuth is not configured in this build".into())
}
fn client_secret() -> Option<String> {
    std::env::var("OMI_GOOGLE_CLIENT_SECRET")
        .ok()
        .or_else(|| std::env::var("GOOGLE_CLIENT_SECRET").ok())
}
fn random() -> Result<String, String> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|error| error.to_string())?;
    Ok(URL_SAFE_NO_PAD.encode(bytes))
}
fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |value| value.as_millis().try_into().unwrap_or(i64::MAX))
}
fn sync_file() -> Result<std::path::PathBuf, String> {
    Ok(native::data_root()
        .map_err(|error| error.to_string())?
        .join("google-sync.json"))
}
fn processed(source: &str) -> Result<Vec<String>, String> {
    let file = sync_file()?;
    let value = match fs::read(file) {
        Ok(bytes) => serde_json::from_slice(&bytes)
            .map_err(|error| format!("invalid Google sync state: {error}"))?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => serde_json::Value::default(),
        Err(error) => return Err(format!("could not read Google sync state: {error}")),
    };
    Ok(value
        .get(source)
        .and_then(|value| value.get("processedIds"))
        .and_then(serde_json::Value::as_array)
        .map(|ids| {
            ids.iter()
                .filter_map(|id| id.as_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default())
}
fn mark(source: &str, ids: Vec<String>) -> Result<(), String> {
    let file = sync_file()?;
    let mut value = match fs::read(&file) {
        Ok(bytes) => serde_json::from_slice(&bytes)
            .map_err(|error| format!("invalid Google sync state: {error}"))?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => serde_json::json!({}),
        Err(error) => return Err(format!("could not read Google sync state: {error}")),
    };
    let mut all = processed(source)?;
    all.extend(ids);
    all.dedup();
    if all.len() > 1000 {
        all = all.split_off(all.len() - 1000);
    }
    value[source] = serde_json::json!({ "lastSyncAt": now_ms(), "processedIds": all });
    fs::write(
        file,
        serde_json::to_vec(&value).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

async fn access(runtime: &GoogleRuntime) -> Result<String, String> {
    if let Some((token, expiry)) = runtime
        .0
        .lock()
        .map_err(|error| error.to_string())?
        .as_ref()
    {
        if now_ms() < *expiry {
            return Ok(token.clone());
        }
    }
    let grant = grant()?.ok_or("not_connected")?;
    let mut form = vec![
        ("client_id", client_id()?),
        ("refresh_token", grant.refresh_token),
        ("grant_type", "refresh_token".into()),
    ];
    if let Some(secret) = client_secret() {
        form.push(("client_secret", secret));
    }
    let token = reqwest::Client::new()
        .post(TOKEN_URL)
        .form(&form)
        .send()
        .await
        .map_err(|error| error.to_string())?;
    if !token.status().is_success() {
        return Err(format!("Token refresh failed: {}", token.status()));
    }
    let token = token
        .json::<Token>()
        .await
        .map_err(|error| error.to_string())?;
    *runtime.0.lock().map_err(|error| error.to_string())? = Some((
        token.access_token.clone(),
        now_ms() + token.expires_in * 1000,
    ));
    Ok(token.access_token)
}

async fn callback(listener: TcpListener, state: String) -> Result<(String, String), String> {
    let (mut stream, _) = timeout(Duration::from_secs(300), listener.accept())
        .await
        .map_err(|_| "Timed out waiting for Google authorization")?
        .map_err(|error| error.to_string())?;
    let mut request = vec![0; 8_192];
    let length = stream
        .read(&mut request)
        .await
        .map_err(|error| error.to_string())?;
    let request = String::from_utf8_lossy(&request[..length]);
    let target = request
        .split_whitespace()
        .nth(1)
        .ok_or("Invalid Google callback")?;
    let url =
        url::Url::parse(&format!("http://127.0.0.1{target}")).map_err(|error| error.to_string())?;
    let query = url.query_pairs().collect::<BTreeMap<_, _>>();
    stream
        .write_all(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\nConnected to Omi. You can close this tab.")
        .await
        .map_err(|error| error.to_string())?;
    if query.get("state").map(|value| value.as_ref()) != Some(state.as_str()) {
        return Err("OAuth state mismatch".into());
    }
    if let Some(error) = query.get("error") {
        return Err(format!("Google authorization failed: {error}"));
    }
    Ok((
        query
            .get("code")
            .ok_or("No authorization code returned")?
            .to_string(),
        format!(
            "http://127.0.0.1:{}",
            listener
                .local_addr()
                .map_err(|error| error.to_string())?
                .port()
        ),
    ))
}

fn desktop_authorize_url(redirect: &str, state: &str, challenge: &str) -> Result<url::Url, String> {
    let mut auth = url::Url::parse(OMI_AUTH_URL).map_err(|error| error.to_string())?;
    auth.query_pairs_mut()
        .append_pair("provider", "google")
        .append_pair("redirect_uri", redirect)
        .append_pair("state", state)
        .append_pair("code_challenge", challenge)
        .append_pair("code_challenge_method", "S256");
    Ok(auth)
}

#[tauri::command]
pub async fn auth_google_sign_in(app: AppHandle) -> Result<String, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|error| error.to_string())?;
    let redirect = format!(
        "http://127.0.0.1:{}",
        listener
            .local_addr()
            .map_err(|error| error.to_string())?
            .port()
    );
    let verifier = random()?;
    let state = random()?;
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    let auth = desktop_authorize_url(&redirect, &state, &challenge)?;
    app.opener()
        .open_url(auth.as_str(), None::<&str>)
        .map_err(|error| error.to_string())?;
    let (code, redirect) = callback(listener, state).await?;
    let response = reqwest::Client::new()
        .post(OMI_TOKEN_URL)
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code.as_str()),
            ("redirect_uri", redirect.as_str()),
            ("use_custom_token", "true"),
            ("code_verifier", verifier.as_str()),
        ])
        .send()
        .await
        .map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("Omi sign-in failed: {}", response.status()));
    }
    let token = response
        .json::<DesktopAuthToken>()
        .await
        .map_err(|error| error.to_string())?;
    if token.custom_token.is_empty() {
        return Err("Omi sign-in returned an empty custom token".into());
    }
    Ok(token.custom_token)
}

#[tauri::command]
pub fn google_status() -> Result<GoogleStatus, String> {
    Ok(grant()?.map_or(
        GoogleStatus {
            connected: false,
            email: None,
            last_sync_at: None,
        },
        |grant| GoogleStatus {
            connected: true,
            email: Some(grant.email),
            last_sync_at: None,
        },
    ))
}

#[tauri::command]
pub async fn google_connect(
    app: AppHandle,
    runtime: tauri::State<'_, GoogleRuntime>,
) -> Result<GoogleStatus, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|error| error.to_string())?;
    let redirect = format!(
        "http://127.0.0.1:{}",
        listener
            .local_addr()
            .map_err(|error| error.to_string())?
            .port()
    );
    let verifier = random()?;
    let state = random()?;
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    let mut auth = url::Url::parse(AUTH_URL).map_err(|error| error.to_string())?;
    auth.query_pairs_mut().append_pair("client_id", &client_id()?).append_pair("redirect_uri", &redirect).append_pair("response_type", "code").append_pair("scope", "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly").append_pair("access_type", "offline").append_pair("prompt", "consent").append_pair("code_challenge", &challenge).append_pair("code_challenge_method", "S256").append_pair("state", &state);
    app.opener()
        .open_url(auth.as_str(), None::<&str>)
        .map_err(|error| error.to_string())?;
    let (code, redirect) = callback(listener, state).await?;
    let mut form = vec![
        ("client_id", client_id()?),
        ("code", code),
        ("code_verifier", verifier),
        ("grant_type", "authorization_code".into()),
        ("redirect_uri", redirect),
    ];
    if let Some(secret) = client_secret() {
        form.push(("client_secret", secret));
    }
    let response = reqwest::Client::new()
        .post(TOKEN_URL)
        .form(&form)
        .send()
        .await
        .map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("Token exchange failed: {}", response.status()));
    }
    let token = response
        .json::<Token>()
        .await
        .map_err(|error| error.to_string())?;
    let refresh = token
        .refresh_token
        .ok_or("Google did not return a refresh token")?;
    let email = match reqwest::Client::new()
        .get(format!("{GMAIL_URL}/profile"))
        .bearer_auth(&token.access_token)
        .send()
        .await
    {
        Ok(response) => response
            .json::<serde_json::Value>()
            .await
            .ok()
            .and_then(|json| json.get("emailAddress")?.as_str().map(str::to_owned))
            .unwrap_or_default(),
        Err(_) => String::new(),
    };
    entry()?
        .set_password(
            &serde_json::to_string(&Grant {
                refresh_token: refresh,
                email: email.clone(),
            })
            .map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())?;
    *runtime.0.lock().map_err(|error| error.to_string())? =
        Some((token.access_token, now_ms() + token.expires_in * 1000));
    Ok(GoogleStatus {
        connected: true,
        email: Some(email),
        last_sync_at: None,
    })
}

#[tauri::command]
pub fn google_disconnect(runtime: tauri::State<'_, GoogleRuntime>) -> Result<GoogleStatus, String> {
    match entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => {}
        Err(error) => return Err(format!("could not remove saved Google connection: {error}")),
    }
    *runtime.0.lock().map_err(|error| error.to_string())? = None;
    Ok(GoogleStatus {
        connected: false,
        email: None,
        last_sync_at: None,
    })
}
#[tauri::command]
pub async fn google_gmail_fetch_new(
    runtime: tauri::State<'_, GoogleRuntime>,
) -> Result<FetchResult<GmailItem>, String> {
    let token = match access(&runtime).await {
        Ok(token) => token,
        Err(error) => {
            return Ok(FetchResult {
                ok: false,
                items: Vec::new(),
                error: Some(error),
            })
        }
    };
    let client = reqwest::Client::new();
    let mut list_url =
        url::Url::parse(&format!("{GMAIL_URL}/messages")).map_err(|error| error.to_string())?;
    list_url
        .query_pairs_mut()
        .append_pair("q", "in:inbox newer_than:7d")
        .append_pair("maxResults", "25");
    let list = client
        .get(list_url)
        .bearer_auth(&token)
        .send()
        .await
        .map_err(|error| error.to_string())?
        .json::<serde_json::Value>()
        .await
        .map_err(|error| error.to_string())?;
    let seen = processed("gmail")?.into_iter().collect::<HashSet<_>>();
    let mut items = Vec::new();
    for id in list
        .get("messages")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|item| item.get("id").and_then(serde_json::Value::as_str))
        .filter(|id| !seen.contains(*id))
    {
        let message = client.get(format!("{GMAIL_URL}/messages/{id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From")).bearer_auth(&token).send().await.map_err(|error| error.to_string())?.json::<serde_json::Value>().await.map_err(|error| error.to_string())?;
        let header = |name: &str| {
            message
                .pointer("/payload/headers")
                .and_then(serde_json::Value::as_array)
                .and_then(|headers| {
                    headers.iter().find(|header| {
                        header
                            .get("name")
                            .and_then(serde_json::Value::as_str)
                            .is_some_and(|value| value.eq_ignore_ascii_case(name))
                    })
                })
                .and_then(|header| header.get("value"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or("")
                .to_owned()
        };
        items.push(GmailItem {
            id: id.to_owned(),
            subject: header("Subject"),
            from: header("From"),
            snippet: message
                .get("snippet")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("")
                .to_owned(),
            internal_date_ms: message
                .get("internalDate")
                .and_then(serde_json::Value::as_str)
                .and_then(|value| value.parse().ok())
                .unwrap_or(0),
        });
    }
    Ok(FetchResult {
        ok: true,
        items,
        error: None,
    })
}
#[tauri::command]
pub async fn google_calendar_fetch_new(
    runtime: tauri::State<'_, GoogleRuntime>,
) -> Result<FetchResult<CalendarItem>, String> {
    let token = match access(&runtime).await {
        Ok(token) => token,
        Err(error) => {
            return Ok(FetchResult {
                ok: false,
                items: Vec::new(),
                error: Some(error),
            })
        }
    };
    let now = OffsetDateTime::now_utc();
    let mut url = url::Url::parse(&format!("{CALENDAR_URL}/calendars/primary/events"))
        .map_err(|error| error.to_string())?;
    url.query_pairs_mut()
        .append_pair(
            "timeMin",
            &now.format(&Rfc3339).map_err(|error| error.to_string())?,
        )
        .append_pair(
            "timeMax",
            &(now + time::Duration::days(14))
                .format(&Rfc3339)
                .map_err(|error| error.to_string())?,
        )
        .append_pair("singleEvents", "true")
        .append_pair("orderBy", "startTime")
        .append_pair("maxResults", "50");
    let data = reqwest::Client::new()
        .get(url)
        .bearer_auth(token)
        .send()
        .await
        .map_err(|error| error.to_string())?
        .json::<serde_json::Value>()
        .await
        .map_err(|error| error.to_string())?;
    let seen = processed("calendar")?.into_iter().collect::<HashSet<_>>();
    let items = data
        .get("items")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|event| {
            let id = event.get("id")?.as_str()?.to_owned();
            (!seen.contains(&id)).then(|| CalendarItem {
                id,
                title: event
                    .get("summary")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("(no title)")
                    .to_owned(),
                start_ms: calendar_ms(
                    event
                        .pointer("/start/dateTime")
                        .or_else(|| event.pointer("/start/date")),
                ),
                end_ms: calendar_ms(
                    event
                        .pointer("/end/dateTime")
                        .or_else(|| event.pointer("/end/date")),
                ),
                location: event
                    .get("location")
                    .and_then(serde_json::Value::as_str)
                    .map(str::to_owned),
                description: event
                    .get("description")
                    .and_then(serde_json::Value::as_str)
                    .map(str::to_owned),
                updated_ms: calendar_ms(event.get("updated")),
            })
        })
        .collect();
    Ok(FetchResult {
        ok: true,
        items,
        error: None,
    })
}
#[tauri::command]
pub fn google_mark_processed(source: String, ids: Vec<String>) -> Result<(), String> {
    mark(&source, ids)
}
#[tauri::command]
pub fn sticky_notes_read() -> Result<StickyNotesResult, String> {
    if cfg!(target_os = "windows") {
        Err("Sticky Notes migration is not implemented for Tauri yet".into())
    } else {
        Err("Sticky Notes is only supported on Windows".into())
    }
}
fn calendar_ms(value: Option<&serde_json::Value>) -> i64 {
    value
        .and_then(serde_json::Value::as_str)
        .and_then(|value| OffsetDateTime::parse(value, &Rfc3339).ok())
        .or_else(|| {
            value
                .and_then(serde_json::Value::as_str)
                .and_then(date_only)
                .map(|date| PrimitiveDateTime::new(date, Time::MIDNIGHT).assume_utc())
        })
        .and_then(|value| i64::try_from(value.unix_timestamp_nanos() / 1_000_000).ok())
        .unwrap_or(0)
}

fn date_only(value: &str) -> Option<Date> {
    let mut fields = value.split('-');
    let year = fields.next()?.parse().ok()?;
    let month = Month::try_from(fields.next()?.parse::<u8>().ok()?).ok()?;
    let day = fields.next()?.parse().ok()?;
    fields
        .next()
        .is_none()
        .then(|| Date::from_calendar_date(year, month, day).ok())
        .flatten()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_google_rfc3339_timestamps_to_epoch_milliseconds() {
        assert_eq!(
            calendar_ms(Some(&serde_json::json!("1970-01-01T00:00:01Z"))),
            1_000
        );
        assert!(calendar_ms(Some(&serde_json::json!("2026-07-19"))) > 0);
    }

    #[test]
    fn desktop_authorization_uses_loopback_pkce() {
        let url = desktop_authorize_url("http://127.0.0.1:4321", "state", "challenge").unwrap();
        let query = url.query_pairs().collect::<BTreeMap<_, _>>();
        assert_eq!(url.as_str().split('?').next(), Some(OMI_AUTH_URL));
        assert_eq!(
            query.get("provider").map(|value| value.as_ref()),
            Some("google")
        );
        assert_eq!(
            query.get("redirect_uri").map(|value| value.as_ref()),
            Some("http://127.0.0.1:4321")
        );
        assert_eq!(
            query.get("state").map(|value| value.as_ref()),
            Some("state")
        );
        assert_eq!(
            query.get("code_challenge").map(|value| value.as_ref()),
            Some("challenge")
        );
        assert_eq!(
            query
                .get("code_challenge_method")
                .map(|value| value.as_ref()),
            Some("S256")
        );
    }
}
