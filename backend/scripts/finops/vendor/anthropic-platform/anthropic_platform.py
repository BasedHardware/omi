#!/usr/bin/env python3
"""Read-only client for Anthropic organization usage and cost reports.

This client intentionally has no write endpoints, configurable host, or HTTP
method option. Every API request is a GET to one of SAFE_PATHS.
"""

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
SAFE_PATHS = {
    "/v1/organizations/usage_report/messages",
    "/v1/organizations/cost_report",
}
USAGE_GROUP_BY = {
    "account_id",
    "api_key_id",
    "context_window",
    "inference_geo",
    "model",
    "service_account_id",
    "service_tier",
    "speed",
    "workspace_id",
}
COST_GROUP_BY = {"description", "workspace_id"}
# The live Cost Report's `amount` is denominated in USD cents even though its
# currency label is USD. Preserve the raw field and expose normalized USD.
# Verified against the Console and token × published-price reconciliation.
COST_AMOUNT_USD_SCALE = Decimal("0.01")


def cost_amount_usd(result: dict) -> Decimal:
    """Convert a Cost Report's minor-unit amount to USD."""
    try:
        return Decimal(result["amount"]) * COST_AMOUNT_USD_SCALE
    except (KeyError, InvalidOperation) as exc:
        raise RuntimeError("Cost report contained an invalid amount") from exc


def normalize_cost_report_amounts(report: dict) -> dict:
    """Add `amount_usd` while retaining the API's raw minor-unit `amount`."""
    for bucket in report.get("data", []):
        for result in bucket.get("results", []):
            result["amount_usd"] = str(cost_amount_usd(result))
    return report


def load_api_key(env_path: Path) -> str:
    """Read the admin credential without sourcing the file into a shell."""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_ADMIN_API_KEY="):
                key = line.partition("=")[2].strip()
                if key.startswith("sk-ant-"):
                    return key
    except OSError as exc:
        raise RuntimeError(f"Cannot read credential file: {env_path}") from exc
    raise RuntimeError("ANTHROPIC_ADMIN_API_KEY is missing or malformed in the credential file")


def safe_error_message(body: bytes, api_key: str) -> str:
    """Return a concise API error while ensuring the credential cannot be echoed."""
    try:
        payload = json.loads(body.decode("utf-8"))
        error = payload.get("error", payload)
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str) and message:
            return message.replace(api_key, "[redacted]")
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return "No safe API error message was provided."


def fetch_all(endpoint: str, parameters: dict, api_key: str, *, opener=urlopen, max_pages: int = 50) -> dict:
    """GET every result page from one allowlisted report endpoint."""
    if endpoint not in SAFE_PATHS:
        raise ValueError("Endpoint is not allowlisted for this read-only client")
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages must be between 1 and 100")

    data = []
    query = dict(parameters)
    for page_count in range(1, max_pages + 1):
        encoded_query = {f"{name}[]" if isinstance(value, list) else name: value for name, value in query.items()}
        url = f"{API_BASE}{endpoint}?{urlencode(encoded_query, doseq=True)}"
        request = Request(
            url,
            headers={
                "X-api-key": api_key,
                "anthropic-version": API_VERSION,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"Anthropic Admin API returned HTTP {exc.code}: {safe_error_message(exc.read(), api_key)}"
            ) from None
        except URLError as exc:
            raise RuntimeError(f"Anthropic Admin API network error: {exc.reason}") from None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Anthropic Admin API returned invalid JSON") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise RuntimeError("Anthropic Admin API returned an unexpected report shape")
        data.extend(payload["data"])
        if not payload.get("has_more"):
            return {"data": data, "page_count": page_count}
        next_page = payload.get("next_page")
        if not isinstance(next_page, str) or not next_page:
            raise RuntimeError("Anthropic Admin API indicated another page without a next_page token")
        query["page"] = next_page
    raise RuntimeError(f"Stopped after {max_pages} pages; rerun with a larger --max-pages if intended")


def cost_summary(report: dict) -> dict:
    """Sum exact Decimal cost amounts by currency and description."""
    by_currency: dict[str, Decimal] = {}
    by_description: dict[str, Decimal] = {}
    result_count = 0
    for bucket in report.get("data", []):
        for result in bucket.get("results", []):
            amount = cost_amount_usd(result)
            currency = result.get("currency", "unknown")
            description = result.get("description", "unknown")
            by_currency[currency] = by_currency.get(currency, Decimal()) + amount
            by_description[description] = by_description.get(description, Decimal()) + amount
            result_count += 1
    return {
        "currency_totals": {key: str(value) for key, value in sorted(by_currency.items())},
        "description_totals": {key: str(value) for key, value in sorted(by_description.items())},
        "result_count": result_count,
    }


def rfc3339(value: str) -> str:
    """Validate and normalize a user-supplied RFC 3339 timestamp to UTC."""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamps must be RFC 3339, e.g. 2026-07-01T00:00:00Z") from exc
    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps must include a UTC offset or Z")
    return timestamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def csv_values(value: str, allowed: set[str], flag: str) -> list[str]:
    values = [part.strip() for part in value.split(",") if part.strip()]
    invalid = set(values) - allowed
    if not values or invalid:
        raise ValueError(f"{flag} accepts only: {', '.join(sorted(allowed))}")
    return values


def time_bounds(args: argparse.Namespace, default_days: int) -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = args.start or (now - timedelta(days=args.days or default_days)).isoformat().replace("+00:00", "Z")
    end = args.end or now.isoformat().replace("+00:00", "Z")
    if start >= end:
        raise ValueError("--start must be earlier than --end")
    return start, end


def report_limit(raw: str) -> int:
    """Parse the report API's documented live maximum page size."""
    try:
        limit = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit must be an integer") from exc
    if not 1 <= limit <= 31:
        raise argparse.ArgumentTypeError("--limit must be between 1 and 31")
    return limit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Anthropic Admin usage and cost reports")
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[1] / "references" / ".env")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--days", type=int, help="Look back this many days (default varies by report)")
        subparser.add_argument("--start", type=rfc3339, help="RFC 3339 inclusive start timestamp")
        subparser.add_argument("--end", type=rfc3339, help="RFC 3339 exclusive end timestamp")
        subparser.add_argument("--limit", type=report_limit, default=31, help="Buckets per API page (1-31)")
        subparser.add_argument("--max-pages", type=int, default=50, help="Maximum paginated GET requests (1-100)")

    usage = subparsers.add_parser("usage", help="Get detailed Messages usage report")
    common(usage)
    usage.add_argument("--bucket-width", choices=("1m", "1h", "1d"), default="1d")
    usage.add_argument("--group-by", default="model,workspace_id")
    usage.add_argument("--model", action="append", default=[])
    usage.add_argument("--workspace-id", action="append", default=[])
    usage.add_argument("--api-key-id", action="append", default=[])
    usage.add_argument("--service-account-id", action="append", default=[])
    usage.add_argument("--account-id", action="append", default=[])

    cost = subparsers.add_parser("cost", help="Get detailed Cost report")
    common(cost)
    cost.add_argument("--group-by", default="description,workspace_id")

    summary = subparsers.add_parser("cost-summary", help="Get and exactly sum normalized USD Cost Report amounts")
    common(summary)
    summary.add_argument("--group-by", default="description,workspace_id")

    preflight = subparsers.add_parser(
        "preflight", help="Verify credential access to both reports and cost normalization"
    )
    common(preflight)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.days is not None and args.days < 1:
        raise SystemExit("--days must be at least 1")
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    try:
        key = load_api_key(args.env_file)
        if args.command == "preflight":
            start, end = time_bounds(args, default_days=1)
            usage = fetch_all(
                "/v1/organizations/usage_report/messages",
                {
                    "starting_at": start,
                    "ending_at": end,
                    "bucket_width": "1d",
                    "group_by": ["model"],
                    "limit": args.limit,
                },
                key,
                max_pages=args.max_pages,
            )
            cost = fetch_all(
                "/v1/organizations/cost_report",
                {
                    "starting_at": start,
                    "ending_at": end,
                    "bucket_width": "1d",
                    "group_by": ["description", "workspace_id"],
                    "limit": args.limit,
                },
                key,
                max_pages=args.max_pages,
            )
            normalize_cost_report_amounts(cost)
            report = {
                "credential": "valid",
                "window": {"starting_at": start, "ending_at": end},
                "usage": {
                    "page_count": usage["page_count"],
                    "bucket_count": len(usage["data"]),
                    "result_count": sum(len(b.get("results", [])) for b in usage["data"]),
                },
                "cost": {"page_count": cost["page_count"], "bucket_count": len(cost["data"]), **cost_summary(cost)},
                "cost_amount_interpretation": "raw amount is USD cents; cost totals are normalized USD",
            }
        elif args.command == "usage":
            start, end = time_bounds(args, default_days=7)
            parameters = {
                "starting_at": start,
                "ending_at": end,
                "bucket_width": args.bucket_width,
                "group_by": csv_values(args.group_by, USAGE_GROUP_BY, "--group-by"),
                "limit": args.limit,
            }
            for field in ("model", "workspace_id", "api_key_id", "service_account_id", "account_id"):
                values = getattr(args, field)
                if values:
                    parameters[f"{field}s"] = values
            report = fetch_all("/v1/organizations/usage_report/messages", parameters, key, max_pages=args.max_pages)
        else:
            start, end = time_bounds(args, default_days=30)
            parameters = {
                "starting_at": start,
                "ending_at": end,
                "bucket_width": "1d",
                "group_by": csv_values(args.group_by, COST_GROUP_BY, "--group-by"),
                "limit": args.limit,
            }
            report = fetch_all("/v1/organizations/cost_report", parameters, key, max_pages=args.max_pages)
            normalize_cost_report_amounts(report)
            if args.command == "cost-summary":
                report = cost_summary(report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
