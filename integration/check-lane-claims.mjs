#!/usr/bin/env node
// LIFECYCLE: permanent
//
// Rejects a commit message that claims a verification lane with no receipt
// matching the CURRENT tree. See integration/lib/receipts.mjs for the
// receipt system and integration/lib/provenance.mjs for the tree-hash
// mechanism this rests on.
//
// SCOPE. This script is invoked BY HAND or by the lane runner. It does NOT
// install a git hook — that is explicitly out of scope. A hook is a decision
// about every contributor's local workflow (bypassable with --no-verify,
// invisible until it fires, one more thing `make setup` has to keep in sync);
// wiring one in is a separate, deliberate change, not a side effect of
// building the checker. Run it yourself:
//
//   node integration/check-lane-claims.mjs [--repo core-foundation|platform]
//                                          [--rev <git-rev>] [--message-file <path>]
//                                          [--json]
//
// CLAIMS ARE STRUCTURED, NEVER PROSE. See integration/lib/receipts.mjs's
// parseLaneClaims() for the full reasoning (the import-fence incident in
// platform/scripts/lint-import-graph.ts): a checker that fires on honest
// prose gets routed around, and once routed around it protects nothing. Only
// an exact `Lanes: L0,L1,L2` trailer line is ever inspected.
//
// THE OVERRIDE HATCH. AGENTS.md: "A broken gate is never a reason to be
// stuck." A `Lane-Claim-Override: <reason>` trailer bypasses a failing check
// — but is REPORTED loudly (never silently accepted) and requires a
// non-empty reason, mirroring the fence's `// storage-provenance-ok(<reason>)`
// idiom in lint-import-graph.ts. A gate with no hatch trains people to bypass
// the whole system instead of just the one broken check.

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  LANE_REGISTRY,
  LANE_IDS,
  verifyReceipt,
  parseLaneClaims,
  parseLaneClaimOverride,
} from "./lib/receipts.mjs";
import { REPO_PATHS } from "./lib/provenance.mjs";

function printHelp() {
  process.stdout.write(
    [
      "node integration/check-lane-claims.mjs [flags]",
      "",
      "Validates that every lane a commit message claims (via a `Lanes: L0,L1,L2`",
      "trailer) has a receipt that matches the current working tree.",
      "",
      "Flags:",
      "  --repo <name>          which repo's commit message to read (default: core-foundation)",
      "  --rev <git-rev>        commit to read the message of (default: HEAD)",
      "  --message-file <path>  read the message from a file instead of git log",
      "  --json                 emit machine-readable {error, next_actions} on failure",
      "  --help",
      "",
      "Does NOT install a git hook. Invoke by hand or from the lane runner.",
    ].join("\n") + "\n",
  );
}

function readMessage({ repo, rev, messageFile }) {
  if (messageFile) {
    return readFileSync(messageFile, "utf8");
  }
  const repoRoot = REPO_PATHS[repo];
  if (!repoRoot) {
    throw new Error(`unknown --repo "${repo}". Known: ${Object.keys(REPO_PATHS).join(", ")}.`);
  }
  return execFileSync("git", ["log", "-1", "--format=%B", rev], {
    cwd: repoRoot,
    encoding: "utf8",
  });
}

/** Next action per verifyReceipt() `kind` — structured, not prose-parsed. */
const NEXT_ACTION = {
  "unknown-lane": (lane) =>
    `"${lane}" is not a known lane. Known lanes: ${LANE_IDS.join(", ")}. Fix the Lanes: trailer.`,
  absent: (lane) =>
    `Run ${lane} (${LANE_REGISTRY[lane]?.description ?? "see LANE_REGISTRY"}) so it writes a receipt, then retry.`,
  stale: (lane) =>
    `Rerun ${lane} against the current tree — its receipt was written before this edit.`,
  failed: (lane) => `${lane}'s last run failed. Fix it and rerun until it passes, then retry.`,
};

export function checkLaneClaims(message, { workspaceRoot } = {}) {
  const claims = parseLaneClaims(message);
  const override = parseLaneClaimOverride(message);

  if (claims.length === 0) {
    return { ok: true, claims: [], failures: [], override: override.present ? override : null };
  }

  const failures = [];
  for (const lane of claims) {
    const outcome = verifyReceipt(lane, { workspaceRoot });
    if (!outcome.ok) {
      failures.push({
        lane,
        kind: outcome.kind,
        reason: outcome.reason,
        nextAction: (NEXT_ACTION[outcome.kind] ?? (() => `Investigate and rerun ${lane}.`))(lane),
      });
    }
  }

  if (failures.length === 0) {
    return { ok: true, claims, failures: [], override: override.present ? override : null };
  }

  // Override present but malformed (no reason) is NOT a pass-through — an
  // override that silently ignores its own missing reason is not "reported
  // loudly", it's just a hole.
  if (override.present && !override.valid) {
    return {
      ok: false,
      claims,
      failures,
      override,
      overrideError: 'Lane-Claim-Override trailer present but empty — it requires a non-empty reason.',
    };
  }

  if (override.present && override.valid) {
    return { ok: true, claims, failures, override, overridden: true };
  }

  return { ok: false, claims, failures, override: null };
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.includes("--help") || argv.includes("-h")) {
    printHelp();
    process.exit(0);
  }
  const flag = (name) => {
    const i = argv.indexOf(name);
    return i === -1 ? undefined : argv[i + 1];
  };
  const repo = flag("--repo") ?? "core-foundation";
  const rev = flag("--rev") ?? "HEAD";
  const messageFile = flag("--message-file");
  const json = argv.includes("--json");

  let message;
  try {
    message = readMessage({ repo, rev, messageFile });
  } catch (err) {
    const error = `could not read commit message: ${err.message}`;
    if (json) {
      console.log(JSON.stringify({ error, next_actions: ["Check --repo/--rev/--message-file."] }, null, 2));
    } else {
      console.error(`✗ ${error}`);
    }
    process.exit(2);
  }

  const result = checkLaneClaims(message);

  if (result.overrideError) {
    const error = result.overrideError;
    if (json) {
      console.log(
        JSON.stringify(
          { error, next_actions: ["Add a reason: `Lane-Claim-Override: <why>`."] },
          null,
          2,
        ),
      );
    } else {
      console.error(`✗ ${error}`);
    }
    process.exit(1);
  }

  if (result.claims.length === 0) {
    if (json) {
      console.log(JSON.stringify({ ok: true, claims: [] }, null, 2));
    } else {
      console.log("no `Lanes:` trailer — no lane claims to verify.");
    }
    process.exit(0);
  }

  if (result.overridden) {
    // REPORTED LOUDLY: this is the one output that must never be quiet, in
    // either mode, because it is the record of a gate being bypassed.
    const banner =
      `OVERRIDE — Lane-Claim-Override: ${result.override.reason}\n` +
      `The following claimed lane(s) failed verification and were bypassed:\n` +
      result.failures.map((f) => `  - ${f.lane}: ${f.reason}`).join("\n");
    if (json) {
      console.log(
        JSON.stringify(
          {
            ok: true,
            claims: result.claims,
            overridden: true,
            override_reason: result.override.reason,
            bypassed_failures: result.failures,
          },
          null,
          2,
        ),
      );
      console.error(banner);
    } else {
      console.error(`⚠ ${banner}`);
      console.log(`lane claims [${result.claims.join(", ")}] accepted via override.`);
    }
    process.exit(0);
  }

  if (!result.ok) {
    const error = `${result.failures.length} claimed lane(s) failed verification: ${result.failures
      .map((f) => f.lane)
      .join(", ")}`;
    if (json) {
      console.log(
        JSON.stringify(
          {
            error,
            claims: result.claims,
            failures: result.failures,
            next_actions: result.failures.map((f) => f.nextAction),
          },
          null,
          2,
        ),
      );
    } else {
      console.error(`✗ ${error}`);
      for (const f of result.failures) {
        console.error(`    ${f.lane}: ${f.reason}`);
        console.error(`      -> ${f.nextAction}`);
      }
      console.error(
        "    (Escape hatch: add a `Lane-Claim-Override: <reason>` trailer if this gate itself is broken.)",
      );
    }
    process.exit(1);
  }

  if (json) {
    console.log(JSON.stringify({ ok: true, claims: result.claims }, null, 2));
  } else {
    console.log(`lane claims [${result.claims.join(", ")}] all verified against the current tree.`);
  }
  process.exit(0);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main();
}
