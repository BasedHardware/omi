import {
  defineMemoryRouteReadPort,
  type MemoryRouteReadOutcome,
  type MemoryRouteReadPort,
} from "../../apps/service/routes/memory-read-port";
import type { PostgresFirebaseAuthorizedMemoryReadRuntime } from
  "./firebase-authorized-memory-read-runtime";

/** Binds the Firebase/PostgreSQL runtime to the existing public route classes. */
export const createPostgresFirebaseMemoryRouteReadPort = (
  runtime: Pick<PostgresFirebaseAuthorizedMemoryReadRuntime, "authenticate" | "read">,
): MemoryRouteReadPort => {
  if (runtime === null || typeof runtime !== "object" || isProxy(runtime)) {
    throw new TypeError("invalid PostgreSQL Firebase memory read runtime");
  }
  const authenticateDescriptor = Object.getOwnPropertyDescriptor(runtime, "authenticate");
  const descriptor = Object.getOwnPropertyDescriptor(runtime, "read");
  if (!authenticateDescriptor || !("value" in authenticateDescriptor)
    || typeof authenticateDescriptor.value !== "function" || isProxy(authenticateDescriptor.value)
    || !descriptor || !("value" in descriptor) || typeof descriptor.value !== "function"
    || isProxy(descriptor.value)) {
    throw new TypeError("invalid PostgreSQL Firebase memory read runtime");
  }
  const authenticate = authenticateDescriptor.value as PostgresFirebaseAuthorizedMemoryReadRuntime["authenticate"];
  const read = descriptor.value as PostgresFirebaseAuthorizedMemoryReadRuntime["read"];
  return defineMemoryRouteReadPort(
    async (input) => await Reflect.apply(authenticate, undefined, [
      input.bearer_token,
      input.now_epoch_seconds,
    ]),
    async (input): Promise<MemoryRouteReadOutcome> => {
  const outcome = await Reflect.apply(read, undefined, [
    input.bearer_token,
    input.now_epoch_seconds,
    input.request,
  ]);
  if (outcome.kind === "loaded") {
    return Object.freeze({ kind: "loaded", canonical_json: outcome.canonical_json });
  }
  if (outcome.kind === "invalid_cursor") {
    return Object.freeze({ kind: "invalid_cursor" });
  }
  if (outcome.kind === "denied") {
    return outcome.outcome === "authentication"
      ? Object.freeze({ kind: "authentication_denied" })
      : outcome.outcome === "authorization" || outcome.outcome === "stale_epoch"
      ? Object.freeze({ kind: "authorization_denied" })
      : Object.freeze({ kind: "unavailable" });
  }
  return Object.freeze({ kind: "unavailable" });
    },
  );
};
import { isProxy } from "node:util/types";
