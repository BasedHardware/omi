#!/usr/bin/env python3
"""Offline tests for jig_gestures.py (no hardware, no adapter profile)."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jig_gestures as jig  # noqa: E402

pm = jig.power_model


def scenario(timeline, initial=None, faults=None, build="default"):
    return {"id": "t", "summary": "t", "events": pm.normalize_timeline(timeline), "end": 9000,
            "initial": initial or {}, "faults": faults or [], "build": build, "expect": {}}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class PlanTests(unittest.TestCase):
    def test_power_on_hold_presses_before_power(self):
        steps = jig.plan(scenario([{"t": 0, "hold": 10600}, {"t": 0, "charger": "on"}]))
        self.assertEqual(steps, [(0, "charger_on"), (0, "button_press"), (0, "power_on"),
                                 (10600, "button_release")])

    def test_power_cycle_opens_relay_for_the_off_gap(self):
        steps = jig.plan(scenario([{"t": 4000, "power": "cycle"}], {"power_off_ms": 800}))
        self.assertIn((4000, "power_off"), steps)
        self.assertIn((4800, "power_on"), steps)

    def test_simulator_only_stimuli_are_refused(self):
        for case in (scenario([{"t": 1, "panic": True}]), scenario([{"t": 1, "app_mute": 1}]),
                     scenario([{"t": 1, "power": "pin_reset"}]), scenario([], {"connected": True}),
                     scenario([], faults=[{"op": "settings_init", "rc": -5}]), scenario([], build="wdt-starve")):
            with self.assertRaises(jig.NotPhysical):
                jig.plan(case)

    def test_matrix_covers_the_manual_safe_mode_gestures(self):
        rows = {r["id"]: r for r in jig.matrix()}
        for name in ("safe/poweron-hold-then-cold-boot", "safe/charger-hold-10s-enters-then-hold-exits",
                     "safe/hold-12s-without-charger-boots-normal", "button/long-press-held-through-poweroff"):
            self.assertTrue(rows[name]["jig"], name)
        self.assertFalse(rows["safe/crash-loop-enters-safe"]["jig"])


class ExecuteTests(unittest.TestCase):
    def test_actions_fire_on_time_and_button_is_released_on_abort(self):
        clock, fired = FakeClock(), []

        def adapter(action):
            fired.append((round(clock.now * 1000), action))
            if action == "power_on" and len(fired) > 2:
                raise KeyboardInterrupt

        steps = [(0, "button_press"), (0, "power_on"), (3000, "power_off"), (3500, "power_on")]
        with self.assertRaises(KeyboardInterrupt):
            jig.execute(steps, 9000, adapter, clock=clock, sleep=clock.sleep, out=io.StringIO())
        self.assertEqual(fired[:4], [(0, "button_press"), (0, "power_on"), (3000, "power_off"), (3500, "power_on")])
        self.assertEqual(fired[-1][1], "button_release")

    def test_receipt_runs_to_scenario_end(self):
        clock = FakeClock()
        receipt = jig.execute([(0, "power_on"), (100, "button_press"), (300, "button_release")], 2000,
                              lambda a: None, clock=clock, sleep=clock.sleep, out=io.StringIO())
        self.assertEqual([r["action"] for r in receipt], ["power_on", "button_press", "button_release"])
        self.assertEqual(clock.now, 2.0)

    def test_command_profile_must_cover_every_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jig.json"
            path.write_text(json.dumps({"button_press": ["true"]}))
            with self.assertRaises(SystemExit):
                jig.Command(path)
            path.write_text(json.dumps({a: ["true"] for a in jig.ACTIONS}))
            jig.Command(path)("button_press")


if __name__ == "__main__":
    unittest.main()
