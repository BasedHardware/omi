#!/usr/bin/env python3
"""Compile CV1 simulator scenarios into bench-jig gesture plans.

The simulator (omi/firmware/omi/sim) and the bench jig share one source of
truth for gestures: the scenario YAML timeline. This tool turns the subset of a
scenario a jig can physically perform -- the user button (driven through a GPIO
fixture), the charger (a switched 5 V relay) and battery power (a relay in the
cell or supply line) -- into a timed action plan, and executes that plan
through a pluggable adapter.

No hardware adapter ships here. The default adapter is a dry run that prints
the plan with its timing; the `command` adapter runs one argv per action from a
private bench profile (JSON, outside the repository), for example a GPIO tool
or a relay controller CLI. This module never discovers, opens or flashes a
device by itself.

  python3 omi/firmware/tools/cv1/jig_gestures.py plan safe/poweron-hold-then-cold-boot
  python3 omi/firmware/tools/cv1/jig_gestures.py matrix --json
  python3 omi/firmware/tools/cv1/jig_gestures.py run safe/... --adapter command --profile ~/bench/jig.json

Scenario events with no physical counterpart (kernel panics, injected settings
or SD faults, app mute writes, scripted battery voltage, BLE connection state,
retained-RAM options) make a scenario simulator-only; `plan` refuses them and
`matrix` lists them as such.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

SIM = Path(__file__).resolve().parents[2] / "omi" / "sim"
SCENARIOS = SIM / "scenarios"
sys.path.insert(0, str(SIM))
import power_model  # noqa: E402

ACTIONS = ("button_press", "button_release", "charger_on", "charger_off", "power_off", "power_on")
# A power relay must stay open long enough for the rails and retained RAM to
# discharge; the simulator's default off gap (initial power_off_ms) is the same.
COLD_GAP_MS = 500
PHYSICAL_INITIAL = {"charging", "power_off_ms"}


class NotPhysical(ValueError):
    """The scenario needs a simulator-only stimulus."""


def plan(scenario):
    """Return [(t_ms, action)] for a loaded scenario, or raise NotPhysical."""
    reasons = []
    if scenario.get("faults"):
        reasons.append("injected faults")
    if scenario.get("build", "default") != "default":
        reasons.append(f"dev build {scenario['build']!r}")
    extra = set(scenario.get("initial", {})) - PHYSICAL_INITIAL - {"button"}
    extra -= {k for k, v in scenario.get("initial", {}).items() if not v}
    if extra:
        reasons.append("initial " + ", ".join(sorted(extra)))
    steps = [(0, "power_on")]
    if scenario.get("initial", {}).get("charging"):
        steps.insert(0, (0, "charger_on"))
    gap = int(scenario.get("initial", {}).get("power_off_ms", COLD_GAP_MS))
    for event in scenario["events"]:
        t, kind, value = event[:3]
        if kind == "button":
            steps.append((t, "button_press" if value else "button_release"))
        elif kind == "charger":
            steps.append((t, "charger_on" if value else "charger_off"))
        elif kind == "power" and value == "cycle":
            steps += [(t, "power_off"), (t + gap, "power_on")]
        else:
            reasons.append(f"{kind}={value!r} at {t} ms")
    if reasons:
        raise NotPhysical("; ".join(reasons))
    order = {name: i for i, name in enumerate(ACTIONS)}
    # Stable: same-instant actions keep timeline order, except a charger change
    # lands before a press at the same instant (the firmware samples both).
    return sorted(steps, key=lambda s: (s[0], 0 if s[1].startswith("charger") else 1, order[s[1]]))


def load(selector):
    files = power_model.discover(SCENARIOS, [selector])
    if len(files) != 1:
        raise SystemExit(f"{selector!r} matches {len(files)} scenarios; name exactly one")
    return power_model.load_scenario(files[0], SCENARIOS)


def matrix():
    rows = []
    for path in power_model.discover(SCENARIOS):
        scenario = power_model.load_scenario(path, SCENARIOS)
        try:
            steps = plan(scenario)
            rows.append({"id": scenario["id"], "jig": True, "steps": len(steps), "end_ms": scenario["end"]})
        except NotPhysical as exc:
            rows.append({"id": scenario["id"], "jig": False, "reason": str(exc)})
    return rows


class DryRun:
    def __init__(self, out=sys.stdout):
        self.out = out

    def __call__(self, action):
        print(f"  {action}", file=self.out, flush=True)


class Command:
    """Runs profile[action] (an argv list) per action; nothing else."""

    def __init__(self, profile):
        data = json.loads(Path(profile).expanduser().read_text())
        missing = [a for a in ACTIONS if not isinstance(data.get(a), list) or not data[a]]
        if missing:
            raise SystemExit(f"jig profile lacks argv for: {', '.join(missing)}")
        self.argv = {a: [str(x) for x in data[a]] for a in ACTIONS}

    def __call__(self, action):
        subprocess.run(self.argv[action], check=True, timeout=10)


def execute(steps, end_ms, adapter, clock=time.monotonic, sleep=time.sleep, out=sys.stdout):
    """Fire each action at its offset; returns the receipt rows with lateness."""
    start = clock()
    receipt = []
    pressed = False
    try:
        for t, action in steps:
            delay = start + t / 1000 - clock()
            if delay > 0:
                sleep(delay)
            late = max(0.0, (clock() - start) * 1000 - t)
            print(f"{t:>8} ms (+{late:.0f}) {action}", file=out, flush=True)
            adapter(action)
            pressed = action == "button_press" or (pressed and action != "button_release")
            receipt.append({"t_ms": t, "action": action, "late_ms": round(late, 1)})
        remaining = start + end_ms / 1000 - clock()
        if remaining > 0:
            sleep(remaining)
    finally:
        # Never leave the button asserted on the bench, even on Ctrl-C.
        if pressed:
            adapter("button_release")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="print the jig action plan for one scenario")
    p.add_argument("scenario")
    p.add_argument("--json", action="store_true")
    m = sub.add_parser("matrix", help="list which scenarios a jig can perform")
    m.add_argument("--json", action="store_true")
    r = sub.add_parser("run", help="execute one scenario's plan through an adapter")
    r.add_argument("scenario")
    r.add_argument("--adapter", choices=["dry-run", "command"], default="dry-run")
    r.add_argument("--profile", help="private JSON mapping each action to an argv (command adapter)")
    r.add_argument("--receipt", type=Path, help="write the timing receipt here")
    args = parser.parse_args(argv)
    if args.command == "matrix":
        rows = matrix()
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(f"{'JIG ' if row['jig'] else 'SIM '} {row['id']}" + ("" if row["jig"] else f"  ({row['reason']})"))
        return 0
    scenario = load(args.scenario)
    try:
        steps = plan(scenario)
    except NotPhysical as exc:
        raise SystemExit(f"{scenario['id']} is simulator-only: {exc}")
    if args.command == "plan":
        if args.json:
            print(json.dumps({"id": scenario["id"], "end_ms": scenario["end"],
                              "steps": [{"t_ms": t, "action": a} for t, a in steps]}, indent=2))
        else:
            print(f"{scenario['id']}: {scenario['summary'].strip()}")
            for t, action in steps:
                print(f"{t:>8} ms  {action}")
            print(f"{scenario['end']:>8} ms  end (observe: {json.dumps(scenario['expect'])})")
        return 0
    if args.adapter == "command" and not args.profile:
        parser.error("--adapter command needs --profile")
    adapter = Command(args.profile) if args.adapter == "command" else DryRun()
    receipt = execute(steps, scenario["end"], adapter)
    if args.receipt:
        args.receipt.write_text(json.dumps({"id": scenario["id"], "adapter": args.adapter, "steps": receipt,
                                            "expect": scenario["expect"]}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
