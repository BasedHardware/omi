import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("macOS release CI", () => {
  it("installs pi-mono-extension dependencies before running extension tests", () => {
    const codemagic = readFileSync(new URL("../../../../codemagic.yaml", import.meta.url), "utf8");
    const stepStart = codemagic.indexOf("name: Test pi-mono-extension denylist classifier");
    expect(stepStart).toBeGreaterThanOrEqual(0);

    const step = codemagic.slice(stepStart, codemagic.indexOf("- name:", stepStart + 1));
    expect(step).toContain("cd pi-mono-extension");
    expect(step).toContain("npm ci --no-fund --no-audit");
    expect(step.indexOf("npm ci --no-fund --no-audit")).toBeLessThan(
      step.indexOf("node --experimental-strip-types --test index.test.ts")
    );
  });
});
