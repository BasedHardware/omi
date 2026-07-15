#!/usr/bin/env python3
"""Safely configure Smart Tasks and Chat-first UI for one approved dogfood account.

The default is a dry-run.  An apply is deliberately limited to the existing
canonical-memory dogfood UID, requires explicit UID/mode/generation
confirmations plus an exact Chat-first UI confirmation, and writes only that
user's task-intelligence control document.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from google.cloud import firestore
except ImportError:  # pragma: no cover - exercised when cloud dependencies are unavailable
    firestore = None

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.google_credentials import prepare_google_credentials
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
from utils.memory.memory_system import CANONICAL_MEMORY_USERS

TASK_INTELLIGENCE_DOGFOOD_UID = 'vi7SA9ckQCe4ccobWNxlbdcNdC23'
CONTROL_PATH_TEMPLATE = 'users/{uid}/task_intelligence_control/state'
DEFAULT_FIRESTORE_RPC_TIMEOUT_SECONDS = 20.0
GCLOUD_USER_CREDENTIAL_SOURCE = 'gcloud-user'
APPLICATION_DEFAULT_CREDENTIAL_SOURCE = 'application-default'


@dataclass(frozen=True)
class ActivationPlan:
    uid: str
    document_path: str
    current_control: dict[str, Any]
    target_control: dict[str, Any]
    canonical_memory_whitelisted: bool


@dataclass(frozen=True)
class FirestoreControlSnapshot:
    control: TaskWorkflowControl
    exists: bool
    update_time: str | None


class FirestoreRestError(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__(f'Firestore REST request failed with status {status_code}')
        self.status_code = status_code


def control_path(uid: str) -> str:
    return CONTROL_PATH_TEMPLATE.format(uid=uid)


def require_dogfood_uid(uid: str) -> None:
    if uid != TASK_INTELLIGENCE_DOGFOOD_UID:
        raise ValueError('this operator tool is restricted to the approved Smart Tasks dogfood UID')
    if uid not in CANONICAL_MEMORY_USERS:
        raise RuntimeError('approved Smart Tasks dogfood UID is not in the canonical-memory code whitelist')


def _snapshot_control(snapshot: Any) -> TaskWorkflowControl:
    if snapshot is None or getattr(snapshot, 'exists', False) is False:
        return TaskWorkflowControl()
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        raise RuntimeError('task-intelligence control document must be an object')
    return TaskWorkflowControl.model_validate(payload)


def read_control(
    db_client: Any,
    *,
    uid: str,
    rpc_timeout_seconds: float = DEFAULT_FIRESTORE_RPC_TIMEOUT_SECONDS,
) -> TaskWorkflowControl:
    require_dogfood_uid(uid)
    return _snapshot_control(db_client.document(control_path(uid)).get(timeout=rpc_timeout_seconds))


def _gcloud_user_access_token(*, rpc_timeout_seconds: float) -> str:
    try:
        result = subprocess.run(
            ['gcloud', 'auth', 'print-access-token'],
            check=True,
            capture_output=True,
            text=True,
            timeout=rpc_timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError('unable to obtain a gcloud user access token') from exc
    token = result.stdout.strip()
    if not token:
        raise RuntimeError('gcloud returned an empty user access token')
    return token


def _firestore_rest_url(*, firestore_project: str, uid: str) -> str:
    return (
        f'https://firestore.googleapis.com/v1/projects/{firestore_project}/databases/(default)/documents/'
        f'{control_path(uid)}'
    )


def _firestore_rest_request(
    *,
    method: str,
    url: str,
    access_token: str,
    rpc_timeout_seconds: float,
    payload: dict[str, Any] | None = None,
    http_open=None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
    )
    try:
        with (http_open or urlopen)(request, timeout=rpc_timeout_seconds) as response:
            raw = response.read()
    except HTTPError as exc:
        raise FirestoreRestError(exc.code) from exc
    except URLError as exc:
        raise RuntimeError('Firestore REST transport failed') from exc
    if not raw:
        return {}
    decoded = json.loads(raw.decode('utf-8'))
    if not isinstance(decoded, dict):
        raise RuntimeError('Firestore REST response must be an object')
    return decoded


def _firestore_value(value: object) -> object:
    if not isinstance(value, dict) or len(value) != 1:
        raise RuntimeError('Firestore control field is malformed')
    kind, raw = next(iter(value.items()))
    if kind == 'stringValue' and isinstance(raw, str):
        return raw
    if kind == 'integerValue' and isinstance(raw, str) and raw.isdigit():
        return int(raw)
    if kind == 'booleanValue' and isinstance(raw, bool):
        return raw
    raise RuntimeError('Firestore control field has an unsupported type')


def _control_snapshot_from_firestore_document(payload: dict[str, Any]) -> FirestoreControlSnapshot:
    fields = payload.get('fields')
    update_time = payload.get('updateTime')
    if not isinstance(fields, dict) or not isinstance(update_time, str) or not update_time:
        raise RuntimeError('Firestore control document is malformed')
    return FirestoreControlSnapshot(
        control=TaskWorkflowControl.model_validate({key: _firestore_value(value) for key, value in fields.items()}),
        exists=True,
        update_time=update_time,
    )


def read_control_with_gcloud_user_token(
    *,
    firestore_project: str,
    uid: str,
    rpc_timeout_seconds: float,
    http_open=None,
    access_token: str | None = None,
) -> FirestoreControlSnapshot:
    require_dogfood_uid(uid)
    token = access_token or _gcloud_user_access_token(rpc_timeout_seconds=rpc_timeout_seconds)
    try:
        payload = _firestore_rest_request(
            method='GET',
            url=_firestore_rest_url(firestore_project=firestore_project, uid=uid),
            access_token=token,
            rpc_timeout_seconds=rpc_timeout_seconds,
            http_open=http_open,
        )
    except FirestoreRestError as exc:
        if exc.status_code == 404:
            return FirestoreControlSnapshot(control=TaskWorkflowControl(), exists=False, update_time=None)
        raise
    return _control_snapshot_from_firestore_document(payload)


def build_activation_plan(
    uid: str,
    current: TaskWorkflowControl,
    *,
    chat_first_ui_enabled: bool | None = None,
) -> ActivationPlan:
    require_dogfood_uid(uid)
    target = TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.read,
        account_generation=current.account_generation,
        chat_first_ui_enabled=(
            current.chat_first_ui_enabled if chat_first_ui_enabled is None else chat_first_ui_enabled
        ),
    )
    return ActivationPlan(
        uid=uid,
        document_path=control_path(uid),
        current_control=current.persisted_payload(),
        target_control=target.persisted_payload(),
        canonical_memory_whitelisted=True,
    )


def apply_activation(
    db_client: Any,
    *,
    uid: str,
    expected_account_generation: int,
    chat_first_ui_enabled: bool,
    rpc_timeout_seconds: float = DEFAULT_FIRESTORE_RPC_TIMEOUT_SECONDS,
) -> bool:
    """Write the `read` control only if the observed generation remains current.

    The transaction retries on concurrent Firestore changes.  It never changes
    the account generation: an existing generation is preserved and a missing
    control document is explicitly initialized at the valid default of zero.
    """

    require_dogfood_uid(uid)
    if expected_account_generation < 0:
        raise ValueError('expected account generation must be nonnegative')
    if firestore is None:
        raise RuntimeError('google-cloud-firestore is required to apply Smart Tasks activation')

    ref = db_client.document(control_path(uid))

    @firestore.transactional
    def activate(transaction) -> bool:
        current = _snapshot_control(ref.get(transaction=transaction, timeout=rpc_timeout_seconds))
        if current.account_generation != expected_account_generation:
            raise RuntimeError(
                'refusing activation because account generation changed: '
                f'expected {expected_account_generation}, found {current.account_generation}'
            )
        target = TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.read,
            account_generation=current.account_generation,
            chat_first_ui_enabled=chat_first_ui_enabled,
        )
        if current == target:
            return False
        transaction.set(ref, target.persisted_payload())
        return True

    return activate(db_client.transaction())


def _firestore_control_fields(control: TaskWorkflowControl) -> dict[str, dict[str, str | bool]]:
    return {
        'workflow_mode': {'stringValue': control.workflow_mode.value},
        'account_generation': {'integerValue': str(control.account_generation)},
        'chat_first_ui_enabled': {'booleanValue': control.chat_first_ui_enabled},
    }


def apply_activation_with_gcloud_user_token(
    *,
    firestore_project: str,
    uid: str,
    expected_account_generation: int,
    chat_first_ui_enabled: bool,
    current: FirestoreControlSnapshot,
    rpc_timeout_seconds: float,
    http_open=None,
    access_token: str | None = None,
) -> bool:
    require_dogfood_uid(uid)
    if current.control.account_generation != expected_account_generation:
        raise RuntimeError(
            'refusing activation because account generation changed: '
            f'expected {expected_account_generation}, found {current.control.account_generation}'
        )
    target = TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.read,
        account_generation=current.control.account_generation,
        chat_first_ui_enabled=chat_first_ui_enabled,
    )
    if current.control == target:
        return False

    token = access_token or _gcloud_user_access_token(rpc_timeout_seconds=rpc_timeout_seconds)
    precondition = (
        {'currentDocument.updateTime': current.update_time}
        if current.exists and current.update_time
        else {'currentDocument.exists': 'false'}
    )
    query = urlencode(
        {
            **precondition,
            'updateMask.fieldPaths': ['workflow_mode', 'account_generation', 'chat_first_ui_enabled'],
        },
        doseq=True,
    )
    _firestore_rest_request(
        method='PATCH',
        url=f'{_firestore_rest_url(firestore_project=firestore_project, uid=uid)}?{query}',
        access_token=token,
        rpc_timeout_seconds=rpc_timeout_seconds,
        payload={
            'name': f'projects/{firestore_project}/databases/(default)/documents/{control_path(uid)}',
            'fields': _firestore_control_fields(target),
        },
        http_open=http_open,
    )
    return True


def _load_firestore_client(*, firestore_project: str):
    if firestore is None:
        raise RuntimeError('google-cloud-firestore is required to inspect or apply Smart Tasks activation')
    prepare_google_credentials()
    return firestore.Client(project=firestore_project)


def build_report(
    *,
    plan: ActivationPlan,
    firestore_project: str | None,
    credential_source: str,
    applied: bool | None,
    verified_control: TaskWorkflowControl | None,
) -> dict[str, Any]:
    return {
        'artifact': 'task_intelligence_dogfood_activation',
        'dry_run': applied is None,
        'firestore_project': firestore_project,
        'credential_source': credential_source,
        'plan': asdict(plan),
        'applied': applied,
        'verified_control': verified_control.persisted_payload() if verified_control is not None else None,
        'operator_notes': [
            'This tool is restricted to the one approved Smart Tasks dogfood UID.',
            'It writes only users/{uid}/task_intelligence_control/state when --apply is supplied.',
            'It does not change the canonical-memory cohort, runtime environment, or any other user.',
            'The transaction preserves account_generation and rejects a stale expected generation.',
            'The Chat-first UI flag is an explicit per-user input and must be confirmed exactly on apply.',
            'The gcloud-user source obtains a short-lived token without including it in output or reports.',
        ],
    }


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == 'true':
        return True
    if normalized == 'false':
        return False
    raise argparse.ArgumentTypeError('must be true or false')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Dry-run/apply Smart Tasks read mode and Chat-first UI for the approved dogfood UID.'
    )
    parser.add_argument('--uid', default=TASK_INTELLIGENCE_DOGFOOD_UID)
    parser.add_argument('--firestore-project', help='Required for --inspect-existing or --apply.')
    parser.add_argument(
        '--credential-source',
        choices=(APPLICATION_DEFAULT_CREDENTIAL_SOURCE, GCLOUD_USER_CREDENTIAL_SOURCE),
        default=APPLICATION_DEFAULT_CREDENTIAL_SOURCE,
        help='Use application-default credentials or an explicit gcloud user token.',
    )
    parser.add_argument('--inspect-existing', action='store_true', help='Read the existing control document.')
    parser.add_argument('--expected-account-generation', type=int)
    parser.add_argument(
        '--rpc-timeout-seconds',
        type=float,
        default=DEFAULT_FIRESTORE_RPC_TIMEOUT_SECONDS,
        help='Bound each Firestore RPC; defaults to 20 seconds.',
    )
    parser.add_argument('--apply', action='store_true', help='Write the explicit read-mode control document.')
    parser.add_argument('--confirm-uid', help='Required with --apply; must exactly match --uid.')
    parser.add_argument(
        '--confirm-workflow-mode',
        help='Required with --apply; must exactly equal read.',
    )
    parser.add_argument(
        '--chat-first-ui-enabled',
        type=parse_bool,
        help='Requested per-user Chat-first UI flag; required with --apply and accepted as true or false.',
    )
    parser.add_argument(
        '--confirm-chat-first-ui-enabled',
        type=parse_bool,
        help='Required with --apply; must exactly match --chat-first-ui-enabled.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_dogfood_uid(args.uid)
    if args.expected_account_generation is not None and args.expected_account_generation < 0:
        raise SystemExit('--expected-account-generation must be nonnegative')
    if args.rpc_timeout_seconds <= 0:
        raise SystemExit('--rpc-timeout-seconds must be positive')
    if args.apply:
        if args.confirm_uid != args.uid:
            raise SystemExit('--confirm-uid must exactly match --uid when --apply is used')
        if args.confirm_workflow_mode != TaskWorkflowMode.read.value:
            raise SystemExit('--confirm-workflow-mode must exactly equal read when --apply is used')
        if args.expected_account_generation is None:
            raise SystemExit('--expected-account-generation is required when --apply is used')
        if args.chat_first_ui_enabled is None:
            raise SystemExit('--chat-first-ui-enabled is required when --apply is used')
        if args.confirm_chat_first_ui_enabled != args.chat_first_ui_enabled:
            raise SystemExit(
                '--confirm-chat-first-ui-enabled must exactly match --chat-first-ui-enabled when --apply is used'
            )
    if (args.inspect_existing or args.apply) and not args.firestore_project:
        raise SystemExit('--firestore-project is required for inspection or apply')

    current = TaskWorkflowControl()
    current_snapshot = None
    db_client = None
    if args.inspect_existing or args.apply:
        if args.credential_source == GCLOUD_USER_CREDENTIAL_SOURCE:
            current_snapshot = read_control_with_gcloud_user_token(
                firestore_project=args.firestore_project,
                uid=args.uid,
                rpc_timeout_seconds=args.rpc_timeout_seconds,
            )
            current = current_snapshot.control
        else:
            db_client = _load_firestore_client(firestore_project=args.firestore_project)
            current = read_control(db_client, uid=args.uid, rpc_timeout_seconds=args.rpc_timeout_seconds)
    if args.expected_account_generation is not None and current.account_generation != args.expected_account_generation:
        raise SystemExit(
            'expected account generation does not match inspected control: '
            f'expected {args.expected_account_generation}, found {current.account_generation}'
        )

    plan = build_activation_plan(args.uid, current, chat_first_ui_enabled=args.chat_first_ui_enabled)
    applied = None
    verified_control = None
    if args.apply:
        if args.credential_source == GCLOUD_USER_CREDENTIAL_SOURCE:
            if current_snapshot is None:
                raise RuntimeError('gcloud-user activation requires an inspected control snapshot')
            applied = apply_activation_with_gcloud_user_token(
                firestore_project=args.firestore_project,
                uid=args.uid,
                expected_account_generation=args.expected_account_generation,
                chat_first_ui_enabled=args.chat_first_ui_enabled,
                current=current_snapshot,
                rpc_timeout_seconds=args.rpc_timeout_seconds,
            )
            verified_control = read_control_with_gcloud_user_token(
                firestore_project=args.firestore_project,
                uid=args.uid,
                rpc_timeout_seconds=args.rpc_timeout_seconds,
            ).control
        else:
            applied = apply_activation(
                db_client,
                uid=args.uid,
                expected_account_generation=args.expected_account_generation,
                chat_first_ui_enabled=args.chat_first_ui_enabled,
                rpc_timeout_seconds=args.rpc_timeout_seconds,
            )
            verified_control = read_control(
                db_client,
                uid=args.uid,
                rpc_timeout_seconds=args.rpc_timeout_seconds,
            )
        if verified_control != TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.read,
            account_generation=current.account_generation,
            chat_first_ui_enabled=args.chat_first_ui_enabled,
        ):
            raise RuntimeError('post-apply control verification did not match the requested control')
    print(
        json.dumps(
            build_report(
                plan=plan,
                firestore_project=args.firestore_project,
                credential_source=args.credential_source,
                applied=applied,
                verified_control=verified_control,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
