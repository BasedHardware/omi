/**
 * Hermetic agent-run trace replay.
 *
 * This command reads only the supplied JSON artifact. It never creates a
 * provider client, opens a socket, reads a corpus, or touches an AgentRun
 * store. A non-zero exit means the artifact's trace or projection failed its
 * strict schema/privacy/replay checks.
 */
import { readFile } from "node:fs/promises";
import { replayAgentRunTrace } from "../apps/service/chat/agent-run-trace";

const path = process.argv[2];
if (path === undefined || process.argv.length !== 3) {
  console.error("usage: bun scripts/replay-agent-run.ts <trace.json>");
  process.exit(2);
}

try {
  const bytes = await readFile(path, "utf8");
  if (!bytes.endsWith("\n")) throw new TypeError("trace artifact must end with one newline");
  const value: unknown = JSON.parse(bytes);
  const replay = replayAgentRunTrace(value);
  console.log(JSON.stringify({
    ok: true,
    schema: replay.bundle.schema,
    schemaVersion: replay.bundle.schemaVersion,
    buildId: replay.bundle.buildId,
    runId: replay.bundle.runId,
    eventCount: replay.bundle.eventTrace.length,
    projectionDigest: replay.projectionDigest,
  }));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
