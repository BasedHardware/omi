import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  parseSettingsWireEnvelope,
  type HttpResponse,
  type SettingsWireEnvelope,
} from "@omi-core/contracts";
import {
  deletePlatformCurrentSession,
  fetchPlatformSettings,
  PLATFORM_CURRENT_SESSION_PATH,
  PLATFORM_SETTINGS_PATH,
} from "@omi-core/adapters-platform";
import { ScriptedHttp } from "../fakes.js";

type CorpusRow = {
  readonly wireCase: string;
  readonly status: number;
  readonly body: unknown;
  readonly accepted: boolean;
};

const SETTINGS_WIRE_CORPUS = "contracts/wire/settings/settings-wire-conformance.json";
const corpus = JSON.parse(readFileSync(
  new URL(`../../../../${SETTINGS_WIRE_CORPUS}`, import.meta.url),
  "utf8",
)) as CorpusRow[];

test("the Settings parser consumes every shared wire case without repairing it", () => {
  for (const row of corpus.filter((candidate) => candidate.status === 200)) {
    const parsed = parseSettingsWireEnvelope(row.body);
    assert.equal(parsed !== null, row.accepted, row.wireCase);
    if (row.accepted) {
      assert.deepEqual(parsed, row.body, `${row.wireCase} must round-trip exactly`);
    }
  }
  // red-proof: remove any exact-key or semantic check in
  // parseSettingsWireEnvelope and one of the named refusal rows above becomes
  // accepted. Remove empty-string preservation or coerce limit:null and the
  // corresponding accepted row no longer round-trips exactly.
});

test("hostile Settings objects fail closed", () => {
  const identity = { displayName: "A", email: "a@example.invalid" };
  const entitlement = {
    planLabel: "Omi Plus",
    limitKey: "memories",
    used: 7,
    limit: 100,
    limitReached: false,
    upgradeAvailable: true,
  };
  const hostile: unknown[] = [
    null,
    [],
    {},
    { identity },
    { identity, entitlement, extra: true },
    { identity: { ...identity, extra: true }, entitlement: null },
    { identity, entitlement: { ...entitlement, extra: true } },
    { identity: { displayName: 7, email: "" }, entitlement: null },
    { identity, entitlement: { ...entitlement, used: -1 } },
    { identity, entitlement: { ...entitlement, used: Number.NaN } },
    { identity, entitlement: { ...entitlement, limit: Number.POSITIVE_INFINITY } },
    { identity, entitlement: { ...entitlement, limit: null, limitReached: true } },
    { identity: null, entitlement },
  ];
  for (const raw of hostile) assert.equal(parseSettingsWireEnvelope(raw), null);
});

test("the adapter uses only the two exact origin-relative Settings routes", async () => {
  const http = new ScriptedHttp();
  const envelope: SettingsWireEnvelope = {
    identity: { displayName: "A", email: "" },
    entitlement: null,
  };
  http.respond({ status: 200, json: envelope }, { status: 204, json: null });

  assert.deepEqual(await fetchPlatformSettings(http), {
    kind: "snapshot",
    snapshot: envelope,
  });
  assert.deepEqual(await deletePlatformCurrentSession(http), { ok: true });
  assert.deepEqual(http.calls, [
    { method: "GET", path: PLATFORM_SETTINGS_PATH },
    { method: "DELETE", path: PLATFORM_CURRENT_SESSION_PATH },
  ]);
  const wire = JSON.stringify(http.calls);
  assert.doesNotMatch(wire, /https?:\/\//);
  assert.doesNotMatch(wire, /authorization|bearer/i);
  assert.equal(http.calls.some((call) => Object.hasOwn(call, "body")), false);
});

test("only a typed host not-authenticated failure is signed-out", async () => {
  const responses: HttpResponse[] = [
    { status: 401, json: null, transportFailureReason: "not-authenticated" },
    { status: 401, json: { error: "unauthorized" } },
  ];
  const http = new ScriptedHttp();
  http.respond(...responses);

  assert.deepEqual(await fetchPlatformSettings(http), {
    kind: "snapshot",
    snapshot: { identity: null, entitlement: null },
  });
  assert.deepEqual(await fetchPlatformSettings(http), { kind: "auth-invalid", status: 401 });
  // red-proof: interpreting status 401 alone as signed-out makes the second
  // assertion return a snapshot and erases the absent-vs-invalid distinction.
});

test("malformed success and failed DELETE remain unavailable", async () => {
  const http = new ScriptedHttp();
  http.respond(
    { status: 200, json: { identity: null } },
    { status: 503, json: { error: "service_unavailable" } },
  );
  assert.deepEqual(await fetchPlatformSettings(http), { kind: "unavailable", status: 200 });
  assert.deepEqual(await deletePlatformCurrentSession(http), { ok: false, status: 503 });
});
