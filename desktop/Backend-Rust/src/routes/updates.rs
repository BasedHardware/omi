// Sparkle auto-update routes
//
// Serves appcast.xml for macOS Sparkle framework auto-updates.
// The appcast contains version info, download URLs, and EdDSA signatures.

use axum::{
    extract::{Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, patch, post},
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
    /// Release channel: None = unpromoted (staging), Some("stable") = stable, Some("beta"), Some("staging")
    pub channel: Option<String>,
}

/// Generate Sparkle 2.0 appcast XML
///
/// Picks the latest live release per channel (stable, beta, staging).
/// Releases arrive sorted by build_number desc, so first live hit per channel wins.
/// Releases with channel="stable" get no XML tag (Sparkle default = stable).
/// Releases with channel=None (unpromoted) get `<sparkle:channel>staging</sparkle:channel>`.
fn generate_appcast_xml(releases: &[ReleaseInfo], platform: &str) -> String {
    let mut xml = String::from(r#"<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Omi Desktop Updates</title>
    <description>Omi AI Desktop Application</description>
    <language>en</language>
"#);

    // Deduplicate: pick the latest live release per channel
    let mut seen_channels = std::collections::HashSet::new();
    for release in releases {
        if !release.is_live {
            continue;
        }
        let ch_key = release.channel.clone().unwrap_or_else(|| "staging".to_string());
        if !seen_channels.insert(ch_key) {
            continue; // already emitted an item for this channel
        }

        // Build changelog HTML from release items
        let changelog_html = if release.changelog.is_empty() {
            "<p>Bug fixes and improvements.</p>".to_string()
        } else {
            let items: String = release.changelog.iter()
                .map(|c| format!("<li>{}</li>", c))
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

        // Emit channel tag: None/missing → staging, "stable" → no tag (Sparkle default), others → as-is
        match release.channel.as_deref() {
            Some("stable") => {} // No tag = Sparkle default channel (stable)
            Some(ch) if !ch.is_empty() => {
                xml.push_str(&format!("      <sparkle:channel>{}</sparkle:channel>\n", ch));
            }
            _ => {
                // None or empty = unpromoted, treat as staging
                xml.push_str("      <sparkle:channel>staging</sparkle:channel>\n");
            }
        }

        if release.is_critical {
            xml.push_str("      <sparkle:criticalUpdate />\n");
        }

        xml.push_str("    </item>\n");
    }

    xml.push_str("  </channel>\n</rss>\n");
    xml
}

/// GET /appcast.xml - Sparkle appcast feed
async fn get_appcast(
    State(state): State<AppState>,
    Query(query): Query<AppcastQuery>,
) -> Response {
    // Fetch all releases — generate_appcast_xml handles filtering and per-channel dedup
    let releases = match state.firestore.get_desktop_releases().await {
        Ok(releases) => releases,
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
            // Return the latest live stable release (channel == "stable")
            if let Some(latest) = releases.into_iter().filter(|r| r.is_live && r.channel.as_deref() == Some("stable")).next() {
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
/// Redirects to GCS-hosted DMG for faster downloads and better browser trust
/// (fewer redirect hops = fewer Chrome Safe Browsing warnings)
async fn download_redirect(State(state): State<AppState>) -> impl IntoResponse {
    match state.firestore.get_desktop_releases().await {
        Ok(releases) => {
            // Return the latest live stable release for download (channel == "stable")
            if let Some(latest) = releases.into_iter().filter(|r| r.is_live && r.channel.as_deref() == Some("stable")).next() {
                // Serve from GCS bucket for direct download (avoids multi-hop GitHub redirects)
                let gcs_url = format!(
                    "https://storage.googleapis.com/omi_macos_updates/releases/v{}/Omi.Beta.dmg",
                    latest.version
                );
                tracing::info!("Redirecting download to GCS: {}", gcs_url);
                axum::response::Redirect::temporary(&gcs_url).into_response()
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
    #[serde(default)]
    pub is_live: bool,
    #[serde(default)]
    pub is_critical: bool,
    /// Release channel: None/null = unpromoted (staging), "stable", "beta", "staging"
    pub channel: Option<String>,
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
        channel: request.channel,
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

/// Request body for promoting a release to the next channel
#[derive(Debug, Deserialize)]
struct PromoteReleaseRequest {
    /// Firestore doc ID, e.g. "v0.9.6+9006"
    doc_id: String,
}

/// Response for promote release
#[derive(Serialize)]
struct PromoteReleaseResponse {
    success: bool,
    doc_id: String,
    old_channel: String,
    new_channel: String,
    message: String,
}

/// PATCH /updates/releases/promote - Promote a release to the next channel
/// staging → beta → stable
async fn promote_release(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<PromoteReleaseRequest>,
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
            Json(PromoteReleaseResponse {
                success: false,
                doc_id: request.doc_id,
                old_channel: String::new(),
                new_channel: String::new(),
                message: "Invalid or missing X-Release-Secret header".to_string(),
            }),
        );
    }

    match state.firestore.promote_desktop_release(&request.doc_id).await {
        Ok((old_channel, new_channel)) => {
            let old_display = old_channel.clone();
            let new_display = new_channel.clone();
            tracing::info!("Promoted release {}: {} → {}", request.doc_id, old_display, new_display);
            let message = format!("Release promoted from {} to {}", old_display, new_display);
            (
                StatusCode::OK,
                Json(PromoteReleaseResponse {
                    success: true,
                    doc_id: request.doc_id,
                    old_channel: old_display,
                    new_channel: new_display,
                    message,
                }),
            )
        }
        Err(e) => {
            tracing::error!("Failed to promote release {}: {}", request.doc_id, e);
            (
                StatusCode::BAD_REQUEST,
                Json(PromoteReleaseResponse {
                    success: false,
                    doc_id: request.doc_id,
                    old_channel: String::new(),
                    new_channel: String::new(),
                    message: format!("Failed to promote: {}", e),
                }),
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_release(version: &str, build: u32, channel: Option<&str>, is_live: bool) -> ReleaseInfo {
        ReleaseInfo {
            version: version.to_string(),
            build_number: build,
            download_url: format!("https://example.com/{}.zip", version),
            ed_signature: "sig123".to_string(),
            published_at: "2025-01-01T00:00:00Z".to_string(),
            changelog: vec![],
            is_live,
            is_critical: false,
            channel: channel.map(|s| s.to_string()),
        }
    }

    #[test]
    fn test_null_channel_gets_staging_tag() {
        let releases = vec![make_release("0.1.0", 100, None, true)];
        let xml = generate_appcast_xml(&releases, "macos");
        assert!(xml.contains("<sparkle:channel>staging</sparkle:channel>"),
            "null channel should emit staging tag, got:\n{}", xml);
    }

    #[test]
    fn test_stable_channel_gets_no_tag() {
        let releases = vec![make_release("0.2.0", 200, Some("stable"), true)];
        let xml = generate_appcast_xml(&releases, "macos");
        assert!(!xml.contains("<sparkle:channel>"),
            "stable channel should emit no channel tag, got:\n{}", xml);
    }

    #[test]
    fn test_beta_channel_gets_beta_tag() {
        let releases = vec![make_release("0.3.0", 300, Some("beta"), true)];
        let xml = generate_appcast_xml(&releases, "macos");
        assert!(xml.contains("<sparkle:channel>beta</sparkle:channel>"),
            "beta channel should emit beta tag, got:\n{}", xml);
    }

    #[test]
    fn test_staging_channel_gets_staging_tag() {
        let releases = vec![make_release("0.4.0", 400, Some("staging"), true)];
        let xml = generate_appcast_xml(&releases, "macos");
        assert!(xml.contains("<sparkle:channel>staging</sparkle:channel>"),
            "staging channel should emit staging tag, got:\n{}", xml);
    }

    #[test]
    fn test_dedup_null_and_staging_same_group() {
        // null-channel and staging-channel should deduplicate together
        let releases = vec![
            make_release("0.5.0", 500, None, true),          // null → staging group
            make_release("0.4.0", 400, Some("staging"), true), // explicit staging
        ];
        let xml = generate_appcast_xml(&releases, "macos");
        // Only the first (higher build) should appear
        assert!(xml.contains("0.5.0"), "first staging release should appear");
        assert!(!xml.contains("0.4.0"), "second staging release should be deduped");
    }

    #[test]
    fn test_stable_and_null_are_separate_groups() {
        let releases = vec![
            make_release("1.0.0", 1000, Some("stable"), true),
            make_release("0.9.0", 900, None, true), // null → staging
        ];
        let xml = generate_appcast_xml(&releases, "macos");
        assert!(xml.contains("1.0.0"), "stable release should appear");
        assert!(xml.contains("0.9.0"), "null/staging release should also appear (different group)");
    }

    #[test]
    fn test_not_live_releases_excluded() {
        let releases = vec![make_release("0.1.0", 100, Some("stable"), false)];
        let xml = generate_appcast_xml(&releases, "macos");
        assert!(!xml.contains("0.1.0"), "non-live release should not appear");
    }
}

pub fn updates_routes() -> Router<AppState> {
    Router::new()
        .route("/appcast.xml", get(get_appcast))
        .route("/updates/latest", get(get_latest_version))
        .route("/updates/releases", post(create_release))
        .route("/updates/releases/promote", patch(promote_release))
        .route("/download", get(download_redirect))
}
