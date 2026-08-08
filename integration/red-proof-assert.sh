#!/bin/bash
# LIFECYCLE: permanent
# ============================================================================
# red-proof-assert — prove the assertion path can FAIL, by making it fail
# ============================================================================
#
# core/AGENTS.md rule 14: a test that guards an invariant carries a `// red-proof:`
# comment naming the mutation that makes it fail, and the reviewer applies that
# mutation before accepting the test. This script is that rule applied to the
# acceptance path itself.
#
# WHY IT EXISTS. Over one night, seven mechanisms reported success for things
# that had not happened — and the seventh was inside the acceptance path built to
# catch the other six. None was found by reading code or by a green suite. An
# assertion nobody has ever seen fail is indistinguishable from an assertion that
# cannot fail, and the difference only shows up on the day it matters.
#
# So: three real failures, applied to the real stack, each required to be caught
# by a named assertion. Not "the run failed" — the RIGHT assertion must go red,
# because a run that fails for the wrong reason is a passing test in disguise.
#
#   legacy-branch  -> no_generation_mismatch   (the actual historical defect)
#   stale-dist     -> stamps_agree
#   dead-backend   -> backend_reachable
#
# Each takes a full L3 cycle, so this is ~90s. It is NOT part of a lane: it is
# what you run when you change the assertions, and what a reviewer runs before
# believing them.
#
#   integration/red-proof-assert.sh            # all three
#   integration/red-proof-assert.sh stale-dist # just one
#
# Exit 0 only if EVERY red-proof went red for the right reason. The stack is
# stopped at the end — it has been deliberately broken and must not be left as
# though it were a healthy one.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_REPO="$(cd "$HERE/.." && pwd)"

if [[ -t 1 ]]; then R=$'\033[31m'; G=$'\033[32m'; B=$'\033[1m'; Y=$'\033[33m'; Z=$'\033[0m'
else R=""; G=""; B=""; Y=""; Z=""; fi

# proof name -> the assertion that MUST be the one reporting fail
declare -a PROOFS=(
  "legacy-branch:no_generation_mismatch"
  "stale-dist:stamps_agree"
  "dead-backend:backend_reachable"
)

WANT="${1:-}"
FAILURES=0
RESULTS=()

for row in "${PROOFS[@]}"; do
  proof="${row%%:*}"; expect="${row#*:}"
  [[ -n "$WANT" && "$WANT" != "$proof" ]] && continue

  printf '\n%s\n' "${B}── red-proof: $proof  (must turn $expect red) ──${Z}"
  "$HERE/dev-stack.sh" --stop >/dev/null 2>&1

  # `legacy-branch` is a SOURCE mutation, not a launcher flag, and finding that
  # out was the most useful thing this script has done so far.
  #
  # It was originally written the cheap way: drop `route=memories` and keep
  # `generation=platform`, which is EXACTLY the historical defect (generation
  # honored, route falls back to home, home takes the legacy branch). It came
  # back GREEN — because that bug is genuinely fixed. `resolveProductionRoute`
  # now takes `memoriesGeneration` into account, so a bare platform selection
  # lands on the memories route by itself. The defect cannot be reproduced
  # through configuration any more.
  #
  # A red-proof that no longer reproduces is not a passing red-proof; it is an
  # assertion with no evidence behind it. So this forces the legacy branch at
  # the only place it still exists — the source condition — and rebuilds. Slower,
  # honest, and it fails if someone deletes the guard.
  MUTATED=""
  restore_mutation() {
    [[ -n "$MUTATED" ]] && cp "$MUTATED" "$CORE_REPO/core/packages/surfaces/src/production/main.tsx" && rm -f "$MUTATED"
    MUTATED=""
  }
  trap restore_mutation EXIT INT TERM
  if [[ "$proof" == "legacy-branch" ]]; then
    main_tsx="$CORE_REPO/core/packages/surfaces/src/production/main.tsx"
    MUTATED="$(mktemp)"; cp "$main_tsx" "$MUTATED"
    perl -0pi -e 's/if \(route === "memories" && platform\.selection\.memories === "platform"\) \{/if (false) { \/\/ RED-PROOF MUTATION: force the legacy branch/' "$main_tsx"
    if ! grep -q "RED-PROOF MUTATION" "$main_tsx"; then
      printf '%s\n' "${R}✗ could not apply the source mutation — the condition it patches has moved.${Z}"
      printf '%s\n' "${Y}   Update the pattern in this script; a red-proof that cannot be applied is not a red-proof.${Z}"
      restore_mutation; FAILURES=$((FAILURES + 1)); RESULTS+=("FAIL $proof -> mutation could not be applied"); continue
    fi
    printf '  %s\n' "${Y}applied source mutation to main.tsx (rebuild follows; restored afterwards)${Z}"
  fi

  out="$("$HERE/dev-stack.sh" --no-ios --generation platform --red-proof "$proof" --assert --json 2>&1)"
  status=$?
  restore_mutation
  trap - EXIT INT TERM

  # Two independent conditions, and BOTH are required. A nonzero exit alone
  # would be satisfied by the launcher crashing for an unrelated reason — which
  # is how a broken harness passes its own red-proof.
  named_red="$(printf '%s' "$out" | node -e '
    let s=""; process.stdin.on("data",d=>s+=d).on("end",()=>{
      // The launcher prints progress first and the report last, and the
      // progress contains JSON of its own (qa/stats bodies). Anchor on the LAST
      // line that is exactly "{" — the start of the report object — instead of
      // the first brace anywhere, which found a counter payload and called the
      // whole proof UNPARSEABLE.
      // ...and the launcher keeps printing AFTER the report (shutdown lines),
      // so the slice must end at the closing brace too. Anchoring only the
      // start left trailing prose inside the parse and reported every proof as
      // UNPARSEABLE - a harness failing its own red-proof for a reason that had
      // nothing to do with the assertions. (No apostrophes in this block: it
      // sits inside a single-quoted bash string. Second time today.)
      const lines=s.split("\n");
      const at=(m)=>lines.map((l,i)=>[l,i]).filter(([l])=>l===m).map(([,i])=>i);
      const start=at("{").pop();
      const end=at("}").filter((i)=>i>start).pop();
      if(start===undefined||end===undefined){console.log("NO_JSON");return;}
      try{
        const r=JSON.parse(lines.slice(start,end+1).join("\n"));
        const a=(r.assertions||[]).find(x=>x.name===process.argv[1]);
        console.log(!a ? "NOT_EVALUATED" : a.result==="fail" ? "RED" : "GREEN");
      }catch(e){console.log("UNPARSEABLE")}
    });' "$expect")"

  if [[ $status -ne 0 && "$named_red" == "RED" ]]; then
    printf '%s\n' "${G}✓ went red for the right reason${Z} (exit $status, $expect=fail)"
    RESULTS+=("PASS $proof -> $expect red")
  else
    printf '%s\n' "${R}✗ DID NOT go red correctly${Z} (exit $status, $expect=$named_red)"
    printf '%s\n' "${Y}   An assertion that cannot fail is not evidence. Fix it before trusting --assert.${Z}"
    printf '%s\n' "$out" | tail -25
    RESULTS+=("FAIL $proof -> $expect $named_red (exit $status)")
    FAILURES=$((FAILURES + 1))
  fi
done

"$HERE/dev-stack.sh" --stop >/dev/null 2>&1

printf '\n%s\n' "${B}── red-proof summary ──${Z}"
for r in "${RESULTS[@]}"; do printf '  %s\n' "$r"; done
if [[ $FAILURES -eq 0 ]]; then
  printf '%s\n' "${G}${B}every assertion was seen red.${Z} The stack was left STOPPED — it was deliberately broken."
  printf '  %s\n' "bring a real one back up:  make l3"
else
  printf '%s\n' "${R}${B}$FAILURES red-proof(s) did not fire.${Z}"
fi
exit $FAILURES
