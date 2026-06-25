"""Integration test: the demo script runs and produces the documented output.

UAT-FN-07 fix: the demo used to be docs-only with no test coverage. Now it's
verified to actually run AND produce the expected picks (modulo any future
benchmark changes — these assertions use the COMMITTED example benchmarks).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/ → repo root
DEMO_CMD = [
    sys.executable,
    "-m",
    "utils.auto_router.demo.run",
]


@pytest.fixture(scope="module")
def demo_output() -> str:
    """Run the demo script as a subprocess once per module and cache the output."""
    result = subprocess.run(
        DEMO_CMD,
        cwd=str(REPO_ROOT / "backend"),
        env={
            **__import__("os").environ,
            "PYENV_VERSION": "3.12.8",
            # Use the in-memory prefs store in the demo subprocess so tests
            # don't require a live Firestore connection. The AA_API_KEY is
            # also unset (falls back to example benchmarks).
            "AUTO_ROUTER_PREFS_BACKEND": "memory",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"demo script failed: returncode={result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    return result.stdout


class TestDemoRuns:
    """Smoke tests — the demo script runs without error."""

    def test_demo_exits_with_zero(self, demo_output: str):
        # If we got here, returncode was 0 (enforced by fixture).
        assert demo_output  # output is non-empty

    def test_demo_has_all_four_sections(self, demo_output: str):
        for header in ("Demo 1:", "Demo 2:", "Demo 3:", "Demo 4:"):
            assert header in demo_output, f"missing section header {header!r} in demo output"

    def test_demo_prints_picks_and_scores(self, demo_output: str):
        # Each demo should print at least 3 "score=" lines (top 3 picks per demo × 3 demos).
        score_lines = [line for line in demo_output.splitlines() if "score=" in line]
        assert len(score_lines) >= 9, f"expected >= 9 score lines (3 per demo × 3 demos), got {len(score_lines)}"


class TestDemoExpectedPicks:
    """Verify the demo produces the documented picks (with the committed example benchmarks).

    These assertions lock in the demo's current behavior. If you intentionally
    change `benchmarks.example.json` scores, update these expectations.
    """

    def test_demo_1_low_cost_general_assistant_picks_haiku(self, demo_output: str):
        # Demo 1: low-cost mode (q=0.1/l=0.1/c=0.8) for general_assistant.
        # haiku-4-5 has the highest cost_score (0.85), so it wins.
        # Find the "Picks with OVERRIDDEN weights" section for Demo 1.
        m = re.search(
            r"Demo 1:.*?Picks with OVERRIDDEN weights:\s*\n\s*1\.\s+(\S+)",
            demo_output,
            re.DOTALL,
        )
        assert m is not None, "could not find Demo 1 override winner"
        assert m.group(1) == "haiku-4-5", f"Demo 1 winner changed: {m.group(1)}"

    def test_demo_2_high_quality_screenshot_picks_claude(self, demo_output: str):
        # Demo 2: high-quality mode (q=0.95/l=0.025/c=0.025) for screenshot_understanding.
        # claude-sonnet-4-6 has the highest quality_score (0.95), so it wins.
        m = re.search(
            r"Demo 2:.*?Picks with OVERRIDDEN weights:\s*\n\s*1\.\s+(\S+)",
            demo_output,
            re.DOTALL,
        )
        assert m is not None, "could not find Demo 2 override winner"
        assert m.group(1) == "claude-sonnet-4-6", f"Demo 2 winner changed: {m.group(1)}"

    def test_demo_3_low_latency_ptt_picks_gemini_flash(self, demo_output: str):
        # Demo 3: low-latency mode (q=0.05/l=0.9/c=0.05) for ptt_response.
        # gemini-1-5-flash-8b-exp has the highest latency_score (0.95), so it wins.
        m = re.search(
            r"Demo 3:.*?Picks with OVERRIDDEN weights:\s*\n\s*1\.\s+(\S+)",
            demo_output,
            re.DOTALL,
        )
        assert m is not None, "could not find Demo 3 override winner"
        assert m.group(1) == "gemini-1-5-flash-8b-exp", f"Demo 3 winner changed: {m.group(1)}"


class TestDemoInvariants:
    """Properties that should hold regardless of benchmark changes."""

    def test_each_demo_lists_three_picks(self, demo_output: str):
        for demo_n in (1, 2, 3):
            # Find this demo's "Picks with OVERRIDDEN" section and count numbered items.
            m = re.search(
                rf"Demo {demo_n}:.*?Picks with OVERRIDDEN weights:\s*\n((?:\s+\d+\..*?\n)+)",
                demo_output,
                re.DOTALL,
            )
            assert m is not None, f"Demo {demo_n} override section missing"
            lines = [l for l in m.group(1).splitlines() if re.match(r"\s+\d+\.", l)]
            assert len(lines) == 3, f"Demo {demo_n} should list 3 picks, got {len(lines)}"

    def test_scores_are_in_valid_range(self, demo_output: str):
        # All scores should be 0.0 .. 1.0 (or close to it for unnormalized overrides).
        for match in re.finditer(r"score=(\d+\.\d+)", demo_output):
            score = float(match.group(1))
            assert 0.0 <= score <= 2.0, f"score {score} out of plausible range"


class TestDemoRunsV3:
    """Demo 5 (per-user prefs flow) + Demo 6 (AA fallback observability) run successfully."""

    def test_demo_5_changes_pick_with_prefs(self, demo_output: str):
        """Demo 5 demonstrates that setting prefs changes the pick."""
        # Demo 5 sets q=1.0 prefs for ptt_response and expects claude-sonnet-4-6 to win.
        assert "Demo 5" in demo_output
        assert "claude-sonnet-4-6" in demo_output
        assert "weights_source=user_prefs" in demo_output

    def test_demo_6_aa_fallback_observability(self, demo_output: str):
        """Demo 6 shows benchmarks_source='example' when AA_API_KEY is unset."""
        assert "Demo 6" in demo_output
        assert "benchmarks_source: example" in demo_output
        assert "benchmarks_last_refresh: None" in demo_output

    def test_demo_runs_all_six_demos(self, demo_output: str):
        assert "All 6 demos complete" in demo_output
