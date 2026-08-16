/** One suite, every domain: the rule-12 laws executed against all fetchers. */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  fetchPlatformConversationIdSnapshot,
  fetchPlatformFolderIdSnapshot,
  fetchPlatformTaskIdSnapshot,
  fetchSynthesizedMemoryIdSnapshot,
} from "@omi-core/adapters-platform";
import { checkSnapshotConformance, type SnapshotDescriptor } from "../snapshot-conformance.js";

/**
 * `completeEvidence` is the ONLY thing that licenses `complete: true`.
 * After David's 2026-08-16 ruling retired the legacy generation, this suite
 * asserts the platform generation only. Completeness is the server's declared
 * envelope, never inferred from page fullness.
 */
const DESCRIPTORS: SnapshotDescriptor[] = [
  {
    domain: "tasks-platform",
    fetch: (http) => fetchPlatformTaskIdSnapshot(http),
    okBody: (ids) => taskEnvelope(ids.map(asPlatformTaskId)),
    completeEvidence:
      "@omi-core/ratified-contracts TaskRead: the server DECLARES coverage in a versioned completeness envelope (tasks-completeness-v1); fetchPlatformTaskIdSnapshot claims complete only when every page of a walk begun at the first page declared status:'complete' AND the walk terminated on the CompleteTerminalWindow variant within maxPages — see contracts/ratified/fixtures/tasks-read-conformance.json",
  },
  {
    domain: "memories-platform",
    fetch: (http) => fetchSynthesizedMemoryIdSnapshot(http),
    okBody: (ids) => ({
      contractVersion: "1.0.0",
      items: ids.map((id) => ({ id: `retrieval-node-v1:${id}`, text: `synthesized ${id}` })),
      window: { status: "complete", complete: true, hasMore: false, nextCursor: null },
      completeness: {
        version: "recall-completeness-v1",
        status: "complete",
        reasons: [],
        frontiers: {
          declaredFrontier: "frontier-v1:declared",
          newestSearchedAcceptedFrontier: "frontier-v1:declared",
          missingAcceptedFrontierReason: null,
          newestSearchedStmFrontier: "frontier-v1:included",
          missingStmFrontierReason: null,
        },
      },
      absence: null,
    }),
    completeEvidence:
      "@omi-core/ratified-contracts 0.1.1 SynthesizedMemoryRead: the server DECLARES coverage in a versioned completeness envelope (recall-completeness-v1) carrying declaredFrontier vs newestSearchedAcceptedFrontier and typed null reasons; fetchSynthesizedMemoryIdSnapshot claims complete only when every page of a walk begun at the first page declared status:'complete' AND the walk terminated on the CompleteTerminalWindow variant within maxPages — see contracts/ratified/fixtures/recall-completeness.json and status-matrix.json, both executed in platform-memories-adapter.test.ts",
  },
  {
    domain: "conversations-platform",
    fetch: (http) => fetchPlatformConversationIdSnapshot(http),
    okBody: (ids) => conversationEnvelope(ids),
    completeEvidence:
      "@omi-core/ratified-contracts 0.9.0 ConversationRead: the server DECLARES coverage in a versioned completeness envelope (conversations-completeness-v1) carrying declaredFrontier vs newestAppliedFrontier; fetchPlatformConversationIdSnapshot claims complete only when every page of a walk begun at the first page declared status:'complete' AND the walk terminated on the CompleteTerminalWindow variant within maxPages — see contracts/ratified/fixtures/conversations-read-conformance.json",
  },
  {
    domain: "folders-platform",
    fetch: (http) => fetchPlatformFolderIdSnapshot(http),
    okBody: (ids) => folderEnvelope(ids),
    completeEvidence:
      "@omi-core/ratified-contracts 0.9.0 FolderRead: the server DECLARES coverage in a versioned completeness envelope (folders-completeness-v1) carrying declaredFrontier vs newestAppliedFrontier; fetchPlatformFolderIdSnapshot claims complete only when every page of a walk begun at the first page declared status:'complete' AND the walk terminated on the CompleteTerminalWindow variant within maxPages — see contracts/ratified/fixtures/folders-read-conformance.json",
  },
];

test("every domain's id-snapshot fetcher obeys the rule-12 honesty laws", async () => {
  const failures = await checkSnapshotConformance(DESCRIPTORS);
  assert.deepEqual(failures, [], failures.map((f) => `${f.domain}: ${f.law} (got ${f.got})`).join("\n"));
});

/**
 * The harness must reject a descriptor that claims completeness without real
 * evidence — the mechanism failure that let the memories data-loss bug ship
 * past a green suite. Proven here rather than assumed, since this suite is now
 * the only thing standing between a wrong `complete: true` and user data loss.
 */
test("a complete-capable descriptor with no substantive evidence is rejected", async () => {
  const bare: SnapshotDescriptor = {
    domain: "fixture-bare-claim",
    fetch: async () => ({ setVersion: "x", complete: true, ids: [] }),
    okBody: (ids) => ids,
    completeEvidence: "unfiltered",
  };
  const failures = await checkSnapshotConformance([bare]);
  assert.equal(failures.length, 1, "a hand-wave must not license completeness");
  assert.match(failures[0]!.law, /completeEvidence must be a real locator or justification/);
});

test("a fetcher that claims completeness without declaring evidence is rejected", async () => {
  const undeclared: SnapshotDescriptor = {
    domain: "fixture-undeclared-complete",
    fetch: async (http) => {
      const res = await http.request("GET", "/");
      if (res.status !== 200 || !Array.isArray(res.json)) return null;
      return { setVersion: "x", complete: true, ids: res.json as string[] };
    },
    okBody: (ids) => ids,
  };
  const failures = await checkSnapshotConformance([undeclared]);
  assert.equal(failures.length, 1);
  assert.match(failures[0]!.law, /no completeEvidence declared, so complete must NEVER be true/);
});

test("declared evidence that the fetcher never honors is rejected as a dead license", async () => {
  const dead: SnapshotDescriptor = {
    domain: "fixture-dead-license",
    fetch: async (http) => {
      const res = await http.request("GET", "/");
      if (res.status !== 200 || !Array.isArray(res.json)) return null;
      return { setVersion: "x", complete: false, ids: res.json as string[] };
    },
    okBody: (ids) => ids,
    completeEvidence:
      "a plausible-looking but incorrect justification string of more than the minimum length",
  };
  const failures = await checkSnapshotConformance([dead]);
  assert.equal(failures.length, 1);
  assert.match(failures[0]!.law, /completeEvidence is declared but the fetcher never achieves complete:true/);
});

const asPlatformTaskId = (id: string): string =>
  `task1_${id.replace(/[^0-9a-f]/gi, "a").toLowerCase().padEnd(64, "a").slice(0, 64)}`;

const taskEnvelope = (ids: readonly string[]): unknown => ({
  contractVersion: "1.0.0",
  items: ids.map((id) => ({
    id,
    description: "d",
    dueAt: 1,
    completed: false,
    completedAt: null,
    createdAt: 1,
    updatedAt: 1,
    owner: "self",
    source: "assistant",
    provenance: ["assistant:summarizer-v3"],
    sortOrder: 0,
    indentLevel: 0,
    revision: "rev-1",
  })),
  window: { status: "complete", complete: true, hasMore: false, nextCursor: null },
  completeness: {
    version: "tasks-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: "vk1_declared",
      newestAppliedFrontier: "vk1_declared",
      missingAppliedFrontierReason: null,
    },
  },
  absence: ids.length === 0 ? { kind: "query_gap" } : null,
});

const conversationEnvelope = (ids: readonly string[]): unknown => ({
  contractVersion: "1.0.0",
  items: ids.map((id) => ({
    id,
    title: "t",
    overview: "o",
    createdAt: 1,
    updatedAt: 1,
    startedAt: null,
    finishedAt: null,
    source: "omi",
    status: "completed",
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: "0",
  })),
  window: { status: "complete", complete: true, hasMore: false, nextCursor: null },
  completeness: {
    version: "conversations-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: "vk1_declared",
      newestAppliedFrontier: "vk1_declared",
      missingAppliedFrontierReason: null,
    },
  },
  absence: ids.length === 0 ? { kind: "query_gap" } : null,
});

const folderEnvelope = (ids: readonly string[]): unknown => ({
  contractVersion: "1.0.0",
  items: ids.map((id) => ({
    id,
    name: "n",
    description: null,
    color: "#6B7280",
    icon: "folder",
    createdAt: 1,
    updatedAt: 1,
    order: 0,
    isDefault: false,
    isSystem: false,
    revision: null,
  })),
  window: { status: "complete", complete: true, hasMore: false, nextCursor: null },
  completeness: {
    version: "folders-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: "vk1_declared",
      newestAppliedFrontier: "vk1_declared",
      missingAppliedFrontierReason: null,
    },
  },
  absence: ids.length === 0 ? { kind: "query_gap" } : null,
});
