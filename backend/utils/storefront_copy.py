"""Plans-sheet copy and the recording-hours formula. Clients do not hardcode either."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
import json
from typing import Any

from babel import Locale as BabelLocale
from babel.dates import format_skeleton

import config.plan_catalog_generated as plan_catalog

# units_per_recorded_hour is provisional. See storefront_copy_v1.json "recording.note":
# evidence/2026-10-12-unit-economics-and-usage.md §1/§3. Replace with shadow-ledger p50 (#21369).
_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

# Stripe zero-decimal currencies: unit_amount is already the major unit
# (500 JPY is ¥500, not ¥5.00). https://docs.stripe.com/currencies#zero-decimal
# UGX is omitted: Stripe still sends it as two-decimal (500 is 5 UGX), like ISK.
_ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        'bif',
        'clp',
        'djf',
        'gnf',
        'jpy',
        'kmf',
        'krw',
        'mga',
        'pyg',
        'rwf',
        'vnd',
        'vuv',
        'xaf',
        'xof',
        'xpf',
    }
)

# Stripe three-decimal currencies: unit_amount counts thousandths.
_THREE_DECIMAL_CURRENCIES = frozenset({'bhd', 'jod', 'kwd', 'omr', 'tnd'})


@lru_cache(maxsize=1)
def load_copy() -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parents[1] / 'config/storefront_copy_v1.json').read_text())


# Norwegian Bokmål/Nynorsk tags have no catalog of their own; the app uses `no`.
_LANGUAGE_ALIASES = {'nb': 'no', 'nn': 'no'}
# Babel's locale id where it differs from the catalog key.
_BABEL_TAGS = {'no': 'nb', 'zh': 'zh_Hans', 'sr': 'sr_Cyrl'}


def _deep_merge(base: Any, overlay: Any) -> Any:
    """Overlay wins. A missing nested key keeps the base value, so a partial locale cannot drop a section."""
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return overlay
    merged = dict(base)
    for key, value in overlay.items():
        merged[key] = _deep_merge(merged[key], value) if key in merged else value
    return merged


def _locale_key(locale: str | None, locales: dict[str, Any], default: str) -> str:
    if not locale or not str(locale).strip():
        return default
    index = {name.lower(): name for name in locales}
    raw = str(locale).strip().replace('_', '-')
    if raw.lower() in index:
        return index[raw.lower()]
    short = _LANGUAGE_ALIASES.get(raw.split('-', 1)[0].lower(), raw.split('-', 1)[0].lower())
    return index.get(short, default)


def copy_for(locale: str | None) -> dict[str, Any]:
    payload = load_copy()
    locales = payload['locales']
    default = payload['default_locale']
    key = _locale_key(locale, locales, default)
    if key == default:
        return locales[default]
    return _deep_merge(locales[default], locales[key])


def _babel_tag(locale: str | None) -> str:
    payload = load_copy()
    key = _locale_key(locale, payload['locales'], payload['default_locale'])
    return _BABEL_TAGS.get(key, key)


def _plural_category(count: int, locale: str | None) -> str:
    try:
        return BabelLocale.parse(_babel_tag(locale)).plural_form(count)
    except (ValueError, LookupError):
        return 'one' if count == 1 else 'other'


def _count_template(
    group: dict[str, Any], count: int, locale: str | None, *, plural_key: str, one_key: str, many_key: str
) -> str:
    """CLDR category when the catalog has one, otherwise the one/many pair."""
    forms = group.get(plural_key)
    if isinstance(forms, dict) and forms:
        category = _plural_category(count, locale)
        template = forms.get(category) or forms.get('other') or forms.get('many')
        if isinstance(template, str):
            return template
    if count == 1 and isinstance(group.get(one_key), str):
        return group[one_key]
    return group[many_key]


def _recording() -> dict[str, Any]:
    return load_copy()['recording']


def _share() -> Decimal:
    # str() keeps the JSON decimal ("0.85") exact; a binary float would not.
    return Decimal(str(_recording()['recording_share']))


def _units_per_hour() -> Decimal:
    from config.rate_card import recording_units_per_hour

    return recording_units_per_hour()


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
    return _capacity_hours(plan_id, raw)


def _capacity_hours(plan_id: str, raw: Decimal) -> int:
    # Keep a supported promise boundary visible when nice rounding would hide it.
    threshold = {'plus': 240, 'operator': 720, 'architect': 1440}.get(plan_id)
    nice = floor_to_nice(raw)
    return max(nice, threshold) if threshold is not None and raw >= threshold else nice


def per_day_count(monthly_hours: int) -> int:
    return int((Decimal(monthly_hours) / Decimal(30)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def per_day_phrase(monthly_hours: int, locale: str | None = None) -> str:
    """monthly ÷ 30. <6 → about N hour(s) a day; 6–16 → all day; >16 → more than one device.

    Shipped cards use the per-tier hours_line templates, not this phrase.
    """
    phrases = copy_for(locale)['per_day']
    daily = Decimal(monthly_hours) / Decimal(30)
    if daily < 6:
        count = per_day_count(monthly_hours)
        template = _count_template(
            phrases, count, locale, plural_key='under_6_plural', one_key='under_6_one', many_key='under_6'
        )
        return template.format(n=count)
    if daily <= 16:
        return phrases['all_day']
    return phrases['multi_device']


def hours_line(plan_id: str, locale: str | None = None) -> str:
    templates = copy_for(locale)['hours_lines']
    template = templates.get(plan_id)
    if not template:
        return ''
    hours = recording_hours(plan_id)
    bands = copy_for(locale)['hours_bands']
    threshold = {'plus': 240, 'operator': 720, 'architect': 1440}.get(plan_id)
    if threshold is not None and hours >= threshold:
        return bands[plan_id].format(hours=f'{hours:,}')
    return template.format(hours=f'{hours:,}', per_day=per_day_count(hours))


def recording_hours_left(plan_id: str, percent: float) -> int:
    """Remaining wall-clock hours, never below zero.

    Paid plans reuse the recording-hours definition on the unused units
    (remaining × recording_share / units_per_recorded_hour, then floor_to_nice).
    Free has no unit budget; scale its fixed hours by the unused share.
    A budget percent at or above 100 clamps to 0.
    """
    fraction = (Decimal(100) - Decimal(str(percent))) / Decimal(100)
    if fraction <= 0:
        return 0
    if plan_id == 'basic':
        remaining = Decimal(recording_hours('basic')) * fraction
        return int(remaining.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    units = budget_units_for(plan_id)
    if units is None:
        return 0
    remaining_units = Decimal(units) * fraction
    return _capacity_hours(plan_id, remaining_units * _share() / _units_per_hour())


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
    cancel_scheduled: bool = False,
    plan_name_text: str | None = None,
    period_end: int | None = None,
) -> str:
    headers = copy_for(locale)['headers']
    if legacy:
        return headers['legacy']
    if cancel_scheduled and plan_name_text and type(period_end) is int and period_end > 0:
        return headers['cancel_scheduled'].format(plan=plan_name_text, date=format_date(period_end, locale))
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


def format_date(timestamp: int, locale: str | None = None) -> str:
    """Locale month-and-day. English stays `Nov 1` (Babel skeleton MMMd)."""
    moment = datetime.fromtimestamp(timestamp, timezone.utc).date()
    tag = _babel_tag(locale)
    if tag == 'en':
        # Shipped English goldens use this abbreviation. Babel's en skeleton matches it today.
        return f'{_MONTHS[moment.month - 1]} {moment.day}'
    try:
        return format_skeleton('MMMd', moment, locale=tag)
    except (ValueError, LookupError):
        return f'{_MONTHS[moment.month - 1]} {moment.day}'


def reset_parts(reset_at: int, locale: str | None = None) -> tuple[str, str]:
    moment = datetime.fromtimestamp(reset_at, timezone.utc)
    reset_label = copy_for(locale)['dates']['resets'].format(date=format_date(reset_at, locale))
    period = moment
    if moment.day == 1 and moment.hour == 0 and moment.minute == 0 and moment.second == 0:
        period = moment - timedelta(days=1)
    return f'{period.year:04d}-{period.month:02d}', reset_label


def _minor_exponent(currency: str) -> int:
    code = currency.strip().lower()
    if code in _ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in _THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def money(amount_minor: int) -> str:
    return format_money(amount_minor, 'usd')


def format_money(amount_minor: int, currency: str) -> str:
    """Format a minor-unit amount in its price currency.

    USD uses a dollar sign. Other currencies keep a trailing ISO code.
    Thousands separators always apply. A whole major unit drops a trailing
    ``.00`` (or ``.000``); a non-zero fraction keeps the currency's decimals
    (``$499.90``). Zero-decimal currencies such as JPY are not divided by 100.
    """
    code = currency.strip()
    exponent = _minor_exponent(code)
    quantizer = Decimal('1') if exponent == 0 else Decimal(10) ** -exponent
    amount = (Decimal(amount_minor) / (Decimal(10) ** exponent)).quantize(quantizer, rounding=ROUND_HALF_UP)
    if exponent == 0 or amount == amount.to_integral_value():
        rendered = f'{int(amount):,}'
    else:
        rendered = format(amount, f',.{exponent}f')
    if code.lower() == 'usd':
        return f'${rendered}'
    return f'{rendered} {code.upper()}'


def months_free_phrase(count: int, locale: str | None = None) -> str:
    prices = copy_for(locale)['prices']
    template = _count_template(
        prices, count, locale, plural_key='months_free_plural', one_key='months_free_one', many_key='months_free_many'
    )
    return template.format(n=count)


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
    currency: str = 'usd',
) -> tuple[str, str | None]:
    text = copy_for(locale)['current']
    note = text['legacy_note'] if legacy else None
    if plan_id == 'basic':
        return text['free'], note
    date = format_date(period_end, locale) if type(period_end) is int and period_end > 0 else None
    # Paid cancel-scheduled: price only. The end date moves to the header.
    # Legacy keeps the previous "ends {date}" line; resubscribe is not offered.
    if cancel and not legacy and amount_minor is not None and interval in {'month', 'year'}:
        period = _period_word(interval, locale)
        price = format_money(amount_minor, currency)
        return text['cancel'].format(plan=plan_name_text, price=price, period=period), note
    if cancel and date:
        return text['cancel_ends'].format(plan=plan_name_text, date=date), note
    if amount_minor is not None and interval in {'month', 'year'}:
        period = _period_word(interval, locale)
        price = format_money(amount_minor, currency)
        if date:
            return text['paid'].format(plan=plan_name_text, price=price, period=period, date=date), note
        return text['paid_no_date'].format(plan=plan_name_text, price=price, period=period), note
    return text['name_only'].format(plan=plan_name_text), note


def _period_word(interval: str, locale: str | None) -> str:
    dates = copy_for(locale)['dates']
    return dates['period_month'] if interval == 'month' else dates['period_year']


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


def monthly_headline(amount_minor: int, locale: str | None = None, currency: str = 'usd') -> str:
    """Monthly price line. Free is "$0"; a paid month is "{amount}/month"."""
    text = copy_for(locale)['prices']
    if amount_minor == 0:
        return text['headline_free']
    return text['headline_month'].format(amount=format_money(amount_minor, currency))


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
        # Half-up in minor units. USD cents: 19990 → 1666 → $16.66.
        # Zero-decimal currencies stay whole major units (no /100).
        equivalent_minor = int((Decimal(amount_minor) / Decimal(12)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        headline = text['headline_year'].format(amount=format_money(equivalent_minor, currency))
        free = months_free(monthly_minor, amount_minor) if monthly_minor else None
        annual = format_money(amount_minor, currency)
        if free is not None:
            subline = text['subline_year'].format(amount=annual, free=months_free_phrase(free, locale))
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
        'headline': monthly_headline(amount_minor, locale, currency=currency),
        'subline': None,
        'renewal_line': text['renewal_month'] if amount_minor else None,
        'months_free': None,
    }


def yearly_toggle_label(months: int | None, locale: str | None = None) -> str | None:
    if months is None or months < 1:
        return None
    return copy_for(locale)['prices']['toggle'].format(free=months_free_phrase(months, locale))


def blocked_line(locale: str | None = None) -> str:
    return copy_for(locale)['blocked_line']


def yearly_switch_label(
    *, monthly_minor: int, annual_minor: int, currency: str, locale: str | None = None
) -> str | None:
    """12× monthly − annual, in the price currency. Absent when the yearly price does not save."""
    saved = monthly_minor * 12 - annual_minor
    if saved <= 0:
        return None
    return copy_for(locale)['cta']['switch_yearly'].format(saving=format_money(saved, currency))


def _wire_percent(percent: float) -> int:
    rounded = int(Decimal(str(percent)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    # Never promote an unexhausted budget into the cap/Architect surface by rounding.
    return min(rounded, 99) if percent < 100 else rounded


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
        period_id, reset_label = reset_parts(reset_at, locale)
        payload['period_id'] = period_id
        payload['reset_label'] = reset_label
    if kind == 'usage_budget' and payload['reset_label']:
        # Hours only from 80 up to, but not including, 100. At the cap the at-cap
        # state applies, so the meter never says "about 0 hours".
        if 80 <= shown < 100:
            left = recording_hours_left(plan_id, shown)
            if left > 0:
                payload['hours_left'] = left
                payload['meter_line'] = _meter_hours_line(
                    text, shown=shown, left=left, reset=payload['reset_label'], locale=locale
                )
            else:
                payload['meter_line'] = text['meter']['line_short'].format(percent=shown, reset=payload['reset_label'])
            payload['nudge_line'] = text['meter']['nudge_80'].format(reset=payload['reset_label'])
        else:
            payload['meter_line'] = text['meter']['line_short'].format(percent=shown, reset=payload['reset_label'])
        payload['more_label'] = text['meter']['more_label']
    return payload


def _meter_hours_line(text: dict[str, Any], *, shown: int, left: int, reset: str, locale: str | None) -> str:
    meter = text['meter']
    forms = meter.get('line_plural')
    template = meter['line']
    if isinstance(forms, dict) and forms:
        category = _plural_category(left, locale)
        chosen = forms.get(category) or forms.get('other')
        if isinstance(chosen, str):
            template = chosen
    return template.format(percent=shown, hours=f'{left:,}', reset=reset)


def chat_at_cap(plan_id: str, reset_at: int, locale: str | None = None) -> dict[str, Any]:
    """One backend-owned pause state shared by admission, quota and storefront."""
    text = copy_for(locale)['chat_at_cap']
    upgrade = {'basic': ('plus', 'Plus'), 'plus': ('operator', 'Pro'), 'operator': ('architect', 'Architect')}.get(
        plan_id
    )
    return {
        'state': 'paused',
        'title': text['title'],
        'body': text['body'],
        'reset_at': reset_at,
        'reset_line': text['reset_line'].format(date=format_date(reset_at, locale)),
        'trigger': 'usage_budget',
        'upgrade_plan': upgrade[0] if upgrade else None,
        'upgrade_label': text['upgrade_label'].format(plan=upgrade[1]) if upgrade else None,
    }
