use omi_agent_runtime::provider_policy::ManagedTransport;
use omi_agent_runtime::{
    emit_line, parse_line, select_execution_mode, ExecutionMode, Message, PROTOCOL_VERSION,
};
use rx4::{Agent, Event};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::env;
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::{mpsc, watch};

const RUNTIME_VERSION: &str = env!("CARGO_PKG_VERSION");

macro_rules! required_fields {
    ($fields:expr, $($name:literal),+ $(,)?) => {
        (|| Some(($(string_field($fields, $name)?),+)))()
    };
}

#[derive(Clone)]
struct ManagedCredentials {
    owner_id: String,
    bearer_token: String,
}

#[derive(Clone)]
struct ExecutionProfile {
    generation: u64,
    adapter_id: String,
    model_profile: Option<String>,
    working_directory: String,
    execution_role: &'static str,
}

#[derive(Clone)]
struct SurfaceSession {
    owner_id: String,
    surface_kind: String,
    conversation_id: String,
    profile: ExecutionProfile,
}

#[derive(Clone)]
struct ContextSource {
    source_revision: String,
    outcome: String,
    captured_at_ms: u64,
    expires_at_ms: Option<u64>,
    payload: Map<String, Value>,
}

#[derive(Clone)]
struct OwnerRevocationReceipt {
    owner_id: String,
    revoked_run_ids: Vec<String>,
}

struct Runtime {
    managed_base_url: Option<String>,
    credentials: Option<ManagedCredentials>,
    running: HashMap<String, watch::Sender<bool>>,
    preferences: HashMap<String, ExecutionProfile>,
    sessions: HashMap<String, SurfaceSession>,
    surfaces: HashMap<(String, String, String, String), String>,
    context_sources: HashMap<(String, String, String), ContextSource>,
    next_session: u64,
    owner_id: Option<String>,
    last_revocation: Option<OwnerRevocationReceipt>,
    journal: JournalStore,
    output: mpsc::UnboundedSender<Message>,
    completed: mpsc::UnboundedSender<String>,
}

impl Runtime {
    fn new(
        managed_base_url: Option<String>,
        journal: JournalStore,
        output: mpsc::UnboundedSender<Message>,
        completed: mpsc::UnboundedSender<String>,
    ) -> Self {
        Self {
            managed_base_url,
            credentials: None,
            running: HashMap::new(),
            preferences: HashMap::new(),
            sessions: HashMap::new(),
            surfaces: HashMap::new(),
            context_sources: HashMap::new(),
            next_session: 1,
            owner_id: None,
            last_revocation: None,
            journal,
            output,
            completed,
        }
    }

    fn emit(&self, kind: &str, fields: Map<String, Value>) {
        let _ = self.output.send(Message {
            kind: kind.into(),
            fields,
        });
    }

    fn handle(&mut self, input: Message) {
        if is_owner_scoped_message(&input.kind) && !self.require_active_owner(&input.fields) {
            return;
        }
        match input.kind.as_str() {
            "refresh_token" => self.refresh_token(input.fields),
            "refresh_owner" => self.refresh_owner(input.fields),
            "revoke_owner_runtime" => self.revoke_owner_runtime(input.fields),
            "configure_default_execution_profile" => {
                self.configure_default_execution_profile(input.fields)
            }
            "resolve_surface_session" => self.resolve_surface_session(input.fields),
            "migrate_session_execution_profile" => {
                self.migrate_session_execution_profile(input.fields)
            }
            "context_source_update" => self.context_source_update(input.fields),
            "get_context_snapshot" => self.get_context_snapshot(input.fields),
            "invalidate_session" => self.invalidate_session(input.fields),
            "journal_record_turn" => self.journal_record_turn(input.fields),
            "journal_record_exchange" => self.journal_record_exchange(input.fields),
            "journal_update_turn" => self.journal_update_turn(input.fields),
            "journal_terminalize_turn" => self.journal_terminalize_turn(input.fields),
            "journal_list_turns" => self.journal_list_turns(input.fields),
            "journal_clear_turns" => self.journal_clear_turns(input.fields),
            "query" => self.query(input.fields),
            "interrupt" => self.interrupt(input.fields),
            "stop" => self.stop(),
            _ => {}
        }
    }

    fn require_active_owner(&self, fields: &Map<String, Value>) -> bool {
        let requested_owner = string_field(fields, "ownerId");
        let authorized = self
            .owner_id
            .as_ref()
            .is_some_and(|owner_id| requested_owner.as_deref() == Some(owner_id));
        if !authorized {
            self.emit_error(
                string_field(fields, "requestId"),
                string_field(fields, "clientId"),
                "authentication",
                "request owner does not match the active runtime owner",
            );
        }
        authorized
    }

    fn configure_default_execution_profile(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id, owner_id, adapter_id, working_directory)) = required_fields!(
            &fields,
            "requestId",
            "clientId",
            "ownerId",
            "adapterId",
            "workingDirectory"
        ) else {
            self.invalid_request(&fields, "execution profile requires requestId, clientId, ownerId, adapterId, and workingDirectory");
            return;
        };
        if !valid_adapter(&adapter_id) || working_directory.trim().is_empty() {
            self.invalid_request(
                &fields,
                "execution profile requires rx4 and a working directory",
            );
            return;
        }
        let expected_generation = fields
            .get("expectedPreferenceGeneration")
            .and_then(Value::as_u64);
        if fields.contains_key("expectedPreferenceGeneration") && expected_generation.is_none() {
            self.invalid_request(
                &fields,
                "default execution profile preference generation is invalid",
            );
            return;
        }
        let previous = self.preferences.get(&owner_id);
        if expected_generation.is_some_and(|generation| {
            generation != previous.map_or(0, |profile| profile.generation)
        }) {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "default execution profile preference generation is stale",
            );
            return;
        }
        let model_profile = optional_string_field(&fields, "modelProfile");
        let profile = match previous {
            Some(profile)
                if profile.adapter_id == adapter_id
                    && profile.model_profile == model_profile
                    && profile.working_directory == working_directory =>
            {
                profile.clone()
            }
            Some(profile) => ExecutionProfile {
                generation: profile.generation + 1,
                adapter_id,
                model_profile,
                working_directory,
                execution_role: "coordinator",
            },
            None => ExecutionProfile {
                generation: 1,
                adapter_id,
                model_profile,
                working_directory,
                execution_role: "coordinator",
            },
        };
        self.preferences.insert(owner_id, profile.clone());
        self.emit(
            "default_execution_profile_configured",
            envelope(
                Some(&request_id),
                Some(&client_id),
                json!({
                    "preferenceGeneration": profile.generation,
                    "adapterId": profile.adapter_id,
                    "credentialScope": "managed_cloud",
                    "modelProfile": profile.model_profile,
                    "workingDirectory": profile.working_directory,
                    "appliesTo": "new_sessions"
                }),
            ),
        );
    }

    fn resolve_surface_session(&mut self, fields: Map<String, Value>) {
        let Some((
            request_id,
            client_id,
            owner_id,
            surface_kind,
            external_ref_kind,
            external_ref_id,
        )) = required_fields!(
            &fields,
            "requestId",
            "clientId",
            "ownerId",
            "surfaceKind",
            "externalRefKind",
            "externalRefId"
        )
        else {
            self.invalid_request(
                &fields,
                "surface session requires requestId, clientId, ownerId, and surface reference",
            );
            return;
        };
        let key = (
            owner_id.clone(),
            surface_kind.clone(),
            external_ref_kind,
            external_ref_id,
        );
        let session_id = self.surfaces.get(&key).cloned();
        let created = session_id.is_none();
        if fields.contains_key("creationProfile") && creation_profile(&fields).is_none() {
            self.invalid_request(
                &fields,
                "session creation profile requires rx4 and a working directory",
            );
            return;
        }
        let session_id = session_id.unwrap_or_else(|| {
            let profile = creation_profile(&fields).unwrap_or_else(|| {
                self.preferences
                    .get(&owner_id)
                    .cloned()
                    .unwrap_or_else(default_profile)
            });
            let session_id = format!("rx4-session-{}", self.next_session);
            self.next_session += 1;
            let conversation_id = format!("rx4-conversation-{}", self.next_session - 1);
            self.sessions.insert(
                session_id.clone(),
                SurfaceSession {
                    owner_id: owner_id.clone(),
                    surface_kind: surface_kind.clone(),
                    conversation_id,
                    profile,
                },
            );
            self.surfaces.insert(key, session_id.clone());
            session_id
        });
        let Some(session) = self.sessions.get(&session_id) else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "runtime_error",
                "surface session is unavailable",
            );
            return;
        };
        self.emit(
            "surface_session_resolved",
            envelope(
                Some(&request_id),
                Some(&client_id),
                json!({
                    "created": created,
                    "conversationId": session.conversation_id,
                    "sessionId": session_id,
                    "profile": profile_json(&session.profile)
                }),
            ),
        );
    }

    fn migrate_session_execution_profile(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id, owner_id, session_id, adapter_id, working_directory)) = required_fields!(
            &fields,
            "requestId",
            "clientId",
            "ownerId",
            "sessionId",
            "adapterId",
            "workingDirectory"
        ) else {
            self.invalid_request(&fields, "profile migration requires requestId, clientId, ownerId, sessionId, adapterId, and workingDirectory");
            return;
        };
        let expected_generation = fields
            .get("expectedProfileGeneration")
            .and_then(Value::as_u64);
        let Some(session) = self.sessions.get_mut(&session_id) else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "agent session is unavailable",
            );
            return;
        };
        if session.owner_id != owner_id
            || !valid_adapter(&adapter_id)
            || working_directory.trim().is_empty()
        {
            self.invalid_request(
                &fields,
                "profile migration is not authorized for this session",
            );
            return;
        }
        if expected_generation != Some(session.profile.generation) {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "session execution profile generation is stale",
            );
            return;
        }
        let previous_generation = session.profile.generation;
        session.profile = ExecutionProfile {
            generation: previous_generation + 1,
            adapter_id,
            model_profile: optional_string_field(&fields, "modelProfile"),
            working_directory,
            execution_role: session.profile.execution_role,
        };
        let profile = session.profile.clone();
        self.emit(
            "session_execution_profile_migrated",
            envelope(
                Some(&request_id),
                Some(&client_id),
                json!({
                    "sessionId": session_id,
                    "previousProfileGeneration": previous_generation,
                    "profile": profile_json(&profile),
                    "staleBindingIds": []
                }),
            ),
        );
    }

    fn context_source_update(&mut self, fields: Map<String, Value>) {
        let Some((
            request_id,
            client_id,
            owner_id,
            session_id,
            surface_kind,
            source,
            source_revision,
            outcome,
        )) = required_fields!(
            &fields,
            "requestId",
            "clientId",
            "ownerId",
            "sessionId",
            "surfaceKind",
            "source",
            "sourceRevision",
            "outcome"
        )
        else {
            self.invalid_request(&fields, "context update requires requestId, clientId, ownerId, sessionId, surfaceKind, source, sourceRevision, and outcome");
            return;
        };
        let captured_at_ms = fields.get("capturedAtMs").and_then(Value::as_u64);
        let expires_at_ms = fields.get("expiresAtMs").and_then(Value::as_u64);
        let payload = fields.get("payload").and_then(Value::as_object).cloned();
        if !self.session_is_owned(&session_id, &owner_id)
            || !valid_context_source(&source)
            || !valid_context_outcome(&outcome)
            || source_revision.len() > 256
            || source_revision.trim().is_empty()
            || captured_at_ms.is_none()
            || (fields.contains_key("expiresAtMs") && expires_at_ms.is_none())
            || payload.is_none()
            || expires_at_ms.is_some_and(|expires| expires < captured_at_ms.unwrap_or_default())
        {
            self.invalid_request(&fields, "context update is invalid for this session");
            return;
        }
        let source_surface_kind = if source == "surface" {
            surface_kind.clone()
        } else {
            String::new()
        };
        let key = (session_id.clone(), source_surface_kind, source.clone());
        let update = ContextSource {
            source_revision: source_revision.clone(),
            outcome,
            captured_at_ms: captured_at_ms.unwrap_or_default(),
            expires_at_ms,
            payload: payload.unwrap_or_default(),
        };
        let changed = self.context_sources.get(&key).is_none_or(|previous| {
            previous.source_revision != update.source_revision
                || previous.outcome != update.outcome
                || previous.payload != update.payload
                || previous.captured_at_ms != update.captured_at_ms
                || previous.expires_at_ms != update.expires_at_ms
        });
        self.context_sources.insert(key, update);
        let snapshot = self.snapshot(&session_id, &owner_id, &surface_kind);
        self.emit(
            "context_source_updated",
            envelope(
                Some(&request_id),
                Some(&client_id),
                json!({
                    "sessionId": session_id,
                    "source": source,
                    "sourceRevision": source_revision,
                    "changed": changed,
                    "snapshotVersion": snapshot["version"],
                    "snapshotGeneration": snapshot["snapshotGeneration"],
                    "rendererFingerprint": snapshot["rendererFingerprint"],
                    "capabilityVersion": snapshot["capabilityVersion"]
                }),
            ),
        );
    }

    fn get_context_snapshot(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id, owner_id, session_id, surface_kind)) = required_fields!(
            &fields,
            "requestId",
            "clientId",
            "ownerId",
            "sessionId",
            "surfaceKind"
        ) else {
            self.invalid_request(&fields, "context snapshot requires requestId, clientId, ownerId, sessionId, and surfaceKind");
            return;
        };
        if !self.session_is_owned(&session_id, &owner_id) {
            self.invalid_request(
                &fields,
                "context snapshot is not authorized for this session",
            );
            return;
        }
        self.emit(
            "context_snapshot",
            envelope(
                Some(&request_id),
                Some(&client_id),
                json!({"snapshot": self.snapshot(&session_id, &owner_id, &surface_kind)}),
            ),
        );
    }

    fn invalidate_session(&mut self, fields: Map<String, Value>) {
        let Some((owner_id, surface_kind, external_ref_kind, external_ref_id)) = required_fields!(
            &fields,
            "ownerId",
            "surfaceKind",
            "externalRefKind",
            "externalRefId"
        ) else {
            return;
        };
        let key = (owner_id, surface_kind, external_ref_kind, external_ref_id);
        let _ = self.surfaces.get(&key);
    }

    fn journal_record_turn(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal record requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal record requires a surface reference");
            return;
        };
        let Some(turn) = fields.get("turn").and_then(Value::as_object) else {
            self.invalid_request(&fields, "journal record requires turn");
            return;
        };
        match self.journal.record(&surface, turn) {
            Ok(page) => {
                self.emit_journal_result("record", &request_id, &client_id, &surface, page, true)
            }
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
            }
        }
    }

    fn journal_record_exchange(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal exchange requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal exchange requires a surface reference");
            return;
        };
        let Some(turns) = fields.get("turns").and_then(Value::as_array) else {
            self.invalid_request(&fields, "journal exchange requires turns");
            return;
        };
        let turns = turns
            .iter()
            .map(Value::as_object)
            .collect::<Option<Vec<_>>>();
        match turns {
            Some(turns) => match self
                .journal
                .record_many(&surface, &turns.into_iter().cloned().collect::<Vec<_>>())
            {
                Ok(page) => self.emit_journal_result(
                    "record_exchange",
                    &request_id,
                    &client_id,
                    &surface,
                    page,
                    true,
                ),
                Err(error) => {
                    self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
                }
            },
            None => self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "journal exchange is invalid",
            ),
        }
    }

    fn journal_update_turn(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal update requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal update requires a surface reference");
            return;
        };
        let Some(update) = fields.get("update").and_then(Value::as_object) else {
            self.invalid_request(&fields, "journal update requires update");
            return;
        };
        match self.journal.update(&surface, update) {
            Ok(page) => {
                self.emit_journal_result("update", &request_id, &client_id, &surface, page, true)
            }
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
            }
        }
    }

    fn journal_terminalize_turn(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(
                &fields,
                "journal terminalization requires requestId and clientId",
            );
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(
                &fields,
                "journal terminalization requires a surface reference",
            );
            return;
        };
        let Some(terminalization) = fields.get("terminalization").and_then(Value::as_object) else {
            self.invalid_request(&fields, "journal terminalization requires terminalization");
            return;
        };
        match self.journal.terminalize(&surface, terminalization) {
            Ok(page) => self.emit_journal_result(
                "terminalize",
                &request_id,
                &client_id,
                &surface,
                page,
                true,
            ),
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
            }
        }
    }

    fn journal_list_turns(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal list requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal list requires a surface reference");
            return;
        };
        let after = fields
            .get("afterTurnSeq")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let limit = fields.get("limit").and_then(Value::as_u64).unwrap_or(100);
        match self.journal.list(&surface, after, limit) {
            Ok(page) => {
                self.emit_journal_result("list", &request_id, &client_id, &surface, page, false)
            }
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
            }
        }
    }

    fn journal_clear_turns(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal clear requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal clear requires a surface reference");
            return;
        };
        let expected = fields.get("expectedGeneration").and_then(Value::as_u64);
        if fields.contains_key("expectedGeneration") && expected.is_none() {
            self.invalid_request(&fields, "journal expected generation is invalid");
            return;
        }
        match self.journal.clear(&surface, expected) {
            Ok(page) => {
                self.emit_journal_result("clear", &request_id, &client_id, &surface, page, false)
            }
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
            }
        }
    }

    fn emit_journal_result(
        &self,
        operation: &str,
        request_id: &str,
        client_id: &str,
        surface: &JournalSurface,
        page: JournalResultPage,
        emit_changes: bool,
    ) {
        let turn = page.turn.clone();
        let turns = page.turns.clone();
        self.emit("journal_operation_result", envelope(Some(request_id), Some(client_id), json!({
            "operation": operation, "conversationId": page.conversation_id, "surfaceKind": surface.surface_kind,
            "externalRefKind": surface.external_ref_kind, "externalRefId": surface.external_ref_id,
            "turn": turn, "turns": turns, "clearedCount": page.cleared_count,
            "highWaterTurnSeq": page.high_water_turn_seq, "conversationGeneration": page.generation,
            "generationBaseTurnSeq": page.generation_base_turn_seq
        })));
        if emit_changes {
            for turn in page.turns {
                self.emit("journal_turn_changed", envelope(None, None, json!({"ownerId": surface.owner_id, "conversationGeneration": page.generation, "generationBaseTurnSeq": page.generation_base_turn_seq, "surfaceKind": surface.surface_kind, "externalRefKind": surface.external_ref_kind, "externalRefId": surface.external_ref_id, "turn": turn})));
            }
        }
    }

    fn session_is_owned(&self, session_id: &str, owner_id: &str) -> bool {
        self.sessions
            .get(session_id)
            .is_some_and(|session| session.owner_id == owner_id)
    }

    fn snapshot(&self, session_id: &str, owner_id: &str, surface_kind: &str) -> Value {
        let Some(session) = self.sessions.get(session_id) else {
            return json!({});
        };
        let mut source_outcomes = context_source_kinds()
            .iter()
            .map(|source| {
                let source_state = self
                    .context_sources
                    .iter()
                    .find(
                        |((stored_session_id, stored_surface_kind, stored_source), _)| {
                            stored_session_id == session_id
                                && stored_source == source
                                && (stored_source != "surface"
                                    || stored_surface_kind == surface_kind)
                        },
                    )
                    .map(|(_, source_state)| source_state);
                match source_state {
                    Some(source_state) => json!({
                        "source": source,
                        "sourceRevision": source_state.source_revision,
                        "outcome": source_state.outcome,
                        "capturedAtMs": source_state.captured_at_ms,
                        "expiresAtMs": source_state.expires_at_ms,
                        "payloadHash": hash_json(&Value::Object(source_state.payload.clone())),
                        "payload": source_state.payload
                    }),
                    None => json!({
                        "source": source,
                        "sourceRevision": "kernel:missing@1",
                        "outcome": "unavailable",
                        "capturedAtMs": 0,
                        "expiresAtMs": Value::Null,
                        "payloadHash": hash_text(&format!("context-source-missing@1:{source}")),
                        "payload": {}
                    }),
                }
            })
            .collect::<Vec<_>>();
        source_outcomes
            .sort_by(|left, right| left["source"].as_str().cmp(&right["source"].as_str()));
        let version = hash_json(
            &json!({"ownerId": owner_id, "sessionId": session_id, "sourceOutcomes": source_outcomes}),
        );
        json!({
            "snapshotId": format!("{session_id}:{version}"),
            "version": version,
            "snapshotGeneration": 1,
            "rendererFingerprint": hash_text(&session.surface_kind),
            "rendererPolicyVersion": "omi-rx4-context@1",
            "capabilityVersion": "omi-rx4-tools@1",
            "renderedContext": "",
            "ownerId": owner_id,
            "sessionId": session_id,
            "conversationId": session.conversation_id,
            "recentTurns": [],
            "sourceOutcomes": source_outcomes,
            "activeRuns": [],
            "recentCompletedRuns": [],
            "capabilities": {"executionRole": session.profile.execution_role, "manifestVersion": 1, "manifestDigest": "rx4", "allowedToolNames": []},
            "contextPlan": {"version": 1, "planId": format!("{session_id}:plan"), "semanticGuidanceVersion": "omi-rx4-semantic@1", "semanticGuidance": "", "retainedTurnStartSeq": Value::Null, "retainedTurnEndSeq": Value::Null, "retainedTurnCount": 0, "totalTurnCount": 0, "omittedTurnCount": 0, "olderHistoryStrategy": "none", "stableCacheIdentity": format!("{session_id}:stable"), "dynamicContextIdentity": version}
        })
    }

    fn invalid_request(&self, fields: &Map<String, Value>, message: &str) {
        self.emit_error(
            string_field(fields, "requestId"),
            string_field(fields, "clientId"),
            "invalid_request",
            message,
        );
    }

    fn refresh_token(&mut self, fields: Map<String, Value>) {
        let Some(owner_id) = string_field(&fields, "ownerId") else {
            return;
        };
        let Some(bearer_token) = string_field(&fields, "token") else {
            return;
        };
        if !self.establish_owner(&owner_id) {
            return;
        }
        self.credentials = Some(ManagedCredentials {
            owner_id,
            bearer_token,
        });
        self.last_revocation = None;
    }

    fn refresh_owner(&mut self, fields: Map<String, Value>) {
        let Some(owner_id) = string_field(&fields, "ownerId") else {
            return;
        };
        if self.establish_owner(&owner_id) {
            self.last_revocation = None;
        }
    }

    fn establish_owner(&mut self, owner_id: &str) -> bool {
        match self.owner_id.as_deref() {
            None => {
                self.owner_id = Some(owner_id.to_owned());
                true
            }
            Some(active_owner) => active_owner == owner_id,
        }
    }

    fn revoke_owner_runtime(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id, owner_id)) =
            required_fields!(&fields, "requestId", "clientId", "ownerId")
        else {
            let owner_id = string_field(&fields, "ownerId").unwrap_or_default();
            self.emit_owner_revocation(
                string_field(&fields, "requestId"),
                string_field(&fields, "clientId"),
                owner_id,
                false,
                false,
                Vec::new(),
            );
            return;
        };
        if self.owner_id.is_none() {
            if let Some(receipt) = self
                .last_revocation
                .as_ref()
                .filter(|receipt| receipt.owner_id == owner_id)
            {
                self.emit_owner_revocation(
                    Some(request_id),
                    Some(client_id),
                    owner_id,
                    true,
                    true,
                    receipt.revoked_run_ids.clone(),
                );
                return;
            }
            self.emit_owner_revocation(
                Some(request_id),
                Some(client_id),
                owner_id,
                false,
                false,
                Vec::new(),
            );
            return;
        }
        if self.owner_id.as_deref() != Some(owner_id.as_str()) {
            self.emit_owner_revocation(
                Some(request_id),
                Some(client_id),
                owner_id,
                false,
                false,
                Vec::new(),
            );
            return;
        }
        let mut revoked_run_ids = self.running.keys().cloned().collect::<Vec<_>>();
        revoked_run_ids.sort();
        for cancel in self.running.values() {
            let _ = cancel.send(true);
        }
        self.clear_owner_state(&owner_id);
        self.owner_id = None;
        self.credentials = None;
        self.last_revocation = Some(OwnerRevocationReceipt {
            owner_id: owner_id.clone(),
            revoked_run_ids: revoked_run_ids.clone(),
        });
        self.emit_owner_revocation(
            Some(request_id),
            Some(client_id),
            owner_id,
            true,
            false,
            revoked_run_ids,
        );
    }

    fn clear_owner_state(&mut self, owner_id: &str) {
        self.preferences.remove(owner_id);
        self.surfaces
            .retain(|(stored_owner_id, _, _, _), _| stored_owner_id != owner_id);
        let session_ids = self
            .sessions
            .iter()
            .filter_map(|(session_id, session)| {
                (session.owner_id == owner_id).then_some(session_id.clone())
            })
            .collect::<Vec<_>>();
        self.sessions
            .retain(|_, session| session.owner_id != owner_id);
        self.context_sources
            .retain(|(session_id, _, _), _| !session_ids.contains(session_id));
    }

    fn emit_owner_revocation(
        &self,
        request_id: Option<String>,
        client_id: Option<String>,
        owner_id: String,
        ok: bool,
        duplicate: bool,
        revoked_run_ids: Vec<String>,
    ) {
        self.emit(
            "owner_runtime_revoked",
            envelope(
                request_id.as_deref(),
                client_id.as_deref(),
                json!({
                    "ownerId": owner_id,
                    "ok": ok,
                    "duplicate": duplicate,
                    "revokedRunIds": revoked_run_ids,
                    "invalidatedBindingIds": []
                }),
            ),
        );
    }

    fn query(&mut self, fields: Map<String, Value>) {
        let request_id = string_field(&fields, "requestId");
        let client_id = string_field(&fields, "clientId");
        let session_id = string_field(&fields, "sessionId");
        let prompt = string_field(&fields, "prompt");
        let Some((request_id, client_id, session_id, prompt)) =
            request_id.zip(client_id).zip(session_id).zip(prompt).map(
                |(((request_id, client_id), session_id), prompt)| {
                    (request_id, client_id, session_id, prompt)
                },
            )
        else {
            self.emit_error(
                None,
                None,
                "invalid_request",
                "query requires requestId, clientId, sessionId, and prompt",
            );
            return;
        };

        let Some(base_url) = self.managed_base_url.clone() else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "provider_setup_needed",
                "Omi managed transport is not configured",
            );
            return;
        };
        let Some(credentials) = self.credentials.clone() else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "provider_setup_needed",
                "Omi managed credentials are required",
            );
            return;
        };
        if string_field(&fields, "ownerId").as_deref() != Some(credentials.owner_id.as_str()) {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "authentication",
                "query owner does not match the configured Omi managed credentials",
            );
            return;
        }
        if self.running.contains_key(&request_id) {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "query requestId is already running",
            );
            return;
        }

        let requested_mode = fields
            .get("agentMode")
            .or_else(|| fields.get("executionMode"))
            .and_then(Value::as_str)
            .and_then(|mode| match mode {
                "fast" => Some(ExecutionMode::Fast),
                "deep" => Some(ExecutionMode::Deep),
                _ => None,
            });
        let execution_mode = select_execution_mode(&prompt, requested_mode);
        let model = string_field(&fields, "modelProfile").unwrap_or_else(|| match execution_mode {
            ExecutionMode::Fast => "omi-fast".into(),
            ExecutionMode::Deep => "omi-deep".into(),
        });
        let (cancel, mut cancelled) = watch::channel(false);
        self.running.insert(request_id.clone(), cancel);
        let output = self.output.clone();
        let completed = self.completed.clone();
        tokio::spawn(async move {
            let transport = ManagedTransport::new(base_url, credentials.bearer_token);
            let Ok(transport) = transport else {
                send_error(
                    &output,
                    &request_id,
                    &client_id,
                    "provider_setup_needed",
                    "Omi managed transport is not configured",
                );
                let _ = completed.send(request_id);
                return;
            };
            let mut agent = Agent::new();
            agent.set_model(model);
            agent.set_provider(std::sync::Arc::new(transport.provider()));
            let events = output.clone();
            let event_request_id = request_id.clone();
            let event_client_id = client_id.clone();
            agent.subscribe(move |event| {
                if let Some(message) = map_agent_event(event, &event_request_id, &event_client_id) {
                    let _ = events.send(message);
                }
            });
            let text = Arc::new(Mutex::new(String::new()));
            let collected_text = Arc::clone(&text);
            let prompt_run = async {
                agent.subscribe(move |event| {
                    if let Event::MessageDelta { delta } = event {
                        if let Ok(mut text) = collected_text.lock() {
                            text.push_str(delta);
                        }
                    }
                });
                agent.prompt(&prompt).await
            };
            tokio::pin!(prompt_run);
            tokio::select! {
                result = &mut prompt_run => match result {
                    Ok(()) => {
                        let text = text.lock().map(|text| text.clone()).unwrap_or_default();
                        send_result(&output, &request_id, &client_id, &session_id, &text, "succeeded")
                    }
                    Err(error) => send_error(&output, &request_id, &client_id, "transport_interruption", &error.to_string()),
                },
                changed = cancelled.changed() => {
                    if changed.is_ok() && *cancelled.borrow() {
                        send_result(&output, &request_id, &client_id, &session_id, "", "cancelled");
                    }
                }
            }
            let _ = completed.send(request_id);
        });
    }

    fn interrupt(&mut self, fields: Map<String, Value>) {
        let request_id = string_field(&fields, "requestId");
        let accepted = request_id
            .as_deref()
            .and_then(|request_id| self.running.get(request_id))
            .is_some_and(|cancel| cancel.send(true).is_ok());
        self.emit(
            "cancel_ack",
            envelope(
                request_id.as_deref(),
                fields.get("clientId").and_then(Value::as_str),
                json!({"accepted": accepted, "dispatchAttempted": accepted, "adapterAcknowledged": accepted}),
            ),
        );
    }

    fn stop(&mut self) {
        for cancel in self.running.values() {
            let _ = cancel.send(true);
        }
        self.emit(
            "cancel_ack",
            envelope(
                None,
                None,
                json!({"accepted": true, "dispatchAttempted": true, "adapterAcknowledged": true}),
            ),
        );
    }

    fn emit_error(
        &self,
        request_id: Option<String>,
        client_id: Option<String>,
        failure_code: &str,
        message: &str,
    ) {
        send_error(
            &self.output,
            request_id.as_deref().unwrap_or_default(),
            client_id.as_deref().unwrap_or_default(),
            failure_code,
            message,
        );
    }
}

fn map_agent_event(event: &Event, request_id: &str, client_id: &str) -> Option<Message> {
    match event {
        Event::MessageDelta { delta } => Some(Message {
            kind: "text_delta".into(),
            fields: envelope(Some(request_id), Some(client_id), json!({"text": delta})),
        }),
        Event::ToolCall(call) => {
            let input =
                serde_json::from_str::<Map<String, Value>>(&call.arguments).unwrap_or_default();
            Some(Message {
                kind: "tool_use".into(),
                fields: envelope(
                    Some(request_id),
                    Some(client_id),
                    json!({"callId": call.id, "name": call.name, "input": input}),
                ),
            })
        }
        Event::Error(message) => Some(Message {
            kind: "error".into(),
            fields: envelope(
                Some(request_id),
                Some(client_id),
                json!({"message": message, "failure": {"code": "transport_interruption", "failureCode": "transport_interruption", "userMessage": message}}),
            ),
        }),
        _ => None,
    }
}

fn send_result(
    output: &mpsc::UnboundedSender<Message>,
    request_id: &str,
    client_id: &str,
    session_id: &str,
    text: &str,
    terminal_status: &str,
) {
    let _ = output.send(Message {
        kind: "result".into(),
        fields: envelope(
            Some(request_id),
            Some(client_id),
            json!({"sessionId": session_id, "text": text, "terminalStatus": terminal_status}),
        ),
    });
}

fn send_error(
    output: &mpsc::UnboundedSender<Message>,
    request_id: &str,
    client_id: &str,
    failure_code: &str,
    message: &str,
) {
    let _ = output.send(Message {
        kind: "error".into(),
        fields: envelope(
            (!request_id.is_empty()).then_some(request_id),
            (!client_id.is_empty()).then_some(client_id),
            json!({"message": message, "failure": {"code": failure_code, "failureCode": failure_code, "userMessage": message}}),
        ),
    });
}

fn envelope(request_id: Option<&str>, client_id: Option<&str>, extra: Value) -> Map<String, Value> {
    let mut fields = extra.as_object().cloned().unwrap_or_default();
    fields.insert("protocolVersion".into(), json!(PROTOCOL_VERSION));
    if let Some(request_id) = request_id {
        fields.insert("requestId".into(), json!(request_id));
    }
    if let Some(client_id) = client_id {
        fields.insert("clientId".into(), json!(client_id));
    }
    fields
}

fn string_field(fields: &Map<String, Value>, name: &str) -> Option<String> {
    fields
        .get(name)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToOwned::to_owned)
}

fn optional_string_field(fields: &Map<String, Value>, name: &str) -> Option<String> {
    fields
        .get(name)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

fn journal_surface(fields: &Map<String, Value>) -> Option<JournalSurface> {
    Some(JournalSurface {
        owner_id: string_field(fields, "ownerId")?,
        surface_kind: string_field(fields, "surfaceKind")?,
        external_ref_kind: string_field(fields, "externalRefKind")?,
        external_ref_id: string_field(fields, "externalRefId")?,
    })
}

fn valid_adapter(adapter_id: &str) -> bool {
    adapter_id == "rx4"
}

fn is_owner_scoped_message(kind: &str) -> bool {
    matches!(
        kind,
        "configure_default_execution_profile"
            | "resolve_surface_session"
            | "migrate_session_execution_profile"
            | "context_source_update"
            | "get_context_snapshot"
            | "invalidate_session"
            | "query"
            | "interrupt"
            | "journal_record_turn"
            | "journal_record_exchange"
            | "journal_update_turn"
            | "journal_terminalize_turn"
            | "journal_list_turns"
            | "journal_clear_turns"
    )
}

fn valid_context_source(source: &str) -> bool {
    context_source_kinds().contains(&source)
}

fn valid_context_outcome(outcome: &str) -> bool {
    matches!(outcome, "available" | "empty" | "unavailable" | "redacted")
}

fn context_source_kinds() -> [&'static str; 7] {
    [
        "identity",
        "memories",
        "goals",
        "tasks",
        "screen",
        "workspace",
        "surface",
    ]
}

fn default_profile() -> ExecutionProfile {
    ExecutionProfile {
        generation: 1,
        adapter_id: "rx4".into(),
        model_profile: None,
        working_directory: String::new(),
        execution_role: "coordinator",
    }
}

fn creation_profile(fields: &Map<String, Value>) -> Option<ExecutionProfile> {
    let profile = fields.get("creationProfile")?.as_object()?;
    let adapter_id = string_field(profile, "adapterId")?;
    let working_directory = string_field(profile, "workingDirectory")?;
    if !valid_adapter(&adapter_id) {
        return None;
    }
    Some(ExecutionProfile {
        generation: 1,
        adapter_id,
        model_profile: optional_string_field(profile, "modelProfile"),
        working_directory,
        execution_role: "coordinator",
    })
}

fn profile_json(profile: &ExecutionProfile) -> Value {
    json!({
        "profileGeneration": profile.generation,
        "adapterId": profile.adapter_id,
        "credentialScope": "managed_cloud",
        "modelProfile": profile.model_profile,
        "workingDirectory": profile.working_directory,
        "executionRole": profile.execution_role
    })
}

fn hash_text(value: &str) -> String {
    format!("sha256:{:x}", Sha256::digest(value.as_bytes()))
}

fn hash_json(value: &Value) -> String {
    let encoded = match serde_json::to_vec(value) {
        Ok(encoded) => encoded,
        Err(_) => b"null".to_vec(),
    };
    format!("sha256:{:x}", Sha256::digest(encoded))
}

#[tokio::main]
async fn main() {
    let (output, mut output_receiver) = mpsc::unbounded_channel();
    let (completed, mut completed_receiver) = mpsc::unbounded_channel();
    let journal = match JournalStore::open_default() {
        Ok(journal) => journal,
        Err(error) => {
            eprintln!("unable to open Omi journal: {error}");
            return;
        }
    };
    let mut runtime = Runtime::new(
        env::var("OMI_API_BASE_URL").ok(),
        journal,
        output,
        completed,
    );
    runtime.emit(
        "init",
        envelope(
            None,
            None,
            json!({"sessionId": "", "agentControlTools": [], "runtimeVersion": RUNTIME_VERSION, "runtimeCapabilities": ["journal_import_remote_turn", "runtime_adapter_availability"], "runtimeAdapterIds": ["rx4"]}),
        ),
    );
    let stdin = BufReader::new(tokio::io::stdin());
    let mut lines = stdin.lines();
    let mut stdout = tokio::io::stdout();
    loop {
        tokio::select! {
            line = lines.next_line() => match line {
                Ok(Some(line)) if !line.trim().is_empty() => {
                    if let Ok(message) = parse_line(&line) {
                        runtime.handle(message);
                    }
                }
                Ok(Some(_)) => {}
                Ok(None) | Err(_) => break,
            },
            Some(request_id) = completed_receiver.recv() => {
                runtime.running.remove(&request_id);
            },
            Some(message) = output_receiver.recv() => {
                if let Ok(line) = emit_line(&message) {
                    if stdout.write_all(line.as_bytes()).await.is_err() || stdout.flush().await.is_err() {
                        break;
                    }
                }
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_runtime(
        managed_base_url: Option<String>,
        output: mpsc::UnboundedSender<Message>,
        completed: mpsc::UnboundedSender<String>,
    ) -> Runtime {
        let journal = match JournalStore::in_memory() {
            Ok(journal) => journal,
            Err(error) => panic!("journal test setup failed: {error}"),
        };
        Runtime::new(managed_base_url, journal, output, completed)
    }

    #[test]
    fn agent_events_keep_the_swift_jsonl_shapes() {
        let text = map_agent_event(
            &Event::MessageDelta {
                delta: "hello".into(),
            },
            "request",
            "client",
        )
        .expect("text delta must map");
        assert_eq!(text.kind, "text_delta");
        assert_eq!(text.fields["text"], "hello");
        let tool = map_agent_event(
            &Event::ToolCall(rx4::ToolCall {
                id: "tool".into(),
                name: "search".into(),
                arguments: r#"{"q":"omi"}"#.into(),
            }),
            "request",
            "client",
        )
        .expect("tool call must map");
        assert_eq!(tool.kind, "tool_use");
        assert_eq!(tool.fields["input"]["q"], "omi");
    }

    #[tokio::test]
    async fn rejects_query_without_omi_managed_credentials() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(Some("https://api.omi.me/v2".into()), output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"o"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(parse_line(r#"{"type":"query","requestId":"r","clientId":"c","sessionId":"s","ownerId":"o","prompt":"hello"}"#).expect("fixture must parse"));
        let error = receiver.recv().await.expect("query must reject");
        assert_eq!(error.kind, "error");
        assert_eq!(
            error.fields["failure"]["failureCode"],
            "provider_setup_needed"
        );
    }

    #[tokio::test]
    async fn interrupt_emits_existing_cancel_ack_shape() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"o"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(
            parse_line(r#"{"type":"interrupt","requestId":"r","clientId":"c","ownerId":"o"}"#)
                .expect("fixture must parse"),
        );
        let ack = receiver.recv().await.expect("interrupt must acknowledge");
        assert_eq!(ack.kind, "cancel_ack");
        assert_eq!(ack.fields["accepted"], false);
        assert_eq!(ack.fields["protocolVersion"], PROTOCOL_VERSION);
    }

    #[tokio::test]
    async fn session_profile_and_context_messages_keep_swift_contract_shapes() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );

        runtime.handle(parse_line(r#"{"type":"configure_default_execution_profile","requestId":"profile","clientId":"client","ownerId":"owner","adapterId":"rx4","modelProfile":"omi-fast","workingDirectory":"/tmp/omi"}"#).expect("profile fixture must parse"));
        let profile = receiver.recv().await.expect("profile response must emit");
        assert_eq!(profile.kind, "default_execution_profile_configured");
        assert_eq!(profile.fields["preferenceGeneration"], 1);
        assert_eq!(profile.fields["credentialScope"], "managed_cloud");

        runtime.handle(parse_line(r#"{"type":"resolve_surface_session","requestId":"resolve","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("resolve fixture must parse"));
        let resolved = receiver.recv().await.expect("surface response must emit");
        assert_eq!(resolved.kind, "surface_session_resolved");
        assert_eq!(resolved.fields["created"], true);
        let session_id = resolved.fields["sessionId"]
            .as_str()
            .expect("session id must be present")
            .to_owned();
        assert_eq!(resolved.fields["profile"]["adapterId"], "rx4");

        runtime.handle(parse_line(&format!(r#"{{"type":"migrate_session_execution_profile","requestId":"migrate","clientId":"client","ownerId":"owner","sessionId":"{session_id}","expectedProfileGeneration":1,"adapterId":"rx4","modelProfile":"omi-deep","workingDirectory":"/tmp/omi-deep","reason":"user_requested"}}"#)).expect("migration fixture must parse"));
        let migration = receiver.recv().await.expect("migration response must emit");
        assert_eq!(migration.kind, "session_execution_profile_migrated");
        assert_eq!(migration.fields["previousProfileGeneration"], 1);
        assert_eq!(migration.fields["profile"]["profileGeneration"], 2);
        assert_eq!(migration.fields["staleBindingIds"], json!([]));

        runtime.handle(parse_line(&format!(r#"{{"type":"context_source_update","requestId":"context","clientId":"client","ownerId":"owner","sessionId":"{session_id}","surfaceKind":"main_chat","source":"memories","sourceRevision":"rev-1","outcome":"available","capturedAtMs":1,"payload":{{"text":"remember this"}}}}"#)).expect("context fixture must parse"));
        let update = receiver
            .recv()
            .await
            .expect("context update response must emit");
        assert_eq!(update.kind, "context_source_updated");
        assert_eq!(update.fields["source"], "memories");
        assert!(update.fields["snapshotVersion"].as_str().is_some());

        runtime.handle(parse_line(&format!(r#"{{"type":"get_context_snapshot","requestId":"snapshot","clientId":"client","ownerId":"owner","sessionId":"{session_id}","surfaceKind":"main_chat"}}"#)).expect("snapshot fixture must parse"));
        let snapshot = receiver.recv().await.expect("snapshot response must emit");
        assert_eq!(snapshot.kind, "context_snapshot");
        assert_eq!(snapshot.fields["snapshot"]["ownerId"], "owner");
        assert_eq!(snapshot.fields["snapshot"]["sessionId"], session_id);
        assert_eq!(snapshot.fields["snapshot"]["contextPlan"]["version"], 1);
        assert_eq!(
            snapshot.fields["snapshot"]["capabilities"]["executionRole"],
            "coordinator"
        );

        runtime.handle(parse_line(r#"{"type":"invalidate_session","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("invalidation fixture must parse"));
        assert!(receiver.try_recv().is_err());
    }

    #[tokio::test]
    async fn rejects_non_rx4_session_profiles() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(parse_line(r#"{"type":"configure_default_execution_profile","requestId":"profile","clientId":"client","ownerId":"owner","adapterId":"pi-mono","modelProfile":null,"workingDirectory":"/tmp/omi"}"#).expect("profile fixture must parse"));
        let error = receiver.recv().await.expect("invalid adapter must reject");
        assert_eq!(error.kind, "error");
        assert_eq!(error.fields["failure"]["failureCode"], "invalid_request");
    }

    #[tokio::test]
    async fn owner_revocation_cancels_runs_and_reuses_its_receipt() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner-a"}"#)
                .expect("owner fixture must parse"),
        );
        let (cancel, cancelled) = watch::channel(false);
        runtime.running.insert("run-a".into(), cancel);

        runtime.handle(parse_line(r#"{"type":"revoke_owner_runtime","requestId":"revoke-1","clientId":"client","ownerId":"owner-a"}"#).expect("revoke fixture must parse"));
        let revoked = receiver.recv().await.expect("revoke receipt must emit");
        assert_eq!(revoked.kind, "owner_runtime_revoked");
        assert_eq!(revoked.fields["ok"], true);
        assert_eq!(revoked.fields["duplicate"], false);
        assert_eq!(revoked.fields["revokedRunIds"], json!(["run-a"]));
        assert!(*cancelled.borrow());
        assert!(runtime.owner_id.is_none());

        runtime.handle(parse_line(r#"{"type":"revoke_owner_runtime","requestId":"revoke-2","clientId":"client","ownerId":"owner-a"}"#).expect("duplicate revoke fixture must parse"));
        let duplicate = receiver.recv().await.expect("duplicate receipt must emit");
        assert_eq!(duplicate.fields["ok"], true);
        assert_eq!(duplicate.fields["duplicate"], true);
        assert_eq!(duplicate.fields["revokedRunIds"], json!(["run-a"]));
    }

    #[tokio::test]
    async fn token_refresh_cannot_replace_an_established_owner() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner-a"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(
            parse_line(r#"{"type":"refresh_token","ownerId":"owner-b","token":"token-b"}"#)
                .expect("token fixture must parse"),
        );
        assert_eq!(runtime.owner_id.as_deref(), Some("owner-a"));
        assert!(runtime.credentials.is_none());

        runtime.handle(
            parse_line(r#"{"type":"configure_default_execution_profile","requestId":"profile","clientId":"client","ownerId":"owner-b","adapterId":"rx4","modelProfile":null,"workingDirectory":"/tmp/omi"}"#)
                .expect("profile fixture must parse"),
        );
        let error = receiver.recv().await.expect("owner mismatch must reject");
        assert_eq!(error.fields["failure"]["failureCode"], "authentication");
    }

    #[tokio::test]
    async fn journal_rpc_persists_records_revisions_and_clear_generation() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .unwrap_or_else(|error| panic!("owner fixture invalid: {error}")),
        );
        runtime.handle(parse_line(r#"{"type":"journal_record_turn","requestId":"record","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turn":{"turnId":"turn-1","role":"user","origin":"local","status":"completed","content":"hello","contentBlocks":[],"resources":[],"metadataJson":"{}","createdAtMs":1}}"#).unwrap_or_else(|error| panic!("record fixture invalid: {error}")));
        let record = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("record response missing"));
        assert_eq!(record.kind, "journal_operation_result");
        assert_eq!(record.fields["turn"]["turnSeq"], 1);
        let changed = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("change event missing"));
        assert_eq!(changed.kind, "journal_turn_changed");

        runtime.handle(parse_line(r#"{"type":"journal_update_turn","requestId":"update","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","update":{"turnId":"turn-1","content":"hello again","appendContentBlocks":[{"type":"text","text":"hello again"}]}}"#).unwrap_or_else(|error| panic!("update fixture invalid: {error}")));
        let update = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("update response missing"));
        assert_eq!(update.fields["turn"]["turnSeq"], 2);
        let _ = receiver.recv().await;

        runtime.handle(parse_line(r#"{"type":"journal_list_turns","requestId":"list","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","afterTurnSeq":0,"limit":100}"#).unwrap_or_else(|error| panic!("list fixture invalid: {error}")));
        let listed = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("list response missing"));
        assert_eq!(listed.fields["turns"].as_array().map(Vec::len), Some(1));
        assert_eq!(listed.fields["turns"][0]["content"], "hello again");

        runtime.handle(parse_line(r#"{"type":"journal_clear_turns","requestId":"clear","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","expectedGeneration":1}"#).unwrap_or_else(|error| panic!("clear fixture invalid: {error}")));
        let cleared = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("clear response missing"));
        assert_eq!(cleared.fields["clearedCount"], 1);
        assert_eq!(cleared.fields["conversationGeneration"], 2);
    }

    #[tokio::test]
    async fn journal_rpc_rejects_wrong_owner_and_public_runtime_authority_fields() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .unwrap_or_else(|error| panic!("owner fixture invalid: {error}")),
        );
        runtime.handle(parse_line(r#"{"type":"journal_record_turn","requestId":"wrong","clientId":"client","ownerId":"other","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turn":{}}"#).unwrap_or_else(|error| panic!("owner fixture invalid: {error}")));
        let owner_error = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("owner error missing"));
        assert_eq!(
            owner_error.fields["failure"]["failureCode"],
            "authentication"
        );
        runtime.handle(parse_line(r#"{"type":"journal_record_turn","requestId":"record","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turn":{"turnId":"turn-1","role":"assistant","content":"x","producingRunId":"run"}}"#).unwrap_or_else(|error| panic!("record fixture invalid: {error}")));
        let policy_error = receiver
            .recv()
            .await
            .unwrap_or_else(|| panic!("policy error missing"));
        assert_eq!(
            policy_error.fields["failure"]["failureCode"],
            "invalid_request"
        );
    }
}
mod journal;

use journal::{JournalStore, ResultPage as JournalResultPage, Surface as JournalSurface};
