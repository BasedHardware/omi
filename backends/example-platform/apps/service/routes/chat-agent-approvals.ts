import type { Hono } from "hono";

import type { DevPrincipal } from "../auth/dev-token";
import type { AgentApprovalCoordinator } from "../chat/agent-approval-coordinator";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

export interface ChatAgentApprovalRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly coordinator: AgentApprovalCoordinator;
  readonly resolveGenerationOwner: (accountId: string, runId: string) => boolean;
}

const response = (body: unknown, status: number): Response => new Response(
  JSON.stringify(body),
  { status, headers: JSON_HEADERS },
);

const unauthorized = (): Response => response({ error: { code: "unauthorized", retryable: false } }, 401);
const notFound = (): Response => response({ error: { code: "not_found", retryable: false } }, 404);
const badRequest = (): Response => response({ error: { code: "bad_request", retryable: false } }, 400);

export const registerChatAgentApprovalRoutes = (
  app: Hono,
  deps: ChatAgentApprovalRouteDependencies,
): void => {
  app.post("/v1/chat-generations/:generationId/agent-approvals", async (context) => {
    const authorization = context.req.header("authorization");
    if (authorization === undefined || !authorization.startsWith("Bearer ")) return unauthorized();
    const principal = deps.resolvePrincipal(authorization.slice("Bearer ".length));
    if (principal === null) return unauthorized();
    const runId = context.req.param("generationId");
    if (!deps.resolveGenerationOwner(principal.uid, runId)) return notFound();
    let body: unknown;
    try {
      body = await context.req.json();
    } catch {
      return badRequest();
    }
    if (body === null || typeof body !== "object" || Array.isArray(body)) return badRequest();
    const record = body as Record<string, unknown>;
    const approvalId = record.approvalId;
    const resolution = record.resolution;
    if (typeof resolution !== "string"
      || !["approved", "denied", "cancelled"].includes(resolution)
      || (approvalId !== undefined && typeof approvalId !== "string")) {
      return badRequest();
    }
    const extraKeys = Object.keys(record).filter((key) => key !== "resolution" && key !== "approvalId");
    if (extraKeys.length > 0) return badRequest();
    const outcome = await deps.coordinator.resolve({
      runId,
      ...(typeof approvalId === "string" ? { approvalId } : {}),
      resolution: resolution as "approved" | "denied" | "cancelled",
    });
    if (outcome.kind === "failed" && outcome.code === "approval_unknown") return notFound();
    return response({ outcome }, outcome.kind === "completed" ? 200 : 202);
  });
};
