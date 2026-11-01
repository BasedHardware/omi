// macOS conformance suite for contracts/parity/agent_routing.json.
//
// The same vectors run through the Windows port in
// `desktop/windows/src/main/codingAgent/parityAgentRouting.test.ts`. Two copies
// of one string-matching rule is the divergence class contracts/parity exists to
// catch: a negator-scoping fix or a new alias applied here and not there
// silently changes which agent a user's spoken task runs on.
//
// Changing behaviour means editing the fixture, which shows up in review as a
// cross-platform decision rather than a single-platform drive-by.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  explicitProviderFrom,
  negatedAgentsFrom,
} from "../src/runtime/agent-mention.js";

interface ParityCase {
  name: string;
  utterance: string;
  expected_agent: string | null;
  expected_ruled_out: string[];
}

const FIXTURE_PATH = fileURLToPath(
  new URL("../../../../contracts/parity/agent_routing.json", import.meta.url),
);

const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as {
  $comment: string;
  cases: ParityCase[];
};

describe("parity: agent_routing.json", () => {
  it("has a non-empty, uniquely named case set", () => {
    expect(fixture.cases.length).toBeGreaterThan(0);
    const names = fixture.cases.map((testCase) => testCase.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it.each(fixture.cases.map((testCase) => [testCase.name, testCase] as const))(
    "%s",
    (_name, testCase) => {
      expect(explicitProviderFrom(testCase.utterance)).toBe(testCase.expected_agent);
      // Order is not part of the contract; the set of excluded agents is.
      expect([...negatedAgentsFrom(testCase.utterance)].sort()).toEqual(
        [...testCase.expected_ruled_out].sort(),
      );
    },
  );
});
