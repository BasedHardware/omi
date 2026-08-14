// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-001)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import type { ApplicationMemoryReadAuthorizationRequest } from "../../../core/retrieve/authorization-boundary";
import { createSqliteQaRecallLoader } from "../../../drivers/sqlite/application-recall-read";
import { createQaRecallReader } from "../../qa/recall-service";
import { seedQaSnapshot } from "../../qa/seed";
import {
  QA_MEMORY_READ_CURSOR_BINDINGS,
  qaMemoryReadProduceRenders,
} from "../../qa/memory-read-bindings";
import { prepareMemoryRead, readMemoryPage, type CoherentQaLoad } from "./memory-read";

/**
 * THE ASSERTION THIS WHOLE COLLAPSE EXISTS FOR:
 * **one memory has ONE public identity, whichever door served it.**
 *
 * Nothing asserted this before. `ApplicationReadPorts` was constructed twice —
 * here for the REST door and in `apps/qa/recall-service.ts` for the MCP door —
 * and the granularity tests compared STRUCTURAL NODE SETS, which agreed
 * perfectly while the public ids did not. Measured on the pre-collapse tree,
 * over the shared snapshot and shared principal this file uses:
 *
 *   text                    identical
 *   provenance.outputDigest identical  (217942867fbea63c… — the same render)
 *   id                      MCP  mem1_eca59618fff27e10…
 *                           REST mem1_dd73274cc9b1a9ac…
 *
 * Same memory, same render, two public identities — because the two
 * compositions keyed the opaque-ref codecs differently. Every node-level
 * cross-door assertion in the suite passed throughout, which is exactly how a
 * divergence one layer below where anyone is looking survives.
 *
 * This test drives BOTH doors' real entry points below the transport
 * (`createQaRecallReader` for MCP, `prepareMemoryRead`/`readMemoryPage` for
 * REST) over ONE SQLite snapshot with ONE principal and ONE set of key
 * material. The transports themselves are correctly separate and are not
 * exercised here.
 *
 * red-proof: give either door its own opaque-ref codec factory again — e.g.
 * scope the MCP door by a caller-assembled `owner|app|key` string instead of the
 * authorization boundary's `principal_digest` — and the item-id assertion fails
 * while the text and node-set assertions keep passing.
 */

const OWNER = "owner:cross-door";
const APP = "app:cross-door";
const KEY = "key:cross-door";
const TIMEZONE = "UTC";
const READ_TIMESTAMP = 1_800_000_000;
const CLAIMS = 5;

const CODEC_ROOT_SECRET = new Uint8Array(32).fill(0x2d);
const SIGNING_KEYSET = Object.freeze({
  active_key_id: "cross-door-key-1",
  keys: Object.freeze([Object.freeze({
    key_id: "cross-door-key-1",
    secret: new Uint8Array(32).fill(0x71),
  })]),
});

const AUTHORIZATION: ApplicationMemoryReadAuthorizationRequest = Object.freeze({
  owner_account_id: OWNER,
  credential: Object.freeze({
    owner_account_id: OWNER,
    credential_kind: "mcp_api_key" as const,
    app_id: APP,
    key_id: KEY,
    scopes: Object.freeze(["memories.read"]),
    active: true,
  }),
  persisted_grant: Object.freeze({
    owner_account_id: OWNER,
    consumer: "mcp" as const,
    app_id: APP,
    key_id: KEY,
    enabled: true,
    default_read: true,
    scopes: Object.freeze(["memories.read"]),
  }),
});

const seededDatabase = (): Database => {
  const db = new Database(":memory:");
  seedQaSnapshot(db, {
    owner_account_id: OWNER,
    account_timezone: TIMEZONE,
    claim_count: CLAIMS,
  });
  return db;
};

/** The MCP door, below its transport. */
const readViaMcpDoor = async (db: Database): Promise<string> => {
  const reader = createQaRecallReader({
    db,
    principal: { owner_account_id: OWNER, app_id: APP, key_id: KEY },
    account_timezone: TIMEZONE,
    limits: { max_items: 256, max_bytes: 4_000_000 },
    codec_root_secret: CODEC_ROOT_SECRET,
    cursor_signing_keyset: SIGNING_KEYSET,
    authorization: { resolveAuthorizationRequest: () => AUTHORIZATION },
    read_timestamp_epoch_seconds: READ_TIMESTAMP,
    traceSink: () => {},
  });
  await reader.refresh();
  return (await reader.readPage({ limit: 100, cursor: null })).canonical_json;
};

/** The REST door, below its transport. */
const readViaRestDoor = async (db: Database): Promise<string> => {
  const loader = createSqliteQaRecallLoader({
    db,
    owner_account_id: OWNER,
    account_timezone: TIMEZONE,
    limits: { max_items: 256, max_bytes: 4_000_000 },
  });
  const prepared = await prepareMemoryRead({
    cursorBindings: QA_MEMORY_READ_CURSOR_BINDINGS,
    produceRenders: qaMemoryReadProduceRenders,
    loadCoherent: loader as unknown as () => CoherentQaLoad,
    resolveAuthorization: () => AUTHORIZATION,
    codecRootSecret: CODEC_ROOT_SECRET,
    cursorSigningKeyset: SIGNING_KEYSET,
    readTimestampEpochSeconds: READ_TIMESTAMP,
    acceptedCoverageState: "no_eligible",
    stmCoverageState: "no_eligible",
    traceSink: () => {},
  });
  return (await readMemoryPage({ limit: 100, cursor: null }, prepared)).canonical_json;
};

const parse = (json: string) => {
  const page = parseSynthesizedPageJson(json);
  expect(page).not.toBeNull();
  return page as NonNullable<ReturnType<typeof parseSynthesizedPageJson>>;
};

describe("one memory, one public identity, whichever door", () => {
  test("both doors mint the same public item ids for the same memories", async () => {
    const db = seededDatabase();
    const [mcpJson, restJson] = await Promise.all([readViaMcpDoor(db), readViaRestDoor(db)]);
    const mcp = parse(mcpJson);
    const rest = parse(restJson);

    // Non-vacuity, first: an empty page would satisfy every equality below.
    expect(mcp.items.length).toBe(CLAIMS);
    expect(rest.items.length).toBe(CLAIMS);

    // The pre-collapse tree passed this line and failed the next one.
    expect(rest.items.map((item) => item.text)).toEqual(mcp.items.map((item) => item.text));
    expect(rest.items.map((item) => item.id)).toEqual(mcp.items.map((item) => item.id));
    expect(rest.items.map((item) => [...item.citations]))
      .toEqual(mcp.items.map((item) => [...item.citations]));
  });

  test("both doors emit byte-identical page bytes for the same read", async () => {
    // Stronger than the item-level assertion and the reason it is worth having:
    // the completeness envelope, the declared frontier, and the window are also
    // wire-visible, and none of them is reached by an item-for-item comparison.
    // The pre-collapse doors disagreed here too — `frontier-v1:qa:<generation>`
    // against a keyed reader-scoped handle.
    const db = seededDatabase();
    const [mcpJson, restJson] = await Promise.all([readViaMcpDoor(db), readViaRestDoor(db)]);
    expect(restJson).toBe(mcpJson);
  });

  test("a cursor minted at one door is redeemable at the other", async () => {
    // A cursor binds the read's coherent snapshot. If the two doors derived any
    // bound coordinate differently the token would not cross, which is the same
    // divergence expressed in pagination state rather than in ids.
    const db = seededDatabase();
    const firstFromMcp = parse(await (async () => {
      const reader = createQaRecallReader({
        db,
        principal: { owner_account_id: OWNER, app_id: APP, key_id: KEY },
        account_timezone: TIMEZONE,
        limits: { max_items: 256, max_bytes: 4_000_000 },
        codec_root_secret: CODEC_ROOT_SECRET,
        cursor_signing_keyset: SIGNING_KEYSET,
        authorization: { resolveAuthorizationRequest: () => AUTHORIZATION },
        read_timestamp_epoch_seconds: READ_TIMESTAMP,
        traceSink: () => {},
      });
      await reader.refresh();
      return (await reader.readPage({ limit: 2, cursor: null })).canonical_json;
    })());
    expect(firstFromMcp.window.nextCursor).not.toBeNull();

    const loader = createSqliteQaRecallLoader({
      db,
      owner_account_id: OWNER,
      account_timezone: TIMEZONE,
      limits: { max_items: 256, max_bytes: 4_000_000 },
    });
    const prepared = await prepareMemoryRead({
    cursorBindings: QA_MEMORY_READ_CURSOR_BINDINGS,
    produceRenders: qaMemoryReadProduceRenders,
      loadCoherent: loader as unknown as () => CoherentQaLoad,
      resolveAuthorization: () => AUTHORIZATION,
      codecRootSecret: CODEC_ROOT_SECRET,
      cursorSigningKeyset: SIGNING_KEYSET,
      readTimestampEpochSeconds: READ_TIMESTAMP,
      acceptedCoverageState: "no_eligible",
      stmCoverageState: "no_eligible",
      traceSink: () => {},
    });
    const secondFromRest = parse((await readMemoryPage(
      { limit: 2, cursor: firstFromMcp.window.nextCursor },
      prepared,
    )).canonical_json);

    expect(secondFromRest.items.length).toBe(2);
    const firstIds = firstFromMcp.items.map((item) => item.id);
    const secondIds = secondFromRest.items.map((item) => item.id);
    expect(new Set([...firstIds, ...secondIds]).size).toBe(4);
  });
});
