import { rmSync } from "node:fs";
import { resolve } from "node:path";

import { AdapterRegistry } from "../dist/runtime/adapter-registry.js";
import { handleAgentControlToolCall } from "../dist/runtime/control-tools.js";
import { AgentRuntimeKernel } from "../dist/runtime/kernel.js";
import { SqliteAgentStore } from "../dist/runtime/sqlite-store.js";

const databasePath = resolve(process.argv[2] ?? "/tmp/omi-scenario-13-kernel.sqlite");
rmSync(databasePath, { force: true });

function openKernel() {
  const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
  const kernel = new AgentRuntimeKernel({
    store,
    registry: new AdapterRegistry(),
    runtimeNodeId: "scenario-13-runtime",
  });
  return { store, kernel, context: { kernel, getOwnerId: () => "scenario-13-owner" } };
}

function parse(raw) {
  const result = JSON.parse(raw);
  if (result.ok !== true) throw new Error(JSON.stringify(result.error));
  return result;
}

const evidence = [{ kind: "conversation", id: "conversation-friday", scope: "canonical" }];
const productContext = (latestEventSequence) => ({
  canonicalSummary: "The Friday date is incorporated; approval is still pending.",
  redactedCanonicalSummary: "The Friday date is incorporated; approval is still pending.",
  summarySensitivityTier: "low",
  latestEventSequence,
  currentTask: { taskId: "scenario-13-task-review", title: "Review launch email", status: "active" },
  selectedEvents: [{
    eventId: "event-friday",
    type: "conversation",
    summary: "Launch date changed to Friday",
    occurredAtMs: 1_783_676_400_000,
    evidenceRefs: evidence,
    sensitivityTier: "low",
  }],
  artifactHeads: [],
  provenance: {
    snapshotVersion: `workstream:${latestEventSequence}`,
    fetchedAtMs: Date.now(),
    source: "canonical_backend",
  },
});

const first = openKernel();
const legacySurface = {
  surfaceKind: "task_chat",
  externalRefKind: "task",
  externalRefId: "scenario-13-task-draft",
};
first.kernel.resolveSurfaceSession({ ownerId: "scenario-13-owner", surfaceRef: legacySurface });
first.kernel.importConversationTurns({
  ownerId: "scenario-13-owner",
  surfaceRef: legacySurface,
  turns: [{ role: "user", content: "Draft the launch email", createdAtMs: 1_783_669_600_000 }],
});
const prepared = parse(await handleAgentControlToolCall(first.context, "prepare_workstream_continuity", {
  workstreamId: "scenario-13-workstream",
  taskIds: ["scenario-13-task-draft", "scenario-13-task-review"],
}));
const v1 = parse(await handleAgentControlToolCall(first.context, "persist_workstream_continuity", {
  workstreamId: "scenario-13-workstream",
  context: productContext(1),
  artifacts: [{
    logicalKey: "launch-email",
    evidenceRefs: evidence,
    kind: "email_draft",
    role: "result",
    uri: "file:///tmp/omi-scenario-13-email-v1.md",
    contentHash: "sha256:scenario13-email-v1",
    sourceArtifactId: "scenario-13-source-v1",
  }],
}));
const v2 = parse(await handleAgentControlToolCall(first.context, "persist_workstream_continuity", {
  workstreamId: "scenario-13-workstream",
  context: productContext(3),
  artifacts: [{
    logicalKey: "launch-email",
    evidenceRefs: evidence,
    kind: "email_draft",
    role: "result",
    uri: "file:///tmp/omi-scenario-13-email-v2.md",
    contentHash: "sha256:scenario13-email-v2",
    sourceArtifactId: "scenario-13-source-v2",
  }],
}));
const checkpoint = v2.checkpoint;
first.store.close();

const restarted = openKernel();
const resumed = parse(await handleAgentControlToolCall(restarted.context, "prepare_workstream_continuity", {
  workstreamId: "scenario-13-workstream",
  taskIds: ["scenario-13-task-draft", "scenario-13-task-review"],
  checkpoint: {
    checkpointId: checkpoint.checkpointId,
    runtimeId: checkpoint.sourceRuntimeId,
    lastEventSequence: checkpoint.lastEventSequence,
    contextSummary: checkpoint.canonicalSummary,
    evidenceRefs: checkpoint.evidenceRefs,
    updatedAtMs: checkpoint.createdAtMs,
  },
}));
const replay = parse(await handleAgentControlToolCall(restarted.context, "persist_workstream_continuity", {
  workstreamId: "scenario-13-workstream",
  context: productContext(3),
  artifacts: [{
    logicalKey: "launch-email",
    evidenceRefs: evidence,
    kind: "email_draft",
    role: "result",
    uri: "file:///tmp/omi-scenario-13-email-v2.md",
    contentHash: "sha256:scenario13-email-v2",
    sourceArtifactId: "scenario-13-source-v2",
  }],
}));
const policy = parse(await handleAgentControlToolCall(restarted.context, "evaluate_desktop_tool_policy", {
  requestedBundles: ["external.write_send"],
  selectedBundles: ["external.write_send"],
  externalSend: true,
  operation: "send_email",
  resourceRef: "workstream:scenario-13-workstream",
}));
const versions = restarted.store.allRows(
  "SELECT logical_key, version, evidence_refs_json FROM workstream_artifact_versions ORDER BY version ASC",
);
const turns = restarted.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns");
restarted.store.close();

process.stdout.write(JSON.stringify({
  ok: true,
  workstreamId: "scenario-13-workstream",
  migratedTaskMappings: prepared.migration.migratedTaskMappings,
  copiedTurns: prepared.migration.copiedTurns,
  conversationTurnsAfterRestart: Number(turns.count),
  versions: versions.map((row) => ({
    logicalKey: String(row.logical_key),
    version: Number(row.version),
    cited: JSON.parse(String(row.evidence_refs_json)).length > 0,
  })),
  firstVersion: v1.artifactVersions[0]?.version,
  secondVersion: v2.artifactVersions[0]?.version,
  replayVersion: replay.artifactVersions[0]?.version,
  resumedSessionId: resumed.session.agentSessionId,
  queuedDeliveriesAfterRestart: resumed.deliveries.length,
  externalSendDecision: policy.policy.decision,
}, null, 2));
