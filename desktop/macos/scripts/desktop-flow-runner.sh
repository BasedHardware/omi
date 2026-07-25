#!/usr/bin/env bash
# Run desktop e2e flows through flow-walker's full pipeline → shareable HTML report.
#
# Usage:
#   ./scripts/desktop-flow-runner.sh flows/navigation.yaml --bundle-id com.omi.computer-macos.beta
#   ./scripts/desktop-flow-runner.sh flows/navigation.yaml --bundle-id com.omi.omi-test --push
#   ./scripts/desktop-flow-runner.sh --all --bundle-id com.omi.computer-macos.beta --push
#
# The script drives flow-walker's 6-stage pipeline:
#   record init → execute steps via agent-swift → record stream → record finish → verify → report [→ push]
#
# On first run, agent-swift discovers UI elements and streams coordinates.
# On subsequent runs, flow-walker loads the cached snapshot for fast replay.
# The HTML report is self-contained and can be shared as a URL via --push.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
E2E_DIR="$(cd "$SCRIPT_DIR/../e2e" && pwd)"
FLOWS_DIR="$E2E_DIR/flows"
RUNS_DIR="$E2E_DIR/runs"
AGENT_SWIFT="${AGENT_SWIFT_PATH:-$(command -v agent-swift 2>/dev/null || echo "")}"
FLOW_WALKER="${FLOW_WALKER_PATH:-$(command -v flow-walker 2>/dev/null || echo "")}"

BUNDLE_ID=""
PUSH=0
ALL_FLOWS=0
FLOW_FILE=""
TIER_FILTER=""
VERBOSE=0

usage() {
  cat <<'USAGE'
Usage: desktop-flow-runner.sh [flow.yaml | --all] [options]

Arguments:
  flow.yaml          Path to a single flow YAML file (relative to e2e/flows/)
  --all              Run all flows in e2e/flows/

Options:
  --bundle-id ID     Target app bundle ID (required)
  --tier N           Filter flows by tier (1, 2, manual)
  --push             Upload HTML report and print shareable URL
  --verbose          Show detailed output during execution
  --help             Show this help

Examples:
  ./scripts/desktop-flow-runner.sh flows/navigation.yaml --bundle-id com.omi.computer-macos.beta
  ./scripts/desktop-flow-runner.sh --all --tier manual --bundle-id com.omi.omi-test --push
USAGE
  exit 0
}

die() { echo "ERROR: $*" >&2; exit 1; }

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bundle-id) BUNDLE_ID="$2"; shift 2 ;;
      --push) PUSH=1; shift ;;
      --all) ALL_FLOWS=1; shift ;;
      --tier) TIER_FILTER="$2"; shift 2 ;;
      --verbose) VERBOSE=1; shift ;;
      --help|-h) usage ;;
      -*) die "unknown option: $1" ;;
      *)
        if [[ -z "$FLOW_FILE" ]]; then
          FLOW_FILE="$1"
        else
          die "unexpected argument: $1"
        fi
        shift ;;
    esac
  done

  [[ -n "$BUNDLE_ID" ]] || die "--bundle-id is required"
  [[ "$ALL_FLOWS" = "1" ]] || [[ -n "$FLOW_FILE" ]] || die "specify a flow YAML or --all"
  [[ -n "$AGENT_SWIFT" ]] || die "agent-swift not found; install with: brew install beastoin/tap/agent-swift"
  [[ -n "$FLOW_WALKER" ]] || die "flow-walker not found; install with: npm install -g flow-walker-cli"
}

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
vlog() { [[ "$VERBOSE" = "1" ]] && log "$*" || true; }

resolve_flow_path() {
  local f="$1"
  if [[ -f "$f" ]]; then echo "$f"; return; fi
  if [[ -f "$FLOWS_DIR/$f" ]]; then echo "$FLOWS_DIR/$f"; return; fi
  if [[ -f "$FLOWS_DIR/${f}.yaml" ]]; then echo "$FLOWS_DIR/${f}.yaml"; return; fi
  die "flow not found: $f"
}

get_flow_tier() {
  local yaml_file="$1"
  python3 -c "
import sys
try:
    import yaml
except ImportError:
    print('manual')
    sys.exit(0)
with open('$yaml_file') as f:
    d = yaml.safe_load(f) or {}
print(d.get('tier', 'manual'))
"
}

connect_agent_swift() {
  log "Connecting agent-swift to $BUNDLE_ID..."
  local result
  result=$("$AGENT_SWIFT" connect --bundle-id "$BUNDLE_ID" 2>&1) || {
    echo "$result" >&2
    die "Failed to connect agent-swift to $BUNDLE_ID. Is the app running?"
  }
  vlog "Connected: $result"
}

snapshot_interactive() {
  "$AGENT_SWIFT" snapshot -i --json 2>/dev/null || echo "[]"
}

snapshot_full() {
  "$AGENT_SWIFT" snapshot --json 2>/dev/null || echo "[]"
}

take_screenshot() {
  local path="$1"
  "$AGENT_SWIFT" screenshot "$path" 2>/dev/null || true
}

check_text_visible() {
  local text="$1"
  local full_snap
  full_snap=$(snapshot_full)
  echo "$full_snap" | python3 -c "
import json, sys
target = sys.argv[1].lower()
def search(nodes):
    for n in nodes:
        label = (n.get('label') or '').lower()
        title = (n.get('title') or '').lower()
        value = (n.get('value') or '').lower()
        if target in label or target in title or target in value:
            return True
        children = n.get('children', [])
        if children and search(children):
            return True
    return False
data = json.load(sys.stdin)
print('true' if search(data) else 'false')
" "$text" 2>/dev/null || echo "false"
}

check_interactive_count() {
  local min_count="$1"
  local snap
  snap=$(snapshot_interactive)
  local count
  count=$(echo "$snap" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len([e for e in data if e.get('enabled', True)]))
" 2>/dev/null || echo "0")
  [[ "$count" -ge "$min_count" ]] && echo "true" || echo "false"
}

run_single_flow() {
  local flow_path="$1"
  local flow_name
  flow_name=$(basename "$flow_path" .yaml)

  log "━━━ Running flow: $flow_name ━━━"

  mkdir -p "$RUNS_DIR"

  # Stage 1: record init
  vlog "Stage 1: record init"
  local init_json
  init_json=$("$FLOW_WALKER" record init \
    --flow "$flow_path" \
    --output-dir "$RUNS_DIR" \
    --no-video \
    --json 2>/dev/null) || die "record init failed for $flow_name"

  local run_id run_dir replay_mode
  run_id=$(echo "$init_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  run_dir=$(echo "$init_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['dir'])")
  replay_mode=$(echo "$init_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('replay', {})
print(r.get('mode', 'fresh'))
" 2>/dev/null || echo "fresh")

  log "Run ID: $run_id | Dir: $run_dir | Mode: $replay_mode"

  # Parse flow steps
  local steps_json
  steps_json=$(python3 -c "
import json, sys
try:
    import yaml
except ImportError:
    print('[]')
    sys.exit(0)
with open('$flow_path') as f:
    d = yaml.safe_load(f) or {}
steps = d.get('steps', [])
print(json.dumps(steps))
")

  local step_count
  step_count=$(echo "$steps_json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")

  # Parse replay plan for cached coordinates
  local replay_steps
  replay_steps=$(echo "$init_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('replay', {})
print(json.dumps(r.get('steps', {})))
" 2>/dev/null || echo "{}")

  # Stage 2: execute steps and collect events
  vlog "Stage 2: executing $step_count steps"
  local events_file="$run_dir/events.jsonl"
  local overall_status="pass"
  > "$events_file"

  # run.start event
  echo "{\"type\":\"run.start\",\"run_id\":\"$run_id\",\"flow\":\"$flow_name\",\"platform\":\"macos\"}" >> "$events_file"

  local step_idx=0
  while [[ "$step_idx" -lt "$step_count" ]]; do
    local step_id step_name step_do
    step_id=$(echo "$steps_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[$step_idx].get('id','S$((step_idx+1))'))")
    step_name=$(echo "$steps_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[$step_idx].get('name','Step $((step_idx+1))'))")
    step_do=$(echo "$steps_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[$step_idx].get('do',''))")

    log "  [$step_id] $step_name"

    # step.start
    echo "{\"type\":\"step.start\",\"step_id\":\"$step_id\",\"name\":\"$step_name\"}" >> "$events_file"

    local step_outcome="pass"

    if [[ -n "$step_do" ]]; then
      # Take pre-action snapshot
      local pre_snapshot
      pre_snapshot=$(snapshot_interactive)
      vlog "    Pre-snapshot: $(echo "$pre_snapshot" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo '?') elements"

      # Check for cached replay coordinates
      local has_replay
      has_replay=$(echo "$replay_steps" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('true' if '$step_id' in d and 'center' in d['$step_id'] else 'false')
" 2>/dev/null || echo "false")

      # Execute the step action
      local action_command="observe"
      local action_ref=""
      local action_text=""
      local action_bounds_json=""

      if echo "$step_do" | grep -qi "click\|tap\|press"; then
        action_command="click"
        # Extract click target from do: instruction
        action_text=$(echo "$step_do" | python3 -c "
import re, sys
text = sys.stdin.read()
# Priority 1: explicit (label 'X') or find text 'X'
m = re.search(r\"(?:label|find text|find label) ['\\\"]([^'\\\"]+)['\\\"]\", text, re.I)
if m: print(m.group(1)); sys.exit(0)
# Priority 2: 'Click X' where X is a single-quoted target
m = re.search(r\"(?:click|tap|press) ['\\\"]([^'\\\"]+)['\\\"]\", text, re.I)
if m: print(m.group(1)); sys.exit(0)
# Priority 3: 'Click the X button/icon/tab'
m = re.search(r'(?:click|tap|press) (?:the |on )?(.+?)(?:\s+(?:button|icon|tab|link|menu item|gear|section|row))', text, re.I)
if m:
    val = m.group(1).strip().strip(\"'\\\"\")
    if val: print(val); sys.exit(0)
# Priority 4: 'Click the X' at sentence boundary
m = re.search(r'(?:click|tap|press) (?:the |on )?([A-Z][a-zA-Z &]+?)(?:\.|,|\s+to\s|\s+in\s|\s+and\s|$)', text, re.I)
if m: print(m.group(1).strip()); sys.exit(0)
print('')
" 2>/dev/null || echo "")

        local clicked=0

        # Try replay cached coordinates first for speed
        if [[ "$has_replay" = "true" ]]; then
          local cx cy
          cx=$(echo "$replay_steps" | python3 -c "import json,sys; print(int(json.load(sys.stdin)['$step_id']['center']['x']))" 2>/dev/null || echo "0")
          cy=$(echo "$replay_steps" | python3 -c "import json,sys; print(int(json.load(sys.stdin)['$step_id']['center']['y']))" 2>/dev/null || echo "0")
          if [[ "$cx" != "0" ]] && [[ "$cy" != "0" ]]; then
            vlog "    Action: click cached ($cx, $cy)"
            "$AGENT_SWIFT" click "$cx" "$cy" 2>/dev/null || true
            clicked=1
          fi
        fi

        if [[ "$clicked" = "0" ]] && [[ -n "$action_text" ]]; then
          vlog "    Action: click text='$action_text'"
          local click_result
          click_result=$("$AGENT_SWIFT" find text "$action_text" click 2>&1) && clicked=1 || {
            click_result=$("$AGENT_SWIFT" find label "$action_text" click 2>&1) && clicked=1 || true
          }
          if [[ "$clicked" = "1" ]]; then
            action_ref=$(echo "$click_result" | python3 -c "
import json, sys
try: d = json.load(sys.stdin); print(d.get('ref', ''))
except: print('')
" 2>/dev/null || echo "")
            action_bounds_json=$(echo "$click_result" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    b = d.get('bounds', {})
    if b: print(json.dumps(b))
    else: print('')
except: print('')
" 2>/dev/null || echo "")
          fi
        fi

        [[ "$clicked" = "0" ]] && vlog "    No actionable click target found"
      fi

      # Emit action event with replay-friendly metadata
      local action_extra=""
      [[ -n "$action_ref" ]] && action_extra=",\"element_ref\":\"$action_ref\""
      [[ -n "$action_text" ]] && action_extra="$action_extra,\"element_text\":\"$action_text\""
      [[ -n "$action_bounds_json" ]] && action_extra="$action_extra,\"element_bounds\":$action_bounds_json"
      echo "{\"type\":\"action\",\"step_id\":\"$step_id\",\"command\":\"$action_command\"$action_extra}" >> "$events_file"

      # Brief wait for UI to settle
      sleep 0.5

      # Take post-action screenshot
      local screenshot_path="$run_dir/step-${step_id}.png"
      take_screenshot "$screenshot_path"
      if [[ -f "$screenshot_path" ]]; then
        echo "{\"type\":\"artifact\",\"step_id\":\"$step_id\",\"kind\":\"screenshot\",\"path\":\"step-${step_id}.png\"}" >> "$events_file"
      fi

      # Check expectations
      local expect_json
      expect_json=$(echo "$steps_json" | python3 -c "
import json, sys
step = json.load(sys.stdin)[$step_idx]
expect = step.get('expect', {})
print(json.dumps(expect))
" 2>/dev/null || echo "{}")

      # Check text_visible expectations
      local text_values
      text_values=$(echo "$expect_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
tv = d.get('text_visible', [])
if isinstance(tv, list):
    for v in tv:
        print(v)
" 2>/dev/null || true)

      if [[ -n "$text_values" ]]; then
        while IFS= read -r expected_text; do
          local found
          found=$(check_text_visible "$expected_text")
          echo "{\"type\":\"assert\",\"step_id\":\"$step_id\",\"kind\":\"text-visible\",\"passed\":$found,\"found\":[\"$expected_text\"]}" >> "$events_file"
          if [[ "$found" = "false" ]]; then
            vlog "    ASSERT FAIL: text '$expected_text' not visible"
            step_outcome="fail"
          fi
        done <<< "$text_values"
      fi

      # Check interactive_count expectations
      local min_interactive
      min_interactive=$(echo "$expect_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ic = d.get('interactive_count', {})
if isinstance(ic, dict):
    print(ic.get('min', ''))
elif isinstance(ic, int):
    print(ic)
else:
    print('')
" 2>/dev/null || echo "")

      if [[ -n "$min_interactive" ]]; then
        local count_ok
        count_ok=$(check_interactive_count "$min_interactive")
        echo "{\"type\":\"assert\",\"step_id\":\"$step_id\",\"kind\":\"interactive-count\",\"passed\":$count_ok}" >> "$events_file"
        if [[ "$count_ok" = "false" ]]; then
          vlog "    ASSERT FAIL: interactive count < $min_interactive"
          step_outcome="fail"
        fi
      fi
    else
      # No do: instruction — observation-only step
      echo "{\"type\":\"action\",\"step_id\":\"$step_id\",\"command\":\"observe\"}" >> "$events_file"
    fi

    # step.end
    echo "{\"type\":\"step.end\",\"step_id\":\"$step_id\",\"outcome\":\"$step_outcome\"}" >> "$events_file"
    [[ "$step_outcome" = "fail" ]] && overall_status="fail"

    log "  [$step_id] → $step_outcome"
    step_idx=$((step_idx + 1))
  done

  # run.end event
  echo "{\"type\":\"run.end\",\"run_id\":\"$run_id\",\"status\":\"$overall_status\"}" >> "$events_file"

  # Stage 3: stream events to flow-walker
  vlog "Stage 3: record stream"
  "$FLOW_WALKER" record stream \
    --run-id "$run_id" \
    --run-dir "$run_dir" \
    --json < "$events_file" > /dev/null 2>&1 || true

  # Stage 4: record finish
  vlog "Stage 4: record finish"
  "$FLOW_WALKER" record finish \
    --run-id "$run_id" \
    --run-dir "$run_dir" \
    --status "$overall_status" \
    --flow "$flow_path" \
    --json > /dev/null 2>&1 || true

  # Stage 5: verify
  vlog "Stage 5: verify"
  "$FLOW_WALKER" verify "$flow_path" \
    --run-dir "$run_dir" \
    --mode audit \
    --json > /dev/null 2>&1 || true

  # Stage 6: report
  log "Generating HTML report..."
  "$FLOW_WALKER" report "$run_dir" --json > /dev/null 2>&1 || true

  local report_html="$run_dir/report.html"
  if [[ -f "$report_html" ]]; then
    log "Report: $report_html"
  fi

  # Stage 7 (optional): push
  if [[ "$PUSH" = "1" ]]; then
    log "Pushing report..."
    local push_result
    push_result=$("$FLOW_WALKER" push "$run_dir" --json 2>/dev/null) || true
    local html_url
    html_url=$(echo "$push_result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('htmlUrl',''))" 2>/dev/null || echo "")
    if [[ -n "$html_url" ]]; then
      log "Shareable URL: $html_url"
    else
      log "Push failed or returned no URL"
      vlog "Push output: $push_result"
    fi
  fi

  log "━━━ Flow $flow_name: $overall_status ━━━"
  echo ""

  [[ "$overall_status" = "pass" ]] && return 0 || return 1
}

collect_flows() {
  if [[ "$ALL_FLOWS" = "1" ]]; then
    local flows=()
    for f in "$FLOWS_DIR"/*.yaml; do
      [[ -f "$f" ]] || continue
      if [[ -n "$TIER_FILTER" ]]; then
        local tier
        tier=$(get_flow_tier "$f")
        [[ "$tier" = "$TIER_FILTER" ]] || continue
      fi
      flows+=("$f")
    done
    echo "${flows[@]}"
  else
    resolve_flow_path "$FLOW_FILE"
  fi
}

main() {
  parse_args "$@"

  log "Desktop Flow Runner"
  log "Bundle: $BUNDLE_ID"

  # Connect agent-swift
  connect_agent_swift

  # Collect flows to run
  local flow_list
  flow_list=$(collect_flows)

  local total=0 passed=0 failed=0
  for flow in $flow_list; do
    total=$((total + 1))
    if run_single_flow "$flow"; then
      passed=$((passed + 1))
    else
      failed=$((failed + 1))
    fi
  done

  log "═══════════════════════════════════"
  log "Results: $passed/$total passed, $failed failed"
  log "═══════════════════════════════════"

  [[ "$failed" -eq 0 ]] && exit 0 || exit 1
}

main "$@"
