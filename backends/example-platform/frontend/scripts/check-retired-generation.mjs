#!/usr/bin/env node
/**
 * Standing check that the retired backend generation stays retired.
 *
 * `legacy` remains a recognized name so a host request can be refused by
 * name (`generation-unavailable`). What this fence forbids is advertising
 * it as something a domain can still serve, or putting it back on a
 * launcher as a successful `--generation` arm.
 *
 * Narrow on purpose. It does not scan account-lifecycle `account_generation`,
 * Listen entitlement frames, QA fixtures, or tests that pass `--generation
 * legacy` to prove the refusal. Those are live. A tree-wide "no string
 * legacy" grep would fire on them and get muted.
 *
 * WHAT IT CATCHES:
 *   1. `"legacy"` appearing in `PRODUCTION_GENERATION_AVAILABILITY`.
 *   2. A launcher `case "$generation"` serving arm named `legacy`
 *      (the `*)` refusal arm may mention it).
 *
 * Positive control: every production domain must list `platform`. A
 * parser that matched nothing would otherwise go green.
 *
 * Self-test fixtures run on every invocation. A rename that defangs the
 * table or the case-arm match fails the self-test rather than silently
 * passing.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SELECTION = "packages/domain/src/generation-selection.ts";
const LAUNCHERS = [
  "shells/macos/scripts/dev-run-macos.sh",
  "shells/ios/scripts/dev-run-ios.sh",
];

const availabilityTable = (source) => {
  const match = source.match(
    /export const PRODUCTION_GENERATION_AVAILABILITY[\s\S]*?=\s*\{([\s\S]*?)\n\};/,
  );
  if (match === null) return null;
  const rows = [];
  for (const row of match[1].matchAll(/(\w+)\s*:\s*\[([^\]]*)\]/g)) {
    const generations = [...row[2].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    rows.push({ domain: row[1], generations });
  }
  return rows;
};

const generationServingArms = (source) => {
  const match = source.match(/case "\$generation" in\s*([\s\S]*?)esac/);
  if (match === null) return null;
  const beforeDefault = match[1].split(/\*\)/)[0] ?? "";
  const arms = [];
  for (const row of beforeDefault.matchAll(/([A-Za-z0-9_|]+)\s*\)/g)) {
    arms.push(...row[1].split("|"));
  }
  return arms;
};

const analyzeAvailability = (source) => {
  const failures = [];
  const rows = availabilityTable(source);
  if (rows === null || rows.length === 0) {
    return ["PRODUCTION_GENERATION_AVAILABILITY table was not found"];
  }
  for (const row of rows) {
    if (row.generations.includes("legacy")) {
      failures.push(
        `${row.domain} advertises retired generation "legacy"; available must stay platform-only`,
      );
    }
    if (!row.generations.includes("platform")) {
      failures.push(
        `${row.domain} does not list "platform" — the parser matched nothing useful`,
      );
    }
  }
  return failures;
};

const analyzeLauncher = (shown, source) => {
  const failures = [];
  const arms = generationServingArms(source);
  if (arms === null) {
    return [`${shown}: case "$generation" was not found`];
  }
  if (!arms.includes("platform")) {
    failures.push(
      `${shown}: generation case has no platform serving arm — the parser matched nothing useful`,
    );
  }
  if (arms.includes("legacy")) {
    failures.push(
      `${shown}: generation case serves "legacy"; the retired generation must stay a *) refusal`,
    );
  }
  return failures;
};

const FIXTURE_AVAILABILITY_PLATFORM_ONLY = `
export const PRODUCTION_GENERATION_AVAILABILITY: Readonly<
  Record<ProductionDomain, readonly BackendGeneration[]>
> = {
  memories: ["platform"],
  conversations: ["platform"],
  folders: ["platform"],
  tasks: ["platform"],
};
`;

const FIXTURE_AVAILABILITY_LISTS_LEGACY = FIXTURE_AVAILABILITY_PLATFORM_ONLY.replace(
  'memories: ["platform"]',
  'memories: ["legacy", "platform"]',
);

const FIXTURE_LAUNCHER_PLATFORM_ONLY = `
case "$generation" in
  platform) ;;
  *) echo "ERROR: --generation \${generation} cannot be served (legacy generation is retired); available: platform" >&2; exit 2 ;;
esac
`;

const FIXTURE_LAUNCHER_SERVES_LEGACY = `
case "$generation" in
  platform|legacy) ;;
  *) echo "ERROR: --generation \${generation} cannot be served" >&2; exit 2 ;;
esac
`;

const SELF_TEST_FIXTURES = [
  {
    name: "availability lists legacy",
    run: () => analyzeAvailability(FIXTURE_AVAILABILITY_LISTS_LEGACY),
    mustPass: false,
  },
  {
    name: "availability is platform-only",
    run: () => analyzeAvailability(FIXTURE_AVAILABILITY_PLATFORM_ONLY),
    mustPass: true,
  },
  {
    name: "launcher serves legacy",
    run: () => analyzeLauncher("fixture.sh", FIXTURE_LAUNCHER_SERVES_LEGACY),
    mustPass: false,
  },
  {
    name: "launcher refuses legacy",
    run: () => analyzeLauncher("fixture.sh", FIXTURE_LAUNCHER_PLATFORM_ONLY),
    mustPass: true,
  },
];

const selfTestFailures = [];
for (const fixture of SELF_TEST_FIXTURES) {
  const failures = fixture.run();
  const passed = failures.length === 0;
  if (passed !== fixture.mustPass) {
    selfTestFailures.push(
      `self-test "${fixture.name}": expected ${fixture.mustPass ? "PASS" : "FAIL"}, `
      + `it ${passed ? "passed" : "failed"}`
      + (failures.length ? ` (${failures.join("; ")})` : ""),
    );
  }
}
if (selfTestFailures.length) {
  console.error(`frontend retired-generation fence IS ITSELF BROKEN (${selfTestFailures.length}):`);
  for (const failure of selfTestFailures) console.error("  " + failure);
  process.exit(1);
}

const failures = [
  ...analyzeAvailability(readFileSync(join(ROOT, SELECTION), "utf8")).map(
    (failure) => `${SELECTION}: ${failure}`,
  ),
  ...LAUNCHERS.flatMap((shown) => analyzeLauncher(shown, readFileSync(join(ROOT, shown), "utf8"))),
];
if (failures.length) {
  console.error(`frontend retired-generation fence FAILED (${failures.length}):`);
  for (const failure of failures) console.error("  " + failure);
  process.exit(1);
}
console.log(
  "frontend retired-generation fence passed "
  + `(availability from ${SELECTION}; ${LAUNCHERS.length} launchers; `
  + `${SELF_TEST_FIXTURES.length} self-test fixtures green).`,
);
