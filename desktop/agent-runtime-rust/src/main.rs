use omi_agent_runtime::journal::{
    JournalStore, ResultPage as JournalResultPage, RunIdentity, Surface as JournalSurface,
};
use omi_agent_runtime::provider_policy::ManagedTransport;
use omi_agent_runtime::tool_relay::{Identity, ToolRelay};
use omi_agent_runtime::{
    emit_line, parse_line, select_execution_mode, ExecutionMode, Message, PROTOCOL_VERSION,
};
use rx4::{Agent, Event};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::env;
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::{mpsc, watch};
use uuid::Uuid;

const RUNTIME_VERSION: &str = env!("CARGO_PKG_VERSION");
const MAX_JSONL_LINE_BYTES: usize = 1024 * 1024;

mod tool_authority;
use tool_authority::{RunningQuery, ToolRequest};

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
    running: HashMap<String, RunningQuery>,
    preferences: HashMap<String, ExecutionProfile>,
    sessions: HashMap<String, SurfaceSession>,
    surfaces: HashMap<(String, String, String, String), String>,
    context_sources: HashMap<(String, String, String), ContextSource>,
    next_session: u64,
    owner_id: Option<String>,
    last_revocation: Option<OwnerRevocationReceipt>,
    journal: JournalStore,
    tool_relay: ToolRelay,
    daemon_boot_epoch: String,
    output: mpsc::UnboundedSender<Message>,
    completed: mpsc::UnboundedSender<String>,
    tool_requests: mpsc::UnboundedSender<ToolRequest>,
}

impl Runtime {
    fn new(
        managed_base_url: Option<String>,
        journal: JournalStore,
        output: mpsc::UnboundedSender<Message>,
        completed: mpsc::UnboundedSender<String>,
        tool_requests: mpsc::UnboundedSender<ToolRequest>,
        daemon_boot_epoch: String,
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
            tool_relay: ToolRelay::new(),
            daemon_boot_epoch,
            output,
            completed,
            tool_requests,
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
            "journal_import_remote_turn" => self.journal_import_remote_turn(input.fields),
            "journal_update_turn" => self.journal_update_turn(input.fields),
            "journal_terminalize_turn" => self.journal_terminalize_turn(input.fields),
            "journal_list_turns" => self.journal_list_turns(input.fields),
            "journal_clear_turns" => self.journal_clear_turns(input.fields),
            "journal_repair_turns" => self.journal_repair_turns(input.fields),
            "authorized_tool_execution_result" => {
                self.authorized_tool_execution_result(input.fields)
            }
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
            external_ref_kind.clone(),
            external_ref_id.clone(),
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
            let conversation_id = match self.journal.conversation_id(&JournalSurface {
                owner_id: owner_id.clone(),
                surface_kind: surface_kind.clone(),
                external_ref_kind: external_ref_kind.clone(),
                external_ref_id: external_ref_id.clone(),
            }) {
                Ok(conversation_id) => conversation_id,
                Err(error) => {
                    self.emit_error(
                        Some(request_id.clone()),
                        Some(client_id.clone()),
                        "runtime_state",
                        &error,
                    );
                    return String::new();
                }
            };
            let profile = creation_profile(&fields).unwrap_or_else(|| {
                self.preferences
                    .get(&owner_id)
                    .cloned()
                    .unwrap_or_else(default_profile)
            });
            if profile.working_directory.trim().is_empty() {
                self.invalid_request(
                    &fields,
                    "session creation profile requires rx4 and a working directory",
                );
                return String::new();
            }
            let session_id = format!("rx4-session-{}", self.next_session);
            self.next_session += 1;
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
        if session_id.is_empty() {
            return;
        }
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
            self.invalid_request(
                &fields,
                "invalidate_session requires ownerId, surfaceKind, externalRefKind, and externalRefId",
            );
            return;
        };
        let key = (
            owner_id.clone(),
            surface_kind.clone(),
            external_ref_kind.clone(),
            external_ref_id.clone(),
        );
        let session_id = match self.surfaces.get(&key).cloned() {
            Some(id) => id,
            None => {
                self.emit(
                    "session_invalidated",
                    envelope(
                        None,
                        None,
                        json!({
                            "ownerId": owner_id,
                            "surfaceKind": surface_kind,
                            "externalRefKind": external_ref_kind,
                            "externalRefId": external_ref_id,
                            "invalidated": false,
                            "reason": "no_session_for_surface"
                        }),
                    ),
                );
                return;
            }
        };
        let revoked_tool_claims = match self
            .journal
            .revoke_tool_claims_for_session(&owner_id, &session_id)
        {
            Ok(revoked) => revoked,
            Err(error) => {
                self.emit_error(None, None, "runtime_state", &error);
                return;
            }
        };
        // Cancel every active run bound to this session only after revoking its claims.
        let mut cancelled = 0_u64;
        self.running.retain(|_request_id, running| {
            if running.session_id == session_id {
                let _ = running.cancel.send(true);
                cancelled += 1;
                false
            } else {
                true
            }
        });
        self.sessions.remove(&session_id);
        self.surfaces.remove(&key);
        self.emit(
            "session_invalidated",
            envelope(
                None,
                None,
                json!({
                    "ownerId": owner_id,
                    "surfaceKind": surface_kind,
                    "externalRefKind": external_ref_kind,
                    "externalRefId": external_ref_id,
                    "sessionId": session_id,
                    "invalidated": true,
                    "cancelledRuns": cancelled,
                    "revokedToolClaims": revoked_tool_claims
                }),
            ),
        );
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

    fn journal_import_remote_turn(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal import requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal import requires a surface reference");
            return;
        };
        let Some(turn) = fields.get("turn").and_then(Value::as_object) else {
            self.invalid_request(&fields, "journal import requires turn");
            return;
        };
        let Some(remote_id) = string_field(turn, "remoteId") else {
            self.invalid_request(&fields, "remote journal turn requires remoteId");
            return;
        };
        let canonical_turn_id =
            string_field(turn, "canonicalTurnId").unwrap_or_else(|| remote_id.clone());
        let Some(role) = string_field(turn, "role") else {
            self.invalid_request(&fields, "remote journal turn requires role");
            return;
        };
        let Some(content) = string_field(turn, "content") else {
            self.invalid_request(&fields, "remote journal turn requires content");
            return;
        };
        let Some(content_blocks) = turn.get("contentBlocks").filter(|value| value.is_array())
        else {
            self.invalid_request(&fields, "remote journal turn requires contentBlocks");
            return;
        };
        let Some(resources) = turn.get("resources").filter(|value| value.is_array()) else {
            self.invalid_request(&fields, "remote journal turn requires resources");
            return;
        };
        let Some(metadata_json) = string_field(turn, "metadataJson") else {
            self.invalid_request(&fields, "remote journal turn requires metadataJson");
            return;
        };
        let Some(created_at_ms) = turn.get("createdAtMs").and_then(Value::as_u64) else {
            self.invalid_request(&fields, "remote journal turn requires createdAtMs");
            return;
        };
        let mut imported = Map::new();
        imported.insert("turnId".into(), Value::String(canonical_turn_id));
        imported.insert(
            "producerId".into(),
            Value::String(format!("remote:{remote_id}")),
        );
        imported.insert("role".into(), Value::String(role));
        imported.insert("content".into(), Value::String(content));
        imported.insert("origin".into(), Value::String("legacy_upgrade".into()));
        imported.insert("status".into(), Value::String("completed".into()));
        imported.insert("contentBlocks".into(), content_blocks.clone());
        imported.insert("resources".into(), resources.clone());
        imported.insert("metadataJson".into(), Value::String(metadata_json));
        imported.insert("createdAtMs".into(), Value::Number(created_at_ms.into()));
        match self.journal.record(&surface, &imported) {
            Ok(page) => self.emit_journal_result(
                "import_remote",
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

    fn journal_repair_turns(&mut self, fields: Map<String, Value>) {
        let Some((request_id, client_id)) = required_fields!(&fields, "requestId", "clientId")
        else {
            self.invalid_request(&fields, "journal repair requires requestId and clientId");
            return;
        };
        let Some(surface) = journal_surface(&fields) else {
            self.invalid_request(&fields, "journal repair requires a surface reference");
            return;
        };
        let turn_ids = fields
            .get("turnIds")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .map(ToOwned::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        let active_run_ids = self
            .running
            .values()
            .map(|running| running.run_id.clone())
            .collect::<Vec<_>>();
        match self.journal.repair(&surface, &turn_ids, &active_run_ids) {
            Ok(page) => {
                self.emit_journal_result("repair", &request_id, &client_id, &surface, page, true)
            }
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "invalid_request", &error)
            }
        }
    }

    fn authorized_tool_execution_result(&mut self, fields: Map<String, Value>) {
        match self.tool_relay.complete(&mut self.journal, &fields) {
            Ok((completion, duplicate)) => self.emit(
                "authorized_tool_result",
                envelope(
                    None,
                    None,
                    json!({"invocationId": completion["invocationId"], "outcome": completion["outcome"], "result": completion["result"], "duplicate": duplicate}),
                ),
            ),
            Err(error) => self.emit_error(None, None, "invalid_request", &error),
        }
    }

    fn authorize_tool_request(&mut self, request: ToolRequest) {
        let Some(running) = self.running.get(&request.request_id).cloned() else {
            self.emit_error(
                Some(request.request_id),
                Some(request.client_id),
                "invalid_request",
                "authorized tool execution has no active run",
            );
            return;
        };
        if *running.cancel.borrow() {
            self.emit_error(
                Some(request.request_id),
                Some(request.client_id),
                "invalid_request",
                "authorized tool execution was cancelled",
            );
            return;
        }
        let input = match serde_json::from_str::<Map<String, Value>>(&request.call.arguments) {
            Ok(input) => input,
            Err(_) => {
                self.emit_error(
                    Some(request.request_id),
                    Some(request.client_id),
                    "invalid_request",
                    "authorized tool arguments must be a JSON object",
                );
                return;
            }
        };
        let identity = Identity {
            invocation_id: request.call.id.clone(),
            owner_id: running.owner_id,
            session_id: running.session_id,
            run_id: running.run_id,
            attempt_id: running.attempt_id,
            profile_generation: running.profile_generation,
            daemon_boot_epoch: self.daemon_boot_epoch.clone(),
            execution_generation: 1,
        };
        match self.tool_relay.dispatch(
            &mut self.journal,
            identity,
            request.call.name,
            input,
            running.surface_kind,
            None,
            None,
            "act".into(),
        ) {
            Ok(authorized) => {
                let mut fields = authorized.as_object().cloned().unwrap_or_default();
                fields.insert("requestId".into(), json!(request.request_id));
                fields.insert("clientId".into(), json!(request.client_id));
                fields.insert("protocolVersion".into(), json!(PROTOCOL_VERSION));
                self.emit("authorized_tool_execution", fields);
            }
            Err(error) => self.emit_error(
                Some(request.request_id),
                Some(request.client_id),
                "invalid_request",
                &error,
            ),
        }
    }

    fn complete_run(
        &mut self,
        request_id: String,
        tool_requests: &mut mpsc::UnboundedReceiver<ToolRequest>,
    ) {
        let cancelled = self
            .running
            .get(&request_id)
            .is_some_and(|running| *running.cancel.borrow());
        let mut deferred = Vec::new();
        while let Ok(request) = tool_requests.try_recv() {
            if request.request_id != request_id {
                deferred.push(request);
                continue;
            }
            if cancelled {
                continue;
            }
            self.authorize_tool_request(request);
        }
        for request in deferred {
            let _ = self.tool_requests.send(request);
        }
        if cancelled {
            if let Some(running) = self.running.get(&request_id).cloned() {
                if let Err(error) = self.tool_relay.revoke_owner_run(
                    &mut self.journal,
                    &running.owner_id,
                    Some(&running.run_id),
                ) {
                    self.emit_error(None, None, "runtime_state", &error);
                }
            }
        }
        self.running.remove(&request_id);
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
        let mut revoked_run_ids = self
            .running
            .values()
            .map(|running| running.run_id.clone())
            .collect::<Vec<_>>();
        revoked_run_ids.sort();
        revoked_run_ids.dedup();
        for running in self.running.values() {
            let _ = running.cancel.send(true);
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
        let _ = self
            .tool_relay
            .revoke_owner_run(&mut self.journal, owner_id, None);
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
        self.running
            .retain(|_, running| running.owner_id != owner_id);
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
        if let Err(error) = self.journal.prune_expired_runtime_state() {
            self.emit_error(Some(request_id), Some(client_id), "runtime_state", &error);
            return;
        }
        let Some(session) = self.sessions.get(&session_id) else {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "agent session is unavailable",
            );
            return;
        };
        if session.owner_id != credentials.owner_id {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "authentication",
                "query is not authorized for this session",
            );
            return;
        }
        if session.profile.working_directory.trim().is_empty() {
            self.emit_error(
                Some(request_id),
                Some(client_id),
                "invalid_request",
                "execution profile requires a working directory",
            );
            return;
        }
        let working_directory = session.profile.working_directory.clone();
        let profile_generation = session.profile.generation;
        let surface_kind = session.surface_kind.clone();
        let run_identity = match self.journal.admit_run(
            &credentials.owner_id,
            &session_id,
            &session.conversation_id,
            profile_generation,
        ) {
            Ok(identity) => identity,
            Err(error) => {
                self.emit_error(Some(request_id), Some(client_id), "runtime_state", &error);
                return;
            }
        };
        let result_identity = run_identity.clone();

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
        self.running.insert(
            request_id.clone(),
            RunningQuery {
                cancel,
                owner_id: credentials.owner_id.clone(),
                session_id: session_id.clone(),
                run_id: run_identity.run_id,
                attempt_id: run_identity.attempt_id,
                profile_generation,
                surface_kind,
            },
        );
        let output = self.output.clone();
        let completed = self.completed.clone();
        let tool_requests = self.tool_requests.clone();
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
            let mut agent = prepare_query_agent(model, working_directory);
            agent.set_provider(std::sync::Arc::new(transport.provider()));
            let events = output.clone();
            let event_request_id = request_id.clone();
            let event_client_id = client_id.clone();
            let tool_sink = tool_requests.clone();
            agent.subscribe(move |event| {
                if let Event::ToolCall(call) = event {
                    let _ = tool_sink.send(ToolRequest {
                        request_id: event_request_id.clone(),
                        client_id: event_client_id.clone(),
                        call: call.clone(),
                    });
                    return;
                }
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
                        send_result(
                            &output,
                            &request_id,
                            &client_id,
                            &session_id,
                            &result_identity,
                            &text,
                            "succeeded",
                        )
                    }
                    Err(error) => send_error(&output, &request_id, &client_id, "transport_interruption", &error.to_string()),
                },
                changed = cancelled.changed() => {
                    if changed.is_ok() && *cancelled.borrow() {
                        send_result(
                            &output,
                            &request_id,
                            &client_id,
                            &session_id,
                            &result_identity,
                            "",
                            "cancelled",
                        );
                    }
                }
            }
            let _ = completed.send(request_id);
        });
    }

    fn interrupt(&mut self, fields: Map<String, Value>) {
        let request_id = string_field(&fields, "requestId");
        let accepted = match request_id
            .as_deref()
            .and_then(|request_id| self.running.get(request_id))
            .cloned()
        {
            Some(running) => {
                match self.tool_relay.revoke_owner_run(
                    &mut self.journal,
                    &running.owner_id,
                    Some(&running.run_id),
                ) {
                    Ok(_) => running.cancel.send(true).is_ok(),
                    Err(error) => {
                        self.emit_error(
                            request_id.clone(),
                            fields
                                .get("clientId")
                                .and_then(Value::as_str)
                                .map(str::to_owned),
                            "runtime_state",
                            &error,
                        );
                        false
                    }
                }
            }
            None => false,
        };
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
        for running in self.running.values() {
            let _ = running.cancel.send(true);
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

    fn handle_stdin_frame(&mut self, line: &[u8]) {
        match std::str::from_utf8(line) {
            Ok(line) => match parse_line(line) {
                Ok(message) => self.handle(message),
                Err(error) => self.emit_error(
                    None,
                    None,
                    "invalid_request",
                    &format!("invalid protocol frame: {error}"),
                ),
            },
            Err(_) => self.emit_error(
                None,
                None,
                "invalid_request",
                "stdin frame is not valid UTF-8",
            ),
        }
    }
}

fn map_agent_event(event: &Event, request_id: &str, client_id: &str) -> Option<Message> {
    match event {
        Event::MessageDelta { delta } => Some(Message {
            kind: "text_delta".into(),
            fields: envelope(Some(request_id), Some(client_id), json!({"text": delta})),
        }),
        Event::Error(message) => Some(Message {
            kind: "error".into(),
            fields: envelope(
                Some(request_id),
                Some(client_id),
                json!({"message": message, "failure": {"code": "transport_interruption", "failureCode": "transport_interruption", "userMessage": message}}),
            ),
        }),
        Event::ToolCall(_) => None,
        _ => None,
    }
}

fn send_result(
    output: &mpsc::UnboundedSender<Message>,
    request_id: &str,
    client_id: &str,
    session_id: &str,
    run: &RunIdentity,
    text: &str,
    terminal_status: &str,
) {
    let _ = output.send(Message {
        kind: "result".into(),
        fields: envelope(
            Some(request_id),
            Some(client_id),
            json!({"sessionId": session_id, "runId": run.run_id, "attemptId": run.attempt_id, "text": text, "terminalStatus": terminal_status}),
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
            | "journal_import_remote_turn"
            | "journal_update_turn"
            | "journal_terminalize_turn"
            | "journal_list_turns"
            | "journal_clear_turns"
            | "journal_repair_turns"
            | "authorized_tool_execution_result"
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

fn prepare_query_agent(model: String, working_directory: String) -> Agent {
    let mut agent = Agent::new();
    agent.set_model(model);
    agent.set_workspace_root(working_directory);
    agent
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

async fn read_bounded_jsonl_line<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    max_line_bytes: usize,
) -> std::io::Result<Option<Vec<u8>>> {
    let mut line = Vec::new();
    let mut oversized = false;
    loop {
        let (consumed, newline) = {
            let available = reader.fill_buf().await?;
            if available.is_empty() {
                if oversized {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::InvalidData,
                        "JSONL line exceeds maximum size",
                    ));
                }
                return Ok((!line.is_empty()).then_some(line));
            }
            let newline = available.iter().position(|byte| *byte == b'\n');
            let consumed = newline.map_or(available.len(), |position| position + 1);
            let content_bytes = newline.unwrap_or(available.len());
            if !oversized {
                if line.len().saturating_add(content_bytes) > max_line_bytes {
                    oversized = true;
                } else {
                    line.extend_from_slice(&available[..consumed]);
                }
            }
            (consumed, newline.is_some())
        };
        reader.consume(consumed);
        if newline {
            return if oversized {
                Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "JSONL line exceeds maximum size",
                ))
            } else {
                Ok(Some(line))
            };
        }
    }
}

#[tokio::main]
async fn main() {
    let (output, mut output_receiver) = mpsc::unbounded_channel();
    let (completed, mut completed_receiver) = mpsc::unbounded_channel();
    let (tool_requests, mut tool_request_receiver) = mpsc::unbounded_channel();
    let mut journal = match JournalStore::open_default() {
        Ok(journal) => journal,
        Err(error) => {
            eprintln!("unable to open Omi journal: {error}");
            return;
        }
    };
    if let Err(error) = journal.reconcile_pending_tool_claims(None) {
        eprintln!("unable to reconcile Omi tool claims: {error}");
        return;
    }
    if let Err(error) = journal.prune_expired_runtime_state() {
        eprintln!("unable to prune expired Omi runtime state: {error}");
        return;
    }
    let daemon_boot_epoch = Uuid::new_v4().to_string();
    let mut runtime = Runtime::new(
        env::var("OMI_API_BASE_URL").ok(),
        journal,
        output,
        completed,
        tool_requests,
        daemon_boot_epoch,
    );
    runtime.emit(
        "init",
        envelope(
            None,
            None,
            json!({"sessionId": "", "agentControlTools": [], "runtimeVersion": RUNTIME_VERSION, "runtimeCapabilities": ["journal_import_remote_turn", "runtime_adapter_availability"], "runtimeAdapterIds": ["rx4"]}),
        ),
    );
    let mut stdin = BufReader::new(tokio::io::stdin());
    let mut stdout = tokio::io::stdout();
    loop {
        tokio::select! {
            line = read_bounded_jsonl_line(&mut stdin, MAX_JSONL_LINE_BYTES) => match line {
                Ok(Some(line)) if !line.iter().all(u8::is_ascii_whitespace) => {
                    runtime.handle_stdin_frame(&line);
                }
                Err(error) => runtime.emit_error(None, None, "invalid_request", &error.to_string()),
                Ok(Some(_)) => {}
                Ok(None) => break,
            },
            Some(request_id) = completed_receiver.recv() => {
                runtime.complete_run(request_id, &mut tool_request_receiver);
            },
            Some(request) = tool_request_receiver.recv() => {
                runtime.authorize_tool_request(request);
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
        let (tool_requests, _) = mpsc::unbounded_channel();
        Runtime::new(
            managed_base_url,
            journal,
            output,
            completed,
            tool_requests,
            "boot-test".into(),
        )
    }

    #[test]
    fn prepare_query_agent_binds_session_working_directory() {
        let working_directory = "/tmp/omi-repo-workspace";
        let agent = prepare_query_agent("omi-fast".into(), working_directory.into());
        assert_eq!(
            agent.workspace_root,
            std::path::PathBuf::from(working_directory)
        );
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
        assert!(map_agent_event(
            &Event::ToolCall(rx4::ToolCall {
                id: "tool".into(),
                name: "search".into(),
                arguments: r#"{"q":"omi"}"#.into(),
            }),
            "request",
            "client",
        )
        .is_none());
    }

    #[test]
    fn result_keeps_the_run_identity_swift_reads() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        send_result(
            &output,
            "request",
            "client",
            "session",
            &RunIdentity {
                run_id: "run".into(),
                attempt_id: "attempt".into(),
            },
            "done",
            "succeeded",
        );
        let result = receiver.try_recv().expect("result must emit");
        assert_eq!(result.fields["runId"], "run");
        assert_eq!(result.fields["attemptId"], "attempt");
    }

    #[tokio::test]
    async fn authorized_tool_result_requires_the_active_owner() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        let run = runtime
            .journal
            .admit_run("owner", "session", "conversation", 1)
            .expect("run must admit");
        let run_id = run.run_id.clone();
        let (cancel, _) = watch::channel(false);
        runtime.running.insert(
            "request".into(),
            RunningQuery {
                cancel,
                owner_id: "owner".into(),
                session_id: "session".into(),
                run_id: run.run_id,
                attempt_id: run.attempt_id,
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );
        runtime.authorize_tool_request(ToolRequest {
            request_id: "request".into(),
            client_id: "client".into(),
            call: rx4::ToolCall {
                id: "invoke-1".into(),
                name: "search".into(),
                arguments: r#"{"q":"omi"}"#.into(),
            },
        });
        let authorized = receiver
            .recv()
            .await
            .expect("authorized tool execution must emit");
        assert_eq!(authorized.kind, "authorized_tool_execution");
        assert_eq!(authorized.fields["invocationId"], "invoke-1");
        assert_eq!(authorized.fields["runId"], run_id);
        let mut result = authorized.fields.clone();
        result.insert("type".into(), json!("authorized_tool_execution_result"));
        result.insert("outcome".into(), json!("succeeded"));
        result.insert("result".into(), json!("found"));
        for key in [
            "toolName",
            "input",
            "effectClass",
            "retryPolicy",
            "surfaceKind",
            "externalRefKind",
            "externalRefId",
            "originatingUserText",
            "precedingAssistantText",
            "runMode",
            "chatMode",
            "requestId",
            "clientId",
        ] {
            result.remove(key);
        }
        result.insert("ownerId".into(), json!("other-owner"));
        runtime.handle(Message {
            kind: "authorized_tool_execution_result".into(),
            fields: result.clone(),
        });
        let rejected = receiver
            .recv()
            .await
            .expect("wrong owner result must reject");
        assert_eq!(rejected.kind, "error");
        assert_eq!(rejected.fields["failure"]["failureCode"], "authentication");
        assert!(runtime
            .journal
            .pending_tool_claim("invoke-1")
            .expect("pending claim lookup must succeed")
            .is_some());

        result.insert("ownerId".into(), json!("owner"));
        runtime.handle(Message {
            kind: "authorized_tool_execution_result".into(),
            fields: result,
        });
        let accepted = receiver
            .recv()
            .await
            .expect("authorized tool result must emit");
        assert_eq!(accepted.kind, "authorized_tool_result");
        assert_eq!(accepted.fields["outcome"], "succeeded");
        assert_eq!(accepted.fields["duplicate"], false);
    }

    #[tokio::test]
    async fn completed_run_authorizes_queued_tool_call_before_removal() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        let run = runtime
            .journal
            .admit_run("owner", "session", "conversation", 1)
            .expect("run must admit");
        let (cancel, _) = watch::channel(false);
        runtime.running.insert(
            "request".into(),
            RunningQuery {
                cancel,
                owner_id: "owner".into(),
                session_id: "session".into(),
                run_id: run.run_id,
                attempt_id: run.attempt_id,
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );
        let (tool_requests, mut queued_tool_requests) = mpsc::unbounded_channel();
        tool_requests
            .send(ToolRequest {
                request_id: "request".into(),
                client_id: "client".into(),
                call: rx4::ToolCall {
                    id: "invoke-queued".into(),
                    name: "search".into(),
                    arguments: r#"{"q":"omi"}"#.into(),
                },
            })
            .expect("queued tool call must send");

        runtime.complete_run("request".into(), &mut queued_tool_requests);

        let authorized = receiver
            .recv()
            .await
            .expect("queued tool call must authorize before completion");
        assert_eq!(authorized.kind, "authorized_tool_execution");
        assert_eq!(authorized.fields["invocationId"], "invoke-queued");
        assert!(!runtime.running.contains_key("request"));

        let mut result = authorized.fields;
        result.insert("type".into(), json!("authorized_tool_execution_result"));
        result.insert("outcome".into(), json!("succeeded"));
        result.insert("result".into(), json!("found"));
        for key in [
            "toolName",
            "input",
            "effectClass",
            "retryPolicy",
            "surfaceKind",
            "externalRefKind",
            "externalRefId",
            "originatingUserText",
            "precedingAssistantText",
            "runMode",
            "chatMode",
            "requestId",
            "clientId",
        ] {
            result.remove(key);
        }
        runtime.handle(Message {
            kind: "authorized_tool_execution_result".into(),
            fields: result,
        });
        let completed = receiver
            .recv()
            .await
            .expect("pending tool claim must complete after its run ends");
        assert_eq!(completed.kind, "authorized_tool_result");
    }

    #[tokio::test]
    async fn cancelled_run_discards_queued_tool_calls_and_revokes_claims() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        let run = runtime
            .journal
            .admit_run("owner", "session", "conversation", 1)
            .expect("run must admit");
        let (cancel, cancel_receiver) = watch::channel(false);
        runtime.running.insert(
            "request".into(),
            RunningQuery {
                cancel,
                owner_id: "owner".into(),
                session_id: "session".into(),
                run_id: run.run_id,
                attempt_id: run.attempt_id,
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );
        runtime.authorize_tool_request(ToolRequest {
            request_id: "request".into(),
            client_id: "client".into(),
            call: rx4::ToolCall {
                id: "invoke-before-cancel".into(),
                name: "search".into(),
                arguments: r#"{"q":"before"}"#.into(),
            },
        });
        let authorized = receiver
            .recv()
            .await
            .expect("pre-cancel tool must authorize");
        assert_eq!(authorized.kind, "authorized_tool_execution");

        runtime.handle(
            parse_line(r#"{"type":"interrupt","requestId":"request","clientId":"client","ownerId":"owner"}"#)
                .expect("interrupt fixture must parse"),
        );
        let ack = receiver.recv().await.expect("interrupt must acknowledge");
        assert_eq!(ack.kind, "cancel_ack");
        assert_eq!(ack.fields["accepted"], true);
        assert!(*cancel_receiver.borrow());
        assert!(runtime
            .journal
            .pending_tool_claim("invoke-before-cancel")
            .expect("claim lookup must succeed")
            .is_none());

        let (tool_requests, mut queued_tool_requests) = mpsc::unbounded_channel();
        tool_requests
            .send(ToolRequest {
                request_id: "request".into(),
                client_id: "client".into(),
                call: rx4::ToolCall {
                    id: "invoke-queued-after-cancel".into(),
                    name: "search".into(),
                    arguments: r#"{"q":"after"}"#.into(),
                },
            })
            .expect("queued tool call must send");

        runtime.complete_run("request".into(), &mut queued_tool_requests);

        assert!(receiver.try_recv().is_err());
        assert!(!runtime.running.contains_key("request"));
        assert!(runtime
            .journal
            .pending_tool_claim("invoke-queued-after-cancel")
            .expect("queued claim lookup must succeed")
            .is_none());
    }

    #[tokio::test]
    async fn restart_reconcile_revokes_pending_tool_claims() {
        let path = std::env::temp_dir().join(format!(
            "omi-runtime-claim-{}.sqlite3",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|duration| duration.as_millis())
                .unwrap_or(0)
        ));
        let mut journal = JournalStore::open(path.clone()).expect("journal must open");
        let relay = ToolRelay::new();
        let run = journal
            .admit_run("owner", "session", "conversation", 1)
            .expect("run must admit");
        relay
            .dispatch(
                &mut journal,
                Identity {
                    invocation_id: "invoke-restart".into(),
                    owner_id: "owner".into(),
                    session_id: "session".into(),
                    run_id: run.run_id,
                    attempt_id: run.attempt_id,
                    profile_generation: 1,
                    daemon_boot_epoch: "boot".into(),
                    execution_generation: 1,
                },
                "search".into(),
                serde_json::from_value(json!({"q":"omi"})).unwrap_or_default(),
                "main_chat".into(),
                None,
                None,
                "act".into(),
            )
            .expect("dispatch must persist");
        drop(journal);
        let mut reopened = JournalStore::open(path.clone()).expect("journal must reopen");
        assert_eq!(
            reopened
                .reconcile_pending_tool_claims(Some("owner"))
                .expect("reconcile"),
            1
        );
        assert!(reopened
            .pending_tool_claim("invoke-restart")
            .expect("lookup")
            .is_none());
        let _ = std::fs::remove_file(path);
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
    async fn rejects_an_oversized_jsonl_frame_without_losing_the_next_frame() {
        let oversized = format!("{}\n{{\"type\":\"stop\"}}\n", "x".repeat(33));
        let mut reader = BufReader::new(std::io::Cursor::new(oversized));

        let error = read_bounded_jsonl_line(&mut reader, 32)
            .await
            .expect_err("oversized JSONL frame must reject");
        assert_eq!(error.kind(), std::io::ErrorKind::InvalidData);
        let next = read_bounded_jsonl_line(&mut reader, 32)
            .await
            .expect("next frame must be readable")
            .expect("next frame must exist");
        assert_eq!(next, b"{\"type\":\"stop\"}\n");
    }

    #[tokio::test]
    async fn unparseable_stdin_frame_emits_an_error_envelope() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle_stdin_frame(b"{not valid json");
        let error = receiver
            .recv()
            .await
            .expect("unparseable frame must respond");
        assert_eq!(error.kind, "error");
        assert_eq!(error.fields["failure"]["code"], "invalid_request");

        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle_stdin_frame(&[0xff, 0xfe, 0xfd]);
        let error = receiver.recv().await.expect("non-UTF-8 frame must respond");
        assert_eq!(error.kind, "error");
        assert_eq!(error.fields["failure"]["code"], "invalid_request");
    }

    #[tokio::test]
    async fn invalidate_session_without_surface_fields_emits_an_error() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"o"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(
            parse_line(
                r#"{"type":"invalidate_session","requestId":"i","clientId":"c","ownerId":"o"}"#,
            )
            .expect("fixture must parse"),
        );
        let response = receiver.recv().await.expect("invalidation must respond");
        assert_eq!(response.kind, "error");
        assert_eq!(response.fields["requestId"], "i");
        assert_eq!(response.fields["failure"]["code"], "invalid_request");
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
        let invalidation = receiver.try_recv().expect("invalidation must emit");
        assert_eq!(invalidation.kind, "session_invalidated");
        assert_eq!(invalidation.fields["invalidated"], true);
        assert_eq!(invalidation.fields["sessionId"], session_id);
    }

    #[tokio::test]
    async fn query_rejects_an_invalidated_session_before_run_admission() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(Some("https://api.omi.me/v2".into()), output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.credentials = Some(ManagedCredentials {
            owner_id: "owner".into(),
            bearer_token: "test-token".into(),
        });
        runtime.handle(parse_line(r#"{"type":"configure_default_execution_profile","requestId":"profile","clientId":"client","ownerId":"owner","adapterId":"rx4","workingDirectory":"/tmp/omi"}"#).expect("profile fixture must parse"));
        let _ = receiver.recv().await.expect("profile response must emit");
        runtime.handle(parse_line(r#"{"type":"resolve_surface_session","requestId":"resolve","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("surface fixture must parse"));
        let resolved = receiver.recv().await.expect("surface response must emit");
        let session_id = resolved.fields["sessionId"]
            .as_str()
            .expect("session id must be present")
            .to_owned();
        runtime.handle(parse_line(r#"{"type":"invalidate_session","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("invalidation fixture must parse"));
        let _ = receiver.recv().await.expect("invalidation must emit");

        runtime.handle(parse_line(&format!(r#"{{"type":"query","requestId":"query","clientId":"client","ownerId":"owner","sessionId":"{session_id}","prompt":"hello"}}"#)).expect("query fixture must parse"));
        let rejection = receiver.recv().await.expect("stale session must reject");
        assert_eq!(rejection.kind, "error");
        assert_eq!(
            rejection.fields["failure"]["failureCode"],
            "invalid_request"
        );
        assert!(!runtime.running.contains_key("query"));
    }

    #[tokio::test]
    async fn invalidating_a_session_revokes_its_pending_tool_claims() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(parse_line(r#"{"type":"configure_default_execution_profile","requestId":"profile","clientId":"client","ownerId":"owner","adapterId":"rx4","workingDirectory":"/tmp/omi"}"#).expect("profile fixture must parse"));
        let _ = receiver.recv().await.expect("profile response must emit");
        runtime.handle(parse_line(r#"{"type":"resolve_surface_session","requestId":"resolve","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("surface fixture must parse"));
        let resolved = receiver.recv().await.expect("surface response must emit");
        let session_id = resolved.fields["sessionId"]
            .as_str()
            .expect("session id must be present")
            .to_owned();
        let conversation_id = runtime
            .sessions
            .get(&session_id)
            .expect("resolved session must exist")
            .conversation_id
            .clone();
        let run = runtime
            .journal
            .admit_run("owner", &session_id, &conversation_id, 1)
            .expect("run must admit");
        let (cancel, _) = watch::channel(false);
        runtime.running.insert(
            "request".into(),
            RunningQuery {
                cancel,
                owner_id: "owner".into(),
                session_id: session_id.clone(),
                run_id: run.run_id,
                attempt_id: run.attempt_id,
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );
        let (tool_requests, mut queued_tool_requests) = mpsc::unbounded_channel();
        tool_requests
            .send(ToolRequest {
                request_id: "request".into(),
                client_id: "client".into(),
                call: rx4::ToolCall {
                    id: "invoke-1".into(),
                    name: "search".into(),
                    arguments: r#"{"q":"omi"}"#.into(),
                },
            })
            .expect("queued tool call must send");
        runtime.complete_run("request".into(), &mut queued_tool_requests);
        assert!(!runtime.running.contains_key("request"));
        let authorized = receiver
            .recv()
            .await
            .expect("queued tool execution must authorize before run removal");
        runtime.handle(parse_line(r#"{"type":"invalidate_session","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("invalidation fixture must parse"));
        let invalidation = receiver.recv().await.expect("invalidation must emit");
        assert_eq!(invalidation.kind, "session_invalidated");
        assert_eq!(invalidation.fields["revokedToolClaims"], 1);
        let mut result = authorized.fields;
        result.insert("type".into(), json!("authorized_tool_execution_result"));
        result.insert("outcome".into(), json!("succeeded"));
        result.insert("result".into(), json!("found"));
        for key in [
            "toolName",
            "input",
            "effectClass",
            "retryPolicy",
            "surfaceKind",
            "externalRefKind",
            "externalRefId",
            "originatingUserText",
            "precedingAssistantText",
            "runMode",
            "chatMode",
            "requestId",
            "clientId",
        ] {
            result.remove(key);
        }
        runtime.authorized_tool_execution_result(result);
        let rejection = receiver
            .recv()
            .await
            .expect("revoked claim must reject completion");
        assert_eq!(rejection.kind, "error");
        assert_eq!(
            rejection.fields["failure"]["failureCode"],
            "invalid_request"
        );
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
        runtime.running.insert(
            "request-a".into(),
            RunningQuery {
                cancel,
                owner_id: "owner-a".into(),
                session_id: "session".into(),
                run_id: "run-a".into(),
                attempt_id: "attempt-a".into(),
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );

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
    async fn surface_session_uses_the_journal_conversation_id() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(parse_line(r#"{"type":"configure_default_execution_profile","requestId":"profile","clientId":"client","ownerId":"owner","adapterId":"rx4","workingDirectory":"/tmp/omi"}"#).expect("profile fixture must parse"));
        let _ = receiver.recv().await.expect("profile response must emit");
        runtime.handle(parse_line(r#"{"type":"resolve_surface_session","requestId":"resolve","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("resolve fixture must parse"));
        let resolved = receiver.recv().await.expect("surface response must emit");
        let conversation_id = resolved.fields["conversationId"]
            .as_str()
            .expect("resolved conversation ID must be present")
            .to_owned();

        runtime.handle(parse_line(r#"{"type":"journal_record_turn","requestId":"record","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turn":{"turnId":"turn-1","role":"user","content":"hello","status":"completed"}}"#).expect("record fixture must parse"));
        let record = receiver.recv().await.expect("journal response must emit");
        assert_eq!(record.fields["conversationId"], conversation_id);
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
    async fn journal_import_remote_turn_returns_the_imported_projection() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );

        runtime.handle(parse_line(r#"{"type":"journal_import_remote_turn","requestId":"import","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turn":{"remoteId":"remote-1","canonicalTurnId":"turn-1","role":"assistant","content":"hello","contentBlocks":[],"resources":[],"metadataJson":"{}","createdAtMs":1}}"#).expect("import fixture must parse"));

        let imported = receiver.recv().await.expect("import response must emit");
        assert_eq!(imported.kind, "journal_operation_result");
        assert_eq!(imported.fields["operation"], "import_remote");
        assert_eq!(imported.fields["turn"]["turnId"], "turn-1");
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

    #[tokio::test]
    async fn journal_repair_turns_terminalizes_orphaned_assistant_turns() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(None, output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.handle(parse_line(r#"{"type":"journal_record_turn","requestId":"record","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turn":{"turnId":"orphan-turn","role":"assistant","origin":"agent_runtime","status":"streaming","content":"partial","contentBlocks":[],"resources":[],"metadataJson":"{}"}}"#).expect("record fixture must parse"));
        let _ = receiver.recv().await.expect("record response must emit");
        let _ = receiver.recv().await.expect("record change must emit");

        runtime.handle(parse_line(r#"{"type":"journal_repair_turns","requestId":"repair","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1","turnIds":["orphan-turn","orphan-turn","missing"]}"#).expect("repair fixture must parse"));
        let repaired = receiver.recv().await.expect("repair response must emit");
        assert_eq!(repaired.kind, "journal_operation_result");
        assert_eq!(repaired.fields["operation"], "repair");
        assert_eq!(repaired.fields["turns"].as_array().map(Vec::len), Some(1));
        assert_eq!(repaired.fields["turns"][0]["turnId"], "orphan-turn");
        assert_eq!(repaired.fields["turns"][0]["status"], "failed");
        let changed = receiver.recv().await.expect("repair change must emit");
        assert_eq!(changed.kind, "journal_turn_changed");
        assert_eq!(changed.fields["turn"]["status"], "failed");
    }

    #[tokio::test]
    async fn resolve_and_query_reject_empty_working_directory() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let mut runtime = test_runtime(Some("https://api.omi.me/v2".into()), output, completed);
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        runtime.credentials = Some(ManagedCredentials {
            owner_id: "owner".into(),
            bearer_token: "test-token".into(),
        });

        runtime.handle(parse_line(r#"{"type":"resolve_surface_session","requestId":"resolve","clientId":"client","ownerId":"owner","surfaceKind":"main_chat","externalRefKind":"chat","externalRefId":"chat-1"}"#).expect("resolve fixture must parse"));
        let rejection = receiver
            .recv()
            .await
            .expect("empty working directory must reject session creation");
        assert_eq!(rejection.kind, "error");
        assert_eq!(
            rejection.fields["failure"]["failureCode"],
            "invalid_request"
        );
        assert!(runtime.sessions.is_empty());

        runtime.sessions.insert(
            "rx4-session-empty".into(),
            SurfaceSession {
                owner_id: "owner".into(),
                surface_kind: "main_chat".into(),
                conversation_id: "conversation".into(),
                profile: default_profile(),
            },
        );
        runtime.handle(parse_line(r#"{"type":"query","requestId":"query","clientId":"client","ownerId":"owner","sessionId":"rx4-session-empty","prompt":"hello"}"#).expect("query fixture must parse"));
        let query_rejection = receiver
            .recv()
            .await
            .expect("empty working directory must reject query");
        assert_eq!(query_rejection.kind, "error");
        assert_eq!(
            query_rejection.fields["failure"]["failureCode"],
            "invalid_request"
        );
        assert!(!runtime.running.contains_key("query"));
    }

    #[tokio::test]
    async fn complete_run_does_not_authorize_tools_for_other_runs() {
        let (output, mut receiver) = mpsc::unbounded_channel();
        let (completed, _) = mpsc::unbounded_channel();
        let journal = JournalStore::in_memory().expect("journal must open");
        let (tool_requests, mut queued_tool_requests) = mpsc::unbounded_channel();
        let mut runtime = Runtime::new(
            None,
            journal,
            output,
            completed,
            tool_requests,
            "boot-test".into(),
        );
        runtime.handle(
            parse_line(r#"{"type":"refresh_owner","ownerId":"owner"}"#)
                .expect("owner fixture must parse"),
        );
        let run_a = runtime
            .journal
            .admit_run("owner", "session-a", "conversation", 1)
            .expect("run a must admit");
        let run_b = runtime
            .journal
            .admit_run("owner", "session-b", "conversation", 1)
            .expect("run b must admit");
        let (cancel_a, _) = watch::channel(false);
        let (cancel_b, _) = watch::channel(false);
        runtime.running.insert(
            "request-a".into(),
            RunningQuery {
                cancel: cancel_a,
                owner_id: "owner".into(),
                session_id: "session-a".into(),
                run_id: run_a.run_id,
                attempt_id: run_a.attempt_id,
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );
        runtime.running.insert(
            "request-b".into(),
            RunningQuery {
                cancel: cancel_b,
                owner_id: "owner".into(),
                session_id: "session-b".into(),
                run_id: run_b.run_id,
                attempt_id: run_b.attempt_id,
                profile_generation: 1,
                surface_kind: "main_chat".into(),
            },
        );
        runtime
            .tool_requests
            .send(ToolRequest {
                request_id: "request-b".into(),
                client_id: "client".into(),
                call: rx4::ToolCall {
                    id: "invoke-b".into(),
                    name: "search".into(),
                    arguments: r#"{"q":"other"}"#.into(),
                },
            })
            .expect("other run tool must queue");
        runtime
            .tool_requests
            .send(ToolRequest {
                request_id: "request-a".into(),
                client_id: "client".into(),
                call: rx4::ToolCall {
                    id: "invoke-a".into(),
                    name: "search".into(),
                    arguments: r#"{"q":"same"}"#.into(),
                },
            })
            .expect("completing run tool must queue");

        runtime.complete_run("request-a".into(), &mut queued_tool_requests);

        let authorized = receiver
            .recv()
            .await
            .expect("completing run tool must authorize");
        assert_eq!(authorized.kind, "authorized_tool_execution");
        assert_eq!(authorized.fields["invocationId"], "invoke-a");
        assert!(receiver.try_recv().is_err());
        assert!(runtime.running.contains_key("request-b"));
        assert!(!runtime.running.contains_key("request-a"));

        let deferred = queued_tool_requests
            .try_recv()
            .expect("other run tool must remain queued");
        assert_eq!(deferred.request_id, "request-b");
        assert_eq!(deferred.call.id, "invoke-b");
    }
}
