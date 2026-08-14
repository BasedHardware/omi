import { describe, expect, test } from "bun:test";

import { parseAgentRunEvent } from "./agent-run-events";
import {
  goldenAgentRunEventV0,
  goldenAgentToolDefinitionV0,
  parseAgentToolDefinition,
} from "./agent-tool-compat";
import { normalizeChatGenerationContext } from "./generation-context";

describe("agent tool and run-event compatibility window", () => {
  test("golden v0 tool and event fixtures replay through current-minus-one parsers", () => {
    const tool = parseAgentToolDefinition(goldenAgentToolDefinitionV0);
    expect(tool.ok).toBe(true);
    if (tool.ok) {
      expect(tool.definition.schemaVersion).toBe(1);
      expect(tool.definition.name).toBe("safe.lookup");
    }
    const event = parseAgentRunEvent(goldenAgentRunEventV0);
    expect(event.ok).toBe(true);
    if (event.ok) expect(event.event.schemaVersion).toBe(1);
    expect(parseAgentToolDefinition({ ...goldenAgentToolDefinitionV0, schemaVersion: 99 }).ok).toBe(false);
    expect(parseAgentRunEvent({ ...goldenAgentRunEventV0, schemaVersion: 99 }).ok).toBe(false);
  });

  test("bare context strings are not historical packets and context stays v1-only", () => {
    expect(() => normalizeChatGenerationContext(["legacy note"], {
      accountId: "owner",
      generationId: "generation-1",
      nowEpochMilliseconds: 1,
    })).not.toThrow();
    const packet = normalizeChatGenerationContext(["legacy note"], {
      accountId: "owner",
      generationId: "generation-1",
      nowEpochMilliseconds: 1,
    });
    expect(packet.schemaVersion).toBe("v1");
    expect(() => normalizeChatGenerationContext({
      schemaVersion: "v2",
      ownerAccountId: "owner",
      generationId: "generation-1",
    } as unknown as string[], {
      accountId: "owner",
      generationId: "generation-1",
      nowEpochMilliseconds: 1,
    })).toThrow();
  });
});
