import assert from "node:assert/strict";
import { test } from "node:test";
import type {
  SettingsAppearancePreference,
  SettingsAppearanceSelection,
  SettingsWireEnvelope,
} from "@omi-core/contracts";
import { PlatformSettingsStore } from "@omi-core/domain";
import { ScriptedHttp } from "../fakes.js";

class MemoryAppearancePreference implements SettingsAppearancePreference {
  value: SettingsAppearanceSelection | null = null;
  readonly writes: SettingsAppearanceSelection[] = [];

  async readAppearance(): Promise<SettingsAppearanceSelection | null> {
    return this.value;
  }

  async writeAppearance(value: SettingsAppearanceSelection): Promise<void> {
    this.writes.push(value);
    this.value = value;
  }
}

const signedIn = (entitlement: SettingsWireEnvelope["entitlement"] = null): SettingsWireEnvelope => ({
  identity: { displayName: "Alex Rivera", email: "alex@example.com" },
  entitlement,
});

test("Settings refresh caches one coherent snapshot and reports offline truthfully", async () => {
  const http = new ScriptedHttp();
  const preference = new MemoryAppearancePreference();
  const store = await PlatformSettingsStore.open(http, preference);
  assert.deepEqual(store.status().refresh, { phase: "initial-loading", hasSavedData: false });

  http.respond({ status: 200, json: signedIn() });
  await store.refresh();
  assert.deepEqual(await store.snapshot(), {
    identity: { displayName: "Alex Rivera", email: "alex@example.com" },
    entitlement: null,
    appearance: "default",
  });
  assert.deepEqual(store.status().refresh, { phase: "ready", hasSavedData: true });

  http.respond({ status: 503, json: null, transportFailureReason: "offline" });
  await store.refresh();
  assert.deepEqual(store.status().refresh, {
    phase: "saved-but-refresh-failed",
    hasSavedData: true,
  });
  assert.equal((await store.snapshot()).identity?.email, "alex@example.com");

  http.respond({ status: 401, json: { error: "unauthorized" } });
  await store.refresh();
  assert.deepEqual(store.status().refresh, { phase: "unavailable", hasSavedData: false });
  // red-proof: folding real 401 into the synthetic signed-out case makes this
  // ready with identity:null instead of an auth-invalid blackout.
});

test("appearance persists through reopen and never enters an HTTP body", async () => {
  const preference = new MemoryAppearancePreference();
  const firstHttp = new ScriptedHttp();
  const first = await PlatformSettingsStore.open(firstHttp, preference);
  firstHttp.respond({ status: 200, json: { identity: null, entitlement: null } });
  await first.refresh();
  await first.patch({ appearance: "dark" });
  assert.deepEqual(preference.writes, ["dark"]);
  assert.equal((await first.snapshot()).appearance, "dark");

  const reopenedHttp = new ScriptedHttp();
  const reopened = await PlatformSettingsStore.open(reopenedHttp, preference);
  assert.equal((await reopened.snapshot()).appearance, "dark");
  assert.equal(reopenedHttp.calls.length, 0, "reopen reads the injected device preference only");
  assert.equal(JSON.stringify(firstHttp.calls).includes("appearance"), false);
  assert.equal(JSON.stringify(firstHttp.calls).includes("dark"), false);
});

test("sign-out is idempotent, updates the coherent cache, and has no outbox fiction", async () => {
  const http = new ScriptedHttp();
  const store = await PlatformSettingsStore.open(http, new MemoryAppearancePreference());
  http.respond({ status: 200, json: signedIn() }, { status: 204, json: null });
  await store.refresh();
  await store.signOut();
  await store.signOut();

  assert.deepEqual(await store.snapshot(), {
    identity: null,
    entitlement: null,
    appearance: "default",
  });
  assert.equal(http.calls.filter((call) => call.method === "DELETE").length, 1);
  assert.deepEqual(store.status().queue, { phase: "idle", pendingCount: 0 });
  assert.deepEqual(await store.deadLetters(), []);
  await store.discardDeadLetter("does-not-exist");
  assert.deepEqual(await store.deadLetters(), []);
});

test("failed sign-out preserves cached identity", async () => {
  const http = new ScriptedHttp();
  const store = await PlatformSettingsStore.open(http, new MemoryAppearancePreference());
  http.respond({ status: 200, json: signedIn() }, { status: 503, json: null });
  await store.refresh();
  await assert.rejects(store.signOut(), /sign-out unavailable/);
  assert.equal((await store.snapshot()).identity?.displayName, "Alex Rivera");
});
