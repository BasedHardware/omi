import { describe, expect, it } from "vitest";
import { resolveToolCallCorrelation, type ToolCallCorrelationResolver } from "../src/runtime/tool-correlation.js";

function resolver(): ToolCallCorrelationResolver {
  return {
    forRequest: (requestId, clientId) => ({
      protocolVersion: 2,
      requestId,
      clientId,
      sessionId: "omi-session",
      runId: "omi-run",
      attemptId: "omi-attempt",
    }),
    forAdapter: (adapterId) => ({
      protocolVersion: 2,
      requestId: `adapter-request:${adapterId}`,
      clientId: `adapter-client:${adapterId}`,
      sessionId: "adapter-omi-session",
      runId: "adapter-omi-run",
      attemptId: "adapter-omi-attempt",
    }),
    unscoped: () => ({
      protocolVersion: 2,
      requestId: "unscoped-request",
      clientId: "unscoped-client",
      sessionId: "unscoped-omi-session",
      runId: "unscoped-omi-run",
      attemptId: "unscoped-omi-attempt",
    }),
  };
}

describe("resolveToolCallCorrelation", () => {
  it("requires clientId when requestId is supplied", () => {
    expect(
      resolveToolCallCorrelation({ requestId: "stale-request", adapterId: "pi-mono" }, resolver())
    ).toEqual({});
  });

  it("does not fall back when scoped request lookup misses", () => {
    const missingRequestResolver = {
      ...resolver(),
      forRequest: () => ({}),
    };

    expect(
      resolveToolCallCorrelation(
        { requestId: "stale-request", clientId: "client-a", adapterId: "pi-mono" },
        missingRequestResolver
      )
    ).toEqual({});
  });

  it("uses adapter or unscoped correlation only when no requestId is supplied", () => {
    expect(resolveToolCallCorrelation({ adapterId: "pi-mono" }, resolver())).toMatchObject({
      requestId: "adapter-request:pi-mono",
      clientId: "adapter-client:pi-mono",
    });
    expect(resolveToolCallCorrelation({}, resolver())).toMatchObject({
      requestId: "unscoped-request",
      clientId: "unscoped-client",
    });
  });
});
