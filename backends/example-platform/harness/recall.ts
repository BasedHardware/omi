import type { Database } from "bun:sqlite";
import { appendFileSync, mkdirSync } from "node:fs";
import { hostname } from "node:os";
import { basename, dirname, join } from "node:path";
import { projectTreeInputSnapshot } from "../core/retrieve";
import { retrieveAgentic, type AgenticModelPort } from "../core/retrieve/agentic";
import type { DogfoodResponse } from "../core/retrieve/dogfood";
import { SqliteLedger } from "../drivers/sqlite";

export interface CitedSpan { evidence_id: string; excerpt: string | null; capture_session_id: string }
export interface RecallAnswer extends DogfoodResponse {
  cited_spans: readonly CitedSpan[];
  agent_steps?: number;
  agent_trace?: readonly { tool: string; args: Record<string, unknown> }[];
}
export interface RecallModelPort extends AgenticModelPort {}
export interface RecallRequest {
  db: Database;
  owner_account_id: string;
  query: string;
  model: RecallModelPort;
  as_of?: string;
  account_timezone?: string;
  model_version?: string;
  /** Override log dir. Default: `recall-logs/` beside the db file (skipped for `:memory:` unless set / OMI_RECALL_LOG_DIR). */
  log_dir?: string;
}

/** Versioned JSONL path for one recall model_version. Null when there is nowhere durable to write.
 * Default sits beside the db so logs inherit the run dir's privacy: recall answers quote real
 * personal data and must never land in a tracked path. */
export const recallLogPath = (db: Database, model_version: string, log_dir?: string): string | null => {
  const dir = log_dir ?? process.env.OMI_RECALL_LOG_DIR ?? (() => {
    const file = db.filename;
    if (!file || file === ":memory:") return null;
    return join(dirname(file), "recall-logs");
  })();
  return dir ? join(dir, `${model_version}.jsonl`) : null;
};

const appendRecallLog = (path: string, record: Record<string, unknown>) => {
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${JSON.stringify(record)}\n`);
};

/** Owner recall: agentic graph tools over the live claim set, then grounded compose. */
export const answerQuestion = async (request: RecallRequest): Promise<RecallAnswer> => {
  const started = Date.now();
  const graph = new SqliteLedger(request.db).snapshot(request.owner_account_id);
  const input = projectTreeInputSnapshot(graph, {
    account_timezone: request.account_timezone ?? "UTC",
    request_context: { reader_account_id: request.owner_account_id, grant: { grant_id: "owner-recall", policy_classes: [] } },
  });
  const model_version = request.model_version ?? "agentic-recall-v2";
  const response = await retrieveAgentic({
    owner_account_id: request.owner_account_id,
    query: request.query,
    as_of: request.as_of,
    request_context: { reader_account_id: request.owner_account_id, grant: { grant_id: "owner-recall", policy_classes: [] } },
  }, graph, input, request.model, model_version);
  const spanById = new Map(input.evidence_index.map((span) => [span.evidence_id, span]));
  const answer: RecallAnswer = {
    ...response,
    cited_spans: response.citations.flatMap((evidence_id) => {
      const span = spanById.get(evidence_id);
      return span ? [{ evidence_id, excerpt: span.excerpt, capture_session_id: span.capture_session_id }] : [];
    }),
  };
  // Lightweight eval row: no evidence excerpts / tool args (those bloat + PII; ids + answer are enough to compare versions).
  const logPath = recallLogPath(request.db, model_version, request.log_dir);
  if (logPath) {
    const dbFile = request.db.filename;
    appendRecallLog(logPath, {
      schema_version: "recall_log.v3",
      recorded_at: new Date().toISOString(),
      host: hostname(),
      db: dbFile && dbFile !== ":memory:" ? basename(dbFile) : null,
      model_version,
      query: request.query,
      ms: Date.now() - started,
      answer_text: answer.answer_text,
      citations: answer.citations,
      grounded_assertion_citations: answer.assertions.map((assertion, ordinal) => ({
        ordinal,
        citations: assertion.citations,
      })),
      absence: answer.absence?.kind ?? null,
      grounding: answer.grounding?.status ?? null,
      agent_steps: answer.agent_steps ?? null,
      tools: (answer.agent_trace ?? []).map((step) => step.tool),
    });
  }
  return answer;
};
