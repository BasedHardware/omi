#!/usr/bin/env python3
"""Attribute chat-agent LLM spend across the gateway accounting ledger.

The ledger already records every billable component of an Anthropic Messages
attempt (cached reads, uncached input, cache writes and their TTL, output), but
nothing reads it back per feature. Cost work on the chat agent otherwise starts
from guesses about which component dominates, and the two candidate levers pull
in opposite directions depending on the answer: a low cache-read share means the
request prefix is being rewritten rather than reused, while a high output share
means generation settings matter more than prefix layout.

Aggregation is pure and takes ledger rows as plain mappings, so the arithmetic is
testable without Firestore. Only the fetch step touches the database.

Reads one day per query using two equality filters, which Firestore serves from
single-field indexes — no composite index and no schema change. An optional
user_uid equality filter is served the same way, so scoping to one user still
needs no composite index.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

ATTEMPTS_COLLECTION = 'llm_gateway_attempts'
DEFAULT_FEATURE = 'chat_agent'
DEFAULT_DAYS = 7
MICRO_USD_PER_USD = 1_000_000
TOKENS_PER_MILLION = 1_000_000

# Cache writes are billed at a TTL-dependent rate, so the 5-minute, 30-minute,
# and 1-hour components are never collapsed into one number.
TTL_FIVE_MINUTES = '5m'
TTL_THIRTY_MINUTES = '30m'
TTL_ONE_HOUR = '1h'


@dataclass
class Rates:
    """Per-million-token micro-USD rates for one provider model."""

    rate_card_id: str
    input_micro_usd: int
    cached_input_micro_usd: int
    output_micro_usd: int
    cache_write_micro_usd: int
    cache_write_1h_micro_usd: int


@dataclass
class Totals:
    """Accumulated ledger quantities for one feature over a date range."""

    attempts: int = 0
    priced_attempts: int = 0
    cached_input_tokens: int = 0
    uncached_input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_30m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_write_untagged_tokens: int = 0
    output_tokens: int = 0
    ledger_cost_micro_usd: int = 0
    attempts_with_cache_read: int = 0
    attempts_with_cache_write: int = 0
    cache_status: Counter[str] = field(default_factory=Counter)
    outcome: Counter[str] = field(default_factory=Counter)
    models: Counter[str] = field(default_factory=Counter)
    days: set[str] = field(default_factory=set)


def _int_field(row: Mapping[str, Any], key: str) -> int:
    """Read a non-negative integer, treating absent or malformed values as zero.

    A ledger row is written best-effort from provider usage that may omit
    fields; a partially reported attempt must still contribute the components it
    did report rather than abort the whole report.
    """
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _str_field(row: Mapping[str, Any], key: str, default: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) and value else default


def accumulate(totals: Totals, row: Mapping[str, Any]) -> None:
    """Fold one ledger row into ``totals``."""
    totals.attempts += 1
    totals.days.add(_str_field(row, 'date', 'unknown'))
    totals.cache_status[_str_field(row, 'cache_status', 'not_reported')] += 1
    totals.outcome[_str_field(row, 'outcome', 'unknown')] += 1
    totals.models[_str_field(row, 'actual_model_version', _str_field(row, 'configured_model', 'unknown'))] += 1

    cached = _int_field(row, 'cached_input_tokens')
    cache_write = _int_field(row, 'cache_write_tokens')
    totals.cached_input_tokens += cached
    totals.uncached_input_tokens += _int_field(row, 'uncached_input_tokens')
    totals.output_tokens += _int_field(row, 'output_tokens')
    if cached:
        totals.attempts_with_cache_read += 1
    if cache_write:
        totals.attempts_with_cache_write += 1

    ttl = _str_field(row, 'cache_write_ttl', '')
    if ttl == TTL_ONE_HOUR:
        totals.cache_write_1h_tokens += cache_write
    elif ttl == TTL_THIRTY_MINUTES:
        totals.cache_write_30m_tokens += cache_write
    elif ttl == TTL_FIVE_MINUTES:
        totals.cache_write_5m_tokens += cache_write
    else:
        # 'mixed', absent, or an unrecognized TTL. Priced at the 1h rate below so
        # the estimate stays conservative, but reported separately because a
        # non-zero value here means the request's breakpoints disagree.
        totals.cache_write_untagged_tokens += cache_write

    cost = row.get('estimated_cost_micro_usd')
    if isinstance(cost, int) and not isinstance(cost, bool) and cost >= 0:
        totals.ledger_cost_micro_usd += cost
        totals.priced_attempts += 1


def _cost(tokens: int, micro_usd_per_million: int) -> int:
    return round(tokens * micro_usd_per_million / TOKENS_PER_MILLION)


@dataclass(frozen=True)
class Component:
    name: str
    tokens: int
    cost_micro_usd: int


def cost_components(totals: Totals, rates: Rates) -> list[Component]:
    """Split spend into the components a change can actually move."""
    untagged_and_1h = totals.cache_write_1h_tokens + totals.cache_write_untagged_tokens
    return [
        Component(
            'cached input (read)',
            totals.cached_input_tokens,
            _cost(totals.cached_input_tokens, rates.cached_input_micro_usd),
        ),
        Component(
            'uncached input', totals.uncached_input_tokens, _cost(totals.uncached_input_tokens, rates.input_micro_usd)
        ),
        Component(
            'cache write 30m',
            totals.cache_write_30m_tokens,
            _cost(totals.cache_write_30m_tokens, rates.cache_write_micro_usd),
        ),
        Component('cache write 1h', untagged_and_1h, _cost(untagged_and_1h, rates.cache_write_1h_micro_usd)),
        Component(
            'cache write 5m',
            totals.cache_write_5m_tokens,
            _cost(totals.cache_write_5m_tokens, rates.cache_write_micro_usd),
        ),
        Component('output', totals.output_tokens, _cost(totals.output_tokens, rates.output_micro_usd)),
    ]


def write_read_ratio(totals: Totals) -> float | None:
    """Cache-write tokens billed per cache-read token served.

    The prefix layout is working when this is well below 1: each written prefix
    is read back many times. A ratio near or above 1 means prefixes are being
    written about as often as they are reused, which is what a per-user (rather
    than shared) cache breakpoint produces.
    """
    reads = totals.cached_input_tokens
    if reads <= 0:
        return None
    writes = (
        totals.cache_write_1h_tokens
        + totals.cache_write_30m_tokens
        + totals.cache_write_5m_tokens
        + totals.cache_write_untagged_tokens
    )
    return writes / reads


def load_rates(model: str, rate_card_path: Path, *, rate_card_id: str = '') -> Rates:
    """Read rates from the gateway rate card.

    ``rate_card_id`` selects the exact card an attempt was priced on and is preferred when the
    ledger recorded one; ``model`` is the fallback for rows predating that field, and picks
    whichever card currently carries the name.

    Raises ``LookupError`` when nothing matches, because reporting an unpriced
    total silently understates spend.
    """
    import yaml

    raw = yaml.safe_load(rate_card_path.read_text(encoding='utf-8')) or {}
    cards = raw.get('rate_cards')
    if not isinstance(cards, list):
        raise LookupError(f'{rate_card_path} has no rate_cards list')
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        if rate_card_id:
            if card.get('rate_card_id') != rate_card_id:
                continue
        elif card.get('model') != model:
            continue
        input_rate = int(card.get('input_micro_usd_per_million', 0))
        return Rates(
            rate_card_id=str(card.get('rate_card_id', model)),
            input_micro_usd=input_rate,
            cached_input_micro_usd=int(card.get('cached_input_micro_usd_per_million', 0)),
            output_micro_usd=int(card.get('output_micro_usd_per_million', 0)),
            # Anthropic bills a 5-minute write at 1.25x input and a 1-hour write
            # at 2x. Fall back to those multiples so a card that predates the
            # explicit fields still prices writes instead of dropping them.
            cache_write_micro_usd=int(card.get('cache_write_micro_usd_per_million', round(input_rate * 1.25))),
            cache_write_1h_micro_usd=int(card.get('cache_write_1h_micro_usd_per_million', input_rate * 2)),
        )
    wanted = f'rate card id {rate_card_id!r}' if rate_card_id else f'model {model!r}'
    raise LookupError(f'no rate card for {wanted} in {rate_card_path}')


def date_range(end: date, days: int) -> list[str]:
    """Return ``days`` ISO dates ending at (and including) ``end``."""
    if days < 1:
        raise ValueError('days must be at least 1')
    return [(end - timedelta(days=offset)).isoformat() for offset in reversed(range(days))]


def fetch_rows(
    client: Any, feature: str, days: Sequence[str], *, uid: str | None = None
) -> Iterator[Mapping[str, Any]]:
    """Stream ledger rows for one feature, one day per query.

    Two equality filters are served by single-field indexes, so this needs no
    composite index. An optional user_uid equality filter is served the same way,
    so scoping to one user still needs no composite index. Days are queried
    separately to keep each result set bounded and to let a partial run still
    report the days it did read.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    for day in days:
        query = (
            client.collection(ATTEMPTS_COLLECTION)
            .where(filter=FieldFilter('feature', '==', feature))
            .where(filter=FieldFilter('date', '==', day))
        )
        if uid is not None:
            query = query.where(filter=FieldFilter('user_uid', '==', uid))
        for snapshot in query.stream():
            row = snapshot.to_dict()
            if isinstance(row, Mapping):
                yield row


def _pct(part: float, whole: float) -> str:
    return f'{(100 * part / whole):5.1f}%' if whole else '    —'


def _usd(micro_usd: int) -> str:
    return f'${micro_usd / MICRO_USD_PER_USD:,.2f}'


def render(totals: Totals, rates: Rates, feature: str, *, uid: str | None = None) -> str:
    """Render the report as plain text."""
    scope = f'scope: uid={uid}' if uid is not None else None
    if totals.attempts == 0:
        message = f'No {feature} attempts found. Check the date range and that accounting is enabled.'
        return f'{scope}\n{message}' if scope is not None else message

    lines: list[str] = []
    span = f'{min(totals.days)}..{max(totals.days)}' if totals.days else 'unknown'
    lines.append(f'{feature} spend composition — {span} ({len(totals.days)} day(s))')
    if scope is not None:
        lines.append(scope)
    lines.append(f'rate card: {rates.rate_card_id}')
    lines.append('')
    lines.append(f'attempts: {totals.attempts:,}')
    for name, count in totals.outcome.most_common():
        lines.append(f'  outcome {name:<24} {count:>10,}  {_pct(count, totals.attempts)}')
    lines.append('')
    lines.append('served models')
    for name, count in totals.models.most_common():
        lines.append(f'  {name:<32} {count:>10,}  {_pct(count, totals.attempts)}')

    components = cost_components(totals, rates)
    modeled_total = sum(component.cost_micro_usd for component in components)
    lines.append('')
    lines.append(f'{"component":<24}{"tokens":>16}{"per attempt":>14}{"cost":>14}{"share":>9}')
    for component in components:
        per_attempt = component.tokens / totals.attempts
        lines.append(
            f'  {component.name:<22}{component.tokens:>16,}{per_attempt:>14,.0f}'
            f'{_usd(component.cost_micro_usd):>14}{_pct(component.cost_micro_usd, modeled_total):>9}'
        )
    lines.append(f'  {"total (modeled)":<22}{"":>16}{"":>14}{_usd(modeled_total):>14}')

    lines.append('')
    lines.append(
        f'ledger total (estimated_cost_micro_usd over {totals.priced_attempts:,} priced attempts): '
        f'{_usd(totals.ledger_cost_micro_usd)}'
    )
    unpriced = totals.attempts - totals.priced_attempts
    if unpriced:
        lines.append(f'  {unpriced:,} attempt(s) carried no cost estimate and are excluded from the ledger total.')

    lines.append('')
    lines.append('cache status')
    for name, count in totals.cache_status.most_common():
        lines.append(f'  {name:<32} {count:>10,}  {_pct(count, totals.attempts)}')

    ratio = write_read_ratio(totals)
    lines.append('')
    if ratio is None:
        lines.append('write:read ratio: no cache reads observed — the prefix is never being reused.')
    else:
        lines.append(f'write:read ratio: {ratio:.2f} cache-write tokens billed per cache-read token served')
    lines.append(
        f'  attempts writing cache: {totals.attempts_with_cache_write:,} '
        f'({_pct(totals.attempts_with_cache_write, totals.attempts).strip()})   '
        f'reading cache: {totals.attempts_with_cache_read:,} '
        f'({_pct(totals.attempts_with_cache_read, totals.attempts).strip()})'
    )
    if totals.cache_write_untagged_tokens:
        lines.append(
            f'  {totals.cache_write_untagged_tokens:,} cache-write token(s) had no single TTL '
            "('mixed', absent, or unrecognized); priced at the 1h rate."
        )
    return '\n'.join(lines)


def build_totals(rows: Iterable[Mapping[str, Any]]) -> Totals:
    totals = Totals()
    for row in rows:
        accumulate(totals, row)
    return totals


def row_model(row: Mapping[str, Any]) -> str:
    """The model an attempt was actually billed as."""
    return _str_field(row, 'actual_model_version', _str_field(row, 'configured_model', 'unknown'))


def row_pricing_basis(row: Mapping[str, Any]) -> tuple[str, str]:
    """The exact basis an attempt was priced on: ``(model, rate_card_id)``.

    The card id is carried because a model's pricing can be revised (an intro rate expiring, for
    instance) while the model name stays the same, so the name alone does not identify the rates
    that were in force. Rows written before the field existed carry an empty id and fall back to
    a lookup by model.
    """
    return row_model(row), _str_field(row, 'rate_card_id', '')


def build_totals_by_pricing_basis(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], Totals]:
    """Group the range by the basis each attempt was actually priced on.

    One rate card cannot price a range that spans a routing change or a price revision, and
    `chat_agent` has already moved provider once. Pricing every attempt at whatever is current
    today would silently misattribute every component for every attempt served before the
    switch — so the range is split and each group is priced on its own recorded basis.
    """
    grouped: dict[tuple[str, str], Totals] = {}
    for row in rows:
        accumulate(grouped.setdefault(row_pricing_basis(row), Totals()), row)
    return grouped


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--feature', default=DEFAULT_FEATURE, help=f'ledger feature name (default: {DEFAULT_FEATURE})')
    parser.add_argument(
        '--days', type=int, default=DEFAULT_DAYS, help=f'days to read, ending at --end (default: {DEFAULT_DAYS})'
    )
    parser.add_argument('--end', default=None, help='last day to read, YYYY-MM-DD (default: today, UTC)')
    parser.add_argument('--uid', default=None, help='ledger user_uid to scope the report to one user')
    parser.add_argument(
        '--model', default=None, help='rate-card model (default: resolved from the gateway route override)'
    )
    return parser.parse_args(argv)


def resolve_model(explicit: str | None, feature: str) -> str:
    """Prefer the operator-supplied model, else the feature's served route.

    The route override is the model actually billed; ``model_config`` records the
    pre-override choice and would price the report against a model that never ran.
    """
    if explicit:
        return explicit
    import yaml

    overrides_path = BACKEND_ROOT / 'llm_gateway' / 'config' / 'generated_route_overrides.yaml'
    raw = yaml.safe_load(overrides_path.read_text(encoding='utf-8')) or {}
    for override in raw.get('generated_route_overrides') or []:
        if isinstance(override, Mapping) and override.get('feature') == feature:
            primary = override.get('primary')
            if isinstance(primary, Mapping) and isinstance(primary.get('model'), str):
                return primary['model']
    raise LookupError(f'no route override for feature {feature!r}; pass --model explicitly')


def main(argv: Sequence[str] | None = None, *, get_client: Callable[[], Any] | None = None) -> int:
    import yaml

    args = parse_args(argv)
    card_path = BACKEND_ROOT / 'llm_gateway' / 'config' / 'cost_rate_cards.yaml'
    try:
        # The ledger's ``date`` field is UTC, so the default window has to be too — a local
        # ``today()`` east or west of UTC asks for a day the range was never meant to cover.
        end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()
        days = date_range(end, args.days)
        # ``--model`` prices the whole range from one card; without it each pricing basis found
        # in the range is priced on its own.
        forced_rates = load_rates(resolve_model(args.model, args.feature), card_path) if args.model else None
    except (ValueError, LookupError, OSError, yaml.YAMLError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2

    if get_client is None:
        from database._client import get_firestore_client

        get_client = get_firestore_client

    grouped = build_totals_by_pricing_basis(fetch_rows(get_client(), args.feature, days, uid=args.uid))
    if not grouped:
        print(render(Totals(), Rates('none', 0, 0, 0, 0, 0), args.feature, uid=args.uid))
        return 0

    for basis in sorted(grouped, key=lambda key: -grouped[key].attempts):
        model, rate_card_id = basis
        if forced_rates is not None:
            rates = forced_rates
        else:
            try:
                rates = load_rates(model, card_path, rate_card_id=rate_card_id)
            except (LookupError, OSError, yaml.YAMLError) as error:
                # One unpriceable basis must not cost the operator the rest of the report.
                print(f'{args.feature} — {model}: not priced ({error})\n', file=sys.stderr)
                continue
        print(render(grouped[basis], rates, args.feature, uid=args.uid))
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
