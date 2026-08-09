#!/bin/bash
# LIFECYCLE: permanent
# ============================================================================
# red-proof-write-journey — make the L3 write journey fail, on purpose, live
# ============================================================================
#
# `integration/lib/write-journey.test.mjs` is the CHEAP half of the red-proof:
# it hands the verdict function doctored facts and requires each assertion to go
# red. That proves the evaluator CAN fail. It says nothing about whether the
# DRIVER feeds it honest facts — and "the evaluator is fine, the driver was
# lying to it" is precisely the shape that made `servedCount=4 status=PASS`
# possible while the backend served zero.
#
# So this is the expensive half: four real mutations, applied to a real door
# over real HTTP, each required to turn a NAMED assertion red. Not "the journey
# failed" — a journey that fails for the wrong reason is a passing test in
# disguise.
#
#   skip-seed             -> control_seeded          (R3's seeding is load-bearing:
#                                                     with no control state the fence
#                                                     denies, so the 202 above is not
#                                                     a constant)
#   unstale-epoch         -> stale_epoch_refused     (the 409 is caused by the EPOCH,
#                                                     not by the route)
#   wrong-door            -> create_admitted         ("not 2xx" absence, and a fence
#                                                     counter that stays empty)
#   registered-mismatch   -> door_agreement          (the tree says the real route
#                                                     exists while the journey drives
#                                                     the harness — the failure that
#                                                     would otherwise leave two steps
#                                                     PENDING forever, green)
#
# The last one is the one that matters most. Everything else here guards a step;
# that one guards the STAGING, which is the only reason any step is allowed to
# report `pending` at all.
#
#   integration/red-proof-write-journey.sh                     # all four
#   integration/red-proof-write-journey.sh registered-mismatch # just one
#
# Exit 0 only if every mutation went red for the right reason.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_PATHS_JSON="$(node "$HERE/lib/provenance.mjs" --paths 2>/dev/null || true)"
read -r CORE_REPO PLATFORM_REPO <<<"$(printf '%s' "$REPO_PATHS_JSON" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
    try{const j=JSON.parse(s);console.log(`${j["core-foundation"]} ${j.platform}`)}catch{console.log("")}})')"
[[ -n "${PLATFORM_REPO:-}" ]] || { echo "could not resolve repo paths — run: node $HERE/lib/provenance.mjs --paths" >&2; exit 2; }

if [[ -t 1 ]]; then R=$'\033[31m'; G=$'\033[32m'; B=$'\033[1m'; Y=$'\033[33m'; Z=$'\033[0m'
else R=""; G=""; B=""; Y=""; Z=""; fi

# Its own ports, deliberately not the dev-stack's: this script must be safe to
# run beside a live stack, and it is about to break the thing it boots.
DOOR_PORT="${OMI_RED_PROOF_DOOR_PORT:-4863}"
DEAD_PORT="${OMI_RED_PROOF_DEAD_PORT:-4864}"
TOKEN="omi-fence-integration-qa-token-v1"
ACCOUNT="acct-fence-integration-fixture"
TMP="$(mktemp -d)"
DOOR_PID=""; DEAD_PID=""

# Kill the LISTENER, not only the subshell. `( cd … && bun run … ) &` records
# the subshell's pid in `$!`; killing that leaves `bun` holding the port, and
# the leak is invisible until the next run of a DIFFERENT harness fails to bind
# and reads someone else's 404 as its own server's answer. That happened here
# once already: an orphaned fence server on 4853 made the cross-side wire test
# report the memories route as a 404.
cleanup() {
  for pid in "$DOOR_PID" "$DEAD_PID"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
  done
  for port in "$DOOR_PORT" "$DEAD_PORT"; do
    holder="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    for pid in $holder; do kill "$pid" 2>/dev/null; done
  done
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

# ── the real fence door ─────────────────────────────────────────────────────
( cd "$PLATFORM_REPO" && TZ=UTC OMI_FENCE_INTEGRATION_PORT="$DOOR_PORT" \
    bun run integration/control/fence-server.ts ) > "$TMP/door.log" 2>&1 &
DOOR_PID=$!
for _ in $(seq 1 40); do
  curl -fsS --max-time 1 "http://127.0.0.1:$DOOR_PORT/health" >/dev/null 2>&1 && break
  sleep 0.25
done
curl -fsS --max-time 1 "http://127.0.0.1:$DOOR_PORT/health" >/dev/null 2>&1 \
  || { echo "${R}the fence door never came up on $DOOR_PORT${Z}"; cat "$TMP/door.log"; exit 2; }

# ── a door that is UP and serves nothing: absence wearing a refusal's clothes ─
node -e '
  require("http").createServer((_,res)=>{res.writeHead(404,{"content-type":"application/json"});res.end("{\"error\":\"not_found\"}")})
    .listen(Number(process.argv[1]),"127.0.0.1");' "$DEAD_PORT" > "$TMP/dead.log" 2>&1 &
DEAD_PID=$!
sleep 0.5

# ── a platform tree that CLAIMS the route is registered ─────────────────────
# Not an edit to the real platform checkout: swarm-protocol §3a forbids that,
# and a red-proof that dirties a shared tree blocks every other lane's L2.
FAKE_PLATFORM="$TMP/platform-claiming-registered"
mkdir -p "$FAKE_PLATFORM/scripts"
cat > "$FAKE_PLATFORM/scripts/lint-import-graph.ts" <<'REGISTRY'
const WIRE_PATH_REGISTRY: readonly WirePathRegistryRow[] = [
  {
    wirePath: "/v1/tasks/ops",
    servedBy: "apps/service/routes/tasks-ops.ts",
    boundVia: ["routes/tasks-ops", "app-facing"],
    reason: "RED-PROOF FIXTURE — a tree that claims the write route is registered.",
  },
];
REGISTRY
ln -s "$PLATFORM_REPO/node_modules" "$FAKE_PLATFORM/node_modules"

# proof : expected-red-assertion : extra args
declare -a PROOFS=(
  "skip-seed:control_seeded:--red-proof-skip-seed"
  "unstale-epoch:stale_epoch_refused:--stale-epoch 7"
  "wrong-door:create_admitted:--door-override http://127.0.0.1:$DEAD_PORT"
  "registered-mismatch:door_agreement:--platform-repo-override $FAKE_PLATFORM"
)

WANT="${1:-}"
FAILURES=0
RESULTS=()

for row in "${PROOFS[@]}"; do
  proof="${row%%:*}"; rest="${row#*:}"; expect="${rest%%:*}"; extra="${rest#*:}"
  [[ -n "$WANT" && "$WANT" != "$proof" ]] && continue
  printf '\n%s\n' "${B}── red-proof: $proof  (must turn $expect red) ──${Z}"

  door="http://127.0.0.1:$DOOR_PORT"
  platform_repo="$PLATFORM_REPO"
  args=()
  case "$extra" in
    "--door-override "*)          door="${extra#--door-override }" ;;
    "--platform-repo-override "*) platform_repo="${extra#--platform-repo-override }" ;;
    *)                            read -r -a args <<<"$extra" ;;
  esac

  # The control plane stays the REAL fence server even when the door is the dead
  # one: that is the point of measuring them separately. A journey whose door
  # went missing must be caught by the producer-side counter reporting nothing
  # for the run, not by the driver noticing its own request failed.
  out="$TMP/$proof.json"
  node "$HERE/lib/write-journey.mjs" \
    --door "$door" --control "http://127.0.0.1:$DOOR_PORT" \
    --token "$TOKEN" --account "$ACCOUNT" \
    --run "redproof-$proof-$$" --epoch 7 \
    --platform-repo "$platform_repo" \
    "${args[@]+"${args[@]}"}" \
    --out "$out" --json > "$TMP/$proof.log" 2>&1
  status=$?

  named_red="$(node -e '
    const fs=require("fs");
    let v=null; try{ v=JSON.parse(fs.readFileSync(process.argv[1],"utf8")) }catch{ console.log("NO_VERDICT"); process.exit(0) }
    const a=(v.assertions||[]).find(x=>x.name===process.argv[2]);
    console.log(!a ? "NOT_EVALUATED" : a.result==="fail" ? "RED" : a.result.toUpperCase());
  ' "$out" "$expect" 2>/dev/null || echo NO_VERDICT)"

  # BOTH conditions. A nonzero exit alone is satisfied by the driver crashing
  # for an unrelated reason, which is how a broken harness passes its own
  # red-proof.
  if [[ $status -ne 0 && "$named_red" == "RED" ]]; then
    printf '%s\n' "${G}✓ went red for the right reason${Z} (exit $status, $expect=fail)"
    RESULTS+=("PASS $proof -> $expect red")
  else
    printf '%s\n' "${R}✗ DID NOT go red correctly${Z} (exit $status, $expect=$named_red)"
    printf '%s\n' "${Y}   An assertion that cannot fail is not evidence.${Z}"
    tail -20 "$TMP/$proof.log"
    RESULTS+=("FAIL $proof -> $expect $named_red (exit $status)")
    FAILURES=$((FAILURES + 1))
  fi
done

# ── the control: the SAME driver, unmutated, must still be green ────────────
# Without this the whole script is satisfied by a journey that fails at
# everything. Four reds prove the assertions can fire; this proves they are not
# simply stuck on.
printf '\n%s\n' "${B}── control: the unmutated journey (must NOT fail) ──${Z}"
node "$HERE/lib/write-journey.mjs" \
  --door "http://127.0.0.1:$DOOR_PORT" --control "http://127.0.0.1:$DOOR_PORT" \
  --token "$TOKEN" --account "$ACCOUNT" --run "redproof-control-$$" --epoch 7 \
  --platform-repo "$PLATFORM_REPO" --out "$TMP/control.json" --json > "$TMP/control.log" 2>&1
control_status=$?
if [[ $control_status -eq 0 ]]; then
  printf '%s\n' "${G}✓ the unmutated journey is green${Z}"
  RESULTS+=("PASS control -> unmutated journey not failing")
else
  printf '%s\n' "${R}✗ the unmutated journey FAILED — every red above is uninterpretable${Z}"
  tail -25 "$TMP/control.log"
  RESULTS+=("FAIL control -> unmutated journey failed (exit $control_status)")
  FAILURES=$((FAILURES + 1))
fi

printf '\n%s\n' "${B}── red-proof summary ──${Z}"
for r in "${RESULTS[@]}"; do printf '  %s\n' "$r"; done
if [[ $FAILURES -eq 0 ]]; then
  printf '%s\n' "${G}${B}every write-journey assertion under test was seen red, and the control stayed green.${Z}"
else
  printf '%s\n' "${R}${B}$FAILURES red-proof(s) did not fire.${Z}"
fi
exit $FAILURES
