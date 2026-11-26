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

from config.plan_catalog import PAID_PLAN_IDS
from config.refactor_modes import default_on
from database import legal_holds, support_actions
from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.support_actions import ActionContext, digest
from utils.support.plan_correction_receipts import OWNER, PrivatePacket, append_receipt

BASIC = 'basic'
PAID_PLANS = PAID_PLAN_IDS | {'pro'}
TERMINAL_SUBSCRIPTIONS = frozenset({'canceled', 'incomplete_expired'})
BILLING_ROUTE = 'account correct-plan'
RECEIPT_SCHEMA = 'support_plan_correction.v1'
MAX_PAGES = 10
MAX_STRIPE_CUSTOMERS = 10
MAX_DRY_RUN_OWNERS = 100
MAX_APPLY_OWNERS = 10
STOP_REASONS = frozenset(
    {'pending_checkout', 'billing_unknown', 'basic_with_price', 'state_changed', 'rollback_conflict'}
)
UNSAFE_OUTCOMES = (STOP_REASONS - {'pending_checkout'}) | {'failed', 'readback_failed'}


class EvidenceUnavailable(ValueError):
    pass


class InvalidReceipt(EvidenceUnavailable):
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

    def _search_owner(self, path: str, uid: str) -> Iterator[dict[str, Any]]:
        params = {'query': f"metadata['uid']:'{uid}'", 'limit': '100'}
        for _ in range(MAX_PAGES):
            response = self.client.get(path, params=params)
            response.raise_for_status()
            page = response.json()
            if page['object'] != 'search_result' or not isinstance(page['data'], list):
                raise EvidenceUnavailable()
            for row in page['data']:
                if row['livemode'] is not True or row['metadata'].get('uid') != uid:
                    raise EvidenceUnavailable()
                yield row
            if page['has_more'] is False:
                return
            if page['has_more'] is not True or not page['next_page']:
                raise EvidenceUnavailable()
            params['page'] = page['next_page']
        raise EvidenceUnavailable()

    def _billing_customers(self, uid: str, customer: str) -> set[str]:
        # Search discovers historical customer bindings. Live lists on each
        # discovered customer supply the guard evidence.
        customers = {customer}
        for path, field in (('subscriptions/search', 'customer'), ('customers/search', 'id')):
            for row in self._search_owner(path, uid):
                bound = row[field]
                if not isinstance(bound, str) or not re.fullmatch(r'cus_[A-Za-z0-9]+', bound):
                    raise EvidenceUnavailable()
                customers.add(bound)
                if len(customers) > MAX_STRIPE_CUSTOMERS:
                    raise EvidenceUnavailable()
        return customers

    def guard(
        self, uid: str, customer: str, subscription: str, since: int, now: int, *, price: str | None = None
    ) -> str | None:
        rows = list(self._list('subscriptions', customer, status='all'))
        projected = next((row for row in rows if row['id'] == subscription), None)
        reason = self._subscription_guard(rows)
        if reason:
            return reason
        if not projected or projected['status'] != 'canceled' or projected['metadata'].get('uid') != uid:
            return 'billing_unknown'
        if price is not None and not any(item['price']['id'] == price for item in projected['items']['data']):
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
        for session in self._list('checkout/sessions', customer, status='complete'):
            if session['mode'] in {'subscription', 'payment'} and session['payment_status'] == 'unpaid':
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
            'started_at': firestore.SERVER_TIMESTAMP,
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
        return ref.get(transaction=transaction, field_paths=field_paths, retry=None, timeout=3)

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
            return {'outcome': problem}
        profile = snapshot.to_dict() or {}
        sub = profile.get('subscription')
        if not isinstance(sub, dict):
            return {'outcome': 'billing_unknown'}
        plan = sub.get('plan')
        if not isinstance(plan, str):
            return {'outcome': 'billing_unknown'}
        if plan in {BASIC, 'free'} and not rollback:
            outcome = 'basic_with_price' if sub.get('current_price_id') is not None else 'already_basic'
            return {'outcome': outcome}
        if (not rollback and plan not in PAID_PLANS) or (rollback and plan != BASIC):
            return {'outcome': 'billing_unknown'}
        customer, stripe_sub = profile.get('stripe_customer_id'), sub.get('stripe_subscription_id')
        if not (
            isinstance(customer, str)
            and re.fullmatch(r'cus_[A-Za-z0-9]+', customer)
            and isinstance(stripe_sub, str)
            and re.fullmatch(r'sub_[A-Za-z0-9]+', stripe_sub)
            and sub.get('status') == 'active'
        ):
            return {'outcome': 'billing_unknown'}
        before_price = sub.get('current_price_id')
        if before_price is not None and not isinstance(before_price, str):
            return {'outcome': 'billing_unknown'}
        row: dict[str, Any] = {
            'before': plan,
            'after': BASIC,
            'before_price_present': 'current_price_id' in sub,
            'before_price_id': before_price,
            'after_price_id': None,
        }
        state_digest = digest([customer, sub])
        if proof and not rollback and (proof['before'] != plan or proof['state_digest'] != state_digest):
            return {**row, 'outcome': 'state_changed'}
        if rollback and proof is None:
            return {**row, 'outcome': 'rollback_conflict'}
        original_ref = None
        if rollback and proof is not None:
            original_ref = self.client.collection(support_actions.SUPPORT_ACTIONS_COLLECTION).document(proof['action'])
            row['after'] = proof['before']
            price_present = proof['before_price_present']
            prior_price = proof['before_price_id']
            if (
                type(price_present) is not bool
                or price_present != row['before_price_present']
                or (prior_price is not None and (not isinstance(prior_price, str) or not price_present))
                or before_price is not None
            ):
                return {**row, 'outcome': 'rollback_conflict'}
            row['after_price_id'] = prior_price
        expected = {**sub, 'plan': row['after']}
        patch = {'subscription.plan': row['after']}
        if before_price != row['after_price_id']:
            expected['current_price_id'] = row['after_price_id']
            patch['subscription.current_price_id'] = row['after_price_id']
        problem = self.billing.guard(
            uid,
            customer,
            stripe_sub,
            self.since,
            int(datetime.now(timezone.utc).timestamp()),
            price=row['after_price_id'] if rollback else before_price,
        )
        if problem:
            return {**row, 'outcome': problem}
        if not self.ctx.apply and not rollback:
            return {**row, 'outcome': 'ready', 'state_digest': state_digest}

        action_ref = self.client.collection(support_actions.SUPPORT_ACTIONS_COLLECTION).document(uuid4().hex)
        if self.ctx.apply:
            append_receipt(receipt, {'owner': uid, **row, 'action': action_ref.id, 'outcome': 'prepared'})
        transaction = self.client.transaction(max_attempts=1, read_only=not self.ctx.apply)

        @firestore.transactional
        def change(txn):
            problem, current = self._state(uid, user_ref, txn)
            if problem:
                return problem
            if current.to_dict() != profile:
                return 'state_changed'
            if original_ref is not None and proof is not None:
                original = self._read(original_ref, txn).to_dict() or {}
                if (
                    original.get('command') != BILLING_ROUTE
                    or original.get('outcome') != 'succeeded'
                    or original.get('args_digest') != digest([original_ref.id, uid])
                    or original.get('after_digest') != digest(sub)
                    or original.get('before_digest') != digest(expected)
                    or original.get('summary', {}).get('before_plan') != row['after']
                    or row['after'] not in PAID_PLANS
                    or original.get('ticket') != self.ctx.ticket
                    or _version(current.update_time) != proof['version']
                ):
                    return 'rollback_conflict'
            if self.ctx.apply:
                txn.update(user_ref, patch)
                _write_audit(
                    txn, action_ref, self.ctx, uid, row, sub, expected, original_ref.id if original_ref else None
                )
            return None

        problem = change(transaction)
        if problem:
            return {**row, 'outcome': problem}
        if not self.ctx.apply:
            return {**row, 'outcome': 'ready', 'state_digest': state_digest}
        result = {**row, 'action': action_ref.id}
        writes = transaction.write_results or ()
        version = _version(writes[0].update_time) if writes else ''
        if not version:
            return {**result, 'outcome': 'readback_failed'}
        result['version'] = version
        current = self._read(user_ref, field_paths=['subscription'])
        audit = self._read(action_ref).to_dict() or {}
        if (
            _version(current.update_time) != version
            or (current.to_dict() or {}).get('subscription') != expected
            or audit.get('outcome') != 'succeeded'
            or audit.get('args_digest') != digest([action_ref.id, uid])
            or audit.get('after_digest') != digest(expected)
        ):
            return {**result, 'outcome': 'readback_failed'}
        return {**result, 'outcome': 'rolled_back' if rollback else 'corrected'}


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
    try:
        header, *entries, trailer = packet.receipt(proof_path)
        expected_mode, status = ('apply', 'corrected') if mode == 'rollback' else ('dry_run', 'ready')
        if header.get('schema') != RECEIPT_SCHEMA or trailer.get('complete') is not True:
            raise InvalidReceipt()
        if (
            header.get('mode') != expected_mode
            or header.get('ticket') != ctx.ticket
            or header.get('since') != args.since.isoformat()
        ):
            raise InvalidReceipt()
        eligible = {row['owner']: row for row in entries if row.get('outcome') == status}
        if mode == 'apply':
            created_at, counts = header.get('created_at'), trailer.get('counts')
            if not isinstance(created_at, str) or not isinstance(counts, dict):
                raise InvalidReceipt()
            age = now - datetime.fromisoformat(created_at)
            if not 0 <= age.total_seconds() <= 86400:
                raise InvalidReceipt()
            if any(counts.get(reason, 0) for reason in UNSAFE_OUTCOMES):
                raise InvalidReceipt()
        if not set(owners) <= eligible.keys():
            raise InvalidReceipt()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise InvalidReceipt() from exc
    return owners, mode, eligible


def run(args: argparse.Namespace, ctx: ActionContext, *, firestore_client=None) -> tuple[dict, int]:
    """Return count-only output. Per-owner status is written exclusively to the packet."""
    reads = 0
    counts: Counter = Counter()
    try:
        if ctx.apply and not default_on('OMI_SUPPORT_CORRECT_PLAN_ENABLED'):
            return {'document_reads': 0, 'counts': {}, 'error': 'disabled'}, 1
        key = os.environ['STRIPE_PLAN_CORRECTION_READ_KEY']
        if not key.startswith('rk_live_'):
            raise EvidenceUnavailable()
        packet = PrivatePacket(args.private_checkout, os.environ['OMI_SUPPORT_TRIAGE_ORIGIN'])
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
                f,
                {
                    'schema': RECEIPT_SCHEMA,
                    'mode': mode,
                    'ticket': ctx.ticket,
                    'created_at': now.isoformat(),
                    'since': args.since.isoformat(),
                },
            )
            operator = PlanCorrection(
                account_deletion_firestore_client(firestore_client=firestore_client), StripeBilling(stripe), since, ctx
            )
            try:
                for uid in owners:
                    try:
                        row = operator.process(uid, f, proofs.get(uid), rollback=mode == 'rollback')
                    except EvidenceUnavailable:
                        row = {'outcome': 'billing_unknown'}
                    except Exception:
                        row = {'outcome': 'failed'}
                    append_receipt(f, {'owner': uid, **row})
                    counts[row['outcome']] += 1
                    if ctx.apply and row['outcome'] in STOP_REASONS | UNSAFE_OUTCOMES:
                        break
            finally:
                reads = operator.reads
            counts['unprocessed'] = len(owners) - sum(counts.values())
            append_receipt(f, {'complete': True, 'document_reads': reads, 'counts': dict(counts)})
    except InvalidReceipt:
        return {'document_reads': reads, 'counts': dict(counts), 'error': 'invalid_receipt'}, 1
    except Exception:
        return {'document_reads': reads, 'counts': dict(counts), 'error': 'command_failed'}, 1
    unsafe = UNSAFE_OUTCOMES | {'pending_checkout'} if ctx.apply else UNSAFE_OUTCOMES
    return {'document_reads': reads, 'counts': dict(counts)}, int(any(counts[status] for status in unsafe))
