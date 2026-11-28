"""``transcription-credit`` commands: grant, revoke and inspect support transcription credit.

A grant gives one account extra managed transcription seconds, spent only after
the plan's monthly allowance runs out, live and batch alike, until it expires
(default 30 days, at most 90). It is the only writer of
``users/{uid}.support_transcription_credit``; admission reads it in
``utils.subscription.resolve_transcription_allowance`` and the batch hold
controller re-offers cap-held work at the owner's next check (about 5
minutes) because a grant changes the owner's entitlement generation. This
command never touches held jobs or controller state itself.

Usage is metered after admission, so releasing held batch work is
all-or-nothing per owner: a grant smaller than the parked audio would still
release all of it. ``grant`` therefore refuses unless the grant covers the
parked seconds, or ``--allow-partial`` says the overrun is accepted.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath

from config.support_credit import DEFAULT_EXPIRES_DAYS, FIELD, MAX_EXPIRES_DAYS, enabled
from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.support_actions import ActionContext, ActionRecord, digest
from utils import support_credit

DEFAULT_NAMESPACE = 'batch_pipeline_prod'
_HELD_PAGE = 100
# An operator read of one owner's parked units; far above any real backlog.
_HELD_SCAN_LIMIT = 20000


class CreditCommandError(RuntimeError):
    pass


def _firestore_client() -> Any:
    return account_deletion_firestore_client()


def _now() -> float:
    return time.time()


def _allowance(uid: str, raw: Any, now: float) -> dict[str, Any]:
    """The plan allowance and the credit balance as admission would compute them."""
    from utils import subscription as subscription_utils

    plan = subscription_utils.users_db.get_user_valid_subscription(uid, provision=False)
    if not plan:
        return {'plan': None, 'allowance_seconds': 0, 'used_seconds': None, 'credit_usable_seconds': 0}
    allowance = subscription_utils.transcription_allowance_seconds(plan.plan)
    usage = subscription_utils.get_monthly_usage_for_subscription(uid)
    used = support_credit.usage_seconds(usage)
    grants = support_credit.parse_grants(raw)
    usable = 0
    if grants and allowance is not None and used is not None:
        remaining = support_credit.remaining_by_grant(
            grants,
            now=now,
            current_used=used,
            current_allowance=allowance,
            month_used=lambda month: support_credit.past_month_used(uid, month),
        )
        usable = support_credit.usable_seconds(grants, remaining, now)
    return {
        'plan': getattr(plan.plan, 'value', plan.plan),
        'allowance_seconds': allowance,
        'used_seconds': used,
        'credit_usable_seconds': usable,
    }


def _held(client: Any, uid: str, namespace: str) -> dict[str, Any]:
    """Parked (``allowance_held``) units for this owner and their audio seconds. Read only.

    Pages the hold controller's own ``allowance_page`` query, then point-reads
    each unit's duration. The store refuses a namespace that does not match
    ``OMI_ENV_STAGE``, so run it with ``OMI_ENV_STAGE=prod`` against production.
    """
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if namespace != f'batch_pipeline_{stage}':
        raise CreditCommandError(
            f'reading {namespace} needs OMI_ENV_STAGE={namespace.removeprefix("batch_pipeline_")} (now {stage or "unset"})'
        )
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline.scheduler import owner_key

    store = FirestoreStore(namespace, firestore_client=client)
    jobs = client.collection(f'{namespace}_jobs')
    key = owner_key(uid)
    units, seconds, after = 0, 0.0, None
    while units < _HELD_SCAN_LIMIT:
        page = store.allowance_page(key, after, _HELD_PAGE)
        data: dict[str, Any] = {}
        for segment in page:
            data = jobs.document(segment).get(['duration_seconds', 'capture_at', 'segment_id']).to_dict() or {}
            units += 1
            value = data.get('duration_seconds')
            seconds += value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
        if len(page) < _HELD_PAGE:
            break
        after = [data.get('capture_at'), data.get('segment_id')]
    return {'held_units': units, 'held_seconds': int(seconds), 'held_scan_truncated': units >= _HELD_SCAN_LIMIT}


def _stored(client: Any, uid: str, transaction: Any = None) -> tuple[bool, Any]:
    snapshot = client.collection('users').document(uid).get([FIELD], transaction=transaction)
    if not snapshot.exists:
        return False, None
    return True, (snapshot.to_dict() or {}).get(FIELD)


def _transact(client: Any, body: Any) -> Any:
    """Run ``body(transaction)`` once in a Firestore transaction (no retry: a conflict reruns by hand)."""
    return firestore.transactional(body)(client.transaction(max_attempts=1))


def _seconds(args: argparse.Namespace) -> int:
    if (args.hours is None) == (args.seconds is None):
        raise CreditCommandError('pass exactly one of --hours or --seconds')
    value = round(args.hours * 3600) if args.hours is not None else args.seconds
    if value <= 0:
        raise CreditCommandError('the grant must be positive')
    return int(value)


def _expires_days(args: argparse.Namespace) -> int:
    days = args.expires_days
    if days < 1 or days > MAX_EXPIRES_DAYS:
        raise CreditCommandError(f'--expires-days must be between 1 and {MAX_EXPIRES_DAYS}')
    return days


def _view(raw: Any, now: float) -> list[dict[str, Any]]:
    try:
        grants = support_credit.parse_grants(raw)
    except support_credit.CreditUnreadable as exc:
        keys = sorted(raw) if isinstance(raw, dict) else []
        return [{'malformed': str(exc), 'stored_keys': keys, 'repair': 'revoke the bad key'}]
    return [
        {
            'action_id': grant.action_id,
            **support_credit.serialize(grant),
            'expired': grant.expires_at <= now,
            'expires': datetime.fromtimestamp(grant.expires_at, timezone.utc).isoformat(),
        }
        for grant in grants
    ]


def status(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    now = _now()
    exists, raw = _stored(client, args.uid)
    if not exists:
        raise CreditCommandError('account not found')
    grants = _view(raw, now)
    readable = not (grants and 'malformed' in grants[0])
    record.summary = {'grants': len(grants) if readable else None, 'switch_enabled': enabled()}
    return {
        'uid': args.uid,
        'switch_enabled': enabled(),
        'grants': grants,
        **(_allowance(args.uid, raw, now) if readable else {}),
        **_held(client, args.uid, args.namespace),
    }


def grant(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    now = _now()
    seconds = _seconds(args)
    days = _expires_days(args)
    exists, raw = _stored(client, args.uid)
    if not exists:
        raise CreditCommandError('account not found')
    if account_deletion_document(args.uid, firestore_client=client).get().exists:
        raise CreditCommandError('account deletion is pending')
    try:
        before = _allowance(args.uid, raw, now)
    except support_credit.CreditUnreadable as exc:
        raise CreditCommandError(f'the stored credit is unreadable ({exc}); see status, revoke the bad key') from exc
    held = _held(client, args.uid, args.namespace)
    if before['allowance_seconds'] is None:
        raise CreditCommandError('the plan is unlimited; a credit would never be spent')
    if before['plan'] is None or before['used_seconds'] is None:
        # The baseline must be trustworthy, or later usage could spend the credit on
        # transcription that happened before the grant.
        raise CreditCommandError('this month\'s usage is unreadable; no baseline to grant against')
    grant_seconds = int(now)
    entry = support_credit.Grant(
        action_id=record.action_id,
        seconds=seconds,
        granted_at=grant_seconds,
        expires_at=grant_seconds + days * 86400,
        baseline_seconds=before['used_seconds'],
        allowance_seconds=before['allowance_seconds'],
    )
    # A truncated scan undercounts the parked audio, so it never proves coverage.
    covers_held = not held['held_scan_truncated'] and before['credit_usable_seconds'] + seconds >= held['held_seconds']
    record.before_digest = digest(raw)
    record.summary = {
        'grant_seconds': seconds,
        'expires_days': days,
        'held_units': held['held_units'],
        'held_seconds': held['held_seconds'],
        'covers_held': covers_held,
        'switch_enabled': enabled(),
    }
    plan = {
        'uid': args.uid,
        'grant': {**support_credit.serialize(entry), 'action_id': entry.action_id},
        'before': before,
        **held,
        'covers_held': covers_held,
        'switch_enabled': enabled(),
        'release': 'held units are re-offered at the owner\'s next hold check (about 5 minutes)',
    }
    refused = not covers_held and not args.allow_partial
    if not ctx.apply:
        return {**plan, 'dry_run': True, 'apply_would_refuse': refused}
    if refused:
        raise CreditCommandError(
            'the grant does not cover the parked audio (or the scan was truncated), which would all be '
            'released; raise it or pass --allow-partial'
        )
    user_ref = client.collection('users').document(args.uid)

    def write(tx) -> Any:
        found, current = _stored(client, args.uid, tx)
        if not found:
            raise CreditCommandError('account not found')
        if digest(current) != record.before_digest:
            raise CreditCommandError('the credit changed since it was read; rerun')
        kept = support_credit.retained(support_credit.parse_grants(current), now)
        stored = {item.action_id: support_credit.serialize(item) for item in kept}
        stored[entry.action_id] = support_credit.serialize(entry)
        tx.update(user_ref, {FIELD: stored})
        return stored

    stored = _transact(client, write)
    _, after_raw = _stored(client, args.uid)
    if (after_raw or {}).get(entry.action_id) != support_credit.serialize(entry):
        raise CreditCommandError('the grant did not read back')
    record.after_digest = digest(after_raw)
    record.summary['granted'] = True
    return {**plan, 'granted': True, 'grants': _view(stored, now), 'after': _allowance(args.uid, after_raw, now)}


def revoke(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    now = _now()
    exists, raw = _stored(client, args.uid)
    if not exists:
        raise CreditCommandError('account not found')
    # By raw key, without parsing the map, so a malformed entry can be removed too.
    if not isinstance(raw, dict) or args.grant not in raw:
        raise CreditCommandError('no such grant on this account')
    seconds = raw[args.grant].get('seconds') if isinstance(raw[args.grant], dict) else None
    record.before_digest = digest(raw)
    record.summary = {'revoked_seconds': seconds}
    if not ctx.apply:
        return {'uid': args.uid, 'dry_run': True, 'would_revoke': {args.grant: raw[args.grant]}}
    user_ref = client.collection('users').document(args.uid)

    def write(tx) -> None:
        _, current = _stored(client, args.uid, tx)
        if digest(current) != record.before_digest:
            raise CreditCommandError('the credit changed since it was read; rerun')
        tx.update(user_ref, {FieldPath(FIELD, args.grant).to_api_repr(): firestore.DELETE_FIELD})

    _transact(client, write)
    _, after_raw = _stored(client, args.uid)
    if args.grant in (after_raw or {}):
        raise CreditCommandError('the revoke did not read back')
    record.after_digest = digest(after_raw)
    record.summary['revoked'] = True
    return {'uid': args.uid, 'revoked': args.grant, 'grants': _view(after_raw, now)}


def register(groups: Any) -> None:
    group = groups.add_parser('transcription-credit', help='grant, revoke or inspect support transcription credit')
    actions = group.add_subparsers(dest='action', required=True)

    status_parser = actions.add_parser('status', help='grants, balance and parked batch audio for one account')
    status_parser.add_argument('uid')
    status_parser.add_argument('--namespace', default=DEFAULT_NAMESPACE)
    status_parser.set_defaults(handler=status)

    grant_parser = actions.add_parser('grant', help='grant extra managed transcription (dry run unless --apply)')
    grant_parser.add_argument('uid')
    amount = grant_parser.add_mutually_exclusive_group(required=True)
    amount.add_argument('--hours', type=float)
    amount.add_argument('--seconds', type=int)
    grant_parser.add_argument('--expires-days', type=int, default=DEFAULT_EXPIRES_DAYS)
    grant_parser.add_argument(
        '--allow-partial', action='store_true', help='grant less than the parked audio, accepting the overrun'
    )
    grant_parser.add_argument('--namespace', default=DEFAULT_NAMESPACE)
    grant_parser.set_defaults(handler=grant)

    revoke_parser = actions.add_parser('revoke', help='remove one grant (dry run unless --apply)')
    revoke_parser.add_argument('uid')
    revoke_parser.add_argument('grant', help='the grant action id')
    revoke_parser.set_defaults(handler=revoke)
