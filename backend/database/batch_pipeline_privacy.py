"""Transactional privacy authority for batch intake, compute and projection.

All reads precede caller writes and use the customer-data transaction. The
hashed generation survives recursive account wipes and contains no content.
"""

from collections import OrderedDict, deque
from collections.abc import Iterable
import hashlib
import threading
import time
from uuid import uuid4
from enum import Enum
from typing import Any

from config.firestore_read_levers import lever_enabled, lever_percent
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.batch_privacy_attempt import SCHEMA_FIELD, TOKEN_FIELD, TOKEN_SCHEMA, current_attempt, token_version
from database import privacy_check_metrics as metrics
from database import batch_privacy_negative_cache as negative_cache
from database.privacy_ttl_cache import BoundedTTLCache, disabled as ttl_disabled, enabled as ttl_enabled, is_missing

PRIVACY_COLLECTION = 'batch_pipeline_privacy'
# Token-validated generations shared across task attempts in this process
# (lever bpp_decision_cache). Keys hold the client object itself, so planes and
# recycled ids never mix; entries expire 60s after the authority walk started.
PROCESS_DECISIONS = BoundedTTLCache()
# Owner-level decisions (lever bpp_owner_memo, default on): key (client, uid);
# value (token_version, generation, certified conversation-id union, user sync
# default). Same per-use certification as PROCESS_DECISIONS — every use re-reads
# the durable token inside the caller's transaction and requires token, server
# revision and generation to match; ids the entry has not certified under that
# token are verified live in the same transaction. BLOCK is never stored.
PROCESS_OWNERS = BoundedTTLCache()
# The walk's own fence budget; a certified union never grows past it.
OWNER_ID_CAP = 256


class BatchPrivacyReason(str, Enum):
    ACCOUNT_DELETED = 'account_deleted'
    ACCOUNT_MISSING = 'account_missing'
    DATA_PROTECTION_CHANGED = 'data_protection_changed'
    PRIVACY_GENERATION_CHANGED = 'privacy_generation_changed'
    CONVERSATION_REDIRECT_CYCLE = 'conversation_redirect_cycle'
    CONVERSATION_FENCE_BUDGET = 'conversation_fence_budget'
    CONVERSATION_DELETED = 'conversation_deleted'
    RECORDING_PRIVACY_CHANGED = 'recording_privacy_changed'
    CONVERSATION_REDIRECT_MISSING = 'conversation_redirect_missing'
    RESULT_LEASE_LOST = 'result_lease_lost'
    UNKNOWN = 'unknown'


STRUCTURAL_REASONS = frozenset(
    {
        BatchPrivacyReason.CONVERSATION_REDIRECT_CYCLE,
        BatchPrivacyReason.CONVERSATION_REDIRECT_MISSING,
        BatchPrivacyReason.CONVERSATION_FENCE_BUDGET,
    }
)


class BatchPrivacyBlocked(RuntimeError):
    """A deleted, migrating or E2EE owner/source cannot accept server results."""

    def __init__(self, *args, conversation_id: str | None = None):
        super().__init__(*args)
        # Internal re-planning hint only; never include identifiers in the message.
        self.conversation_id = conversation_id

    @property
    def reason(self) -> BatchPrivacyReason:
        """Bound telemetry even if a caller supplies an unsafe exception message."""
        try:
            return BatchPrivacyReason(self.args[0])
        except (IndexError, ValueError, TypeError):
            return BatchPrivacyReason.UNKNOWN


def privacy_owner_key(uid: str) -> str:
    if not uid or '/' in uid or len(uid.encode()) > 256:
        raise ValueError('bounded owner document ID required')
    return hashlib.sha256(uid.encode()).hexdigest()


@metrics.with_batch_plan
def assert_batch_write_allowed(
    client: Any,
    transaction: Any,
    uid: str,
    *,
    conversation_ids: Iterable[str] = (),
    expected_generation: int | None = None,
    snapshots: dict | None = None,
    allow_token_mint: bool = True,
    read_budget=None,
    verified_out: set | None = None,
) -> int:
    """Measure the authorizing decision; shadow always runs after live authority.

    The nontransactional provider-STT preflight stays live. A decision the owner
    memo (bpp_owner_memo) serves exports no rows for ids it has already certified;
    unseen ids are walked live and their rows are exported, so a caller may get a
    partial export. Shadow never publishes snapshots, raises its failure or
    changes a decision.

    ``verified_out`` optionally receives every conversation document id this
    check actually verified, redirect hops included. Callers use it to keep a
    distinct-document budget across several checks without an export.
    """
    metrics.called('batch')
    # A generation-memo hit would hide the live lookups needed for shadow proof.
    negative_shadow = lever_enabled('privacy_negative_lookup_cache', uid) and lever_enabled(
        'privacy_checks_shadow', uid
    )
    # The sampled cohort serves the live decision and compares an owner-memo
    # candidate on EVERY transactional path: attempt-scoped calls, the
    # store/retention no_attempt mass, and the snapshots callers (projection,
    # intake). Requiring an attempt here would leave those paths enforcing the
    # memo with no comparison. Nontransactional calls cannot be compared (and
    # the memo cannot enforce there); the negative cache keeps its own shadow.
    # The window is fleet-wide for the owner memo: while ANY shadow percentage
    # is set, no uid enforces it — sampled uids compare a candidate and every
    # other uid serves live (see owner_on below) — so an unsampled uid can
    # never serve a decision the comparison cohort has not validated.
    shadow = lever_enabled('privacy_checks_shadow', uid) and not negative_shadow
    enforce = (
        (lever_enabled('bpp_generation_memo', uid) or lever_enabled('bpp_owner_memo', uid))
        and not shadow
        and not negative_shadow
    )
    # Materialize once when comparing, including one-shot source generators.
    ids = tuple(conversation_ids) if shadow else conversation_ids
    kwargs: dict[str, Any] = dict(
        conversation_ids=ids,
        expected_generation=expected_generation,
        snapshots=snapshots,
        read_budget=read_budget,
        verified_out=verified_out,
    )
    if enforce:
        kwargs['allow_token_mint'] = allow_token_mint
    # The candidate always gets a throwaway export: a comparison may fill its
    # own copy but can never publish rows or perturb the caller's export. It
    # also decides with the owner path ON (owner_candidate): it must compute
    # what the memo would serve after the window, not what the window allows.
    candidate_kwargs: dict[str, Any] = dict(
        conversation_ids=ids,
        expected_generation=expected_generation,
        snapshots={} if snapshots is not None else None,
        read_budget=read_budget,
        owner_candidate=True,
        allow_token_mint=allow_token_mint,
    )
    function = _assert_batch_write_allowed_memo if enforce else _assert_batch_write_allowed_live
    live_evidence = metrics.DecisionEvidence() if shadow or enforce else None

    def shadow_after(reason):
        if not shadow or transaction is None or enforce:
            return
        try:
            candidate_evidence = metrics.DecisionEvidence()
            with metrics.mode_scope('shadow'), metrics.evidence_scope(candidate_evidence):
                metrics.called('batch')
                try:
                    _assert_batch_write_allowed_memo(client, transaction, uid, **candidate_kwargs)
                    candidate = 'allow'
                except BatchPrivacyBlocked as error:
                    candidate = error.reason.value
                metrics.decision('batch', candidate)
            metrics.compare(
                'batch', reason, candidate, live_evidence=live_evidence, candidate_evidence=candidate_evidence
            )
        except Exception:
            metrics.shadow_error('batch')

    with metrics.evidence_scope(live_evidence):
        if shadow and transaction is not None:
            # Observation only, before the live walk; failures cannot alter live authority.
            try:
                metrics.read_snapshot(
                    'batch',
                    client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid)),
                    transaction=transaction,
                    read_budget=read_budget,
                )
            except Exception:
                pass
        try:
            result = function(client, transaction, uid, **kwargs)
        except BatchPrivacyBlocked as error:
            metrics.decision('batch', error.reason.value)
            shadow_after(error.reason.value)
            raise
        except Exception:
            metrics.decision('batch', 'authority_unavailable')
            raise
        metrics.decision('batch')
        shadow_after('allow')
        return result


def _assert_batch_write_allowed_memo(
    client: Any,
    transaction: Any,
    uid: str,
    *,
    conversation_ids: Iterable[str] = (),
    expected_generation: int | None = None,
    snapshots: dict | None = None,
    allow_token_mint: bool = True,
    read_budget=None,
    verified_out: set | None = None,
    owner_candidate: bool = False,
):
    # Keep the disabled path's live read order and counts unchanged.
    # A served owner decision exports no rows for ids the entry has already
    # certified; unseen ids are verified live here and their rows ARE exported,
    # so an export caller may receive a partial export. The token certifies
    # authorization, not row payloads, and the caller reads any missing rows
    # itself. A miss walks live and fills the export exactly as before.
    attempt = current_attempt()
    # A call with no attempt may still consult a process cache, but only inside
    # a transaction with no snapshots export (bpp_decision_cache) or through
    # the owner memo (bpp_owner_memo), which also admits snapshots calls
    # because a hit serves no rows. Short-circuit on the transaction and the
    # lever so nontransactional and lever-off calls never poll a kill switch.
    # Shadow window: while any privacy_checks_shadow percentage is set, the
    # owner memo serves no one — sampled uids compare a candidate after the
    # live decision (owner_candidate, set only by that comparison) and every
    # other uid stays live — so a zero stale_allow is evidence for every path
    # the memo will serve once the window clears. The already-shipped id-set
    # memo is NOT gated by the window; it keeps its own levers and keying.
    owner_on = (
        transaction is not None
        and lever_enabled('bpp_owner_memo', uid)
        and not ttl_disabled()
        and (owner_candidate or lever_percent('privacy_checks_shadow') == 0)
    )
    # The id-set memo keeps its own levers so turning the owner memo off (or
    # on) never changes what the id-set path does.
    idset_on = lever_enabled('bpp_generation_memo', uid)
    process_on = (
        attempt is None and transaction is not None and snapshots is None and ttl_enabled('bpp_decision_cache', uid)
    )
    if (
        (attempt is None and not process_on and not owner_on)
        or transaction is None
        or (snapshots is not None and not owner_on)
    ):
        metrics.memo_result('batch', 'ineligible')
        metrics.memo_ineligible(
            'no_attempt' if attempt is None else 'no_transaction' if transaction is None else 'snapshots'
        )
        return _assert_batch_write_allowed_live(
            client,
            transaction,
            uid,
            conversation_ids=conversation_ids,
            expected_generation=expected_generation,
            snapshots=snapshots,
            read_budget=read_budget,
            verified_out=verified_out,
        )
    ids = frozenset(conversation_ids)
    # Retain the client object itself, preventing id reuse and cross-plane hits.
    key = (client, uid, ids)
    owner_key = (client, uid)
    reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))
    if attempt is not None:
        process_on = idset_on and ttl_enabled('bpp_decision_cache', uid)
    started = PROCESS_DECISIONS.clock()
    owner_started = PROCESS_OWNERS.clock()
    evidence = metrics.current_evidence()
    try:
        # Every decision reads this token afresh, including repeated checks in one transaction.
        # Every authorizing transaction enrolls the token in its conflict set.
        try:
            snapshot = metrics.read_snapshot('batch', reference, transaction=transaction, read_budget=read_budget)
        except Exception:
            if attempt is not None:
                attempt.forget(key)
                attempt.owner_forget(owner_key)
            PROCESS_DECISIONS.forget(key)
            PROCESS_OWNERS.forget(owner_key)
            metrics.memo_result('batch', 'ineligible')
            if evidence is not None:
                evidence.token_seen, evidence.token, evidence.generation = True, None, None
                evidence.source, evidence.certification = 'fresh_read', 'unavailable'
            return _assert_batch_write_allowed_live(
                client,
                transaction,
                uid,
                conversation_ids=ids,
                expected_generation=expected_generation,
                snapshots=snapshots,
                read_budget=read_budget,
                verified_out=verified_out,
            )
        # GAPIC transport retries may replay an already-prepared random token
        # after another writer. The server revision prevents that ABA: replay
        # commits get a new update_time, including deletion/recreation. Keep
        # nanoseconds too rather than relying on datetime's microsecond equality.
        version = token_version(snapshot)
        authority_generation = (snapshot.to_dict() or {}).get('generation', 0)
        eligible = version is not None and type(authority_generation) is int
        generation = attempt.get(key, version) if eligible and attempt is not None and idset_on else None
        if type(generation) is not int or generation != authority_generation:
            generation = None
        if evidence is not None:
            evidence.certification = 'miss' if eligible else 'unavailable'
            if generation is not None:
                evidence.source, evidence.certification = 'session_hit', 'matched'
        if owner_on and eligible:
            served = _owner_decision(
                client,
                transaction,
                uid,
                ids=ids,
                expected_generation=expected_generation,
                version=version,
                authority_generation=authority_generation,
                snapshots=snapshots,
                read_budget=read_budget,
                attempt=attempt,
                evidence=evidence,
                started=owner_started,
                verified_out=verified_out,
            )
            if served is not None:
                return served
            # The owner entry could not certify this call; the id-set memo and
            # the live walk below decide it, and a fresh owner entry is stored.
        if generation is None and eligible and process_on:
            # Process-wide reuse across attempts (lever bpp_decision_cache), at most
            # 60s old, and still certified by THIS transaction's token read: any
            # authority write since the cached walk rotated the token in the same
            # commit (database.batch_privacy_write_fence), so a changed token misses
            # and a concurrent writer aborts this transaction at commit.
            cached, age = PROCESS_DECISIONS.get(key)
            if evidence is not None:
                evidence.age = age
                evidence.certification = 'miss' if is_missing(cached) else 'mismatch'
            if (
                isinstance(cached, tuple)
                and len(cached) == 3
                and cached[0] == version
                and type(cached[1]) is int
                and cached[1] == authority_generation
            ):
                generation = cached[1]
                metrics.ttl_result('batch', 'hit')
                if evidence is not None:
                    evidence.source, evidence.certification = 'ttl_hit', 'matched'
                    evidence.markers.update(cached[2])
                if attempt is not None:
                    attempt.put(key, version, generation)
            else:
                metrics.ttl_result('batch', 'miss')
        if generation is not None and (expected_generation is None or generation == expected_generation):
            metrics.memo_result('batch', 'hit')
            return generation
        metrics.memo_result('batch', 'miss' if eligible else 'ineligible')
        if allow_token_mint and not eligible and _mintable(snapshot):
            metrics.memo_result('batch', 'no_token')
            try:
                schedule_token_mint(client, reference, uid)
            except Exception:  # best effort: scheduling must never change or block the decision
                metrics.memo_result('batch', 'mint_error')
        if attempt is not None:
            attempt.forget(key)
        if evidence is not None:
            evidence.source = 'fresh_read'
        walk_out: dict[str, Any] = {}
        generation = _assert_batch_write_allowed_live(
            client,
            transaction,
            uid,
            conversation_ids=ids,
            expected_generation=expected_generation,
            # An export caller admitted by the owner memo still gets its rows
            # from the walk it actually paid for.
            snapshots=snapshots,
            privacy_snapshot=snapshot,
            read_budget=read_budget,
            walk_out=walk_out,
            verified_out=verified_out,
        )
        if eligible:
            if idset_on:
                if attempt is not None:
                    attempt.put(key, version, generation)
                if process_on and PROCESS_DECISIONS.put(
                    key, (version, generation, dict(evidence.markers) if evidence else {}), started=started
                ):
                    metrics.ttl_result('batch', 'store')
            if owner_on:
                _owner_store(
                    owner_key,
                    version,
                    generation,
                    ids | walk_out.get('verified', set()),
                    walk_out.get('user_sync_enabled', True),
                    attempt,
                    started=owner_started,
                )
        return generation
    except BaseException:
        # Neither a partial authority walk nor a failed token read is reusable.
        if attempt is not None:
            attempt.forget(key)
            attempt.owner_forget(owner_key)
        PROCESS_DECISIONS.forget(key)
        PROCESS_OWNERS.forget(owner_key)
        raise


def _owner_store(owner_key, version, generation, certified_ids, user_sync_enabled, attempt, *, started) -> None:
    """Store one ALLOW walk as the owner's certified decision (never a BLOCK).

    ``started`` is when the authority walk began; every later reuse of this
    entry — including grown unions — keeps it, so the 60s bound stays anchored
    to the walk that actually read the authority documents.
    """
    certified = frozenset(certified_ids)
    if len(certified) > OWNER_ID_CAP:
        # Keep the union inside the walk's own fence budget; overflow ids are
        # simply re-verified live on their next check.
        certified = frozenset(sorted(certified)[:OWNER_ID_CAP])
    entry = (version, generation, certified, bool(user_sync_enabled), started)
    if attempt is not None:
        attempt.owner_put(owner_key, entry)
    if PROCESS_OWNERS.put(owner_key, entry, started=started):
        metrics.ttl_result('batch', 'store')


def _owner_decision(
    client: Any,
    transaction: Any,
    uid: str,
    *,
    ids: frozenset,
    expected_generation: int | None,
    version,
    authority_generation,
    snapshots: dict | None,
    read_budget,
    attempt,
    evidence,
    started: float,
    verified_out: set | None = None,
) -> int | None:
    """Serve one check from the owner-level memo; None when it cannot certify.

    The certification rule is unchanged: THIS decision's fresh token read must
    match the entry's token version and generation, and every conversation id
    the entry has not certified under that token is verified live inside this
    transaction (tombstone, conversation row, redirect chain, lane check)
    before the decision is served. A served decision leaves ``snapshots`` empty
    for already-certified ids; unseen ids are verified live here and their rows
    are written into the caller's export.
    """
    owner_key = (client, uid)
    entry = attempt.owner_get(owner_key) if attempt is not None else None
    from_process = False
    if not (isinstance(entry, tuple) and len(entry) == 5 and entry[0] == version and entry[1] == authority_generation):
        cached, _age = PROCESS_OWNERS.get(owner_key)
        if (
            isinstance(cached, tuple)
            and len(cached) == 5
            and cached[0] == version
            and cached[1] == authority_generation
        ):
            entry, from_process = cached, True
            if attempt is not None:
                attempt.owner_put(owner_key, entry)
        else:
            entry = None
    if entry is None:
        if evidence is not None:
            evidence.certification = 'miss'
        return None
    _version, generation, certified, user_sync_enabled, started = entry
    if expected_generation is not None and generation != expected_generation:
        # The entry is still certified, but this caller expects another
        # generation: only the live walk can raise the exact refusal.
        if attempt is not None:
            attempt.owner_forget(owner_key)
        PROCESS_OWNERS.forget(owner_key)
        if evidence is not None:
            evidence.certification = 'mismatch'
        return None
    new_ids = ids - certified
    if new_ids:
        negative_on = lever_enabled('privacy_negative_lookup_cache', uid) and snapshots is None
        negative_shadow = negative_on and lever_enabled('privacy_checks_shadow', uid)
        negative_started = negative_cache.LOOKUPS.clock() if negative_on else None

        def live_read(reference):
            return metrics.read_snapshot('batch', reference, transaction=transaction, read_budget=read_budget)

        def read(reference, collection=None):
            if negative_on and collection is not None:
                return negative_cache.read(
                    client,
                    uid,
                    reference,
                    collection,
                    version,
                    live_read,
                    shadow=negative_shadow,
                    started=negative_started,
                )
            return live_read(reference)

        try:
            _verify_conversation_ids(
                client, transaction, uid, new_ids, user_sync_enabled, snapshots, read, verified_out=verified_out
            )
        except BatchPrivacyBlocked:
            # The entry's previously certified ids remain certified, but a
            # refusal on a new id must never be served from this entry again.
            if attempt is not None:
                attempt.owner_forget(owner_key)
            PROCESS_OWNERS.forget(owner_key)
            raise
        grown = certified | new_ids
        if len(grown) <= OWNER_ID_CAP:
            # The union grows, but the bound stays with the original walk.
            entry = (version, generation, grown, user_sync_enabled, started)
            if attempt is not None:
                attempt.owner_put(owner_key, entry)
            PROCESS_OWNERS.put(owner_key, entry, started=started)
    metrics.memo_result('batch', 'hit')
    if from_process:
        metrics.ttl_result('batch', 'hit')
    if evidence is not None:
        evidence.source, evidence.certification = 'owner_hit', 'matched'
        evidence.generation = generation
        if from_process:
            evidence.age = PROCESS_OWNERS.clock() - started
    return generation


def _assert_batch_write_allowed_live(
    client: Any,
    transaction: Any,
    uid: str,
    *,
    conversation_ids: Iterable[str] = (),
    expected_generation: int | None = None,
    snapshots: dict | None = None,
    read_budget=None,
    privacy_snapshot: Any = None,
    walk_out: dict | None = None,
    verified_out: set | None = None,
) -> int:
    """Fence a mutation. Admission records the returned generation for replay.

    Check all source IDs and assigned targets inside the mutation transaction:
    choosing another target must never revive a deleted source. Unknown accounts
    are denied even if their deletion marker has disappeared.
    """
    key = privacy_owner_key(uid)

    def live_read(reference):
        return metrics.read_snapshot('batch', reference, transaction=transaction, read_budget=read_budget)

    # Full-row exports and nontransactional preflights always read live. The
    # disabled path retains its exact original read order/counts. Do not poll
    # the older TTL cache's Firestore kill doc or involve Redis in this path.
    negative_on = lever_enabled('privacy_negative_lookup_cache', uid) and transaction is not None and snapshots is None
    negative_shadow = negative_on and lever_enabled('privacy_checks_shadow', uid)
    started = negative_cache.LOOKUPS.clock() if negative_on else None
    if negative_on and privacy_snapshot is None:
        # This per-decision read must enroll the token in the transaction conflict set.
        privacy_snapshot = live_read(client.collection(PRIVACY_COLLECTION).document(key))
    version = token_version(privacy_snapshot) if negative_on else None

    def read(reference, collection=None):
        if negative_on and collection is not None:
            return negative_cache.read(
                client, uid, reference, collection, version, live_read, shadow=negative_shadow, started=started
            )
        return live_read(reference)

    marker = read(client.collection('account_deletions').document(uid), 'account_deletions')
    status = normalize_account_deletion_status(
        marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
    )
    if account_deletion_blocks_access(status):
        raise BatchPrivacyBlocked('account_deleted')
    user = client.collection('users').document(uid)
    snapshot = read(user)
    data = snapshot.to_dict() or {}
    subscription = data.get('subscription')
    metrics.observe_batch_plan(subscription.get('plan') if isinstance(subscription, dict) else None)
    if snapshots is not None:
        snapshots['user'] = data
    if not snapshot.exists:
        raise BatchPrivacyBlocked('account_missing')
    if (
        data.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}
        or data.get('migration_status') is not None
    ):
        raise BatchPrivacyBlocked('data_protection_changed')
    privacy = (
        privacy_snapshot if privacy_snapshot is not None else read(client.collection(PRIVACY_COLLECTION).document(key))
    ).to_dict() or {}
    generation = int(privacy.get('generation', 0))
    if (
        privacy.get('blocked')
        or privacy.get('purging')
        or (expected_generation is not None and expected_generation != generation)
    ):
        raise BatchPrivacyBlocked('privacy_generation_changed')
    # Merge donors converge on shared redirect targets, so charge the budget per
    # distinct document. A walk that reaches a document an earlier walk already
    # passed stops there; cycle detection stays per source and every source is
    # still read and checked itself.
    user_sync_enabled = bool(data.get('private_cloud_sync_enabled', True))
    _verify_conversation_ids(
        client,
        transaction,
        uid,
        set(conversation_ids),
        user_sync_enabled,
        snapshots,
        read,
        walk_out=walk_out,
        verified_out=verified_out,
    )
    return generation


def _verify_conversation_ids(
    client: Any,
    transaction: Any,
    uid: str,
    ids: Iterable[str],
    user_sync_enabled: bool,
    snapshots: dict | None,
    read,
    walk_out: dict | None = None,
    verified_out: set | None = None,
) -> None:
    """Check every source id (and its redirect chain) inside this transaction.

    Shared by the live walk (which passes the user row it just read) and the
    owner memo's new-id verification (which passes the token-certified user
    sync default). Exports rows it reads into ``snapshots`` when given, and
    reports every verified document id (redirect survivors included) into
    ``verified_out`` when given.
    """
    verified: dict[str, bool] = {}  # conversation ID -> document existed
    for source_id in ids:
        conversation_id = source_id
        chain: dict[str, bool] = {}
        redirected = False
        while True:
            if conversation_id in chain:
                raise BatchPrivacyBlocked('conversation_redirect_cycle')
            if conversation_id in verified:
                if redirected and not verified[conversation_id]:
                    raise BatchPrivacyBlocked('conversation_redirect_missing')
                break
            chain[conversation_id] = False
            if len(verified) + len(chain) > 256:
                raise BatchPrivacyBlocked('conversation_fence_budget')
            if not conversation_id or '/' in conversation_id or len(conversation_id.encode()) > 256:
                raise ValueError('bounded conversation document ID required')
            metrics.walked()
            if read(
                client.collection('users').document(uid).collection('deleted_conversations').document(conversation_id),
                'deleted_conversations',
            ).exists:
                raise BatchPrivacyBlocked('conversation_deleted', conversation_id=conversation_id)
            conversation = read(
                client.collection('users').document(uid).collection('conversations').document(conversation_id),
                'conversations',
            )
            # Report each completed conversation read immediately. A later
            # tombstone or privacy refusal in this redirect chain must not hide
            # the prefix from a caller maintaining a wider prepare budget.
            if verified_out is not None:
                verified_out.add(conversation_id)
            row = conversation.to_dict() or {}
            chain[conversation_id] = bool(conversation.exists)
            if snapshots is not None:
                snapshots.setdefault('conversations', {})[conversation_id] = row
            if row.get('record_lane_owner') == 'batch_live_v1' and (
                row.get('uses_custom_stt')
                or not row.get('private_cloud_sync_enabled')
                # Match users.get_user_private_cloud_sync_enabled without an
                # out-of-transaction read: absent means enabled, opt-out wins.
                or not user_sync_enabled
            ):
                raise BatchPrivacyBlocked('recording_privacy_changed')
            if redirected and not conversation.exists:
                raise BatchPrivacyBlocked('conversation_redirect_missing')
            if not row.get('deleted'):
                break
            target = row.get('sync_merged_into')
            if not isinstance(target, str) or not target:
                raise BatchPrivacyBlocked('conversation_deleted', conversation_id=conversation_id)
            # Server-owned redirects are expected. Follow the target in this
            # transaction; user intent above always dominates a redirect.
            conversation_id, redirected = target, True
        verified.update(chain)
    if walk_out is not None:
        walk_out['verified'] = set(verified)
        walk_out['user_sync_enabled'] = user_sync_enabled


# --- lazy memo-token mint (lever bpp_token_mint) -------------------------------------------------
# 86% of batch decisions were memo-ineligible on 2026-11-05 because the owner's privacy document had
# no memo token: tokens were only ever written by authority writes. Minting one makes later decisions
# certifiable by the (exact, in-transaction) token. The mint writes ONLY the token fields through the
# installed write fence, never generation/blocked/purging, and runs after a delay so the authorizing
# transaction that observed the gap commits first; a collision costs that transaction one retry.
MINT_DELAY_SECONDS = 2.0
_MINT_MAX_PENDING = 10_000
_mint_lock = threading.Lock()
_mint_seen: OrderedDict = OrderedDict()
_mint_queue: deque = deque()
_mint_wake = threading.Event()
_mint_thread: list = []


def _mintable(snapshot) -> bool:
    """No usable token, and nothing that must keep the owner ineligible."""
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    if any(data.get(field) for field in ('blocked', 'purging', 'memo_blocked')):
        return False
    return not (isinstance(data.get(TOKEN_FIELD), str) and data.get(SCHEMA_FIELD) == TOKEN_SCHEMA)


def schedule_token_mint(client, reference, uid: str) -> None:
    if not lever_enabled('bpp_token_mint', uid):
        return
    with _mint_lock:
        if reference.path in _mint_seen or len(_mint_queue) >= _MINT_MAX_PENDING:
            return
        # Start (or confirm) the worker BEFORE recording anything: a failed start must
        # leave no queued item or dedupe entry behind, so a later call retries cleanly.
        if not _mint_thread:
            worker = threading.Thread(target=_mint_worker, name='bpp-token-mint', daemon=True)
            try:
                worker.start()
            except Exception:
                # Never fail a privacy decision over an optimization.
                metrics.memo_result('batch', 'mint_error')
                return
            _mint_thread.append(worker)
        _mint_seen[reference.path] = True
        while len(_mint_seen) > 100_000:
            _mint_seen.popitem(last=False)
        _mint_queue.append((time.monotonic() + MINT_DELAY_SECONDS, client, reference))
    _mint_wake.set()


def mint_token(client, reference) -> bool:
    """Transactionally add a token to an owner that has none; True when one was written.

    Re-reads inside the transaction and writes nothing when the owner is blocked,
    purging or memo_blocked, or already carries a token (an authority writer won the
    race). Writes ONLY the token fields as a masked update when the document exists. When
    it never existed, it creates it with the token plus the defaults every reader already
    applies to a missing document (generation 0, not blocked, not purging). The installed write
    fence appends its own rotation in the same commit.
    """
    from google.cloud import firestore

    fields = {TOKEN_FIELD: uuid4().hex, SCHEMA_FIELD: TOKEN_SCHEMA}

    @firestore.transactional
    def mint(transaction) -> bool:
        snapshot = reference.get(transaction=transaction)
        if not _mintable(snapshot):
            return False
        if snapshot.exists:
            transaction.update(reference, fields)
        else:
            # The write fence rejects a privacy-document replacement that omits the
            # authority state; these are the defaults every reader applies to a
            # missing document, so the decision is unchanged.
            transaction.create(reference, {'generation': 0, 'blocked': False, 'purging': False, **fields})
        return True

    return mint(client.transaction())


def _mint_worker() -> None:
    while True:
        with _mint_lock:
            item = _mint_queue.popleft() if _mint_queue else None
        if item is None:
            _mint_wake.wait(5)
            _mint_wake.clear()
            continue
        due, client, reference = item
        delay = due - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        try:
            if mint_token(client, reference):
                metrics.memo_result('batch', 'mint')
        except Exception:
            metrics.memo_result('batch', 'mint_error')


def advance_privacy_generation(client: Any, uid: str, *, blocked: bool) -> int:
    """Invalidate in-flight references before account/protection cleanup."""
    from google.cloud import firestore

    reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))

    @firestore.transactional
    def advance(transaction):
        previous = reference.get(transaction=transaction).to_dict() or {}
        generation = int(previous.get('generation', 0)) + 1
        transaction.set(
            reference, {'generation': generation, 'blocked': blocked or bool(previous.get('blocked')), 'purging': True}
        )
        return generation

    return advance(client.transaction())


def finish_privacy_purge(client: Any, uid: str, generation: int) -> None:
    """Reopen admission only after this exact protection purge converges."""
    from google.cloud import firestore

    reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))

    @firestore.transactional
    def finish(transaction):
        previous = reference.get(transaction=transaction).to_dict() or {}
        if previous.get('generation') == generation:
            transaction.update(reference, {'purging': False})

    finish(client.transaction())


def erased_predecessors(
    client: Any,
    transaction: Any,
    namespace: str,
    owner_key: str,
    predecessor: str | None,
    watermark: str | None,
) -> list[Any] | None:
    """Read an erased ordering chain without skipping unfinished projections.

    Caller TTLs returned receipts only after its cursor advance commits. A
    bounded read budget fails closed; maintenance may advance in smaller steps.
    """
    references = []
    seen = set()
    for _ in range(128):
        if predecessor == watermark:
            return references
        if predecessor is None or predecessor in seen:
            return None
        seen.add(predecessor)
        reference = client.collection(f'{namespace}_results').document(predecessor)
        data = reference.get(transaction=transaction).to_dict() or {}
        if data.get('owner_key') != owner_key or data.get('projection_state') != 'erased':
            return None
        references.append(reference)
        predecessor = data.get('previous_segment_id')
    return references if predecessor == watermark else None
