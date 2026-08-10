// domain-pending(DIV-DOMCORE-012)

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";

import { createSqliteLocalServiceStores } from "./index";
import { createSqliteListenSegmentUnitOfWork } from "./listen-segment-unit-of-work";

test("segment durability and usage accounting roll back together across the crash seam", async () => {
  const db = new Database(":memory:");
  const stores = createSqliteLocalServiceStores(db);
  const accountId = "atomic-listen-account";
  const sessionId = "257e409b-b22e-41a4-958e-3cbc054b2d74";
  const segment = Object.freeze({
    id: "crash-window-segment",
    text: "charge exactly once",
    is_user: false,
    start: 0,
    end: 1.25,
  });
  stores.settings.putEntitlement(accountId, {
    planLabel: "Omi Free",
    limitKey: "transcription_seconds",
    used: 2,
    limit: 10,
    limitReached: false,
    upgradeAvailable: true,
  });
  stores.listen.openOrResume({
    accountId,
    id: sessionId,
    conversationId: sessionId,
    clientConversationId: sessionId,
    at: "2026-08-10T12:00:00.000Z",
    source: "desktop",
    codec: "opus",
    sampleRate: 16_000,
    channels: 1,
  });

  const crash = createSqliteListenSegmentUnitOfWork(db, {
    afterSegmentAppend: () => { throw new Error("injected crash after transcript write"); },
  });
  await expect(crash.reserve({
    accountId,
    sessionId,
    segment,
    consumedSeconds: 1.25,
    at: "2026-08-10T12:00:01.000Z",
  })).rejects.toThrow("injected crash after transcript write");
  expect(stores.listen.listSegments(accountId, sessionId)).toEqual([]);
  expect(stores.settings.readEntitlement(accountId)?.used).toBe(2);

  const healthy = createSqliteListenSegmentUnitOfWork(db);
  expect((await healthy.reserve({
    accountId,
    sessionId,
    segment,
    consumedSeconds: 1.25,
    at: "2026-08-10T12:00:02.000Z",
  })).kind).toBe("accepted");
  expect(stores.settings.readEntitlement(accountId)?.used).toBe(3.25);
  expect((await healthy.reserve({
    accountId,
    sessionId,
    segment,
    consumedSeconds: 1.25,
    at: "2026-08-10T12:00:03.000Z",
  })).kind).toBe("accepted");
  expect(stores.listen.listSegments(accountId, sessionId)).toEqual([segment]);
  expect(stores.settings.readEntitlement(accountId)?.used).toBe(3.25);
  db.close();
});

test("listen sessions, transcript ids, delivery state, and shared usage survive restart", () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-listen-store-"));
  const path = join(directory, "service.sqlite");
  const accountId = "sqlite-listen-account";
  const sessionId = "3bb98296-fc81-4928-a96d-96a8fd31ecb4";
  const segment = Object.freeze({
    id: "stable-segment-id",
    text: "survives restart",
    is_user: false,
    start: 0,
    end: 1.5,
  });

  try {
    const firstDb = new Database(path, { create: true });
    const first = createSqliteLocalServiceStores(firstDb);
    first.settings.putEntitlement(accountId, {
      planLabel: "Omi Free",
      limitKey: "transcription_seconds",
      used: 2,
      limit: 10,
      limitReached: false,
      upgradeAvailable: true,
    });
    first.listen.openOrResume({
      accountId,
      id: sessionId,
      conversationId: sessionId,
      clientConversationId: sessionId,
      at: "2026-08-10T12:00:00.000Z",
      source: "desktop",
      codec: "opus",
      sampleRate: 16_000,
      channels: 1,
    });
    expect(first.listen.appendSegment(
      accountId,
      sessionId,
      segment,
      "2026-08-10T12:00:01.000Z",
    ).inserted).toBeTrue();
    first.settings.consumeTranscriptionSeconds(accountId, 1.5);
    first.listen.closeSession(
      accountId,
      sessionId,
      "interrupted",
      "2026-08-10T12:00:02.000Z",
    );
    firstDb.close();

    const secondDb = new Database(path);
    const second = createSqliteLocalServiceStores(secondDb);
    expect(second.listen.pendingSegments(accountId, sessionId)).toEqual([segment]);
    expect(second.settings.readEntitlement(accountId)?.used).toBe(3.5);
    const resumed = second.listen.openOrResume({
      accountId,
      id: sessionId,
      conversationId: sessionId,
      clientConversationId: sessionId,
      at: "2026-08-10T12:01:00.000Z",
      source: "desktop",
      codec: "opus",
      sampleRate: 16_000,
      channels: 1,
    });
    expect(resumed.resumed).toBeTrue();
    expect(resumed.pendingSegments.map((item) => item.id)).toEqual([segment.id]);
    expect(second.listen.appendSegment(
      accountId,
      sessionId,
      segment,
      "2026-08-10T12:01:01.000Z",
    ).inserted).toBeFalse();
    second.listen.markDelivered(accountId, sessionId, [segment.id]);
    expect(second.listen.pendingSegments(accountId, sessionId)).toEqual([]);
    expect(second.listen.listSegments(accountId, sessionId)).toEqual([segment]);
    expect(second.listen.openOrResume({
      accountId,
      id: sessionId,
      conversationId: sessionId,
      clientConversationId: sessionId,
      at: "2026-08-10T12:02:00.000Z",
      source: "desktop",
      codec: "opus",
      sampleRate: 16_000,
      channels: 1,
    }).pendingSegments).toEqual([segment]);
    secondDb.close();
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
