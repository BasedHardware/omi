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
import { requestCompletedEvent, requestFailedEvent } from "./observability";
import { backendError } from "./wire";

export function createElysiaApp(env: CoreEnv): Elysia {
  const app = new Elysia({ name: "omi-v5-backend" });
  for (const route of publicRoutes) {
    mount(app, env, route, false);
  }
  for (const route of v1Routes) {
    mount(app, env, route, true);
  }
  app.onError(({ error, request }) => {
    console.error(
      JSON.stringify(
        requestFailedEvent({
          requestId: request.headers.get("x-omi-request-id") ?? "unavailable",
          name: error instanceof Error ? error.name : "Error",
          route: safeRoute(new URL(request.url).pathname),
        })
      )
    );
    return backendError("internal_server_error", "retry", 500, true);
  });
  return app.notFound(() => backendError("not_found", "edit_request", 404));
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
    if (authed) {
      const refusal = authorizeV1(context);
      if (refusal !== null) return observed(context, refusal, startedAt);
    }
    return observed(context, await route.handle(context), startedAt);
  };
  if (route.method === "GET") app.get(route.path, handler);
  else if (route.method === "POST") app.post(route.path, handler);
  else app.delete(route.path, handler);
}

function observed(
  context: CoreContext,
  response: Response,
  startedAt: number
): Response {
  const headers = new Headers(response.headers);
  headers.set("x-omi-request-id", context.get("requestId"));
  console.log(
    JSON.stringify(
      requestCompletedEvent({
        requestId: context.get("requestId") || "unavailable",
        method: context.req.method,
        route: safeRoute(context.req.routePath),
        status: response.status,
        durationMs: Math.max(0, Date.now() - startedAt),
      })
    )
  );
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
