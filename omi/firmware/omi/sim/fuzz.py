"""Seeded property lane for the CV1 simulator.

Each seed composes a random multi-boot chain (button gestures, charger
plug/unplug, app mute writes, power cycles and resets, kernel panics, battery
dips, settings faults) and checks the cross-boot invariants in
power_model.INVARIANTS after every boot. A failing seed is written out as a
ready-to-commit scenario YAML under <cache>/fuzz-failures/ so it can graduate
into the named suite. Seeds are deterministic: seed N always produces the
same chain on every host.
"""
import random

import power_model

FUZZ_INVARIANTS = [
    "no-stuck-safe",
    "manual-entry-needs-charger",
    "manual-entry-needs-10s-hold",
    "mute-follows-app",
    "mute-blocks-capture",
    "poweroff-waits-release",
    "critical-battery-respects-charger",
    "capture-after-settings",
]


def chain(seed):
    rng = random.Random(seed)
    end = rng.randrange(30000, 120001, 1000)
    timeline = []
    t = 0
    if rng.random() < 0.3:
        # Start with a power-on gesture: the 3.0.23 failure class.
        hold = rng.choice([500, 2900, 3100, 3500, 5000, 9900, 10100, 10600, 12000])
        timeline.append({"t": 0, "hold": hold})
        t = hold + rng.randrange(200, 2000)
    charging = rng.random() < 0.3
    while t < end - 1000:
        op = rng.choices(
            ["tap", "double", "hold", "charger", "mute", "power", "panic", "battery", "connected", "idle"],
            weights=[8, 6, 6, 5, 6, 4, 1, 3, 3, 8],
        )[0]
        if op == "tap":
            timeline.append({"t": t, "tap": [rng.randrange(40, 280)]})
            t += 400
        elif op == "double":
            timeline.append({"t": t, "tap": [rng.randrange(40, 200), rng.randrange(80, 250), rng.randrange(40, 200)]})
            t += 900
        elif op == "hold":
            ms = rng.choice([rng.randrange(300, 2900), rng.randrange(3100, 6000), rng.randrange(6000, 14000)])
            timeline.append({"t": t, "hold": ms})
            t += ms + rng.randrange(100, 3000)
        elif op == "charger":
            charging = not charging
            timeline.append({"t": t, "charger": "on" if charging else "off"})
        elif op == "mute":
            timeline.append({"t": t, "app_mute": rng.randrange(2)})
        elif op == "power":
            timeline.append({"t": t, "power": rng.choice(["cycle", "cycle", "pin_reset", "soft_reset"])})
            t += 600
        elif op == "panic":
            timeline.append({"t": t, "panic": True})
        elif op == "battery":
            timeline.append({"t": t, "battery_mv": rng.choice([3300, 3450, 3499, 3500, 3600, 3900, 4150])})
        elif op == "connected":
            timeline.append({"t": t, "connected": rng.random() < 0.5})
        t += rng.randrange(200, 6000)
    faults = []
    if rng.random() < 0.15:
        op = rng.choice(["settings_load", "settings_init", "settings_save"])
        fault = {"op": op, "rc": -5, "boots": [rng.randrange(0, 4)]}
        if op == "settings_load":
            fault["key"] = "omi"
        if op == "settings_save":
            fault["key"] = "omi/muted"
        faults.append(fault)
    return {
        "id": f"fuzz/seed-{seed}",
        "summary": f"fuzz chain for seed {seed}",
        "tags": ["fuzz"],
        "build": "default",
        "initial": {"charging": False, "off_retains_ram": rng.random() < 0.2},
        "timeline": timeline,
        "faults": faults,
        "end": end,
        "expect": {"invariants": FUZZ_INVARIANTS},
    }


def to_yaml(scenario):
    import yaml

    data = {k: scenario[k] for k in ("id", "summary", "tags", "build", "initial", "timeline", "faults", "end", "expect")}
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=None, width=110)


def run_batch(count, start, exes, cache, run_scenario, jobs):
    import concurrent.futures

    seeds = list(range(start, start + count))
    failures = []

    def one(seed):
        raw = chain(seed)
        scenario = dict(raw, events=power_model.normalize_timeline(raw["timeline"]))
        row = run_scenario(scenario, exes["default"], cache, "current")
        if row["verdict"] != "pass":
            out = cache / "fuzz-failures"
            out.mkdir(exist_ok=True)
            path = out / f"seed-{seed}.yaml"
            path.write_text(to_yaml(raw))
            print(f"FUZZ FAIL seed {seed}: {row['failures'][:3]} -> {path}", flush=True)
            return {"seed": seed, "failures": row["failures"], "repro": str(path.relative_to(cache))}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        failures = [f for f in pool.map(one, seeds) if f]
    print(f"fuzz: {count - len(failures)}/{count} seeds passed (seeds {start}..{start + count - 1})", flush=True)
    return {"verdict": "fail" if failures else "pass", "seeds": count, "first_seed": start,
            "invariants": FUZZ_INVARIANTS, "failures": failures}
