#!/usr/bin/env python3
"""Validate experiment specs and render reviewable, inactive PostHog API plans.

Dry run is the default and requires no credentials or network. --apply creates
only inactive, zero-rollout flags and experiment drafts. Existing versions are
immutable: exact matches are reused; active trials, foreign ownership and drift
are refused. Management credentials are read only from the environment.
"""
import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
import re

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")


def validate(spec, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    for field in ("key", "owner", "hypothesis", "default_variant", "expires_at"):
        if not isinstance(spec.get(field), str) or not spec[field].strip():
            raise ValueError(f"Missing {field}")
    if not IDENTIFIER.fullmatch(spec["key"]) or type(spec.get("version")) is not int or spec["version"] < 1:
        raise ValueError("Invalid key/version")
    if spec.get("status") != "draft":
        raise ValueError("Only draft specs are accepted")
    for field in ("surfaces",):
        if not isinstance(spec.get(field), list) or not spec[field] or not all(
            isinstance(v, str) and IDENTIFIER.fullmatch(v) for v in spec[field]
        ):
            raise ValueError(f"Invalid {field}")
    if not isinstance(spec.get("guardrails"), list) or not spec["guardrails"]:
        raise ValueError("Guardrails required")
    metrics = [spec.get("primary_metric")] + spec["guardrails"]
    registry_path = Path(__file__).parents[3] / "contracts/analytics/events.json"
    registry = json.loads(registry_path.read_text())
    registered = {event["wire_name"]: event for event in registry["events"]}
    for metric in metrics:
        if not isinstance(metric, dict) or metric.get("event") not in registered or not isinstance(metric.get("filters"), dict):
            raise ValueError("Metric requires registered event and explicit filters")
        properties = {prop["wire_name"]: prop for prop in registered[metric["event"]]["properties"].values()}
        for key, value in metric["filters"].items():
            if key not in properties or ("values" in properties[key] and value not in properties[key]["values"]):
                raise ValueError("Metric filter is not in the event contract")
    expiry = dt.datetime.fromisoformat(spec["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= now:
        raise ValueError("Expiry must be a future timestamp with timezone")
    targeting = spec.get("targeting", {})
    namespaces = targeting.get("namespaces", [])
    if not namespaces or not isinstance(namespaces, list) or not all(
        namespace in ("mobile-dev", "mobile-prod") for namespace in namespaces
    ):
        raise ValueError("Explicit mobile namespace targeting required")
    if type(targeting.get("minimum_build")) is not int or targeting["minimum_build"] < 0:
        raise ValueError("Explicit minimum build required")
    variants = spec.get("variants", [])
    if not isinstance(variants, list) or not 2 <= len(variants) <= 8:
        raise ValueError("Expected 2 to 8 variants")
    keys = []
    for variant in variants:
        key, weight = variant.get("key"), variant.get("rollout_percentage")
        if not isinstance(key, str) or not IDENTIFIER.fullmatch(key) or type(weight) not in (int, float) or not 0 < weight <= 100:
            raise ValueError("Invalid variant key or allocation")
        keys.append(key)
    if len(set(keys)) != len(keys) or spec["default_variant"] not in keys or abs(sum(v["rollout_percentage"] for v in variants) - 100) > 0.0001:
        raise ValueError("Variants must be unique, include default, and total 100 percent")
    collision = spec.get("collision_policy")
    if collision not in ("independent", "server-layer"):
        raise ValueError("Explicit collision policy required")
    if collision == "server-layer" and not IDENTIFIER.fullmatch(spec.get("layer", "")):
        raise ValueError("Server-layer policy needs registered layer key")
    analysis = spec.get("analysis", {})
    if analysis.get("exposure_event") != "experiment_exposed" or analysis.get("unit") != "distinct_id" or \
            type(analysis.get("conversion_window_hours")) is not int or not 1 <= analysis["conversion_window_hours"] <= 168:
        raise ValueError("Exposure, analysis unit and bounded conversion window required")
    return spec


MANAGED_BY = "omi-mobile-experiments-v1"
ALLOWED_HOSTS = {"https://us.posthog.com", "https://eu.posthog.com", "https://app.posthog.com"}


def event_filters(filters):
    return [{"key": key, "type": "event", "operator": "exact", "value": value}
            for key, value in sorted(filters.items())]


def metric_payload(metric, spec, index, goal):
    """The experiment exposure is automatically prepended to each funnel."""
    return {"kind": "ExperimentMetric", "metric_type": "funnel",
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"omi:{spec['key']}:{spec['version']}:{index}")),
            "name": metric.get("name") or f"{metric['event']}: " + ", ".join(
                f"{key}={value}" for key, value in sorted(metric["filters"].items())),
            "goal": goal, "conversion_window": spec["analysis"]["conversion_window_hours"],
            "conversion_window_unit": "hour",
            "series": [{"kind": "EventsNode", "event": metric["event"],
                        "properties": event_filters({**metric["filters"], "experiment_context_verified": True,
                            f"$feature/{spec['key']}": [variant["key"] for variant in spec["variants"]]})}]}


def plan(spec, project_id, now=None):
    validate(spec, now)
    if not re.fullmatch(r"[1-9][0-9]*", str(project_id)):
        raise ValueError("Explicit numeric PostHog project ID required")
    targeting = spec["targeting"]
    properties = [
        {"key": "experiment_namespace", "type": "person", "operator": "exact", "value": targeting["namespaces"]},
        {"key": "app_build", "type": "person", "operator": "gte", "value": targeting["minimum_build"]},
    ]
    marker = f"[{MANAGED_BY}:{spec['key']}:{spec['version']}]"
    flag = {"key": spec["key"], "name": marker + " " + spec["hypothesis"], "active": False,
            "filters": {"groups": [{"properties": properties, "rollout_percentage": 0}],
                        "multivariate": {"variants": spec["variants"]}}}
    experiment = {
        "name": spec["key"],
        "description": json.dumps({"managed_by": MANAGED_BY, "key": spec["key"],
                                   "version": spec["version"], "spec": spec}, sort_keys=True),
        "feature_flag_key": spec["key"], "type": "product", "start_date": None, "end_date": None,
        "metrics": [metric_payload(spec["primary_metric"], spec, "primary", "increase")],
        "metrics_secondary": [metric_payload(metric, spec, f"guardrail-{index}", "decrease")
                              for index, metric in enumerate(spec["guardrails"])],
        "exposure_criteria": {"filterTestAccounts": True, "multiple_variant_handling": "exclude",
                              "exposure_config": {"kind": "ExperimentEventExposureConfig",
                                                  "event": "experiment_exposed",
                                                  "properties": event_filters({"experiment_key": spec["key"],
                                                      "experiment_version": spec["version"], "experiment_qa": False})}},
    }
    return {"dry_run": True, "project_id": str(project_id), "spec": spec,
            "requests": [{"method": "POST", "path": f"/api/projects/{project_id}/feature_flags/", "body": flag},
                         {"method": "POST", "path": f"/api/projects/{project_id}/experiments/", "body": experiment}],
            "before_launch": ["Read back inactive flag and draft metric/exposure configuration in the intended project.",
                              "Verify registry parity, namespace/build targeting, sample size, stop rules and expiry.",
                              "Configure the disabled-by-default mobile-experiments-enabled gate and any server layer.",
                              "Run synthetic QA and separately authorize activation; this tool cannot launch."]}


class ProvisionError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProvisionError("Management API redirect refused")


class ManagementApi:
    def __init__(self, host, project_id, token):
        if host not in ALLOWED_HOSTS or not re.fullmatch(r"[1-9][0-9]*", str(project_id)):
            raise ProvisionError("Expected explicit PostHog cloud management host and numeric project")
        if not token:
            raise ProvisionError("POSTHOG_PERSONAL_API_KEY environment variable required for --apply")
        self.host = host
        self.prefix = f"/api/projects/{project_id}/"
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, body=None):
        parsed = urllib.parse.urlsplit(urllib.parse.urljoin(self.host, path))
        if (parsed.scheme + "://" + parsed.netloc != self.host or not parsed.path.startswith(self.prefix)
                or parsed.fragment or parsed.username or parsed.password):
            raise ProvisionError("Management request escaped selected project/host")
        if method not in ("GET", "POST") or (method == "POST" and parsed.path not in (
                self.prefix + "experiments/", self.prefix + "feature_flags/")):
            raise ProvisionError("Only reads and inactive draft creation are supported")
        if method == "POST":
            if parsed.path.endswith("feature_flags/") and (body.get("active") is not False or
                    any(group.get("rollout_percentage") != 0 for group in body.get("filters", {}).get("groups", []))):
                raise ProvisionError("Flag activation refused")
            if parsed.path.endswith("experiments/") and (body.get("start_date") is not None or
                    body.get("end_date") is not None or body.get("scheduling_config")):
                raise ProvisionError("Experiment launch/scheduling refused")
        url = urllib.parse.urlunsplit(parsed)
        request = urllib.request.Request(url, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status not in (200, 201):
                    raise ProvisionError(f"Management API returned HTTP {response.status}")
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Never print token, request body, customer/project response contents.
            raise ProvisionError(f"Management API returned HTTP {error.code}; no retry attempted") from None
        except (urllib.error.URLError, TimeoutError):
            raise ProvisionError("Management request failed; rerun to discover partial completion") from None

    def all(self, path):
        result, seen = [], set()
        while path:
            if path in seen or len(seen) >= 1000:
                raise ProvisionError("Invalid or excessive pagination")
            seen.add(path)
            page = self.request("GET", path)
            if not isinstance(page, dict) or not isinstance(page.get("results"), list):
                raise ProvisionError("Malformed management listing")
            result.extend(page["results"])
            path = page.get("next")
        return result


def subset_equal(actual, expected):
    """Allow server-added defaults without hiding changes to owned fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and subset_equal(actual[key], value)
                                               for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            subset_equal(a, e) for a, e in zip(actual, expected))
    if type(actual) in (int, float) and type(expected) in (int, float):
        return actual == expected
    return type(actual) is type(expected) and actual == expected


def require_safe_flag(flag, expected):
    if flag.get("active") is not False or flag.get("deleted") is True:
        raise ProvisionError("Existing active/deleted flag is immutable; choose a new experiment key/version")
    if not subset_equal(flag, expected):
        raise ProvisionError("Existing flag ownership/configuration differs; refusing to overwrite")


def require_safe_experiment(experiment, expected):
    if (experiment.get("status") != "draft" or experiment.get("start_date") is not None or
            experiment.get("end_date") is not None or experiment.get("archived") or experiment.get("deleted") or
            experiment.get("scheduling_config")):
        raise ProvisionError("Existing launched/archived/scheduled experiment is immutable")
    if not subset_equal(experiment, expected):
        raise ProvisionError("Existing experiment version/ownership/configuration differs; refusing to overwrite")


def reconcile(draft, api):
    """Create-only reconciliation is restartable after partial completion.

    Existing versioned drafts are immutable. Configuration drift requires a new
    reviewed key/version, preventing concurrent launch races from being patched.
    """
    flag_request, experiment_request = draft["requests"]
    flag_body, experiment_body = flag_request["body"], experiment_request["body"]
    key = draft["spec"]["key"]
    # Discover both fully before any mutation; a running trial must never be reset.
    all_experiments = {}
    for archived in ("false", "true"):
        for item in api.all(experiment_request["path"] + f"?status=all&archived={archived}"):
            all_experiments[item["id"]] = item
    experiments = [item for item in all_experiments.values() if item.get("feature_flag_key") == key]
    flags = [item for item in api.all(flag_request["path"]) if item.get("key") == key]
    if len(experiments) > 1 or len(flags) > 1:
        raise ProvisionError("Duplicate experiment/flag keys; manual investigation required")
    experiment = None
    if experiments:
        experiment = api.request("GET", experiment_request["path"] + str(experiments[0]["id"]) + "/")
        require_safe_experiment(experiment, experiment_body)
    flag = None
    if flags:
        flag = api.request("GET", flag_request["path"] + str(flags[0]["id"]) + "/")
        require_safe_flag(flag, flag_body)
    if experiment and not flag:
        raise ProvisionError("Existing experiment has no matching inactive flag")
    created = []
    if flag is None:
        flag = api.request("POST", flag_request["path"], flag_body)
        created.append("flag")
        flag = api.request("GET", flag_request["path"] + str(flag["id"]) + "/")
        require_safe_flag(flag, flag_body)
    if experiment is None:
        # Read again immediately before binding the flag, without mutating it.
        require_safe_flag(api.request("GET", flag_request["path"] + str(flag["id"]) + "/"), flag_body)
        experiment = api.request("POST", experiment_request["path"], experiment_body)
        created.append("experiment")
    verified = api.request("GET", experiment_request["path"] + str(experiment["id"]) + "/")
    require_safe_experiment(verified, experiment_body)
    require_safe_flag(api.request("GET", flag_request["path"] + str(flag["id"]) + "/"), flag_body)
    return {"dry_run": False, "project_id": draft["project_id"], "key": key,
            "version": draft["spec"]["version"], "created": created,
            "experiment_id": experiment["id"], "flag_id": flag["id"], "verified_status": "draft",
            "verified_flag_active": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--host", choices=sorted(ALLOWED_HOSTS))
    parser.add_argument("--apply", action="store_true", help="Create inactive drafts; never launch or modify existing versions")
    args = parser.parse_args()
    try:
        draft = plan(json.loads(args.spec.read_text()), args.project_id)
        if args.apply:
            if not args.host:
                raise ProvisionError("--apply requires explicit --host")
            api = ManagementApi(args.host, args.project_id, os.environ.get("POSTHOG_PERSONAL_API_KEY", ""))
            result = reconcile(draft, api)
        else:
            result = draft
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Experiment provisioning refused: {error}\n")


if __name__ == "__main__":
    main()
