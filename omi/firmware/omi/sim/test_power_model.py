#!/usr/bin/env python3
"""Host unit tests for the simulator's scenario model (no Docker, no Zephyr)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import power_model as pm  # noqa: E402

SCENARIOS = Path(__file__).resolve().parent / "scenarios"


def scenario(timeline, end, initial=None, faults=None):
    return {"events": pm.normalize_timeline(timeline), "end": end, "initial": initial or {},
            "faults": faults or [], "build": "default", "tags": [], "id": "t", "summary": "t"}


class FakeDevice:
    """Executor double: each boot ends as scripted, recording what it was given."""

    def __init__(self, exits):
        self.exits = list(exits)
        self.calls = []

    def __call__(self, index, cfg, stop_ms, warm):
        self.calls.append({"cfg": cfg, "stop_ms": stop_ms, "warm": warm})
        exit_class, uptime, extra = self.exits.pop(0) if self.exits else ("stop", stop_ms, {})
        state = {"exit": exit_class, "uptime_ms": uptime, **extra}
        return {"exit": exit_class, "uptime_ms": uptime, "state": state, "log": ""}


class TimelineTests(unittest.TestCase):
    def test_hold_and_tap_expand(self):
        events = pm.normalize_timeline([{"t": 100, "hold": 50}, {"t": 1000, "tap": [10, 20, 30]}])
        self.assertEqual(events, [(100, "button", True), (150, "button", False), (1000, "button", True),
                                  (1010, "button", False), (1030, "button", True), (1060, "button", False)])

    def test_rejects_bad_rows(self):
        for row in ({"hold": 5}, {"t": -1, "panic": True}, {"t": 0, "power": "zap"},
                    {"t": 0, "button": True, "panic": True}, {"t": 0, "warp": 1}, {"t": 0, "sd": "wet"}):
            with self.assertRaises(pm.ScenarioError):
                pm.normalize_timeline([row])

    def test_levels_at_boot_start_become_initial_state(self):
        s = scenario([{"t": 0, "hold": 3500}, {"t": 0, "charger": "on"}], 10000)
        cfg = pm.boot_config(s, 0, 10000, "power-on", 0)
        self.assertIn("button 1", cfg)
        self.assertIn("charging 1", cfg)
        self.assertIn("event 3500 1 0", cfg)
        self.assertNotIn("event 0 ", cfg)

    def test_events_are_rebased_to_the_boot(self):
        s = scenario([{"t": 7000, "panic": True}], 10000)
        cfg = pm.boot_config(s, 5000, 5000, "watchdog", 1)
        self.assertIn("reset 2", cfg)
        self.assertIn("event 2000 4 1", cfg)

    def test_pulse_that_ended_a_boot_is_not_replayed(self):
        s = scenario([{"t": 1000, "panic": True}, {"t": 1000, "app_mute": 1}], 5000)
        self.assertIn("event 1000 4 1", pm.boot_config(s, 0, 5000, "power-on", 0))
        self.assertNotIn("event 0 4", pm.boot_config(s, 1000, 4000, "software", 1))
        device = FakeDevice([("fatal", 1000, {})])
        out = pm.run_power_model(s, device)
        self.assertEqual(len(out["boots"]), 2)

    def test_faults_are_scoped_to_boots(self):
        s = scenario([], 1000, faults=[{"op": "settings_load", "key": "omi", "rc": -5, "boots": [1]}])
        self.assertNotIn("fault", pm.boot_config(s, 0, 1000, "power-on", 0))
        self.assertIn("fault 2 -5 -1 omi", pm.boot_config(s, 0, 1000, "power-on", 1))


class PowerModelTests(unittest.TestCase):
    def test_cold_cycle_drops_ram(self):
        device = FakeDevice([])
        out = pm.run_power_model(scenario([{"t": 4000, "power": "cycle"}], 9000), device)
        self.assertEqual([b["reset"] for b in out["boots"]], ["power-on", "power-on"])
        self.assertEqual([c["warm"] for c in device.calls], [False, False])
        self.assertEqual(out["boots"][1]["start_ms"], 4500)
        self.assertEqual(device.calls[0]["stop_ms"], 4000)

    def test_watchdog_and_fatal_are_warm(self):
        device = FakeDevice([("watchdog", 1000, {}), ("fatal", 500, {})])
        out = pm.run_power_model(scenario([], 5000), device)
        self.assertEqual([b["reset"] for b in out["boots"]], ["power-on", "watchdog", "software"])
        self.assertEqual([c["warm"] for c in device.calls], [False, True, True])
        self.assertEqual(out["boots"][2]["start_ms"], 1500)

    def test_poweroff_with_button_held_wakes_immediately(self):
        device = FakeDevice([("poweroff", 2000, {"button_held_at_poweroff": True})])
        out = pm.run_power_model(scenario([], 5000), device)
        self.assertEqual(out["boots"][1]["reset"], "off-wake")
        self.assertEqual(out["boots"][1]["start_ms"], 2000)
        self.assertFalse(device.calls[1]["warm"])

    def test_jammed_button_wakes_on_release_when_armed_for_it(self):
        device = FakeDevice([("poweroff", 65000, {"button_held_at_poweroff": True})])
        s = scenario([{"t": 2000, "hold": 75000}], 120000)

        def execute(index, cfg, stop_ms, warm):
            out = device(index, cfg, stop_ms, warm)
            if index == 0:
                out["log"] = "usr_btn still held at power-off: " + pm.WAKE_ON_RELEASE
            return out

        out = pm.run_power_model(s, execute)
        self.assertEqual(out["boots"][1]["reset"], "off-wake")
        self.assertEqual(out["boots"][1]["start_ms"], 77000)
        self.assertIn("button 0", device.calls[1]["cfg"])
        self.assertEqual(pm.inv_poweroff_waits_release(out["boots"], out), [])

    def test_poweroff_waits_for_next_press(self):
        device = FakeDevice([("poweroff", 2000, {})])
        out = pm.run_power_model(scenario([{"t": 1000, "hold": 500}, {"t": 6000, "tap": [100]}], 9000), device)
        self.assertEqual(out["boots"][1]["start_ms"], 6000)
        self.assertIn("button 1", device.calls[1]["cfg"])

    def test_poweroff_without_wake_ends_off(self):
        out = pm.run_power_model(scenario([], 5000), FakeDevice([("poweroff", 2000, {})]))
        self.assertEqual(out["final"], "off")
        self.assertEqual(len(out["boots"]), 1)

    def test_off_retains_ram_option(self):
        device = FakeDevice([("poweroff", 2000, {})])
        pm.run_power_model(scenario([{"t": 3000, "tap": [100]}], 9000, {"off_retains_ram": True}), device)
        self.assertTrue(device.calls[1]["warm"])

    def test_runaway_loop_is_bounded(self):
        device = FakeDevice([("watchdog", 1, {})] * 100)
        with self.assertRaises(pm.ScenarioError):
            pm.run_power_model(scenario([], 10 ** 9), device)


class OracleTests(unittest.TestCase):
    def test_parse_and_check(self):
        log = 'boot\nSIM EXIT: stop\nSIMSTATE: {"exit":"stop","uptime_ms":5000,"safe":false,"muted":1}\n'
        boot = pm.parse_boot_log(log)
        boot.update(index=0, reset="power-on", warm=False, log=log)
        outcome = {"boots": [boot], "final": "running"}
        self.assertEqual(pm.check({"boots": [{"safe": False, "muted": 1, "log": ["boot"]}]}, outcome), [])
        failures = pm.check({"boot_count": 2, "boots": [{"safe": True, "not_log": ["boot"]}]}, outcome)
        self.assertEqual(len(failures), 3)

    def test_safe_boot_reports_the_reason_that_selected_it(self):
        log = ('BOOTSTATE: active=1 count=1 reason=2 reset=0x00000001 state=0\nSIM EXIT: poweroff\n'
               'SIMSTATE: {"exit":"poweroff","uptime_ms":20000,"safe":true,"latch_reason":0}\n')
        state = pm.parse_boot_log(log)["state"]
        self.assertEqual((state["latch_reason"], state["exit_latch_reason"]), (2, 0))
        normal = pm.parse_boot_log('BOOTSTATE: active=0 count=1 reason=0 reset=0x0 state=0\nSIM EXIT: stop\n'
                                   'SIMSTATE: {"exit":"stop","uptime_ms":1,"safe":false,"latch_reason":0}\n')
        self.assertEqual(normal["state"]["latch_reason"], 0)

    def test_parse_rejects_missing_or_double_state(self):
        with self.assertRaises(pm.ScenarioError):
            pm.parse_boot_log("SIM EXIT: stop\n")
        with self.assertRaises(pm.ScenarioError):
            pm.parse_boot_log('SIM EXIT: stop\nSIMSTATE: {"exit":"watchdog","uptime_ms":1}\n')

    def test_mute_is_judged_only_after_settings_applied(self):
        early = {"index": 0, "exit": "fatal", "log": "", "state": {"safe": False, "muted": 1, "sd_paused": False}}
        late = {"index": 1, "exit": "stop", "log": "Settings initialized. muted=1",
                "state": {"safe": False, "muted": 1, "sd_paused": False}}
        self.assertEqual(pm.inv_mute_follows_app([early], {}), [])
        self.assertEqual(pm.inv_mute_blocks_capture([dict(early, exit="stop")], {}), [])
        self.assertEqual(len(pm.inv_mute_follows_app([late], {})), 1)
        self.assertEqual(len(pm.inv_mute_blocks_capture([late], {})), 1)

    def test_capture_after_settings(self):
        good = {"index": 0, "log": "Settings initialized. muted=0\nSIM: Microphone started", "state": {}}
        bad = {"index": 1, "log": "SIM: Microphone started\nSettings initialized. muted=1", "state": {}}
        none = {"index": 2, "log": "SIM: Microphone started", "state": {}}
        self.assertEqual(pm.inv_capture_after_settings([good], {}), [])
        self.assertEqual(len(pm.inv_capture_after_settings([bad, none], {})), 2)

    def test_no_stuck_safe(self):
        boots = [{"index": 0, "reset": "power-on", "exit": "stop", "state": {"safe": True, "latch_reason": 1}},
                 {"index": 1, "reset": "watchdog", "exit": "stop", "state": {"safe": True, "latch_reason": 1}},
                 {"index": 2, "reset": "off-wake", "exit": "stop", "state": {"safe": True, "latch_reason": 2}}]
        self.assertEqual(len(pm.inv_no_stuck_safe(boots, {})), 1)


class CatalogTests(unittest.TestCase):
    def test_every_scenario_loads_and_baseline_bugs_document_the_bug(self):
        files = pm.discover(SCENARIOS)
        self.assertGreater(len(files), 20)
        for path in files:
            s = pm.load_scenario(path, SCENARIOS)
            if "baseline-bug" in s["tags"]:
                self.assertIn("baseline_bug", s, s["id"])
            for name in s["expect"].get("invariants", []):
                self.assertIn(name, pm.INVARIANTS, s["id"])


if __name__ == "__main__":
    unittest.main()
