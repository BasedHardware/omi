import { Hono } from "hono";
import { SYNTHESIZED_READ_CONTRACT_VERSION } from "@omi-core/ratified-contracts/projections/synthesized";

import { AccountBackend } from "./account";
import { backendError, isChatCreate, json } from "./wire";

type WorkerEnv = Env & { API_TOKEN: string };
type Variables = { accountId: string };

const app = new Hono<{ Bindings: WorkerEnv; Variables: Variables }>({
  strict: true,
});

app.get("/health", (context) =>
  json({ status: "ok", environment: context.env.ENVIRONMENT })
);
app.get("/ready", (context) =>
  json({ status: "ready", environment: context.env.ENVIRONMENT })
);

app.use("/v1/*", async (context, next) => {
  const authorization = context.req.header("authorization");
  if (authorization === undefined || !authorization.startsWith("Bearer ")) {
    return backendError("unauthorized", "reauthenticate", 401);
  }
  const supplied = new TextEncoder().encode(
    authorization.slice("Bearer ".length)
  );
  const expected = new TextEncoder().encode(context.env.API_TOKEN);
  if (!constantTimeEqual(supplied, expected)) {
    return backendError("unauthorized", "reauthenticate", 401);
  }
  const clientId = context.req.header("x-omi-client-id");
  if (clientId === undefined || clientId.length === 0) {
    return backendError("bad_request", "edit_request", 400);
  }
  context.set("accountId", `token:${await digest(context.env.API_TOKEN)}`);
  await next();
});

app.get("/v1/chat-messages", async (context) => {
  const limit = parseLimit(context.req.query("limit"));
  if (limit === null || context.req.query("olderCursor") !== undefined) {
    return backendError("bad_request", "edit_request", 400);
  }
  return json(await account(context).history(limit));
});

app.post("/v1/chat-messages", async (context) => {
  let body: unknown;
  try {
    body = await context.req.json();
  } catch {
    return backendError("bad_request", "edit_request", 400);
  }
  if (!isChatCreate(body))
    return backendError("validation", "edit_request", 422);
  const stub = account(context);
  const admission = await stub.admit(body);
  if (admission === "conflict") {
    return backendError("client_message_id_conflict", "edit_request", 409);
  }
  if (admission.created) {
    context.executionCtx.waitUntil(
      generate(context.env, stub, admission.generation.id, body.text)
    );
  }
  return json(
    { message: admission.message, generation: admission.generation },
    admission.created ? 201 : 200
  );
});

app.get("/v1/chat-generations/:id/events", (context) => {
  const generationId = context.req.param("id");
  const target = new URL("https://account.internal/events");
  target.searchParams.set("generationId", generationId);
  return account(context).fetch(
    new Request(target, { headers: context.req.raw.headers })
  );
});

app.delete("/v1/chat-generations/:id", async (context) => {
  const cancelled = await account(context).cancel(context.req.param("id"));
  return cancelled
    ? new Response(null, { status: 202 })
    : backendError("not_found", "refresh_history", 404);
});

app.get("/v1/conversations", () => json([]));
app.get("/v1/memories", () => json(emptyPage("recall-completeness-v1")));
app.get("/v1/tasks", () => json(emptyPage("tasks-completeness-v1")));

app.notFound(() => backendError("not_found", "edit_request", 404));
app.onError((error, context) => {
  console.error(
    JSON.stringify({
      message: "request_failed",
      name: error.name,
      path: context.req.path,
    })
  );
  return backendError("internal_server_error", "retry", 500, true);
});

const handler = {
  fetch: app.fetch,
} satisfies ExportedHandler<WorkerEnv>;

export { AccountBackend };
export default handler;

function account(context: { env: WorkerEnv; get(key: "accountId"): string }) {
  return context.env.ACCOUNTS.getByName(context.get("accountId"));
}

async function digest(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value)
  );
  return [...new Uint8Array(bytes)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function constantTimeEqual(
  supplied: Uint8Array,
  expected: Uint8Array
): boolean {
  const length = Math.max(supplied.byteLength, expected.byteLength);
  let difference = supplied.byteLength ^ expected.byteLength;
  for (let index = 0; index < length; index += 1) {
    difference |= (supplied[index] ?? 0) ^ (expected[index] ?? 0);
  }
  return difference === 0;
}

function parseLimit(value: string | undefined): number | null {
  if (value === undefined) return 50;
  if (!/^(?:[1-9]|[1-9][0-9]|100)$/.test(value)) return null;
  return Number(value);
}

function emptyPage(
  completenessVersion: "recall-completeness-v1" | "tasks-completeness-v1"
) {
  return {
    contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
    items: [],
    window: {
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    },
    completeness: {
      version: completenessVersion,
      status: "complete",
      reasons: [],
      frontiers:
        completenessVersion === "tasks-completeness-v1"
          ? {
              declaredFrontier: "frontier-v1:tasks-declared",
              newestAppliedFrontier: "frontier-v1:tasks-declared",
              missingAppliedFrontierReason: null,
            }
          : {
              declaredFrontier: "frontier-v1:declared",
              newestSearchedAcceptedFrontier: null,
              missingAcceptedFrontierReason: "no_accepted_work",
              newestSearchedStmFrontier: null,
              missingStmFrontierReason: "no_eligible_stm",
            },
    },
    absence: { kind: "query_gap" },
  };
}

async function generate(
  env: WorkerEnv,
  accountStub: DurableObjectStub<AccountBackend>,
  generationId: string,
  prompt: string
): Promise<void> {
  try {
    const result = await env.AI.run(env.AI_MODEL as keyof AiModels, {
      messages: [
        {
          role: "system",
          content: "You are Omi, a concise and helpful personal assistant.",
        },
        { role: "user", content: prompt },
      ],
      max_tokens: 768,
    });
    const response = result as { response?: unknown };
    if (
      typeof response.response !== "string" ||
      response.response.length === 0
    ) {
      await accountStub.fail(generationId);
      return;
    }
    await accountStub.complete(generationId, response.response);
  } catch {
    await accountStub.fail(generationId);
  }
}
