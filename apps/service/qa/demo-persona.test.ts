// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-007)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMTASK-001)
import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { createLocalDevService } from "../app-facing";
import {
  applyDemoPersonaSeed,
  DEMO_PERSONA_DISPLAY_NAME,
  DEMO_PERSONA_MEMORY_COUNT,
  parseSeedPersona,
} from "./demo-persona";

const OWNER = "local-dev-user";
const TIMEZONE = "America/Los_Angeles";
const SECRET = "demo-persona-http-proof";

const boot = (overlay: boolean) => {
  const db = new Database(":memory:");
  const service = createLocalDevService({
    db,
    ownerAccountId: OWNER,
    memoryCount: overlay ? DEMO_PERSONA_MEMORY_COUNT : 12,
    accountTimezone: TIMEZONE,
    devSecretLabel: SECRET,
    listenDefaultUnmetered: true,
    ...(overlay
      ? { seedPersona: "demo" as const, overlaySeed: applyDemoPersonaSeed }
      : {}),
  });
  const request = (path: string) => service.app.request(path, {
    headers: { authorization: `Bearer ${service.devToken}` },
  });
  return { db, service, request };
};

interface RouteSnapshot {
  readonly memories: string;
  readonly tasks: { readonly items: readonly unknown[] };
  readonly conversations: readonly { readonly id: string }[];
  readonly folders: readonly { readonly id: string }[];
  readonly chat: { readonly messages: readonly unknown[] };
  readonly settings: {
    readonly identity: { readonly displayName: string; readonly email: string };
  };
  readonly screen: {
    readonly days: readonly string[];
    readonly frame_count: number;
  };
}

const snapshotRoutes = async (
  request: (path: string) => Promise<Response>,
): Promise<RouteSnapshot> => {
  const memories = await (await request("/v1/memories?limit=25")).text();
  const tasks = await (await request("/v1/tasks?limit=25")).json() as RouteSnapshot["tasks"];
  const conversations = await (await request("/v1/conversations?limit=50&offset=0")).json() as RouteSnapshot["conversations"];
  const folders = await (await request("/v1/folders")).json() as RouteSnapshot["folders"];
  const chat = await (await request("/v1/chat-messages?limit=50")).json() as RouteSnapshot["chat"];
  const settings = await (await request("/v1/settings")).json() as RouteSnapshot["settings"];
  const screen = await (await request("/v1/screen/days")).json() as RouteSnapshot["screen"];
  return { memories, tasks, conversations, folders, chat, settings, screen };
};

const assertQaSeedUnchanged = (snapshot: RouteSnapshot): void => {
  // Served memories are synthesized from claim structure, not evidence excerpts.
  // The historical QA predicate is the user-visible lock.
  if (!snapshot.memories.includes("qa_memory")) {
    throw new TypeError("QA seed lock: memories page lost the historical qa_memory predicate");
  }
  if (snapshot.memories.includes("Harborline") || snapshot.memories.includes("Mira Vale")) {
    throw new TypeError("QA seed lock: memories page contains demo persona text");
  }
  if (snapshot.conversations.map((row) => row.id).join(",") !== "quiet-chat-qa") {
    throw new TypeError("QA seed lock: conversations are not the historical QA row");
  }
  if (snapshot.folders.map((row) => row.id).join(",") !== "default-folder-qa,work-folder-qa") {
    throw new TypeError("QA seed lock: folders are not the historical QA rows");
  }
  if (snapshot.tasks.items.length !== 0) {
    throw new TypeError("QA seed lock: tasks are not empty");
  }
  if (snapshot.chat.messages.length !== 0) {
    throw new TypeError("QA seed lock: chat history is not empty");
  }
  if (snapshot.settings.identity.displayName !== OWNER || snapshot.settings.identity.email !== "") {
    throw new TypeError("QA seed lock: settings identity is not the historical QA owner");
  }
  if (snapshot.screen.frame_count !== 0 || snapshot.screen.days.length !== 0) {
    throw new TypeError("QA seed lock: screen frames are not empty");
  }
};

describe("parseSeedPersona", () => {
  test("unset and empty stay off; only demo is accepted", () => {
    expect(parseSeedPersona(undefined)).toBeNull();
    expect(parseSeedPersona("")).toBeNull();
    expect(parseSeedPersona("demo")).toBe("demo");
    expect(() => parseSeedPersona("other")).toThrow("OMI_SEED_PERSONA must be unset or \"demo\"");
  });
});

describe("QA seed unchanged without the persona overlay", () => {
  test("HTTP routes keep the historical QA seed", async () => {
    // red-proof: install overlaySeed / seedPersona demo on this boot and
    // assertQaSeedUnchanged throws (the next test proves that path).
    const { db, request } = boot(false);
    try {
      const snapshot = await snapshotRoutes(request);
      expect(() => assertQaSeedUnchanged(snapshot)).not.toThrow();
    } finally {
      db.close();
    }
  });

  test("flipping the demo persona on fails the QA-seed-unchanged assertions", async () => {
    const { db, request } = boot(true);
    try {
      const snapshot = await snapshotRoutes(request);
      expect(() => assertQaSeedUnchanged(snapshot)).toThrow(/QA seed lock:/);
    } finally {
      db.close();
    }
  });
});

describe("demo persona HTTP routes", () => {
  test("memories, tasks, conversations, folders, chat, and settings are non-empty and fictional", async () => {
    const { db, request, service } = boot(true);
    try {
      const snapshot = await snapshotRoutes(request);
      expect(snapshot.memories.includes("Mira Vale")).toBe(true);
      expect(snapshot.memories.includes("Harborline")).toBe(true);
      expect(snapshot.memories.includes("qa_memory")).toBe(false);
      expect(snapshot.conversations.length).toBeGreaterThan(1);
      expect(snapshot.conversations.some((row) => row.id === "harborline-catchup-demo")).toBe(true);
      expect(JSON.stringify(snapshot.conversations)).toContain("Cedar Loop");
      expect(snapshot.folders.some((row) => row.id === "weekend-plans-demo")).toBe(true);
      expect(snapshot.folders.some((row) => row.id === "studio-notes-demo")).toBe(true);
      expect(snapshot.tasks.items.length).toBeGreaterThan(0);
      expect(JSON.stringify(snapshot.tasks)).toContain("Harborline Cafe");
      expect(snapshot.chat.messages.length).toBeGreaterThan(0);
      expect(JSON.stringify(snapshot.chat)).toContain("Mira Vale");
      expect(snapshot.settings.identity).toEqual({
        displayName: DEMO_PERSONA_DISPLAY_NAME,
        email: "",
      });
      expect(snapshot.screen.frame_count).toBeGreaterThan(0);
      expect(JSON.stringify(snapshot.screen)).toContain("2026-08-");
      const search = await (await request("/v1/screen/search?q=Harborline")).json() as {
        readonly hits: readonly { readonly snippet: string }[];
      };
      expect(search.hits.length).toBeGreaterThan(0);
      expect(JSON.stringify(search)).toContain("Harborline");
      expect(service.seedIdentity()).toMatchObject({
        owner_account_id: OWNER,
        memory_count: DEMO_PERSONA_MEMORY_COUNT,
        persona: "demo",
      });
      const status = await (await request("/v1/qa/status")).json() as { readonly stt_engine?: string };
      expect(status.stt_engine).toBe("scripted");
    } finally {
      db.close();
    }
  });

  test("the same overlay is byte-identical across two boots", async () => {
    const first = boot(true);
    const second = boot(true);
    try {
      const left = await snapshotRoutes(first.request);
      const right = await snapshotRoutes(second.request);
      expect(right.memories).toBe(left.memories);
      expect(JSON.stringify(right.tasks)).toBe(JSON.stringify(left.tasks));
      expect(JSON.stringify(right.conversations)).toBe(JSON.stringify(left.conversations));
      expect(JSON.stringify(right.chat)).toBe(JSON.stringify(left.chat));
      expect(JSON.stringify(right.settings)).toBe(JSON.stringify(left.settings));
      expect(JSON.stringify(right.screen)).toBe(JSON.stringify(left.screen));
    } finally {
      first.db.close();
      second.db.close();
    }
  });

  test("seeded screen frames use opaque refs and never claim missing chunk files", async () => {
    // red-proof: restore kind:"chunk" path chunks/demo/${id}.hevc. This test
    // fails, and Rewind on the seeded stack shows "Frame image is not available here."
    const { db, request } = boot(true);
    try {
      const span = await (await request("/v1/screen/days")).json() as { readonly days: readonly string[] };
      const frames: Array<{ readonly id: string; readonly frame_ref: { readonly kind: string; readonly ref?: string; readonly path?: string } }> = [];
      for (const day of span.days) {
        const page = await (await request(`/v1/screen/timeline?day=${day}`)).json() as {
          readonly frames: readonly { readonly id: string; readonly frame_ref: { readonly kind: string; readonly ref?: string; readonly path?: string } }[];
        };
        frames.push(...page.frames);
      }
      expect(frames.map((frame) => frame.id).sort()).toEqual([
        "demo-screen-cedar-packing",
        "demo-screen-fable-wick-sketch",
        "demo-screen-harborline-reservation",
      ]);
      for (const frame of frames) {
        expect(frame.frame_ref).toEqual({ kind: "opaque", ref: frame.id });
      }
      expect(JSON.stringify(frames)).not.toContain("chunks/demo");
      expect(JSON.stringify(frames)).not.toContain(".hevc");
    } finally {
      db.close();
    }
  });
});

describe("persona fence", () => {
  test("production entrypoints and app-facing do not import the persona module", () => {
    const root = join(import.meta.dir, "../../..");
    const files = [
      "apps/service/app-facing.ts",
      "drivers/postgres/firebase-authorized-memory-service-process.ts",
      "drivers/postgres/firebase-authorized-memory-service-app.ts",
      "apps/mcp/bun-http.ts",
    ];
    for (const relative of files) {
      const source = readFileSync(join(root, relative), "utf8");
      expect(source.includes("demo-persona")).toBe(false);
    }
    const devServer = readFileSync(join(root, "apps/service/bin/dev-server.ts"), "utf8");
    expect(devServer.includes("qa/demo-persona")).toBe(true);
    expect(devServer.includes("OMI_SEED_PERSONA")).toBe(true);
  });
});

describe("qa status reports the live STT engine", () => {
  test("mlx-whisper is visible on /v1/qa/status when composed", async () => {
    const db = new Database(":memory:");
    const service = createLocalDevService({
      db,
      ownerAccountId: OWNER,
      memoryCount: 12,
      accountTimezone: TIMEZONE,
      devSecretLabel: SECRET,
      listenDefaultUnmetered: true,
      sttEngine: "mlx-whisper",
    });
    try {
      const status = await (await service.app.request("/v1/qa/status")).json() as {
        readonly stt_engine?: string;
      };
      expect(status.stt_engine).toBe("mlx-whisper");
    } finally {
      db.close();
    }
  });
});
