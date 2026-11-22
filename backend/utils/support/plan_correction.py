"""Audited, owner-scoped repair for stale commercial Stripe plan projections."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timezone
import os
from pathlib import Path
import re
from typing import Any, Iterable, Iterator, TextIO
from uuid import uuid4

from google.cloud import firestore
import httpx

from database import legal_holds, support_actions
from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.support_actions import ActionContext, digest
from utils.support.plan_correction_receipts import OWNER, PrivatePacket, append_receipt

BASIC = 'basic'
PAID_PLANS = frozenset({'architect', 'plus', 'pro', 'unlimited', 'unlimited_v2'})
TERMINAL_SUBSCRIPTIONS = frozenset({'canceled', 'incomplete_expired'})
BILLING_ROUTE = 'account correct-plan'
MAX_PAGES = 10
MAX_STRIPE_CUSTOMERS = 5
MAX_DRY_RUN_OWNERS = 100
MAX_APPLY_OWNERS = 10
STOP_REASONS = frozenset({'pending_checkout', 'billing_unknown', 'state_changed', 'rollback_conflict'})


class EvidenceUnavailable(ValueError):
    pass


class StripeBilling:
    def __init__(self, client: httpx.Client):
        self.client = client

    def _list(self, path: str, customer: str, **filters: Any) -> Iterator[dict[str, Any]]:
        params = {'customer': customer, 'limit': 100, **filters}
        for _ in range(MAX_PAGES):
            response = self.client.get(path, params=params)
            response.raise_for_status()
            page = response.json()
            data, has_more = page['data'], page['has_more']
            if page['object'] != 'list' or not isinstance(data, list) or type(has_more) is not bool:
                raise EvidenceUnavailable()
            for row in data:
                if row['livemode'] is not True or row['customer'] != customer:
                    raise EvidenceUnavailable()
                yield row
            if not has_more:
                return
            params['starting_after'] = data[-1]['id']
        raise EvidenceUnavailable()

    def _billing_customers(self, uid: str, customer: str) -> set[str]:
        # Search only discovers historical customer bindings. Live lists on
        # each discovered customer supply the actual guard evidence.
        customers = {customer}
        params = {'query': f"metadata['uid']:'{uid}'", 'limit': '100'}
        for _ in range(MAX_PAGES):
            response = self.client.get('subscriptions/search', params=params)
            response.raise_for_status()
            page = response.json()
            if page['object'] != 'search_result' or not isinstance(page['data'], list):
                raise EvidenceUnavailable()
            for row in page['data']:
                if row['livemode'] is not True or row['metadata'].get('uid') != uid:
                    raise EvidenceUnavailable()
                bound = row['customer']
                if not isinstance(bound, str) or not re.fullmatch(r'cus_[A-Za-z0-9]+', bound):
                    raise EvidenceUnavailable()
                customers.add(bound)
                if len(customers) > MAX_STRIPE_CUSTOMERS:
                    raise EvidenceUnavailable()
            if page['has_more'] is False:
                return customers
            if page['has_more'] is not True or not page['next_page']:
                raise EvidenceUnavailable()
            params['page'] = page['next_page']
        raise EvidenceUnavailable()

    def guard(self, uid: str, customer: str, subscription: str, since: int, now: int) -> str | None:
        rows = list(self._list('subscriptions', customer, status='all'))
        projected = next((row for row in rows if row['id'] == subscription), None)
        reason = self._subscription_guard(rows)
        if reason:
            return reason
        if not projected or projected['status'] != 'canceled' or projected['metadata'].get('uid') != uid:
            return 'billing_unknown'
        ended_at = projected['ended_at']
        if type(ended_at) is not int or not 0 < ended_at <= now:
            return 'billing_unknown'
        cutoff = min(since, ended_at)
        for other in sorted(self._billing_customers(uid, customer) - {customer}):
            reason = self._subscription_guard(self._list('subscriptions', other, status='all'))
            if reason:
                return reason
            reason = self._payment_guard(other, cutoff, now)
            if reason:
                return reason
        return self._payment_guard(customer, cutoff, now)

    @staticmethod
    def _subscription_guard(rows: Iterable[dict[str, Any]]) -> str | None:
        statuses = {row['status'] for row in rows}
        if 'incomplete' in statuses:
            return 'pending_checkout'
        if statuses - TERMINAL_SUBSCRIPTIONS:
            return 'active_subscription'
        return None

    def _payment_guard(self, customer: str, cutoff: int, now: int) -> str | None:
        for invoice in self._list('invoices', customer):
            paid = invoice['amount_paid']
            if type(paid) is not int or paid < 0:
                raise EvidenceUnavailable()
            if not paid:
                continue
            paid_at = invoice['status_transitions']['paid_at']
            if type(paid_at) is not int or paid_at <= 0:
                return 'billing_unknown'
            if paid_at >= cutoff:
                return 'recent_payment'
            # Protect paid subscription periods still in force even if the
            # payment predates the packet. Invoice period_end is a billing
            # window. The service period comes from each subscription line.
            lines = invoice['lines']
            if lines['has_more'] is not False:
                return 'billing_unknown'
            if any(line['type'] == 'subscription' and line['period']['end'] >= now for line in lines['data']):
                return 'paid_subscription'
        for charge in self._list('charges', customer, **{'expand[]': 'data.balance_transaction'}):
            if charge['status'] == 'pending' or (charge['paid'] is True and charge['captured'] is False):
                return 'pending_checkout'
            if charge['paid'] is True:
                settlement = charge['balance_transaction']
                if type(charge['created']) is not int or not isinstance(settlement, dict):
                    return 'billing_unknown'
                if charge['created'] >= cutoff or settlement['created'] >= cutoff:
                    return 'recent_payment'
        for session in self._list('checkout/sessions', customer, status='complete', **{'created[gte]': cutoff}):
            if session['mode'] == 'subscription' and session['payment_status'] == 'unpaid':
                return 'pending_checkout'
        if any(self._list('checkout/sessions', customer, status='open')):
            return 'pending_checkout'
        return None


def register(actions: Any) -> None:
    parser = actions.add_parser('correct-plan', help='audit and correct an owner’s stale canceled Stripe plan')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--owner')
    target.add_argument('--owners-file', help='committed packet path with one owner per line')
    parser.add_argument('--since', required=True, type=date.fromisoformat, help='packet date in UTC')
    parser.add_argument('--private-checkout', type=Path, required=True)
    parser.add_argument('--receipt', required=True, help='new JSONL path under packets/ in the private checkout')
    proof = parser.add_mutually_exclusive_group()
    proof.add_argument('--dry-run-receipt', help='committed fresh dry run required for apply')
    proof.add_argument('--rollback-receipt', help='committed correction apply receipt for one owner')
    parser.set_defaults(plan_correction=True)


def _write_audit(
    transaction, ref, ctx: ActionContext, owner: str, row: dict, old: dict, new: dict, rollback: str | None
):
    transaction.create(
        ref,
        {
            'schema_version': support_actions.SUPPORT_ACTION_SCHEMA_VERSION,
            'ticket': ctx.ticket,
            'actor': ctx.actor,
            'agent': ctx.agent,
            'principal': ctx.principal,
            'reason': ctx.reason,
            'command': BILLING_ROUTE + (' rollback' if rollback else ''),
            'apply': True,
            'args_digest': digest([ref.id, owner]),
            'before_digest': digest(old),
            'after_digest': digest(new),
            'outcome': 'succeeded',
            'finished_at': firestore.SERVER_TIMESTAMP,
            'summary': {'before_plan': row['before'], 'after_plan': row['after'], 'rollback_of': rollback},
        },
    )


class PlanCorrection:
    def __init__(self, client, billing: StripeBilling, since: int, ctx: ActionContext):
        self.client = client
        self.billing = billing
        self.since = since
        self.ctx = ctx
        self.reads = 0

    def _read(self, ref, transaction=None, field_paths=None):
        self.reads += 1
        return ref.get(transaction=transaction, field_paths=field_paths, retry=None, timeout=8)

    def _state(self, uid: str, user_ref, transaction=None):
        user = self._read(user_ref, transaction, ['subscription', 'stripe_customer_id'])
        hold = legal_holds.validate_legal_hold_snapshot(
            self._read(self.client.collection(legal_holds.LEGAL_HOLDS_COLLECTION).document(uid), transaction)
        )
        if hold and hold['active']:
            return 'legal_hold', user
        if self._read(account_deletion_document(uid, firestore_client=self.client), transaction).exists:
            return 'deletion_marker', user
        if not user.exists:
            return 'missing_account', user
        return None, user

    def process(self, uid: str, receipt: TextIO, proof: dict | None, *, rollback: bool) -> dict:
        user_ref = self.client.collection('users').document(uid)
        problem, snapshot = self._state(uid, user_ref)
        if problem:
            return {'status': problem}
        profile = snapshot.to_dict() or {}
        sub = profile.get('subscription')
        plan = sub.get('plan') if isinstance(sub, dict) else None
        if not isinstance(plan, str):
            return {'status': 'billing_unknown'}
        if plan in {BASIC, 'free'} and not rollback:
            return {'status': 'already_basic'}
        if (not rollback and plan not in PAID_PLANS) or (rollback and plan != BASIC):
            return {'status': 'billing_unknown'}
        customer, stripe_sub = profile.get('stripe_customer_id'), sub.get('stripe_subscription_id')
        if not (
            isinstance(customer, str)
            and re.fullmatch(r'cus_[A-Za-z0-9]+', customer)
            and isinstance(stripe_sub, str)
            and re.fullmatch(r'sub_[A-Za-z0-9]+', stripe_sub)
            and sub.get('status') == 'active'
        ):
            return {'status': 'billing_unknown'}
        row: dict[str, Any] = {'before': plan, 'after': BASIC}
        state_digest = digest([customer, sub])
        if proof and not rollback and (proof['before'] != plan or proof['state_digest'] != state_digest):
            return {**row, 'status': 'state_changed'}
        original_ref = None
        if rollback and proof:
            original_ref = self.client.collection(support_actions.SUPPORT_ACTIONS_COLLECTION).document(proof['action'])
            row['after'] = proof['before']
        problem = self.billing.guard(uid, customer, stripe_sub, self.since, int(datetime.now(timezone.utc).timestamp()))
        if problem:
            return {**row, 'status': problem}
        if not self.ctx.apply and not rollback:
            return {**row, 'status': 'ready', 'state_digest': state_digest}

        action_ref = self.client.collection(support_actions.SUPPORT_ACTIONS_COLLECTION).document(uuid4().hex)
        if self.ctx.apply:
            append_receipt(receipt, {'owner': uid, **row, 'action': action_ref.id, 'status': 'prepared'})
        transaction = self.client.transaction(max_attempts=1, read_only=not self.ctx.apply)

        @firestore.transactional
        def change(txn):
            problem, current = self._state(uid, user_ref, txn)
            if problem:
                return problem
            if current.to_dict() != profile:
                return 'state_changed'
            if original_ref is not None:
                original = self._read(original_ref, txn).to_dict() or {}
                if (
                    original.get('command') != BILLING_ROUTE
                    or original.get('outcome') != 'succeeded'
                    or original.get('args_digest') != digest([original_ref.id, uid])
                    or original.get('after_digest') != digest(sub)
                    or original.get('summary', {}).get('before_plan') != row['after']
                    or row['after'] not in PAID_PLANS
                    or original.get('ticket') != self.ctx.ticket
                    or _version(current.update_time) != proof['version']
                ):
                    return 'rollback_conflict'
            if self.ctx.apply:
                new = {**sub, 'plan': row['after']}
                txn.update(user_ref, {'subscription.plan': row['after']})
                _write_audit(txn, action_ref, self.ctx, uid, row, sub, new, original_ref.id if original_ref else None)
            return None

        problem = change(transaction)
        if problem:
            return {**row, 'status': problem}
        if not self.ctx.apply:
            return {**row, 'status': 'ready', 'state_digest': state_digest}
        version = _version(transaction.write_results[0].update_time)
        result = {**row, 'action': action_ref.id, 'version': version}
        current = self._read(user_ref, field_paths=['subscription'])
        audit = self._read(action_ref).to_dict() or {}
        if (
            _version(current.update_time) != version
            or (current.to_dict() or {}).get('subscription') != {**sub, 'plan': row['after']}
            or audit.get('outcome') != 'succeeded'
            or audit.get('args_digest') != digest([action_ref.id, uid])
            or audit.get('after_digest') != digest({**sub, 'plan': row['after']})
        ):
            return {**result, 'status': 'readback_failed'}
        return {**result, 'status': 'rolled_back' if rollback else 'corrected'}


def _version(timestamp) -> str:
    return timestamp.rfc3339() if timestamp else ''


def _inputs(args: argparse.Namespace, ctx: ActionContext, packet: PrivatePacket, now: datetime):
    owners = [args.owner] if args.owner is not None else packet.owners(args.owners_file)
    if (
        not owners
        or len(owners) > (MAX_APPLY_OWNERS if ctx.apply else MAX_DRY_RUN_OWNERS)
        or len(owners) != len(set(owners))
        or any(OWNER.fullmatch(uid) is None for uid in owners)
        or args.since > now.date()
    ):
        raise EvidenceUnavailable()
    mode = 'rollback' if args.rollback_receipt else 'apply' if ctx.apply else 'dry_run'
    if mode == 'rollback' and len(owners) != 1:
        raise EvidenceUnavailable()
    proof_path = args.rollback_receipt or args.dry_run_receipt
    if (ctx.apply or mode == 'rollback') and not proof_path:
        raise EvidenceUnavailable()
    if not proof_path:
        return owners, mode, {}
    header, *entries, trailer = packet.receipt(proof_path)
    if trailer.get('complete') is not True:
        raise EvidenceUnavailable()
    expected_mode, status = ('apply', 'corrected') if mode == 'rollback' else ('dry_run', 'ready')
    if header['mode'] != expected_mode or header['ticket'] != ctx.ticket or header['since'] != args.since.isoformat():
        raise EvidenceUnavailable()
    if mode == 'apply' and not 0 <= (now - datetime.fromisoformat(header['created_at'])).total_seconds() <= 86400:
        raise EvidenceUnavailable()
    eligible = {row['owner']: row for row in entries if row.get('status') == status}
    if any(trailer['counts'].get(reason, 0) for reason in ('failed', 'billing_unknown')) and mode == 'apply':
        raise EvidenceUnavailable()
    if not set(owners) <= eligible.keys():
        raise EvidenceUnavailable()
    return owners, mode, eligible


def run(args: argparse.Namespace, ctx: ActionContext, *, firestore_client=None) -> tuple[dict, int]:
    """Return count-only output. Per-owner status is written exclusively to the packet."""
    reads = 0
    counts: Counter = Counter()
    try:
        if ctx.apply and os.getenv('OMI_SUPPORT_CORRECT_PLAN_ENABLED', 'true').lower() == 'false':
            return {'document_reads': 0, 'counts': {}, 'error': 'disabled'}, 1
        key = os.environ['STRIPE_PLAN_CORRECTION_READ_KEY']
        if not key.startswith(('rk_live_', 'sk_live_')):
            raise EvidenceUnavailable()
        packet = PrivatePacket(args.private_checkout)
        now = datetime.now(timezone.utc)
        owners, mode, proofs = _inputs(args, ctx, packet, now)
        since = int(datetime.combine(args.since, time.min, tzinfo=timezone.utc).timestamp())
        with (
            packet.new_receipt(args.receipt) as f,
            httpx.Client(
                base_url='https://api.stripe.com/v1/',
                headers={'Authorization': f'Bearer {key}', 'Stripe-Version': '2024-10-28.acacia'},
                timeout=8,
                trust_env=False,
                follow_redirects=False,
            ) as stripe,
        ):
            append_receipt(
                f, {'mode': mode, 'ticket': ctx.ticket, 'created_at': now.isoformat(), 'since': args.since.isoformat()}
            )
            operator = PlanCorrection(
                account_deletion_firestore_client(firestore_client=firestore_client), StripeBilling(stripe), since, ctx
            )
            try:
                for uid in owners:
                    try:
                        row = operator.process(uid, f, proofs.get(uid), rollback=mode == 'rollback')
                    except Exception:
                        row = {'status': 'failed'}
                    append_receipt(f, {'owner': uid, **row})
                    counts[row['status']] += 1
                    if ctx.apply and (row['status'] in STOP_REASONS or row['status'] in {'failed', 'readback_failed'}):
                        break
            finally:
                reads = operator.reads
            counts['unprocessed'] = len(owners) - sum(counts.values())
            append_receipt(f, {'complete': True, 'document_reads': reads, 'counts': dict(counts)})
    except Exception:
        return {'document_reads': reads, 'counts': dict(counts), 'error': 'command_failed'}, 1
    unsafe = {'failed', 'readback_failed', 'billing_unknown', 'state_changed', 'rollback_conflict'}
    if ctx.apply:
        unsafe.add('pending_checkout')
    return {'document_reads': reads, 'counts': dict(counts)}, int(any(counts[status] for status in unsafe))
