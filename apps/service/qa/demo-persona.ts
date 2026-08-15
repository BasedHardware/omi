// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-007)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
import { createHash } from "node:crypto";
import type { Database } from "bun:sqlite";

import type { LocalServiceStores } from "../app-facing";
import type { ConversationRecord } from "../stores/conversations-store";
import type { FolderRecord } from "../stores/folders-store";
import type { ChatMessageRecord } from "../stores/chat-messages-store";
import {
  QA_FIXTURE_TIME_ANCHOR_UTC,
  qaFixtureInstant,
  seedQaSnapshot,
  type SeedMemoryContent,
} from "./seed";

/**
 * Env-gated local demo persona. Lives on the dev/QA side of the fence:
 * `bin/dev-server.ts` and tests import this module; production entrypoints
 * must not.
 *
 * Overlay is additive on the store side (extra folders, conversations, tasks,
 * chat, settings identity) and reuses `seedQaSnapshot` for memories so the
 * fixture time anchor, day math, and writer stay one machinery. Unset
 * `OMI_SEED_PERSONA` never calls this, so every seeded QA byte stays identical.
 */

export const DEMO_SEED_PERSONA = "demo" as const;
export type SeedPersona = typeof DEMO_SEED_PERSONA;

export const DEMO_PERSONA_DISPLAY_NAME = "Demo User";
export const DEMO_PERSONA_EMAIL = "";

export const parseSeedPersona = (value: string | undefined): SeedPersona | null => {
  if (value === undefined || value.length === 0) return null;
  if (value === DEMO_SEED_PERSONA) return DEMO_SEED_PERSONA;
  throw new TypeError(
    `OMI_SEED_PERSONA must be unset or "${DEMO_SEED_PERSONA}", got a different value.`,
  );
};

const memory = (
  excerpt: string,
  handle: string,
  predicate: string,
  subjectLiteral: string,
): SeedMemoryContent => Object.freeze({
  excerpt,
  handle,
  predicate,
  subject_literal: subjectLiteral,
});

/**
 * Seven distinct local days, newest at index 0. Named people and places are
 * invented for the fixture — none are the repo owner's.
 */
export const DEMO_MEMORY_CONTENTS: readonly SeedMemoryContent[] = Object.freeze([
  memory(
    "Mira Vale met Jordan Hale at Harborline Cafe to plan the Cedar Loop hike.",
    "mira-vale",
    "met Jordan Hale at the fictional Harborline Cafe to plan the Cedar Loop hike",
    "Mira Vale",
  ),
  memory(
    "Ellis Quinn reserved the Northbridge Library hold before the weekend.",
    "ellis-quinn",
    "reserved a Northbridge Library hold for a clearly fictional field guide",
    "Ellis Quinn",
  ),
  memory(
    "Jordan Hale packed rain shells for the Cedar Loop trail.",
    "jordan-hale",
    "packed rain shells for the fictional Cedar Loop trail",
    "Jordan Hale",
  ),
  memory(
    "Sable Wren sketched the Fable and Wick studio window display.",
    "sable-wren",
    "sketched the Fable and Wick studio window display on Wickwater pier",
    "Sable Wren",
  ),
  memory(
    "Nico Bram picked tomatoes at Glassfield Market.",
    "nico-bram",
    "picked tomatoes at the fictional Glassfield Market",
    "Nico Bram",
  ),
  memory(
    "Rowan Peck practiced the Harborline open-mic set.",
    "rowan-peck",
    "practiced a Harborline Cafe open-mic set with Lumen Ortiz",
    "Rowan Peck",
  ),
  memory(
    "Lumen Ortiz confirmed the Fable and Wick delivery window.",
    "lumen-ortiz",
    "confirmed the Fable and Wick delivery window with Sable Wren",
    "Lumen Ortiz",
  ),
]);

export const DEMO_PERSONA_MEMORY_COUNT = DEMO_MEMORY_CONTENTS.length;

const instantMs = (dayIndex: number, offsetMs = 0): number =>
  Date.parse(qaFixtureInstant(dayIndex)) + offsetMs;

const folder = (
  id: string,
  name: string,
  description: string,
  color: string,
  order: number,
): FolderRecord => Object.freeze({
  id,
  name,
  description,
  color,
  icon: "folder",
  created_at: qaFixtureInstant(4),
  updated_at: QA_FIXTURE_TIME_ANCHOR_UTC,
  order,
  is_default: false,
  is_system: false,
});

export const DEMO_FOLDER_SEED: readonly FolderRecord[] = Object.freeze([
  folder("weekend-plans-demo", "Weekend plans", "Fictional Saturday plans around Harborline.", "#34C759", 2),
  folder("studio-notes-demo", "Studio notes", "Notes from the fictional Fable and Wick studio.", "#AF52DE", 3),
]);

const conversation = (
  id: string,
  title: string,
  overview: string,
  folderId: string,
  dayIndex: number,
): ConversationRecord => Object.freeze({
  id,
  structured: Object.freeze({ title, overview }),
  created_at: qaFixtureInstant(dayIndex + 1),
  updated_at: qaFixtureInstant(dayIndex),
  started_at: new Date(instantMs(dayIndex, -50 * 60_000)).toISOString(),
  finished_at: qaFixtureInstant(dayIndex),
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private" as const,
  is_locked: false,
  folder_id: folderId,
});

export const DEMO_CONVERSATION_SEED: readonly ConversationRecord[] = Object.freeze([
  conversation(
    "harborline-catchup-demo",
    "Harborline Cafe catch-up",
    [
      "Mira Vale: If the weather holds, we still do Cedar Loop after lunch?",
      "Jordan Hale: Noon at Harborline Cafe. I will bring the rain shells just in case.",
      "Mira Vale: Perfect. I will text Ellis Quinn that we might be late to the Northbridge Library hold.",
    ].join("\n"),
    "weekend-plans-demo",
    0,
  ),
  conversation(
    "cedar-loop-packing-demo",
    "Cedar Loop packing",
    [
      "Jordan Hale: Rain shells, two water bottles, and the field guide Ellis reserved.",
      "Mira Vale: I can grab the field guide if you hold the table at Harborline.",
      "Jordan Hale: Deal. Meet at noon, walk the loop if the clouds stay high.",
    ].join("\n"),
    "weekend-plans-demo",
    2,
  ),
  conversation(
    "fable-wick-standup-demo",
    "Fable and Wick standup",
    [
      "Sable Wren: Window display sketch is done. Delivery window still Wednesday?",
      "Lumen Ortiz: Wednesday, before the pier market crowd.",
      "Sable Wren: I will pin the sketch next to the Wickwater crate list.",
    ].join("\n"),
    "studio-notes-demo",
    3,
  ),
]);

const taskContent = (
  description: string,
  completed: boolean,
  dueDayIndex: number,
  sortOrder: number,
  provenance: readonly string[],
  createdDayIndex: number,
): Readonly<Record<string, unknown>> => Object.freeze({
  description,
  completed,
  completedAt: completed ? instantMs(createdDayIndex, 3_600_000) : null,
  dueAt: instantMs(dueDayIndex, 15 * 3_600_000),
  owner: null,
  source: provenance.length > 0 ? "assistant" : "user",
  provenance: Object.freeze([...provenance]),
  sortOrder,
  indentLevel: 0,
  createdAt: instantMs(createdDayIndex),
  updatedAt: instantMs(createdDayIndex, completed ? 3_600_000 : 0),
});

export const DEMO_TASK_SEED: readonly {
  readonly record_id: string;
  readonly content: Readonly<Record<string, unknown>>;
}[] = Object.freeze([
  Object.freeze({
    record_id: "demo-task-harborline-text",
    content: taskContent(
      "Text Jordan Hale the Harborline Cafe table time",
      false,
      0,
      1,
      ["conversation:harborline-catchup-demo"],
      0,
    ),
  }),
  Object.freeze({
    record_id: "demo-task-cedar-shells",
    content: taskContent(
      "Pack rain shells for the Cedar Loop hike",
      false,
      0,
      2,
      ["conversation:cedar-loop-packing-demo"],
      2,
    ),
  }),
  Object.freeze({
    record_id: "demo-task-library-hold",
    content: taskContent(
      "Pick up the Northbridge Library hold for Ellis Quinn",
      false,
      1,
      3,
      ["conversation:harborline-catchup-demo"],
      1,
    ),
  }),
  Object.freeze({
    record_id: "demo-task-window-sketch",
    content: taskContent(
      "Pin the Fable and Wick window sketch next to the crate list",
      true,
      3,
      4,
      ["conversation:fable-wick-standup-demo"],
      3,
    ),
  }),
]);

const payloadHash = (text: string): string =>
  `sha256:${createHash("sha256").update(text, "utf8").digest("hex")}`;

const chatMessage = (
  id: string,
  text: string,
  sender: "human" | "ai",
  createdAt: number,
): ChatMessageRecord => Object.freeze({
  id,
  text,
  sender,
  type: "text",
  createdAt,
  updatedAt: createdAt,
  chatSessionId: null,
  appId: null,
  journalRevision: 1,
  payloadHash: payloadHash(text),
  messageSource: "chat",
  rating: null,
  reported: false,
  revision: `revision_${createHash("sha256").update(id, "utf8").digest("hex")}`,
  attachments: Object.freeze([]),
});

const DEMO_CHAT_HUMAN_TEXT =
  "Remind me what Mira Vale and Jordan Hale decided about Saturday.";
const DEMO_CHAT_AI_TEXT =
  "They picked Harborline Cafe at noon, then the fictional Cedar Loop trail if the weather holds. Ellis Quinn's Northbridge Library hold is the only thing that might make them late.";

export const DEMO_CHAT_SEED: readonly {
  readonly message: ChatMessageRecord;
  readonly generationId: string | null;
}[] = Object.freeze([
  Object.freeze({
    message: chatMessage("demo-chat-human-saturday", DEMO_CHAT_HUMAN_TEXT, "human", instantMs(0, -20 * 60_000)),
    generationId: "generation_demo_saturday",
  }),
  Object.freeze({
    message: chatMessage("demo-chat-ai-saturday", DEMO_CHAT_AI_TEXT, "ai", instantMs(0, -19 * 60_000)),
    generationId: "generation_demo_saturday",
  }),
]);

const DEMO_CHAT_GENERATION_ID = "generation_demo_saturday";

const screenBlock = (
  id: string,
  text: string,
  x: number,
  y: number,
  w: number,
  h: number,
  confidence: number,
) => Object.freeze({ id, text, x, y, w, h, confidence });

const demoFrame = (
  id: string,
  dayIndex: number,
  offsetMs: number,
  appBundleId: string,
  appName: string,
  windowTitle: string,
  fullText: string,
  blocks: readonly ReturnType<typeof screenBlock>[],
  chunkOffset: number,
) => Object.freeze({
  id,
  captured_at: new Date(instantMs(dayIndex, offsetMs)).toISOString(),
  app_bundle_id: appBundleId,
  app_name: appName,
  window_title: windowTitle,
  device_name: "Demo Mac",
  client_device_id: "demo-mac-1",
  frame_ref: Object.freeze({
    kind: "chunk" as const,
    path: `chunks/demo/${id}.hevc`,
    offset: chunkOffset,
  }),
  dhash: `demo-dhash-${id}`,
  ocr: Object.freeze({
    full_text: fullText,
    blocks,
  }),
});

export const DEMO_SCREEN_CAPTURE_SESSION_ID = "harborline-weekend-demo";

export const DEMO_SCREEN_FRAME_SEED = Object.freeze([
  demoFrame(
    "demo-screen-harborline-reservation",
    0,
    -30 * 60_000,
    "com.apple.Safari",
    "Safari",
    "Harborline Cafe — Saturday table",
    "Harborline Cafe Saturday noon table for Mira Vale and Jordan Hale.",
    Object.freeze([
      screenBlock("0", "Harborline Cafe", 0.08, 0.12, 0.4, 0.08, 0.98),
      screenBlock("1", "Saturday noon table for Mira Vale and Jordan Hale.", 0.08, 0.22, 0.7, 0.1, 0.94),
    ]),
    0,
  ),
  demoFrame(
    "demo-screen-cedar-packing",
    0,
    -10 * 60_000,
    "com.apple.Notes",
    "Notes",
    "Cedar Loop packing",
    "Pack rain shells, two water bottles, and the Northbridge Library field guide.",
    Object.freeze([
      screenBlock("0", "Pack rain shells", 0.1, 0.18, 0.5, 0.08, 0.96),
      screenBlock("1", "two water bottles, and the Northbridge Library field guide.", 0.1, 0.28, 0.72, 0.12, 0.91),
    ]),
    12_000,
  ),
  demoFrame(
    "demo-screen-fable-wick-sketch",
    3,
    -2 * 60_000,
    "com.apple.Preview",
    "Preview",
    "Fable and Wick window sketch",
    "Sable Wren pinned the Fable and Wick window sketch next to the Wickwater crate list.",
    Object.freeze([
      screenBlock("0", "Fable and Wick window sketch", 0.15, 0.2, 0.6, 0.1, 0.97),
      screenBlock("1", "Wickwater crate list", 0.15, 0.4, 0.45, 0.08, 0.93),
    ]),
    4_000,
  ),
]);

export interface DemoPersonaSeedInput {
  readonly db: Database;
  readonly stores: LocalServiceStores;
  readonly ownerAccountId: string;
  readonly accountTimezone: string;
}

/**
 * Replaces the QA memory corpus with the demo week and layers believable
 * store rows on the same owner. Called from `reseed` only when the persona
 * overlay is installed by the dev server.
 */
export const applyDemoPersonaSeed = (input: DemoPersonaSeedInput): void => {
  seedQaSnapshot(input.db, {
    owner_account_id: input.ownerAccountId,
    memory_count: DEMO_PERSONA_MEMORY_COUNT,
    account_timezone: input.accountTimezone,
    contents: DEMO_MEMORY_CONTENTS,
  });

  for (const row of DEMO_FOLDER_SEED) {
    input.stores.folders.upsert(input.ownerAccountId, row);
  }
  for (const row of DEMO_CONVERSATION_SEED) {
    const seeded = input.stores.conversations.upsert(input.ownerAccountId, row);
    if (!seeded.stored) {
      throw new TypeError(`demo conversation ${row.id} references an unknown folder`);
    }
  }
  for (const row of DEMO_TASK_SEED) {
    const applied = input.stores.tasks.apply(input.ownerAccountId, {
      op: "create",
      record_id: row.record_id,
      content: row.content,
    });
    if (!applied.applied) throw new TypeError(`demo task ${row.record_id} failed to apply`);
  }
  for (const row of DEMO_CHAT_SEED) {
    const written = input.stores.chatMessages.writeCanonical(
      input.ownerAccountId,
      row.message,
      row.generationId,
    );
    if (written.kind === "conflict" || written.kind === "invalid_vocabulary") {
      throw new TypeError(`demo chat message ${row.message.id} failed to write`);
    }
  }
  const human = input.stores.chatMessages.readMessage(
    input.ownerAccountId,
    "demo-chat-human-saturday",
  );
  const assistant = input.stores.chatMessages.readMessage(
    input.ownerAccountId,
    "demo-chat-ai-saturday",
  );
  if (human === null || assistant === null) {
    throw new TypeError("demo chat messages were not readable after write");
  }
  const accepted = input.stores.chatEvents.append({
    accountId: input.ownerAccountId,
    generationId: DEMO_CHAT_GENERATION_ID,
    eventId: "event_demo_saturday_accepted",
    createdAt: human.message.createdAt,
    frame: {
      kind: "accepted",
      message: human.message,
      generation: { id: DEMO_CHAT_GENERATION_ID },
    },
  });
  const done = input.stores.chatEvents.append({
    accountId: input.ownerAccountId,
    generationId: DEMO_CHAT_GENERATION_ID,
    eventId: "event_demo_saturday_done",
    createdAt: assistant.message.createdAt,
    frame: { kind: "done", message: assistant.message },
  });
  if (accepted.kind === "conflict" || done.kind === "conflict") {
    throw new TypeError("demo chat generation events failed to append");
  }
  input.stores.settings.putIdentity(input.ownerAccountId, {
    displayName: DEMO_PERSONA_DISPLAY_NAME,
    email: DEMO_PERSONA_EMAIL,
  });
  input.stores.screen.ingest({
    accountId: input.ownerAccountId,
    captureSessionId: DEMO_SCREEN_CAPTURE_SESSION_ID,
    frames: DEMO_SCREEN_FRAME_SEED,
  });
};
