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
): Hono => {
  const app = createServiceApp(mcpHandler, observability);
  registerMemoryRoutes(app, memoryRoutes);
  return app;
};
