import { registerTasksReadRoutes } from "./routes/tasks-read";
import { registerTasksOpsRoutes } from "./routes/tasks-ops";
import type { Hono } from "hono";

import {
  createServiceApp,
  type ServiceAppObservability,
  type StandardFetchHandler,
} from "./app";
import {
  registerMemoryRoutes,
  type MemoryRouteDependencies,
} from "./routes/memories";

/**
 * One canonical service shell for the existing REST collection and MCP door.
 * The injected ports choose credentials and storage; this root chooses no
 * production listener, deployment, or default.
 */
export const createMemoryServiceApp = (
  mcpHandler: StandardFetchHandler,
  memoryRoutes: MemoryRouteDependencies,
  observability: ServiceAppObservability = {},
  tasks?: { readonly executeRequest: (request: Request) => Promise<Response> },
  deviceSessions?: { readonly fetch: (request: Request) => Promise<Response> },
): Hono => {
  const app = createServiceApp(mcpHandler, observability);
  registerMemoryRoutes(app, memoryRoutes);
  if (tasks) {
    registerTasksReadRoutes(app, tasks);
    registerTasksOpsRoutes(app, tasks);
  }
  if (deviceSessions) {
    app.post("/v1/device-sessions", context => deviceSessions.fetch(context.req.raw));
    app.get("/v1/device-sessions/:id", context => deviceSessions.fetch(context.req.raw));
    app.post("/v1/device-sessions/:id/audio", context => deviceSessions.fetch(context.req.raw));
    app.post("/v1/device-sessions/:id/complete", context => deviceSessions.fetch(context.req.raw));
  }
  return app;
};
