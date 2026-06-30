use super::*;

impl FirestoreService {
    pub async fn get_desktop_releases(
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
                    if let Ok(release) = self.parse_release(doc) {
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
        releases.sort_by(|a, b| b.build_number.cmp(&a.build_number));

        Ok(releases)
    }

    /// Parse Firestore document to ReleaseInfo
    fn parse_release(
        &self,
        doc: &Value,
    ) -> Result<crate::routes::updates::ReleaseInfo, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;

        let changelog = if let Some(arr) = fields
            .get("changelog")
            .and_then(|c| c.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|v| v.as_array())
        {
            arr.iter()
                .filter_map(|v| v.get("stringValue").and_then(|s| s.as_str()))
                .map(|s| s.to_string())
                .collect()
        } else {
            vec![]
        };

        // channel: None = unpromoted (staging), Some("stable") = promoted stable
        let channel = self.parse_string(fields, "channel");

        Ok(crate::routes::updates::ReleaseInfo {
            version: self.parse_string(fields, "version").unwrap_or_default(),
            build_number: self
                .parse_int(fields, "build_number")
                .and_then(|value| u32::try_from(value).ok())
                .unwrap_or(0),
            download_url: self
                .parse_string(fields, "download_url")
                .unwrap_or_default(),
            manual_download_url: self.parse_string(fields, "manual_download_url"),
            ed_signature: self
                .parse_string(fields, "ed_signature")
                .unwrap_or_default(),
            published_at: self
                .parse_string(fields, "published_at")
                .unwrap_or_default(),
            changelog,
            is_live: self.parse_bool(fields, "is_live").unwrap_or(false),
            is_critical: self.parse_bool(fields, "is_critical").unwrap_or(false),
            channel,
        })
    }

    /// Create a new desktop release in Firestore
    pub async fn create_desktop_release(
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
    pub async fn promote_desktop_release(
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
        let current_channel = self.parse_string(fields, "channel").unwrap_or_default();

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
