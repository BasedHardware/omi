// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
/**
 * Round-trip proof at the rendered layer: a user-asserted note (HTTP door) and
 * a finalized listen conversation each produce synthesized `GET /v1/memories`
 * text that carries the fact. Red-proof: the same assertion fails when the
 * local pipeline is unwired (`accept-only`).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Database } from "bun:sqlite";
import { afterEach, describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";
import { WRITE_ERRORS } from "@omi-core/ratified-contracts/write/ops";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  createLocalService,
  type LocalMemoryFormationMode,
  type LocalService,
} from "../app-facing";
import { createScriptedChatGenerationSource } from "../chat/generation-source";
import { createEmptyChatGenerationContextSource } from "../chat/generation-context";
import { createDeterministicListenConversationProcessor } from "../listen/conversation-processor";
import { createScriptedTranscriptionSource } from "../listen/transcription-source";
import { STM_NOTES_OPS_PATH } from "./stm-notes";

const OWNER = "local-dev-user";
const LISTEN_ACCOUNT = "listen-account";
const LISTEN_SESSION = "a661b15a-2401-4f5c-a4c4-23643dcf26d1";
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";
const ACTIVE_EPOCH = 7;
const NOTE_FACT = "Atlas likes oat milk at Harborline Cafe";
const LISTEN_FACT = "Cedar Loop hosts the Saturday market";
const openServers: Array<ReturnType<typeof Bun.serve>> = [];

afterEach(() => {
  for (const server of openServers.splice(0)) server.stop(true);
});

const writeId = (seed: string): string => seed.padEnd(64, "0").slice(0, 64);

interface Booted {
  readonly service: LocalService;
  readonly auth: string;
}

const bootNotes = (mode: LocalMemoryFormationMode = "wired"): Booted => {
  const service = createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: OWNER,
    memoryCount: 0,
    accountTimezone: "America/Los_Angeles",
    devSecretLabel: `${DEV_KEY_MATERIAL_LABEL}-${mode}`,
    memoryFormationMode: mode,
  });
  return { service, auth: `Bearer ${service.devToken}` };
};

const control = async (booted: Booted, path: string, body: unknown): Promise<Response> =>
  booted.service.app.request(path, {
    method: "POST",
    headers: { authorization: booted.auth, "content-type": "application/json" },
    body: JSON.stringify(body),
  });

const cutOver = async (booted: Booted, epoch = ACTIVE_EPOCH): Promise<void> => {
  const observation = (overrides: Record<string, unknown>) => ({
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });
  await control(booted, "/v1/qa/control/observe", observation({}));
  await control(booted, "/v1/qa/control/observe", observation({
    control_revision: 2, account_generation: "migrating",
  }));
  await control(booted, "/v1/qa/control/observe", observation({
    control_revision: 3, account_generation: "new", account_epoch: epoch,
  }));
  const activated = await control(booted, "/v1/qa/control/activate", {
    epoch, at_control_revision: 3,
  });
  expect(await activated.json()).toMatchObject({ activated: true });
};

const noteEnvelope = (text: string, seed: string): string => JSON.stringify({
  write_id: writeId(seed),
  account_epoch: ACTIVE_EPOCH,
  domain: "stm-notes",
  op: {
    op: "create",
    record_id: `note-${seed}`,
    content: { text, client_write_ref: `ref-${seed}` },
  },
});

const postNote = async (booted: Booted, body: string): Promise<{
  readonly status: number;
  readonly text: string;
}> => {
  const response = await booted.service.app.request(STM_NOTES_OPS_PATH, {
    method: "POST",
    headers: {
      authorization: booted.auth,
      "content-type": "application/json",
    },
    body,
  });
  return { status: response.status, text: await response.text() };
};

const renderedMemories = async (service: LocalService, token: string): Promise<{
  readonly status: number;
  readonly texts: readonly string[];
  readonly body: string;
}> => {
  const response = await service.app.request("/v1/memories?limit=25", {
    headers: { authorization: `Bearer ${token}` },
  });
  const body = await response.text();
  if (response.status !== 200) {
    return { status: response.status, texts: [], body };
  }
  const page = parseSynthesizedPageJson(body);
  if (page === null) {
    return { status: response.status, texts: [], body };
  }
  return {
    status: response.status,
    texts: page.items.map((item) => item.text),
    body,
  };
};

const hop = (label: string, value: unknown): void => {
  console.log(`HOP ${label} ${typeof value === "string" ? value : JSON.stringify(value)}`);
};

const bootListen = (mode: LocalMemoryFormationMode, transcript: string) => {
  const stores = createInMemoryLocalServiceStores();
  stores.settings.putIdentity(LISTEN_ACCOUNT, {
    displayName: "Listen fixture",
    email: "listen@example.invalid",
  });
  stores.settings.putEntitlement(LISTEN_ACCOUNT, {
    planLabel: "Omi Plus",
    limitKey: "transcription_seconds",
    used: 0,
    limit: null,
    limitReached: false,
    upgradeAvailable: false,
  });
  stores.accountLifecycle.setLifecycle(LISTEN_ACCOUNT, "active");
  const service = createLocalService({
    db: new Database(":memory:"),
    ownerAccountId: LISTEN_ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: `listen-formation-${mode}`,
    stores,
    transcriptionSource: createScriptedTranscriptionSource([{
      delayMs: 5,
      text: transcript,
      start: 0,
      end: 1,
      consumedSeconds: 1,
    }]),
    conversationProcessorFactory: createDeterministicListenConversationProcessor,
    generationSource: createScriptedChatGenerationSource(),
    generationContext: createEmptyChatGenerationContextSource(),
    memoryFormationMode: mode,
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

const waitUntil = async (predicate: () => boolean, timeoutMs = 2_000): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await Bun.sleep(5);
  }
  throw new Error("condition timeout");
};

const captureListen = async (
  service: LocalService,
  baseUrl: string,
): Promise<void> => {
  const socket = new WebSocket(
    `${baseUrl}/v4/listen?client_conversation_id=${LISTEN_SESSION}`,
    { headers: { authorization: `Bearer ${service.devToken}` } },
  );
  const frames: unknown[] = [];
  const opened = new Promise<void>((resolve, reject) => {
    socket.addEventListener("open", () => resolve(), { once: true });
    socket.addEventListener("error", () => reject(new Error("websocket failed to open")), {
      once: true,
    });
  });
  const closed = new Promise<CloseEvent>((resolve) => {
    socket.addEventListener("close", resolve, { once: true });
  });
  socket.addEventListener("message", (event) => {
    frames.push(JSON.parse(String(event.data)));
  });
  await opened;
  const readyDeadline = Date.now() + 2_000;
  while (Date.now() < readyDeadline) {
    const ready = frames.some((frame) => {
      const value = frame as { readonly type?: unknown; readonly status?: unknown };
      return value?.type === "service_status" && value.status === "ready";
    });
    if (ready) break;
    await Bun.sleep(5);
  }
  socket.send(new Uint8Array([1, 2, 3, 4]));
  const transcriptDeadline = Date.now() + 2_000;
  while (Date.now() < transcriptDeadline) {
    const transcript = frames.some((frame) => Array.isArray(frame) && frame.length > 0);
    if (transcript) break;
    await Bun.sleep(5);
  }
  socket.close(1000, "done");
  await closed;
};

describe("HTTP user-asserted note round trip at GET /v1/memories", () => {
  test("red-proof: accept-only writes the note and does not render the fact", async () => {
    const booted = bootNotes("accept-only");
    await cutOver(booted);
    const written = await postNote(booted, noteEnvelope(NOTE_FACT, "a"));
    hop("http-write-red", written);
    expect(written.status).toBe(200);
    expect(booted.service.memoryFormation.lastDrain).toBeNull();
    const rendered = await renderedMemories(booted.service, booted.service.devToken);
    hop("rendered-red", rendered.texts);
    expect(rendered.status).toBe(200);
    expect(rendered.texts.some((text) => text.includes(NOTE_FACT))).toBe(false);
  });

  test("wired: the note's fact is in synthesized memory text", async () => {
    const booted = bootNotes("wired");
    await cutOver(booted);
    const written = await postNote(booted, noteEnvelope(NOTE_FACT, "b"));
    hop("http-write", written);
    expect(written.status).toBe(200);
    hop("drain", booted.service.memoryFormation.lastDrain);
    expect(booted.service.memoryFormation.lastDrain?.formation.kind).toBe("completed");
    expect(booted.service.memoryFormation.lastDrain?.promotion.promoted).toBeGreaterThan(0);
    const rendered = await renderedMemories(booted.service, booted.service.devToken);
    hop("rendered", rendered.texts);
    expect(rendered.status).toBe(200);
    expect(rendered.texts.some((text) => text.includes(NOTE_FACT))).toBe(true);
  });

  test("a later note adds; it does not overwrite the first user-asserted fact", async () => {
    const booted = bootNotes("wired");
    await cutOver(booted);
    const first = await postNote(booted, noteEnvelope(NOTE_FACT, "c"));
    expect(first.status).toBe(200);
    const CORRECTION = "Atlas likes almond milk at Harborline Cafe";
    const second = await postNote(booted, noteEnvelope(CORRECTION, "d"));
    expect(second.status).toBe(200);
    const rendered = await renderedMemories(booted.service, booted.service.devToken);
    hop("rendered-additive", rendered.texts);
    expect(rendered.status).toBe(200);
    expect(rendered.texts.some((text) => text.includes(NOTE_FACT))).toBe(true);
    expect(rendered.texts.some((text) => text.includes(CORRECTION))).toBe(true);
  });

  test("POST /v1/memories/ops cannot patch a synthesized memory", async () => {
    const booted = bootNotes("wired");
    await cutOver(booted);
    await postNote(booted, noteEnvelope(NOTE_FACT, "e"));
    const before = await renderedMemories(booted.service, booted.service.devToken);
    const response = await booted.service.app.request("/v1/memories/ops", {
      method: "POST",
      headers: {
        authorization: booted.auth,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        write_id: writeId("f"),
        account_epoch: ACTIVE_EPOCH,
        domain: "memories",
        op: { op: "patch", record_id: "anything", patch: { text: "silently overwritten" } },
      }),
    });
    expect(response.status).toBe(WRITE_ERRORS.validation.status);
    expect(await response.text()).toBe(WRITE_ERRORS.validation.body);
    const after = await renderedMemories(booted.service, booted.service.devToken);
    expect(after.texts).toEqual(before.texts);
    expect(after.texts.some((text) => text.includes("silently overwritten"))).toBe(false);
    expect(after.texts.some((text) => text.includes(NOTE_FACT))).toBe(true);
  });
});

describe("locked-row principle on the platform path", () => {
  test("the mechanism is append-only promotion and create-only notes, not a locked field", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const promotion = readFileSync(join(here, "../composition/local-visible-promotion.ts"), "utf8");
    const notes = readFileSync(join(here, "stm-notes.ts"), "utf8");
    expect(promotion).toContain("alreadyCanonical");
    expect(promotion).toContain("source_provisional_revision_ids");
    expect(promotion).toContain("canonical:local-visible:");
    expect(promotion).toContain("a user-asserted fact is never silently overwritten");
    expect(notes).toContain('op.op !== "create"');
    expect(notes).toContain('write_door: "http"');
    expect(notes).toContain("The note is never quality-gated or dropped");
    const quality = readFileSync(join(here, "../../../core/extract/quality.ts"), "utf8");
    expect(quality).not.toContain("source_trust");
    expect(quality).not.toContain("user_asserted");
    expect(quality).toContain("distributional");
  });
});

describe("finalized listen conversation round trip at GET /v1/memories", () => {
  test("red-proof: accept-only finalizes listen and does not render the transcript fact", async () => {
    const { service, stores, baseUrl } = bootListen("accept-only", LISTEN_FACT);
    await captureListen(service, baseUrl);
    await waitUntil(() => stores.listen.readSession(LISTEN_ACCOUNT, LISTEN_SESSION)?.status === "completed");
    expect(service.memoryFormation.lastDrain).toBeNull();
    const rendered = await renderedMemories(service, service.devToken);
    hop("listen-rendered-red", rendered.texts);
    expect(rendered.status).toBe(200);
    expect(rendered.texts.some((text) => text.includes(LISTEN_FACT))).toBe(false);
  });

  test("wired: the transcript fact is in synthesized memory text", async () => {
    const { service, stores, baseUrl } = bootListen("wired", LISTEN_FACT);
    await captureListen(service, baseUrl);
    await waitUntil(() => stores.listen.readSession(LISTEN_ACCOUNT, LISTEN_SESSION)?.status === "completed");
    await waitUntil(() => service.memoryFormation.lastDrain !== null);
    hop("listen-producer", service.memoryFormation.lastDrain);
    const drain = await service.memoryFormation.drain({
      accountId: LISTEN_ACCOUNT,
      accountEpoch: 0,
      nowEpochSeconds: Math.floor(Date.parse("2026-08-07T12:00:00.000Z") / 1_000),
    });
    hop("listen-drain", drain);
    const rendered = await renderedMemories(service, service.devToken);
    hop("listen-rendered", rendered.texts);
    expect(rendered.status).toBe(200);
    expect(rendered.texts.some((text) => text.includes(LISTEN_FACT))).toBe(true);
  });
});
