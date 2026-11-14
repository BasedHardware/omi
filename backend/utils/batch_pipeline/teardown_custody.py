"""Flight-teardown custody: the four best-effort lease exits report on honest channels.

A GPU flight ends in four fenced store calls, each with the lease window
itself as its durable fallback: the stop refund (claimed behind a
sibling's chain when SIGTERM or a fatal GPU error arrived), the
GPU-restart refund (``FatalGpuError``), the skipped refund (a cancelled or
lost decode's siblings) and the finished-lease release. A contention loss
on any of them is that fallback engaging -- the same "losing the race is
not a fault" doctrine the pull lane (``event=batch_pull outcome=backoff``,
INFO), the deferred publication-drain lane
(``event=batch_merge_drain outcome=maintenance_backstop``, WARNING) and
the publication re-strike lane already ship. All four catch sites booked
every exception on the ERROR fault channel, so one store storm reached the
production error sensor once more per refunded or released lease per
flight teardown, on top of the retry engine's single
``firestore_transaction_contention outcome=exhausted`` storm signal.

The contract, owned here so every teardown site reads one table:

- ``TEARDOWN_SITES`` is the closed site table. Each row names the
  historical event prefix and outcome token the site has always rendered,
  the honest channel a closed contention loss reports on (WARNING for a
  lost refund whose unit waits out the lease before the fenced recovery
  sweep re-queues it, INFO for a finished lease whose release loss only
  holds the fence past work that is already done), and the site's total
  attempt budget: the two live refund sites replay, the GPU-restart
  refund and the release are single-attempt because their flight is
  already ending.
- ``teardown_loss_is_contention`` is the closed contention class --
  ``FirestoreContentionExhausted`` including the Postgres job-store
  subclass, plus any exception whose cause chain classifies as atomic
  transaction contention: exactly the class the publication re-strike
  lane replays under. Everything else -- a revoked lease, an admission
  refusal, a real write failure -- is the lease window's decision, not a
  lost race, and keeps the historical ERROR line byte-for-byte.
- ``report_teardown_custody_loss`` books one loss on its row's channel,
  carrying the losing store label, the sanitized attempt and the storm
  window the damper had armed (``retry_after_ms``, ``0`` when unstamped).
  The exception name is the only payload any line carries.
- ``replay_teardown_refund`` runs one site's fenced call to its budget:
  a closed contention loss replays on ``teardown_replay_delay``'s
  doubling ladder with every wait raised to the stamped storm window
  (``teardown_storm_after``, clamped at the store damper's own 4.0s cap),
  so the replay lands after the armed window instead of colliding inside
  it. The replays stay silent, so a storm that converges logs nothing;
  past the budget the loss is reported once and the lease-expiry backstop
  owns the unit exactly as before. The whole replay runs synchronously on
  the db-executor thread the fenced call already occupies -- the same
  blocking-sleep precedent the re-strike lane's entry consult set.

Durable state, custody, metrics and the fallbacks are unchanged; only the
report channel, the report fields and a lost refund's wait moved.

Failure-Class: FC-flight-custody-contention-losses-booked-as-production-faults
"""

import logging
import math
import time
from dataclasses import dataclass

from database.batch_pipeline_transaction_labels import require_operation_label
from database.firestore_transaction_retry import FirestoreContentionExhausted, is_transaction_contention

# Total attempts per refund: the first fenced call plus two bounded
# replays. Report-only rows carry a budget of one and never sleep.
TEARDOWN_REPLAY_ATTEMPTS = 3
TEARDOWN_REPLAY_BASE_SECONDS = 0.25
TEARDOWN_REPLAY_MAX_SECONDS = 2.0
# The storm term's own ceiling: the store's damper caps an armed window at
# 4.0s (``FirestoreStore.STORM_DAMPER_CAP_SECONDS``), so a window deeper
# than the ladder's 2.0s cap must still be clearable. ``utils`` stays
# independent of ``database`` internals by pinning the literal here, the
# same way the publication re-strike lane pins it.
TEARDOWN_REPLAY_STORM_MAX_SECONDS = 4.0


@dataclass(frozen=True)
class LeaseTeardownSite:
    """One flight-teardown custody site: its historical line and its channel."""

    key: str
    event: str
    outcome: str
    contention_level: int
    attempts: int


TEARDOWN_SITES = {
    'stop_refund': LeaseTeardownSite(
        key='stop_refund',
        event='event=batch_flight',
        outcome='lease_recovery',
        contention_level=logging.WARNING,
        attempts=TEARDOWN_REPLAY_ATTEMPTS,
    ),
    'gpu_restart_refund': LeaseTeardownSite(
        key='gpu_restart_refund',
        event='event=batch_gpu_restart',
        outcome='lease_recovery',
        contention_level=logging.WARNING,
        attempts=1,
    ),
    'skipped_refund': LeaseTeardownSite(
        key='skipped_refund',
        event='event=batch_flight',
        outcome='lease_recovery',
        contention_level=logging.WARNING,
        attempts=TEARDOWN_REPLAY_ATTEMPTS,
    ),
    'release': LeaseTeardownSite(
        key='release',
        event='event=batch_flight',
        outcome='lease_release',
        contention_level=logging.INFO,
        attempts=1,
    ),
}


def contention_operation_field(error: BaseException) -> str:
    """The losing store label stamped on a contention exhaustion, log-ready.

    ``FirestoreStore.run`` stamps the label that burned the budget onto
    the raised chain's ``operation`` (the same ride-along contract as
    ``retry_after``), so a caller reporting the loss names the exact
    operation that lost instead of an anonymous chain. Anything the label
    validator refuses -- a foreign exception, a missing or hostile
    attribute shape -- reports nothing rather than interpolating
    unvalidated text into a log line. Never raises.

    Home: every contention reporter (the pull lane, the drain backstop,
    the teardown custody family) reads the same stamp the same way from
    here; ``scheduler`` re-exports the name its existing readers import.
    """
    label = getattr(error, 'operation', None)
    if not isinstance(label, str):
        return ''
    try:
        require_operation_label(label)
    except Exception:
        return ''
    return f' operation={label}'


def teardown_loss_is_contention(error: BaseException) -> bool:
    """True for exactly the bounded contention budget a teardown may absorb.

    ``FirestoreContentionExhausted`` -- including the Postgres job-store
    subclass -- and any exception whose cause chain classifies as atomic
    transaction contention: the same closed class the publication
    re-strike lane replays under. Everything else (a revoked lease, an
    admission refusal, a real write failure) is the lease window's
    decision, not a lost race, and keeps its fault line. Never raises on
    hostile input.
    """
    return isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)


def teardown_storm_after(error: BaseException | None) -> float:
    """The measured storm window a teardown replay must land after.

    ``FirestoreStore.run`` stamps the window its storm damper actually
    armed for the exhausted label onto the raised chain's ``retry_after``;
    a replay that ignores it fires into the window's interior, where the
    entry consult parks the db-executor thread on the residual sleep and a
    chain that still loses re-arms the storm the replay just re-entered.
    Only a positive finite number counts; a foreign exception, an
    exhaustion raised with no damper in scope, and hostile or malformed
    input all return ``0.0`` (the caller keeps its documented ladder).
    Only a chain exhaustion carries a stamp in production -- a
    cause-chain contention loss (a bare ``Aborted``) was raised outside a
    labeled damper run and keeps the ladder -- so the read narrows to the
    exhaustion class before touching the attribute. The clamp is the
    store damper's own window cap, so the deepest real window stays
    clearable while the family's horizon stays bounded and documented.
    Never raises.
    """
    stamped: object = None
    if isinstance(error, FirestoreContentionExhausted):
        try:
            stamped = error.retry_after
        except Exception:
            stamped = None
    if isinstance(stamped, bool) or not isinstance(stamped, (int, float)):
        return 0.0
    value = float(stamped)
    if not math.isfinite(value) or value <= 0.0:
        return 0.0
    return min(value, TEARDOWN_REPLAY_STORM_MAX_SECONDS)


def teardown_replay_delay(replay_index: object) -> float:
    """One ladder step of the bounded teardown replay schedule, in seconds.

    ``min(max, base * 2 ** (index - 1))`` -- 0.25s before the first
    replay, 0.5s before the second -- so the schedule spends its first
    steps inside the seconds-wide contention wave and the whole budget
    stays an order of magnitude under the 120-second lease the fence
    still honors when the budget ends. A hostile index (a non-int, a
    bool, below 1) collapses to the first step, the ``object``-annotation
    convention the pull lane's ``pull_backoff_delay`` set; never raises.
    """
    if not isinstance(replay_index, int) or isinstance(replay_index, bool) or replay_index < 1:
        index = 1
    else:
        index = replay_index
    return min(TEARDOWN_REPLAY_MAX_SECONDS, TEARDOWN_REPLAY_BASE_SECONDS * 2 ** (index - 1))


def _log_attempt(attempt: object) -> int:
    """The attempt count a custody line renders, sanitized for ``%d``."""
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        return 1
    return attempt


def report_teardown_custody_loss(logger, *, site: LeaseTeardownSite, error: BaseException, attempt: object = 1) -> None:
    """Book one flight-teardown custody loss on its site's honest channel.

    The closed contention class reports at the level the site's row names
    -- INFO for a finished lease's release, WARNING for a lost refund --
    carrying the losing store label, the sanitized attempt and the storm
    window the damper had armed. Everything else keeps the historical
    fault line byte-for-byte: same logger, same event and outcome tokens,
    same exception-name payload, nothing added. Never raises.
    """
    error_type = type(error).__name__
    if teardown_loss_is_contention(error):
        logger.log(
            site.contention_level,
            '%s outcome=%s exception_type=%s%s attempt=%d retry_after_ms=%d',
            site.event,
            site.outcome,
            error_type,
            contention_operation_field(error),
            _log_attempt(attempt),
            round(teardown_storm_after(error) * 1000),
        )
        return
    logger.error('%s outcome=%s exception_type=%s', site.event, site.outcome, error_type)


def replay_teardown_refund(call, *, site: LeaseTeardownSite, logger, sleep=time.sleep) -> int:
    """Run one teardown site's fenced call to its row's attempt budget.

    ``call`` is a zero-argument callable performing one fenced attempt
    (it raises on a loss). A closed contention loss
    (``teardown_loss_is_contention``) replays on
    ``teardown_replay_delay``'s ladder with every wait raised to
    ``teardown_storm_after``'s measured window, so the replay lands after
    the damper's armed window instead of colliding inside it; the waits
    run on the db-executor thread the fenced call already occupies, and
    the replays themselves stay silent so a storm that converges logs
    nothing. Past the budget the loss is reported once on the row's
    honest channel and the lease-expiry backstop owns the unit exactly as
    before. A non-contention fault reports on the historical fault line
    immediately without replaying -- re-striking a real failure would
    only replay the same refusal. Returns the attempts spent. Rows with a
    budget of one (the GPU-restart refund whose process is ending, the
    finished-lease release whose flight is unwinding) make this the
    single-attempt report path. ``KeyboardInterrupt``/``SystemExit`` and
    ``asyncio.CancelledError`` are ``BaseException``: a teardown never
    swallows its own shutdown.
    """
    attempts = 0
    while attempts < site.attempts:
        attempts += 1
        try:
            call()
            return attempts
        except Exception as error:
            if attempts >= site.attempts or not teardown_loss_is_contention(error):
                report_teardown_custody_loss(logger, site=site, error=error, attempt=attempts)
                return attempts
            sleep(max(teardown_replay_delay(attempts), teardown_storm_after(error)))
    return attempts
