use super::*;
use crate::models::conversation::{ConversationSource, ConversationStatus};
use serde::Serialize;

pub(super) fn serde_wire_value<T: Serialize>(value: &T) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .unwrap_or_default()
}

pub(super) fn conversation_source_wire(source: &ConversationSource) -> String {
    serde_wire_value(source)
}

pub(super) fn conversation_status_wire(status: &ConversationStatus) -> String {
    serde_wire_value(status)
}

pub(super) fn category_wire(category: &Category) -> String {
    serde_wire_value(category)
}

pub(super) fn memory_category_wire(category: &MemoryCategory) -> String {
    serde_wire_value(category)
}

pub(super) fn memory_is_active(memory: &MemoryDB, include_invalidated: bool) -> bool {
    memory.user_review != Some(false) && (include_invalidated || memory.invalid_at.is_none())
}

pub(super) fn memory_is_public(memory: &MemoryDB) -> bool {
    memory.visibility == "public"
}

impl FirestoreService {
    pub(super) fn parse_string_array(&self, fields: &Value, key: &str) -> Vec<String> {
        fields
            .get(key)
            .and_then(|v| v.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.get("stringValue")?.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default()
    }

    // =========================================================================
    // PARSING HELPERS
    // =========================================================================

    /// Parse Firestore document to Conversation
    /// Decrypts transcript_segments and photos if data_protection_level is "enhanced"
    pub(super) fn parse_conversation(
        &self,
        doc: &Value,
        uid: &str,
    ) -> Result<Conversation, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields in document")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        // Use created_at as fallback for missing timestamps
        let created_at = self
            .parse_timestamp_optional(fields, "created_at")
            .unwrap_or_else(Utc::now);
        let started_at = self
            .parse_timestamp_optional(fields, "started_at")
            .unwrap_or(created_at);
        let finished_at = self
            .parse_timestamp_optional(fields, "finished_at")
            .unwrap_or(created_at);

        // Parse apps_results
        let apps_results = self.parse_apps_results(fields);

        Ok(Conversation {
            id,
            created_at,
            started_at,
            finished_at,
            source: self
                .parse_string(fields, "source")
                .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
                .unwrap_or_default(),
            language: self.parse_string(fields, "language").unwrap_or_default(),
            status: self
                .parse_string(fields, "status")
                .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
                .unwrap_or_default(),
            discarded: self.parse_bool(fields, "discarded").unwrap_or(false),
            deleted: self.parse_bool(fields, "deleted").unwrap_or(false),
            starred: self.parse_bool(fields, "starred").unwrap_or(false),
            is_locked: self.parse_bool(fields, "is_locked").unwrap_or(false),
            folder_id: self.parse_string(fields, "folder_id"),
            structured: self.parse_structured(fields)?,
            transcript_segments: self.parse_transcript_segments(fields, uid)?,
            apps_results,
            geolocation: self.parse_geolocation(fields),
            photos: self.parse_photos(fields, uid),
            input_device_name: self.parse_string(fields, "input_device_name"),
        })
    }

    /// Parse apps_results array from Firestore fields
    pub(super) fn parse_apps_results(&self, fields: &Value) -> Vec<crate::models::AppResult> {
        let array = match fields
            .get("apps_results")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array
            .iter()
            .filter_map(|item| {
                let map_fields = item.get("mapValue")?.get("fields")?;
                let app_id = self.parse_string(map_fields, "app_id");
                let content = self.parse_string(map_fields, "content").unwrap_or_default();
                Some(crate::models::AppResult { app_id, content })
            })
            .collect()
    }

    /// Parse Firestore document to ActionItemDB
    pub(super) fn parse_action_item(
        &self,
        doc: &Value,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        Ok(ActionItemDB {
            id,
            description: self.parse_string(fields, "description").unwrap_or_default(),
            completed: self.parse_bool(fields, "completed").unwrap_or(false),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at"),
            due_at: self.parse_timestamp_optional(fields, "due_at"),
            completed_at: self.parse_timestamp_optional(fields, "completed_at"),
            conversation_id: self.parse_string(fields, "conversation_id"),
            source: self.parse_string(fields, "source"),
            priority: self.parse_string(fields, "priority"),
            metadata: self.parse_string(fields, "metadata"),
            deleted: self.parse_bool(fields, "deleted").ok(),
            deleted_by: self.parse_string(fields, "deleted_by"),
            deleted_at: self.parse_timestamp_optional(fields, "deleted_at"),
            deleted_reason: self.parse_string(fields, "deleted_reason"),
            kept_task_id: self.parse_string(fields, "kept_task_id"),
            category: self.parse_string(fields, "category"),
            goal_id: self.parse_string(fields, "goal_id"),
            relevance_score: self.parse_int(fields, "relevance_score"),
            sort_order: self.parse_int(fields, "sort_order"),
            indent_level: self.parse_int(fields, "indent_level"),
            from_staged: self.parse_bool(fields, "from_staged").ok(),
            recurrence_rule: self.parse_string(fields, "recurrence_rule"),
            recurrence_parent_id: self.parse_string(fields, "recurrence_parent_id"),
        })
    }

    /// Parse Firestore document to MemoryDB
    /// Decrypts content if data_protection_level is "enhanced" and encryption secret is available.
    pub(super) fn parse_memory(
        &self,
        doc: &Value,
        uid: &str,
    ) -> Result<MemoryDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        // Get raw content
        let mut content = self.parse_string(fields, "content").unwrap_or_default();

        // Check if content is encrypted (data_protection_level = "enhanced")
        let data_protection_level = self.parse_string(fields, "data_protection_level");
        if data_protection_level.as_deref() == Some("enhanced") {
            if let Some(ref secret) = self.encryption_secret {
                match encryption::decrypt(&content, uid, secret) {
                    Ok(decrypted) => content = decrypted,
                    Err(e) => {
                        tracing::warn!("Failed to decrypt memory {}: {}", id, e);
                        content =
                            "[Protected memory — cannot decrypt with current key]".to_string();
                    }
                }
            } else {
                tracing::warn!(
                    "Memory {} has enhanced protection but no encryption secret configured",
                    id
                );
                content = "[Protected memory — ENCRYPTION_SECRET not configured]".to_string();
            }
        }

        Ok(MemoryDB {
            id: id.clone(),
            uid: "".to_string(), // Not stored in document
            content,
            category: self
                .parse_string(fields, "category")
                .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
                .unwrap_or_default(),
            created_at: self.parse_timestamp(fields, "created_at")?,
            updated_at: self.parse_timestamp(fields, "updated_at")?,
            memory_id: self.parse_string(fields, "memory_id"),
            conversation_id: self.parse_string(fields, "conversation_id"),
            reviewed: self.parse_bool(fields, "reviewed").unwrap_or(false),
            user_review: self.parse_bool(fields, "user_review").ok(),
            visibility: self
                .parse_string(fields, "visibility")
                .unwrap_or_else(|| "public".to_string()),
            manually_added: self.parse_bool(fields, "manually_added").unwrap_or(false),
            scoring: self.parse_string(fields, "scoring"),
            source: self.parse_string(fields, "source"), // Can be stored directly for tips, or enriched from conversation
            input_device_name: None,                     // Enriched later from linked conversation
            confidence: self.parse_float(fields, "confidence"),
            source_app: self.parse_string(fields, "source_app"),
            context_summary: self.parse_string(fields, "context_summary"),
            is_read: self.parse_bool(fields, "is_read").unwrap_or(false),
            is_dismissed: self.parse_bool(fields, "is_dismissed").unwrap_or(false),
            tags: self.parse_string_array(fields, "tags"),
            reasoning: self.parse_string(fields, "reasoning"),
            current_activity: self.parse_string(fields, "current_activity"),
            window_title: self.parse_string(fields, "window_title"),
            data_protection_level,
            valid_at: self.parse_timestamp_optional(fields, "valid_at"),
            invalid_at: self.parse_timestamp_optional(fields, "invalid_at"),
            superseded_by: self.parse_string(fields, "superseded_by"),
            edited: self.parse_bool(fields, "edited").unwrap_or(false),
            is_locked: self.parse_bool(fields, "is_locked").unwrap_or(false),
            kg_extracted: self.parse_bool(fields, "kg_extracted").unwrap_or(false),
            app_id: self.parse_string(fields, "app_id"),
        })
    }

    /// Parse structured data from conversation
    pub(super) fn parse_structured(
        &self,
        fields: &Value,
    ) -> Result<Structured, Box<dyn std::error::Error + Send + Sync>> {
        let structured = fields
            .get("structured")
            .and_then(|s| s.get("mapValue"))
            .and_then(|m| m.get("fields"));

        if let Some(s) = structured {
            let title = self.parse_string(s, "title").unwrap_or_default();
            if title.is_empty() {
                tracing::warn!(
                    "DEBUG parse_structured: title is empty! structured fields: {}",
                    serde_json::to_string_pretty(s).unwrap_or_default()
                );
            }
            Ok(Structured {
                title,
                overview: self.parse_string(s, "overview").unwrap_or_default(),
                emoji: self
                    .parse_string(s, "emoji")
                    .unwrap_or_else(|| "🧠".to_string()),
                category: self
                    .parse_string(s, "category")
                    .and_then(|c| serde_json::from_str(&format!("\"{}\"", c)).ok())
                    .unwrap_or_default(),
                action_items: self.parse_action_items_from_structured(s),
                events: self.parse_events_from_structured(s),
            })
        } else {
            tracing::warn!(
                "DEBUG parse_structured: no structured field found! fields: {}",
                serde_json::to_string_pretty(fields).unwrap_or_default()
            );
            Ok(Structured::default())
        }
    }

    /// Parse action_items array from structured field
    pub(super) fn parse_action_items_from_structured(
        &self,
        structured_fields: &Value,
    ) -> Vec<crate::models::ActionItem> {
        let array = match structured_fields
            .get("action_items")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array
            .iter()
            .filter_map(|item| {
                let map_fields = item.get("mapValue")?.get("fields")?;
                let description = self
                    .parse_string(map_fields, "description")
                    .unwrap_or_default();
                let completed = self.parse_bool(map_fields, "completed").unwrap_or(false);
                let due_at = self.parse_timestamp_optional(map_fields, "due_at");
                Some(crate::models::ActionItem {
                    description,
                    completed,
                    due_at,
                    confidence: None,
                    priority: None,
                })
            })
            .collect()
    }

    /// Parse events array from structured field
    pub(super) fn parse_events_from_structured(
        &self,
        structured_fields: &Value,
    ) -> Vec<crate::models::Event> {
        let array = match structured_fields
            .get("events")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array
            .iter()
            .filter_map(|item| {
                let map_fields = item.get("mapValue")?.get("fields")?;
                let title = self.parse_string(map_fields, "title").unwrap_or_default();
                let description = self
                    .parse_string(map_fields, "description")
                    .unwrap_or_default();
                let start = self.parse_timestamp_optional(map_fields, "start")?;
                let duration = self.parse_int(map_fields, "duration").unwrap_or(30);
                Some(crate::models::Event {
                    title,
                    description,
                    start,
                    duration,
                })
            })
            .collect()
    }

    /// Parse geolocation from conversation fields
    pub(super) fn parse_geolocation(&self, fields: &Value) -> Option<crate::models::Geolocation> {
        let geo = fields.get("geolocation")?.get("mapValue")?.get("fields")?;

        Some(crate::models::Geolocation {
            google_place_id: self.parse_string(geo, "google_place_id"),
            latitude: self.parse_float(geo, "latitude").unwrap_or(0.0),
            longitude: self.parse_float(geo, "longitude").unwrap_or(0.0),
            address: self.parse_string(geo, "address"),
            location_type: self.parse_string(geo, "location_type"),
        })
    }

    /// Parse photos array from conversation fields
    /// Decrypts base64 field if data_protection_level is "enhanced"
    pub(super) fn parse_photos(
        &self,
        fields: &Value,
        uid: &str,
    ) -> Vec<crate::models::ConversationPhoto> {
        let array = match fields
            .get("photos")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array.iter().filter_map(|item| {
            let map_fields = item.get("mapValue")?.get("fields")?;
            let id = self.parse_string(map_fields, "id");
            let mut base64 = self.parse_string(map_fields, "base64").unwrap_or_default();
            let description = self.parse_string(map_fields, "description");
            let created_at = self.parse_timestamp_optional(map_fields, "created_at").unwrap_or_else(Utc::now);
            let discarded = self.parse_bool(map_fields, "discarded").unwrap_or(false);

            // Check if photo is encrypted (data_protection_level = "enhanced")
            let data_protection_level = self.parse_string(map_fields, "data_protection_level");
            if data_protection_level.as_deref() == Some("enhanced") {
                if let Some(ref secret) = self.encryption_secret {
                    match encryption::decrypt(&base64, uid, secret) {
                        Ok(decrypted) => base64 = decrypted,
                        Err(e) => {
                            tracing::warn!("Failed to decrypt photo {:?}: {} — skipping", id, e);
                            return None;
                        }
                    }
                } else {
                    tracing::warn!("Photo {:?} has enhanced protection but no encryption secret — skipping", id);
                    return None;
                }
            }

            Some(crate::models::ConversationPhoto { id, base64, description, created_at, discarded })
        }).collect()
    }

    /// Parse transcript segments
    /// Handles plain arrays, zlib-compressed bytes (from OMI device), and encrypted segments.
    /// For encrypted segments (data_protection_level = "enhanced"):
    ///   - Decrypts the base64 string → hex string
    ///   - Converts hex to bytes
    ///   - Decompresses with zlib
    ///   - Parses JSON array
    pub(super) fn parse_transcript_segments(
        &self,
        fields: &Value,
        uid: &str,
    ) -> Result<Vec<TranscriptSegment>, Box<dyn std::error::Error + Send + Sync>> {
        use flate2::read::ZlibDecoder;
        use std::io::Read;

        let transcript_field = fields.get("transcript_segments");

        // Check if transcript is a string (encrypted for enhanced protection)
        if let Some(string_val) = transcript_field
            .and_then(|t| t.get("stringValue"))
            .and_then(|s| s.as_str())
        {
            let data_protection_level = self.parse_string(fields, "data_protection_level");
            if data_protection_level.as_deref() == Some("enhanced") {
                if let Some(ref secret) = self.encryption_secret {
                    // Decrypt the encrypted string
                    let decrypted_payload = match encryption::decrypt(string_val, uid, secret) {
                        Ok(decrypted) => decrypted,
                        Err(e) => {
                            tracing::warn!("Failed to decrypt transcript segments: {}", e);
                            return Ok(vec![]);
                        }
                    };

                    // Check if compression is used (should always be true for enhanced)
                    let is_compressed = self
                        .parse_bool(fields, "transcript_segments_compressed")
                        .unwrap_or(false);

                    if is_compressed {
                        // Decrypted payload is a hex string, convert to bytes
                        match hex::decode(&decrypted_payload) {
                            Ok(compressed_bytes) => {
                                // Decompress with zlib
                                let mut decoder = ZlibDecoder::new(&compressed_bytes[..]);
                                let mut decompressed = String::new();
                                if let Err(e) = decoder.read_to_string(&mut decompressed) {
                                    tracing::warn!(
                                        "Failed to decompress encrypted transcript segments: {}",
                                        e
                                    );
                                    return Ok(vec![]);
                                }

                                // Parse JSON array of segments
                                match serde_json::from_str::<Vec<serde_json::Value>>(&decompressed)
                                {
                                    Ok(segments) => {
                                        let result: Vec<TranscriptSegment> = segments
                                            .iter()
                                            .filter_map(|seg| {
                                                Some(TranscriptSegment {
                                                    id: seg
                                                        .get("id")
                                                        .and_then(|s| s.as_str())
                                                        .map(|s| s.to_string()),
                                                    text: seg.get("text")?.as_str()?.to_string(),
                                                    speaker: seg
                                                        .get("speaker")
                                                        .and_then(|s| s.as_str())
                                                        .unwrap_or("SPEAKER_00")
                                                        .to_string(),
                                                    speaker_id: seg
                                                        .get("speaker_id")
                                                        .and_then(|s| s.as_i64())
                                                        .unwrap_or(0)
                                                        as i32,
                                                    is_user: seg
                                                        .get("is_user")
                                                        .and_then(|s| s.as_bool())
                                                        .unwrap_or(false),
                                                    person_id: seg
                                                        .get("person_id")
                                                        .and_then(|s| s.as_str())
                                                        .map(|s| s.to_string()),
                                                    start: seg
                                                        .get("start")
                                                        .and_then(|s| s.as_f64())
                                                        .unwrap_or(0.0),
                                                    end: seg
                                                        .get("end")
                                                        .and_then(|s| s.as_f64())
                                                        .unwrap_or(0.0),
                                                })
                                            })
                                            .collect();
                                        tracing::debug!("Decrypted and decompressed {} transcript segments for user {}", result.len(), uid);
                                        return Ok(result);
                                    }
                                    Err(e) => {
                                        tracing::warn!("Failed to parse decrypted transcript segments JSON: {}", e);
                                        return Ok(vec![]);
                                    }
                                }
                            }
                            Err(e) => {
                                tracing::warn!(
                                    "Failed to decode hex from decrypted transcript: {}",
                                    e
                                );
                                return Ok(vec![]);
                            }
                        }
                    } else {
                        // Old format: decrypted payload is JSON directly (backward compatibility)
                        match serde_json::from_str::<Vec<serde_json::Value>>(&decrypted_payload) {
                            Ok(segments) => {
                                let result: Vec<TranscriptSegment> = segments
                                    .iter()
                                    .filter_map(|seg| {
                                        Some(TranscriptSegment {
                                            id: seg
                                                .get("id")
                                                .and_then(|s| s.as_str())
                                                .map(|s| s.to_string()),
                                            text: seg.get("text")?.as_str()?.to_string(),
                                            speaker: seg
                                                .get("speaker")
                                                .and_then(|s| s.as_str())
                                                .unwrap_or("SPEAKER_00")
                                                .to_string(),
                                            speaker_id: seg
                                                .get("speaker_id")
                                                .and_then(|s| s.as_i64())
                                                .unwrap_or(0)
                                                as i32,
                                            is_user: seg
                                                .get("is_user")
                                                .and_then(|s| s.as_bool())
                                                .unwrap_or(false),
                                            person_id: seg
                                                .get("person_id")
                                                .and_then(|s| s.as_str())
                                                .map(|s| s.to_string()),
                                            start: seg
                                                .get("start")
                                                .and_then(|s| s.as_f64())
                                                .unwrap_or(0.0),
                                            end: seg
                                                .get("end")
                                                .and_then(|s| s.as_f64())
                                                .unwrap_or(0.0),
                                        })
                                    })
                                    .collect();
                                tracing::debug!(
                                    "Decrypted {} transcript segments (uncompressed) for user {}",
                                    result.len(),
                                    uid
                                );
                                return Ok(result);
                            }
                            Err(e) => {
                                tracing::warn!(
                                    "Failed to parse decrypted transcript segments JSON: {}",
                                    e
                                );
                                return Ok(vec![]);
                            }
                        }
                    }
                } else {
                    tracing::debug!(
                        "Transcript segments have enhanced protection but no encryption secret configured"
                    );
                    return Ok(vec![]);
                }
            } else {
                // String but not enhanced - shouldn't happen, but return empty
                tracing::debug!(
                    "Transcript segments are string format but not enhanced protection"
                );
                return Ok(vec![]);
            }
        }

        // Check if transcript is bytes (zlib compressed) - decompress it
        if let Some(bytes_val) = transcript_field.and_then(|t| t.get("bytesValue")) {
            if let Some(b64_str) = bytes_val.as_str() {
                match self.decompress_transcript_segments(b64_str) {
                    Ok(segments) => {
                        tracing::debug!("Decompressed {} transcript segments", segments.len());
                        return Ok(segments);
                    }
                    Err(e) => {
                        tracing::warn!("Failed to decompress transcript segments: {}", e);
                        return Ok(vec![]);
                    }
                }
            }
        }

        // Handle plain array format
        let segments = transcript_field
            .and_then(|s| s.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|v| v.as_array());

        if let Some(segs) = segments {
            Ok(segs
                .iter()
                .filter_map(|seg| {
                    let seg_fields = seg.get("mapValue")?.get("fields")?;
                    Some(TranscriptSegment {
                        id: self.parse_string(seg_fields, "id"),
                        text: self.parse_string(seg_fields, "text").unwrap_or_default(),
                        speaker: self
                            .parse_string(seg_fields, "speaker")
                            .unwrap_or_else(|| "SPEAKER_00".to_string()),
                        speaker_id: self.parse_int(seg_fields, "speaker_id").unwrap_or(0),
                        is_user: self.parse_bool(seg_fields, "is_user").unwrap_or(false),
                        person_id: self.parse_string(seg_fields, "person_id"),
                        start: self.parse_float(seg_fields, "start").unwrap_or(0.0),
                        end: self.parse_float(seg_fields, "end").unwrap_or(0.0),
                    })
                })
                .collect())
        } else {
            Ok(vec![])
        }
    }

    /// Decompress zlib-compressed transcript segments from base64-encoded bytes
    pub(super) fn decompress_transcript_segments(
        &self,
        b64_str: &str,
    ) -> Result<Vec<TranscriptSegment>, Box<dyn std::error::Error + Send + Sync>> {
        use flate2::read::ZlibDecoder;
        use std::io::Read;

        // Decode base64 to bytes
        let compressed_bytes =
            base64::Engine::decode(&base64::engine::general_purpose::STANDARD, b64_str)?;

        // Decompress with zlib
        let mut decoder = ZlibDecoder::new(&compressed_bytes[..]);
        let mut decompressed = String::new();
        decoder.read_to_string(&mut decompressed)?;

        // Parse JSON array of segments
        let segments: Vec<serde_json::Value> = serde_json::from_str(&decompressed)?;

        // Convert to TranscriptSegment
        Ok(segments
            .iter()
            .filter_map(|seg| {
                Some(TranscriptSegment {
                    id: seg
                        .get("id")
                        .and_then(|s| s.as_str())
                        .map(|s| s.to_string()),
                    text: seg.get("text")?.as_str()?.to_string(),
                    speaker: seg
                        .get("speaker")
                        .and_then(|s| s.as_str())
                        .unwrap_or("SPEAKER_00")
                        .to_string(),
                    speaker_id: seg.get("speaker_id").and_then(|s| s.as_i64()).unwrap_or(0) as i32,
                    is_user: seg
                        .get("is_user")
                        .and_then(|s| s.as_bool())
                        .unwrap_or(false),
                    person_id: seg
                        .get("person_id")
                        .and_then(|s| s.as_str())
                        .map(|s| s.to_string()),
                    start: seg.get("start").and_then(|s| s.as_f64()).unwrap_or(0.0),
                    end: seg.get("end").and_then(|s| s.as_f64()).unwrap_or(0.0),
                })
            })
            .collect())
    }

    /// Convert conversation to Firestore document format
    /// Compresses transcript_segments with zlib to match Python backend format.
    /// If encryption_secret is available, also encrypts (enhanced protection).
    pub(super) fn conversation_to_firestore(&self, conv: &Conversation, uid: &str) -> Value {
        // Build action_items array for structured
        let action_items_values: Vec<Value> = conv
            .structured
            .action_items
            .iter()
            .map(|item| {
                let mut fields = serde_json::Map::new();
                fields.insert(
                    "description".to_string(),
                    json!({"stringValue": item.description}),
                );
                fields.insert(
                    "completed".to_string(),
                    json!({"booleanValue": item.completed}),
                );
                if let Some(due_at) = &item.due_at {
                    fields.insert(
                        "due_at".to_string(),
                        json!({"timestampValue": due_at.to_rfc3339()}),
                    );
                }
                json!({"mapValue": {"fields": fields}})
            })
            .collect();

        // Build events array for structured
        let events_values: Vec<Value> = conv
            .structured
            .events
            .iter()
            .map(|event| {
                json!({
                    "mapValue": {
                        "fields": {
                            "title": {"stringValue": event.title},
                            "description": {"stringValue": event.description},
                            "start": {"timestampValue": event.start.to_rfc3339()},
                            "duration": {"integerValue": event.duration.to_string()}
                        }
                    }
                })
            })
            .collect();

        // Build apps_results array
        let apps_results_values: Vec<Value> = conv
            .apps_results
            .iter()
            .map(|result| {
                let mut fields = serde_json::Map::new();
                if let Some(app_id) = &result.app_id {
                    fields.insert("app_id".to_string(), json!({"stringValue": app_id}));
                }
                fields.insert(
                    "content".to_string(),
                    json!({"stringValue": result.content}),
                );
                json!({"mapValue": {"fields": fields}})
            })
            .collect();

        // Build the main document
        let mut fields = serde_json::Map::new();

        // CRITICAL: Include the id field - Python backend requires this
        fields.insert("id".to_string(), json!({"stringValue": conv.id}));
        fields.insert(
            "created_at".to_string(),
            json!({"timestampValue": conv.created_at.to_rfc3339()}),
        );
        fields.insert(
            "started_at".to_string(),
            json!({"timestampValue": conv.started_at.to_rfc3339()}),
        );
        fields.insert(
            "finished_at".to_string(),
            json!({"timestampValue": conv.finished_at.to_rfc3339()}),
        );
        fields.insert(
            "source".to_string(),
            json!({"stringValue": conversation_source_wire(&conv.source)}),
        );
        fields.insert(
            "language".to_string(),
            json!({"stringValue": conv.language}),
        );
        fields.insert(
            "status".to_string(),
            json!({"stringValue": conversation_status_wire(&conv.status)}),
        );
        fields.insert(
            "discarded".to_string(),
            json!({"booleanValue": conv.discarded}),
        );
        fields.insert("deleted".to_string(), json!({"booleanValue": conv.deleted}));
        fields.insert("starred".to_string(), json!({"booleanValue": conv.starred}));
        fields.insert(
            "is_locked".to_string(),
            json!({"booleanValue": conv.is_locked}),
        );

        // Add folder_id if present
        if let Some(folder_id) = &conv.folder_id {
            fields.insert("folder_id".to_string(), json!({"stringValue": folder_id}));
        }

        // Add geolocation if present
        if let Some(geo) = &conv.geolocation {
            let mut geo_fields = serde_json::Map::new();
            if let Some(place_id) = &geo.google_place_id {
                geo_fields.insert(
                    "google_place_id".to_string(),
                    json!({"stringValue": place_id}),
                );
            }
            geo_fields.insert("latitude".to_string(), json!({"doubleValue": geo.latitude}));
            geo_fields.insert(
                "longitude".to_string(),
                json!({"doubleValue": geo.longitude}),
            );
            if let Some(address) = &geo.address {
                geo_fields.insert("address".to_string(), json!({"stringValue": address}));
            }
            if let Some(loc_type) = &geo.location_type {
                geo_fields.insert(
                    "location_type".to_string(),
                    json!({"stringValue": loc_type}),
                );
            }
            fields.insert(
                "geolocation".to_string(),
                json!({"mapValue": {"fields": geo_fields}}),
            );
        }

        // Add photos array
        if !conv.photos.is_empty() {
            let photos_values: Vec<Value> = conv
                .photos
                .iter()
                .map(|photo| {
                    let mut photo_fields = serde_json::Map::new();
                    if let Some(id) = &photo.id {
                        photo_fields.insert("id".to_string(), json!({"stringValue": id}));
                    }
                    photo_fields
                        .insert("base64".to_string(), json!({"stringValue": &photo.base64}));
                    if let Some(desc) = &photo.description {
                        photo_fields
                            .insert("description".to_string(), json!({"stringValue": desc}));
                    }
                    photo_fields.insert(
                        "created_at".to_string(),
                        json!({"timestampValue": photo.created_at.to_rfc3339()}),
                    );
                    photo_fields.insert(
                        "discarded".to_string(),
                        json!({"booleanValue": photo.discarded}),
                    );
                    json!({"mapValue": {"fields": photo_fields}})
                })
                .collect();
            fields.insert(
                "photos".to_string(),
                json!({"arrayValue": {"values": photos_values}}),
            );
        }

        // Build structured with action_items and events
        let mut structured_fields = serde_json::Map::new();
        structured_fields.insert(
            "title".to_string(),
            json!({"stringValue": conv.structured.title}),
        );
        structured_fields.insert(
            "overview".to_string(),
            json!({"stringValue": conv.structured.overview}),
        );
        structured_fields.insert(
            "emoji".to_string(),
            json!({"stringValue": conv.structured.emoji}),
        );
        structured_fields.insert(
            "category".to_string(),
            json!({"stringValue": category_wire(&conv.structured.category)}),
        );
        structured_fields.insert(
            "action_items".to_string(),
            json!({"arrayValue": {"values": action_items_values}}),
        );
        structured_fields.insert(
            "events".to_string(),
            json!({"arrayValue": {"values": events_values}}),
        );

        fields.insert(
            "structured".to_string(),
            json!({"mapValue": {"fields": structured_fields}}),
        );

        // Add transcript_segments — compressed (and optionally encrypted) to match Python backend
        {
            use flate2::write::ZlibEncoder;
            use flate2::Compression;
            use std::io::Write;

            // Step 1: Serialize segments to JSON array (matching Python's json.dumps format)
            let segments_json: Vec<serde_json::Value> = conv
                .transcript_segments
                .iter()
                .map(|seg| {
                    let mut segment = json!({
                        "text": seg.text,
                        "speaker": seg.speaker,
                        "speaker_id": seg.speaker_id,
                        "is_user": seg.is_user,
                        "start": seg.start,
                        "end": seg.end
                    });
                    if let Some(id) = &seg.id {
                        segment["id"] = json!(id);
                    }
                    if let Some(person_id) = &seg.person_id {
                        segment["person_id"] = json!(person_id);
                    }
                    segment
                })
                .collect();
            let json_str =
                serde_json::to_string(&segments_json).unwrap_or_else(|_| "[]".to_string());

            // Step 2: Zlib compress
            let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
            let _ = encoder.write_all(json_str.as_bytes());
            let compressed_bytes = encoder.finish().unwrap_or_default();

            // Step 3: Store as compressed bytes or encrypt if secret is available
            if let Some(ref secret) = self.encryption_secret {
                // Enhanced: hex encode compressed bytes → encrypt → store as stringValue
                let hex_str = hex::encode(&compressed_bytes);
                match encryption::encrypt(&hex_str, uid, secret) {
                    Ok(encrypted) => {
                        fields.insert(
                            "transcript_segments".to_string(),
                            json!({"stringValue": encrypted}),
                        );
                        fields.insert(
                            "data_protection_level".to_string(),
                            json!({"stringValue": "enhanced"}),
                        );
                    }
                    Err(e) => {
                        tracing::warn!("Failed to encrypt transcript segments: {}, falling back to compressed bytes", e);
                        let b64 =
                            base64::engine::general_purpose::STANDARD.encode(&compressed_bytes);
                        fields.insert(
                            "transcript_segments".to_string(),
                            json!({"bytesValue": b64}),
                        );
                    }
                }
            } else {
                // Standard: store as bytesValue (Firestore REST API expects base64 for bytes)
                let b64 = base64::engine::general_purpose::STANDARD.encode(&compressed_bytes);
                fields.insert(
                    "transcript_segments".to_string(),
                    json!({"bytesValue": b64}),
                );
            }
            fields.insert(
                "transcript_segments_compressed".to_string(),
                json!({"booleanValue": true}),
            );
        }

        // Add apps_results
        fields.insert(
            "apps_results".to_string(),
            json!({"arrayValue": {"values": apps_results_values}}),
        );

        // Add input_device_name if present
        if let Some(device_name) = &conv.input_device_name {
            fields.insert(
                "input_device_name".to_string(),
                json!({"stringValue": device_name}),
            );
        }

        json!({"fields": fields})
    }

    // Field parsing helpers
    pub(super) fn parse_string(&self, fields: &Value, key: &str) -> Option<String> {
        fields
            .get(key)?
            .get("stringValue")?
            .as_str()
            .map(|s| s.to_string())
    }

    pub(super) fn parse_bool(
        &self,
        fields: &Value,
        key: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        fields
            .get(key)
            .and_then(|v| v.get("booleanValue"))
            .and_then(|v| v.as_bool())
            .ok_or_else(|| format!("Missing or invalid bool field: {}", key).into())
    }

    pub(super) fn parse_int(&self, fields: &Value, key: &str) -> Option<i32> {
        fields
            .get(key)?
            .get("integerValue")?
            .as_str()
            .and_then(|s| s.parse().ok())
    }

    pub(super) fn parse_float(&self, fields: &Value, key: &str) -> Option<f64> {
        let value = fields.get(key)?;
        if let Some(double_value) = value.get("doubleValue").and_then(|v| v.as_f64()) {
            return Some(double_value);
        }
        value
            .get("integerValue")
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<f64>().ok())
    }

    pub(super) fn parse_timestamp(
        &self,
        fields: &Value,
        key: &str,
    ) -> Result<DateTime<Utc>, Box<dyn std::error::Error + Send + Sync>> {
        let ts = fields
            .get(key)
            .and_then(|v| v.get("timestampValue"))
            .and_then(|v| v.as_str())
            .ok_or_else(|| format!("Missing timestamp field: {}", key))?;

        DateTime::parse_from_rfc3339(ts)
            .map(|dt| dt.with_timezone(&Utc))
            .map_err(|e| format!("Invalid timestamp {}: {}", key, e).into())
    }

    pub(super) fn parse_timestamp_optional(
        &self,
        fields: &Value,
        key: &str,
    ) -> Option<DateTime<Utc>> {
        fields
            .get(key)
            .and_then(|v| v.get("timestampValue"))
            .and_then(|v| v.as_str())
            .and_then(|ts| DateTime::parse_from_rfc3339(ts).ok())
            .map(|dt| dt.with_timezone(&Utc))
    }
}

#[cfg(test)]
mod contract_tests {
    use super::*;

    fn fixture(name: &str) -> Value {
        let path = format!(
            "{}/../../../contract_tests/fixtures/{}",
            env!("CARGO_MANIFEST_DIR"),
            name
        );
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
    }

    fn secret_bytes(value: &Value) -> Vec<u8> {
        value["encryption_secret"]
            .as_str()
            .unwrap()
            .as_bytes()
            .to_vec()
    }

    #[test]
    fn contract_wire_values_match_python_enums() {
        let data = fixture("conversations.json");
        let expected = &data["wire_values"];

        assert_eq!(
            conversation_source_wire(&ConversationSource::ExternalIntegration),
            expected["source_external_integration"].as_str().unwrap()
        );
        assert_eq!(
            conversation_status_wire(&ConversationStatus::InProgress),
            expected["status_in_progress"].as_str().unwrap()
        );
        assert_eq!(
            category_wire(&Category::Romance),
            expected["category_romance"].as_str().unwrap()
        );
        assert_eq!(memory_category_wire(&MemoryCategory::Workflow), "workflow");
    }

    #[test]
    fn contract_parse_transcript_segments_reads_shared_standard_and_enhanced_fixtures() {
        let data = fixture("conversations.json");
        let service = FirestoreService::new_for_contract(Some(secret_bytes(&data)));
        let uid = data["uid"].as_str().unwrap();

        let standard_fields = json!({
            "data_protection_level": {"stringValue": "standard"},
            "transcript_segments": {"bytesValue": data["standard_compressed_transcript_b64"]},
            "transcript_segments_compressed": {"booleanValue": true}
        });
        let enhanced_fields = json!({
            "data_protection_level": {"stringValue": "enhanced"},
            "transcript_segments": {"stringValue": data["enhanced_encrypted_transcript"]},
            "transcript_segments_compressed": {"booleanValue": true}
        });

        let standard = service
            .parse_transcript_segments(&standard_fields, uid)
            .unwrap();
        let enhanced = service
            .parse_transcript_segments(&enhanced_fields, uid)
            .unwrap();

        assert_eq!(standard.len(), data["segments"].as_array().unwrap().len());
        assert_eq!(enhanced.len(), data["segments"].as_array().unwrap().len());
        assert_eq!(standard[0].text, "Hello from desktop");
        assert_eq!(enhanced[1].text, "Rust and Python should agree");
        assert_eq!(standard[0].person_id.as_deref(), Some("person-user"));
    }

    #[test]
    fn contract_parse_memory_reads_python_owned_fields_and_missing_visibility_as_public() {
        let data = fixture("memories.json");
        let service = FirestoreService::new_for_contract(Some(secret_bytes(&data)));
        let uid = data["uid"].as_str().unwrap();
        let doc = json!({
            "name": "projects/contract/databases/(default)/documents/users/contract-user-8547/memories/memory-1",
            "fields": {
                "content": {"stringValue": data["enhanced_encrypted_content"]},
                "category": {"stringValue": "workflow"},
                "created_at": {"timestampValue": data["created_at"]},
                "updated_at": {"timestampValue": data["created_at"]},
                "data_protection_level": {"stringValue": "enhanced"},
                "memory_id": {"stringValue": "conversation-1"},
                "conversation_id": {"stringValue": "conversation-1"},
                "valid_at": {"timestampValue": data["created_at"]},
                "invalid_at": {"timestampValue": "2026-02-03T04:05:06+00:00"},
                "superseded_by": {"stringValue": "memory-2"},
                "edited": {"booleanValue": true},
                "is_locked": {"booleanValue": true},
                "kg_extracted": {"booleanValue": true},
                "app_id": {"stringValue": "app-1"},
                "tags": {"arrayValue": {"values": [{"stringValue": "contract"}]}}
            }
        });

        let memory = service.parse_memory(&doc, uid).unwrap();

        assert_eq!(memory.id, "memory-1");
        assert_eq!(
            memory.content,
            data["enhanced_plain_content"].as_str().unwrap()
        );
        assert_eq!(memory.category, MemoryCategory::Workflow);
        assert_eq!(memory.visibility, "public");
        assert_eq!(memory.memory_id.as_deref(), Some("conversation-1"));
        assert!(memory.invalid_at.is_some());
        assert_eq!(memory.superseded_by.as_deref(), Some("memory-2"));
        assert!(memory.edited);
        assert!(memory.is_locked);
        assert!(memory.kg_extracted);
        assert_eq!(memory.app_id.as_deref(), Some("app-1"));
        assert_eq!(memory.tags, vec!["contract".to_string()]);
    }
}
