#!/usr/bin/env python3
"""
YAML-based E2E test runner for the Omi desktop macOS app.

Interprets declarative YAML flows and executes them via agent-swift CLI.
Each YAML step maps to one or more agent-swift commands.

Usage:
    python3 runner.py navigation          # run a single flow
    python3 runner.py --all               # run all flows
    python3 runner.py --list              # list available flows

Environment:
    AGENT_SWIFT         Path to agent-swift binary (default: auto-detect)
    E2E_SSH_HOST        SSH host for remote execution (e.g. 100.126.187.125)
    E2E_SSH_USER        SSH GUI user prefix (default: sudo launchctl asuser 501 sudo -u beastoinagents)
    E2E_SCREENSHOT_DIR  Screenshot output dir (default: /tmp/omi-desktop-e2e)
    E2E_WAIT            Settle time between actions in seconds (default: 0.5)
    E2E_FAST            Set to 1 to skip screenshots
    E2E_BUNDLE_ID       Override bundle ID (default: from YAML or com.omi.desktop-dev)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    # Inline minimal YAML parser for environments without PyYAML
    yaml = None


# ---------------------------------------------------------------------------
# Minimal YAML fallback (handles the subset we use in flow files)
# ---------------------------------------------------------------------------

def _parse_yaml_fallback(text: str) -> dict:
    """Minimal YAML parser for flow files when PyYAML is not installed."""
    # Try to use the system Python's yaml if available
    result = subprocess.run(
        [sys.executable, "-c",
         "import yaml, json, sys; print(json.dumps(yaml.safe_load(sys.stdin.read())))"],
        input=text, capture_output=True, text=True
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    raise ImportError(
        "PyYAML is required. Install with: pip install pyyaml"
    )


def load_yaml(path: str) -> dict:
    """Load a YAML file, using PyYAML if available, fallback otherwise."""
    text = Path(path).read_text()
    if yaml:
        return yaml.safe_load(text)
    return _parse_yaml_fallback(text)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    name: str
    passed: bool
    message: str = ""
    screenshot: str = ""
    optional: bool = False


@dataclass
class FlowResult:
    name: str
    steps: list = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for s in self.steps if s.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for s in self.steps if not s.passed and not s.optional)

    @property
    def skip_count(self) -> int:
        return sum(1 for s in self.steps if not s.passed and s.optional)


# ---------------------------------------------------------------------------
# FlowRunner
# ---------------------------------------------------------------------------

class FlowRunner:
    def __init__(self):
        self.agent_swift = self._find_agent_swift()
        self.ssh_host = os.environ.get("E2E_SSH_HOST", "")
        self.ssh_user_prefix = os.environ.get(
            "E2E_SSH_USER",
            "sudo launchctl asuser 501 sudo -u beastoinagents"
        )
        self.screenshot_dir = os.environ.get("E2E_SCREENSHOT_DIR", "/tmp/omi-desktop-e2e")
        self.wait_time = float(os.environ.get("E2E_WAIT", "0.5"))
        self.fast_mode = os.environ.get("E2E_FAST", "") == "1"
        self.bundle_id = os.environ.get("E2E_BUNDLE_ID", "")

        self._variables: dict[str, str] = {}
        self._snapshot_cache: list[dict] | None = None
        self._connected = False

    def _find_agent_swift(self) -> str:
        """Find agent-swift binary."""
        env_path = os.environ.get("AGENT_SWIFT", "")
        if env_path:
            return env_path
        # Check PATH
        result = subprocess.run(["which", "agent-swift"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        # Check common locations
        for path in ["/tmp/agent-swift", "/usr/local/bin/agent-swift"]:
            if os.path.isfile(path):
                return path
        return "agent-swift"  # Hope it's on PATH

    def run_as(self, *args: str, json_output: bool = False) -> tuple[int, str]:
        """Run an agent-swift command. Returns (exit_code, stdout)."""
        cmd_args = list(args)
        if json_output and "--json" not in cmd_args:
            cmd_args.append("--json")

        if self.ssh_host:
            # Remote execution via SSH
            remote_cmd = f"{self.ssh_user_prefix} {self.agent_swift} {' '.join(cmd_args)}"
            full_cmd = ["ssh", self.ssh_host, remote_cmd]
        else:
            full_cmd = [self.agent_swift] + cmd_args

        try:
            result = subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=30
            )
            return result.returncode, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return 1, "TIMEOUT"
        except FileNotFoundError:
            return 1, f"agent-swift not found at: {self.agent_swift}"

    def _invalidate_cache(self):
        """Invalidate snapshot cache after mutations."""
        self._snapshot_cache = None

    def snapshot_json(self, interactive_only: bool = False) -> list[dict]:
        """Get current element snapshot as parsed JSON."""
        args = ["snapshot"]
        if interactive_only:
            args.append("-i")
        rc, out = self.run_as(*args, json_output=True)
        if rc != 0:
            return []
        try:
            data = json.loads(out)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def snapshot_interactive(self) -> list[dict]:
        """Get interactive elements only."""
        return self.snapshot_json(interactive_only=True)

    def _settle(self):
        """Wait for UI to settle after an action."""
        time.sleep(self.wait_time)

    def resolve_ref(self, value: str) -> str:
        """Resolve $variable references in a string."""
        if isinstance(value, str) and value.startswith("$"):
            var_name = value[1:]
            return self._variables.get(var_name, value)
        return str(value)

    def find_element(self, criteria: dict, elements: list[dict] | None = None) -> str | None:
        """Find an element matching criteria. Returns ref string or None.

        Criteria keys: type, label, value, value_contains, text, text_contains,
                       role, identifier, identifier_prefix
        """
        if elements is None:
            elements = self.snapshot_json()

        for elem in elements:
            match = True
            if "type" in criteria and elem.get("type") != criteria["type"]:
                match = False
            if "label" in criteria and elem.get("label") != criteria["label"]:
                match = False
            if "value" in criteria and elem.get("value") != criteria["value"]:
                match = False
            if "value_contains" in criteria:
                val = elem.get("value") or ""
                if criteria["value_contains"] not in val:
                    match = False
            if "text" in criteria:
                # Check both value and label fields for text match
                text = criteria["text"]
                elem_value = elem.get("value") or ""
                elem_label = elem.get("label") or ""
                if text not in elem_value and text not in elem_label:
                    match = False
            if "text_contains" in criteria:
                text = criteria["text_contains"]
                elem_value = elem.get("value") or ""
                elem_label = elem.get("label") or ""
                if text not in elem_value and text not in elem_label:
                    match = False
            if "role" in criteria and elem.get("role", elem.get("type")) != criteria["role"]:
                match = False
            if "identifier" in criteria and elem.get("identifier") != criteria["identifier"]:
                match = False
            if "identifier_prefix" in criteria:
                ident = elem.get("identifier") or ""
                if not ident.startswith(criteria["identifier_prefix"]):
                    match = False
            if match:
                return elem.get("ref")
        return None

    def find_all_elements(self, criteria: dict, elements: list[dict] | None = None) -> list[dict]:
        """Find all elements matching criteria."""
        if elements is None:
            elements = self.snapshot_json()
        results = []
        for elem in elements:
            match = True
            if "type" in criteria and elem.get("type") != criteria["type"]:
                match = False
            if "label" in criteria and elem.get("label") != criteria["label"]:
                match = False
            if "value" in criteria and elem.get("value") != criteria["value"]:
                match = False
            if "value_contains" in criteria:
                val = elem.get("value") or ""
                if criteria["value_contains"] not in val:
                    match = False
            if "text" in criteria:
                text = criteria["text"]
                elem_value = elem.get("value") or ""
                elem_label = elem.get("label") or ""
                if text not in elem_value and text not in elem_label:
                    match = False
            if "text_contains" in criteria:
                text = criteria["text_contains"]
                elem_value = elem.get("value") or ""
                elem_label = elem.get("label") or ""
                if text not in elem_value and text not in elem_label:
                    match = False
            if "identifier_prefix" in criteria:
                ident = elem.get("identifier") or ""
                if not ident.startswith(criteria["identifier_prefix"]):
                    match = False
            if match:
                results.append(elem)
        return results

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------

    def setup(self, flow: dict) -> bool:
        """Connect to the app and verify it's ready."""
        bundle_id = self.bundle_id or flow.get("bundle_id", "com.omi.desktop-dev")
        flow_name = flow.get("name", "unknown")

        print(f"\n=== E2E: {flow_name} ===\n")

        # Check connection status
        rc, out = self.run_as("status", json_output=True)
        connected = False
        if rc == 0:
            try:
                status = json.loads(out)
                connected = status.get("connected", False)
            except (json.JSONDecodeError, TypeError):
                pass

        if not connected:
            print(f"[setup] Connecting to {bundle_id}...")
            rc, out = self.run_as("connect", "--bundle-id", bundle_id)
            if rc != 0:
                print(f"[setup] Could not connect: {out}")
                return False
            print("[setup] Connected")
        else:
            print("[setup] Already connected")

        # Health check
        elements = self.snapshot_interactive()
        count = len(elements)
        if count >= 3:
            print(f"[setup] Ready ({count} interactive elements)")
        else:
            print(f"[setup] App may not be fully loaded ({count} elements)")

        self._connected = True
        self._variables.clear()
        os.makedirs(self.screenshot_dir, exist_ok=True)
        return True

    def teardown(self, result: FlowResult):
        """Print summary."""
        print(f"\n=== {result.name}: {result.pass_count} passed, "
              f"{result.fail_count} failed, {result.skip_count} skipped ===")
        if result.fail_count > 0:
            print("FAILURES:")
            for s in result.steps:
                if not s.passed and not s.optional:
                    print(f"  - {s.name}: {s.message}")

    # ------------------------------------------------------------------
    # Step action handlers
    # ------------------------------------------------------------------

    def do_click(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle click action."""
        click_spec = step.get("click")
        if click_spec is None:
            return None

        if isinstance(click_spec, dict):
            # Find element by criteria
            ref = self._find_by_spec(click_spec)
            if ref is None:
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message=f"Could not find element for click: {click_spec}",
                    optional=step.get("optional", False)
                )
            print(f"  click @{ref}")
            self.run_as("click", f"@{ref}")
        else:
            # Direct ref
            resolved = self.resolve_ref(str(click_spec))
            print(f"  click @{resolved}")
            self.run_as("click", f"@{resolved}")

        self._invalidate_cache()
        self._settle()
        return None  # Success, continue processing step

    def do_press(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle press action (AXPress for AppKit/Settings sidebar)."""
        press_spec = step.get("press")
        if press_spec is None:
            return None

        if isinstance(press_spec, dict):
            ref = self._find_by_spec(press_spec)
            if ref is None:
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message=f"Could not find element for press: {press_spec}",
                    optional=step.get("optional", False)
                )
            print(f"  press @{ref}")
            self.run_as("press", f"@{ref}")
        else:
            resolved = self.resolve_ref(str(press_spec))
            print(f"  press @{resolved}")
            self.run_as("press", f"@{resolved}")

        self._invalidate_cache()
        self._settle()
        return None

    def do_fill(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle fill action."""
        fill_spec = step.get("fill")
        if fill_spec is None:
            return None

        if isinstance(fill_spec, dict):
            field_type = fill_spec.get("type", "textfield")
            value = fill_spec.get("value", "")
            # Find a text field
            elements = self.snapshot_json()
            field_types = ["textfield", "textarea", "searchfield"]
            if field_type not in field_types:
                field_types = [field_type]
            ref = None
            for elem in elements:
                if elem.get("type") in field_types:
                    ref = elem.get("ref")
                    break
            if ref is None:
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message="No text field found",
                    optional=step.get("optional", False)
                )
            print(f"  fill @{ref} \"{value}\"")
            self.run_as("fill", f"@{ref}", value)
        else:
            print(f"  fill {fill_spec}")
            return StepResult(
                name=step.get("name", f"step {step_num}"),
                passed=False,
                message="fill requires a dict with type and value",
                optional=step.get("optional", False)
            )

        self._invalidate_cache()
        self._settle()
        return None

    def do_scroll(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle scroll action."""
        scroll_spec = step.get("scroll")
        if scroll_spec is None:
            return None

        directions = scroll_spec if isinstance(scroll_spec, list) else [scroll_spec]
        for direction in directions:
            print(f"  scroll {direction}")
            rc, _ = self.run_as("scroll", str(direction))
            if rc != 0:
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message=f"scroll {direction} failed",
                    optional=step.get("optional", False)
                )
            self._settle()

        self._invalidate_cache()
        return None

    def do_wait(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle wait action."""
        wait_spec = step.get("wait")
        if wait_spec is None:
            return None

        if isinstance(wait_spec, dict):
            timeout = str(wait_spec.get("timeout", 5000))
            if "text" in wait_spec:
                text = wait_spec["text"]
                print(f"  wait text \"{text}\" (timeout {timeout}ms)")
                rc, _ = self.run_as("wait", "text", text, "--timeout", timeout)
            elif "exists" in wait_spec:
                ref = self.resolve_ref(wait_spec["exists"])
                print(f"  wait exists @{ref} (timeout {timeout}ms)")
                rc, _ = self.run_as("wait", "exists", f"@{ref}", "--timeout", timeout)
            else:
                return None
            if rc != 0:
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message=f"wait timed out: {wait_spec}",
                    optional=step.get("optional", False)
                )
        return None

    def do_assert(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle assert action."""
        assert_spec = step.get("assert")
        if assert_spec is None:
            return None

        # Normalize to list
        specs = assert_spec if isinstance(assert_spec, list) else [assert_spec]
        elements = self.snapshot_json()

        for spec in specs:
            result = self._check_assertion(spec, elements, step, step_num)
            if result is not None:
                return result
        return None

    def _check_assertion(self, spec: dict, elements: list[dict],
                         step: dict, step_num: int) -> StepResult | None:
        """Check a single assertion. Returns StepResult on failure, None on success."""
        name = step.get("name", f"step {step_num}")
        optional = step.get("optional", False)

        # interactive_count assertion
        if "interactive_count" in spec:
            count_spec = spec["interactive_count"]
            interactive = self.snapshot_interactive()
            count = len(interactive)
            min_count = count_spec.get("min", 0)
            if count < min_count:
                return StepResult(name=name, passed=False,
                                  message=f"interactive count {count} < min {min_count}",
                                  optional=optional)
            print(f"  assert interactive_count >= {min_count}: {count} (OK)")
            return None

        # exists assertion
        if "exists" in spec:
            ref = self.resolve_ref(spec["exists"])
            rc, _ = self.run_as("is", "exists", f"@{ref}")
            if rc != 0:
                return StepResult(name=name, passed=False,
                                  message=f"element @{ref} does not exist",
                                  optional=optional)
            print(f"  assert exists @{ref}: OK")
            return None

        # not_exists assertion
        if "not_exists" in spec:
            ref = self.resolve_ref(spec["not_exists"])
            rc, _ = self.run_as("is", "exists", f"@{ref}")
            if rc == 0:
                return StepResult(name=name, passed=False,
                                  message=f"element @{ref} unexpectedly exists",
                                  optional=optional)
            print(f"  assert not_exists @{ref}: OK")
            return None

        # text assertion
        if "text" in spec:
            text = spec["text"]
            found = any(
                text in (e.get("value") or "") or text in (e.get("label") or "")
                for e in elements
            )
            if not found:
                return StepResult(name=name, passed=False,
                                  message=f"text \"{text}\" not found",
                                  optional=optional)
            print(f"  assert text \"{text}\": found")
            return None

        # type + min_count assertion
        if "type" in spec and "min_count" in spec:
            elem_type = spec["type"]
            min_count = spec["min_count"]

            # Handle identifier_prefixes filter
            if "identifier_prefixes" in spec:
                prefixes = spec["identifier_prefixes"]
                matching = [
                    e for e in elements
                    if e.get("type") == elem_type
                    and any((e.get("identifier") or "").startswith(p) for p in prefixes)
                ]
            else:
                matching = [e for e in elements if e.get("type") == elem_type]

            count = len(matching)
            if count < min_count:
                return StepResult(name=name, passed=False,
                                  message=f"found {count} {elem_type} elements, need >= {min_count}",
                                  optional=optional)
            print(f"  assert {elem_type} count >= {min_count}: {count} (OK)")
            return None

        # type + max_count assertion
        if "type" in spec and "max_count" in spec:
            elem_type = spec["type"]
            max_count = spec["max_count"]
            matching = [e for e in elements if e.get("type") == elem_type]
            count = len(matching)
            if count > max_count:
                return StepResult(name=name, passed=False,
                                  message=f"found {count} {elem_type} elements, need <= {max_count}",
                                  optional=optional)
            print(f"  assert {elem_type} count <= {max_count}: {count} (OK)")
            return None

        # type + label assertion (element exists with that type and label)
        if "type" in spec and "label" in spec:
            elem_type = spec["type"]
            label = spec["label"]
            found = any(
                e.get("type") == elem_type and e.get("label") == label
                for e in elements
            )
            if not found:
                return StepResult(name=name, passed=False,
                                  message=f"element type={elem_type} label={label} not found",
                                  optional=optional)
            print(f"  assert {elem_type} label=\"{label}\": found")
            return None

        return None

    def do_find(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle find action."""
        find_spec = step.get("find")
        if find_spec is None:
            return None

        if isinstance(find_spec, dict):
            # Use agent-swift find command for role-based searches
            if "role" in find_spec:
                rc, out = self.run_as("find", "role", find_spec["role"], json_output=True)
                if rc == 0:
                    try:
                        data = json.loads(out)
                        ref = data.get("ref", "")
                        if ref:
                            print(f"  find role {find_spec['role']} -> @{ref}")
                            if "save_ref" in step:
                                self._variables[step["save_ref"]] = ref
                            return None
                    except (json.JSONDecodeError, TypeError):
                        pass
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message=f"find returned no results: {find_spec}",
                    optional=step.get("optional", False)
                )
            else:
                ref = self.find_element(find_spec)
                if ref:
                    print(f"  find {find_spec} -> @{ref}")
                    if "save_ref" in step:
                        self._variables[step["save_ref"]] = ref
                    return None
                return StepResult(
                    name=step.get("name", f"step {step_num}"),
                    passed=False,
                    message=f"find returned no results: {find_spec}",
                    optional=step.get("optional", False)
                )
        return None

    def do_get(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle get action — read a property value."""
        get_spec = step.get("get")
        if get_spec is None:
            return None

        if isinstance(get_spec, dict):
            prop = get_spec.get("property", "value")

            # Find element by type or ref
            if "ref" in get_spec:
                ref = self.resolve_ref(get_spec["ref"])
            elif "type" in get_spec:
                elements = self.snapshot_json()
                matching = [e for e in elements if e.get("type") == get_spec["type"]]
                if not matching:
                    return StepResult(
                        name=step.get("name", f"step {step_num}"),
                        passed=False,
                        message=f"no element of type {get_spec['type']} for get",
                        optional=step.get("optional", False)
                    )
                ref = matching[0].get("ref", "")
            else:
                return None

            rc, out = self.run_as("get", prop, f"@{ref}", json_output=True)
            if rc == 0:
                try:
                    data = json.loads(out)
                    value = data.get("value", "?")
                    print(f"  get {prop} @{ref} = {value}")
                    if "save_as" in step:
                        self._variables[step["save_as"]] = str(value)
                    return None
                except (json.JSONDecodeError, TypeError):
                    pass
            return StepResult(
                name=step.get("name", f"step {step_num}"),
                passed=False,
                message=f"get {prop} @{ref} failed",
                optional=step.get("optional", False)
            )
        return None

    def do_dismiss(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle dismiss action — non-fatal press for optional dialogs."""
        dismiss_spec = step.get("dismiss")
        if dismiss_spec is None:
            return None

        if isinstance(dismiss_spec, dict) and "text" in dismiss_spec:
            text = dismiss_spec["text"]
            ref = self.find_element({"text": text})
            if ref:
                print(f"  dismiss \"{text}\" @{ref}")
                self.run_as("press", f"@{ref}")
                self._invalidate_cache()
                self._settle()
            else:
                print(f"  dismiss \"{text}\": not found (OK)")
        return None

    def do_screenshot(self, step: dict, flow_name: str, step_num: int) -> str:
        """Handle screenshot action. Returns screenshot path."""
        screenshot_name = step.get("screenshot")
        if screenshot_name is None or self.fast_mode:
            return ""

        path = os.path.join(
            self.screenshot_dir,
            f"{flow_name}-{step_num:02d}-{screenshot_name}.png"
        )
        rc, _ = self.run_as("screenshot", path)
        if rc == 0:
            print(f"  screenshot: {path}")
        return path

    def do_assert_each(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle assert_each — check multiple labels of same type exist."""
        spec = step.get("assert_each")
        if spec is None:
            return None

        elem_type = spec.get("type", "")
        labels = spec.get("labels", [])
        min_found = spec.get("min_found", len(labels))

        elements = self.snapshot_json()
        found = 0
        for label in labels:
            matching = [
                e for e in elements
                if e.get("type") == elem_type and e.get("label") == label
            ]
            if matching:
                found += 1
                print(f"  found {elem_type} \"{label}\": @{matching[0].get('ref', '?')}")

        if found >= min_found:
            print(f"  assert_each: {found}/{len(labels)} found (need >= {min_found})")
            return None
        return StepResult(
            name=step.get("name", f"step {step_num}"),
            passed=False,
            message=f"assert_each: only {found}/{len(labels)} found, need >= {min_found}",
            optional=step.get("optional", False)
        )

    def do_navigate_sidebar(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle navigate_sidebar — click through a list of sidebar items."""
        items = step.get("navigate_sidebar")
        if items is None:
            return None

        action = step.get("action", "click")  # click or press
        min_success = step.get("min_success", 1)
        screenshot_each = step.get("screenshot_each", False)

        success = 0
        for item in items:
            elements = self.snapshot_json()
            ref = self.find_element(item, elements)
            label = item.get("label", "?")
            if ref:
                print(f"  {action} \"{label}\" @{ref}")
                self.run_as(action, f"@{ref}")
                self._invalidate_cache()
                self._settle()
                success += 1
                if screenshot_each and not self.fast_mode:
                    path = os.path.join(
                        self.screenshot_dir,
                        f"{flow_name}-{step_num:02d}-{label}.png"
                    )
                    self.run_as("screenshot", path)
            else:
                print(f"  {label}: not found")

        if success >= min_success:
            print(f"  navigate_sidebar: {success}/{len(items)} succeeded")
            return None
        return StepResult(
            name=step.get("name", f"step {step_num}"),
            passed=False,
            message=f"navigate_sidebar: only {success}/{len(items)}, need >= {min_success}",
            optional=step.get("optional", False)
        )

    def do_click_menu_item(self, step: dict, flow_name: str, step_num: int) -> StepResult | None:
        """Handle click_menu_item — try clicking menu items by label."""
        spec = step.get("click_menu_item")
        if spec is None:
            return None

        try_labels = spec.get("try_labels", [])
        elements = self.snapshot_json()

        for label in try_labels:
            matching = [
                e for e in elements
                if e.get("type") == "menuitem"
                and (label in (e.get("label") or "") or label in (e.get("value") or ""))
            ]
            if matching:
                ref = matching[0].get("ref", "")
                print(f"  click_menu_item \"{label}\" @{ref}")
                self.run_as("click", f"@{ref}")
                self._invalidate_cache()
                self._settle()
                return None

        print(f"  click_menu_item: none of {try_labels} found")
        return StepResult(
            name=step.get("name", f"step {step_num}"),
            passed=False,
            message=f"no menu item found from: {try_labels}",
            optional=step.get("optional", False)
        )

    def _find_by_spec(self, spec: dict) -> str | None:
        """Find element ref from a click/press spec dict."""
        elements = self.snapshot_json()

        # Build criteria from spec
        criteria = {}
        for key in ("type", "label", "value", "value_contains", "text",
                     "text_contains", "role", "identifier"):
            if key in spec:
                criteria[key] = spec[key]

        ref = self.find_element(criteria, elements)

        # Fallback label search
        if ref is None and "fallback_label" in spec:
            ref = self.find_element({"label": spec["fallback_label"]}, elements)

        return ref

    # ------------------------------------------------------------------
    # Main step executor
    # ------------------------------------------------------------------

    def execute_step(self, step: dict, flow_name: str, step_num: int) -> StepResult:
        """Execute a single step, dispatching to action handlers."""
        name = step.get("name", f"step {step_num}")
        optional = step.get("optional", False)

        print(f"\n--- Step {step_num}: {name} ---")

        # Process actions in deterministic order
        action_order = [
            "find", "dismiss",
            "click", "press", "fill", "scroll",
            "wait",
            "get",
            "assert", "assert_each",
            "navigate_sidebar", "click_menu_item",
        ]

        screenshot_path = ""

        for action_name in action_order:
            if action_name not in step:
                continue

            handler = getattr(self, f"do_{action_name}", None)
            if handler is None:
                continue

            result = handler(step, flow_name, step_num)
            if result is not None:
                # Action failed
                return result

            # Take screenshot after mutation actions if specified between them
            # (screenshots after the full step are handled below)

        # Handle save_ref from find results (already handled in do_find)

        # Take screenshot at end of step
        if "screenshot" in step:
            screenshot_path = self.do_screenshot(step, flow_name, step_num)

        return StepResult(
            name=name, passed=True,
            message="OK", screenshot=screenshot_path,
            optional=optional
        )

    # ------------------------------------------------------------------
    # Flow execution
    # ------------------------------------------------------------------

    def run_flow(self, flow_path: str) -> FlowResult:
        """Load and run a complete flow from YAML."""
        flow = load_yaml(flow_path)
        flow_name = flow.get("name", Path(flow_path).stem)
        result = FlowResult(name=flow_name)

        if not self.setup(flow):
            result.steps.append(StepResult(
                name="setup", passed=False, message="Could not connect to app"
            ))
            self.teardown(result)
            return result

        steps = flow.get("steps", [])
        for i, step in enumerate(steps, 1):
            step_result = self.execute_step(step, flow_name, i)
            result.steps.append(step_result)
            status = "PASS" if step_result.passed else ("SKIP" if step_result.optional else "FAIL")
            if not step_result.passed:
                print(f"  [{status}] {step_result.message}")
            else:
                print(f"  [PASS]")

        self.teardown(result)
        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_flows_dir() -> Path:
    """Get the flows directory path."""
    return Path(__file__).parent / "flows"


def list_flows():
    """List all available flows."""
    flows_dir = get_flows_dir()
    if not flows_dir.exists():
        print("No flows directory found")
        return

    print(f"\n{'Flow':<20} {'Description':<60} {'Covers'}")
    print("-" * 120)

    for yaml_file in sorted(flows_dir.glob("*.yaml")):
        try:
            flow = load_yaml(str(yaml_file))
            name = flow.get("name", yaml_file.stem)
            desc = flow.get("description", "")[:58]
            covers = ", ".join(
                Path(c).name for c in flow.get("covers", [])
            )
            print(f"{name:<20} {desc:<60} {covers}")
        except Exception as e:
            print(f"{yaml_file.stem:<20} ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="YAML-based E2E test runner for Omi desktop app"
    )
    parser.add_argument("flow", nargs="?", help="Flow name to run (without .yaml)")
    parser.add_argument("--all", action="store_true", help="Run all flows")
    parser.add_argument("--list", action="store_true", help="List available flows")
    parser.add_argument("--video", action="store_true", help="Generate MP4 from screenshots")

    args = parser.parse_args()

    if args.list:
        list_flows()
        return

    flows_dir = get_flows_dir()

    if args.all:
        flow_files = sorted(flows_dir.glob("*.yaml"))
        if not flow_files:
            print("No flow files found")
            sys.exit(1)
    elif args.flow:
        flow_path = flows_dir / f"{args.flow}.yaml"
        if not flow_path.exists():
            print(f"Flow not found: {flow_path}")
            print(f"Available flows: {', '.join(f.stem for f in flows_dir.glob('*.yaml'))}")
            sys.exit(1)
        flow_files = [flow_path]
    else:
        parser.print_help()
        return

    runner = FlowRunner()
    all_results = []
    total_pass = 0
    total_fail = 0

    for flow_file in flow_files:
        result = runner.run_flow(str(flow_file))
        all_results.append(result)
        total_pass += result.pass_count
        total_fail += result.fail_count

    if len(flow_files) > 1:
        print(f"\n{'=' * 60}")
        print(f"TOTAL: {total_pass} passed, {total_fail} failed across {len(flow_files)} flows")
        print(f"{'=' * 60}")

    if args.video and not runner.fast_mode:
        _generate_video(runner.screenshot_dir)

    sys.exit(1 if total_fail > 0 else 0)


def _generate_video(screenshot_dir: str):
    """Generate MP4 from screenshots using ffmpeg."""
    png_files = sorted(Path(screenshot_dir).glob("*.png"))
    if not png_files:
        print("No screenshots to create video from")
        return

    output = os.path.join(screenshot_dir, "e2e-result.mp4")
    # Create a file list for ffmpeg
    list_file = os.path.join(screenshot_dir, "ffmpeg-input.txt")
    with open(list_file, "w") as f:
        for png in png_files:
            f.write(f"file '{png}'\n")
            f.write("duration 1.5\n")
        # Last frame needs an entry without duration
        f.write(f"file '{png_files[-1]}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", output
    ], capture_output=True)

    if os.path.exists(output):
        size_kb = os.path.getsize(output) // 1024
        print(f"\nVideo: {output} ({size_kb}KB)")
    else:
        print("\nVideo generation failed")


if __name__ == "__main__":
    main()
