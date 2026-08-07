#!/usr/bin/env node
// Dependency-free codegen for the /listen realtime protocol schema.
//
// Ported from prototypes/listen-schema/codegen/generate.mjs (attribution: spike 2026-08-06)
// into core/ — TS-only output, with INV-LISTEN-006 degrade() hooks for unknown frames.
//
// Reads:  contracts/wire/listen/listen-protocol.schema.json
// Writes: packages/wire-listen/src/listen_protocol.generated.ts
//
// Node >= 18, no packages. Run: node scripts/generate.mjs [--check]
// --check exits non-zero if the committed output differs from what would be generated.
//
// Generator choice: TS-native Node script (not Python) — the prototype already proved
// this approach; Dart/Swift are out of this wave's DoD; checked-in output + --check
// matches core's committed-codegen convention.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG = resolve(HERE, "..");
const CORE = resolve(PKG, "../..");
const SCHEMA_PATH = join(CORE, "contracts", "wire", "listen", "listen-protocol.schema.json");
const TS_OUT = join(PKG, "src", "listen_protocol.generated.ts");

const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));
const defs = schema.$defs;
const proto = schema["x-omi-protocol"];
const SOURCE_LABEL = "core/contracts/wire/listen/listen-protocol.schema.json";

const entries = Object.entries(defs);
const byRole = (role) => entries.filter(([, d]) => d["x-omi-role"] === role);

const serverEvents = byRole("server-event");
const clientMessages = byRole("client-message");
const models = byRole("model");

const canonicalServerTypes = serverEvents
  .filter(([, d]) => d["x-omi-in-canonical-16"] !== false)
  .map(([, d]) => d["x-omi-event-type"]);
const canonicalClientTypes = clientMessages
  .filter(([, d]) => d["x-omi-in-canonical-4"])
  .map(([, d]) => d["x-omi-message-type"]);

function refName(ref) {
  const m = /^#\/\$defs\/(.+)$/.exec(ref);
  if (!m) throw new Error(`unsupported $ref: ${ref}`);
  return m[1];
}

function typeList(s) {
  const t = s.type;
  if (t === undefined) return [];
  return Array.isArray(t) ? t : [t];
}

function isNullable(s) {
  return typeList(s).includes("null");
}

function tsScalar(kind) {
  switch (kind) {
    case "string":
      return "string";
    case "integer":
    case "number":
      return "number";
    case "boolean":
      return "boolean";
    case "null":
      return "null";
    case "object":
      return "Record<string, unknown>";
    default:
      throw new Error(`unmapped json type: ${kind}`);
  }
}

function tsType(s) {
  if (s.$ref) {
    const name = refName(s.$ref);
    return defs[name]["x-omi-opaque"] ? "Record<string, unknown>" : name;
  }
  if (s.const !== undefined) return JSON.stringify(s.const);
  const kinds = typeList(s).filter((k) => k !== "null");
  const parts = [];
  for (const kind of kinds) {
    if (kind === "array") {
      parts.push(`${s.items ? tsType(s.items) : "unknown"}[]`);
    } else if (kind === "string" && Array.isArray(s.enum)) {
      const lits = s.enum.map((v) => JSON.stringify(v)).join(" | ");
      parts.push(s["x-omi-open-enum"] ? `${lits} | (string & {})` : lits);
    } else {
      parts.push(tsScalar(kind));
    }
  }
  if (parts.length === 0) parts.push("unknown");
  if (isNullable(s)) parts.push("null");
  return parts.join(" | ");
}

function tsInterface(name, def) {
  const req = new Set(def.required ?? []);
  const lines = [];
  if (def.description) lines.push(`/** ${def.description.replace(/\*\//g, "*\\/")} */`);
  const locator = def["x-omi-locator"];
  if (locator) lines.push(`/** Producer: ${locator} */`);
  lines.push(`export interface ${name} {`);
  for (const [prop, ps] of Object.entries(def.properties ?? {})) {
    const optional = req.has(prop) ? "" : "?";
    lines.push(`  ${JSON.stringify(prop)}${optional}: ${tsType(ps)};`);
  }
  lines.push("}");
  return lines.join("\n");
}

function requiredDataKeys(def) {
  return (def.required ?? []).filter((k) => k !== "type");
}

function generateTs() {
  const out = [];
  out.push("// GENERATED FILE — DO NOT EDIT.");
  out.push(`// Source: ${SOURCE_LABEL}`);
  out.push("// Generator: packages/wire-listen/scripts/generate.mjs");
  out.push(`// Protocol baseline: ${proto.baseline}`);
  out.push(`// Schema version: ${proto.schema_version}`);
  out.push("// Ported from prototypes/listen-schema/codegen/generate.mjs");
  out.push("");
  out.push('import type { FallbackSink, MaybeDegraded } from "@omi-core/contracts";');
  out.push('import { degrade } from "@omi-core/kernel";');
  out.push("");

  for (const [name, def] of models) {
    if (def["x-omi-opaque"]) continue;
    out.push(tsInterface(name, def), "");
  }

  out.push("// ---------------------------------------------------------- server -> client");
  out.push("");
  for (const [name, def] of serverEvents) out.push(tsInterface(name, def), "");

  out.push(`export type ListenServerEvent =\n${serverEvents.map(([n]) => `  | ${n}`).join("\n")};`);
  out.push("");
  out.push("// ---------------------------------------------------------- client -> server");
  out.push("");
  for (const [name, def] of clientMessages) out.push(tsInterface(name, def), "");
  out.push(`export type ListenClientMessage =\n${clientMessages.map(([n]) => `  | ${n}`).join("\n")};`);
  out.push("");

  out.push("// ------------------------------------------------------------------ constants");
  out.push("");
  out.push(
    `/** Canonical server->client event enum (${canonicalServerTypes.length} values). */\nexport const LISTEN_SERVER_EVENT_TYPES = ${JSON.stringify(
      canonicalServerTypes,
      null,
      2,
    )} as const;`,
  );
  out.push("");
  out.push(
    `/** Session-scoped client->server message enum (${canonicalClientTypes.length} values; the web-path \`auth\` frame is handshake-only and not counted). */\nexport const LISTEN_CLIENT_MESSAGE_TYPES = ${JSON.stringify(
      canonicalClientTypes,
      null,
      2,
    )} as const;`,
  );
  out.push("");
  const unemitted = serverEvents
    .filter(([, d]) => d["x-omi-emitted"] === false)
    .map(([, d]) => d["x-omi-event-type"]);
  out.push(
    `/** Types the schema claims but the baseline server never sends (or reserves for a future producer). */\nexport const LISTEN_RESERVED_UNEMITTED_TYPES = ${JSON.stringify(
      unemitted,
      null,
      2,
    )} as const;`,
  );
  out.push("");
  out.push("export interface ListenCloseCodeInfo {");
  out.push("  readonly code: number;");
  out.push("  readonly name: string;");
  out.push("  readonly emittedByListen: boolean;");
  out.push("  readonly clientShouldRetry: boolean;");
  out.push("  readonly meaning: string;");
  out.push("}");
  out.push("");
  const closeCodes = proto.close_codes.map((c) => ({
    code: c.code,
    name: c.name,
    emittedByListen: c.emitted_by_listen,
    clientShouldRetry: Boolean(c.client_should_retry),
    meaning: c.meaning,
  }));
  out.push(
    `export const LISTEN_CLOSE_CODES: Readonly<Record<number, ListenCloseCodeInfo>> = ${JSON.stringify(
      Object.fromEntries(closeCodes.map((c) => [c.code, c])),
      null,
      2,
    )};`,
  );
  out.push("");
  out.push("/** Retry advice for a close code, fail-open: unknown codes are treated as retryable. */");
  out.push("export function shouldRetryAfterClose(code: number): boolean {");
  out.push("  const info = LISTEN_CLOSE_CODES[code];");
  out.push("  return info ? info.clientShouldRetry : true;");
  out.push("}");
  out.push("");
  const handshakes = proto.handshakes.map((h) => ({
    id: h.id,
    path: h.path,
    authMechanism: h.auth.mechanism,
    params: h.params,
  }));
  out.push(`export const LISTEN_HANDSHAKES = ${JSON.stringify(handshakes, null, 2)} as const;`);
  out.push("");
  const paramDefs = defs.HandshakeParams.properties;
  out.push(
    `/** Canonical handshake params with server defaults — the single home the two route signatures should derive from. */\nexport const LISTEN_HANDSHAKE_PARAM_DEFAULTS = ${JSON.stringify(
      Object.fromEntries(Object.entries(paramDefs).map(([k, v]) => [k, v.default ?? null])),
      null,
      2,
    )} as const;`,
  );
  out.push("");
  out.push("// -------------------------------------------------------------------- decoding");
  out.push("");
  out.push(`export const LISTEN_HEARTBEAT_TEXT = ${JSON.stringify(defs.HeartbeatFrame.const)};`);
  out.push("");
  out.push("export type DecodedListenFrame =");
  out.push('  | { kind: "event"; event: ListenServerEvent }');
  out.push('  | { kind: "transcript_batch"; segments: TranscriptSegment[] }');
  out.push('  | { kind: "heartbeat" }');
  out.push('  | { kind: "unknown_event"; type: string; raw: Record<string, unknown> }');
  out.push('  | { kind: "invalid"; reason: InvalidFrameReason; raw: unknown };');
  out.push("");
  out.push("export type InvalidFrameReason =");
  out.push('  | "not_json"');
  out.push('  | "empty"');
  out.push('  | "no_type_field"');
  out.push('  | "missing_required_fields"');
  out.push('  | "not_an_object";');
  out.push("");
  out.push("function hasAll(obj: Record<string, unknown>, keys: readonly string[]): boolean {");
  out.push("  for (const key of keys) if (!(key in obj)) return false;");
  out.push("  return true;");
  out.push("}");
  out.push("");
  out.push(
    "/** Required non-discriminator keys per event type. A known type missing these decodes to `invalid`,\n * never to a half-built object. */",
  );
  out.push(
    `const REQUIRED_KEYS: Readonly<Record<string, readonly string[]>> = ${JSON.stringify(
      Object.fromEntries(serverEvents.map(([, d]) => [d["x-omi-event-type"], requiredDataKeys(d)])),
      null,
      2,
    )};`,
  );
  out.push("");
  out.push("/**");
  out.push(" * Decode one inbound text frame. Total: never throws, never returns undefined.");
  out.push(" * Unrecognised `type` values fail open to `unknown_event` wrapped in Degraded");
  out.push(" * (INV-LISTEN-006 — telemetry by construction via degrade()).");
  out.push(" * Binary frames are audio and are never passed here.");
  out.push(" *");
  out.push(" * `at` is an injected clock reading (Env.now()) — no wall clock in decode.");
  out.push(" */");
  out.push(
    "export function decode(sink: FallbackSink, at: number, raw: string): MaybeDegraded<DecodedListenFrame> {",
  );
  out.push('  if (raw === LISTEN_HEARTBEAT_TEXT) return { kind: "heartbeat" };');
  out.push('  if (raw === "") return { kind: "invalid", reason: "empty", raw };');
  out.push("  let json: unknown;");
  out.push("  try {");
  out.push("    json = JSON.parse(raw);");
  out.push("  } catch {");
  out.push('    return { kind: "invalid", reason: "not_json", raw };');
  out.push("  }");
  out.push("  return decodeValue(sink, at, json);");
  out.push("}");
  out.push("");
  out.push("/** Decode an already-parsed frame value (same contract as `decode`). */");
  out.push(
    "export function decodeValue(sink: FallbackSink, at: number, json: unknown): MaybeDegraded<DecodedListenFrame> {",
  );
  out.push("  if (Array.isArray(json)) {");
  out.push("    // Non-envelope frame 1: the bare transcript array.");
  out.push('    return { kind: "transcript_batch", segments: json as TranscriptSegment[] };');
  out.push("  }");
  out.push('  if (json === null || typeof json !== "object") {');
  out.push('    return { kind: "invalid", reason: "not_an_object", raw: json };');
  out.push("  }");
  out.push("  const obj = json as Record<string, unknown>;");
  out.push('  const type = obj["type"];');
  out.push('  if (typeof type !== "string") return { kind: "invalid", reason: "no_type_field", raw: obj };');
  out.push("  const required = REQUIRED_KEYS[type];");
  out.push("  if (required === undefined) {");
  out.push("    // INV-LISTEN-006: unknown frame kinds are Degraded, never a silent skip.");
  out.push("    return degrade(");
  out.push("      sink,");
  out.push("      {");
  out.push('        path: "listen.decode.unknown-frame",');
  out.push("        from: type,");
  out.push('        to: "unknown_event",');
  out.push("        detail: `unrecognized listen frame type: ${type}`,");
  out.push("        at,");
  out.push("      },");
  out.push('      { kind: "unknown_event", type, raw: obj },');
  out.push("    );");
  out.push("  }");
  out.push('  if (!hasAll(obj, required)) return { kind: "invalid", reason: "missing_required_fields", raw: obj };');
  out.push("  switch (type) {");
  for (const [name, def] of serverEvents) {
    out.push(`    case ${JSON.stringify(def["x-omi-event-type"])}:`);
    out.push(`      return { kind: "event", event: obj as unknown as ${name} };`);
  }
  out.push("    default:");
  out.push("      // Exhaustive over REQUIRED_KEYS today; still fails open (with telemetry) if the two drift.");
  out.push("      return degrade(");
  out.push("        sink,");
  out.push("        {");
  out.push('          path: "listen.decode.unknown-frame",');
  out.push("          from: type,");
  out.push('          to: "unknown_event",');
  out.push("          detail: `unrecognized listen frame type: ${type}`,");
  out.push("          at,");
  out.push("        },");
  out.push('        { kind: "unknown_event", type, raw: obj },');
  out.push("      );");
  out.push("  }");
  out.push("}");
  out.push("");
  out.push("/** Narrowing helper: exhaustiveness assertion for consumer switches. */");
  out.push("export function assertNeverListenEvent(event: never): never {");
  out.push("  throw new Error(`unhandled listen event: ${JSON.stringify(event)}`);");
  out.push("}");
  out.push("");
  return out.join("\n");
}

function emit(path, content, check) {
  const label = path.slice(CORE.length + 1);
  if (check) {
    const existing = existsSync(path) ? readFileSync(path, "utf8") : null;
    if (existing !== content) {
      console.error(`DRIFT: ${label} is stale — re-run packages/wire-listen/scripts/generate.mjs`);
      return false;
    }
    console.log(`ok: ${label}`);
    return true;
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
  console.log(`wrote ${label}`);
  return true;
}

const check = process.argv.includes("--check");
const ok = emit(TS_OUT, generateTs(), check);
if (!ok) process.exit(1);
