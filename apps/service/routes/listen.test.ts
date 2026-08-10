// domain-pending(DIV-DOMCORE-012)

import { connect } from "node:net";
import { Database } from "bun:sqlite";
import { afterEach, describe, expect, test } from "bun:test";
import Ajv2020 from "ajv/dist/2020.js";

import {
  createInMemoryLocalServiceStores,
  createLocalService,
  type LocalService,
} from "../app-facing";
import { createScriptedTranscriptionSource } from "../listen/transcription-source";
import {
  createSqliteListenSegmentUnitOfWork,
  createSqliteLocalServiceStores,
} from "../../../drivers/sqlite/service-stores";
import { createEntitlementFrame } from "./listen";

const ACCOUNT = "listen-account";
const SESSION = "a661b15a-2401-4f5c-a4c4-23643dcf26d1";
const openServers: Array<ReturnType<typeof Bun.serve>> = [];

afterEach(() => {
  for (const server of openServers.splice(0)) server.stop(true);
});

const boot = (options: {
  readonly used?: number;
  readonly limit?: number | null;
  readonly delayMs?: number;
  readonly consumedSeconds?: number;
} = {}) => {
  const stores = createInMemoryLocalServiceStores();
  stores.settings.putIdentity(ACCOUNT, {
    displayName: "Listen fixture",
    email: "listen@example.invalid",
  });
  stores.settings.putEntitlement(ACCOUNT, {
    planLabel: options.limit === null ? "Omi Plus" : "Omi Free",
    limitKey: "transcription_seconds",
    used: options.used ?? 0,
    limit: options.limit ?? null,
    limitReached: false,
    upgradeAvailable: options.limit !== null,
  });
  const service = createLocalService({
    db: new Database(":memory:"),
    ownerAccountId: ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: `listen-${options.used ?? 0}-${options.limit ?? "unmetered"}`,
    stores,
    transcriptionSource: createScriptedTranscriptionSource([{
      delayMs: options.delayMs ?? 20,
      text: "persisted transcript",
      start: 0,
      end: 1,
      consumedSeconds: options.consumedSeconds ?? 1,
    }]),
  });
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch: service.app.fetch,
    websocket: service.websocket,
  });
  openServers.push(server);
  return { service, stores, server, baseUrl: `ws://127.0.0.1:${server.port}` };
};

interface ObservedSocket {
  readonly socket: WebSocket;
  readonly frames: unknown[];
  waitFor(predicate: (frame: unknown) => boolean, timeoutMs?: number): Promise<unknown>;
  readonly closed: Promise<CloseEvent>;
}

const observedSocket = async (
  service: LocalService,
  baseUrl: string,
  sessionId = SESSION,
): Promise<ObservedSocket> => {
  const socket = new WebSocket(
    `${baseUrl}/v4/listen?client_conversation_id=${sessionId}`,
    { headers: { authorization: `Bearer ${service.devToken}` } },
  );
  const frames: unknown[] = [];
  const listeners = new Set<() => void>();
  socket.addEventListener("message", (event) => {
    frames.push(JSON.parse(String(event.data)));
    for (const listener of listeners) listener();
  });
  const opened = new Promise<void>((resolve, reject) => {
    socket.addEventListener("open", () => resolve(), { once: true });
    socket.addEventListener("error", () => reject(new Error("websocket failed to open")), {
      once: true,
    });
  });
  const closed = new Promise<CloseEvent>((resolve) => {
    socket.addEventListener("close", resolve, { once: true });
  });
  await opened;

  return {
    socket,
    frames,
    closed,
    async waitFor(predicate, timeoutMs = 2_000): Promise<unknown> {
      const present = frames.find(predicate);
      if (present !== undefined) return present;
      return await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          listeners.delete(check);
          reject(new Error(`frame timeout; observed ${JSON.stringify(frames)}`));
        }, timeoutMs);
        const check = (): void => {
          const frame = frames.find(predicate);
          if (frame === undefined) return;
          clearTimeout(timeout);
          listeners.delete(check);
          resolve(frame);
        };
        listeners.add(check);
      });
    },
  };
};

const isReady = (frame: unknown): boolean => {
  const value = frame as { readonly type?: unknown; readonly status?: unknown };
  return value?.type === "service_status" && value.status === "ready";
};

const isTranscript = (frame: unknown): frame is readonly { readonly id: string }[] =>
  Array.isArray(frame) && frame.length > 0 && typeof frame[0]?.id === "string";

const schema = await Bun.file(
  new URL("../../../vendor/wire/listen/listen-protocol.schema.json", import.meta.url),
).json() as { readonly $id: string };
const ajv = new Ajv2020({ strict: false, validateFormats: false });
ajv.addSchema(schema);
const validators = {
  service: ajv.compile({ $ref: `${schema.$id}#/$defs/ServiceStatusEvent` }),
  conversation: ajv.compile({ $ref: `${schema.$id}#/$defs/ConversationSessionEvent` }),
  transcript: ajv.compile({ $ref: `${schema.$id}#/$defs/TranscriptBatchFrame` }),
  entitlement: ajv.compile({ $ref: `${schema.$id}#/$defs/EntitlementEvent` }),
};

const validatesEmittedFrame = (frame: unknown): boolean => {
  if (Array.isArray(frame)) return validators.transcript(frame) as boolean;
  const type = (frame as { readonly type?: unknown })?.type;
  if (type === "service_status") return validators.service(frame) as boolean;
  if (type === "conversation_session") return validators.conversation(frame) as boolean;
  if (type === "entitlement") return validators.entitlement(frame) as boolean;
  return false;
};

const waitUntil = async (predicate: () => boolean, timeoutMs = 2_000): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await Bun.sleep(5);
  }
  throw new Error("condition timeout");
};

const rawUpgradeResponse = async (
  port: number,
  authorization: string,
): Promise<string> => await new Promise((resolve, reject) => {
  const client = connect({ host: "127.0.0.1", port });
  let response = "";
  client.setEncoding("utf8");
  client.on("connect", () => {
    client.write(
      `GET /v4/listen?client_conversation_id=${SESSION} HTTP/1.1\r\n`
      + `Host: 127.0.0.1:${port}\r\n`
      + "Connection: Upgrade\r\n"
      + "Upgrade: websocket\r\n"
      + "Sec-WebSocket-Version: 13\r\n"
      + "Sec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\n"
      + `Authorization: ${authorization}\r\n\r\n`,
    );
  });
  client.on("data", (chunk) => {
    response += chunk;
    if (response.includes("\r\n\r\n")) client.end();
  });
  client.on("end", () => resolve(response));
  client.on("error", reject);
});

describe("GET /v4/listen WebSocket", () => {
  test("a crash between transcript durability and usage rolls both back before retry", async () => {
    const db = new Database(":memory:");
    const baseStores = createSqliteLocalServiceStores(db);
    baseStores.settings.putIdentity(ACCOUNT, {
      displayName: "Listen fixture",
      email: "listen@example.invalid",
    });
    baseStores.settings.putEntitlement(ACCOUNT, {
      planLabel: "Omi Free",
      limitKey: "transcription_seconds",
      used: 0,
      limit: 10,
      limitReached: false,
      upgradeAvailable: true,
    });
    let injectCrash = true;
    const stores = Object.freeze({
      ...baseStores,
      listenSegments: createSqliteListenSegmentUnitOfWork(db, {
        afterSegmentAppend: () => {
          if (!injectCrash) return;
          injectCrash = false;
          throw new Error("injected crash after transcript write");
        },
      }),
    });
    const service = createLocalService({
      db: new Database(":memory:"),
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "listen-atomic-crash",
      stores,
      transcriptionSource: createScriptedTranscriptionSource([
        { delayMs: 0, text: "rolled back", start: 0, end: 1, consumedSeconds: 1 },
        { delayMs: 0, text: "retry accepted", start: 1, end: 2, consumedSeconds: 1 },
      ]),
    });
    const server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch: service.app.fetch,
      websocket: service.websocket,
    });
    openServers.push(server);
    const baseUrl = `ws://127.0.0.1:${server.port}`;

    const first = await observedSocket(service, baseUrl);
    await first.waitFor(isReady);
    first.socket.send(new Uint8Array([1, 2, 3]));
    expect((await first.closed).code).toBe(1011);
    expect(stores.listen.listSegments(ACCOUNT, SESSION)).toEqual([]);
    const afterCrash = await service.app.request("/v1/settings", {
      headers: { authorization: `Bearer ${service.devToken}` },
    });
    expect((await afterCrash.json() as {
      readonly entitlement: { readonly used: number };
    }).entitlement.used).toBe(0);

    const retry = await observedSocket(service, baseUrl);
    await retry.waitFor(isReady);
    retry.socket.send(new Uint8Array([1, 2, 3]));
    await retry.waitFor(isTranscript);
    expect(stores.listen.listSegments(ACCOUNT, SESSION)).toHaveLength(1);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(1);
    retry.socket.close(1000, "done");
    await retry.closed;
    await waitUntil(() => stores.listen.readSession(ACCOUNT, SESSION)?.status === "completed");
  });

  test("every emitted frame type validates against the vendored schema and timing is real", async () => {
    const { service, stores, baseUrl } = boot({ used: 7, limit: null, delayMs: 40 });
    const observed = await observedSocket(service, baseUrl);
    await observed.waitFor(isReady);
    const sentAt = Date.now();
    observed.socket.send(new Uint8Array([1, 2, 3, 4]));
    await Bun.sleep(10);
    expect(observed.frames.some(isTranscript)).toBeFalse();
    await observed.waitFor(isTranscript);
    expect(Date.now() - sentAt).toBeGreaterThanOrEqual(30);
    observed.socket.close(1000, "done");
    await observed.closed;

    expect(observed.frames.length).toBeGreaterThan(0);
    expect(observed.frames.every(validatesEmittedFrame)).toBeTrue();
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(8);
    const settingsResponse = await service.app.request("/v1/settings", {
      headers: { authorization: `Bearer ${service.devToken}` },
    });
    expect((await settingsResponse.json() as {
      readonly entitlement: { readonly used: number };
    }).entitlement.used).toBe(8);
    expect(service.writePath.settings).toBe(stores.settings);
    expect(stores.listen.listSegments(ACCOUNT, SESSION)).toHaveLength(1);
    await waitUntil(() => stores.conversations.readRecord(ACCOUNT, SESSION) !== null);
    expect(stores.conversations.readRecord(ACCOUNT, SESSION)?.status).toBe("processing");
  });

  test("crossing a metered ceiling emits the final entitlement frame then closes 4020", async () => {
    const { service, stores, baseUrl } = boot({
      used: 0.5,
      limit: 1,
      delayMs: 1,
      consumedSeconds: 0.75,
    });
    const observed = await observedSocket(service, baseUrl);
    await observed.waitFor(isReady);
    observed.socket.send(new Uint8Array([1, 2, 3, 4]));
    const closed = observed.closed;
    const close = await closed;

    expect(close.code).toBe(4020);
    const entitlement = observed.frames.at(-1) as Record<string, unknown>;
    expect(entitlement).toEqual({
      type: "entitlement",
      state: "upgrade_required",
      reason: "free_tier_transcription_limit",
      usage: { amount: 1.25, unit: "seconds" },
      limit: { kind: "metered", amount: 1, unit: "seconds" },
      upgrade_target: "plan_upgrade",
    });
    expect(validators.entitlement(entitlement)).toBeTrue();
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(1.25);
    expect(stores.listen.readSession(ACCOUNT, SESSION)?.status).toBe("entitlement_exhausted");
    expect(stores.conversations.readRecord(ACCOUNT, SESSION)?.is_locked).toBeTrue();
  });

  test("a deleted account's otherwise valid token is refused on the upgrade request", async () => {
    const { service, stores, server } = boot();
    stores.accountLifecycle.setLifecycle(ACCOUNT, "deleted");
    const wireResponse = await rawUpgradeResponse(
      server.port,
      `Bearer ${service.devToken}`,
    );

    expect(wireResponse.split("\r\n", 1)[0]).toBe("HTTP/1.1 401 Unauthorized");
    expect(stores.listen.readSession(ACCOUNT, SESSION)).toBeNull();
  });

  test("unmetered entitlement payloads retain honest usage and a tagged limit", () => {
    const { stores } = boot({ used: 17.25, limit: null });
    const projection = stores.settings.readEntitlement(ACCOUNT)!;

    expect(createEntitlementFrame(projection)).toEqual({
      type: "entitlement",
      state: "upgrade_required",
      reason: "free_tier_transcription_limit",
      usage: { amount: 17.25, unit: "seconds" },
      limit: { kind: "unmetered" },
      upgrade_target: "plan_upgrade",
    });
    expect(validators.entitlement(createEntitlementFrame(projection))).toBeTrue();
    expect(validators.entitlement({
      ...createEntitlementFrame(projection),
      state: "capture_continues",
    })).toBeFalse();
    expect(validators.entitlement({
      ...createEntitlementFrame(projection),
      limit: { kind: "unmetered", amount: -1 },
    })).toBeFalse();
  });

  test("a drop after send still redelivers the durable segment with its original id", async () => {
    const { service, stores, baseUrl } = boot({ delayMs: 0 });
    const first = await observedSocket(service, baseUrl);
    await first.waitFor(isReady);
    first.socket.send(new Uint8Array([1, 2, 3, 4]));
    const firstDelivery = await first.waitFor(isTranscript) as readonly { readonly id: string }[];
    const originalId = firstDelivery[0]!.id;
    first.socket.close(4000, "simulated_drop");
    await first.closed;

    const reconnected = await observedSocket(service, baseUrl);
    const redelivered = await reconnected.waitFor(isTranscript) as readonly { readonly id: string }[];
    expect(redelivered.map((segment) => segment.id)).toEqual([originalId]);
    expect(stores.listen.listSegments(ACCOUNT, SESSION).map((segment) => segment.id)).toEqual([
      originalId,
    ]);
    reconnected.socket.close(1000, "done");
    await reconnected.closed;
  });

  test("exhaustion after send cannot suppress redelivery on reconnect", async () => {
    const { service, stores, baseUrl } = boot({
      used: 0.5,
      limit: 1,
      delayMs: 0,
      consumedSeconds: 0.75,
    });
    const first = await observedSocket(service, baseUrl);
    await first.waitFor(isReady);
    first.socket.send(new Uint8Array([1, 2, 3, 4]));
    const original = await first.waitFor(isTranscript) as readonly { readonly id: string }[];
    expect((await first.closed).code).toBe(4020);
    expect(stores.settings.readEntitlement(ACCOUNT)?.limitReached).toBeTrue();

    const resumed = await observedSocket(service, baseUrl);
    const replay = await resumed.waitFor(isTranscript) as readonly { readonly id: string }[];
    expect(replay.map((segment) => segment.id)).toEqual(original.map((segment) => segment.id));
    expect((await resumed.closed).code).toBe(4020);
  });
});
