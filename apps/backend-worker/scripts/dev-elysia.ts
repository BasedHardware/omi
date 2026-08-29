import { createElysiaApp } from "../src/elysia";
import type { CoreEnv } from "../src/http-core";
import { createD1Mock } from "../test/d1-mock";

const requiredEnv = (name: string): string => {
  const value = process.env[name];
  if (value === undefined || value.length === 0)
    throw new Error(`missing ${name}`);
  return value;
};

const chatLimit = Number(requiredEnv("STAGING_CHAT_LIMIT"));
if (!Number.isSafeInteger(chatLimit) || chatLimit < 0) {
  throw new Error("invalid STAGING_CHAT_LIMIT");
}

const objects = new Map<string, Uint8Array>();
const env = {
  ENVIRONMENT: requiredEnv("ENVIRONMENT"),
  API_TOKEN: requiredEnv("API_TOKEN"),
  STAGING_ACCOUNT_ID: requiredEnv("STAGING_ACCOUNT_ID"),
  STAGING_DISPLAY_NAME: requiredEnv("STAGING_DISPLAY_NAME"),
  STAGING_EMAIL: requiredEnv("STAGING_EMAIL"),
  STAGING_PLAN_LABEL: requiredEnv("STAGING_PLAN_LABEL"),
  STAGING_CHAT_LIMIT: chatLimit,
  AI_MODEL: requiredEnv("AI_MODEL"),
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
  OPENROUTER_GATEWAY_ENABLED: "false",
  OPENROUTER_MODEL: "",
  OPENROUTER_GATEWAY_URL: "",
  OPENROUTER_API_KEY: "",
  AI: { run: async () => ({ response: "" }) },
  DB: createD1Mock(),
  ATTACHMENTS: {
    async put(key: string, value: unknown) {
      const bytes =
        value instanceof Uint8Array
          ? value
          : typeof value === "string"
          ? new TextEncoder().encode(value)
          : new Uint8Array();
      objects.set(key, bytes);
      return { key, size: bytes.byteLength } as never;
    },
    async get(key: string) {
      const bytes = objects.get(key);
      if (bytes === undefined) return null;
      return {
        key,
        size: bytes.byteLength,
        arrayBuffer: async () =>
          bytes.buffer.slice(
            bytes.byteOffset,
            bytes.byteOffset + bytes.byteLength
          ),
      } as never;
    },
    async head(key: string) {
      const bytes = objects.get(key);
      return bytes === undefined
        ? null
        : ({ key, size: bytes.byteLength } as never);
    },
    async delete() {},
    async list() {
      return { objects: [], truncated: false } as never;
    },
  } as never,
  ACCOUNTS: {
    getByName: () => ({
      admit: async () => "entitlement" as const,
      cancel: async () => "not_found" as const,
      fetch: async () => new Response(null, { status: 404 }),
    }),
  },
} as CoreEnv;

const port = Number(process.env["PORT"] ?? "8787");
createElysiaApp(env).listen(port);
console.log(`elysia listening on http://127.0.0.1:${port}`);
