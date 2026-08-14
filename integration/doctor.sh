#!/bin/bash
# LIFECYCLE: permanent
# ============================================================================
# omi doctor — "what about this machine is not ready?", with an action per finding
# ============================================================================
#
# Standalone and disposable ON PURPOSE. It boots nothing, needs no state from a
# previous run, imports nothing from the launcher, and is safe to run against a
# live stack. Delete it and nothing else breaks.
#
# WHY THIS IS WORTH MORE THAN ANOTHER TEST LANE. The failures that cost the most
# were not test failures — they were environment failures that made every lane
# LIE. `pnpm install` exiting 0 without installing, so the build died with
# `tsc: command not found`. A `dist/` older than the source, so the cross-side
# test exercised yesterday's client and passed. The wrong branch checked out, so
# the backend entrypoint was absent. A green suite says nothing about any of
# these; each one is a single cheap probe.
#
# Every finding names the next action. A diagnostic that reports a problem
# without saying what to do about it just relocates the work.
#
#   integration/doctor.sh          # human
#   integration/doctor.sh --json   # machine: {ok, checks:[...], next_actions:[...]}
#
# Exit status: 0 if nothing is BROKEN. Warnings do not fail — this is a doctor,
# not a gate, and a doctor that refuses to finish its examination is useless.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
paths="$(node "$HERE/lib/provenance.mjs" --paths 2>/dev/null || true)"
read -r CORE_REPO PLATFORM_REPO WORKSPACE <<<"$(printf '%s' "$paths" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(`${j["core-foundation"]} ${j.platform} ${j.workspace}`)}catch{console.log("")}})')"
[[ -n "${CORE_REPO:-}" && -n "${PLATFORM_REPO:-}" ]] || { echo "BROKEN: repo paths could not be resolved" >&2; exit 1; }
SURFACES_DIST="$CORE_REPO/core/packages/surfaces/dist"

JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

if [[ -t 1 && $JSON -eq 0 ]]; then R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'
else R=""; G=""; Y=""; B=""; Z=""; fi

BROKEN=0
ROWS=()
ACTIONS=()

# status: ok | warn | broken
check() {
  local status="$1" name="$2" detail="$3" action="${4:-}"
  ROWS+=("$status"$'\t'"$name"$'\t'"$detail"$'\t'"$action")
  [[ "$status" == "broken" ]] && BROKEN=1
  [[ -n "$action" && "$status" != "ok" ]] && ACTIONS+=("$action")
  if [[ $JSON -eq 0 ]]; then
    local mark
    case "$status" in
      ok)     mark="${G}ok    ${Z}" ;;
      warn)   mark="${Y}warn  ${Z}" ;;
      *)      mark="${R}BROKEN${Z}" ;;
    esac
    printf '  %s %-22s %s\n' "$mark" "$name" "$detail"
    [[ -n "$action" && "$status" != "ok" ]] && printf '         %s→ %s%s\n' "$Y" "$action" "$Z"
  fi
  return 0
}

[[ $JSON -eq 0 ]] && printf '%s\n' "${B}omi doctor${Z} — $WORKSPACE"

# ── tools ───────────────────────────────────────────────────────────────────
for tool in node corepack bun git lsof xcrun; do
  if command -v "$tool" >/dev/null 2>&1; then
    check ok "tool:$tool" "$(command -v "$tool")"
  else
    check broken "tool:$tool" "not on PATH" "install it (node/pnpm: brew install node && npm i -g pnpm@10; bun: brew install oven-sh/bun/bun)"
  fi
done

# swiftc is only needed for the macOS shell; absence is a warning, not a break.
if command -v swiftc >/dev/null 2>&1; then check ok "tool:swiftc" "$(swiftc --version 2>/dev/null | head -1)"
else check warn "tool:swiftc" "absent — macOS shell cannot build" "xcode-select --install"; fi

# Flutter: the version matters and the failure it produces is misleading. The
# app declares sdk ^3.12.2; the PATH flutter is often older and fails version
# solving with "Failed to update packages", which reads like a network error.
newest_flutter="$(ls -d "$HOME/.local/share/mise/installs/flutter"/[0-9]*.[0-9]*.[0-9]* 2>/dev/null | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)"
if [[ -n "$newest_flutter" ]]; then
  check ok "tool:flutter" "$(basename "$newest_flutter") (mise; the launcher picks this, not PATH)"
elif command -v flutter >/dev/null 2>&1; then
  check warn "tool:flutter" "only PATH flutter ($(flutter --version 2>/dev/null | head -1 | cut -d' ' -f2))" \
    "iOS needs >= 3.44 (Dart ^3.12.2); an older one fails with a misleading 'Failed to update packages'. mise use flutter"
else
  check warn "tool:flutter" "absent — iOS lane unavailable" "mise use flutter@3.44.5"
fi

# ── repos and branches ──────────────────────────────────────────────────────
branch_of() { git -C "$1" rev-parse --abbrev-ref HEAD 2>/dev/null; }
cf_branch="$(branch_of "$CORE_REPO")"
if [[ -n "$cf_branch" ]]; then check ok "branch:core-foundation" "$cf_branch"
else check broken "branch:core-foundation" "not a git checkout" "use a core-foundation linked worktree"; fi

pf_branch="$(branch_of "$PLATFORM_REPO")"
if [[ "$pf_branch" == "codex/track3-backend-integration" ]]; then check ok "branch:platform" "$pf_branch"
else check broken "branch:platform" "on '$pf_branch', expected codex/track3-backend-integration" \
  "git -C $PLATFORM_REPO checkout codex/track3-backend-integration"; fi

if [[ -f "$PLATFORM_REPO/apps/service/bin/dev-server.ts" ]]; then check ok "backend:entrypoint" "apps/service/bin/dev-server.ts present"
else check broken "backend:entrypoint" "missing" "wrong branch in $PLATFORM_REPO — see above"; fi

# ── dependencies ────────────────────────────────────────────────────────────
# The install gotcha, made a probe instead of a folk memory.
# Probe a WORKSPACE MEMBER's .bin, not the workspace root's. pnpm links binaries
# into each package, and `core/node_modules` exists (holding .pnpm) even when the
# member install is the thing that silently did not happen — which is precisely
# the failure this probe is for. Checking the root was a false BROKEN on a
# perfectly healthy tree; a diagnostic that cries wolf gets ignored, and then it
# is worse than nothing.
if [[ -x "$CORE_REPO/core/packages/surfaces/node_modules/.bin/tsc" ]]; then
  check ok "deps:core" "workspace members installed (surfaces can resolve tsc)"
else
  check broken "deps:core" "core/node_modules is missing or incomplete — the build will die with 'tsc: command not found'" \
    "cd $CORE_REPO/core && corepack pnpm install --config.confirmModulesPurge=false"
fi
if [[ -d "$PLATFORM_REPO/node_modules" ]]; then check ok "deps:platform" "node_modules present"
else check broken "deps:platform" "missing" "cd $PLATFORM_REPO && bun install"; fi

# ── dist freshness — the stale-artifact check ───────────────────────────────
# This is the one that matters most. `integration/cross-side/wire-agreement.test.mjs`
# imports the BUILT adapters-platform dist; a stale dist means a green test about
# yesterday's client. Same for the surfaces dist the shells bundle.
stamp_report="$(node "$HERE/lib/provenance.mjs" >/dev/null 2>&1 && node -e '
  const {readStampFile, verifyArtifact} = await import("'"$HERE"'/lib/provenance.mjs");
  const p = "'"$SURFACES_DIST"'/omi-build-stamp.json";
  const v = verifyArtifact(readStampFile(p));
  console.log(JSON.stringify({agree: v.agree, reason: v.reason}));
' --input-type=module 2>/dev/null || echo '')"
if [[ -z "$stamp_report" ]]; then
  check warn "dist:surfaces" "could not evaluate the build stamp" "cd $CORE_REPO/core && corepack pnpm --filter @omi-core/surfaces build"
elif [[ "$stamp_report" == *'"agree":true'* ]]; then
  check ok "dist:surfaces" "built from the current working tree"
else
  reason="$(printf '%s' "$stamp_report" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).reason)}catch{console.log("unknown")}})')"
  check broken "dist:surfaces" "STALE — $reason" \
    "cd $CORE_REPO/core && corepack pnpm --filter @omi-core/surfaces build"
fi

if [[ -f "$CORE_REPO/core/packages/adapters-platform/dist/index.js" ]]; then
  src_newest="$(find "$CORE_REPO/core/packages/adapters-platform/src" -type f -newer "$CORE_REPO/core/packages/adapters-platform/dist/index.js" 2>/dev/null | head -1)"
  if [[ -n "$src_newest" ]]; then
    check broken "dist:adapters-platform" "source is newer than dist (e.g. ${src_newest#"$CORE_REPO/"})" \
      "cd $CORE_REPO/core && corepack pnpm -r build"
  else
    check ok "dist:adapters-platform" "newer than its sources"
  fi
else
  check broken "dist:adapters-platform" "not built" "cd $CORE_REPO/core && corepack pnpm -r build"
fi

# ── ports ───────────────────────────────────────────────────────────────────
for spec in "4851:single platform service" "5290:fixed macOS surface origin"; do
  port="${spec%%:*}"; label="${spec#*:}"
  holder="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1)"
  if [[ -z "$holder" ]]; then
    check ok "port:$port" "free ($label)"
  else
    cmd="$(ps -o comm= -p "$holder" 2>/dev/null | sed 's#.*/##')"
    detail="$(ps -o command= -p "$holder" 2>/dev/null || true)"
    check broken "port:$port" "occupied by pid $holder: ${detail:-$cmd} ($label)" "stop that exact listener; the harness never kills it or chooses another port"
  fi
done

# ── output ──────────────────────────────────────────────────────────────────
if [[ $JSON -eq 1 ]]; then
  printf '%s\n' "${ROWS[@]}" | ROWS_OK=$((1 - BROKEN)) node -e '
    let s=""; process.stdin.on("data",d=>s+=d).on("end",()=>{
      const checks = s.split("\n").filter(Boolean).map((l)=>{
        const [status,name,detail,action]=l.split("\t");
        return {status,name,detail,action:action||null};
      });
      const next = [...new Set(checks.filter(c=>c.status!=="ok"&&c.action).map(c=>c.action))];
      const broken = checks.filter(c=>c.status==="broken");
      const out = {schema:1, checkedAt:new Date().toISOString(), ok:broken.length===0, checks};
      // {error, next_actions[]} — the same machine-readable failure shape the
      // launcher emits, so one consumer can handle both.
      if (broken.length>0) { out.error = broken.map(c=>`${c.name}: ${c.detail}`).join("; "); }
      if (next.length>0) out.next_actions = next;
      process.stdout.write(JSON.stringify(out,null,2)+"\n");
    });'
else
  echo
  if [[ $BROKEN -eq 1 ]]; then
    printf '%s\n' "${R}${B}not ready.${Z} Do these, in order:"
    for i in "${!ACTIONS[@]}"; do printf '  %d. %s\n' "$((i+1))" "${ACTIONS[$i]}"; done
  else
    printf '%s\n' "${G}${B}ready.${Z} Nothing is broken."
    [[ ${#ACTIONS[@]} -gt 0 ]] && printf '  %s\n' "(warnings above are optional lanes, not blockers)"
  fi
  echo
fi
exit $BROKEN
