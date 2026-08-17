import { isProxy } from "node:util/types";

import type { ApplicationSynthesizedPageRequest } from
  "../../../core/retrieve/application-read";

export type MemoryRouteReadOutcome =
  | Readonly<{ kind: "loaded"; canonical_json: string }>
  | Readonly<{ kind: "authentication_denied" }>
  | Readonly<{ kind: "authorization_denied" }>
  | Readonly<{ kind: "invalid_cursor" }>
  | Readonly<{ kind: "unavailable" }>;

export interface MemoryRouteReadInput {
  readonly bearer_token: string;
  readonly now_epoch_seconds: number;
  readonly request: ApplicationSynthesizedPageRequest;
}

export interface MemoryRouteReadPort {
  readonly authenticate: (input: Readonly<{
    bearer_token: string;
    now_epoch_seconds: number;
  }>) => Promise<boolean>;
  readonly read: (input: MemoryRouteReadInput) => Promise<MemoryRouteReadOutcome>;
}

const PORT_MARKER: unique symbol = Symbol("memory-route-read-port");
type SealedMemoryRouteReadPort = MemoryRouteReadPort & { readonly [PORT_MARKER]: true };

/**
 * Seals one production-neutral page read behind the existing HTTP route.
 * Route code never imports a storage driver or credential implementation.
 */
export const defineMemoryRouteReadPort = (
  authenticate: MemoryRouteReadPort["authenticate"],
  read: MemoryRouteReadPort["read"],
): MemoryRouteReadPort => {
  if (typeof authenticate !== "function" || isProxy(authenticate)
    || typeof read !== "function" || isProxy(read)) {
    throw new TypeError("memory route read port requires non-proxy functions");
  }
  const stableAuthenticate = authenticate;
  const stableRead = read;
  return Object.freeze({
    [PORT_MARKER]: true as const,
    authenticate: (input: Readonly<{ bearer_token: string; now_epoch_seconds: number }>) =>
      Reflect.apply(stableAuthenticate, undefined, [input]),
    read: (input: MemoryRouteReadInput) => Reflect.apply(stableRead, undefined, [input]),
  }) satisfies SealedMemoryRouteReadPort;
};

export const assertMemoryRouteReadPort = (value: MemoryRouteReadPort): MemoryRouteReadPort => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("invalid memory route read port");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const marker = descriptors[PORT_MARKER];
  const authenticate = descriptors.authenticate;
  const read = descriptors.read;
  if (Reflect.ownKeys(descriptors).length !== 3
    || marker?.value !== true || marker.enumerable !== true
    || !authenticate || !authenticate.enumerable || !("value" in authenticate)
    || typeof authenticate.value !== "function" || isProxy(authenticate.value)
    || !read || !read.enumerable || !("value" in read)
    || typeof read.value !== "function" || isProxy(read.value)) {
    throw new TypeError("invalid memory route read port");
  }
  return value;
};

export const snapshotMemoryRouteReadOutcome = (
  value: unknown,
): MemoryRouteReadOutcome | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) return null;
  for (const descriptor of Object.values(descriptors)) {
    if (!descriptor.enumerable || !("value" in descriptor)) return null;
  }
  const kind = descriptors.kind?.value;
  if (kind === "loaded") {
    if (keys.length !== 2 || !Object.hasOwn(descriptors, "canonical_json")
      || typeof descriptors.canonical_json?.value !== "string") return null;
    return Object.freeze({ kind, canonical_json: descriptors.canonical_json.value });
  }
  if (kind === "authentication_denied" || kind === "authorization_denied"
    || kind === "invalid_cursor" || kind === "unavailable") {
    return keys.length === 1 ? Object.freeze({ kind }) : null;
  }
  return null;
};
