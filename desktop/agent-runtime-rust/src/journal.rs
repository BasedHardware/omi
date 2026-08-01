use rusqlite::{params, Connection, OptionalExtension, Transaction};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

const RUNTIME_STATE_RETENTION_MS: u64 = 30 * 24 * 60 * 60 * 1000;

#[derive(Clone)]
pub struct Surface {
    pub owner_id: String,
    pub surface_kind: String,
    pub external_ref_kind: String,
    pub external_ref_id: String,
}

pub struct ResultPage {
    pub conversation_id: String,
    pub turn: Option<Value>,
    pub turns: Vec<Value>,
    pub cleared_count: u64,
    pub high_water_turn_seq: u64,
    pub generation: u64,
    pub generation_base_turn_seq: u64,
}

pub struct JournalStore {
    connection: Connection,
}

#[derive(Clone)]
pub struct RunIdentity {
    pub run_id: String,
    pub attempt_id: String,
}

#[derive(Clone)]
pub struct ToolClaim {
    pub invocation_id: String,
    pub owner_id: String,
    pub session_id: String,
    pub run_id: String,
    pub attempt_id: String,
    pub profile_generation: u64,
    pub daemon_boot_epoch: String,
    pub execution_generation: u64,
    pub tool_name: String,
    pub input_hash: String,
    pub status: String,
    pub outcome: Option<String>,
    pub result: Option<String>,
}

impl JournalStore {
    pub fn open_default() -> Result<Self, String> {
        let state_dir = env::var_os("OMI_AGENT_STATE_DIR")
            .map(PathBuf::from)
            .or_else(|| {
                env::var_os("HOME").map(|home| {
                    PathBuf::from(home)
                        .join("Library")
                        .join("Application Support")
                        .join("Omi")
                        .join("agent")
                })
            })
            .ok_or_else(|| "cannot determine Omi agent state directory".to_owned())?;
        fs::create_dir_all(&state_dir).map_err(|error| error.to_string())?;
        Self::open(state_dir.join("omi-agentd.sqlite3"))
    }

    pub fn in_memory() -> Result<Self, String> {
        Self::from_connection(Connection::open_in_memory().map_err(|error| error.to_string())?)
    }

    pub fn open(path: PathBuf) -> Result<Self, String> {
        Self::from_connection(Connection::open(path).map_err(|error| error.to_string())?)
    }

    fn from_connection(connection: Connection) -> Result<Self, String> {
        connection
            .execute_batch("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;")
            .map_err(|error| error.to_string())?;
        let store = Self { connection };
        store.migrate()?;
        Ok(store)
    }

    fn migrate(&self) -> Result<(), String> {
        self.connection
            .execute_batch(
                "CREATE TABLE IF NOT EXISTS rx4_journal_conversations (
                 owner_id TEXT NOT NULL,
                 surface_kind TEXT NOT NULL,
                 external_ref_kind TEXT NOT NULL,
                 external_ref_id TEXT NOT NULL,
                 conversation_id TEXT NOT NULL,
                 generation INTEGER NOT NULL DEFAULT 1,
                 generation_base_turn_seq INTEGER NOT NULL DEFAULT 0,
                 high_water_turn_seq INTEGER NOT NULL DEFAULT 0,
                 PRIMARY KEY (owner_id, surface_kind, external_ref_kind, external_ref_id),
                 UNIQUE (conversation_id)
             );
             CREATE TABLE IF NOT EXISTS rx4_journal_turns (
                 conversation_id TEXT NOT NULL,
                 turn_id TEXT NOT NULL,
                 turn_seq INTEGER NOT NULL,
                 producer_id TEXT NOT NULL,
                 payload_hash TEXT NOT NULL,
                 role TEXT NOT NULL,
                 surface_kind TEXT NOT NULL,
                 external_ref_kind TEXT NOT NULL,
                 external_ref_id TEXT NOT NULL,
                 content TEXT NOT NULL,
                 origin TEXT NOT NULL,
                 status TEXT NOT NULL,
                 content_blocks_json TEXT NOT NULL,
                 resources_json TEXT NOT NULL,
                 producing_run_id TEXT,
                 producing_attempt_id TEXT,
                 metadata_json TEXT NOT NULL,
                 created_at_ms INTEGER NOT NULL,
                 updated_at_ms INTEGER NOT NULL,
                 completed_at_ms INTEGER,
                 PRIMARY KEY (conversation_id, turn_id),
                 UNIQUE (conversation_id, turn_seq),
                 UNIQUE (conversation_id, producer_id)
             );
             CREATE INDEX IF NOT EXISTS rx4_journal_turns_seq_idx
                 ON rx4_journal_turns(conversation_id, turn_seq);
             CREATE TABLE IF NOT EXISTS rx4_runtime_runs (
                 run_id TEXT PRIMARY KEY,
                 attempt_id TEXT NOT NULL UNIQUE,
                 owner_id TEXT NOT NULL,
                 session_id TEXT NOT NULL,
                 conversation_id TEXT,
                 profile_generation INTEGER NOT NULL,
                 created_at_ms INTEGER NOT NULL
             );
             CREATE TABLE IF NOT EXISTS rx4_tool_claims (
                 invocation_id TEXT PRIMARY KEY,
                 owner_id TEXT NOT NULL,
                 session_id TEXT NOT NULL,
                 run_id TEXT NOT NULL,
                 attempt_id TEXT NOT NULL,
                 profile_generation INTEGER NOT NULL,
                 daemon_boot_epoch TEXT NOT NULL,
                 execution_generation INTEGER NOT NULL,
                 tool_name TEXT NOT NULL,
                 input_hash TEXT NOT NULL,
                 status TEXT NOT NULL,
                 outcome TEXT,
                 result TEXT,
                 created_at_ms INTEGER NOT NULL,
                 updated_at_ms INTEGER NOT NULL
             );
             CREATE INDEX IF NOT EXISTS rx4_tool_claims_owner_run_idx
                 ON rx4_tool_claims(owner_id, run_id, status);",
            )
            .map_err(|error| error.to_string())?;
        let has_run_conversation: bool = self
            .connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM pragma_table_info('rx4_runtime_runs') WHERE name = 'conversation_id')",
                [],
                |row| row.get(0),
            )
            .map_err(|error| error.to_string())?;
        if !has_run_conversation {
            self.connection
                .execute_batch("ALTER TABLE rx4_runtime_runs ADD COLUMN conversation_id TEXT;")
                .map_err(|error| error.to_string())?;
        }
        self.migrate_node_journal()?;
        Ok(())
    }

    pub fn conversation_id(&self, surface: &Surface) -> Result<String, String> {
        ensure_conversation(&self.connection, surface)
    }

    pub fn admit_run(
        &mut self,
        owner_id: &str,
        session_id: &str,
        conversation_id: &str,
        profile_generation: u64,
    ) -> Result<RunIdentity, String> {
        let identity = RunIdentity {
            run_id: Uuid::new_v4().to_string(),
            attempt_id: Uuid::new_v4().to_string(),
        };
        self.connection.execute("INSERT INTO rx4_runtime_runs(run_id, attempt_id, owner_id, session_id, conversation_id, profile_generation, created_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?)", params![identity.run_id, identity.attempt_id, owner_id, session_id, conversation_id, profile_generation, now_ms()]).map_err(|error| error.to_string())?;
        Ok(identity)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn authorize_tool_claim(
        &mut self,
        invocation_id: &str,
        owner_id: &str,
        session_id: &str,
        run_id: &str,
        attempt_id: &str,
        profile_generation: u64,
        daemon_boot_epoch: &str,
        execution_generation: u64,
        tool_name: &str,
        input_hash: &str,
    ) -> Result<(), String> {
        let existing: Option<String> = self
            .connection
            .query_row(
                "SELECT status FROM rx4_tool_claims WHERE invocation_id = ?",
                params![invocation_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(|error| error.to_string())?;
        if existing.is_some() {
            return Err("authorized tool invocation is already known".into());
        }
        let run_matches: bool = self
            .connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM rx4_runtime_runs WHERE run_id = ? AND attempt_id = ? AND owner_id = ? AND session_id = ?)",
                params![run_id, attempt_id, owner_id, session_id],
                |row| row.get(0),
            )
            .map_err(|error| error.to_string())?;
        if !run_matches {
            return Err("authorized tool claim does not match an admitted run attempt".into());
        }
        let created = now_ms();
        self.connection
            .execute(
                "INSERT INTO rx4_tool_claims(
                    invocation_id, owner_id, session_id, run_id, attempt_id,
                    profile_generation, daemon_boot_epoch, execution_generation,
                    tool_name, input_hash, status, created_at_ms, updated_at_ms
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                params![
                    invocation_id,
                    owner_id,
                    session_id,
                    run_id,
                    attempt_id,
                    profile_generation,
                    daemon_boot_epoch,
                    execution_generation,
                    tool_name,
                    input_hash,
                    created,
                    created
                ],
            )
            .map_err(|error| error.to_string())?;
        Ok(())
    }

    pub fn pending_tool_claim(&self, invocation_id: &str) -> Result<Option<ToolClaim>, String> {
        self.tool_claim_with_status(invocation_id, "pending")
    }

    pub fn completed_tool_claim(&self, invocation_id: &str) -> Result<Option<Value>, String> {
        let claim = self.tool_claim_with_status(invocation_id, "completed")?;
        Ok(claim.map(|claim| {
            json!({
                "invocationId": claim.invocation_id,
                "outcome": claim.outcome.unwrap_or_default(),
                "result": claim.result.unwrap_or_default()
            })
        }))
    }

    pub fn complete_tool_claim(
        &mut self,
        invocation_id: &str,
        outcome: &str,
        result: &str,
    ) -> Result<(), String> {
        let updated = self
            .connection
            .execute(
                "UPDATE rx4_tool_claims
                 SET status = 'completed', outcome = ?, result = ?, updated_at_ms = ?
                 WHERE invocation_id = ? AND status = 'pending'",
                params![outcome, result, now_ms(), invocation_id],
            )
            .map_err(|error| error.to_string())?;
        if updated == 0 {
            return Err("authorized tool result is unknown".into());
        }
        Ok(())
    }

    pub fn revoke_tool_claims(
        &mut self,
        owner_id: &str,
        run_id: Option<&str>,
    ) -> Result<u64, String> {
        let updated = match run_id {
            Some(run_id) => self
                .connection
                .execute(
                    "UPDATE rx4_tool_claims
                     SET status = 'revoked', updated_at_ms = ?
                     WHERE owner_id = ? AND run_id = ? AND status = 'pending'",
                    params![now_ms(), owner_id, run_id],
                )
                .map_err(|error| error.to_string())?,
            None => self
                .connection
                .execute(
                    "UPDATE rx4_tool_claims
                     SET status = 'revoked', updated_at_ms = ?
                     WHERE owner_id = ? AND status = 'pending'",
                    params![now_ms(), owner_id],
                )
                .map_err(|error| error.to_string())?,
        };
        Ok(updated as u64)
    }

    pub fn revoke_tool_claims_for_session(
        &mut self,
        owner_id: &str,
        session_id: &str,
    ) -> Result<u64, String> {
        let updated = self
            .connection
            .execute(
                "UPDATE rx4_tool_claims
                 SET status = 'revoked', updated_at_ms = ?
                 WHERE owner_id = ? AND session_id = ? AND status = 'pending'",
                params![now_ms(), owner_id, session_id],
            )
            .map_err(|error| error.to_string())?;
        Ok(updated as u64)
    }

    pub fn reconcile_pending_tool_claims(&mut self, owner_id: Option<&str>) -> Result<u64, String> {
        let updated = match owner_id {
            Some(owner_id) => self
                .connection
                .execute(
                    "UPDATE rx4_tool_claims
                     SET status = 'revoked', updated_at_ms = ?
                     WHERE owner_id = ? AND status = 'pending'",
                    params![now_ms(), owner_id],
                )
                .map_err(|error| error.to_string())?,
            None => self
                .connection
                .execute(
                    "UPDATE rx4_tool_claims
                     SET status = 'revoked', updated_at_ms = ?
                     WHERE status = 'pending'",
                    params![now_ms()],
                )
                .map_err(|error| error.to_string())?,
        };
        Ok(updated as u64)
    }

    pub fn prune_expired_runtime_state(&mut self) -> Result<u64, String> {
        self.prune_terminal_runtime_state_before(
            now_ms().saturating_sub(RUNTIME_STATE_RETENTION_MS),
        )
    }

    pub fn prune_terminal_runtime_state_before(
        &mut self,
        expired_before_ms: u64,
    ) -> Result<u64, String> {
        let transaction = self
            .connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let claims = transaction
            .execute(
                "DELETE FROM rx4_tool_claims
                 WHERE status IN ('completed', 'revoked') AND updated_at_ms < ?",
                params![expired_before_ms],
            )
            .map_err(|error| error.to_string())?;
        let runs = transaction
            .execute(
                "DELETE FROM rx4_runtime_runs
                 WHERE created_at_ms < ?
                   AND NOT EXISTS (
                       SELECT 1 FROM rx4_tool_claims
                       WHERE rx4_tool_claims.run_id = rx4_runtime_runs.run_id
                   )",
                params![expired_before_ms],
            )
            .map_err(|error| error.to_string())?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok((claims + runs) as u64)
    }

    fn tool_claim_with_status(
        &self,
        invocation_id: &str,
        status: &str,
    ) -> Result<Option<ToolClaim>, String> {
        self.connection
            .query_row(
                "SELECT invocation_id, owner_id, session_id, run_id, attempt_id,
                        profile_generation, daemon_boot_epoch, execution_generation,
                        tool_name, input_hash, status, outcome, result
                 FROM rx4_tool_claims
                 WHERE invocation_id = ? AND status = ?",
                params![invocation_id, status],
                |row| {
                    Ok(ToolClaim {
                        invocation_id: row.get(0)?,
                        owner_id: row.get(1)?,
                        session_id: row.get(2)?,
                        run_id: row.get(3)?,
                        attempt_id: row.get(4)?,
                        profile_generation: row.get(5)?,
                        daemon_boot_epoch: row.get(6)?,
                        execution_generation: row.get(7)?,
                        tool_name: row.get(8)?,
                        input_hash: row.get(9)?,
                        status: row.get(10)?,
                        outcome: row.get(11)?,
                        result: row.get(12)?,
                    })
                },
            )
            .optional()
            .map_err(|error| error.to_string())
    }

    fn migrate_node_journal(&self) -> Result<(), String> {
        let has_surfaces: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'surface_conversations')",
            [],
            |row| row.get(0),
        ).map_err(|error| error.to_string())?;
        let has_turns: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'conversation_turns')",
            [],
            |row| row.get(0),
        ).map_err(|error| error.to_string())?;
        let has_state: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'conversation_journal_state')",
            [],
            |row| row.get(0),
        ).map_err(|error| error.to_string())?;
        let has_producing_attempt: bool = self
            .connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM pragma_table_info('conversation_turns') WHERE name = 'producing_attempt_id')",
                [],
                |row| row.get(0),
            )
            .map_err(|error| error.to_string())?;
        if !has_surfaces || !has_turns || !has_state || !has_producing_attempt {
            return Ok(());
        }
        self.connection
            .execute_batch(
                "INSERT OR IGNORE INTO rx4_journal_conversations(
                 owner_id, surface_kind, external_ref_kind, external_ref_id, conversation_id,
                 generation, generation_base_turn_seq, high_water_turn_seq
             )
             SELECT sc.owner_id, sc.surface_kind, sc.external_ref_kind, sc.external_ref_id,
                    sc.conversation_id, COALESCE(js.generation, 1),
                    COALESCE(js.generation_base_turn_seq, 0),
                    COALESCE(js.high_water_turn_seq, 0)
             FROM surface_conversations sc
             LEFT JOIN conversation_journal_state js ON js.conversation_id = sc.conversation_id;
             INSERT OR IGNORE INTO rx4_journal_turns(
                 conversation_id, turn_id, turn_seq, producer_id, payload_hash, role,
                 surface_kind, external_ref_kind, external_ref_id, content, origin, status,
                 content_blocks_json, resources_json, producing_run_id, producing_attempt_id,
                 metadata_json, created_at_ms, updated_at_ms, completed_at_ms
             )
             SELECT ct.conversation_id, ct.turn_id, ct.turn_seq, ct.producer_id,
                    ct.payload_hash, ct.role, ct.surface_kind, sc.external_ref_kind,
                    sc.external_ref_id, ct.content, ct.origin, ct.status,
                    ct.content_blocks_json, ct.resources_json, ct.producing_run_id,
                    ct.producing_attempt_id, ct.metadata_json, ct.created_at_ms,
                    ct.updated_at_ms, ct.completed_at_ms
             FROM conversation_turns ct
             JOIN surface_conversations sc ON sc.conversation_id = ct.conversation_id;",
            )
            .map_err(|error| error.to_string())?;
        Ok(())
    }

    pub fn record(
        &mut self,
        surface: &Surface,
        input: &Map<String, Value>,
    ) -> Result<ResultPage, String> {
        self.record_many(surface, std::slice::from_ref(input))
    }

    pub fn record_many(
        &mut self,
        surface: &Surface,
        inputs: &[Map<String, Value>],
    ) -> Result<ResultPage, String> {
        if inputs.is_empty() {
            return Err("journal exchange requires turns".into());
        }
        let transaction = self
            .connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let conversation_id = ensure_conversation(&transaction, surface)?;
        let mut turns = Vec::with_capacity(inputs.len());
        for input in inputs {
            turns.push(record_turn(&transaction, &conversation_id, surface, input)?);
        }
        let state = state(&transaction, &conversation_id)?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(ResultPage {
            conversation_id,
            turn: turns.first().cloned(),
            turns,
            cleared_count: 0,
            high_water_turn_seq: state.2,
            generation: state.0,
            generation_base_turn_seq: state.1,
        })
    }

    pub fn update(
        &mut self,
        surface: &Surface,
        input: &Map<String, Value>,
    ) -> Result<ResultPage, String> {
        reject_private_fields(input)?;
        let turn_id = required(input, "turnId")?;
        let transaction = self
            .connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let conversation_id = ensure_conversation(&transaction, surface)?;
        let current = turn_row(&transaction, &conversation_id, &turn_id)?
            .ok_or_else(|| "journal turn not found".to_owned())?;
        if current.producing_run_id.is_some() {
            return Err(
                "runtime-produced journal turns require kernel-authoritative terminalization"
                    .into(),
            );
        }
        let turn = mutate_turn(
            &transaction,
            &conversation_id,
            surface,
            current,
            input,
            None,
        )?;
        let state = state(&transaction, &conversation_id)?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(ResultPage {
            conversation_id,
            turn: Some(turn.clone()),
            turns: vec![turn],
            cleared_count: 0,
            high_water_turn_seq: state.2,
            generation: state.0,
            generation_base_turn_seq: state.1,
        })
    }

    pub fn terminalize(
        &mut self,
        surface: &Surface,
        input: &Map<String, Value>,
    ) -> Result<ResultPage, String> {
        let turn_id = required(input, "turnId")?;
        let run_id = required(input, "producingRunId")?;
        let attempt_id = required(input, "producingAttemptId")?;
        let disposition = required(input, "disposition")?;
        if disposition != "accept" && disposition != "discard" {
            return Err("journal terminalization disposition is invalid".into());
        }
        if disposition == "discard"
            && (input.contains_key("content")
                || input.contains_key("replaceContentBlocks")
                || input.contains_key("replaceResources"))
        {
            return Err("discarded terminalization cannot apply material".into());
        }
        let transaction = self
            .connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let conversation_id = ensure_conversation(&transaction, surface)?;
        let mut current = turn_row(&transaction, &conversation_id, &turn_id)?
            .ok_or_else(|| "journal turn not found".to_owned())?;
        let run_matches: bool = transaction
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM rx4_runtime_runs WHERE run_id = ? AND attempt_id = ? AND owner_id = ? AND conversation_id = ?)",
                params![run_id, attempt_id, surface.owner_id, conversation_id],
                |row| row.get(0),
            )
            .map_err(|error| error.to_string())?;
        if !run_matches {
            return Err("journal terminalization does not match producing run attempt".into());
        }
        if current.producing_run_id.is_none() && current.producing_attempt_id.is_none() {
            transaction
                .execute(
                    "UPDATE rx4_journal_turns SET producing_run_id = ?, producing_attempt_id = ? WHERE conversation_id = ? AND turn_id = ?",
                    params![run_id, attempt_id, conversation_id, turn_id],
                )
                .map_err(|error| error.to_string())?;
            current.producing_run_id = Some(run_id.clone());
            current.producing_attempt_id = Some(attempt_id.clone());
        } else if current.producing_run_id.as_deref() != Some(run_id.as_str())
            || current.producing_attempt_id.as_deref() != Some(attempt_id.as_str())
        {
            return Err("journal terminalization does not match producing run attempt".into());
        }
        let mut patch = input.clone();
        patch.insert(
            "status".into(),
            Value::String(if disposition == "accept" {
                "completed".into()
            } else {
                "failed".into()
            }),
        );
        let turn = mutate_turn(
            &transaction,
            &conversation_id,
            surface,
            current,
            &patch,
            Some(disposition.as_str()),
        )?;
        let state = state(&transaction, &conversation_id)?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(ResultPage {
            conversation_id,
            turn: Some(turn.clone()),
            turns: vec![turn],
            cleared_count: 0,
            high_water_turn_seq: state.2,
            generation: state.0,
            generation_base_turn_seq: state.1,
        })
    }

    pub fn list(
        &mut self,
        surface: &Surface,
        after: u64,
        limit: u64,
    ) -> Result<ResultPage, String> {
        let conversation_id = ensure_conversation(&self.connection, surface)?;
        let (generation, base, high_water) = state(&self.connection, &conversation_id)?;
        let mut statement = self.connection.prepare("SELECT conversation_id, turn_id, turn_seq, producer_id, payload_hash, role, surface_kind, external_ref_kind, external_ref_id, content, origin, status, content_blocks_json, resources_json, producing_run_id, producing_attempt_id, metadata_json, created_at_ms, updated_at_ms, completed_at_ms FROM rx4_journal_turns WHERE conversation_id = ? AND turn_seq > ? ORDER BY turn_seq ASC LIMIT ?").map_err(|error| error.to_string())?;
        let rows = statement
            .query_map(
                params![conversation_id, after, limit.clamp(1, 100)],
                row_to_turn,
            )
            .map_err(|error| error.to_string())?;
        let mut turns = rows
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        for turn in &mut turns {
            apply_state(turn, generation, base);
        }
        Ok(ResultPage {
            conversation_id,
            turn: None,
            turns,
            cleared_count: 0,
            high_water_turn_seq: high_water,
            generation,
            generation_base_turn_seq: base,
        })
    }

    pub fn clear(
        &mut self,
        surface: &Surface,
        expected_generation: Option<u64>,
    ) -> Result<ResultPage, String> {
        let transaction = self
            .connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let conversation_id = ensure_conversation(&transaction, surface)?;
        let (generation, _, high_water) = state(&transaction, &conversation_id)?;
        if expected_generation.is_some_and(|expected| expected != generation) {
            return Err("journal generation is stale".into());
        }
        let cleared_count = transaction
            .execute(
                "DELETE FROM rx4_journal_turns WHERE conversation_id = ?",
                params![conversation_id],
            )
            .map_err(|error| error.to_string())? as u64;
        let next_generation = generation + 1;
        transaction.execute("UPDATE rx4_journal_conversations SET generation = ?, generation_base_turn_seq = ? WHERE conversation_id = ?", params![next_generation, high_water, conversation_id]).map_err(|error| error.to_string())?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(ResultPage {
            conversation_id,
            turn: None,
            turns: vec![],
            cleared_count,
            high_water_turn_seq: high_water,
            generation: next_generation,
            generation_base_turn_seq: high_water,
        })
    }

    pub fn repair(
        &mut self,
        surface: &Surface,
        turn_ids: &[String],
        active_run_ids: &[String],
    ) -> Result<ResultPage, String> {
        let mut unique_ids = Vec::new();
        for turn_id in turn_ids {
            let turn_id = turn_id.trim();
            if turn_id.is_empty() || unique_ids.iter().any(|existing| existing == turn_id) {
                continue;
            }
            unique_ids.push(turn_id.to_owned());
            if unique_ids.len() == 100 {
                break;
            }
        }
        let transaction = self
            .connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let mut repaired = Vec::new();
        let mut page_conversation_id = None;
        for turn_id in unique_ids {
            let Some((conversation_id, turn_surface, current)) =
                find_turn_by_id(&transaction, &turn_id)?
            else {
                continue;
            };
            if turn_surface.owner_id != surface.owner_id {
                return Err("Journal conversation is outside owner scope".into());
            }
            if current.role != "assistant" || terminal(&current.status) {
                continue;
            }
            if current
                .producing_run_id
                .as_ref()
                .is_some_and(|run_id| active_run_ids.iter().any(|active| active == run_id))
            {
                continue;
            }
            let mut patch = Map::new();
            patch.insert("status".into(), Value::String("failed".into()));
            let turn = mutate_turn(
                &transaction,
                &conversation_id,
                &turn_surface,
                current,
                &patch,
                None,
            )?;
            if page_conversation_id.is_none() {
                page_conversation_id = Some(conversation_id);
            }
            repaired.push(turn);
        }
        let conversation_id = match page_conversation_id {
            Some(conversation_id) => conversation_id,
            None => ensure_conversation(&transaction, surface)?,
        };
        let (generation, base, high_water) = state(&transaction, &conversation_id)?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(ResultPage {
            conversation_id,
            turn: repaired.first().cloned(),
            turns: repaired,
            cleared_count: 0,
            high_water_turn_seq: high_water,
            generation,
            generation_base_turn_seq: base,
        })
    }
}

#[derive(Clone)]
struct TurnRow {
    turn_id: String,
    turn_seq: u64,
    producer_id: String,
    payload_hash: String,
    role: String,
    content: String,
    origin: String,
    status: String,
    blocks: String,
    resources: String,
    producing_run_id: Option<String>,
    producing_attempt_id: Option<String>,
    metadata: String,
    created: u64,
    updated: u64,
    completed: Option<u64>,
}

fn ensure_conversation(connection: &Connection, surface: &Surface) -> Result<String, String> {
    let existing: Option<String> = connection.query_row(
        "SELECT conversation_id FROM rx4_journal_conversations WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?",
        params![surface.owner_id, surface.surface_kind, surface.external_ref_kind, surface.external_ref_id],
        |row| row.get(0),
    ).optional().map_err(|error| error.to_string())?;
    if let Some(conversation_id) = existing {
        return Ok(conversation_id);
    }
    let digest = Sha256::digest(format!(
        "{}:{}:{}:{}",
        surface.owner_id, surface.surface_kind, surface.external_ref_kind, surface.external_ref_id
    ));
    let conversation_id = format!("rx4-{:x}", digest);
    connection.execute(
        "INSERT INTO rx4_journal_conversations(owner_id, surface_kind, external_ref_kind, external_ref_id, conversation_id) VALUES (?, ?, ?, ?, ?)",
        params![surface.owner_id, surface.surface_kind, surface.external_ref_kind, surface.external_ref_id, conversation_id],
    ).map_err(|error| error.to_string())?;
    Ok(conversation_id)
}

fn state(connection: &Connection, conversation_id: &str) -> Result<(u64, u64, u64), String> {
    connection.query_row(
        "SELECT generation, generation_base_turn_seq, high_water_turn_seq FROM rx4_journal_conversations WHERE conversation_id = ?",
        params![conversation_id],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
    ).map_err(|error| error.to_string())
}

fn next_sequence(
    transaction: &Transaction<'_>,
    conversation_id: &str,
) -> Result<(u64, u64, u64), String> {
    transaction.execute(
        "UPDATE rx4_journal_conversations SET high_water_turn_seq = high_water_turn_seq + 1 WHERE conversation_id = ?",
        params![conversation_id],
    ).map_err(|error| error.to_string())?;
    state(transaction, conversation_id)
}

fn record_turn(
    transaction: &Transaction<'_>,
    conversation_id: &str,
    surface: &Surface,
    input: &Map<String, Value>,
) -> Result<Value, String> {
    reject_private_fields(input)?;
    let turn_id = required(input, "turnId")?;
    let role = required(input, "role")?;
    if role != "user" && role != "assistant" {
        return Err("journal role is invalid".into());
    }
    let content = optional(input, "content").ok_or_else(|| "content is required".to_owned())?;
    let origin = optional(input, "origin").unwrap_or_else(|| "local".into());
    let status = optional(input, "status").unwrap_or_else(|| "pending".into());
    valid_status(&status)?;
    if content.trim().is_empty() && (role != "assistant" || terminal(&status)) {
        return Err("content is required".into());
    }
    let blocks = json_array(input.get("contentBlocks"))?;
    let resources = json_array(input.get("resources"))?;
    let metadata = object_json(input.get("metadataJson"))?;
    let created = input
        .get("createdAtMs")
        .and_then(Value::as_u64)
        .unwrap_or_else(now_ms);
    let producer_id = optional(input, "producerId").unwrap_or_else(|| format!("turn:{turn_id}"));
    let existing = turn_row(transaction, conversation_id, &turn_id)?;
    if let Some(current) = existing {
        if current.producer_id != producer_id || current.role != role || current.content != content
        {
            return Err("journal record conflicts with existing turn".into());
        }
        return turn_value(
            conversation_id,
            surface,
            current,
            state(transaction, conversation_id)?,
        );
    }
    let (generation, base, sequence) = next_sequence(transaction, conversation_id)?;
    let payload_hash = payload_hash(
        &role, &content, &origin, &status, &blocks, &resources, &metadata,
    );
    let completed = if terminal(&status) {
        Some(created)
    } else {
        None
    };
    transaction.execute(
        "INSERT INTO rx4_journal_turns(conversation_id, turn_id, turn_seq, producer_id, payload_hash, role, surface_kind, external_ref_kind, external_ref_id, content, origin, status, content_blocks_json, resources_json, metadata_json, created_at_ms, updated_at_ms, completed_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        params![conversation_id, turn_id, sequence, producer_id, payload_hash, role, surface.surface_kind, surface.external_ref_kind, surface.external_ref_id, content, origin, status, blocks, resources, metadata, created, created, completed],
    ).map_err(|error| error.to_string())?;
    let row = turn_row(transaction, conversation_id, &turn_id)?
        .ok_or_else(|| "recorded journal turn missing".to_owned())?;
    turn_value(conversation_id, surface, row, (generation, base, sequence))
}

fn mutate_turn(
    transaction: &Transaction<'_>,
    conversation_id: &str,
    surface: &Surface,
    current: TurnRow,
    input: &Map<String, Value>,
    terminal_disposition: Option<&str>,
) -> Result<Value, String> {
    let status = optional(input, "status").unwrap_or_else(|| current.status.clone());
    valid_status(&status)?;
    let content = optional(input, "content").unwrap_or_else(|| current.content.clone());
    let blocks = merge_array(
        &current.blocks,
        input.get("replaceContentBlocks"),
        input.get("appendContentBlocks"),
    )?;
    let resources = merge_array(
        &current.resources,
        input.get("replaceResources"),
        input.get("appendResources"),
    )?;
    let metadata = if let Some(value) = input.get("metadataJson") {
        object_json(Some(value))?
    } else {
        current.metadata.clone()
    };
    let changed = status != current.status
        || content != current.content
        || blocks != current.blocks
        || resources != current.resources
        || metadata != current.metadata;
    if !changed {
        return turn_value(
            conversation_id,
            surface,
            current,
            state(transaction, conversation_id)?,
        );
    }
    let (generation, base, sequence) = next_sequence(transaction, conversation_id)?;
    let updated = now_ms();
    let completed = if terminal(&status) {
        Some(current.completed.unwrap_or(updated))
    } else {
        None
    };
    let payload_hash = payload_hash(
        &current.role,
        &content,
        &current.origin,
        &status,
        &blocks,
        &resources,
        &metadata,
    );
    transaction.execute(
        "UPDATE rx4_journal_turns SET turn_seq = ?, payload_hash = ?, content = ?, status = ?, content_blocks_json = ?, resources_json = ?, metadata_json = ?, updated_at_ms = ?, completed_at_ms = ? WHERE conversation_id = ? AND turn_id = ?",
        params![sequence, payload_hash, content, status, blocks, resources, metadata, updated, completed, conversation_id, current.turn_id],
    ).map_err(|error| error.to_string())?;
    let row = turn_row(transaction, conversation_id, &current.turn_id)?
        .ok_or_else(|| "updated journal turn missing".to_owned())?;
    let value = turn_value(conversation_id, surface, row, (generation, base, sequence))?;
    if terminal_disposition == Some("discard") {
        return Ok(value);
    }
    Ok(value)
}

fn turn_row(
    connection: &Connection,
    conversation_id: &str,
    turn_id: &str,
) -> Result<Option<TurnRow>, String> {
    connection.query_row(
        "SELECT turn_id, turn_seq, producer_id, payload_hash, role, content, origin, status, content_blocks_json, resources_json, producing_run_id, producing_attempt_id, metadata_json, created_at_ms, updated_at_ms, completed_at_ms FROM rx4_journal_turns WHERE conversation_id = ? AND turn_id = ?",
        params![conversation_id, turn_id],
        |row| Ok(TurnRow { turn_id: row.get(0)?, turn_seq: row.get(1)?, producer_id: row.get(2)?, payload_hash: row.get(3)?, role: row.get(4)?, content: row.get(5)?, origin: row.get(6)?, status: row.get(7)?, blocks: row.get(8)?, resources: row.get(9)?, producing_run_id: row.get(10)?, producing_attempt_id: row.get(11)?, metadata: row.get(12)?, created: row.get(13)?, updated: row.get(14)?, completed: row.get(15)? }),
    ).optional().map_err(|error| error.to_string())
}

fn find_turn_by_id(
    connection: &Connection,
    turn_id: &str,
) -> Result<Option<(String, Surface, TurnRow)>, String> {
    connection.query_row(
        "SELECT ct.conversation_id, sc.owner_id, ct.surface_kind, ct.external_ref_kind, ct.external_ref_id,
                ct.turn_id, ct.turn_seq, ct.producer_id, ct.payload_hash, ct.role, ct.content, ct.origin,
                ct.status, ct.content_blocks_json, ct.resources_json, ct.producing_run_id,
                ct.producing_attempt_id, ct.metadata_json, ct.created_at_ms, ct.updated_at_ms, ct.completed_at_ms
         FROM rx4_journal_turns ct
         JOIN rx4_journal_conversations sc ON sc.conversation_id = ct.conversation_id
         WHERE ct.turn_id = ?
         ORDER BY ct.created_at_ms ASC
         LIMIT 1",
        params![turn_id],
        |row| {
            Ok((
                row.get(0)?,
                Surface {
                    owner_id: row.get(1)?,
                    surface_kind: row.get(2)?,
                    external_ref_kind: row.get(3)?,
                    external_ref_id: row.get(4)?,
                },
                TurnRow {
                    turn_id: row.get(5)?,
                    turn_seq: row.get(6)?,
                    producer_id: row.get(7)?,
                    payload_hash: row.get(8)?,
                    role: row.get(9)?,
                    content: row.get(10)?,
                    origin: row.get(11)?,
                    status: row.get(12)?,
                    blocks: row.get(13)?,
                    resources: row.get(14)?,
                    producing_run_id: row.get(15)?,
                    producing_attempt_id: row.get(16)?,
                    metadata: row.get(17)?,
                    created: row.get(18)?,
                    updated: row.get(19)?,
                    completed: row.get(20)?,
                },
            ))
        },
    )
    .optional()
    .map_err(|error| error.to_string())
}

fn row_to_turn(row: &rusqlite::Row<'_>) -> rusqlite::Result<Value> {
    let surface = Surface {
        owner_id: String::new(),
        surface_kind: row.get(6)?,
        external_ref_kind: row.get(7)?,
        external_ref_id: row.get(8)?,
    };
    let turn = TurnRow {
        turn_id: row.get(1)?,
        turn_seq: row.get(2)?,
        producer_id: row.get(3)?,
        payload_hash: row.get(4)?,
        role: row.get(5)?,
        content: row.get(9)?,
        origin: row.get(10)?,
        status: row.get(11)?,
        blocks: row.get(12)?,
        resources: row.get(13)?,
        producing_run_id: row.get(14)?,
        producing_attempt_id: row.get(15)?,
        metadata: row.get(16)?,
        created: row.get(17)?,
        updated: row.get(18)?,
        completed: row.get(19)?,
    };
    let conversation_id: String = row.get(0)?;
    turn_value(&conversation_id, &surface, turn, (0, 0, 0))
        .map_err(|error| rusqlite::Error::ToSqlConversionFailure(error.into()))
}

fn turn_value(
    conversation_id: &str,
    surface: &Surface,
    turn: TurnRow,
    state: (u64, u64, u64),
) -> Result<Value, String> {
    let blocks: Value = serde_json::from_str(&turn.blocks)
        .map_err(|_| "journal content blocks are corrupt".to_owned())?;
    let resources: Value = serde_json::from_str(&turn.resources)
        .map_err(|_| "journal resources are corrupt".to_owned())?;
    Ok(
        json!({"conversationId": conversation_id, "turnId": turn.turn_id, "turnSeq": turn.turn_seq, "conversationGeneration": state.0, "generationBaseTurnSeq": state.1, "producerId": turn.producer_id, "payloadHash": turn.payload_hash, "role": turn.role, "surfaceKind": surface.surface_kind, "externalRefKind": surface.external_ref_kind, "externalRefId": surface.external_ref_id, "content": turn.content, "origin": turn.origin, "status": turn.status, "contentBlocks": blocks, "resources": resources, "producingRunId": turn.producing_run_id, "producingAttemptId": turn.producing_attempt_id, "metadataJson": turn.metadata, "createdAtMs": turn.created, "updatedAtMs": turn.updated, "completedAtMs": turn.completed}),
    )
}

fn apply_state(turn: &mut Value, generation: u64, generation_base_turn_seq: u64) {
    if let Some(object) = turn.as_object_mut() {
        object.insert("conversationGeneration".into(), json!(generation));
        object.insert(
            "generationBaseTurnSeq".into(),
            json!(generation_base_turn_seq),
        );
    }
}

fn required(input: &Map<String, Value>, key: &str) -> Result<String, String> {
    optional(input, key)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{key} is required"))
}
fn optional(input: &Map<String, Value>, key: &str) -> Option<String> {
    input
        .get(key)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}
fn reject_private_fields(input: &Map<String, Value>) -> Result<(), String> {
    if input.contains_key("producingRunId")
        || input.contains_key("producingAttemptId")
        || input.contains_key("delivery")
    {
        Err("public journal mutation cannot set runtime authority fields".into())
    } else {
        Ok(())
    }
}
fn valid_status(status: &str) -> Result<(), String> {
    if matches!(status, "pending" | "streaming" | "completed" | "failed") {
        Ok(())
    } else {
        Err("journal status is invalid".into())
    }
}
fn terminal(status: &str) -> bool {
    status == "completed" || status == "failed"
}
fn json_array(value: Option<&Value>) -> Result<String, String> {
    let value = value.cloned().unwrap_or_else(|| json!([]));
    if !value.is_array() {
        return Err("journal array field is invalid".into());
    }
    serde_json::to_string(&value).map_err(|error| error.to_string())
}
fn object_json(value: Option<&Value>) -> Result<String, String> {
    let value = value.cloned().unwrap_or_else(|| json!({}));
    let parsed = if let Some(string) = value.as_str() {
        serde_json::from_str::<Value>(string).map_err(|_| "metadataJson is invalid".to_owned())?
    } else {
        value
    };
    if !parsed.is_object() {
        return Err("metadataJson is invalid".into());
    }
    serde_json::to_string(&parsed).map_err(|error| error.to_string())
}
fn merge_array(
    current: &str,
    replacement: Option<&Value>,
    append: Option<&Value>,
) -> Result<String, String> {
    let mut values: Vec<Value> =
        serde_json::from_str(current).map_err(|_| "journal array is corrupt".to_owned())?;
    if let Some(replacement) = replacement {
        values = replacement
            .as_array()
            .cloned()
            .ok_or_else(|| "journal array field is invalid".to_owned())?;
    }
    if let Some(append) = append {
        values.extend(
            append
                .as_array()
                .cloned()
                .ok_or_else(|| "journal array field is invalid".to_owned())?,
        );
    }
    serde_json::to_string(&values).map_err(|error| error.to_string())
}
fn payload_hash(
    role: &str,
    content: &str,
    origin: &str,
    status: &str,
    blocks: &str,
    resources: &str,
    metadata: &str,
) -> String {
    format!(
        "sha256:{:x}",
        Sha256::digest(
            format!("{role}:{content}:{origin}:{status}:{blocks}:{resources}:{metadata}")
                .as_bytes()
        )
    )
}
fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis() as u64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn must<T>(value: Result<T, String>) -> T {
        match value {
            Ok(value) => value,
            Err(error) => panic!("journal setup failed: {error}"),
        }
    }

    #[test]
    fn initializes_idempotently_and_reopens_durable_turns() {
        let path = env::temp_dir().join(format!("omi-journal-{}.sqlite3", now_ms()));
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let turn = json!({"turnId":"turn-1","role":"user","content":"hello","status":"completed"});
        let input = match turn.as_object() {
            Some(input) => input,
            None => panic!("turn fixture must be an object"),
        };
        let mut store = must(JournalStore::open(path.clone()));
        let recorded = must(store.record(&surface, input));
        assert_eq!(recorded.high_water_turn_seq, 1);
        drop(store);
        let mut reopened = must(JournalStore::open(path.clone()));
        let listed = must(reopened.list(&surface, 0, 100));
        assert_eq!(listed.turns.len(), 1);
        assert_eq!(listed.turns[0]["content"], "hello");
        let _ = fs::remove_file(path);
    }

    #[test]
    fn imports_existing_node_journal_without_mutating_source_rows() {
        let connection = match Connection::open_in_memory() {
            Ok(connection) => connection,
            Err(error) => panic!("legacy journal setup failed: {error}"),
        };
        if let Err(error) = connection.execute_batch("CREATE TABLE surface_conversations(owner_id TEXT, surface_kind TEXT, external_ref_kind TEXT, external_ref_id TEXT, conversation_id TEXT); CREATE TABLE conversation_journal_state(conversation_id TEXT, generation INTEGER, generation_base_turn_seq INTEGER, high_water_turn_seq INTEGER); CREATE TABLE conversation_turns(conversation_id TEXT, turn_id TEXT, turn_seq INTEGER, producer_id TEXT, payload_hash TEXT, role TEXT, surface_kind TEXT, content TEXT, origin TEXT, status TEXT, content_blocks_json TEXT, resources_json TEXT, producing_run_id TEXT, producing_attempt_id TEXT, metadata_json TEXT, created_at_ms INTEGER, updated_at_ms INTEGER, completed_at_ms INTEGER); INSERT INTO surface_conversations VALUES ('owner', 'main_chat', 'chat', 'chat-1', 'legacy-conversation'); INSERT INTO conversation_journal_state VALUES ('legacy-conversation', 3, 7, 8); INSERT INTO conversation_turns VALUES ('legacy-conversation', 'legacy-turn', 8, 'turn:legacy-turn', 'hash', 'user', 'main_chat', 'hello', 'local', 'completed', '[]', '[]', NULL, NULL, '{}', 1, 1, 1);") { panic!("legacy journal setup failed: {error}"); }
        let mut store = must(JournalStore::from_connection(connection));
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let listed = must(store.list(&surface, 0, 100));
        assert_eq!(listed.conversation_id, "legacy-conversation");
        assert_eq!(listed.generation, 3);
        assert_eq!(listed.turns[0]["turnId"], "legacy-turn");
    }

    #[test]
    fn upgrades_existing_runtime_runs_with_conversation_identity() {
        let connection = match Connection::open_in_memory() {
            Ok(connection) => connection,
            Err(error) => panic!("runtime migration setup failed: {error}"),
        };
        if let Err(error) = connection.execute_batch(
            "CREATE TABLE rx4_runtime_runs (
                run_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL UNIQUE,
                owner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                profile_generation INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL
            );",
        ) {
            panic!("runtime migration setup failed: {error}");
        }
        let store = must(JournalStore::from_connection(connection));
        let has_conversation: bool = store
            .connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM pragma_table_info('rx4_runtime_runs') WHERE name = 'conversation_id')",
                [],
                |row| row.get(0),
            )
            .expect("runtime migration lookup must succeed");
        assert!(has_conversation);
    }

    #[test]
    fn prunes_only_expired_terminal_runtime_state() {
        let mut store = must(JournalStore::in_memory());
        store.connection.execute_batch(
            "INSERT INTO rx4_runtime_runs VALUES ('expired-run', 'expired-attempt', 'owner', 'session', NULL, 1, 1);
             INSERT INTO rx4_runtime_runs VALUES ('pending-run', 'pending-attempt', 'owner', 'session', NULL, 1, 1);
             INSERT INTO rx4_runtime_runs VALUES ('recent-run', 'recent-attempt', 'owner', 'session', NULL, 1, 1);
             INSERT INTO rx4_tool_claims VALUES ('expired-claim', 'owner', 'session', 'expired-run', 'expired-attempt', 1, 'boot', 1, 'search', 'hash', 'completed', 'succeeded', 'result', 1, 1);
             INSERT INTO rx4_tool_claims VALUES ('pending-claim', 'owner', 'session', 'pending-run', 'pending-attempt', 1, 'boot', 1, 'search', 'hash', 'pending', NULL, NULL, 1, 1);
             INSERT INTO rx4_tool_claims VALUES ('recent-claim', 'owner', 'session', 'recent-run', 'recent-attempt', 1, 'boot', 1, 'search', 'hash', 'revoked', NULL, NULL, 99, 99);",
        ).expect("runtime state setup must succeed");

        must(store.prune_terminal_runtime_state_before(10));

        assert!(store
            .pending_tool_claim("pending-claim")
            .expect("pending claim lookup must succeed")
            .is_some());
        assert!(store
            .completed_tool_claim("expired-claim")
            .expect("completed claim lookup must succeed")
            .is_none());
        let remaining_runs: i64 = store
            .connection
            .query_row("SELECT COUNT(*) FROM rx4_runtime_runs", [], |row| {
                row.get(0)
            })
            .expect("run count must succeed");
        assert_eq!(remaining_runs, 2);
        let remaining_claims: i64 = store
            .connection
            .query_row("SELECT COUNT(*) FROM rx4_tool_claims", [], |row| row.get(0))
            .expect("claim count must succeed");
        assert_eq!(remaining_claims, 2);
    }

    #[test]
    fn terminalization_binds_an_unowned_turn_to_its_durable_run() {
        let mut store = must(JournalStore::in_memory());
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let conversation_id = must(store.conversation_id(&surface));
        let run = must(store.admit_run("owner", "session", &conversation_id, 1));
        let record = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "role": "assistant",
            "content": "",
            "status": "streaming"
        }))
        .expect("record fixture must be valid");
        must(store.record(&surface, &record));
        let terminalization = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "producingRunId": run.run_id,
            "producingAttemptId": run.attempt_id,
            "disposition": "accept",
            "content": "done"
        }))
        .expect("terminalization fixture must be valid");
        let result = must(store.terminalize(&surface, &terminalization));
        let turn = result.turn.expect("terminalization must return the turn");
        assert_eq!(turn["status"], "completed");
        assert_eq!(turn["producingRunId"], terminalization["producingRunId"]);
        assert_eq!(
            turn["producingAttemptId"],
            terminalization["producingAttemptId"]
        );
    }

    #[test]
    fn public_update_cannot_terminalize_a_runtime_produced_turn() {
        let mut store = must(JournalStore::in_memory());
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let conversation_id = must(store.conversation_id(&surface));
        let run = must(store.admit_run("owner", "session", &conversation_id, 1));
        let record = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "role": "assistant",
            "content": "",
            "status": "streaming"
        }))
        .expect("record fixture must be valid");
        must(store.record(&surface, &record));
        let terminalization = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "producingRunId": run.run_id,
            "producingAttemptId": run.attempt_id,
            "disposition": "accept",
            "content": "done"
        }))
        .expect("terminalization fixture must be valid");
        must(store.terminalize(&surface, &terminalization));
        let update = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "status": "failed"
        }))
        .expect("update fixture must be valid");
        assert!(store.update(&surface, &update).is_err());
    }

    #[test]
    fn public_update_cannot_rewrite_a_runtime_produced_turn() {
        let mut store = must(JournalStore::in_memory());
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let conversation_id = must(store.conversation_id(&surface));
        let run = must(store.admit_run("owner", "session", &conversation_id, 1));
        let record = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "role": "assistant",
            "content": "",
            "status": "streaming"
        }))
        .expect("record fixture must be valid");
        must(store.record(&surface, &record));
        let terminalization = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "producingRunId": run.run_id,
            "producingAttemptId": run.attempt_id,
            "disposition": "accept",
            "content": "done"
        }))
        .expect("terminalization fixture must be valid");
        must(store.terminalize(&surface, &terminalization));
        let update = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "content": "rewritten",
            "appendContentBlocks": [{"type":"text","text":"rewritten"}]
        }))
        .expect("update fixture must be valid");
        assert!(store.update(&surface, &update).is_err());
    }

    #[test]
    fn tool_claim_requires_the_admitted_run_tuple() {
        let mut store = must(JournalStore::in_memory());
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let conversation_id = must(store.conversation_id(&surface));
        let run = must(store.admit_run("owner", "session", &conversation_id, 1));
        assert!(store
            .authorize_tool_claim(
                "claim",
                "owner",
                "session",
                &run.run_id,
                &run.attempt_id,
                1,
                "boot",
                1,
                "search",
                "hash",
            )
            .is_ok());
        assert!(store
            .authorize_tool_claim(
                "forged-claim",
                "other-owner",
                "session",
                &run.run_id,
                &run.attempt_id,
                1,
                "boot",
                1,
                "search",
                "hash",
            )
            .is_err());
    }

    #[test]
    fn revokes_pending_claims_for_a_session_after_its_run_completes() {
        let mut store = must(JournalStore::in_memory());
        let run = must(store.admit_run("owner", "session", "conversation", 1));
        must(store.authorize_tool_claim(
            "claim",
            "owner",
            "session",
            &run.run_id,
            &run.attempt_id,
            1,
            "boot",
            1,
            "search",
            "hash",
        ));

        assert_eq!(
            must(store.revoke_tool_claims_for_session("owner", "session")),
            1
        );
        assert!(must(store.pending_tool_claim("claim")).is_none());
    }

    #[test]
    fn repair_marks_orphaned_nonterminal_turns_failed_and_skips_active_runs() {
        let mut store = must(JournalStore::in_memory());
        let surface = Surface {
            owner_id: "owner".into(),
            surface_kind: "main_chat".into(),
            external_ref_kind: "chat".into(),
            external_ref_id: "chat-1".into(),
        };
        let conversation_id = must(store.conversation_id(&surface));
        let run = must(store.admit_run("owner", "session", &conversation_id, 1));
        let record = serde_json::from_value(json!({
            "turnId": "assistant-turn",
            "role": "assistant",
            "content": "partial",
            "status": "streaming"
        }))
        .expect("record fixture must be valid");
        must(store.record(&surface, &record));
        store
            .connection
            .execute(
                "UPDATE rx4_journal_turns SET producing_run_id = ?, producing_attempt_id = ? WHERE turn_id = ?",
                params![run.run_id, run.attempt_id, "assistant-turn"],
            )
            .expect("producing run binding must succeed");

        let skipped =
            must(store.repair(&surface, &["assistant-turn".into()], &[run.run_id.clone()]));
        assert!(skipped.turns.is_empty());

        let repaired = must(store.repair(&surface, &["assistant-turn".into()], &[]));
        assert_eq!(repaired.turns.len(), 1);
        assert_eq!(repaired.turns[0]["status"], "failed");
        assert_eq!(repaired.turns[0]["turnId"], "assistant-turn");
    }
}
