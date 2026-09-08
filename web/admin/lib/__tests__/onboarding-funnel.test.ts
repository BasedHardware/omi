import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  ALL_EVENT_NAMES,
  ENTRY_EVENT_NAME,
  ENTRY_PROPERTY_NAME,
  ENTRY_PROPERTY_VALUE,
  STEP_DEFINITIONS,
  computeFunnelSteps,
} from "../onboarding-funnel";

const SB_MODEL = path.resolve(
  __dirname,
  "../../../../desktop/macos/Desktop/Sources/Onboarding/SecondBrain/SBOnboardingModel.swift"
);

/** `SBOnboardingModel.Step` case names, in declaration order. */
function liveStepNames(): string[] {
  const source = readFileSync(SB_MODEL, "utf8");
  const block = source.match(/enum Step: Int, CaseIterable \{([^}]+)\}/);
  if (!block) return [];
  const names: string[] = [];
  const re = /case\s+([^\n]+)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(block[1])) !== null) {
    const cases = match[1].split(",");
    for (let i = 0; i < cases.length; i++) {
      const name = cases[i].trim();
      if (name) names.push(name);
    }
  }
  return names;
}

describe("STEP_DEFINITIONS vs SBOnboardingModel.swift", () => {
  it("covers exactly the live 19 steps, then completed", () => {
    const live = liveStepNames();
    expect(live).toEqual([
      "promise",
      "name",
      "howHeard",
      "language",
      "role",
      "mic",
      "systemAudio",
      "screen",
      "files",
      "accessibility",
      "automation",
      "notifications",
      "shortcutOpen",
      "shortcutTalk",
      "screenDemo",
      "agents",
      "context",
      "capture",
      "referral",
    ]);

    const flow = STEP_DEFINITIONS.filter((s) => s.key !== "completed");
    expect(flow.map((s) => s.key)).toEqual(live);
    expect(flow.every((s) => s.event === "Onboarding Step Completed")).toBe(
      true
    );
    expect(flow.every((s) => s.property === s.key)).toBe(true);
    expect(STEP_DEFINITIONS[STEP_DEFINITIONS.length - 1]).toMatchObject({
      key: "completed",
      event: "Onboarding Completed",
    });
  });

  it("enters the funnel on the promise step", () => {
    expect(ENTRY_EVENT_NAME).toBe("Onboarding Step Completed");
    expect(ENTRY_PROPERTY_NAME).toBe("step");
    expect(ENTRY_PROPERTY_VALUE).toBe("promise");
    expect(STEP_DEFINITIONS[0].key).toBe("promise");
  });

  it("queries only the live event names, never the dead wizard names", () => {
    expect(new Set(ALL_EVENT_NAMES)).toEqual(
      new Set(["Onboarding Step Completed", "Onboarding Completed"])
    );
    expect(ALL_EVENT_NAMES).not.toContain("Onboarding Step Name Completed");
    expect(ALL_EVENT_NAMES).not.toContain("Onboarding Beat Completed");
  });
});

describe("computeFunnelSteps", () => {
  const byKey = (steps: { key: string; users: number }[], key: string) =>
    steps.find((s) => s.key === key)!.users;

  it("counts a skipped step as having reached it", () => {
    const { totalUsers, steps } = computeFunnelSteps([
      ["a", "Onboarding Step Completed", "promise"],
      ["a", "Onboarding Step Completed", "name"],
      ["a", "Onboarding Step Completed", "howHeard"],
      ["a", "Onboarding Step Completed", "language"],
      ["a", "Onboarding Step Completed", "role"],
      ["a", "Onboarding Step Completed", "mic"],
    ]);
    expect(totalUsers).toBe(1);
    expect(byKey(steps, "mic")).toBe(1);
    expect(byKey(steps, "systemAudio")).toBe(0);
  });

  it("counts the three-doors screenDemo step as a funnel row", () => {
    const prefix = [
      "promise",
      "name",
      "howHeard",
      "language",
      "role",
      "mic",
      "systemAudio",
      "screen",
      "files",
      "accessibility",
      "automation",
      "notifications",
      "shortcutOpen",
      "shortcutTalk",
      "screenDemo",
    ];
    const { steps } = computeFunnelSteps(
      prefix.map((step) => ["a", "Onboarding Step Completed", step])
    );
    expect(byKey(steps, "screenDemo")).toBe(1);
    expect(byKey(steps, "agents")).toBe(0);
  });

  it("stops a user at the first gap in the ordered funnel", () => {
    const { steps } = computeFunnelSteps([
      ["a", "Onboarding Step Completed", "promise"],
      // name missing.
      ["a", "Onboarding Step Completed", "howHeard"],
    ]);
    expect(byKey(steps, "promise")).toBe(1);
    expect(byKey(steps, "name")).toBe(0);
    expect(byKey(steps, "howHeard")).toBe(0);
  });

  it("reports completion rates against the entrant count", () => {
    const { totalUsers, steps } = computeFunnelSteps([
      ["a", "Onboarding Step Completed", "promise"],
      ["a", "Onboarding Step Completed", "name"],
      ["b", "Onboarding Step Completed", "promise"],
    ]);
    expect(totalUsers).toBe(2);
    expect(steps.find((s) => s.key === "name")!.completionRate).toBe(50);
  });

  it("ignores unknown events, unknown properties, and malformed rows", () => {
    const { totalUsers } = computeFunnelSteps([
      ["a", "Onboarding Step Completed", "promise"],
      ["a", "Onboarding Step Name Completed", "Name"],
      ["a", "Onboarding Beat Completed", "hello"],
      ["a", "Some Other Event"],
      [null as unknown as string, "Onboarding Step Completed", "promise"],
      [] as unknown[],
    ]);
    expect(totalUsers).toBe(1);
  });

  it("matches the terminal completed event by name alone", () => {
    const prefix = STEP_DEFINITIONS.filter((s) => s.key !== "completed").map(
      (s) => ["a", "Onboarding Step Completed", s.key]
    );
    const { steps } = computeFunnelSteps([
      ...prefix,
      ["a", "Onboarding Completed"],
    ]);
    expect(byKey(steps, "referral")).toBe(1);
    expect(byKey(steps, "completed")).toBe(1);
  });
});
