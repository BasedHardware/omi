import { Elysia } from "elysia";

import {
  authorizeV1,
  coreContext,
  publicRoutes,
  safeRoute,
  v1Routes,
  type CoreContext,
  type CoreEnv,
  type CoreRoute,
} from "./http-core";
import { logRequestCompleted, logRequestFailed } from "./observability";
import { backendError } from "./wire";

export function createElysiaApp(env: CoreEnv): Elysia {
  const app = new Elysia({ name: "omi-v5-backend" });
  for (const route of publicRoutes) {
    mount(app, env, route, false);
  }
  for (const route of v1Routes) {
    mount(app, env, route, true);
  }
  app.onError(({ error, request, code }) => {
    const requestId = crypto.randomUUID();
    const context = coreContext({
      env,
      request,
      routePath: new URL(request.url).pathname,
      params: {},
      values: { requestId },
    });
    if (code === "NOT_FOUND")
      return observed(
        context,
        backendError("not_found", "edit_request", 404),
        Date.now()
      );
    logFailure(context, error);
    return observed(
      context,
      backendError("internal_server_error", "retry", 500, true),
      Date.now()
    );
  });
  return app;
}

function mount(
  app: Elysia,
  env: CoreEnv,
  route: CoreRoute,
  authed: boolean
): void {
  const handler = async ({
    request,
    params,
  }: {
    request: Request;
    params: Record<string, string>;
  }) => {
    const requestId = crypto.randomUUID();
    const startedAt = Date.now();
    const context = coreContext({
      env,
      request,
      routePath: route.path,
      params,
      values: { requestId },
    });
    try {
      if (authed) {
        const refusal = authorizeV1(context);
        if (refusal !== null) return observed(context, refusal, startedAt);
      }
      return observed(context, await route.handle(context), startedAt);
    } catch (error) {
      logFailure(context, error);
      return observed(
        context,
        backendError("internal_server_error", "retry", 500, true),
        startedAt
      );
    }
  };
  if (route.method === "GET") app.get(route.path, handler);
  else if (route.method === "POST") app.post(route.path, handler);
  else app.delete(route.path, handler);
}

function logFailure(context: CoreContext, error: unknown): void {
  logRequestFailed({
    requestId: context.get("requestId") || "unavailable",
    name: error instanceof Error ? error.name : "Error",
    route: safeRoute(context.req.routePath),
  });
}

function observed(
  context: CoreContext,
  response: Response,
  startedAt: number
): Response {
  const headers = new Headers(response.headers);
  headers.set("x-omi-request-id", context.get("requestId"));
  logRequestCompleted({
    requestId: context.get("requestId") || "unavailable",
    method: context.req.method,
    route: safeRoute(context.req.routePath),
    status: response.status,
    durationMs: Math.max(0, Date.now() - startedAt),
  });
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
