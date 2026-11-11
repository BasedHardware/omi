import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { beginProviderAuthWithoutBlocking, requestProviderAuthFromHost } from "../src/adapters/acp.js";

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

/**
 * Settings' Connect Claude control. Before it existed, a token that expired
 * mid-turn told the user to "reconnect Claude in Settings", where no control
 * could produce a sign-in URL.
 */
describe("requestProviderAuthFromHost", () => {
  function hostHarness(activeAuthUrl: string | undefined) {
    const events: string[] = [];
    const logs: string[] = [];
    return {
      events,
      logs,
      deps: {
        activeAuthUrl: () => activeAuthUrl,
        announceAuthUrl: (authUrl: string) => events.push(`announce:${authUrl}`),
        startAuthFlow: () => {
          events.push("flow_started");
          return Promise.reject(new Error("callback timed out"));
        },
        logErr: (message: string) => logs.push(message),
      },
    };
  }

  it("starts a fresh flow when none is waiting for its callback", async () => {
    const { events, logs, deps } = hostHarness(undefined);

    requestProviderAuthFromHost(deps);
    await Promise.resolve();

    expect(events).toEqual(["flow_started"]);
    expect(logs).toEqual(["Host-requested auth flow failed: callback timed out"]);
  });

  it("re-announces the live flow instead of replacing its callback server", () => {
    const { events, deps } = hostHarness("https://claude.ai/oauth/authorize?state=live");

    requestProviderAuthFromHost(deps);

    expect(events).toEqual(["announce:https://claude.ai/oauth/authorize?state=live"]);
  });

  it("is wired to the start_provider_auth message", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "../src/index.ts"), "utf8");
    expect(source).toMatch(/case "start_provider_auth": \{\s*requestProviderAuthFromHost\(/);
  });
});
