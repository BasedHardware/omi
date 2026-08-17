import type { Hono } from "hono";
import { isProxy } from "node:util/types";

import {
  createMemoryServiceApp,
} from "../../apps/service/memory-service-app";
import type {
  ServiceAppObservability,
  StandardFetchHandler,
} from "../../apps/service/app";
import type { ServedCounter } from "../../apps/service/observability/served-count";
import {
  createPostgresFirebaseAuthorizedMemoryReadRuntime,
  type PostgresFirebaseAuthorizedMemoryReadRuntimeOptions,
} from "./firebase-authorized-memory-read-runtime";
import { createPostgresFirebaseMemoryRouteReadPort } from
  "./firebase-memory-route-read-port";

export interface PostgresFirebaseAuthorizedMemoryServiceAppOptions {
  readonly mcp_handler: StandardFetchHandler;
  readonly memory_read: PostgresFirebaseAuthorizedMemoryReadRuntimeOptions;
  readonly now_epoch_seconds: () => number;
  readonly counter: ServedCounter;
  readonly observability?: ServiceAppObservability;
}

/**
 * Route composition only. The caller still owns the listener, secrets, MCP
 * credential implementation, telemetry sink, and deployment activation.
 */
export const createPostgresFirebaseAuthorizedMemoryServiceApp = (
  options: PostgresFirebaseAuthorizedMemoryServiceAppOptions,
): Hono => {
  if (options === null || typeof options !== "object" || Array.isArray(options)
    || isProxy(options) || Object.getPrototypeOf(options) !== Object.prototype) {
    throw new TypeError("invalid PostgreSQL Firebase memory service options");
  }
  const descriptors = Object.getOwnPropertyDescriptors(options);
  const ownKeys = Reflect.ownKeys(descriptors);
  const allowed = new Set(["mcp_handler", "memory_read", "now_epoch_seconds", "counter", "observability"]);
  if (ownKeys.some((key) => typeof key !== "string" || !allowed.has(key))
    || !["mcp_handler", "memory_read", "now_epoch_seconds", "counter"].every((key) =>
      Object.hasOwn(descriptors, key))
    || Object.values(descriptors).some((entry) => !entry.enumerable || !("value" in entry))) {
    throw new TypeError("invalid PostgreSQL Firebase memory service options");
  }
  const mcpHandler = descriptors.mcp_handler!.value;
  const nowEpochSeconds = descriptors.now_epoch_seconds!.value;
  if (typeof mcpHandler !== "function" || isProxy(mcpHandler)
    || typeof nowEpochSeconds !== "function" || isProxy(nowEpochSeconds)) {
    throw new TypeError("invalid PostgreSQL Firebase memory service options");
  }
  const runtime = createPostgresFirebaseAuthorizedMemoryReadRuntime(
    descriptors.memory_read!.value as PostgresFirebaseAuthorizedMemoryReadRuntimeOptions,
  );
  return createMemoryServiceApp(
    mcpHandler as StandardFetchHandler,
    {
      readPort: createPostgresFirebaseMemoryRouteReadPort(runtime),
      nowEpochSeconds: nowEpochSeconds as () => number,
      counter: descriptors.counter!.value as ServedCounter,
    },
    (descriptors.observability?.value ?? {}) as ServiceAppObservability,
  );
};
