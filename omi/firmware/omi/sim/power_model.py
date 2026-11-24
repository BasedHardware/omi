"""Scenario model for the CV1 simulator: parsing, power model and oracle.

Pure Python with no Docker or Zephyr dependency, so it is unit-tested on any
host (test_power_model.py). scenario_runner.py supplies the executor that
actually boots zephyr.exe.

A scenario is one global timeline in milliseconds. The power model turns it
into a chain of simulated boots, the way the hardware would:

  exit        next boot
  ----        ---------
  stop        at a scheduled power event: cycle (cold, RAM lost), pin_reset or
              soft_reset (warm, RAM kept); at `end`: the scenario is over
  watchdog    immediately, warm, RESETREAS DOG0
  fatal       immediately, warm, RESETREAS SREQ (the fatal handler's reset)
  poweroff    System OFF. Wake on a button press (level-low wake): at once if
              the button is still held when OFF is entered, else at the next
              scripted press. RAM is lost unless the scenario sets
              initial.off_retains_ram. A power cycle while off is a cold boot.
"""
import fnmatch
import json
import re
from pathlib import Path

# nRF5340 application-core RESETREAS bits (sim/include/hal/nrf_reset.h).
RESET_BITS = {
    "power-on": 0,
    "pin": 1 << 0,
    "watchdog": 1 << 1,
    "software": 1 << 3,
    "lockup": 1 << 4,
    "off-wake": 1 << 5,
}

EV_BUTTON, EV_CHARGER, EV_BATTERY, EV_PANIC, EV_CONNECTED, EV_SD, EV_APP_MUTE, EV_DFU = 1, 2, 3, 4, 5, 6, 7, 8
# Image-management events an SMP client can cause (sim_plan.h enum omi_sim_dfu_op).
DFU_OPS = {"chunk": 1, "chunk-image1": 2, "chunk-net": 3, "stopped": 4, "pending": 5}
SD_STATES = {"ok": 0, "absent": 1, "slow": 2, "dead": 3}
FAULT_OPS = {"settings_init": 1, "settings_load": 2, "settings_save": 3}
LEVELS = ("button", "charger", "battery_mv", "connected", "sd")
POWER_ACTIONS = ("cycle", "pin_reset", "soft_reset")
EXITS = ("stop", "watchdog", "fatal", "poweroff")
MAX_BOOTS = 64


class ScenarioError(ValueError):
    pass


def _bool(value, name):
    if isinstance(value, bool):
        return value
    if value in ("press", "on", "true", 1):
        return True
    if value in ("release", "off", "false", 0):
        return False
    raise ScenarioError(f"{name}: unrecognized value {value!r}")


def normalize_timeline(raw):
    """Expand shorthands; return sorted [(t, kind, value)] with stable order."""
    events = []
    for index, row in enumerate(raw or []):
        if not isinstance(row, dict) or "t" not in row:
            raise ScenarioError(f"timeline[{index}] needs a t")
        t = int(row["t"])
        if t < 0:
            raise ScenarioError(f"timeline[{index}]: negative time")
        keys = [k for k in row if k != "t"]
        if len(keys) != 1:
            raise ScenarioError(f"timeline[{index}]: exactly one action per row")
        key, value = keys[0], row[keys[0]]
        if key == "hold":
            events.append((t, "button", True, index))
            events.append((t + int(value), "button", False, index))
        elif key == "tap":
            # tap: [press_ms, gap_ms, press_ms, ...] starting at t
            cursor = t
            durations = value if isinstance(value, list) else [value]
            for i, ms in enumerate(durations):
                if i % 2 == 0:
                    events.append((cursor, "button", True, index))
                    events.append((cursor + int(ms), "button", False, index))
                cursor += int(ms)
        elif key == "button":
            events.append((t, "button", _bool(value, key), index))
        elif key in ("charger", "connected"):
            events.append((t, key, _bool(value, key), index))
        elif key == "battery_mv":
            events.append((t, key, int(value), index))
        elif key == "sd":
            if value not in SD_STATES:
                raise ScenarioError(f"timeline[{index}]: sd must be one of {sorted(SD_STATES)}")
            events.append((t, key, value, index))
        elif key == "app_mute":
            events.append((t, key, _bool(value, key), index))
        elif key == "panic":
            events.append((t, "panic", True, index))
        elif key == "dfu":
            if value not in DFU_OPS:
                raise ScenarioError(f"timeline[{index}]: dfu must be one of {sorted(DFU_OPS)}")
            events.append((t, "dfu", value, index))
        elif key == "power":
            if value not in POWER_ACTIONS:
                raise ScenarioError(f"timeline[{index}]: power must be one of {POWER_ACTIONS}")
            events.append((t, "power", value, index))
        else:
            raise ScenarioError(f"timeline[{index}]: unknown action {key!r}")
    events.sort(key=lambda e: (e[0], e[3]))
    return [(t, kind, value) for t, kind, value, _ in events]


def load_scenario(path, root):
    import yaml  # PyYAML: present in the pinned Zephyr CI image and dev hosts

    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ScenarioError(f"{path}: not a mapping")
    expected_id = str(Path(path).relative_to(root).with_suffix(""))
    if data.get("id") != expected_id:
        raise ScenarioError(f"{path}: id must be {expected_id!r}")
    if data.get("expect", {}).get("final") is False:
        raise ScenarioError(f"{path}: quote final: \"off\" (YAML reads bare off as false)")
    for key in ("summary", "end", "expect"):
        if key not in data:
            raise ScenarioError(f"{path}: missing {key}")
    data.setdefault("build", "default")
    data.setdefault("tags", [])
    data.setdefault("initial", {})
    data["events"] = normalize_timeline(data.get("timeline"))
    data["path"] = str(path)
    return data


def discover(root, patterns=None):
    root = Path(root)
    files = sorted(root.rglob("*.yaml"))
    if patterns:
        files = [f for f in files if any(fnmatch.fnmatch(str(f.relative_to(root).with_suffix("")), p)
                                          for p in patterns)]
    return files


def level_at(events, initial, kind, t):
    """Level of a scripted input at time t (events at exactly t apply)."""
    defaults = {"button": False, "charger": False, "battery_mv": 3900,
                "connected": False, "sd": "ok"}
    init_key = "charging" if kind == "charger" else kind
    value = initial.get(init_key, defaults[kind])
    for et, ekind, evalue in events:
        if et > t:
            break
        if ekind == kind:
            value = evalue
    return value


def boot_config(scenario, start, stop_ms, reset, boot_index):
    """Text for boot.cfg, plus the events delivered inside this boot."""
    events = scenario["events"]
    initial = scenario["initial"]
    lines = [f"# boot {boot_index} at scenario t={start} ms",
             f"reset {RESET_BITS[reset]}",
             f"button {int(level_at(events, initial, 'button', start))}",
             f"charging {int(level_at(events, initial, 'charger', start))}",
             f"battery_mv {int(level_at(events, initial, 'battery_mv', start))}",
             f"connected {int(level_at(events, initial, 'connected', start))}",
             f"sd {SD_STATES[level_at(events, initial, 'sd', start)]} {int(initial.get('sd_ready_ms', 0))}"]
    codes = {"button": EV_BUTTON, "charger": EV_CHARGER, "battery_mv": EV_BATTERY,
             "connected": EV_CONNECTED, "sd": EV_SD, "panic": EV_PANIC,
             "app_mute": EV_APP_MUTE, "dfu": EV_DFU}
    for t, kind, value in events:
        if kind == "power" or not start <= t < start + stop_ms:
            continue
        if kind in LEVELS and t == start:
            continue  # already the initial level
        if t == start and boot_index > 0:
            continue  # a pulse at the reboot instant was consumed by the boot it ended
        if kind == "sd":
            value = SD_STATES[value]
        if kind == "dfu":
            value = DFU_OPS[value]
        lines.append(f"event {t - start} {codes[kind]} {int(value)}")
    for fault in scenario.get("faults", []):
        boots = fault.get("boots")
        if boots is not None and boot_index not in boots:
            continue
        op = FAULT_OPS[fault["op"]]
        lines.append(f"fault {op} {int(fault['rc'])} {int(fault.get('remaining', -1))} {fault.get('key', '')}".rstrip())
    return "\n".join(lines) + "\n"


def run_power_model(scenario, execute):
    """Drive the boot chain. execute(index, cfg_text, stop_ms, warm) -> result
    dict with at least exit, uptime_ms, state (SIMSTATE dict) and log."""
    events = scenario["events"]
    end = int(scenario["end"])
    initial = scenario["initial"]
    power = [(t, v) for t, k, v in events if k == "power"]
    boots = []
    t, reset, warm = 0, "power-on", False
    final = "running"
    while True:
        if len(boots) >= MAX_BOOTS:
            raise ScenarioError(f"more than {MAX_BOOTS} boots; runaway reset loop")
        upcoming = [(pt, pv) for pt, pv in power if pt > t]
        stop_at = upcoming[0][0] if upcoming and upcoming[0][0] < end else end
        stop_ms = stop_at - t
        if stop_ms <= 0:
            final = "running"
            break
        cfg = boot_config(scenario, t, stop_ms, reset, len(boots))
        result = execute(len(boots), cfg, stop_ms, warm)
        if result["exit"] not in EXITS:
            raise ScenarioError(f"boot {len(boots)}: unclassified exit {result['exit']!r}")
        result.update(index=len(boots), start_ms=t, reset=reset, warm=warm,
                      charging_at_start=bool(level_at(events, initial, "charger", t)),
                      button_at_start=bool(level_at(events, initial, "button", t)))
        boots.append(result)
        t_exit = t + int(result["uptime_ms"])
        exit_class = result["exit"]
        if exit_class == "stop":
            if stop_at >= end:
                final = "running"
                break
            action = upcoming[0][1]
            t = stop_at
            if action == "cycle":
                reset, warm = "power-on", False
                t += int(initial.get("power_off_ms", 500))
            elif action == "pin_reset":
                reset, warm = "pin", True
            else:
                reset, warm = "software", True
        elif exit_class == "watchdog":
            t, reset, warm = t_exit, "watchdog", True
        elif exit_class == "fatal":
            t, reset, warm = t_exit, "software", True
        else:  # poweroff
            retains = bool(initial.get("off_retains_ram", False))
            release_wake = WAKE_ON_RELEASE in result.get("log", "")
            if result["state"].get("button_held_at_poweroff") and not release_wake:
                t, reset, warm = t_exit, "off-wake", retains
            elif result["state"].get("button_held_at_poweroff"):
                # Armed for release: System OFF wakes when the jam clears.
                release = next((et for et, k, v in events if k == "button" and not v and et > t_exit), None)
                if release is None or release >= end:
                    final = "off"
                    break
                t, reset, warm = release, "off-wake", retains
            else:
                press = next((et for et, k, v in events if k == "button" and v and et > t_exit), None)
                cycle = next((pt for pt, pv in power if pt > t_exit and pv == "cycle"), None)
                if press is not None and press < end and (cycle is None or press < cycle):
                    t, reset, warm = press, "off-wake", retains
                elif cycle is not None and cycle < end:
                    t = cycle + int(initial.get("power_off_ms", 500))
                    reset, warm = "power-on", False
                else:
                    final = "off"
                    break
        if t >= end:
            final = "off" if exit_class == "poweroff" else "running"
            break
    return {"boots": boots, "final": final, "events": events, "faults": scenario.get("faults", [])}


# ---- oracle -------------------------------------------------------------

SIMSTATE = re.compile(r"^SIMSTATE: (\{.*\})\s*$", re.M)
SIM_EXIT = re.compile(r"^SIM EXIT: (\w+)\s*$", re.M)


# button.c logs this when it arms System OFF wake on release (button still
# held after its bounded wait); otherwise wake is armed on press.
WAKE_ON_RELEASE = "waking on release instead"
BOOTSTATE = re.compile(r"^BOOTSTATE: active=1 count=\d+ reason=(\d+)", re.M)


def parse_boot_log(text):
    exits = SIM_EXIT.findall(text)
    states = SIMSTATE.findall(text)
    if len(exits) != 1 or len(states) != 1:
        raise ScenarioError(f"expected one SIM EXIT and one SIMSTATE, got {len(exits)}/{len(states)}")
    state = json.loads(states[0])
    if state.get("exit") != exits[0]:
        raise ScenarioError("SIM EXIT and SIMSTATE disagree")
    # SIMSTATE is taken at exit, after SAFE power-off or a completed upload has
    # already cleared the RAM latch for the next boot. For a SAFE boot,
    # latch_reason means why SAFE was selected: the boot-time BOOTSTATE line.
    # The raw exit value stays available as exit_latch_reason.
    state["exit_latch_reason"] = state.get("latch_reason")
    entry = BOOTSTATE.search(text)
    if entry and state.get("safe"):
        state["latch_reason"] = int(entry.group(1))
    return {"exit": exits[0], "uptime_ms": state["uptime_ms"], "state": state}


def _check_boot(prefix, expect, boot, failures):
    state = boot["state"]
    log = boot.get("log", "")
    simple = {"exit": boot["exit"], "reset": boot["reset"], "warm": boot["warm"], "start_ms": boot.get("start_ms")}
    for key, want in expect.items():
        if key in simple:
            if simple[key] != want:
                failures.append(f"{prefix}: {key}={simple[key]!r}, want {want!r}")
        elif key == "log":
            for token in want:
                if token not in log:
                    failures.append(f"{prefix}: missing log {token!r}")
        elif key == "not_log":
            for token in want:
                if token in log:
                    failures.append(f"{prefix}: forbidden log {token!r}")
        elif key in state:
            if state[key] != want:
                failures.append(f"{prefix}: {key}={state[key]!r}, want {want!r}")
        else:
            failures.append(f"{prefix}: unknown expectation key {key!r}")


def check(expect, outcome):
    """Return a list of failure strings (empty = pass)."""
    failures = []
    boots = outcome["boots"]
    if "boot_count" in expect and len(boots) != expect["boot_count"]:
        failures.append(f"boot_count={len(boots)}, want {expect['boot_count']}")
    if "final" in expect and outcome["final"] != expect["final"]:
        failures.append(f"final={outcome['final']!r}, want {expect['final']!r}")
    for index, want in enumerate(expect.get("boots", [])):
        if index >= len(boots):
            failures.append(f"boot {index}: missing (only {len(boots)} boots)")
            continue
        _check_boot(f"boot {index}", want, boots[index], failures)
    if "last" in expect and boots:
        _check_boot("last boot", expect["last"], boots[-1], failures)
    if "every" in expect:
        for boot in boots:
            _check_boot(f"boot {boot['index']}", expect["every"], boot, failures)
    for name in expect.get("invariants", []):
        failures.extend(INVARIANTS[name](boots, outcome))
    return failures


# ---- invariants (also used by the fuzz lane) -----------------------------

def inv_no_stuck_safe(boots, outcome):
    """A cold power-on or OFF wake never enters SAFE unless this very boot
    saw a deliberate entry (latch reason 2); a crash loop needs warm resets."""
    out = []
    for boot in boots:
        state = boot["state"]
        if boot["reset"] in ("power-on", "off-wake", "pin") and state.get("safe") and state.get("latch_reason") != 2:
            out.append(f"boot {boot['index']}: {boot['reset']} boot in SAFE (reason {state.get('latch_reason')})")
    return out


def inv_manual_entry_needs_charger(boots, outcome):
    out = []
    for boot in boots:
        state = boot["state"]
        if state.get("safe") and state.get("latch_reason") == 2 and not boot.get("charging_at_start", True):
            out.append(f"boot {boot['index']}: manual SAFE entry without charger")
    return out


def _held_through(events, kind, start, until):
    """True if a level input is asserted for the whole [start, until) window."""
    if not level_at(events, {}, kind, start):
        return False
    return not any(k == kind and not v and start < t < until for t, k, v in events)


def inv_manual_entry_needs_10s_hold(boots, outcome):
    """Reason-2 SAFE needs button and charger held from power-on for 10 s."""
    events = outcome.get("events", [])
    out = []
    for boot in boots:
        state = boot["state"]
        if state.get("safe") and state.get("latch_reason") == 2:
            start = boot["start_ms"]
            if not (_held_through(events, "button", start, start + 10000)
                    and _held_through(events, "charger", start, start + 10000)):
                out.append(f"boot {boot['index']}: manual SAFE without a 10 s charger hold")
    return out


APP_MUTE_LINE = re.compile(r"^SIM: app writes mute=(\d) \(rc=(-?\d+)\)", re.M)


# app_settings_init() ran (or failed and fell back to muted). Before this the
# RAM mute is the fail-closed default and nothing captures or stores yet.
SETTINGS_APPLIED = ("Settings initialized", "Failed to initialize settings subsystem")


def _settings_applied(boot):
    return any(token in boot.get("log", "") for token in SETTINGS_APPLIED)


def inv_mute_follows_app(boots, outcome):
    """The app's last delivered mute write wins: nothing else (taps, power,
    faults) may clear a mute, and nothing but a settings fault may set one."""
    faulted = bool(outcome.get("faults"))
    last = None
    out = []
    for boot in boots:
        for value, _rc in APP_MUTE_LINE.findall(boot.get("log", "")):
            last = int(value)
        state = boot["state"]
        if state.get("safe") or "muted" not in state or not _settings_applied(boot):
            continue
        if last == 1 and state["muted"] != 1:
            out.append(f"boot {boot['index']}: app muted but pendant unmuted")
        if last is None and not faulted and state["muted"] != 0:
            out.append(f"boot {boot['index']}: muted without any mute request")
    return out


def inv_capture_after_settings(boots, outcome):
    """The microphone starts only after the persisted mute was applied, so the
    fail-closed default can never be the only thing standing between a muted
    pendant and capture."""
    out = []
    for boot in boots:
        log = boot.get("log", "")
        mic = log.find("Microphone started")
        if mic < 0:
            continue
        applied = [i for i in (log.find(t) for t in SETTINGS_APPLIED) if i >= 0]
        if not applied or min(applied) > mic:
            out.append(f"boot {boot['index']}: microphone started before settings were applied")
    return out


def inv_critical_battery_respects_charger(boots, outcome):
    return [f"boot {b['index']}: critical-battery shutdown while charging"
            for b in boots if "Battery critical level reached" in b.get("log", "") and b["state"].get("charging")]


def inv_mute_blocks_capture(boots, outcome):
    out = []
    for boot in boots:
        state = boot["state"]
        if state.get("muted") and state.get("should_capture"):
            out.append(f"boot {boot['index']}: muted but capture allowed")
        if (not state.get("safe") and state.get("muted") and not state.get("sd_paused") and boot["exit"] == "stop"
                and _settings_applied(boot)):
            out.append(f"boot {boot['index']}: muted but SD writes not paused")
    return out


def inv_poweroff_waits_release(boots, outcome):
    return [f"boot {b['index']}: System OFF entered with the button held (instant re-wake)"
            for b in boots if b["exit"] == "poweroff" and b["state"].get("button_held_at_poweroff")
            and WAKE_ON_RELEASE not in b.get("log", "")]


def inv_no_watchdog_in_healthy_boot(boots, outcome):
    return [f"boot {b['index']}: watchdog reset" for b in boots if b["exit"] == "watchdog"]


def inv_sd_mount_attempts_bounded(boots, outcome):
    """A failing card is retried with backoff: at most one five-try mount per
    second of the first minute, and no more than ~one per minute after."""
    out = []
    for boot in boots:
        attempts = boot["state"].get("sd_mount_attempts", 0)
        minutes = max(1.0, int(boot["uptime_ms"]) / 60000.0)
        if attempts > 5 * (10 + 2 * minutes):
            out.append(f"boot {boot['index']}: {attempts} card inits in {minutes:.1f} min (hot loop)")
    return out


INVARIANTS = {
    "no-stuck-safe": inv_no_stuck_safe,
    "manual-entry-needs-charger": inv_manual_entry_needs_charger,
    "mute-blocks-capture": inv_mute_blocks_capture,
    "poweroff-waits-release": inv_poweroff_waits_release,
    "no-watchdog": inv_no_watchdog_in_healthy_boot,
    "manual-entry-needs-10s-hold": inv_manual_entry_needs_10s_hold,
    "mute-follows-app": inv_mute_follows_app,
    "critical-battery-respects-charger": inv_critical_battery_respects_charger,
    "sd-mount-attempts-bounded": inv_sd_mount_attempts_bounded,
    "capture-after-settings": inv_capture_after_settings,
}
