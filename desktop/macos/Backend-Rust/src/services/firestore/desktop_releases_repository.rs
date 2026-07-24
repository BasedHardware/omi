use super::*;

fn parse_release(
    doc: &Value,
) -> Result<crate::routes::updates::ReleaseInfo, Box<dyn std::error::Error + Send + Sync>> {
    let fields = doc.get("fields").ok_or("Missing fields")?;
    let changelog = fields
        .get("changelog")
        .and_then(|changelog| changelog.get("arrayValue"))
        .and_then(|array| array.get("values"))
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| value.get("stringValue").and_then(Value::as_str))
                .map(str::to_owned)
                .collect()
        })
        .unwrap_or_default();

    Ok(crate::routes::updates::ReleaseInfo {
        version: values::string_field(fields, "version").unwrap_or_default(),
        build_number: values::i32_field(fields, "build_number")
            .and_then(|value| u32::try_from(value).ok())
            .unwrap_or(0),
        download_url: values::string_field(fields, "download_url").unwrap_or_default(),
        manual_download_url: values::string_field(fields, "manual_download_url"),
        ed_signature: values::string_field(fields, "ed_signature").unwrap_or_default(),
        published_at: values::string_field(fields, "published_at").unwrap_or_default(),
        changelog,
        is_live: values::bool_field(fields, "is_live").unwrap_or(false),
        is_critical: values::bool_field(fields, "is_critical").unwrap_or(false),
        channel: values::string_field(fields, "channel"),
    })
}

impl FirestoreService {
    pub(crate) async fn get_desktop_releases(
        &self,
    ) -> Result<Vec<crate::routes::updates::ReleaseInfo>, Box<dyn std::error::Error + Send + Sync>>
    {
        let base_url = format!("{}/desktop_releases", self.base_url());
        let mut page_token: Option<String> = None;
        let mut releases = Vec::new();

        loop {
            let url = match &page_token {
                Some(token) => format!(
                    "{}?pageSize=500&pageToken={}",
                    base_url,
                    urlencoding::encode(token)
                ),
                None => format!("{}?pageSize=500", base_url),
            };

            let response = self
                .build_request(reqwest::Method::GET, &url)
                .await?
                .send()
                .await?;

            if !response.status().is_success() {
                // If collection doesn't exist, return empty list
                if response.status() == reqwest::StatusCode::NOT_FOUND {
                    return Ok(vec![]);
                }
                let error_text = response.text().await?;
                return Err(format!("Firestore error: {}", error_text).into());
            }

            let data: Value = response.json().await?;
            if let Some(documents) = data.get("documents").and_then(|d| d.as_array()) {
                for doc in documents {
                    if let Ok(release) = parse_release(doc) {
                        releases.push(release);
                    }
                }
            }

            page_token = data
                .get("nextPageToken")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            if page_token.is_none() {
                break;
            }
        }

        // Sort by build number descending (newest first)
        releases.sort_by_key(|release| std::cmp::Reverse(release.build_number));

        Ok(releases)
    }

    /// Create a new desktop release in Firestore
    pub(crate) async fn create_desktop_release(
        &self,
        release: &crate::routes::updates::ReleaseInfo,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let doc_id = format!("v{}+{}", release.version, release.build_number);

        let url = format!("{}/desktop_releases/{}", self.base_url(), doc_id);

        // Build changelog array
        let changelog_values: Vec<Value> = release
            .changelog
            .iter()
            .map(|s| json!({"stringValue": s}))
            .collect();

        // Channel field: always a string. None/empty → "staging" (unpromoted default)
        let channel_value = match &release.channel {
            Some(ch) if !ch.is_empty() => json!({"stringValue": ch}),
            _ => json!({"stringValue": "staging"}),
        };

        let manual_download_url_value = match &release.manual_download_url {
            Some(url) if !url.trim().is_empty() => json!({"stringValue": url}),
            _ => json!({"nullValue": null}),
        };

        let doc = json!({
            "fields": {
                "version": {"stringValue": release.version},
                "build_number": {"integerValue": release.build_number.to_string()},
                "download_url": {"stringValue": release.download_url},
                "manual_download_url": manual_download_url_value,
                "ed_signature": {"stringValue": release.ed_signature},
                "published_at": {"stringValue": release.published_at},
                "changelog": {"arrayValue": {"values": changelog_values}},
                "is_live": {"booleanValue": release.is_live},
                "is_critical": {"booleanValue": release.is_critical},
                "channel": channel_value
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!("Created desktop release: {}", doc_id);
        Ok(doc_id)
    }

    /// Promote a desktop release to the next channel: staging → beta → stable
    /// Returns (old_channel, new_channel)
    pub(crate) async fn promote_desktop_release(
        &self,
        doc_id: &str,
    ) -> Result<(String, String), Box<dyn std::error::Error + Send + Sync>> {
        // Fetch the current document
        let url = format!("{}/desktop_releases/{}", self.base_url(), doc_id);

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Release not found: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let fields = doc.get("fields").ok_or("Missing fields in document")?;
        let current_channel = values::string_field(fields, "channel").unwrap_or_default();

        // Determine next channel
        let (old_channel, new_channel) = match current_channel.as_str() {
            "staging" | "" => ("staging".to_string(), "beta".to_string()),
            "beta" => ("beta".to_string(), "stable".to_string()),
            "stable" => {
                return Err("Release is already on stable channel, cannot promote further".into())
            }
            other => return Err(format!("Unknown channel '{}', cannot promote", other).into()),
        };
        let new_channel_value = json!({"stringValue": new_channel});

        // PATCH only the channel field
        let update_time = doc
            .get("updateTime")
            .and_then(|v| v.as_str())
            .ok_or("Missing updateTime in document")?;
        let patch_url = format!(
            "{}/desktop_releases/{}?updateMask.fieldPaths=channel&currentDocument.updateTime={}",
            self.base_url(),
            doc_id,
            urlencoding::encode(update_time)
        );

        let patch_doc = json!({
            "fields": {
                "channel": new_channel_value
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &patch_url)
            .await?
            .json(&patch_doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to update channel: {}", error_text).into());
        }

        tracing::info!(
            "Promoted release {}: {} → {}",
            doc_id,
            old_channel,
            new_channel
        );

        Ok((old_channel, new_channel))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_release_manifest_without_service_or_credentials() {
        let release = parse_release(&json!({
            "fields": {
                "version": {"stringValue": "1.2.3"},
                "build_number": {"integerValue": "42"},
                "download_url": {"stringValue": "https://example.com/app.zip"},
                "manual_download_url": {"stringValue": "https://example.com"},
                "ed_signature": {"stringValue": "signature"},
                "published_at": {"stringValue": "2026-07-12T00:00:00Z"},
                "changelog": {"arrayValue": {"values": [
                    {"stringValue": "First"},
                    {"integerValue": "ignored"},
                    {"stringValue": "Second"}
                ]}},
                "is_live": {"booleanValue": true},
                "is_critical": {"booleanValue": false},
                "channel": {"stringValue": "beta"}
            }
        }))
        .expect("valid release document");

        assert_eq!(release.version, "1.2.3");
        assert_eq!(release.build_number, 42);
        assert_eq!(release.changelog, ["First", "Second"]);
        assert!(release.is_live);
        assert!(!release.is_critical);
        assert_eq!(release.channel.as_deref(), Some("beta"));
    }

    #[test]
    fn rejects_release_document_without_fields() {
        assert!(parse_release(&json!({})).is_err());
    }
}
