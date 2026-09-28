import type { Hono } from "hono";

import {
  isQaEvidenceRunId,
  type QaProducerEvidence,
} from "../observability/producer-evidence";

export const QA_EVIDENCE_PATH = "/v1/qa/evidence";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });

export interface QaEvidenceRouteDependencies {
  readonly evidence: QaProducerEvidence;
  readonly isAuthorizedControlToken: (token: string) => boolean;
}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const exactRunQuery = (rawUrl: string): string | null => {
  let parameters: URLSearchParams;
  try {
    parameters = new URL(rawUrl).searchParams;
  } catch {
    return null;
  }
  const keys = [...parameters.keys()];
  if (keys.length !== 1 || keys[0] !== "run") return null;
  const runs = parameters.getAll("run");
  return runs.length === 1 && isQaEvidenceRunId(runs[0]) ? runs[0]! : null;
};

/** Registers the counts-only producer projection on the local dev service. */
export const registerQaEvidenceRoutes = (
  app: Hono,
  deps: QaEvidenceRouteDependencies,
): void => {
  app.get(QA_EVIDENCE_PATH, (context) => {
    const token = bearerToken(context.req.header("authorization"));
    if (token === null || !deps.isAuthorizedControlToken(token)) {
      return fixedResponse(UNAUTHORIZED_BODY, 401);
    }
    const runId = exactRunQuery(context.req.url);
    if (runId === null) return fixedResponse(BAD_REQUEST_BODY, 400);
    return new Response(JSON.stringify(deps.evidence.snapshot(runId)), {
      status: 200,
      headers: JSON_HEADERS,
    });
  });
};
