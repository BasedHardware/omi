#!/usr/bin/env python3
"""Render backend/docs/feature-flag-registry.md from config/feature-flags.yaml.

Deterministic: the as-of date comes from --as-of or the committed doc's own
header marker, never from wall-clock time, so CI drift checks are stable.
"""

from __future__ import annotations

import argparse

from feature_flag_parser_defaults import parser_defaults
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from run_checks import _parse_yaml_subset

DOC_PATH = "backend/docs/feature-flag-registry.md"
REGISTRY_PATH = "config/feature-flags.yaml"
AS_OF = re.compile(r"<!-- feature-flag-registry as-of: (\d{4}-\d{2}-\d{2}) -->")
GENERATED_NOTICE = (
    "GENERATED from `config/feature-flags.yaml` by `scripts/render_feature_flag_registry.py`; do not edit."
)
LIFECYCLES = ("experiment", "rollout", "ops_kill", "config_switch")


def _unquote(value: str) -> str:
    value = value.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _parse_mapping(text: str) -> dict[str, Any]:
    """Indentation-aware parse of the manifest's mapping-only subset.

    List items and comments are skipped; env maps in the runtime_env sources
    are pure ``key:`` / ``key: value`` mappings, which is all we need.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    anchors: dict[str, dict[str, Any]] = {}
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("- "):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not isinstance(parent, dict):
            continue
        if key == "<<":
            # Shared cohort overlays use a JSON-compatible flow mapping anchor
            # and merge aliases so one data edit updates every serving host.
            if rest.startswith("&"):
                anchor, literal = rest[1:].split(" ", 1)
                anchors[anchor] = json.loads(literal)
                parent.update(anchors[anchor])
            elif rest.startswith("*"):
                parent.update(anchors[rest[1:]])
            else:
                raise ValueError(f"unsupported mapping merge: {rest}")
        elif rest == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _unquote(rest)
    return root


def _env_token(entry: Any) -> str:
    """Literal value, or the declaration kind when no literal is present."""
    if isinstance(entry, dict):
        if "value" in entry:
            return str(entry["value"])
        for ref in ("config_map", "env_var", "secret", "secret_ref"):
            if ref in entry:
                return ref
        return "declared"
    return str(entry)


def _manifest_envs(path: Path) -> dict[str, dict[str, str]]:
    """host label -> {env key: token} for every env: map in a runtime_env source."""
    if not path.is_file():
        return {}
    tree = _parse_mapping(path.read_text(encoding="utf-8"))
    shared = tree.get("environment_shared") or tree.get("overlay") or {}
    if not isinstance(shared, dict):
        return {}
    hosts: dict[str, dict[str, str]] = {}

    def grab(container: Any, key: str, label: str) -> None:
        body = container.get(key) if isinstance(container, dict) else None
        env = body.get("env") if isinstance(body, dict) else None
        if isinstance(env, dict):
            hosts[label] = {name: _env_token(entry) for name, entry in env.items()}

    gke = shared.get("gke")
    if isinstance(gke, dict):
        for service in gke:
            grab(gke, service, f"gke/{service}")
    grab(shared, "desktop_backend", "desktop-backend")
    cloud_run = shared.get("cloud_run")
    if isinstance(cloud_run, dict):
        services = cloud_run.get("services")
        if isinstance(services, dict):
            for name in services:
                grab(services, name, f"cloud_run/{name}")
        jobs = cloud_run.get("jobs")
        if isinstance(jobs, dict):
            for name in jobs:
                grab(jobs, name, f"job/{name}")
    return hosts


def _effective_envs(base: dict[str, dict[str, str]], overlay: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Effective per-host env for one environment: base inheritance + overlay."""
    merged: dict[str, dict[str, str]] = {host: dict(env) for host, env in base.items()}
    for host, env in overlay.items():
        merged.setdefault(host, {}).update(env)
    return merged


_CHART_NAME = re.compile(r"^\s*-\s*name:\s*['\"]?([A-Za-z0-9_.\-]+)['\"]?\s*$")
_ACTION_ASSIGNMENT = re.compile(r"^\s*([A-Z][A-Z0-9_]+)=([^,\s]+)")
_ACTION_ENV_ARG = re.compile(r"--(?:update|set)-env-vars(?:=|\s+)(?:\"([^\"]*)\"|'([^']*)'|([^\s\\]+))", re.S)


def _chart_envs(path: Path) -> dict[str, str]:
    """env list records of one chart values file: {env key: token}."""
    if not path.is_file():
        return {}
    envs: dict[str, str] = {}
    in_env = False
    current: str | None = None
    name_indent = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            in_env = stripped == "env:" or stripped.startswith("env: ")
            current = None
            continue
        if not in_env:
            continue
        match = _CHART_NAME.match(raw)
        if match and indent <= name_indent + 2:
            current = match[1]
            name_indent = indent
            envs[current] = "declared"
            continue
        if current is not None and indent == name_indent + 2:
            field, _, rest = stripped.partition(":")
            field = field.strip()
            if field == "value":
                envs[current] = _unquote(rest)
            elif field == "valueFrom":
                envs[current] = "valueFrom"
    return envs


def _action_envs(path: Path) -> dict[str, str]:
    """Literal env overlays emitted by deploy actions or workflow gcloud calls."""
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    envs: dict[str, str] = {}
    for match in _ACTION_ENV_ARG.finditer(text):
        payload = next((value for value in match.groups() if value is not None), "")
        for item in payload.replace("\\\n", "").split(","):
            key, separator, value = item.partition("=")
            key = key.strip()
            if separator and re.fullmatch(r"[A-Z][A-Z0-9_]+", key):
                envs[key] = _unquote(value.strip()) or "declared"
    # The sync-backfill composite action publishes a small, literal output map
    # which is merged into the deployed service's cloned runtime contract.
    if path.as_posix().endswith(".github/actions/sync-backfill-lifecycle/action.yml"):
        in_output = False
        for raw in text.splitlines():
            if 'echo "sync_backfill_env_vars<<EOF"' in raw:
                in_output = True
                continue
            if in_output and 'echo "EOF"' in raw:
                break
            if in_output:
                match = _ACTION_ASSIGNMENT.match(raw.strip().removeprefix('echo "').removesuffix('"'))
                if match:
                    envs[match[1]] = match[2]
    return envs


def _deploy_index(root: Path) -> dict[str, dict[str, dict[str, str]]]:
    """scope -> host label -> {env key: token} for base/dev/prod plus charts."""
    deploy_dir = root / "backend" / "deploy" / "runtime_env"
    base = _manifest_envs(deploy_dir / "_base.yaml")
    result: dict[str, dict[str, dict[str, str]]] = {"base": dict(base)}
    for env in ("dev", "prod"):
        overlay = _manifest_envs(deploy_dir / f"{env}.overlay.yaml")
        effective = _effective_envs(base, overlay)
        charts_dir = root / "backend" / "charts"
        if charts_dir.is_dir():
            for chart in sorted(p for p in charts_dir.iterdir() if p.is_dir()):
                for values in sorted(chart.glob(f"{env}_*values.yaml")):
                    envs = _chart_envs(values)
                    if envs:
                        effective[f"{chart.name} (chart)"] = envs
        actions_dir = root / ".github" / "actions"
        if actions_dir.is_dir():
            for action in sorted(actions_dir.rglob("action.yml")):
                envs = _action_envs(action)
                if envs:
                    effective[f"{action.parent.name} (action)"] = envs
        if env == "prod":
            workflows_dir = root / ".github" / "workflows"
            if workflows_dir.is_dir():
                for workflow in sorted(workflows_dir.glob("*prod*.y*ml")):
                    envs = _action_envs(workflow)
                    if envs:
                        effective[f"{workflow.stem} (action)"] = envs
        result[env] = effective
    return result


def _display(token: str) -> str:
    return "''" if token == "" else token


def _scope_cell(key: str, hosts: dict[str, dict[str, str]]) -> str:
    entries = [(host, env[key]) for host, env in sorted(hosts.items()) if key in env]
    if not entries:
        return "—"
    groups: dict[str, list[str]] = {}
    for host, token in entries:
        groups.setdefault(token, []).append(host)
    if len(groups) == 1 and not any(host.endswith(" (chart)") for host, _ in entries):
        return _display(next(iter(groups)))
    parts = [f"{_display(token)} ({', '.join(hosts)})" for token, hosts in sorted(groups.items())]
    return "; ".join(parts)


def _env_columns(key: str, index: dict[str, dict[str, dict[str, str]]]) -> tuple[str, str, str]:
    return (
        _scope_cell(key, index["base"]),
        _scope_cell(key, index["dev"]),
        _scope_cell(key, index["prod"]),
    )


def _md(text: object) -> str:
    return str(text).replace("|", "\\|")


def _posthog_cell(entry: dict[str, Any]) -> str:
    posthog = entry.get("posthog")
    if entry.get("kind") != "posthog" or not isinstance(posthog, dict):
        return "—"
    return f"{posthog.get('row')} ({posthog.get('role')})"


def _preamble() -> list[str]:
    return [
        "# Feature-flag authority registry",
        "",
        GENERATED_NOTICE,
        "",
        "Boolean `fail` fields for migrated switches are generated from the shared parser's",
        "missing-value policy. `CAPTURE_COVERAGE_MODE` off/shadow preserves the legacy token",
        "grammar; serve uses `refactor_modes.default_on/default_off`. Explicit child settings",
        "override repeat-work inheritance only in serve mode. Check with `--check-parsers`.",
        "",
        "Flipping a row here does not turn a feature on; PostHog / bundle identity /",
        "`runtime_env` remain the live levers. This file is a catalog of *which* lever",
        "owns each gate, not the switch itself.",
        "",
        "`terminal` records the reviewed end state: `on` graduates a feature, `off`",
        "kills it, `keep` retains an ops kill or config switch, and `undecided` means",
        "no terminal ruling is recorded yet.",
        "",
        "## Contributing registry rows",
        "",
        "Edit `config/feature-flags.yaml`, then regenerate this document with",
        "`python3 scripts/render_feature_flag_registry.py`. A `ramp` object is optional",
        "for existing rows. It is required for `lifecycle: rollout` rows that are",
        "pending (`decision: pending` or `terminal: undecided`) and created on or after",
        "2026-10-21. Include every field below; `done_by` must be on or before",
        "`review_by`.",
        "",
        "- `cohorts`: ordered rollout steps, ending in the full intended cohort;",
        "  a single-user step such as `David-only` cannot be terminal.",
        "- `clean_metric`: the metric that must stay clean before expansion.",
        "- `expander`: the session, role, or person responsible for each expansion.",
        "- `done_by`: the date the ramp reaches its final cohort.",
        "",
        "Example:",
        "",
        "```yaml",
        "ramp:",
        '  cohorts: ["release-probe", "1%", "5% 3h", "25%", "100%"]',
        '  clean_metric: "checkout_error_rate"',
        '  expander: "release-owner session"',
        '  done_by: "2026-11-15"',
        "```",
        "",
        "Rows created before the cutoff stay grandfathered when `ramp` is absent;",
        "the checker warns and reports their count. Do not backfill plans into them.",
        "",
        "This is **not** a second classification of deployment wiring. Secret vs config",
        "vs `public_build` still lives only in",
        "[`config/deployment-setting-classification.json`](../../config/deployment-setting-classification.json)",
        "and [`deployment-setting-classification.mdx`](deployment-setting-classification.mdx).",
        "## How to read the three authorities",
        "",
        "### Bundle identity",
        "",
        "Omi Beta (`com.omi.computer-macos.beta`) vs stable (`com.omi.computer-macos`).",
        "Use this for dogfood features whose backend half is only on the **dev** API:",
        "Beta is the only production-family identity that talks to that API",
        "(`DesktopBackendEnvironment.shouldForceDevelopmentServingEndpoints`). Stable",
        "stays dark until an explicit PostHog enable flag is true. Named/dev bundles",
        "are a third identity (non-production) and usually take a local `OMI_FORCE_*`",
        "override instead of PostHog.",
        "",
        "### PostHog (project 302298)",
        "",
        "Per-user, percent, or remote kill **without a new build**. The SDK",
        "(`PostHogManager.isFeatureEnabled`) is fail-closed while uninitialized: a",
        "missing row is `false`. That is why a Beta-by-default feature needs an",
        "**inverted kill** (`*_kill` true means off) so \"flag missing\" leaves Beta on,",
        "and why a dark production launch needs a **positive** enable flag so \"flag",
        "missing\" stays off.",
        "",
        "### `runtime_env`",
        "",
        "Whole environment or Cloud Run job, declared in",
        "`backend/deploy/runtime_env/{_base,dev.overlay,prod.overlay}.yaml`. Use this",
        "for fleet-wide backend switches. Do not put those in PostHog.",
        "",
        "The source of truth is the composed manifest (`backend/deploy/runtime_env.yaml`)",
        "plus the GKE listener/pusher values. A flag value in this registry describes",
        "repository capability, not a deployed or currently serving value.",
        "",
        "## Rules",
        "",
        "1. If Swift or Python names a PostHog key, the PostHog row must exist. A kill",
        "   row is armed-but-off only when it is **active with a single 0% rollout",
        "   group**; an inactive or absent row reads as unknown, and a missing kill",
        "   row cannot disarm a bad Beta.",
        "2. If a PostHog row exists and no code reads it for enablement, delete it",
        "   and put the name in `retired:` so the checker fails on reintroduction.",
        "3. Kill switches for Beta-by-default features must exist in PostHog as an",
        "   active row with one 0% rollout group, so a bad Beta can be disarmed",
        "   without a build.",
        "4. Do not put fleet-wide backend switches in PostHog.",
        "5. Do not put Beta-vs-stable enablement in PostHog person properties.",
        "   `update_channel` was measured unreliable (person-side channel null or",
        "   `stable` for most Beta installs). Bundle identity is the authority.",
        "",
        "`BetaDogfoodRollout` is the shared client shape: non-production requires an",
        "explicit `OMI_FORCE_*=1` (except where noted), Beta is on unless the kill is",
        "true, stable is on only when the enable flag is true.",
        "",
    ]


def _not_feature_flags(ignore: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Not feature flags",
        "",
        "Do not list these as rollout flags:",
        "",
        "- Flutter `OmiFeatures` hardware capability bits.",
        "- Integration-nudge UserDefaults opt-out (per-user preference, not a remote gate).",
        "- Local process overrides (`OMI_FORCE_*` and the bucket-pipeline",
        "  `OMI_FORCE_BUCKET_*` / `OMI_FORCE_DWELL_REFRESH` /",
        "  `OMI_FORCE_DEPARTURE_EVALUATION` / `OMI_FORCE_FACT_WRITE_POLICY` knobs).",
        "  Most are dev-only controls, but some (e.g. `OMI_FORCE_CLOUD_STT`,",
        "  `OMI_FORCE_NOTCH`) are deliberately honored by shipped builds. Either way",
        "  the `ignore:` row records the classification as a visible decision: local",
        "  environment data, never remote rollout authority.",
        "",
        "The registry `ignore:` block names every other intentional non-flag with its",
        "reason:",
        "",
        "| Key | Reason | owner | decision | review_by | notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in ignore:
        lines.append(
            f"| `{entry['key']}` | {entry['reason']} | {entry.get('owner', '—')} | "
            f"{entry.get('decision', '—')} | {entry.get('review_by', '—')} | {_md(entry.get('notes', '—'))} |"
        )
    lines.append("")
    return lines


def _render_ramp_plans(flags: list[dict[str, Any]]) -> list[str]:
    lines = ["## Rollout ramp plans", ""]
    ramped = [entry for entry in flags if isinstance(entry.get("ramp"), dict)]
    if ramped:
        lines += [
            "| key | cohorts | clean metric | expander | done_by |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in ramped:
            ramp = entry["ramp"]
            cohorts = " → ".join(str(step) for step in ramp.get("cohorts", []))
            lines.append(
                f"| `{entry['key']}` | {_md(cohorts)} | {_md(ramp.get('clean_metric', '—'))} | "
                f"{_md(ramp.get('expander', '—'))} | {ramp.get('done_by', '—')} |"
            )
    else:
        lines.append("(none)")
    lines.append("")
    return lines


def render(root: Path, registry: dict[str, list[dict[str, Any]]], as_of: date) -> str:
    """Render the registry doc for ``root`` as of ``as_of`` (never wall clock)."""
    index = _deploy_index(root)
    flags = sorted(registry.get("flags", []), key=lambda entry: entry["key"])

    lines = [f"<!-- feature-flag-registry as-of: {as_of.isoformat()} -->", ""]
    lines += _preamble()

    lines += ["## Running experiments", ""]
    experiments = [
        entry for entry in flags if entry.get("lifecycle") == "experiment" and entry.get("decision") != "kill"
    ]
    if experiments:
        lines += [
            "Every running experiment links its preregistration doc. `decision: kill`",
            "entries are exempt: they are queued for removal, not running.",
            "",
            "| key | terminal | owner | prereg | review_by |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in experiments:
            prereg = entry.get("prereg")
            prereg_cell = f"[{_md(prereg)}](../../{prereg})" if prereg else "—"
            review_by = entry.get("review_by", "—")
            if entry.get("review_by") and date.fromisoformat(entry["review_by"]) < as_of:
                review_by += " OVERDUE"
            lines.append(
                f"| `{entry['key']}` | {entry['terminal']} | {_md(entry['owner'])} | {prereg_cell} | {review_by} |"
            )
    else:
        lines.append("(none)")
    lines.append("")

    lines += ["## Overdue for a decision", ""]
    overdue = [
        entry
        for entry in flags
        if entry.get("lifecycle") in {"experiment", "rollout"}
        and entry.get("review_by")
        and date.fromisoformat(entry["review_by"]) < as_of
    ]
    if overdue:
        lines += [
            "These rollout/experiment entries passed `review_by`. The checker warns",
            "during the seven-day grace, then fails unless a dated `review_overdue`",
            "exception is recorded for David.",
            "",
        ]
        for entry in overdue:
            lines.append(f"- `{entry['key']}` — review_by {entry['review_by']} ({_md(entry['owner'])})")
    else:
        lines.append(f"None as of {as_of.isoformat()}.")
    lines.append("")

    lines += [
        "## Flags",
        "",
        "`_base`, `dev`, and `prod` show declared literals from `runtime_env`",
        "(`dev`/`prod` are `_base` inheritance plus the environment overlay). Chart",
        "values and deploy-action env overlays appear as extra sources suffixed",
        "`(chart)` and `(action)` and never mask runtime",
        "differences; differing values list their hosts. A declaration without a",
        "literal (`config_map`, `env_var`, `secret`, `valueFrom`) counts as declared,",
        "and an explicit empty literal renders as `''`.",
        "",
    ]
    for lifecycle in LIFECYCLES:
        rows = [entry for entry in flags if entry.get("lifecycle") == lifecycle]
        lines += [f"### {lifecycle}", ""]
        if not rows:
            lines += ["(none)", ""]
            continue
        lines += [
            "| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | terminal | review_by | owner |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for entry in rows:
            surfaces = ", ".join(entry.get("surfaces", []))
            review_by = entry.get("review_by", "—")
            base, dev, prod = _env_columns(entry["key"], index) if entry.get("kind") == "env" else ("—", "—", "—")
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{entry['key']}`",
                        _md(entry["summary"]),
                        _md(surfaces),
                        entry["kind"],
                        entry["fail"],
                        _md(base),
                        _md(dev),
                        _md(prod),
                        _posthog_cell(entry),
                        entry["decision"],
                        entry["terminal"],
                        review_by,
                        _md(entry["owner"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines += _render_ramp_plans(flags)

    lines += ["## Undeclared env flags", ""]
    undeclared = [
        entry
        for entry in flags
        if entry.get("kind") == "env"
        and all(entry["key"] not in env for scope in index.values() for env in scope.values())
    ]
    if undeclared:
        lines += [
            "Env flags with no declaration in `runtime_env` or any chart; they run on",
            "their code default (`fail` tells you which way a missing value resolves).",
            "",
        ]
        for entry in undeclared:
            lines.append(f"- `{entry['key']}` — {entry['summary']} (fail: {entry['fail']})")
    else:
        lines.append("None.")
    lines.append("")

    lines += _not_feature_flags(registry.get("ignore", []))

    lines += ["## Retired names — do not reuse", ""]
    retired = registry.get("retired", [])
    if retired:
        lines += [
            "Code was deleted but an external row may still exist. Names cover PostHog",
            "keys, env switches, and shipped local preference keys; the sync reports live PostHog",
            "leftovers as read-only delete candidates. Never re-read these names for",
            "admission.",
            "",
            "| Key | Retired | Reason |",
            "| --- | --- | --- |",
        ]
        for entry in retired:
            lines.append(f"| `{entry['key']}` | {entry['retired']} | {entry['reason']} |")
    else:
        lines.append("None.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--as-of", dest="as_of", help="YYYY-MM-DD; required on first render")
    parser.add_argument(
        '--check-parsers', action='store_true', help='Check migrated boolean fail fields without writing'
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if args.as_of:
        as_of = date.fromisoformat(args.as_of)
    else:
        doc = root / DOC_PATH
        text = doc.read_text(encoding="utf-8") if doc.is_file() else ""
        match = AS_OF.search(text)
        if match is None:
            print(
                f"{DOC_PATH}: no committed as-of header; pass --as-of YYYY-MM-DD for the first render",
                file=sys.stderr,
            )
            return 2
        as_of = date.fromisoformat(match[1])

    registry_path = root / REGISTRY_PATH
    defaults = parser_defaults(root)
    original = registry_path.read_text(encoding='utf-8')
    updated = []
    mismatches = []
    for line in original.splitlines(keepends=True):
        match = re.search(r'"key"\s*:\s*"([A-Z0-9_]+)"', line)
        if match and match[1] in defaults:
            expected = defaults[match[1]]
            declared = re.search(r'"fail"\s*:\s*"(open|closed)"', line)
            if declared is None:
                raise ValueError(f"{match[1]}: missing or invalid fail field")
            if declared[1] != expected:
                mismatches.append(match[1])
                line = line[: declared.start(1)] + expected + line[declared.end(1) :]
        updated.append(line)
    if args.check_parsers:
        if mismatches:
            print('parser fail field mismatch: ' + ', '.join(mismatches), file=sys.stderr)
            return 1
        print(f'checked {len(defaults)} migrated boolean parser defaults')
        return 0
    registry_path.write_text(''.join(updated), encoding='utf-8')
    registry = _parse_yaml_subset(registry_path)
    rendered = render(root, registry, as_of)
    doc = root / DOC_PATH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(rendered, encoding="utf-8")
    print(f"wrote {DOC_PATH} (as-of {as_of.isoformat()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
