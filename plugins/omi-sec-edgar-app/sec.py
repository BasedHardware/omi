from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from models import (
    CompanyRequest,
    FinancialSnapshotRequest,
    RecentFilingsRequest,
)


DATA_BASE_URL = "https://data.sec.gov"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SOURCE_URL = "https://www.sec.gov/edgar"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
TICKER_CACHE_SECONDS = 3600

ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")

METRICS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "diluted_eps": ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"),
}

METRIC_LABELS = {
    "revenue": "Revenue",
    "net_income": "Net income",
    "assets": "Total assets",
    "liabilities": "Total liabilities",
    "stockholders_equity": "Stockholders' equity",
    "cash": "Cash and equivalents",
    "diluted_eps": "Diluted EPS",
}

_ticker_cache: tuple[float, dict[str, Any]] | None = None


class SecEdgarError(Exception):
    """A safe, user-facing SEC EDGAR provider or payload error."""


def normalize_cik(value: str) -> str:
    cleaned = value.strip().upper()
    if cleaned.startswith("CIK"):
        cleaned = cleaned[3:]
    cleaned = cleaned.lstrip("0") or "0"
    if not cleaned.isdigit() or len(cleaned) > 10:
        raise ValueError("CIK must contain 1 to 10 digits")
    return cleaned.zfill(10)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    not_found_message: Optional[str] = None,
) -> Any:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise SecEdgarError(
                not_found_message or "SEC EDGAR record not found"
            ) from exc
        if status in (403, 429):
            raise SecEdgarError(
                "SEC EDGAR refused or rate-limited the request. Set "
                "SEC_USER_AGENT to an identifying app name and contact address, "
                "then retry later."
            ) from exc
        raise SecEdgarError(f"SEC EDGAR returned HTTP {status}") from exc
    except httpx.RequestError as exc:
        raise SecEdgarError(f"SEC EDGAR request failed: {type(exc).__name__}") from exc

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SecEdgarError("SEC EDGAR response exceeded the size limit")

    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        raise SecEdgarError("SEC EDGAR returned a non-JSON response")

    try:
        return response.json()
    except ValueError as exc:
        raise SecEdgarError("SEC EDGAR returned malformed JSON") from exc


async def _company_tickers(
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    global _ticker_cache
    now = time.monotonic()
    if _ticker_cache and now - _ticker_cache[0] < TICKER_CACHE_SECONDS:
        return _ticker_cache[1]

    payload = await _get_json(client, TICKER_URL)
    if not isinstance(payload, dict):
        raise SecEdgarError("SEC EDGAR returned an unexpected ticker payload")
    _ticker_cache = (now, payload)
    return payload


def _ticker_candidates(payload: dict[str, Any], query: str) -> list[dict[str, Any]]:
    needle = query.casefold().strip()
    exact_ticker: list[dict[str, Any]] = []
    name_matches: list[dict[str, Any]] = []

    for value in payload.values():
        row = _as_dict(value)
        ticker = _clean_text(row.get("ticker"), 30)
        title = _clean_text(row.get("title"), 180)
        if ticker.casefold() == needle:
            exact_ticker.append(row)
        elif needle and needle in title.casefold():
            name_matches.append(row)

    return exact_ticker or name_matches


async def _resolve_cik(
    client: httpx.AsyncClient,
    query: str,
) -> tuple[str, Optional[dict[str, Any]]]:
    try:
        return normalize_cik(query), None
    except ValueError:
        pass

    payload = await _company_tickers(client)
    matches = _ticker_candidates(payload, query)
    if not matches:
        raise SecEdgarError(f"No SEC EDGAR company matched '{query}'")

    unique_ciks = {
        normalize_cik(str(_as_dict(row).get("cik_str", "")))
        for row in matches
        if _as_dict(row).get("cik_str") is not None
    }
    if len(unique_ciks) != 1:
        examples = []
        for row in matches[:5]:
            row = _as_dict(row)
            examples.append(
                f"{_clean_text(row.get('ticker'), 20)} "
                f"({_clean_text(row.get('title'), 80)})"
            )
        raise SecEdgarError(
            f"Multiple SEC EDGAR companies matched '{query}': "
            + "; ".join(examples)
            + ". Use a ticker or CIK."
        )

    row = _as_dict(matches[0])
    return next(iter(unique_ciks)), row


async def _company_submission(
    client: httpx.AsyncClient,
    company: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    cik, ticker_row = await _resolve_cik(client, company)
    payload = await _get_json(
        client,
        f"{DATA_BASE_URL}/submissions/CIK{cik}.json",
        not_found_message="SEC EDGAR company not found",
    )
    if not isinstance(payload, dict):
        raise SecEdgarError("SEC EDGAR returned an unexpected company payload")
    return payload, ticker_row


def _format_address(payload: dict[str, Any]) -> str:
    addresses = _as_dict(payload.get("addresses"))
    address = _as_dict(addresses.get("business") or addresses.get("mailing"))
    parts = [
        _clean_text(address.get("street1"), 120),
        _clean_text(address.get("street2"), 120),
        _clean_text(address.get("city"), 80),
        _clean_text(address.get("stateOrCountry"), 40),
        _clean_text(address.get("zipCode"), 30),
    ]
    return ", ".join(part for part in parts if part) or "not listed"


def _format_company_profile(
    payload: dict[str, Any],
    ticker_row: Optional[dict[str, Any]],
) -> str:
    name = _clean_text(payload.get("name"), 180) or "Unknown SEC registrant"
    tickers = [_clean_text(item, 30) for item in _as_list(payload.get("tickers"))]
    if not tickers and ticker_row:
        ticker = _clean_text(ticker_row.get("ticker"), 30)
        if ticker:
            tickers = [ticker]

    exchanges = [_clean_text(item, 80) for item in _as_list(payload.get("exchanges"))]
    lines = [
        name,
        f"CIK: {normalize_cik(str(payload.get('cik', '')))}",
        f"Ticker: {', '.join(tickers) if tickers else 'not listed'}",
        f"Exchange: {', '.join(exchanges) if exchanges else 'not listed'}",
        (
            "SIC: "
            f"{_clean_text(payload.get('sic'), 20) or 'not listed'} - "
            f"{_clean_text(payload.get('sicDescription'), 160) or 'not listed'}"
        ),
        f"Filer category: {_clean_text(payload.get('category'), 100) or 'not listed'}",
        f"Fiscal year end: {_clean_text(payload.get('fiscalYearEnd'), 10) or 'not listed'}",
        (
            "State of incorporation: "
            f"{_clean_text(payload.get('stateOfIncorporationDescription'), 80) or 'not listed'}"
        ),
        f"Website: {_clean_text(payload.get('website'), 200) or 'not listed'}",
        f"Business address: {_format_address(payload)}",
        f"Source: {SOURCE_URL}",
    ]
    return "\n".join(lines)


def _filing_url(cik: str, accession: str, primary_document: str) -> str:
    compact_accession = accession.replace("-", "")
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{compact_accession}/{primary_document}"
    )


def _recent_filing_rows(
    cik: str,
    submissions: dict[str, Any],
    request: RecentFilingsRequest,
) -> list[str]:
    filings = _as_dict(submissions.get("filings"))
    recent = _as_dict(filings.get("recent"))
    forms = _as_list(recent.get("form"))
    dates = _as_list(recent.get("filingDate"))
    report_dates = _as_list(recent.get("reportDate"))
    accessions = _as_list(recent.get("accessionNumber"))
    documents = _as_list(recent.get("primaryDocument"))
    descriptions = _as_list(recent.get("primaryDocDescription"))

    rows: list[str] = []
    requested_form = (request.form_type or "").upper()
    for index, form_value in enumerate(forms):
        form = _clean_text(form_value, 40)
        if requested_form and form.upper() != requested_form:
            continue

        accession = (
            _clean_text(accessions[index], 40) if index < len(accessions) else ""
        )
        document = _clean_text(documents[index], 180) if index < len(documents) else ""
        filing_date = _clean_text(dates[index], 20) if index < len(dates) else ""
        report_date = (
            _clean_text(report_dates[index], 20) if index < len(report_dates) else ""
        )
        description = (
            _clean_text(descriptions[index], 180) if index < len(descriptions) else ""
        )
        if not form or not accession:
            continue

        line = f"- {form} | filed {filing_date or 'unknown'}"
        if report_date:
            line += f" | period {report_date}"
        if description:
            line += f" | {description}"
        if document:
            line += f"\n  {_filing_url(cik, accession, document)}"
        rows.append(line)
        if len(rows) >= request.limit:
            break
    return rows


def _format_filing_value(value: Any, unit: str) -> str:
    if not isinstance(value, (int, float)):
        return "not available"
    if unit == "USD/shares":
        return f"${value:,.2f}"
    if unit == "shares":
        return f"{value:,.0f} shares"
    if unit != "USD":
        return f"{value:,.4g} {unit}"

    absolute = abs(value)
    if absolute >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:,.2f}T"
    if absolute >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    return f"${value:,.2f}"


def _annual_facts(
    facts: dict[str, Any],
    concept_names: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str]:
    for taxonomy in ("us-gaap", "ifrs-full"):
        taxonomy_facts = _as_dict(facts.get(taxonomy))
        for concept_name in concept_names:
            concept = _as_dict(taxonomy_facts.get(concept_name))
            units = _as_dict(concept.get("units"))
            for unit_name, unit_facts in units.items():
                rows = []
                for value in _as_list(unit_facts):
                    row = _as_dict(value)
                    form = _clean_text(row.get("form"), 20).upper()
                    if not any(form.startswith(prefix) for prefix in ANNUAL_FORMS):
                        continue
                    if not _clean_text(row.get("end"), 20):
                        continue
                    rows.append(row)
                rows.sort(
                    key=lambda row: (
                        _clean_text(row.get("end"), 20),
                        _clean_text(row.get("filed"), 20),
                    ),
                    reverse=True,
                )
                if rows:
                    return rows, _clean_text(unit_name, 30)
    return [], ""


def _format_financial_snapshot(
    submissions: dict[str, Any],
    facts_payload: dict[str, Any],
    request: FinancialSnapshotRequest,
) -> str:
    facts = _as_dict(facts_payload.get("facts"))
    lines = [
        (
            f"Financial snapshot for "
            f"{_clean_text(submissions.get('name'), 180) or 'SEC registrant'} "
            f"(CIK {normalize_cik(str(submissions.get('cik', '')))})."
        )
    ]

    for metric_name, concept_names in METRICS.items():
        rows, unit = _annual_facts(facts, concept_names)
        if not rows:
            continue
        lines.append(f"{METRIC_LABELS[metric_name]}:")
        seen_periods: set[str] = set()
        emitted = 0
        for row in rows:
            period = _clean_text(row.get("end"), 20)
            if not period or period in seen_periods:
                continue
            seen_periods.add(period)
            lines.append(
                f"- {period}: {_format_filing_value(row.get('val'), unit)} "
                f"({_clean_text(row.get('form'), 20) or 'annual filing'})"
            )
            emitted += 1
            if emitted >= request.years:
                break

    if len(lines) == 1:
        lines.append(
            "No annual facts were available for the core metrics supported by "
            "this tool."
        )
    lines.append(
        "Values come from SEC XBRL filings and may be restated. This is filing "
        "data, not investment advice."
    )
    lines.append(f"Source: {SOURCE_URL}")
    return "\n".join(lines)


async def get_company_profile(
    client: httpx.AsyncClient,
    request: CompanyRequest,
) -> str:
    payload, ticker_row = await _company_submission(client, request.company)
    return _format_company_profile(payload, ticker_row)


async def list_recent_filings(
    client: httpx.AsyncClient,
    request: RecentFilingsRequest,
) -> str:
    payload, _ticker_row = await _company_submission(client, request.company)
    cik = normalize_cik(str(payload.get("cik", "")))
    rows = _recent_filing_rows(cik, payload, request)
    heading = (
        f"Recent SEC filings for "
        f"{_clean_text(payload.get('name'), 180) or 'registrant'}"
    )
    if request.form_type:
        heading += f" of type {request.form_type.upper()}"
    if not rows:
        return (
            heading + ": none found in the recent filing index.\n"
            f"Source: {SOURCE_URL}"
        )
    return "\n".join(
        [
            heading + ":",
            *rows,
            "Recent index results may not include every historical filing.",
            f"Source: {SOURCE_URL}",
        ]
    )


async def get_financial_snapshot(
    client: httpx.AsyncClient,
    request: FinancialSnapshotRequest,
) -> str:
    submissions, _ticker_row = await _company_submission(client, request.company)
    cik = normalize_cik(str(submissions.get("cik", "")))
    facts_payload = await _get_json(
        client,
        f"{DATA_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json",
        not_found_message="SEC EDGAR financial facts not found",
    )
    if not isinstance(facts_payload, dict):
        raise SecEdgarError("SEC EDGAR returned an unexpected facts payload")
    return _format_financial_snapshot(submissions, facts_payload, request)
