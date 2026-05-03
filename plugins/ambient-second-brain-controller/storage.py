import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from models import CaptureSettings

DEFAULT_DB_PATH = Path(__file__).with_name("ambient_second_brain.sqlite3")
DATABASE_URL = os.getenv("DATABASE_URL") or str(DEFAULT_DB_PATH)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_list(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _db_path() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.removeprefix("sqlite:///")
    return DATABASE_URL


@contextmanager
def connect():
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                omi_user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                omi_user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                device_label TEXT NOT NULL,
                app_install_id TEXT NOT NULL,
                client_public_key TEXT,
                device_token TEXT NOT NULL,
                policy_sequence INTEGER NOT NULL DEFAULT 0,
                revoked INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (omi_user_id, device_id)
            );
            CREATE TABLE IF NOT EXISTS settings (
                omi_user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plugin_authorizations (
                omi_user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                PRIMARY KEY (omi_user_id, device_id)
            );
            CREATE TABLE IF NOT EXISTS capture_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                signature TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                valid_until TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS capture_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                capture_state TEXT,
                health_state TEXT,
                foreground_app TEXT,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS capture_audio_spools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                duration_estimate REAL NOT NULL,
                sample_rate INTEGER NOT NULL,
                channels INTEGER NOT NULL,
                codec TEXT NOT NULL,
                status TEXT NOT NULL,
                omi_conversation_id TEXT,
                metadata TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                imported_at TEXT
            );
            CREATE TABLE IF NOT EXISTS fallback_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL,
                confidence REAL,
                health_state TEXT NOT NULL,
                raw_audio_available INTEGER NOT NULL,
                foreground_app TEXT,
                metadata TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                queued_for_omi INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS extracted_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                source_conversation_id TEXT,
                source_segment_ids TEXT NOT NULL,
                due_at TEXT,
                owner TEXT NOT NULL,
                confidence REAL NOT NULL,
                destination TEXT NOT NULL,
                requires_confirmation INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accountability_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                cadence TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT,
                device_id TEXT,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS integration_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omi_user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                account_label TEXT,
                encrypted_credentials TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)


def row_to_dict(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def ensure_user(omi_user_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (omi_user_id, created_at) VALUES (?, ?)",
            (omi_user_id, now_iso()),
        )


def get_settings(omi_user_id: str) -> CaptureSettings:
    ensure_user(omi_user_id)
    with connect() as conn:
        row = conn.execute("SELECT data FROM settings WHERE omi_user_id = ?", (omi_user_id,)).fetchone()
    if not row:
        settings = CaptureSettings()
        save_settings(omi_user_id, settings.model_dump(mode="json"))
        return settings
    return CaptureSettings.model_validate(json.loads(row["data"]))


def has_settings(omi_user_id: str) -> bool:
    ensure_user(omi_user_id)
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM settings WHERE omi_user_id = ?", (omi_user_id,)).fetchone()
    return row is not None


def default_capture_settings_from_env() -> CaptureSettings:
    base = CaptureSettings().model_dump(mode="json")
    base.update(
        {
            "advanced_capture_enabled": env_bool("AMBIENT_DEFAULT_CAPTURE_ENABLED", True),
            "default_capture_mode": os.getenv("AMBIENT_DEFAULT_CAPTURE_MODE", "normal"),
            "sensitivity": os.getenv("AMBIENT_DEFAULT_SENSITIVITY", "medium"),
            "silence_detection_seconds": env_int("AMBIENT_DEFAULT_SILENCE_SECONDS", 12),
            "rms_silence_dbfs_threshold": env_float("AMBIENT_DEFAULT_RMS_DBFS_THRESHOLD", -75),
            "zero_frame_threshold": env_float("AMBIENT_DEFAULT_ZERO_FRAME_THRESHOLD", 0.98),
            "allow_accessibility_mode": env_bool("AMBIENT_DEFAULT_ACCESSIBILITY_MODE", True),
            "allow_local_stt_fallback": env_bool("AMBIENT_DEFAULT_LOCAL_STT_FALLBACK", True),
            "allow_caption_fallback": env_bool("AMBIENT_DEFAULT_CAPTION_FALLBACK", True),
            "allow_audio_upload": env_bool("AMBIENT_DEFAULT_AUDIO_UPLOAD", True),
            "allow_transcript_upload": env_bool("AMBIENT_DEFAULT_TRANSCRIPT_UPLOAD", True),
            "raw_audio_retention": os.getenv("AMBIENT_DEFAULT_RAW_AUDIO_RETENTION", "until_synced"),
            "communication_mode": os.getenv("AMBIENT_DEFAULT_COMMUNICATION_MODE", "detect_and_caption_fallback"),
            "high_risk_apps": env_list(
                "AMBIENT_DEFAULT_HIGH_RISK_APPS",
                [
                    "com.microsoft.teams",
                    "us.zoom.videomeetings",
                    "com.google.android.apps.meetings",
                    "com.Slack",
                    "com.google.android.dialer",
                    "com.samsung.android.dialer",
                ],
            ),
            "notification_aggressiveness": os.getenv("AMBIENT_DEFAULT_NOTIFICATION_AGGRESSIVENESS", "normal"),
            "audit_level": os.getenv("AMBIENT_DEFAULT_AUDIT_LEVEL", "basic"),
        }
    )
    return CaptureSettings.model_validate(base)


def ensure_default_settings_for_registration(omi_user_id: str) -> CaptureSettings:
    if has_settings(omi_user_id):
        return get_settings(omi_user_id)
    settings = default_capture_settings_from_env()
    save_settings(omi_user_id, settings.model_dump(mode="json"))
    audit(omi_user_id, None, "default_settings_created_on_registration", settings.model_dump(mode="json"))
    return settings


def save_settings(omi_user_id: str, data: Dict[str, Any]) -> CaptureSettings:
    settings = CaptureSettings.model_validate(data)
    ensure_user(omi_user_id)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (omi_user_id, data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(omi_user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
            """,
            (omi_user_id, settings.model_dump_json(), now_iso()),
        )
    audit(omi_user_id, None, "settings_updated", settings.model_dump(mode="json"))
    return settings


def register_device(data: Dict[str, Any]) -> str:
    ensure_user(data["omi_user_id"])
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO devices (
                omi_user_id, device_id, device_label, app_install_id, client_public_key,
                device_token, revoked, created_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(omi_user_id, device_id) DO UPDATE SET
                device_label = excluded.device_label,
                app_install_id = excluded.app_install_id,
                client_public_key = excluded.client_public_key,
                device_token = excluded.device_token,
                revoked = 0,
                last_seen_at = excluded.last_seen_at
            """,
            (
                data["omi_user_id"],
                data["device_id"],
                data["device_label"],
                data["app_install_id"],
                data.get("client_public_key"),
                token,
                now_iso(),
                now_iso(),
            ),
        )
        conn.execute(
            """
            INSERT INTO plugin_authorizations (omi_user_id, device_id, active, created_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(omi_user_id, device_id) DO UPDATE SET active = 1, revoked_at = NULL
            """,
            (data["omi_user_id"], data["device_id"], now_iso()),
        )
    audit(data["omi_user_id"], data["device_id"], "device_registered", {"label": data["device_label"]})
    return token


def get_device(omi_user_id: str, device_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM devices WHERE omi_user_id = ? AND device_id = ?",
                (omi_user_id, device_id),
            ).fetchone()
        )


def revoke_device(omi_user_id: str, device_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE devices SET revoked = 1 WHERE omi_user_id = ? AND device_id = ?",
            (omi_user_id, device_id),
        )
        conn.execute(
            """
            UPDATE plugin_authorizations SET active = 0, revoked_at = ?
            WHERE omi_user_id = ? AND device_id = ?
            """,
            (now_iso(), omi_user_id, device_id),
        )
    audit(omi_user_id, device_id, "device_revoked", {})
    return cur.rowcount > 0


def next_policy_sequence(omi_user_id: str, device_id: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT policy_sequence FROM devices WHERE omi_user_id = ? AND device_id = ?",
            (omi_user_id, device_id),
        ).fetchone()
        sequence = int(row["policy_sequence"]) + 1
        conn.execute(
            "UPDATE devices SET policy_sequence = ?, last_seen_at = ? WHERE omi_user_id = ? AND device_id = ?",
            (sequence, now_iso(), omi_user_id, device_id),
        )
        return sequence


def store_policy(omi_user_id: str, device_id: str, sequence: int, payload: Dict[str, Any], signature: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO capture_policies (
                omi_user_id, device_id, sequence, payload_json, signature, issued_at, valid_until
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                omi_user_id,
                device_id,
                sequence,
                json.dumps(payload, sort_keys=True),
                signature,
                payload["issued_at"],
                payload["valid_until"],
            ),
        )
    audit(omi_user_id, device_id, "policy_issued", {"sequence": sequence, "capture_mode": payload["capture_mode"]})


def store_telemetry(event: Dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO capture_telemetry (
                omi_user_id, device_id, event_type, event_timestamp, capture_state,
                health_state, foreground_app, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["omi_user_id"],
                event["device_id"],
                event["event_type"],
                event["timestamp"],
                event.get("capture_state"),
                event.get("health_state"),
                event.get("foreground_app"),
                json.dumps(event.get("metadata", {}), sort_keys=True),
                now_iso(),
            ),
        )


def store_fallback_segment(segment: Dict[str, Any]) -> bool:
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO fallback_segments (
                    omi_user_id, device_id, session_id, text, source, start, end, confidence,
                    health_state, raw_audio_available, foreground_app, metadata, dedupe_key, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment["omi_user_id"],
                    segment["device_id"],
                    segment["session_id"],
                    segment["text"],
                    segment["source"],
                    segment["start"],
                    segment["end"],
                    segment.get("confidence"),
                    segment["health_state"],
                    int(segment["raw_audio_available"]),
                    segment.get("foreground_app"),
                    json.dumps(segment["metadata"], sort_keys=True),
                    segment["dedupe_key"],
                    now_iso(),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def store_audio_spool(spool: Dict[str, Any]) -> bool:
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO capture_audio_spools (
                    omi_user_id, device_id, session_id, filename, file_path, bytes, duration_estimate,
                    sample_rate, channels, codec, status, omi_conversation_id, metadata, dedupe_key,
                    created_at, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spool["omi_user_id"],
                    spool["device_id"],
                    spool["session_id"],
                    spool["filename"],
                    spool["file_path"],
                    spool["bytes"],
                    spool["duration_estimate"],
                    spool["sample_rate"],
                    spool["channels"],
                    spool["codec"],
                    spool["status"],
                    spool.get("omi_conversation_id"),
                    json.dumps(spool.get("metadata", {}), sort_keys=True),
                    spool["dedupe_key"],
                    now_iso(),
                    spool.get("imported_at"),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def mark_segments_queued(ids: Iterable[int]) -> None:
    ids = list(ids)
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        conn.execute(f"UPDATE fallback_segments SET queued_for_omi = 1 WHERE id IN ({placeholders})", ids)


def store_task(omi_user_id: str, task: Dict[str, Any]) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO extracted_tasks (
                omi_user_id, title, description, source_conversation_id, source_segment_ids,
                due_at, owner, confidence, destination, requires_confirmation, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                omi_user_id,
                task["title"],
                task.get("description", ""),
                task.get("source_conversation_id"),
                json.dumps(task.get("source_segment_ids", [])),
                task.get("due_at"),
                task.get("owner", "unknown"),
                task.get("confidence", 0.0),
                task.get("destination", "none"),
                int(task.get("requires_confirmation", True)),
                now_iso(),
            ),
        )
        return int(cur.lastrowid)


def create_rule(omi_user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO accountability_rules (omi_user_id, name, prompt, cadence, enabled, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                omi_user_id,
                data["name"],
                data["prompt"],
                data.get("cadence", "daily"),
                int(data.get("enabled", True)),
                json.dumps(data.get("metadata", {}), sort_keys=True),
                now_iso(),
                now_iso(),
            ),
        )
        rule_id = int(cur.lastrowid)
    audit(omi_user_id, None, "accountability_rule_created", {"rule_id": rule_id})
    return get_rule(rule_id)


def get_rule(rule_id: int) -> Dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM accountability_rules WHERE id = ?", (rule_id,)).fetchone()
    rule = dict(row)
    rule["metadata"] = json.loads(rule["metadata"])
    rule["enabled"] = bool(rule["enabled"])
    return rule


def list_rules(omi_user_id: str) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM accountability_rules WHERE omi_user_id = ? ORDER BY id DESC",
            (omi_user_id,),
        ).fetchall()
    rules = []
    for row in rows:
        rule = dict(row)
        rule["metadata"] = json.loads(rule["metadata"])
        rule["enabled"] = bool(rule["enabled"])
        rules.append(rule)
    return rules


def update_rule(rule_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = get_rule(rule_id)
    merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
    with connect() as conn:
        conn.execute(
            """
            UPDATE accountability_rules
            SET name = ?, prompt = ?, cadence = ?, enabled = ?, metadata = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["name"],
                merged["prompt"],
                merged["cadence"],
                int(merged["enabled"]),
                json.dumps(merged.get("metadata", {}), sort_keys=True),
                now_iso(),
                rule_id,
            ),
        )
    audit(existing["omi_user_id"], None, "accountability_rule_updated", {"rule_id": rule_id})
    return get_rule(rule_id)


def delete_rule(rule_id: int) -> bool:
    existing = get_rule(rule_id)
    with connect() as conn:
        cur = conn.execute("DELETE FROM accountability_rules WHERE id = ?", (rule_id,))
    audit(existing["omi_user_id"], None, "accountability_rule_deleted", {"rule_id": rule_id})
    return cur.rowcount > 0


def audit(omi_user_id: Optional[str], device_id: Optional[str], event_type: str, details: Dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (omi_user_id, device_id, event_type, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (omi_user_id, device_id, event_type, json.dumps(details, sort_keys=True), now_iso()),
        )


def get_audit_log(omi_user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM audit_log
            WHERE omi_user_id = ? OR omi_user_id IS NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (omi_user_id, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["details"] = json.loads(item["details"])
        result.append(item)
    return result
