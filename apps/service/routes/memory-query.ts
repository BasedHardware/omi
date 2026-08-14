import type { Hono } from "hono";
import { isProxy } from "node:util/types";

import {
  MEMORY_RECALL_KERNEL_VERSION,
  parseMemoryRecallKernelResponse,
  type MemoryRecallKernelResponse,
} from "../../../core/retrieve/memory-recall-kernel";
import type { IdentityExpressionAssignment } from "../../../core/retrieve/identity-expression-label";
import type { DerivedGroupRecall, DerivedGroupRecallOutcome } from
  "../composition/derived-group-recall";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";

export const MEMORY_QUERY_PATH = "/v1/memories/query";
export const MEMORY_QUERY_ROUTE_VERSION = "memory-query-route-v1" as const;

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const FORBIDDEN_BODY = JSON.stringify({ error: "forbidden" });
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

export interface MemoryQueryRouteDependencies {
  readonly recall: DerivedGroupRecall;
  readonly authorize: (
    bearerToken: string,
    nowEpochSeconds: number,
  ) => Promise<AuthorizedLedgerWriteContext | null>;
  readonly now_epoch_seconds: () => number;
  readonly build_request: (
    context: AuthorizedLedgerWriteContext,
    questionText: string,
  ) => Promise<Parameters<DerivedGroupRecall["answer"]>[1] | null>;
}

const fail = (code: string): never => { throw new TypeError(`memory query route ${code}`); };

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string") return null;
  const match = /^Bearer ([A-Za-z0-9._~+/-]+=*)$/.exec(header);
  return match?.[1] ?? null;
};

const exactDependencies = (value: unknown): MemoryQueryRouteDependencies => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependencies");
  const keys = Reflect.ownKeys(value as object);
  const expected = ["recall", "authorize", "now_epoch_seconds", "build_request"];
  if (keys.length !== expected.length || !expected.every((key) => keys.includes(key))) {
    fail("invalid_dependencies");
  }
  return value as MemoryQueryRouteDependencies;
};

const queryBody = (
  response: Readonly<MemoryRecallKernelResponse>,
  labels: readonly IdentityExpressionAssignment[],
): string => JSON.stringify({
  version: MEMORY_QUERY_ROUTE_VERSION,
  kernel_version: MEMORY_RECALL_KERNEL_VERSION,
  question_digest: response.question_digest,
  answer_text: response.answer_text,
  absence: response.absence,
  assertions: response.assertions,
  citations: response.citations,
  completeness: response.completeness,
  identity_expression_labels: labels,
  response_digest: response.response_digest,
});

/**
 * Dark versioned query door. Not mounted by `createMemoryServiceApp`.
 * Collection `GET /v1/memories` stays a list; this path never uses `?q=`.
 */
export const registerMemoryQueryRoute = (app: Hono, depsValue: MemoryQueryRouteDependencies): void => {
  const deps = exactDependencies(depsValue);
  app.get(MEMORY_QUERY_PATH, async (context) => {
    const token = bearerToken(context.req.header("authorization"));
    if (token === null) return new Response(UNAUTHORIZED_BODY, { status: 401, headers: JSON_HEADERS });
    if (context.req.query("q") !== undefined) {
      return new Response(BAD_REQUEST_BODY, { status: 400, headers: JSON_HEADERS });
    }
    const question = context.req.query("question");
    if (typeof question !== "string" || question.trim().length === 0) {
      return new Response(BAD_REQUEST_BODY, { status: 400, headers: JSON_HEADERS });
    }
    try {
      const now = deps.now_epoch_seconds();
      if (!Number.isSafeInteger(now) || now < 0) throw new TypeError("invalid clock");
      const authorized = await deps.authorize(token, now);
      if (authorized === null) {
        return new Response(UNAUTHORIZED_BODY, { status: 401, headers: JSON_HEADERS });
      }
      const request = await deps.build_request(authorized, question.trim());
      if (request === null) {
        return new Response(FORBIDDEN_BODY, { status: 403, headers: JSON_HEADERS });
      }
      const outcome: DerivedGroupRecallOutcome = await deps.recall.answer(authorized, request);
      if (outcome.kind === "stopped") {
        return new Response(INTERNAL_BODY, { status: 500, headers: JSON_HEADERS });
      }
      parseMemoryRecallKernelResponse(outcome.response);
      return new Response(queryBody(outcome.response, outcome.identity_expression_labels), {
        status: 200,
        headers: JSON_HEADERS,
      });
    } catch {
      return new Response(INTERNAL_BODY, { status: 500, headers: JSON_HEADERS });
    }
  });
};
