"""English plans-sheet copy and the recording-hours formula. Clients do not hardcode either."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
import json
from typing import Any

import config.plan_catalog_generated as plan_catalog

# units_per_recorded_hour is provisional. See storefront_copy_v1.json "recording.note":
# evidence/2026-10-12-unit-economics-and-usage.md §1/§3. Replace with shadow-ledger p50 (#21369).
_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


@lru_cache(maxsize=1)
def load_copy() -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parents[1] / 'config/storefront_copy_v1.json').read_text())


def copy_for(locale: str | None) -> dict[str, Any]:
    payload = load_copy()
    locales = payload['locales']
    default = payload['default_locale']
    if not locale:
        return locales[default]
    key = locale.lower()
    if key in locales:
        return locales[key]
    short = key.split('-', 1)[0]
    if short in locales:
        return locales[short]
    return locales[default]


def _recording() -> dict[str, Any]:
    return load_copy()['recording']


def _share() -> Decimal:
    # str() keeps the JSON decimal ("0.85") exact; a binary float would not.
    return Decimal(str(_recording()['recording_share']))


def _units_per_hour() -> Decimal:
    return Decimal(_recording()['units_per_recorded_hour'])


def budget_units_for(plan_id: str) -> int | None:
    """Plan-catalog usage budget when declared, otherwise the presentation rate card."""
    for name in ('USAGE_BUDGET_UNITS', 'PLAN_USAGE_BUDGET_UNITS'):
        declared = getattr(plan_catalog, name, None)
        if isinstance(declared, dict) and plan_id in declared:
            return int(declared[plan_id])
    value = load_copy().get('budget_units', {}).get(plan_id)
    if type(value) is int:
        return value
    return None


def floor_to_nice(value: Decimal) -> int:
    """<30 → nearest 5; <300 → nearest 10 down; else nearest 100 down."""
    if value < 30:
        steps = (value / Decimal(5)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return int(steps * 5)
    if value < 300:
        return int(value // 10 * 10)
    return int(value // 100 * 100)


def recording_hours(plan_id: str) -> int:
    """floor_to_nice(budget_units × recording_share / units_per_recorded_hour). Free is fixed."""
    if plan_id == 'basic':
        return int(_recording()['free_hours'])
    units = budget_units_for(plan_id)
    if units is None:
        return 0
    raw = Decimal(units) * _share() / _units_per_hour()
    return floor_to_nice(raw)


def per_day_count(monthly_hours: int) -> int:
    return int((Decimal(monthly_hours) / Decimal(30)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def per_day_phrase(monthly_hours: int, locale: str | None = None) -> str:
    """monthly ÷ 30. <6 → about N hours a day; 6–16 → all day; >16 → more than one device."""
    phrases = copy_for(locale)['per_day']
    daily = Decimal(monthly_hours) / Decimal(30)
    if daily < 6:
        return phrases['under_6'].format(n=per_day_count(monthly_hours))
    if daily <= 16:
        return phrases['all_day']
    return phrases['multi_device']


def hours_line(plan_id: str, locale: str | None = None) -> str:
    templates = copy_for(locale)['hours_lines']
    template = templates.get(plan_id)
    if not template:
        return ''
    hours = recording_hours(plan_id)
    return template.format(hours=f'{hours:,}', per_day=per_day_count(hours))


def recording_hours_left(plan_id: str, percent: float) -> int:
    """Remaining wall-clock hours.

    Paid plans reuse the recording-hours definition on the unused units
    (remaining × recording_share / units_per_recorded_hour, then floor_to_nice).
    Free has no unit budget; scale its fixed hours by the unused share.
    """
    fraction = (Decimal(100) - Decimal(str(percent))) / Decimal(100)
    if plan_id == 'basic':
        remaining = Decimal(recording_hours('basic')) * fraction
        return int(remaining.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    units = budget_units_for(plan_id)
    if units is None:
        return 0
    remaining_units = Decimal(units) * fraction
    return floor_to_nice(remaining_units * _share() / _units_per_hour())


def bullets(plan_id: str, trigger: str | None, locale: str | None = None) -> list[str]:
    text = copy_for(locale)
    items = list(text['bullets'].get(plan_id, []))
    focus = text['bullet_focus']
    if trigger == 'mcp_daily_cap':
        marker = focus['mcp_marker']
        match = next((item for item in items if marker in item), None)
        if match is not None:
            items.remove(match)
            items.insert(0, match)
        return items
    if trigger in {'proactive_agent', 'screen_context'} and plan_id == 'operator':
        target = focus[trigger]
        if target in items:
            items.remove(target)
            items.insert(0, target)
    return items


def header(
    *,
    legacy: bool,
    trigger: str | None,
    percent: float | None,
    mcp_daily_cap: int | None,
    locale: str | None = None,
) -> str:
    headers = copy_for(locale)['headers']
    if legacy:
        return headers['legacy']
    if trigger == 'proactive_agent':
        return headers['proactive_agent']
    if trigger == 'screen_context':
        return headers['screen_context']
    if trigger == 'mcp_daily_cap':
        if mcp_daily_cap is None:
            return headers['default']
        return headers['mcp_daily_cap'].format(n=f'{mcp_daily_cap:,}')
    if trigger == 'usage_budget':
        if percent is not None and percent >= 100:
            return headers['budget_100']
        return headers['budget_80']
    return headers['default']


def format_date(timestamp: int) -> str:
    moment = datetime.fromtimestamp(timestamp, timezone.utc)
    return f'{_MONTHS[moment.month - 1]} {moment.day}'


def reset_parts(reset_at: int) -> tuple[str, str]:
    moment = datetime.fromtimestamp(reset_at, timezone.utc)
    reset_label = f'resets {format_date(reset_at)}'
    period = moment
    if moment.day == 1 and moment.hour == 0 and moment.minute == 0 and moment.second == 0:
        period = moment - timedelta(days=1)
    return f'{period.year:04d}-{period.month:02d}', reset_label


def money(amount_minor: int) -> str:
    dollars = (Decimal(amount_minor) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return f'${dollars:.2f}'


def months_free(monthly_minor: int, annual_minor: int) -> int | None:
    """12 − annual/monthly, only when the live prices give at least one month."""
    if monthly_minor <= 0:
        return None
    value = Decimal(12) - (Decimal(annual_minor) / Decimal(monthly_minor))
    if value < 1:
        return None
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def plan_name(plan_id: str, ladder: dict[str, Any]) -> str:
    for tier in ladder.get('tiers', []):
        if tier.get('plan_id') == plan_id and isinstance(tier.get('display_name'), str):
            return tier['display_name']
    override = load_copy().get('plan_names', {}).get(plan_id)
    if isinstance(override, str):
        return override
    return plan_id


def current_line(
    *,
    plan_id: str,
    plan_name_text: str,
    amount_minor: int | None,
    interval: str | None,
    period_end: int | None,
    cancel: bool,
    legacy: bool,
    locale: str | None = None,
) -> tuple[str, str | None]:
    text = copy_for(locale)['current']
    note = text['legacy_note'] if legacy else None
    if plan_id == 'basic':
        return text['free'], note
    date = format_date(period_end) if type(period_end) is int and period_end > 0 else None
    if cancel and date:
        return text['cancel'].format(plan=plan_name_text, date=date), note
    if amount_minor is not None and interval in {'month', 'year'}:
        period = 'mo' if interval == 'month' else 'yr'
        price = money(amount_minor)
        if date:
            return text['paid'].format(plan=plan_name_text, price=price, period=period, date=date), note
        return text['paid_no_date'].format(plan=plan_name_text, price=price, period=period), note
    return text['name_only'].format(plan=plan_name_text), note


def cta_label(*, action: str, tier_plan: str, current_plan: str, locale: str | None = None) -> str | None:
    if action != 'checkout':
        return None
    labels = copy_for(locale)['cta']
    if tier_plan == current_plan:
        return labels['resubscribe']
    if tier_plan == 'plus':
        return labels['get_plus']
    if tier_plan == 'operator':
        return labels['get_pro'] if current_plan == 'basic' else labels['upgrade_pro']
    if tier_plan == 'architect':
        return labels['get_architect'] if current_plan == 'basic' else labels['upgrade_architect']
    return None


def render_price(
    *,
    price_id: str | None,
    interval: str,
    amount_minor: int,
    currency: str,
    monthly_minor: int | None,
    locale: str | None = None,
) -> dict[str, Any]:
    text = copy_for(locale)['prices']
    if interval == 'year':
        equivalent = (Decimal(amount_minor) / Decimal(100) / Decimal(12)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        headline = text['headline_year'].format(amount=f'${equivalent:.2f}')
        free = months_free(monthly_minor, amount_minor) if monthly_minor else None
        annual = money(amount_minor)
        if free is not None:
            subline = text['subline_year'].format(amount=annual, n=free)
        else:
            subline = text['subline_year_no_free'].format(amount=annual)
            free = None
        return {
            'price_id': price_id,
            'interval': 'year',
            'amount_minor': amount_minor,
            'currency': currency,
            'headline': headline,
            'subline': subline,
            'renewal_line': text['renewal_year'],
            'months_free': free,
        }
    return {
        'price_id': price_id,
        'interval': 'month',
        'amount_minor': amount_minor,
        'currency': currency,
        'headline': text['headline_month'].format(amount=money(amount_minor)),
        'subline': None,
        'renewal_line': text['renewal_month'] if amount_minor else None,
        'months_free': None,
    }


def yearly_toggle_label(months: int | None, locale: str | None = None) -> str | None:
    if months is None or months < 1:
        return None
    return copy_for(locale)['prices']['toggle'].format(n=months)


def _wire_percent(percent: float) -> int:
    return int(Decimal(str(percent)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def present_usage(
    *,
    plan_id: str,
    kind: str,
    percent: float | None,
    reset_at: int | None,
    locale: str | None = None,
) -> dict[str, Any]:
    text = copy_for(locale)
    payload: dict[str, Any] = {
        'kind': kind,
        'percent': None,
        'period_id': None,
        'reset_label': None,
        'meter_line': None,
        'nudge_line': None,
        'pro_gates': list(text['pro_gates']),
    }
    if kind == 'unavailable' or percent is None:
        return payload
    shown = _wire_percent(percent)
    payload['percent'] = shown
    if type(reset_at) is int and reset_at > 0:
        period_id, reset_label = reset_parts(reset_at)
        payload['period_id'] = period_id
        payload['reset_label'] = reset_label
    if kind == 'usage_budget' and payload['reset_label']:
        left = recording_hours_left(plan_id, shown)
        payload['meter_line'] = text['meter']['line'].format(
            percent=shown, hours=f'{left:,}', reset=payload['reset_label']
        )
        if 80 <= shown < 100:
            payload['nudge_line'] = text['meter']['nudge_80'].format(reset=payload['reset_label'])
    return payload
