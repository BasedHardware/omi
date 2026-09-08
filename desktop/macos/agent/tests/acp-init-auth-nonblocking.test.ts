import { describe, expect, it } from "vitest";

import { beginProviderAuthWithoutBlocking } from "../src/adapters/acp.js";

/**
 * Cold-start ACP `initialize` used to `await startAuthFlow()` on -32000, so a
 * launch with expired credentials sat inside init for the whole OAuth callback
 * timeout. No turn was on the wire yet, so nothing could terminalize and the
 * user's first send hung instead of failing fast (#10407).
 *
 * These drive the extracted kickoff seam directly: index.ts cannot be imported
 * under vitest (module scope spawns the ACP subprocess and binds stdin), which
 * is why its other coverage is source-scraping rather than behaviour.
 */

function harness(startAuthFlow: () => Promise<void>) {
  const events: string[] = [];
  const logs: string[] = [];
  const deps = {
    signalAuthRequired: () => events.push("signal"),
    startAuthFlow: () => {
      events.push("flow_started");
      return startAuthFlow();
    },
    logErr: (message: string) => logs.push(message),
  };
  return { events, logs, deps };
}

describe("beginProviderAuthWithoutBlocking", () => {
  it("returns without waiting for the OAuth callback", () => {
    // Never settles — stands in for a user who never completes sign-in. If the
    // kickoff awaited it (the bug), control would never reach the assertions.
    const { events, deps } = harness(() => new Promise<void>(() => {}));

    beginProviderAuthWithoutBlocking(deps);

    expect(events).toEqual(["signal", "flow_started"]);
  });

  it("signals auth_required before the flow produces anything", async () => {
    let release: (() => void) | undefined;
    const { events, deps } = harness(() => new Promise<void>((resolve) => (release = resolve)));

    beginProviderAuthWithoutBlocking(deps);
    // The host must already be told, so a pending send terminalizes as
    // `authentication` rather than waiting on the flow below.
    expect(events[0]).toBe("signal");

    release?.();
    await Promise.resolve();
  });

  it("still starts the flow, because sign-in needs its bridge-issued authUrl", () => {
    // Guards the tempting over-fix: dropping the call entirely leaves Swift's
    // startClaudeAuth with no URL to open, and the user cannot authenticate.
    const { events, deps } = harness(async () => {});

    beginProviderAuthWithoutBlocking(deps);

    expect(events).toContain("flow_started");
  });

  it("logs a failed flow instead of leaking an unhandled rejection", async () => {
    const { logs, deps } = harness(async () => {
      throw new Error("callback server refused to bind");
    });

    beginProviderAuthWithoutBlocking(deps);
    await Promise.resolve();
    await Promise.resolve();

    expect(logs).toHaveLength(1);
    expect(logs[0]).toContain("callback server refused to bind");
  });
});
