import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  loadedChatGenerationMemoryContext,
  unavailableChatGenerationMemoryContext,
  type ChatGenerationContextLoadInput,
  type ChatGenerationContextSource,
} from "../../apps/service/chat/generation-context";
import type { PostgresFirebaseAuthorizedMemoryReadRuntime } from
  "./firebase-authorized-memory-read-runtime";

export interface PostgresFirebaseChatGenerationContextOptions {
  readonly memory: Pick<PostgresFirebaseAuthorizedMemoryReadRuntime, "readForAccount">;
  readonly now_epoch_seconds: () => number;
}

type DataDescriptors = Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;

const exactData = (value: unknown, keys: readonly string[]): DataDescriptors | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) return null;
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) return null;
  }
  return descriptors as DataDescriptors;
};

const safeNow = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const snapshotInput = (value: unknown): Readonly<{
  account_id: string;
  bearer_token: string;
}> | null => {
  const fields = exactData(value, ["accountId", "admitted", "bearerToken"]);
  if (fields === null || !isWellFormedAccountId(fields.accountId!.value)
    || typeof fields.bearerToken!.value !== "string"
    || fields.bearerToken!.value.length < 1
    || Buffer.byteLength(fields.bearerToken!.value, "utf8") > 16_384) return null;
  // The admitted message content is deliberately not inspected here. Its
  // exact stored envelope is required, but memory authorization binds only the
  // account and the source must not turn message text into a second query.
  const admitted = exactData(fields.admitted!.value, ["message", "generationId"]);
  if (admitted === null || admitted.message!.value === null
    || typeof admitted.message!.value !== "object" || Array.isArray(admitted.message!.value)
    || isProxy(admitted.message!.value)
    || !(admitted.generationId!.value === null
      || typeof admitted.generationId!.value === "string")) return null;
  return Object.freeze({
    account_id: fields.accountId!.value,
    bearer_token: fields.bearerToken!.value,
  });
};

const snapshotReadOutcome = (value: unknown): Readonly<{
  kind: "loaded";
  canonical_json: string;
}> | Readonly<{ kind: "closed" }> => {
  const loaded = exactData(value, ["kind", "canonical_json"]);
  if (loaded?.kind!.value === "loaded" && typeof loaded.canonical_json!.value === "string") {
    return Object.freeze({ kind: "loaded", canonical_json: loaded.canonical_json!.value });
  }
  return Object.freeze({ kind: "closed" });
};

/**
 * Opt-in Chat adapter over the canonical authorized memory page read. It owns
 * no database query, model prompt, listener, or activation default.
 */
export const createPostgresFirebaseChatGenerationContextSource = (
  optionsValue: PostgresFirebaseChatGenerationContextOptions,
): ChatGenerationContextSource => {
  const options = exactData(optionsValue, ["memory", "now_epoch_seconds"]);
  if (options === null || typeof options.now_epoch_seconds!.value !== "function"
    || isProxy(options.now_epoch_seconds!.value)) {
    throw new TypeError("invalid PostgreSQL Firebase Chat memory context options");
  }
  const memory = options.memory!.value;
  if (memory === null || typeof memory !== "object" || isProxy(memory)) {
    throw new TypeError("invalid PostgreSQL Firebase Chat memory context options");
  }
  const readDescriptor = Object.getOwnPropertyDescriptor(memory, "readForAccount");
  if (!readDescriptor || !("value" in readDescriptor)
    || typeof readDescriptor.value !== "function" || isProxy(readDescriptor.value)) {
    throw new TypeError("invalid PostgreSQL Firebase Chat memory context options");
  }
  const readForAccount = readDescriptor.value as
    PostgresFirebaseAuthorizedMemoryReadRuntime["readForAccount"];
  const now = options.now_epoch_seconds!.value as () => number;

  return Object.freeze({
    async load(inputValue: ChatGenerationContextLoadInput) {
      const input = snapshotInput(inputValue);
      if (input === null) return unavailableChatGenerationMemoryContext();
      let at: unknown;
      try {
        at = Reflect.apply(now, undefined, []);
      } catch {
        return unavailableChatGenerationMemoryContext();
      }
      if (!safeNow(at)) return unavailableChatGenerationMemoryContext();
      let raw: unknown;
      try {
        raw = await Reflect.apply(readForAccount, undefined, [
          input.bearer_token,
          at,
          input.account_id,
          Object.freeze({ limit: 25, cursor: null }),
        ]);
      } catch {
        return unavailableChatGenerationMemoryContext();
      }
      const outcome = snapshotReadOutcome(raw);
      if (outcome.kind !== "loaded") return unavailableChatGenerationMemoryContext();
      try {
        return loadedChatGenerationMemoryContext(outcome.canonical_json);
      } catch {
        return unavailableChatGenerationMemoryContext();
      }
    },
  });
};
