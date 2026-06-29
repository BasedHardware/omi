use super::*;

impl FirestoreService {
    pub(super) async fn get_user_document(
        &self,
        uid: &str,
    ) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to get user document: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        Ok(doc)
    }

    // =========================================================================
    // BYOK & SUBSCRIPTION (used by paywall + BYOK validation)
    // =========================================================================

    /// Read the BYOK enrollment state from `users/{uid}.byok` in Firestore.
    ///
    /// Returns `ByokState::default()` (inactive) on any parse error so a
    /// Firestore blip never blocks a user.
    pub async fn get_user_byok_state(
        &self,
        uid: &str,
    ) -> Result<crate::byok::ByokState, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        Ok(parse_byok_state_from_doc(&doc))
    }

    /// Read the effective subscription plan for paywall purposes.
    ///
    /// Mirrors Python's `get_user_valid_subscription()`:
    /// - Basic plan with active status → returns "basic"
    /// - Paid plan with `current_period_end` still in the future → returns the plan name
    /// - Paid plan with expired `current_period_end` → falls back to "basic"
    /// - Missing/unparseable → returns "basic" (fail-open)
    /// - Handles legacy `"free"` → `"basic"` migration
    pub async fn get_user_effective_plan(
        &self,
        uid: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let plan = parse_effective_plan_from_doc(&doc);

        // Log interesting fallback cases for paid plans
        if let Some(fields) = doc.get("fields") {
            if let Some(sub_fields) = fields
                .get("subscription")
                .and_then(|v| v.get("mapValue"))
                .and_then(|v| v.get("fields"))
            {
                let raw_plan = sub_fields
                    .get("plan")
                    .and_then(|v| v.get("stringValue"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("basic");

                if raw_plan != "basic" && raw_plan != "free" && plan == "basic" {
                    tracing::info!(
                        "paywall: paid plan '{}' fell back to basic for uid={} (expired or missing period_end)",
                        raw_plan, uid
                    );
                }
            }
        }

        Ok(plan)
    }

    /// Get user account creation time from Firebase Auth Identity Toolkit REST API.
    ///
    /// Returns creation timestamp in milliseconds, or None if lookup fails.
    /// Uses the same service-account auth as `delete_firebase_auth_user`.
    pub async fn get_user_creation_time(
        &self,
        project_id: &str,
        uid: &str,
    ) -> Result<Option<i64>, Box<dyn std::error::Error + Send + Sync>> {
        let access_token = self.get_access_token().await?;
        let url = format!(
            "https://identitytoolkit.googleapis.com/v1/projects/{}/accounts:lookup",
            project_id
        );

        let response = self
            .client
            .post(&url)
            .bearer_auth(access_token)
            .json(&serde_json::json!({ "localId": [uid] }))
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firebase accounts:lookup failed: {}", error_text).into());
        }

        let body: serde_json::Value = response.json().await?;

        // Response: { "users": [{ "createdAt": "1234567890000", ... }] }
        let created_at_ms = body
            .get("users")
            .and_then(|v| v.as_array())
            .and_then(|arr| arr.first())
            .and_then(|user| user.get("createdAt"))
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<i64>().ok());

        Ok(created_at_ms)
    }

    /// Update user document fields (partial update)
    pub(super) async fn update_user_fields(
        &self,
        uid: &str,
        fields: Value,
        update_mask: &[&str],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mask_params = update_mask
            .iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            mask_params
        );

        let doc = json!({ "fields": fields });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to update user fields: {}", error_text).into());
        }

        Ok(())
    }

    /// Get daily summary settings for a user
    pub async fn get_daily_summary_settings(
        &self,
        uid: &str,
    ) -> Result<DailySummarySettings, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(DailySummarySettings {
            enabled: self
                .parse_bool(fields, "daily_summary_enabled")
                .unwrap_or(true),
            hour: self
                .parse_int(fields, "daily_summary_hour_local")
                .unwrap_or(22),
        })
    }

    /// Update daily summary settings for a user
    pub async fn update_daily_summary_settings(
        &self,
        uid: &str,
        enabled: Option<bool>,
        hour: Option<i32>,
    ) -> Result<DailySummarySettings, Box<dyn std::error::Error + Send + Sync>> {
        // Get current settings
        let current = self.get_daily_summary_settings(uid).await?;

        let new_enabled = enabled.unwrap_or(current.enabled);
        let new_hour = hour.unwrap_or(current.hour);

        let fields = json!({
            "daily_summary_enabled": {"booleanValue": new_enabled},
            "daily_summary_hour_local": {"integerValue": new_hour.to_string()}
        });

        self.update_user_fields(
            uid,
            fields,
            &["daily_summary_enabled", "daily_summary_hour_local"],
        )
        .await?;

        Ok(DailySummarySettings {
            enabled: new_enabled,
            hour: new_hour,
        })
    }

    /// Get transcription preferences for a user
    pub async fn get_transcription_preferences(
        &self,
        uid: &str,
    ) -> Result<TranscriptionPreferences, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        // Parse nested transcription_preferences object
        let prefs = fields
            .get("transcription_preferences")
            .and_then(|p| p.get("mapValue"))
            .and_then(|m| m.get("fields"));

        if let Some(pref_fields) = prefs {
            Ok(TranscriptionPreferences {
                single_language_mode: self
                    .parse_bool(pref_fields, "single_language_mode")
                    .unwrap_or(false),
                vocabulary: self.parse_string_array(pref_fields, "vocabulary"),
            })
        } else {
            Ok(TranscriptionPreferences::default())
        }
    }

    /// Update transcription preferences for a user
    pub async fn update_transcription_preferences(
        &self,
        uid: &str,
        single_language_mode: Option<bool>,
        vocabulary: Option<Vec<String>>,
    ) -> Result<TranscriptionPreferences, Box<dyn std::error::Error + Send + Sync>> {
        // Get current settings
        let current = self.get_transcription_preferences(uid).await?;

        let new_single_language_mode = single_language_mode.unwrap_or(current.single_language_mode);
        let new_vocabulary = vocabulary.unwrap_or(current.vocabulary);

        let vocab_values: Vec<Value> = new_vocabulary
            .iter()
            .map(|v| json!({"stringValue": v}))
            .collect();

        let fields = json!({
            "transcription_preferences": {
                "mapValue": {
                    "fields": {
                        "single_language_mode": {"booleanValue": new_single_language_mode},
                        "vocabulary": {
                            "arrayValue": {
                                "values": vocab_values
                            }
                        }
                    }
                }
            }
        });

        self.update_user_fields(uid, fields, &["transcription_preferences"])
            .await?;

        Ok(TranscriptionPreferences {
            single_language_mode: new_single_language_mode,
            vocabulary: new_vocabulary,
        })
    }

    // MARK: - Assistant Settings

    /// Helper: parse a sub-map from Firestore fields
    fn parse_sub_map<'a>(&self, fields: &'a Value, key: &str) -> Option<&'a Value> {
        fields.get(key)?.get("mapValue")?.get("fields")
    }

    /// Helper: build a Firestore string array value
    fn build_string_array_value(&self, items: &[String]) -> Value {
        let values: Vec<Value> = items.iter().map(|v| json!({"stringValue": v})).collect();
        json!({"arrayValue": {"values": values}})
    }

    /// Helper: build a sub-map Firestore value from a serde_json::Map of fields
    fn build_sub_map_value(&self, map_fields: serde_json::Map<String, Value>) -> Value {
        json!({"mapValue": {"fields": map_fields}})
    }

    /// Get assistant settings from user document
    pub async fn get_assistant_settings(
        &self,
        uid: &str,
    ) -> Result<AssistantSettingsData, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        let settings_fields = self.parse_sub_map(fields, "assistant_settings");
        let update_channel = self.parse_string(fields, "update_channel");

        let Some(sf) = settings_fields else {
            return Ok(AssistantSettingsData {
                update_channel,
                ..AssistantSettingsData::default()
            });
        };

        // Parse shared settings
        let shared = self
            .parse_sub_map(sf, "shared")
            .map(|f| SharedAssistantSettingsData {
                cooldown_interval: self.parse_int(f, "cooldown_interval"),
                glow_overlay_enabled: self.parse_bool(f, "glow_overlay_enabled").ok(),
                analysis_delay: self.parse_int(f, "analysis_delay"),
                screen_analysis_enabled: self.parse_bool(f, "screen_analysis_enabled").ok(),
            });

        // Parse focus settings
        let focus = self.parse_sub_map(sf, "focus").map(|f| FocusSettingsData {
            enabled: self.parse_bool(f, "enabled").ok(),
            analysis_prompt: self.parse_string(f, "analysis_prompt"),
            cooldown_interval: self.parse_int(f, "cooldown_interval"),
            notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
            excluded_apps: Some(self.parse_string_array(f, "excluded_apps")),
        });

        // Parse task settings
        let task = self.parse_sub_map(sf, "task").map(|f| TaskSettingsData {
            enabled: self.parse_bool(f, "enabled").ok(),
            analysis_prompt: self.parse_string(f, "analysis_prompt"),
            extraction_interval: self.parse_float(f, "extraction_interval"),
            min_confidence: self.parse_float(f, "min_confidence"),
            notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
            allowed_apps: Some(self.parse_string_array(f, "allowed_apps")),
            browser_keywords: Some(self.parse_string_array(f, "browser_keywords")),
        });

        // Parse advice settings
        let advice = self
            .parse_sub_map(sf, "advice")
            .map(|f| AdviceSettingsData {
                enabled: self.parse_bool(f, "enabled").ok(),
                analysis_prompt: self.parse_string(f, "analysis_prompt"),
                extraction_interval: self.parse_float(f, "extraction_interval"),
                min_confidence: self.parse_float(f, "min_confidence"),
                notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
                excluded_apps: Some(self.parse_string_array(f, "excluded_apps")),
            });

        // Parse memory settings
        let memory = self
            .parse_sub_map(sf, "memory")
            .map(|f| MemorySettingsData {
                enabled: self.parse_bool(f, "enabled").ok(),
                analysis_prompt: self.parse_string(f, "analysis_prompt"),
                extraction_interval: self.parse_float(f, "extraction_interval"),
                min_confidence: self.parse_float(f, "min_confidence"),
                notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
                excluded_apps: Some(self.parse_string_array(f, "excluded_apps")),
            });

        let floating_bar =
            self.parse_sub_map(sf, "floating_bar")
                .map(|f| FloatingBarSettingsData {
                    voice_answers_enabled: self.parse_bool(f, "voice_answers_enabled").ok(),
                });

        Ok(AssistantSettingsData {
            shared,
            focus,
            task,
            advice,
            memory,
            floating_bar,
            update_channel,
        })
    }

    /// Update assistant settings (merge with existing)
    pub async fn update_assistant_settings(
        &self,
        uid: &str,
        data: &AssistantSettingsData,
    ) -> Result<AssistantSettingsData, Box<dyn std::error::Error + Send + Sync>> {
        let current_doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let current_fields = current_doc.get("fields").unwrap_or(&empty);
        let mut top_fields = self
            .parse_sub_map(current_fields, "assistant_settings")
            .and_then(|settings| settings.as_object())
            .cloned()
            .unwrap_or_default();
        let current = self.get_assistant_settings(uid).await?;

        // Build shared sub-map
        if data.shared.is_some() || current.shared.is_some() {
            let cur = current.shared.unwrap_or_default();
            let new = data.shared.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let ci = new.cooldown_interval.or(cur.cooldown_interval);
            if let Some(v) = ci {
                m.insert(
                    "cooldown_interval".into(),
                    json!({"integerValue": v.to_string()}),
                );
            }
            let go = new.glow_overlay_enabled.or(cur.glow_overlay_enabled);
            if let Some(v) = go {
                m.insert("glow_overlay_enabled".into(), json!({"booleanValue": v}));
            }
            let ad = new.analysis_delay.or(cur.analysis_delay);
            if let Some(v) = ad {
                m.insert(
                    "analysis_delay".into(),
                    json!({"integerValue": v.to_string()}),
                );
            }
            let sa = new.screen_analysis_enabled.or(cur.screen_analysis_enabled);
            if let Some(v) = sa {
                m.insert("screen_analysis_enabled".into(), json!({"booleanValue": v}));
            }
            if !m.is_empty() {
                top_fields.insert("shared".into(), self.build_sub_map_value(m));
            }
        }

        // Build focus sub-map
        if data.focus.is_some() || current.focus.is_some() {
            let cur = current.focus.unwrap_or_default();
            let new = data.focus.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en {
                m.insert("enabled".into(), json!({"booleanValue": v}));
            }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap {
                m.insert("analysis_prompt".into(), json!({"stringValue": v}));
            }
            let ci = new.cooldown_interval.or(cur.cooldown_interval);
            if let Some(v) = ci {
                m.insert(
                    "cooldown_interval".into(),
                    json!({"integerValue": v.to_string()}),
                );
            }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne {
                m.insert("notifications_enabled".into(), json!({"booleanValue": v}));
            }
            let ea = new.excluded_apps.or(cur.excluded_apps);
            if let Some(v) = ea {
                m.insert("excluded_apps".into(), self.build_string_array_value(&v));
            }
            if !m.is_empty() {
                top_fields.insert("focus".into(), self.build_sub_map_value(m));
            }
        }

        // Build task sub-map
        if data.task.is_some() || current.task.is_some() {
            let cur = current.task.unwrap_or_default();
            let new = data.task.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en {
                m.insert("enabled".into(), json!({"booleanValue": v}));
            }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap {
                m.insert("analysis_prompt".into(), json!({"stringValue": v}));
            }
            let ei = new.extraction_interval.or(cur.extraction_interval);
            if let Some(v) = ei {
                m.insert("extraction_interval".into(), json!({"doubleValue": v}));
            }
            let mc = new.min_confidence.or(cur.min_confidence);
            if let Some(v) = mc {
                m.insert("min_confidence".into(), json!({"doubleValue": v}));
            }
            let aa = new.allowed_apps.or(cur.allowed_apps);
            if let Some(v) = aa {
                m.insert("allowed_apps".into(), self.build_string_array_value(&v));
            }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne {
                m.insert("notifications_enabled".into(), json!({"booleanValue": v}));
            }
            let bk = new.browser_keywords.or(cur.browser_keywords);
            if let Some(v) = bk {
                m.insert("browser_keywords".into(), self.build_string_array_value(&v));
            }
            if !m.is_empty() {
                top_fields.insert("task".into(), self.build_sub_map_value(m));
            }
        }

        // Build advice sub-map
        if data.advice.is_some() || current.advice.is_some() {
            let cur = current.advice.unwrap_or_default();
            let new = data.advice.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en {
                m.insert("enabled".into(), json!({"booleanValue": v}));
            }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap {
                m.insert("analysis_prompt".into(), json!({"stringValue": v}));
            }
            let ei = new.extraction_interval.or(cur.extraction_interval);
            if let Some(v) = ei {
                m.insert("extraction_interval".into(), json!({"doubleValue": v}));
            }
            let mc = new.min_confidence.or(cur.min_confidence);
            if let Some(v) = mc {
                m.insert("min_confidence".into(), json!({"doubleValue": v}));
            }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne {
                m.insert("notifications_enabled".into(), json!({"booleanValue": v}));
            }
            let ea = new.excluded_apps.or(cur.excluded_apps);
            if let Some(v) = ea {
                m.insert("excluded_apps".into(), self.build_string_array_value(&v));
            }
            if !m.is_empty() {
                top_fields.insert("advice".into(), self.build_sub_map_value(m));
            }
        }

        // Build memory sub-map
        if data.memory.is_some() || current.memory.is_some() {
            let cur = current.memory.unwrap_or_default();
            let new = data.memory.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en {
                m.insert("enabled".into(), json!({"booleanValue": v}));
            }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap {
                m.insert("analysis_prompt".into(), json!({"stringValue": v}));
            }
            let ei = new.extraction_interval.or(cur.extraction_interval);
            if let Some(v) = ei {
                m.insert("extraction_interval".into(), json!({"doubleValue": v}));
            }
            let mc = new.min_confidence.or(cur.min_confidence);
            if let Some(v) = mc {
                m.insert("min_confidence".into(), json!({"doubleValue": v}));
            }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne {
                m.insert("notifications_enabled".into(), json!({"booleanValue": v}));
            }
            let ea = new.excluded_apps.or(cur.excluded_apps);
            if let Some(v) = ea {
                m.insert("excluded_apps".into(), self.build_string_array_value(&v));
            }
            if !m.is_empty() {
                top_fields.insert("memory".into(), self.build_sub_map_value(m));
            }
        }

        if data.floating_bar.is_some() || current.floating_bar.is_some() {
            let cur = current.floating_bar.unwrap_or_default();
            let new = data.floating_bar.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let vae = new.voice_answers_enabled.or(cur.voice_answers_enabled);
            if let Some(v) = vae {
                m.insert("voice_answers_enabled".into(), json!({"booleanValue": v}));
            }
            if !m.is_empty() {
                top_fields.insert("floating_bar".into(), self.build_sub_map_value(m));
            }
        }

        if !top_fields.is_empty() {
            let fields = json!({
                "assistant_settings": {
                    "mapValue": {
                        "fields": Value::Object(top_fields)
                    }
                }
            });

            self.update_user_fields(uid, fields, &["assistant_settings"])
                .await?;
        }

        // Write update_channel as top-level field on user doc (not inside assistant_settings)
        if let Some(ref channel) = data.update_channel {
            let fields = json!({
                "update_channel": {
                    "stringValue": channel
                }
            });
            self.update_user_fields(uid, fields, &["update_channel"])
                .await?;
        }

        // Return merged state
        self.get_assistant_settings(uid).await
    }

    /// Get user email from Firestore profile
    pub async fn get_user_email(
        &self,
        uid: &str,
    ) -> Result<Option<String>, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);
        Ok(self.parse_string(fields, "email"))
    }

    /// Get user language preference
    pub async fn get_user_language(
        &self,
        uid: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(self
            .parse_string(fields, "language")
            .unwrap_or_else(|| "en".to_string()))
    }

    /// Update user language preference
    /// Languages supported by Deepgram Nova-3 multi-language auto-detection.
    const MULTI_LANGUAGE_SUPPORTED: &[&str] = &[
        "en", "en-US", "en-AU", "en-GB", "en-IN", "en-NZ", "es", "es-419", "fr", "fr-CA", "de",
        "hi", "ru", "pt", "pt-BR", "pt-PT", "ja", "it", "nl",
    ];

    pub async fn update_user_language(
        &self,
        uid: &str,
        language: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Set language field
        let lang_fields = json!({
            "language": {"stringValue": language}
        });
        self.update_user_fields(uid, lang_fields, &["language"])
            .await?;

        // Auto-set single_language_mode based on whether the language supports multi-language
        let single_language_mode = !Self::MULTI_LANGUAGE_SUPPORTED.contains(&language);
        self.update_transcription_preferences(uid, Some(single_language_mode), None)
            .await?;

        Ok(())
    }

    /// Get recording permission for a user
    pub async fn get_recording_permission(
        &self,
        uid: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(self
            .parse_bool(fields, "store_recording_permission")
            .unwrap_or(false))
    }

    /// Set recording permission for a user
    pub async fn set_recording_permission(
        &self,
        uid: &str,
        enabled: bool,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let fields = json!({
            "store_recording_permission": {"booleanValue": enabled}
        });

        self.update_user_fields(uid, fields, &["store_recording_permission"])
            .await
    }

    /// Get private cloud sync setting for a user
    pub async fn get_private_cloud_sync(
        &self,
        uid: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        // Default to true if not set
        Ok(self
            .parse_bool(fields, "private_cloud_sync_enabled")
            .unwrap_or(true))
    }

    /// Set private cloud sync setting for a user
    pub async fn set_private_cloud_sync(
        &self,
        uid: &str,
        enabled: bool,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let fields = json!({
            "private_cloud_sync_enabled": {"booleanValue": enabled}
        });

        self.update_user_fields(uid, fields, &["private_cloud_sync_enabled"])
            .await
    }

    /// Get notification settings for a user
    pub async fn get_notification_settings(
        &self,
        uid: &str,
    ) -> Result<NotificationSettings, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(NotificationSettings {
            enabled: self
                .parse_bool(fields, "notifications_enabled")
                .unwrap_or(true),
            frequency: self
                .parse_int(fields, "notification_frequency")
                .unwrap_or(3),
        })
    }

    /// Update notification settings for a user
    pub async fn update_notification_settings(
        &self,
        uid: &str,
        enabled: Option<bool>,
        frequency: Option<i32>,
    ) -> Result<NotificationSettings, Box<dyn std::error::Error + Send + Sync>> {
        // Get current settings
        let current = self.get_notification_settings(uid).await?;

        let new_enabled = enabled.unwrap_or(current.enabled);
        let new_frequency = frequency.unwrap_or(current.frequency);

        let fields = json!({
            "notifications_enabled": {"booleanValue": new_enabled},
            "notification_frequency": {"integerValue": new_frequency.to_string()}
        });

        self.update_user_fields(
            uid,
            fields,
            &["notifications_enabled", "notification_frequency"],
        )
        .await?;

        Ok(NotificationSettings {
            enabled: new_enabled,
            frequency: new_frequency,
        })
    }

    /// Get user profile
    pub async fn get_user_profile(
        &self,
        uid: &str,
    ) -> Result<UserProfile, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(UserProfile {
            uid: uid.to_string(),
            email: self.parse_string(fields, "email"),
            name: self.parse_string(fields, "name"),
            time_zone: self.parse_string(fields, "time_zone"),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .map(|dt| dt.to_rfc3339()),
            motivation: self.parse_string(fields, "motivation"),
            use_case: self.parse_string(fields, "use_case"),
            job: self.parse_string(fields, "job"),
            company: self.parse_string(fields, "company"),
        })
    }

    /// Update user profile fields (onboarding data)
    pub async fn update_user_profile(
        &self,
        uid: &str,
        name: Option<String>,
        motivation: Option<String>,
        use_case: Option<String>,
        job: Option<String>,
        company: Option<String>,
    ) -> Result<UserProfile, Box<dyn std::error::Error + Send + Sync>> {
        let mut fields = json!({});
        let mut mask: Vec<&str> = Vec::new();

        if let Some(ref v) = name {
            fields["name"] = json!({"stringValue": v});
            mask.push("name");
        }
        if let Some(ref v) = motivation {
            fields["motivation"] = json!({"stringValue": v});
            mask.push("motivation");
        }
        if let Some(ref v) = use_case {
            fields["use_case"] = json!({"stringValue": v});
            mask.push("use_case");
        }
        if let Some(ref v) = job {
            fields["job"] = json!({"stringValue": v});
            mask.push("job");
        }
        if let Some(ref v) = company {
            fields["company"] = json!({"stringValue": v});
            mask.push("company");
        }

        if !mask.is_empty() {
            self.update_user_fields(uid, fields, &mask).await?;
        }

        self.get_user_profile(uid).await
    }

    // =========================================================================
    // USER PERSONA
    // =========================================================================

    /// Get AI-generated user profile from user document
    pub async fn get_ai_user_profile(
        &self,
        uid: &str,
    ) -> Result<Option<AIUserProfile>, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        let profile_fields = fields
            .get("ai_user_profile")
            .and_then(|p| p.get("mapValue"))
            .and_then(|m| m.get("fields"));

        if let Some(pf) = profile_fields {
            let profile_text = self.parse_string(pf, "profile_text").unwrap_or_default();
            let generated_at = self.parse_timestamp(pf, "generated_at")?;
            let data_sources_used = self.parse_int(pf, "data_sources_used").unwrap_or(0);

            Ok(Some(AIUserProfile {
                profile_text,
                generated_at,
                data_sources_used,
            }))
        } else {
            Ok(None)
        }
    }

    /// Update AI-generated user profile in user document
    pub async fn update_ai_user_profile(
        &self,
        uid: &str,
        profile_text: &str,
        generated_at: &str,
        data_sources_used: i32,
    ) -> Result<AIUserProfile, Box<dyn std::error::Error + Send + Sync>> {
        let generated_at_dt = DateTime::parse_from_rfc3339(generated_at)
            .map(|dt| dt.with_timezone(&Utc))
            .map_err(|e| format!("Invalid generated_at timestamp: {}", e))?;

        let fields = json!({
            "ai_user_profile": {
                "mapValue": {
                    "fields": {
                        "profile_text": {"stringValue": profile_text},
                        "generated_at": {"timestampValue": generated_at},
                        "data_sources_used": {"integerValue": data_sources_used.to_string()}
                    }
                }
            }
        });

        self.update_user_fields(uid, fields, &["ai_user_profile"])
            .await?;

        Ok(AIUserProfile {
            profile_text: profile_text.to_string(),
            generated_at: generated_at_dt,
            data_sources_used,
        })
    }
}
