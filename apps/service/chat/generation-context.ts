import { isProxy } from "node:util/types";

import { parseSynthesizedPageJson } from
  "@omi-core/ratified-contracts/projections/synthesized";

import type { StoredChatMessage } from "../stores/chat-messages-store";

export type ChatGenerationMemoryContext =
  | Readonly<{
      version: "chat-generation-memory-context-v1";
      state: "loaded";
      /** Exact ratified synthesized-memory page; contains citations and completeness. */
      canonical_page_json: string;
    }>
  | Readonly<{
      version: "chat-generation-memory-context-v1";
      /** Memory was not safely available. This is never proof that no memory exists. */
      state: "unavailable";
    }>;

export interface ChatGenerationContextLoadInput {
  readonly accountId: string;
  readonly admitted: StoredChatMessage;
  /** Ephemeral request credential. A context source must never persist or return it. */
  readonly bearerToken: string;
}

export interface ChatGenerationContextSource {
  load(input: ChatGenerationContextLoadInput): Promise<ChatGenerationMemoryContext>;
}

const UNAVAILABLE_CONTEXT: ChatGenerationMemoryContext = Object.freeze({
  version: "chat-generation-memory-context-v1",
  state: "unavailable",
});

export const unavailableChatGenerationMemoryContext = (): ChatGenerationMemoryContext =>
  UNAVAILABLE_CONTEXT;

export const loadedChatGenerationMemoryContext = (
  canonicalPageJson: string,
): ChatGenerationMemoryContext => {
  if (parseSynthesizedPageJson(canonicalPageJson) === null) {
    throw new TypeError("invalid canonical Chat memory context");
  }
  return Object.freeze({
    version: "chat-generation-memory-context-v1" as const,
    state: "loaded" as const,
    canonical_page_json: canonicalPageJson,
  });
};

/** Detaches a context-source result without invoking caller-owned accessors. */
export const snapshotChatGenerationMemoryContext = (
  value: unknown,
): ChatGenerationMemoryContext | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")
    || Object.values(descriptors).some((descriptor) =>
      !descriptor.enumerable || !("value" in descriptor))) return null;
  const version = descriptors.version?.value;
  const state = descriptors.state?.value;
  if (version !== "chat-generation-memory-context-v1") return null;
  if (state === "unavailable") {
    return keys.length === 2 ? UNAVAILABLE_CONTEXT : null;
  }
  if (state !== "loaded" || keys.length !== 3
    || typeof descriptors.canonical_page_json?.value !== "string") return null;
  try {
    return loadedChatGenerationMemoryContext(descriptors.canonical_page_json.value);
  } catch {
    return null;
  }
};

/**
 * Deliberately empty adapter. The memory lane can later implement this port;
 * generation does not read or model memory storage itself.
 */
export const createEmptyChatGenerationContextSource = (): ChatGenerationContextSource =>
  Object.freeze({ load: async (): Promise<ChatGenerationMemoryContext> => UNAVAILABLE_CONTEXT });
