import { readdirSync, readFileSync, statSync } from "fs";
import { join, resolve } from "path";

import { describe, expect, it } from "vitest";

// #10190 regression guard: any admin code that sends a raw HogQL query directly
// (a `kind: "HogQLQuery"` body via its own fetch, bypassing lib/posthog's
// posthogFetch chokepoint) must apply the shared `withRowLimit` guard, or it
// re-introduces the silent default-100 truncation. Routes that go through
// posthogFetch/posthogResults/cachedPosthogFetch never contain the literal, so
// they are covered automatically and don't trip this check.

const ADMIN_ROOT = resolve(__dirname, "..", "..");
// lib/posthog.ts is the definition site — it holds both the literal and the
// guard, so it passes the rule below without being a special case.
const SCAN_DIRS = ["app", "lib"];

function tsFiles(dir: string): string[] {
  let out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "__tests__") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out = out.concat(tsFiles(full));
    else if (full.endsWith(".ts") || full.endsWith(".tsx")) out.push(full);
  }
  return out;
}

describe("HogQL row-limit guard has no bypass", () => {
  it("every file that sends a raw HogQLQuery also applies withRowLimit", () => {
    const offenders: string[] = [];
    for (const scanDir of SCAN_DIRS) {
      for (const file of tsFiles(join(ADMIN_ROOT, scanDir))) {
        const src = readFileSync(file, "utf8");
        if (!/HogQLQuery/.test(src)) continue;
        if (!/withRowLimit/.test(src)) {
          offenders.push(file.slice(ADMIN_ROOT.length + 1));
        }
      }
    }
    expect(
      offenders,
      `These files send a raw HogQLQuery without the withRowLimit guard (see #10190). ` +
        `Route the fetch through lib/posthog's posthogFetch/posthogResults, or wrap the query with withRowLimit:\n` +
        offenders.join("\n"),
    ).toEqual([]);
  });
});
