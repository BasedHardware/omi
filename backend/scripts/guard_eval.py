#!/usr/bin/env python3
"""Score Cloud Run 5xx for two revisions in one settled window."""

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from subprocess import TimeoutExpired
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_readback import Reader, Refused

CONFIG = Path(__file__).resolve().parents[1] / "cloud-run-guard.json"
EXIT = {"PASS": 0, "TRIP": 1, "NO_COMPARATOR": 3, "INSUFFICIENT_DATA": 4}
CLASSES = {"1xx", "2xx", "3xx", "4xx", "5xx"}
NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")
LOG_PAGE_SIZE = 10_000
LOG_PAGE_BUDGET = 24
# Production keeps 10% of Cloud Run 429 request logs, like 2xx/3xx
# (backend/docs/runbooks/cloud-logging-cost-controls.md, cost-request-429-sample).
SAMPLED_CLIENT_STATUSES = (429,)


class LogPageBudgetExceeded(ValueError):
    pass


def policy_for(service, route_names=None):
    policy = json.loads(CONFIG.read_text(encoding="utf-8"))
    routes = policy.pop("services")[service]
    integers = (
        "success_log_weight",
        "rate_limited_log_weight",
        "settle_seconds",
        "minimum_requests",
        "minimum_effective_requests",
        "minimum_candidate_errors",
    )
    if any(type(policy[key]) is not int or policy[key] <= 0 for key in integers):
        raise ValueError("invalid guard count or delay")
    if not (
        policy["settle_seconds"] % 60 == 0
        and policy["relative_increase"] > 0
        and math.isfinite(policy["relative_increase"])
        and 0 < policy["alpha"] < 0.5
    ):
        raise ValueError("invalid guard delay, relative margin or alpha")
    identities = set()
    for name, route in routes.items():
        method, path = route["method"], route["path"]
        identity = method, path
        if (
            not NAME.fullmatch(name)
            or name == "service"
            or method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
            or not re.fullmatch(r"/[a-z0-9/_-]+", path)
            or identity in identities
            or any(type(status) is not int or not 500 <= status < 600 for status in route.get("refusal_statuses", ()))
        ):
            raise ValueError("invalid or duplicate guard route")
        identities.add(identity)
    if route_names is not None and not set(route_names) <= routes.keys():
        raise ValueError("unknown route")
    # Always read refusals so even a service-only score can subtract them.
    policy["routes"] = {
        name: route
        for name, route in routes.items()
        if route_names is None or name in route_names or route.get("refusal_statuses")
    }
    policy["scored_routes"] = list(routes) if route_names is None else list(dict.fromkeys(route_names))
    policy["required_routes"] = [] if route_names is None else policy["scored_routes"]
    return policy


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("timestamp needs a timezone")
    return timestamp.timestamp()


def parse_window(value):
    start, end = map(parse_time, value.split("/"))
    if start % 60 or end % 60 or not 300 <= end - start <= 3600:
        raise ValueError("window must span 5 to 60 whole minutes on minute boundaries")
    return int(start), int(end)


def count(value):
    result = float(value)
    if type(value) is bool or not math.isfinite(result) or result < 0:
        raise ValueError("invalid count")
    return result


@dataclass(frozen=True)
class Population:
    requests: float
    errors: float
    clients: float
    excluded: float = 0
    weight: int = 1
    population_note: str | None = None

    @property
    def rate(self):
        return self.errors / self.requests if self.requests else None

    def report(self):
        result = {
            "requests": self.requests,
            "5xx": self.errors,
            "4xx": self.clients,
            "excluded_5xx": self.excluded,
            "5xx_rate": self.rate,
            "4xx_rate": self.clients / self.requests if self.requests else None,
        }
        if self.population_note is not None:
            result["population_note"] = self.population_note
        return result


def log_weights(policy):
    return policy["success_log_weight"], policy["rate_limited_log_weight"]


def service_population(side, weights):
    classes = side["service"]
    total = sum(count(value) for value in classes.values())
    if "service_logs" not in side:
        # Historical offline fixtures carry preaggregated status classes.
        return Population(total, count(classes.get("5xx", 0)), count(classes.get("4xx", 0)))
    logged = route_population(side["service_logs"], weights, ())
    if logged.errors > total:
        return replace(logged, population_note="log_total_used_logged_5xx_exceeds_gmp_total")
    return Population(total, logged.errors, logged.clients)


def route_population(statuses, weights, refusal_statuses):
    """Weight sampled log classes back to request counts. Unsampled 4xx/5xx count once."""
    success_weight, limited_weight = weights
    successes = clients = errors = excluded = 0
    for status, value in statuses.items():
        status, value = int(status), count(value)
        if 200 <= status < 400:
            successes += value
        elif status in SAMPLED_CLIENT_STATUSES:
            clients += limited_weight * value
        elif 400 <= status < 500:
            clients += value
        elif 500 <= status < 600:
            errors += value
            if status in refusal_statuses:
                excluded += value
        else:
            raise ValueError("invalid route status")
    weight = max(success_weight, limited_weight)
    return Population(success_weight * successes + clients + errors, errors - excluded, clients, excluded, weight)


def compare(candidate, inverse, policy, alpha):
    row = {"candidate": candidate.report(), "inverse": inverse.report(), "p_value": None}
    if not inverse.requests:
        return dict(row, verdict="NO_COMPARATOR")
    # Bound the effective sample size by treating every request as weighted
    # at the maximum weight. Upweighted logs cannot become independent trials.
    nc, ni = (pop.requests / pop.weight for pop in (candidate, inverse))
    if (
        min(candidate.requests, inverse.requests) < policy["minimum_requests"]
        or min(nc, ni) < policy["minimum_effective_requests"]
    ):
        return dict(row, verdict="INSUFFICIENT_DATA")
    delta = candidate.rate - inverse.rate
    if delta <= inverse.rate * policy["relative_increase"]:
        return dict(row, verdict="PASS")
    if candidate.errors < policy["minimum_candidate_errors"]:
        return dict(row, verdict="PASS")
    pooled = (nc * candidate.rate + ni * inverse.rate) / (nc + ni)
    variance = pooled * (1 - pooled) * (1 / nc + 1 / ni)
    p_value = math.erfc(delta / math.sqrt(2 * variance)) / 2
    return dict(row, p_value=p_value, verdict="TRIP" if p_value <= alpha else "PASS")


def evaluate(policy, candidate, inverse):
    """Evaluate aggregate inputs in candidate/inverse order.

    Each input contains service response classes, service log statuses when
    available, and per-route HTTP statuses from a single window. Missing route
    buckets represent zero after a complete log read. Designed refusals stay in
    the denominator as observed requests.
    """
    weights = log_weights(policy)
    service_pair = [service_population(side, weights) for side in (candidate, inverse)]
    if not service_pair[1].requests:
        # Report the service counts without a separate route read for refusals.
        row = compare(*service_pair, policy, policy["alpha"])
        return {"verdict": "NO_COMPARATOR", "checks": {"service": row}}
    routes = policy["routes"]
    route_pairs = {
        name: [
            route_population(side["routes"].get(name, {}), weights, route.get("refusal_statuses", ()))
            for side in (candidate, inverse)
        ]
        for name, route in routes.items()
    }
    for index, population in enumerate(service_pair):
        excluded = sum(pair[index].excluded for pair in route_pairs.values())
        if excluded > population.errors:
            raise ValueError("refusals exceed service 5xx")
        service_pair[index] = replace(population, errors=population.errors - excluded, excluded=excluded)
    scored = policy["scored_routes"]
    alpha = policy["alpha"] / (1 + len(scored))
    checks = {"service": compare(*service_pair, policy, alpha)}
    for name in scored:
        checks[name] = compare(*route_pairs[name], policy, alpha)
    required = ["service", *policy["required_routes"]]
    if any(row["verdict"] == "TRIP" for row in checks.values()):
        verdict = "TRIP"
    elif any(checks[name]["verdict"] != "PASS" for name in required):
        verdict = "INSUFFICIENT_DATA"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "checks": checks}


class Telemetry:
    def __init__(self, reader, project, region):
        self.reader = reader
        self.project = project
        self.region = region
        self.token = None
        self.log_pages_left = LOG_PAGE_BUDGET

    def request(self, url, params, body=None):
        if self.token is None:
            self.token = self.reader.run(["gcloud", "auth", "print-access-token"]).strip()
        if not self.token:
            raise ValueError("missing token")
        request = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(params),
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.reader.remaining()) as response:
            return json.load(response)

    def service_counts(self, service, candidate, inverse, start, end):
        selector = (
            f'monitored_resource="cloud_run_revision",project_id="{self.project}",'
            f'location="{self.region}",service_name="{service}",'
            f'revision_name=~"{candidate}|{inverse}"'
        )
        query = (
            "sum by (revision_name, response_code_class) "
            f"(increase(run_googleapis_com:request_count{{{selector}}}[{end - start}s]))"
        )
        url = f"https://monitoring.googleapis.com/v1/projects/{self.project}/location/global/" "prometheus/api/v1/query"
        response = self.request(url, {"query": query, "time": end})
        data = response["data"]
        if response["status"] != "success" or response.get("warnings") or data["resultType"] != "vector":
            raise ValueError("incomplete GMP evidence")
        result = {candidate: {}, inverse: {}}
        for row in data["result"]:
            labels = row["metric"]
            revision, status = labels["revision_name"], labels["response_code_class"]
            sample_time, value = row["value"]
            if revision not in result or status not in CLASSES or status in result[revision] or sample_time != end:
                raise ValueError("unexpected GMP series")
            result[revision][status] = count(value)
        return result

    def route_counts(self, service, candidate, inverse, start, end, route):
        return self.log_counts(service, (candidate, inverse), start, end, 200, 600, route=route)

    def log_counts(self, service, revisions, start, end, minimum_status, maximum_status, *, route=None):
        # Project infrastructure labels and status. Apply any route predicate on the server.
        project = f"projects/{self.project}"
        revisions_filter = " OR ".join(f'resource.labels.revision_name="{revision}"' for revision in revisions)
        filters = [
            f'logName="{project}/logs/run.googleapis.com%2Frequests"',
            'resource.type="cloud_run_revision"',
            f'resource.labels.project_id="{self.project}"',
            f'resource.labels.location="{self.region}"',
            f'resource.labels.service_name="{service}"',
            f'({revisions_filter})',
            f'timestamp>"{stamp(start)}"',
            f'timestamp<="{stamp(end)}"',
            f'httpRequest.status>={minimum_status}',
            f'httpRequest.status<{maximum_status}',
        ]
        if route is not None:
            # Policy paths contain only literal RE2 characters. Cloud Logging can zero-match escaped hyphens.
            path = r"^https?://[^/?#]+" + route["path"] + r"/?(?:[?#]|$)"
            filters.extend(
                (f'httpRequest.requestMethod="{route["method"]}"', f'httpRequest.requestUrl =~ {json.dumps(path)}')
            )
        body = {
            "resourceNames": [f"{project}/locations/global/buckets/_Default/views/_AllLogs"],
            "filter": " AND ".join(filters),
            "pageSize": LOG_PAGE_SIZE,
        }
        result = {revision: {} for revision in revisions}
        seen_tokens = set()
        while self.log_pages_left:
            self.log_pages_left -= 1
            response = self.request(
                "https://logging.googleapis.com/v2/entries:list",
                {"fields": "entries(resource/labels,httpRequest/status),nextPageToken"},
                body,
            )
            for row in response.get("entries", []):
                revision = row["resource"]["labels"]["revision_name"]
                status = row["httpRequest"]["status"]
                if type(status) is not int or not (minimum_status <= status < maximum_status):
                    raise ValueError("invalid Logging status")
                counts = result[revision]
                counts[status] = counts.get(status, 0) + 1
            token = response.get("nextPageToken")
            if not token:
                return result
            if token in seen_tokens:
                raise ValueError("repeated Logging page")
            seen_tokens.add(token)
            body["pageToken"] = token
        raise LogPageBudgetExceeded("Logging page budget exhausted")


def read_window(
    service,
    candidate,
    inverse,
    start,
    end,
    *,
    project="based-hardware",
    region="us-central1",
    route_names=None,
    reader=None,
):
    policy = policy_for(service, route_names)
    if (
        not all(NAME.fullmatch(name) for name in (project, region, candidate, inverse))
        or not all(name.startswith(service + "-") for name in (candidate, inverse))
        or candidate == inverse
    ):
        raise ValueError("invalid project, region or revision pair")
    if start % 60 or end % 60 or not 300 <= end - start <= 3600:
        raise ValueError("invalid window")
    identity = {
        "service": service,
        "project": project,
        "region": region,
        "candidate": candidate,
        "inverse": inverse,
        "window": f"{stamp(start)}/{stamp(end)}",
    }
    unavailable = dict(identity, verdict="INSUFFICIENT_DATA", checks={})
    if end + policy["settle_seconds"] > time.time():
        return dict(unavailable, reason="window_not_settled")
    telemetry = Telemetry(reader or Reader("/dev/null", "", time.monotonic() + 120), project, region)
    try:
        counts = telemetry.service_counts(service, candidate, inverse, start, end)
        logs = telemetry.log_counts(service, (candidate, inverse), start, end, 400, 600)
        needs_log_total = tuple(
            revision
            for revision, classes in counts.items()
            if sum(value for status, value in logs[revision].items() if status >= 500) > sum(classes.values())
        )
        if needs_log_total:
            successes = telemetry.log_counts(service, needs_log_total, start, end, 200, 400)
            for revision, statuses in successes.items():
                logs[revision].update(statuses)
        inputs = {
            name: {"service": series, "service_logs": logs[name], "routes": {}} for name, series in counts.items()
        }
        if service_population(inputs[inverse], log_weights(policy)).requests:
            for name, route in policy["routes"].items():
                statuses = telemetry.route_counts(service, candidate, inverse, start, end, route)
                for revision, aggregate in statuses.items():
                    inputs[revision]["routes"][name] = aggregate
        return dict(identity, **evaluate(policy, inputs[candidate], inputs[inverse]))
    except (TimeoutExpired, TimeoutError):
        return dict(unavailable, reason="telemetry_timeout")
    except (OSError, Refused, TypeError, ValueError, KeyError, AttributeError, OverflowError) as error:
        reason = "telemetry_unreadable"
        if isinstance(error, urllib.error.HTTPError):
            reason = f"telemetry_http_{error.code}"
        elif isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError):
            reason = "telemetry_timeout"
        elif isinstance(error, LogPageBudgetExceeded):
            reason = "telemetry_log_page_budget"
        return dict(unavailable, reason=reason)


def print_summary(result, stream):
    def rate(value):
        return "-" if value is None else f"{value:.3%}"

    print(f'{result["service"]} {result["window"]} {result["verdict"]}', file=stream)
    if result.get("reason"):
        print(result["reason"], file=stream)
    if result["verdict"] == "NO_COMPARATOR":
        print("Service counts before refusal adjustment", file=stream)
    if result["checks"]:
        print("Scope                 Cand req   Inv req  Cand 5xx   Inv 5xx  Cand 4xx   Inv 4xx  Verdict", file=stream)
    for name, row in result["checks"].items():
        c, i = row["candidate"], row["inverse"]
        print(
            f'{name:21} {c["requests"]:8.0f} {i["requests"]:9.0f} '
            f'{rate(c["5xx_rate"]):>9} {rate(i["5xx_rate"]):>9} '
            f'{rate(c["4xx_rate"]):>9} {rate(i["4xx_rate"]):>9}  {row["verdict"]}',
            file=stream,
        )
        for side, population in (("candidate", c), ("inverse", i)):
            if note := population.get("population_note"):
                print(f"  {name} {side}: {note}", file=stream)


def main(argv=None, *, reader=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--inverse", required=True)
    parser.add_argument("--window", required=True, metavar="START/END")
    parser.add_argument("--routes", nargs="*", help="required route names from cloud-run-guard.json")
    parser.add_argument("--project", default="based-hardware")
    parser.add_argument("--region", default="us-central1")
    args = parser.parse_args(argv)
    try:
        start, end = parse_window(args.window)
        result = read_window(
            args.service,
            args.candidate,
            args.inverse,
            start,
            end,
            project=args.project,
            region=args.region,
            route_names=args.routes,
            reader=reader,
        )
    except (KeyError, ValueError, TypeError, OSError, OverflowError):
        parser.error("invalid service, revision pair, routes, window or policy")
    print(json.dumps(result, sort_keys=True))
    print_summary(result, sys.stderr)
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
