#!/bin/bash
# Applied red-proofs for the real launcher/report path. Each mutation must make
# the full command and its named assertion fail. No fixture or alternate service
# is allowed to satisfy the negative control.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

run_proof() {
  local proof="$1" assertion="$2"
  local scratch log report rc
  scratch="$(mktemp -d /tmp/omi-red-proof.XXXXXX)"
  log="$scratch/output.log"
  report="$scratch/last-run.json"
  set +e
  ( cd "$ROOT" && OMI_DEV_STACK_RUNDIR="$scratch" integration/dev-stack.sh \
      --red-proof "$proof" --assert --json ) > "$log" 2>&1
  rc=$?
  set -e
  if (( rc == 0 )); then
    echo "FAIL: $proof returned zero; a red-proof that stays green is not evidence." >&2
    cat "$log" >&2
    rm -rf "$scratch"
    return 1
  fi
  if [[ ! -s "$report" ]]; then
    echo "FAIL: $proof produced no structured report." >&2
    cat "$log" >&2
    rm -rf "$scratch"
    return 1
  fi
  ASSERTION="$assertion" node -e '
    const fs=require("fs"),r=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
    const a=r.assertions.find((x)=>x.name===process.env.ASSERTION);
    if(!a||a.result!=="fail") process.exit(1);
    process.stdout.write(`RED ${process.env.ASSERTION}: ${a.detail}\n`);
  ' "$report" || {
    echo "FAIL: $proof did not redden $assertion." >&2
    cat "$log" >&2
    rm -rf "$scratch"
    return 1
  }
  rm -rf "$scratch"
}

run_proof stale-dist exact_evidence_matrix
run_proof dead-backend direct_service_readiness
run_proof generation-mismatch no_generation_mismatch
