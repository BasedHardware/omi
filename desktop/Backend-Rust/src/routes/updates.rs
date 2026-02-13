// Sparkle auto-update routes
//
// Serves appcast.xml for macOS Sparkle framework auto-updates.
// The appcast contains version info, download URLs, and EdDSA signatures.

use axum::{
    extract::{Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::AppState;

/// Query parameters for appcast endpoint
#[derive(Debug, Deserialize)]
pub struct AppcastQuery {
    /// Target platform (default: macos)
    #[serde(default = "default_platform")]
    platform: String,
}

fn default_platform() -> String {
    "macos".to_string()
}

/// Release info stored in Firestore or config
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ReleaseInfo {
    pub version: String,
    pub build_number: u32,
    pub download_url: String,
    pub ed_signature: String,
    pub published_at: String,
    pub changelog: Vec<String>,
    pub is_live: bool,
    pub is_critical: bool,
}

/// Generate Sparkle 2.0 appcast XML
fn generate_appcast_xml(releases: &[ReleaseInfo], platform: &str) -> String {
    let mut xml = String::from(r#"<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Omi Desktop Updates</title>
    <description>Omi AI Desktop Application</description>
    <language>en</language>
"#);

    for release in releases {
        if !release.is_live {
            continue;
        }

        // Build changelog HTML from release items
        let changelog_html = if release.changelog.is_empty() {
            "<p>Bug fixes and improvements.</p>".to_string()
        } else {
            let items: String = release.changelog.iter()
                .map(|c| format!("<li>{}</li>", html_escape(c)))
                .collect();
            format!("<ul>{}</ul>", items)
        };

        xml.push_str(&format!(r#"    <item>
      <title>Omi {}</title>
      <sparkle:version>{}</sparkle:version>
      <sparkle:shortVersionString>{}</sparkle:shortVersionString>
      <description><![CDATA[{}]]></description>
      <pubDate>{}</pubDate>
      <enclosure
        url="{}"
        type="application/octet-stream"
        sparkle:os="{}"
        sparkle:edSignature="{}"
      />
"#,
            release.version,
            release.build_number,
            release.version,
            changelog_html,
            release.published_at,
            release.download_url,
            platform,
            release.ed_signature,
        ));

        if release.is_critical {
            xml.push_str("      <sparkle:criticalUpdate />\n");
        }

        xml.push_str("    </item>\n");
    }

    xml.push_str("  </channel>\n</rss>\n");
    xml
}

/// Simple HTML escape for changelog items
fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// GET /appcast.xml - Sparkle appcast feed
async fn get_appcast(
    State(state): State<AppState>,
    Query(query): Query<AppcastQuery>,
) -> Response {
    // Try to fetch releases from Firestore (only serve the latest live release)
    let releases = match state.firestore.get_desktop_releases().await {
        Ok(releases) => releases.into_iter().filter(|r| r.is_live).take(1).collect(),
        Err(e) => {
            tracing::warn!("Failed to fetch releases from Firestore: {}, using fallback", e);
            // Return empty appcast if no releases found
            vec![]
        }
    };

    let xml = generate_appcast_xml(&releases, &query.platform);

    (
        [
            (header::CONTENT_TYPE, "application/xml; charset=utf-8"),
            (header::CACHE_CONTROL, "max-age=300"), // Cache for 5 minutes
        ],
        xml,
    )
        .into_response()
}

/// GET /updates/latest - Get latest version info as JSON
#[derive(Serialize)]
struct LatestVersionResponse {
    version: String,
    build_number: u32,
    download_url: String,
    is_critical: bool,
}

async fn get_latest_version(State(state): State<AppState>) -> impl IntoResponse {
    match state.firestore.get_desktop_releases().await {
        Ok(releases) => {
            if let Some(latest) = releases.into_iter().filter(|r| r.is_live).next() {
                axum::Json(LatestVersionResponse {
                    version: latest.version,
                    build_number: latest.build_number,
                    download_url: latest.download_url,
                    is_critical: latest.is_critical,
                })
                .into_response()
            } else {
                (
                    axum::http::StatusCode::NOT_FOUND,
                    "No live releases found",
                )
                    .into_response()
            }
        }
        Err(e) => {
            tracing::error!("Failed to fetch releases: {}", e);
            (
                axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to fetch releases: {}", e),
            )
                .into_response()
        }
    }
}

/// GET /download - Redirect to latest DMG download
/// This derives the DMG URL from the ZIP URL stored in Firestore
async fn download_redirect(State(state): State<AppState>) -> impl IntoResponse {
    match state.firestore.get_desktop_releases().await {
        Ok(releases) => {
            if let Some(latest) = releases.into_iter().filter(|r| r.is_live).next() {
                // Convert ZIP URL to DMG URL
                // e.g., .../Omi.zip -> .../Omi.Beta.dmg
                let dmg_url = latest.download_url.replace("Omi.zip", "Omi.Beta.dmg");
                tracing::info!("Redirecting download to: {}", dmg_url);
                axum::response::Redirect::temporary(&dmg_url).into_response()
            } else {
                (
                    StatusCode::NOT_FOUND,
                    "No live releases found",
                )
                    .into_response()
            }
        }
        Err(e) => {
            tracing::error!("Failed to fetch releases for download redirect: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to fetch releases: {}", e),
            )
                .into_response()
        }
    }
}

/// Request body for creating a release
#[derive(Debug, Deserialize)]
pub struct CreateReleaseRequest {
    pub version: String,
    pub build_number: u32,
    pub download_url: String,
    pub ed_signature: String,
    #[serde(default)]
    pub changelog: Vec<String>,
    #[serde(default = "default_true")]
    pub is_live: bool,
    #[serde(default)]
    pub is_critical: bool,
}

fn default_true() -> bool {
    true
}

/// Response for create release
#[derive(Serialize)]
struct CreateReleaseResponse {
    success: bool,
    doc_id: String,
    message: String,
}

/// POST /updates/releases - Create a new release
/// Requires RELEASE_SECRET header for authentication
async fn create_release(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<CreateReleaseRequest>,
) -> impl IntoResponse {
    // Check for release secret
    let expected_secret = std::env::var("RELEASE_SECRET").unwrap_or_default();
    let provided_secret = headers
        .get("X-Release-Secret")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if expected_secret.is_empty() || provided_secret != expected_secret {
        return (
            StatusCode::UNAUTHORIZED,
            Json(CreateReleaseResponse {
                success: false,
                doc_id: String::new(),
                message: "Invalid or missing X-Release-Secret header".to_string(),
            }),
        );
    }

    // Create release info
    let release = ReleaseInfo {
        version: request.version.clone(),
        build_number: request.build_number,
        download_url: request.download_url,
        ed_signature: request.ed_signature,
        published_at: chrono::Utc::now().to_rfc3339(),
        changelog: request.changelog,
        is_live: request.is_live,
        is_critical: request.is_critical,
    };

    // Save to Firestore
    match state.firestore.create_desktop_release(&release).await {
        Ok(doc_id) => {
            tracing::info!("Created release: {} (v{})", doc_id, release.version);
            (
                StatusCode::CREATED,
                Json(CreateReleaseResponse {
                    success: true,
                    doc_id,
                    message: format!("Release v{} created successfully", release.version),
                }),
            )
        }
        Err(e) => {
            tracing::error!("Failed to create release: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(CreateReleaseResponse {
                    success: false,
                    doc_id: String::new(),
                    message: format!("Failed to create release: {}", e),
                }),
            )
        }
    }
}

pub fn updates_routes() -> Router<AppState> {
    Router::new()
        .route("/appcast.xml", get(get_appcast))
        .route("/updates/latest", get(get_latest_version))
        .route("/updates/releases", post(create_release))
        .route("/download", get(download_redirect))
}
