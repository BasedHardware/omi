// Omi Provider Extension for pi-mono
//
// Responsibilities:
//   1. Register "omi" as an LLM provider using the OpenAI-compatible
//      completions API. All inference routes through the Rust desktop-backend
//      proxy for server-side cost tracking, model selection, and billing.
//   2. Install a "tool_call" handler that denies a small set of clearly
//      dangerous operations (privilege escalation, root-level deletes,
//      pipe-to-shell, destructive git, etc.) so tool execution is seamless
//      for normal work but cannot brick the user's machine on a single
//      hallucinated command.
//   3. Install a "tool_result" handler that appends every tool invocation
//      to a per-user audit log (~/.omi/pi-mono-audit.log) so we can review
//      what the agent actually ran.
//
// The classifier functions are exported so they can be unit-tested from
// plain Node (see index.test.ts). Pi's extension loader calls the default
// export with an ExtensionAPI instance; named exports are ignored by pi
// but picked up by the test runner.
//
// Issue #6594: Pi-mono harness with Omi API proxy for server-side cost control.

import {
  defineTool,
  type ExtensionAPI,
  type ToolCallEvent,
  type ToolCallEventResult,
  type ToolResultEvent,
} from "@earendil-works/pi-coding-agent";
import { Type } from "@earendil-works/pi-ai";
import { appendFile, chmod, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { createConnection, type Socket } from "node:net";
import { dirname, join, resolve } from "node:path";
import { isSafeSkillName, loadSkillInstructions, searchSkills } from "../agent/dist/runtime/node-tools.js";
import {
  isStdioServer,
  loadLocalMcpConfig,
  type UserMcpServer,
} from "../agent/dist/runtime/user-extensions.js";
import { type McpClient, type McpPrompt, type McpRemoteTool } from "../agent/dist/runtime/mcp-client.js";
import { McpHttpClient } from "../agent/dist/runtime/mcp-http-client.js";
import { McpSseClient } from "../agent/dist/runtime/mcp-sse-client.js";
import { McpStdioClient } from "../agent/dist/runtime/mcp-stdio-client.js";
import {
  buildToolAvailabilitySnapshot,
  toolNamesForAdapter,
  toolsForAdapter,
  type OmiToolInputSchema,
  type OmiToolManifestEntry,
  type OmiToolProjectionContext,
} from "../agent/dist/runtime/omi-tool-manifest.js";

/**
 * Opaque, request-scoped correlation ids are the only context forwarded to
 * the desktop backend. Keep the header bounded and printable so it is safe to
 * log, and never relay prompt text, account ids, or tool arguments.
 */
const OMI_REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

export function omiRequestIdFromRelayContext(raw: string): string | undefined {
  try {
    const parsed = JSON.parse(raw) as { requestId?: unknown };
    return typeof parsed.requestId === "string" && OMI_REQUEST_ID_PATTERN.test(parsed.requestId)
      ? parsed.requestId
      : undefined;
  } catch {
    return undefined;
  }
}

/** Per-turn effort lane. Strict allowlist — the header must never carry
 *  anything but one of these two opaque tokens. */
export function omiReasoningEffortFromRelayContext(raw: string): string | undefined {
  try {
    const parsed = JSON.parse(raw) as { reasoningEffort?: unknown };
    return parsed.reasoningEffort === "adaptive" || parsed.reasoningEffort === "fast"
      ? parsed.reasoningEffort
      : undefined;
  } catch {
    return undefined;
  }
}

export type OmiJitBudget = {
  contractVersion: string;
  executionID: string;
  maxProviderAttempts: number;
  maxOutputTokensPerAttempt: number;
  maxNormalizedInputTokensPerAttempt: number;
  maxEstimatedSpendMicroUSD: number;
};

export type OmiJitGatewayAttemptReceipt = {
  attemptID: string;
  provider: string;
  configuredModel: string;
  actualModelVersion?: string;
  providerResponseID?: string;
  rateCardID?: string;
  costBasis: string;
  usageStatus: string;
  costStatus: string;
  normalizedUncachedInputTokens: number;
  cachedInputTokens: number;
  cacheWriteTokens: number;
  outputTokens: number;
  estimatedCostMicroUSD: number | null;
};

export type OmiJitGatewayReceipt = {
  schemaVersion: "jit-gateway-receipt-v1";
  runID: string;
  contractVersion: string;
  attempts: OmiJitGatewayAttemptReceipt[];
  aggregate: {
    attemptCount: number;
    normalizedUncachedInputTokens: number;
    cachedInputTokens: number;
    cacheWriteTokens: number;
    outputTokens: number;
    estimatedCostMicroUSD: number | null;
    costStatus: string;
  };
};

function receiptString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 && value.length <= 256 ? value : undefined;
}

function receiptInteger(value: unknown, allowNull = false): number | null | undefined {
  if (allowNull && value === null) return null;
  return Number.isSafeInteger(value) && Number(value) >= 0 ? Number(value) : undefined;
}

function parseOmiJitGatewayReceipt(value: unknown): OmiJitGatewayReceipt | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const raw = value as Record<string, unknown>;
  if (raw.schema_version !== "jit-gateway-receipt-v1") return undefined;
  const runID = receiptString(raw.run_id);
  const contractVersion = receiptString(raw.contract_version);
  if (!runID || !OMI_REQUEST_ID_PATTERN.test(runID) || !contractVersion) return undefined;
  if (!Array.isArray(raw.attempts) || raw.attempts.length === 0) return undefined;
  const attempts: OmiJitGatewayAttemptReceipt[] = [];
  for (const candidate of raw.attempts) {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return undefined;
    const attempt = candidate as Record<string, unknown>;
    const normalized = receiptInteger(attempt.normalized_uncached_input_tokens);
    const cached = receiptInteger(attempt.cached_input_tokens);
    const cacheWrite = receiptInteger(attempt.cache_write_tokens);
    const output = receiptInteger(attempt.output_tokens);
    const cost = receiptInteger(attempt.estimated_cost_micro_usd, true);
    const attemptID = receiptString(attempt.attempt_id);
    const provider = receiptString(attempt.provider);
    const configuredModel = receiptString(attempt.configured_model);
    const costBasis = receiptString(attempt.cost_basis);
    const usageStatus = receiptString(attempt.usage_status);
    const costStatus = receiptString(attempt.cost_status);
    if (normalized === undefined || cached === undefined || cacheWrite === undefined || output === undefined
      || cost === undefined || !attemptID || !provider || !configuredModel || !costBasis || !usageStatus || !costStatus) {
      return undefined;
    }
    attempts.push({
      attemptID,
      provider,
      configuredModel,
      actualModelVersion: receiptString(attempt.actual_model_version),
      providerResponseID: receiptString(attempt.provider_response_id),
      rateCardID: receiptString(attempt.rate_card_id),
      costBasis,
      usageStatus,
      costStatus,
      normalizedUncachedInputTokens: normalized,
      cachedInputTokens: cached,
      cacheWriteTokens: cacheWrite,
      outputTokens: output,
      estimatedCostMicroUSD: cost,
    });
  }
  const aggregate = raw.aggregate;
  if (!aggregate || typeof aggregate !== "object" || Array.isArray(aggregate)) return undefined;
  const summary = aggregate as Record<string, unknown>;
  const attemptCount = receiptInteger(summary.attempt_count);
  const normalized = receiptInteger(summary.normalized_uncached_input_tokens);
  const cached = receiptInteger(summary.cached_input_tokens);
  const cacheWrite = receiptInteger(summary.cache_write_tokens);
  const output = receiptInteger(summary.output_tokens);
  const cost = receiptInteger(summary.estimated_cost_micro_usd, true);
  const costStatus = receiptString(summary.cost_status);
  if (attemptCount !== attempts.length || normalized === undefined || cached === undefined || cacheWrite === undefined
    || output === undefined || cost === undefined || !costStatus) return undefined;
  return {
    schemaVersion: "jit-gateway-receipt-v1",
    runID,
    contractVersion,
    attempts,
    aggregate: {
      attemptCount,
      normalizedUncachedInputTokens: normalized,
      cachedInputTokens: cached,
      cacheWriteTokens: cacheWrite,
      outputTokens: output,
      estimatedCostMicroUSD: cost,
      costStatus,
    },
  };
}

export function omiJitGatewayReceiptFromHeader(value: string | undefined): OmiJitGatewayReceipt | undefined {
  if (!value) return undefined;
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/") + "===";
    return parseOmiJitGatewayReceipt(JSON.parse(Buffer.from(normalized, "base64").toString("utf8")));
  } catch {
    return undefined;
  }
}

export function omiJitGatewayReceiptFromSSE(value: string): OmiJitGatewayReceipt | undefined {
  for (const line of value.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    try {
      const parsed = JSON.parse(line.slice(5).trim()) as { omi_jit_receipt?: unknown };
      const receipt = parseOmiJitGatewayReceipt(parsed.omi_jit_receipt);
      if (receipt) return receipt;
    } catch { /* ignore provider frames */ }
  }
  return undefined;
}

export function omiJitReceiptPathFromRelayContext(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  try {
    const value = (JSON.parse(raw) as { jitReceiptPath?: unknown }).jitReceiptPath;
    return typeof value === "string" && value.startsWith("/") && value.length <= 512 ? value : undefined;
  } catch {
    return undefined;
  }
}

type OmiJitReceiptState = {
  providerAttempts: number;
  costMicroUSD: number | null;
  invalid: boolean;
  /** Last request activity. States are retained after invalidation so an
   * unknown receipt cannot be bypassed by starting a fresh state object. */
  lastTouchedAt: number;
};

const omiJitReceiptStates = new Map<string, OmiJitReceiptState>();
let omiJitFetchGuardInstalled = false;
let omiJitUpstreamFetch: typeof globalThis.fetch | undefined;
const OMI_JIT_STATE_TTL_MS = 30 * 60 * 1_000;

function pruneExpiredOmiJitReceiptStates(now = Date.now()): void {
  for (const [executionID, state] of omiJitReceiptStates) {
    if (now - state.lastTouchedAt > OMI_JIT_STATE_TTL_MS) omiJitReceiptStates.delete(executionID);
  }
}

/** Test-only reset; the extension installs its fetch guard at most once per
 * process, while unit tests need to restore the host fetch between cases. */
export function __resetOmiJitFetchGuardForTest(): void {
  if (omiJitUpstreamFetch) globalThis.fetch = omiJitUpstreamFetch;
  omiJitUpstreamFetch = undefined;
  omiJitFetchGuardInstalled = false;
  omiJitReceiptStates.clear();
}

export function __omiJitReceiptStateCountForTest(): number {
  return omiJitReceiptStates.size;
}

function omiJitBudgetFromRequestHeaders(headers: Headers): OmiJitBudget | undefined {
  const contractVersion = headers.get("x-omi-jit-contract-version") || undefined;
  const executionID = headers.get("x-omi-jit-run-id") || undefined;
  const values = {
    maxProviderAttempts: Number(headers.get("x-omi-jit-max-attempts")),
    maxOutputTokensPerAttempt: Number(headers.get("x-omi-jit-max-output-tokens")),
    maxNormalizedInputTokensPerAttempt: Number(headers.get("x-omi-jit-max-input-tokens")),
    maxEstimatedSpendMicroUSD: Number(headers.get("x-omi-jit-max-spend-micro-usd")),
  };
  if (!contractVersion || !executionID || !OMI_REQUEST_ID_PATTERN.test(executionID)
    || !Object.values(values).every((value) => Number.isSafeInteger(value) && value > 0)) return undefined;
  return { contractVersion, executionID, ...values };
}

async function appendOmiJitReceipt(path: string | undefined, receipt: OmiJitGatewayReceipt): Promise<void> {
  if (!path) return;
  await appendFile(path, `${JSON.stringify({
    schema_version: receipt.schemaVersion,
    run_id: receipt.runID,
    contract_version: receipt.contractVersion,
    attempts: receipt.attempts.map((attempt) => ({
      attempt_id: attempt.attemptID,
      provider: attempt.provider,
      configured_model: attempt.configuredModel,
      actual_model_version: attempt.actualModelVersion,
      provider_response_id: attempt.providerResponseID,
      rate_card_id: attempt.rateCardID,
      cost_basis: attempt.costBasis,
      usage_status: attempt.usageStatus,
      cost_status: attempt.costStatus,
      normalized_uncached_input_tokens: attempt.normalizedUncachedInputTokens,
      cached_input_tokens: attempt.cachedInputTokens,
      cache_write_tokens: attempt.cacheWriteTokens,
      output_tokens: attempt.outputTokens,
      estimated_cost_micro_usd: attempt.estimatedCostMicroUSD,
    })),
    aggregate: {
      attempt_count: receipt.aggregate.attemptCount,
      normalized_uncached_input_tokens: receipt.aggregate.normalizedUncachedInputTokens,
      cached_input_tokens: receipt.aggregate.cachedInputTokens,
      cache_write_tokens: receipt.aggregate.cacheWriteTokens,
      output_tokens: receipt.aggregate.outputTokens,
      estimated_cost_micro_usd: receipt.aggregate.estimatedCostMicroUSD,
      cost_status: receipt.aggregate.costStatus,
    },
  })}\n`, "utf8");
}

/** Capture the gateway's authenticated receipt before pi-ai applies its
 * configured model rates (which intentionally remain zero). The guard also
 * enforces the run-wide ceiling across multiple tool-round HTTP requests. */
function installOmiJitFetchGuard(): void {
  if (omiJitFetchGuardInstalled || typeof globalThis.fetch !== "function") return;
  omiJitFetchGuardInstalled = true;
  const upstreamFetch = globalThis.fetch.bind(globalThis);
  omiJitUpstreamFetch = upstreamFetch;
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const requestHeaders = new Headers(input instanceof Request ? input.headers : undefined);
    if (init?.headers) new Headers(init.headers).forEach((value, key) => requestHeaders.set(key, value));
    const budget = omiJitBudgetFromRequestHeaders(requestHeaders);
    if (!budget) return upstreamFetch(input, init);
    pruneExpiredOmiJitReceiptStates();
    const state = omiJitReceiptStates.get(budget.executionID) ?? {
      providerAttempts: 0,
      costMicroUSD: 0,
      invalid: false,
      lastTouchedAt: Date.now(),
    };
    state.lastTouchedAt = Date.now();
    omiJitReceiptStates.set(budget.executionID, state);
    if (state.invalid || state.providerAttempts >= budget.maxProviderAttempts
      || (state.costMicroUSD !== null && state.costMicroUSD >= budget.maxEstimatedSpendMicroUSD)) {
      throw new Error("JIT gateway receipt missing or qualification budget exhausted");
    }
    try {
      const response = await upstreamFetch(input, init);
      let receipt = omiJitGatewayReceiptFromHeader(response.headers.get("x-omi-jit-gateway-receipt") || undefined);
      let receiptAccepted = false;
      const recordReceipt = async (candidate: OmiJitGatewayReceipt | undefined): Promise<void> => {
        const relayContext = await omiRelayContextRaw();
        if (!candidate || candidate.runID !== budget.executionID || candidate.contractVersion !== budget.contractVersion
          || candidate.aggregate.attemptCount !== candidate.attempts.length) {
          state.invalid = true;
          return;
        }
        state.providerAttempts += candidate.aggregate.attemptCount;
        if (candidate.aggregate.costStatus === "estimated"
          && Number.isSafeInteger(candidate.aggregate.estimatedCostMicroUSD)
          && Number(candidate.aggregate.estimatedCostMicroUSD) >= 0
          && state.costMicroUSD !== null) {
          state.costMicroUSD += Number(candidate.aggregate.estimatedCostMicroUSD);
        } else {
          // Unknown attribution is terminal for this execution. Retaining the
          // invalid state prevents a later tool round from spending blindly.
          state.costMicroUSD = null;
          state.invalid = true;
        }
        if (!state.invalid) receiptAccepted = true;
        await appendOmiJitReceipt(omiJitReceiptPathFromRelayContext(relayContext), candidate);
      };
      if (receipt) {
        await recordReceipt(receipt);
        return response;
      }
      if (!response.body) {
        await recordReceipt(undefined);
        return response;
      }

      // Keep the provider body byte-for-byte intact while inspecting SSE
      // frames. A clone().text() here would consume/buffer the whole stream
      // before pi-ai can receive its first delta.
      const decoder = new TextDecoder();
      let lineBuffer = "";
      let bodyReceipt: OmiJitGatewayReceipt | undefined;
      let receiptRecorded = false;
      let bodyTerminal = false;
      let bodyCancelled = false;
      const inspect = (chunk: Uint8Array, flush = false): OmiJitGatewayReceipt | undefined => {
        let newlyObserved: OmiJitGatewayReceipt | undefined;
        lineBuffer += decoder.decode(chunk, { stream: !flush });
        const lines = lineBuffer.split(/\r\n|\n|\r/);
        lineBuffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.trim() === "data: [DONE]" || line.trim() === "data:[DONE]") bodyTerminal = true;
          if (!line.startsWith("data:")) continue;
          try {
            const parsed = JSON.parse(line.slice(5).trim()) as { omi_jit_receipt?: unknown };
            const parsedReceipt = parseOmiJitGatewayReceipt(parsed.omi_jit_receipt);
            if (parsedReceipt && !bodyReceipt) {
              bodyReceipt = parsedReceipt;
              newlyObserved = parsedReceipt;
            }
          } catch { /* provider frames are not necessarily JSON */ }
        }
        if (flush && lineBuffer.startsWith("data:")) {
          if (lineBuffer.trim() === "data: [DONE]" || lineBuffer.trim() === "data:[DONE]") bodyTerminal = true;
          try {
            const parsed = JSON.parse(lineBuffer.slice(5).trim()) as { omi_jit_receipt?: unknown };
            const parsedReceipt = parseOmiJitGatewayReceipt(parsed.omi_jit_receipt);
            if (parsedReceipt && !bodyReceipt) {
              bodyReceipt = parsedReceipt;
              newlyObserved = parsedReceipt;
            }
          } catch { /* incomplete provider frame */ }
          lineBuffer = "";
        }
        return newlyObserved;
      };
      const sourceReader = response.body.getReader();
      let bodyFinalized = false;
      const finalizeBody = async (): Promise<void> => {
        if (bodyFinalized) return;
        bodyFinalized = true;
        const newlyObserved = inspect(new Uint8Array(), true);
        if (!receiptRecorded) {
          receiptRecorded = true;
          await recordReceipt(newlyObserved ?? bodyReceipt);
        }
      };
      const body = new ReadableStream<Uint8Array>({
        async pull(controller) {
          try {
            const { done, value } = await sourceReader.read();
            if (bodyCancelled) return;
            if (done) {
              await finalizeBody();
              controller.close();
              return;
            }
            const newlyObserved = inspect(value);
            // Pi may stop consuming immediately after the [DONE] frame. The
            // receipt must be durable before this chunk becomes visible so
            // the adapter can join it even when EOF is never read.
            if (newlyObserved && !receiptRecorded) {
              receiptRecorded = true;
              await recordReceipt(newlyObserved);
            }
            // Preserve the exact bytes and chunk boundaries supplied by the
            // provider; only the side-channel inspection is transformed.
            controller.enqueue(value);
          } catch (error) {
            if (bodyCancelled) return;
            state.invalid = true;
            controller.error(error);
          }
        },
        async cancel(reason) {
          // A consumer abort before EOF makes the receipt incomplete. Keep
          // the execution blocked rather than allowing a later round to spend.
          // Pi normally cancels immediately after consuming [DONE], though;
          // once that terminal marker and a validated receipt were both seen,
          // the run is complete and its known budget may continue.
          bodyCancelled = true;
          if (!(bodyTerminal && receiptAccepted)) state.invalid = true;
          await sourceReader.cancel(reason);
        },
      });
      return new Response(body, {
        status: response.status,
        statusText: response.statusText,
        headers: new Headers(response.headers),
      });
    } catch (error) {
      state.invalid = true;
      throw error;
    }
  };
}

/** Test-only entry point for the process-global fetch guard. */
export function __installOmiJitFetchGuardForTest(): void {
  installOmiJitFetchGuard();
}

export function omiJitBudgetFromRelayContext(raw: string): OmiJitBudget | undefined {
  try {
    const parsed = JSON.parse(raw) as { jitBudget?: unknown };
    const value = parsed.jitBudget;
    if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
    const budget = value as Record<string, unknown>;
    if (typeof budget.contractVersion !== "string" || !budget.contractVersion
      || typeof budget.executionID !== "string" || !OMI_REQUEST_ID_PATTERN.test(budget.executionID)) {
      return undefined;
    }
    const numericKeys = [
      "maxProviderAttempts",
      "maxOutputTokensPerAttempt",
      "maxNormalizedInputTokensPerAttempt",
      "maxEstimatedSpendMicroUSD",
    ] as const;
    if (!numericKeys.every((key) => Number.isSafeInteger(budget[key]) && Number(budget[key]) > 0)) {
      return undefined;
    }
    return {
      contractVersion: budget.contractVersion,
      executionID: budget.executionID,
      maxProviderAttempts: Number(budget.maxProviderAttempts),
      maxOutputTokensPerAttempt: Number(budget.maxOutputTokensPerAttempt),
      maxNormalizedInputTokensPerAttempt: Number(budget.maxNormalizedInputTokensPerAttempt),
      maxEstimatedSpendMicroUSD: Number(budget.maxEstimatedSpendMicroUSD),
    };
  } catch {
    return undefined;
  }
}

export type OmiBuiltInToolPolicy = "default" | "read_only";

/** Kernel-minted adapter-native authority. Unknown or malformed context fails
 * closed; only an explicit kernel-written default token enables mutation. */
export function omiBuiltInToolPolicyFromRelayContext(raw: string): OmiBuiltInToolPolicy {
  try {
    const parsed = JSON.parse(raw) as { builtInToolPolicy?: unknown };
    return parsed.builtInToolPolicy === "default" ? "default" : "read_only";
  } catch {
    return "read_only";
  }
}

async function omiRelayContextRaw(): Promise<string | undefined> {
  const contextFile = process.env.OMI_CONTEXT_FILE;
  if (!contextFile) return undefined;
  try {
    return await readFile(contextFile, "utf8");
  } catch {
    return undefined;
  }
}



// ---------------------------------------------------------------------------
// Denylist patterns
// ---------------------------------------------------------------------------

/** A single deny rule. `pattern` MUST match something clearly dangerous;
 *  `reason` is shown to the LLM so it can pick a safer alternative. */
interface DenyRule {
  pattern: RegExp;
  reason: string;
}

/** Lookahead for "end of this shell argument". Used so `/tmp` does NOT match
 *  `/` but `/` alone or `/ foo` does. */
const TARGET_END = `(?=\\s|$|[;&|'"])`;

/** Optional leading shell-quote absorber used before a DANGEROUS_TARGET.
 *  Handles bare, `"`, `'`, ANSI-C quoting (`$'...'`), and locale strings
 *  (`$"..."`), so all of `rm /etc/hosts`, `rm "/etc/hosts"`, `rm '/etc/hosts'`,
 *  `rm $'/etc/hosts'`, and `rm $"/etc/hosts"` match the same way. Closing
 *  quote is handled by TARGET_END which already accepts `'` and `"`. */
const TARGET_QUOTE = `(?:\\$['"]|['"])?`;

/** Composed pattern for "a shell argument that names a root or system-owned
 *  path, or the whole user home". Used by rm / chmod / chown rules. */
const DANGEROUS_TARGET =
  `(?:` +
  // `/` alone (root)
  `\\/${TARGET_END}` +
  // `/*` glob at root
  `|\\/\\*` +
  // `/System`, `/System/foo`, `/Library`, `/usr`, `/etc`, etc.
  `|\\/(?:System|Library|usr|etc|bin|sbin|private)(?:\\/[^\\s;&|'"]*)?${TARGET_END}` +
  // bare `~` or `~/`
  `|~\\/?${TARGET_END}` +
  // bare `$HOME` or `$HOME/`
  `|\\$HOME\\/?${TARGET_END}` +
  // `${HOME}` / `${HOME}/`
  `|\\$\\{HOME\\}\\/?${TARGET_END}` +
  // nested parent traversal (common accidental root-escape)
  `|\\.\\.\\/\\.\\.` +
  `)`;

/** Bash command denylist. Allow-by-default: only block on explicit match. */
const BASH_DENY_RULES: DenyRule[] = [
  {
    // sudo / doas / pkexec / su — at start of line, after a newline, after a
    // shell operator (`;`, `&`, `|`, backtick), or as the head of a subshell
    // (`(cmd)` or `$(cmd)`). `echo "sudo is fun"` is intentionally not blocked
    // because the `"` is not a shell-command separator.
    pattern: /(?:^|[\n;&|`(]|\$\()\s*(?:sudo|doas|pkexec|su\s)/,
    reason:
      "Privilege escalation (sudo/doas/pkexec/su) is blocked by the Omi " +
      "pi-mono denylist. Perform the operation as your current user or ask " +
      "the user to run the command manually.",
  },
  {
    // `rm` targeting a root, system, or home path — ANY flag combination
    // (short `-rf` / `-fr` / `-r -f`, long `--recursive --force`, or no flags
    // at all). A single-file `rm /etc/hosts` is just as destructive as
    // `rm -rf /etc`, so the rule blocks on target, not on flag cluster.
    // `TARGET_QUOTE` absorbs an optional leading shell quote (`"`, `'`, `$'`,
    // `$"`) so `rm "/etc/hosts"`, `rm '/etc/hosts'`, `rm $'/etc/hosts'`, and
    // `rm "$HOME"` are all caught.
    pattern: new RegExp(`\\brm\\b[^\\n]*?\\s${TARGET_QUOTE}${DANGEROUS_TARGET}`),
    reason:
      "Deleting a root or system path with `rm` is blocked. Use a specific " +
      "subdirectory under the working tree, or delete the exact file by path.",
  },
  {
    // Destructive command with command/process substitution. We cannot
    // statically evaluate `$(...)`, backticks, or `<(...)` so their target
    // is unknowable to the classifier — block them outright for rm/chmod/
    // chown so `chmod 000 "$(echo /)"` and `rm $(find / -name hosts)` cannot
    // slip past the DANGEROUS_TARGET matcher. The model is instructed to
    // resolve the substitution itself and pass a literal path instead.
    pattern: /\b(?:rm|chmod|chown)\b[^\n]*?(?:\$\(|`|<\()/,
    reason:
      "Command or process substitution ($(...), `...`, <(...)) with " +
      "rm/chmod/chown is blocked — the classifier cannot statically verify " +
      "the target is safe. Resolve the substitution yourself and pass a " +
      "literal path.",
  },
  {
    // mkfs.*, dd of=/dev/disk..., fork bomb, shred -fuv /...
    pattern:
      /\bmkfs(?:\.|\s)|\bdd\s+[^\n]*\bof=\/dev\/(?:disk|sd[a-z]|nvme|rdisk)|:\(\)\s*\{\s*:\|\s*:\s*&\s*\}\s*;\s*:|\bshred\s+[^\n]*\s\//,
    reason:
      "Low-level filesystem destruction (mkfs/dd to disk/shred/fork bomb) " +
      "is blocked.",
  },
  {
    // Shell redirect into OS paths: `> /etc/hosts`, `>> /System/...`, `> /dev/disk2`.
    // `\d*` suffixes let us match `/dev/disk2`, `/dev/sda1`, `/dev/nvme0n1`, etc.
    // `(?:\$['"]|['"])?` absorbs an optional leading shell quote (`"`, `'`,
    // `$'`, `$"`) so `> "/etc/hosts"`, `> '/etc/hosts'`, and `> $'/etc/hosts'`
    // are all blocked just like their unquoted forms.
    pattern:
      />>?\s*(?:\$['"]|['"])?\/(?:System|Library(?!\/Caches|\/Application Support\/com\.omi)|usr(?!\/local)|etc|bin|sbin|dev\/(?:disk\d*|sd[a-z]\d*|nvme\d*(?:n\d+)?|rdisk\d*|hd[a-z]\d*))\b/,
    reason:
      "Redirecting shell output into a system path (/System, /Library, " +
      "/usr, /etc, /bin, /sbin, /dev/disk*) is blocked. Use the write tool " +
      "with a path under the project or $HOME instead.",
  },
  {
    // Redirect target uses command/process substitution. `>"$(...)"`,
    // `> \`...\``, and `> <(...)` cannot be statically verified so we block
    // them outright rather than try to evaluate the substitution.
    pattern: />>?\s*['"]?(?:\$\(|`|<\()/,
    reason:
      "Redirect target uses command or process substitution — the " +
      "classifier cannot statically verify the destination is safe. Use a " +
      "literal path under the project or $HOME.",
  },
  {
    // shutdown/reboot/halt/poweroff.
    pattern: /\b(?:shutdown|reboot|halt|poweroff)\b/,
    reason:
      "Shutting down or rebooting the host is blocked. Ask the user to " +
      "restart manually if that is really what they want.",
  },
  {
    // Destructive git: force push (with any positional args before the force
    // flag, e.g. `git push origin HEAD --force`), hard reset to a remote ref.
    pattern:
      /\bgit\s+push\b[^\n]*?\s(?:-f\b|--force\b|--force-with-lease\b)|\bgit\s+reset\s+--hard\s+(?:origin\/|upstream\/|remotes\/)/,
    reason:
      "Destructive git operation (force-push, hard reset to remote) is " +
      "blocked. Create a new commit on a feature branch instead.",
  },
  {
    // curl/wget/fetch piped directly into a shell — allow an optional path
    // prefix on the shell target (`/bin/sh`, `/usr/bin/bash`, `~/bin/zsh`).
    // Still allows writing the script to a file for review first.
    pattern:
      /\b(?:curl|wget|fetch|aria2c)\b[^\n|]*\|\s*(?:[^\s|;&<>]*\/)?(?:bash|sh|zsh|fish|dash|ksh)\b/,
    reason:
      "Piping a downloaded script straight into a shell is blocked. " +
      "Download the script to a file, review it, then run it.",
  },
  {
    // launchctl touching system domain. Covers both legacy positional syntax
    // `launchctl unload system/com.x` (system/<id>) and the newer
    // `launchctl bootstrap system /Library/LaunchDaemons/x.plist` (system as
    // its own domain token followed by a service path).
    pattern:
      /\blaunchctl\s+(?:bootout|bootstrap|kickstart|unload|load|enable|disable)\s+system\b/,
    reason:
      "Modifying system launchd services is blocked. Use `launchctl ... " +
      "gui/$(id -u)/...` for the user domain if you need a LaunchAgent.",
  },
  {
    // chmod/chown on root or system-owned trees — ANY flags (`-R -v`, long
    // form, or none) before the dangerous target. `TARGET_QUOTE` absorbs an
    // optional leading shell quote (`"`, `'`, `$'`, `$"`) so
    // `chmod 000 "/"`, `chmod 000 '/'`, `chmod 000 $'/'`, and
    // `chown root "$HOME"` are all caught.
    pattern: new RegExp(
      `\\b(?:chmod|chown)\\b[^\\n]*?\\s${TARGET_QUOTE}${DANGEROUS_TARGET}`
    ),
    reason:
      "Changing permissions or ownership of a root or system path is " +
      "blocked. Apply permissions to specific files under the project tree.",
  },
  {
    // Shell redirect into SSH or cloud credential files. Mirrors the
    // WRITE_PATH_DENY_RULES entries but catches `echo ... > ~/.ssh/id_rsa`
    // style bash-only attacks that the write/edit tool denylist does not see.
    pattern:
      />>?\s*(?:[^\s|;&<>()`]*\/)?(?:\.ssh\/(?:authorized_keys|id_[^\s/;&|'"`]+)|\.aws\/credentials|\.config\/gcloud\/application_default_credentials\.json|\.kube\/config)\b/,
    reason:
      "Redirecting shell output into SSH keys (authorized_keys, id_*) or " +
      "cloud credential files (~/.aws/credentials, gcloud ADC, ~/.kube/" +
      "config) is blocked.",
  },
];

/** Write/edit path denylist. Absolute paths under OS-owned trees and
 *  well-known credential files are blocked. */
const WRITE_PATH_DENY_RULES: DenyRule[] = [
  {
    pattern: /^\/System\//,
    reason: "Writing under /System is blocked (SIP-protected OS tree).",
  },
  {
    pattern: /^\/Library\/(?!Caches\/|Application Support\/com\.omi)/,
    reason:
      "Writing under /Library is blocked except for Omi-owned subpaths. " +
      "Use ~/Library/... for user-scoped state.",
  },
  {
    pattern: /^\/usr\/(?!local\/)/,
    reason: "Writing under /usr is blocked (system binaries/libraries).",
  },
  {
    pattern: /^\/(?:private\/)?etc\//,
    reason: "Writing under /etc is blocked (system configuration).",
  },
  {
    pattern: /^\/(?:bin|sbin)\//,
    reason: "Writing under /bin or /sbin is blocked (system binaries).",
  },
  {
    pattern: /\/\.ssh\/(?:authorized_keys|id_[^/]+)$/,
    reason:
      "Writing SSH private keys or authorized_keys is blocked. Ask the " +
      "user to manage their SSH credentials manually.",
  },
  {
    pattern:
      /\/\.aws\/credentials$|\/\.config\/gcloud\/application_default_credentials\.json$|\/\.kube\/config$/,
    reason:
      "Writing cloud credential files (AWS, gcloud, kubeconfig) is blocked.",
  },
];

// ---------------------------------------------------------------------------
// Classifier functions (pure, exported for unit tests)
// ---------------------------------------------------------------------------

export interface DenyDecision {
  blocked: true;
  reason: string;
}

/** Collapse purely syntactic bash noise so multi-line or line-continued
 *  commands classify the same as their canonical single-line form. Currently
 *  this folds `\<newline>` (bash line continuation) into a single space so the
 *  redirect / target rules see `echo bad > "/etc/hosts"` whether the user
 *  wrote it on one line or split it across two. Line continuations have no
 *  semantic meaning in bash — they are purely a source-code layout tool —
 *  so this normalization cannot produce a false positive. */
function normalizeBashCommand(command: string): string {
  return command.replace(/\\\n/g, " ");
}

/** Classify a bash command. Returns null when allowed. */
export function classifyBash(command: string): DenyDecision | null {
  if (typeof command !== "string" || command.length === 0) return null;
  const normalized = normalizeBashCommand(command);
  for (const rule of BASH_DENY_RULES) {
    if (rule.pattern.test(normalized)) {
      return { blocked: true, reason: rule.reason };
    }
  }
  return null;
}

/** Classify a write/edit target path. Returns null when allowed.
 *  Resolves relative and `..` segments before matching so that
 *  `../../../../etc/hosts` is caught the same way as `/etc/hosts`. */
export function classifyFileWrite(filePath: string): DenyDecision | null {
  if (typeof filePath !== "string" || filePath.length === 0) return null;
  // Resolve to absolute to prevent ../../../etc/hosts traversal bypass
  const resolved = resolve(filePath);
  for (const rule of WRITE_PATH_DENY_RULES) {
    if (rule.pattern.test(resolved)) {
      return { blocked: true, reason: rule.reason };
    }
  }
  return null;
}

/** Classify a whole tool_call event by dispatching on toolName.
 *  When OMI_YOLO_MODE=1, the ordinary interactive denylist is bypassed.
 *  Kernel read-only authority remains mandatory in every build. */
export function inspectToolCall(
  event: ToolCallEvent,
  builtInToolPolicy: OmiBuiltInToolPolicy = "default",
): DenyDecision | null {
  if (
    builtInToolPolicy === "read_only"
    && ["bash", "write", "edit", "edit-diff"].includes(event.toolName)
  ) {
    return { blocked: true, reason: "Ask-mode service runs have read-only adapter authority" };
  }
  if (process.env.OMI_YOLO_MODE === "1") {
    process.stderr.write(`[omi-provider] YOLO bypass: ${event.toolName}\n`);
    return null;
  }
  switch (event.toolName) {
    case "bash": {
      const command = (event.input as { command?: unknown })?.command;
      return typeof command === "string" ? classifyBash(command) : null;
    }
    case "write":
    case "edit":
    case "edit-diff": {
      const path = (event.input as { path?: unknown })?.path;
      return typeof path === "string" ? classifyFileWrite(path) : null;
    }
    default:
      // read, grep, find, ls, and custom tools pass through unchanged.
      return null;
  }
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export interface AuditEntry {
  ts: string;
  phase: "before" | "after";
  tool: string;
  decision: "allow" | "deny" | "ok" | "error";
  reason?: string;
  summary: string;
}

/** One-line redacted summary of a tool-call input for the audit log. */
export function summarizeInput(event: ToolCallEvent): string {
  const { toolName, input } = event;
  try {
    switch (toolName) {
      case "bash": {
        const cmd = (input as { command?: string })?.command ?? "";
        return truncate(cmd, 200);
      }
      case "write":
      case "edit":
      case "edit-diff":
        return (input as { path?: string })?.path ?? "";
      case "read":
        return (input as { path?: string })?.path ?? "";
      case "grep":
        return truncate(
          `${(input as { pattern?: string })?.pattern ?? ""} @ ${
            (input as { path?: string })?.path ?? "."
          }`,
          200
        );
      case "find":
        return truncate(
          `${(input as { pattern?: string })?.pattern ?? ""} @ ${
            (input as { path?: string })?.path ?? "."
          }`,
          200
        );
      case "ls":
        return (input as { path?: string })?.path ?? "";
      default:
        return truncate(JSON.stringify(input ?? {}), 200);
    }
  } catch {
    return `<unserializable ${toolName} input>`;
  }
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max - 1) + "…";
}

/** Resolve the audit log path. Overridable via OMI_PI_AUDIT_LOG for tests. */
function auditLogPath(): string {
  return (
    process.env.OMI_PI_AUDIT_LOG ||
    join(process.env.HOME || homedir(), ".omi", "pi-mono-audit.log")
  );
}

let auditWarned = false;

/** Test-only: reset the `auditWarned` one-shot so tests can assert the
 *  stderr warning fires exactly once per process. Not called from
 *  production code. */
export function __resetAuditWarnedForTest(): void {
  auditWarned = false;
}

/** Append a single JSONL line to the audit log. Never throws; on failure,
 *  logs to stderr once per process so we don't flood on disk-full. Exported
 *  so the fail-safe (EACCES / ENOTDIR / disk-full) can be unit tested. */
export async function appendAudit(entry: AuditEntry): Promise<void> {
  const path = auditLogPath();
  const line = JSON.stringify(entry) + "\n";
  try {
    await mkdir(dirname(path), { recursive: true });
    // Owner-only: the log carries command text. `mode` applies at creation;
    // a file that already exists is tightened at startup by
    // restrictAuditLogPermissions.
    await appendFile(path, line, { encoding: "utf-8", mode: 0o600 });
  } catch (err) {
    if (!auditWarned) {
      auditWarned = true;
      const msg = err instanceof Error ? err.message : String(err);
      process.stderr.write(
        `[omi-provider] audit log unavailable (${msg}); continuing without audit\n`
      );
    }
  }
}

/**
 * Best-effort startup hardening: the audit log carries command text, so an
 * existing more-permissive file (written by an older build at 0644) is
 * tightened to 0600. Failures are ignored — appending is best-effort too, and
 * the 0600 create mode in appendAudit covers new files.
 */
export async function restrictAuditLogPermissions(): Promise<void> {
  try {
    await chmod(auditLogPath(), 0o600);
  } catch {
    // Missing file (nothing to harden yet) or chmod failure — never fatal.
  }
}

// ---------------------------------------------------------------------------
// Omi tools — forwarded to Swift via Unix socket (OMI_BRIDGE_PIPE)
// ---------------------------------------------------------------------------

let omiPipeConnection: Socket | null = null;
let omiPipeBuffer = "";
let omiCallIdCounter = 0;
const omiPendingCalls = new Map<string, { connection: Socket; resolve: (result: string) => void }>();

function connectOmiPipe(pipePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const connection = createConnection(pipePath, () => {
      process.stderr.write(`[omi-tools] Connected to bridge pipe\n`);
      resolve();
    });
    omiPipeConnection = connection;
    connection.on("data", (data: Buffer) => {
      omiPipeBuffer += data.toString();
      let idx;
      while ((idx = omiPipeBuffer.indexOf("\n")) >= 0) {
        const line = omiPipeBuffer.slice(0, idx);
        omiPipeBuffer = omiPipeBuffer.slice(idx + 1);
        if (line.trim()) {
          try {
            const msg = JSON.parse(line);
            if (msg.type === "tool_result" && msg.callId) {
              const pending = omiPendingCalls.get(msg.callId);
              if (pending) {
                pending.resolve(msg.result);
                omiPendingCalls.delete(msg.callId);
              }
            }
          } catch { /* ignore malformed messages */ }
        }
      }
    });
    connection.on("error", (err) => {
      process.stderr.write(`[omi-tools] Pipe error: ${err.message}\n`);
      reject(err);
    });
    // Handle pipe close — resolve all pending tool calls with an error
    // so they don't hang forever if the bridge disconnects mid-call.
    connection.on("close", () => {
      process.stderr.write("[omi-tools] Pipe disconnected\n");
      if (omiPipeConnection === connection) {
        omiPipeConnection = null;
        for (const [callId, pending] of omiPendingCalls) {
          if (pending.connection === connection) {
            pending.resolve("Error: Omi bridge disconnected");
            omiPendingCalls.delete(callId);
          }
        }
      }
    });
  });
}

async function callSwiftTool(name: string, input: Record<string, unknown>, signal?: AbortSignal, timeoutMs = OMI_TOOL_TIMEOUT_MS): Promise<string> {
  const connection: Socket | null = omiPipeConnection;
  if (!connection) return Promise.resolve("Error: not connected to Omi bridge");
  if (signal?.aborted) return Promise.resolve("Error: tool call aborted");
  const callId = `omi-ext-${++omiCallIdCounter}-${Date.now()}`;
  const capabilityRef = await omiRelayCapabilityRef();
  if (!capabilityRef) return Promise.resolve("Error: missing active Omi run capability for tool relay");
  if (signal?.aborted) return Promise.resolve("Error: tool call aborted");
  if (omiPipeConnection !== connection) return Promise.resolve("Error: Omi bridge disconnected");
  return new Promise<string>((resolve) => {
    const timer = setTimeout(() => {
      omiPendingCalls.delete(callId);
      resolve(`Error: tool '${name}' timed out after ${timeoutMs / 1000}s`);
    }, timeoutMs);
    const cleanup = () => {
      clearTimeout(timer);
      omiPendingCalls.delete(callId);
      resolve("Error: tool call aborted");
    };
    signal?.addEventListener("abort", cleanup, { once: true });
    omiPendingCalls.set(callId, {
      connection,
      resolve: (result: string) => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", cleanup);
        resolve(result);
      },
    });
    connection.write(JSON.stringify({
      type: "tool_use",
      callId,
      invocationId: callId,
      name,
      input,
      protocolVersion: 2,
      capabilityRef,
    }) + "\n");
  });
}

/**
 * Every relayed tool call used to re-read the kernel context file for its
 * capabilityRef. Cache the parsed value per process, re-validated by a cheap
 * mtime+size stat so a rewritten context is still picked up; a stat hit skips
 * the content read entirely. Keyed by path, and failures are not cached — a
 * context file being rewritten mid-read retries on the next call.
 */
let capabilityRefCache: { path: string; ref?: string; mtimeMs: number; size: number } | null = null;

async function omiRelayCapabilityRef(): Promise<string | undefined> {
  const path = process.env.OMI_CONTEXT_FILE;
  if (!path) return undefined;
  try {
    const fileStat = await stat(path);
    const cached = capabilityRefCache;
    if (cached && cached.path === path && cached.mtimeMs === fileStat.mtimeMs && cached.size === fileStat.size) {
      return cached.ref;
    }
    const parsed = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    const ref =
      typeof parsed.capabilityRef === "string" && parsed.capabilityRef.length > 0
        ? parsed.capabilityRef
        : undefined;
    capabilityRefCache = { path, ref, mtimeMs: fileStat.mtimeMs, size: fileStat.size };
    return ref;
  } catch {
    return undefined;
  }
}

export const OMI_TOOL_TIMEOUT_MS = 30_000;
export const OMI_LONG_CONTROL_TOOL_TIMEOUT_MS = 10 * 60_000;
export const OMI_CHAT_CONTRACT_VERSION = "1";

export function applyOmiProviderHeaders(
  headers: Record<string, string>,
  relayContextRaw: string | undefined,
): void {
  headers["x-omi-chat-contract-version"] = OMI_CHAT_CONTRACT_VERSION;
  if (relayContextRaw === undefined) return;
  const requestId = omiRequestIdFromRelayContext(relayContextRaw);
  if (requestId) headers["x-omi-request-id"] = requestId;
  const reasoningEffort = omiReasoningEffortFromRelayContext(relayContextRaw);
  if (reasoningEffort) headers["x-omi-reasoning-effort"] = reasoningEffort;
  const jitBudget = omiJitBudgetFromRelayContext(relayContextRaw);
  if (jitBudget) {
    headers["x-omi-jit-contract-version"] = jitBudget.contractVersion;
    headers["x-omi-jit-run-id"] = jitBudget.executionID;
    headers["x-omi-jit-max-attempts"] = String(jitBudget.maxProviderAttempts);
    headers["x-omi-jit-max-output-tokens"] = String(jitBudget.maxOutputTokensPerAttempt);
    headers["x-omi-jit-max-input-tokens"] = String(jitBudget.maxNormalizedInputTokensPerAttempt);
    headers["x-omi-jit-max-spend-micro-usd"] = String(jitBudget.maxEstimatedSpendMicroUSD);
  }
}

export { isSafeSkillName };

// ---------------------------------------------------------------------------
// Omi tool definitions — pi-mono defineTool() with TypeBox schemas
// ---------------------------------------------------------------------------

/** Factory: create a defineTool()-compliant Omi tool that forwards to Swift. */
function omiTool<T extends Parameters<typeof Type.Object>[0]>(spec: {
  name: string;
  label: string;
  description: string;
  promptSnippet: string;
  promptGuidelines?: string[];
  properties: T;
  required: (keyof T)[];
  timeoutMs?: number;
}) {
  const parameters = Type.Object(
    spec.properties,
    { additionalProperties: false },
  );
  const tool = defineTool({
    name: spec.name,
    label: spec.label,
    description: spec.description,
    promptSnippet: spec.promptSnippet,
    promptGuidelines: spec.promptGuidelines,
    parameters,
    async execute(_toolCallId, params, signal) {
      const result = await callSwiftTool(spec.name, params as Record<string, unknown>, signal, spec.timeoutMs);
      return { content: [{ type: "text" as const, text: result }], details: undefined };
    },
  });
  Object.defineProperty(tool, "__omiTimeoutMsForTest", {
    value: spec.timeoutMs ?? OMI_TOOL_TIMEOUT_MS,
    enumerable: false,
  });
  return tool;
}

function typeBoxSchemaForJsonSchema(schema: Record<string, unknown>): unknown {
  const options: Record<string, unknown> = {};
  if (typeof schema.description === "string") options.description = schema.description;
  if (Array.isArray(schema.enum)) options.enum = schema.enum;
  switch (schema.type) {
    case "string":
      return Type.String(options);
    case "number":
    case "integer":
      return Type.Number(options);
    case "boolean":
      return Type.Boolean(options);
    case "array": {
      const itemSchema = schema.items && typeof schema.items === "object"
        ? typeBoxSchemaForJsonSchema(schema.items as Record<string, unknown>)
        : Type.Unknown();
      return Type.Array(itemSchema as never, options);
    }
    case "object": {
      const properties = typeof schema.properties === "object" && schema.properties
        ? typeBoxPropertiesForInputSchema({
            type: "object",
            properties: schema.properties as Record<string, unknown>,
            required: Array.isArray(schema.required) ? schema.required as string[] : [],
            additionalProperties: schema.additionalProperties === true,
          })
        : {};
      return Type.Object(properties, { ...options, additionalProperties: schema.additionalProperties === true });
    }
    default:
      return Type.Unknown(options);
  }
}

function typeBoxPropertiesForInputSchema(tool: OmiToolInputSchema): Parameters<typeof Type.Object>[0] {
  const required = new Set(tool.required ?? []);
  return Object.fromEntries(
    Object.entries(tool.properties).map(([name, property]) => {
      const schema = typeBoxSchemaForJsonSchema(property as Record<string, unknown>);
      return [name, required.has(name) ? schema : Type.Optional(schema as never)];
    })
  ) as Parameters<typeof Type.Object>[0];
}

function omiManifestTool(tool: OmiToolManifestEntry) {
  return omiTool({
    name: tool.name,
    label: tool.label,
    description: tool.description,
    promptSnippet: tool.promptSnippet,
    promptGuidelines: tool.promptGuidelines,
    properties: typeBoxPropertiesForInputSchema(tool.inputSchema),
    required: (tool.inputSchema.required ?? []) as never[],
    timeoutMs: tool.timeoutClass === "long" ? OMI_LONG_CONTROL_TOOL_TIMEOUT_MS : OMI_TOOL_TIMEOUT_MS,
  });
}

function loadSkillTool() {
  return defineTool({
    name: "load_skill",
    label: "Load Skill",
    description: "Load a relevant skill progressively: the first call returns metadata, the body's section table of contents, and only the first section's content; additional sections load one at a time with a part number.",
    promptSnippet: "load_skill - Load a relevant skill returned by the catalog or search_skills",
    parameters: Type.Object({
      name: Type.String({ description: "Skill name returned by the compact catalog or search_skills" }),
      part: Type.Optional(
        Type.Number({ description: "1-based body section to read. Omit for the overview, section list, and first section." })
      ),
    }, { additionalProperties: false }),
    async execute(_toolCallId, params) {
      const name = String((params as { name?: unknown }).name ?? "").trim();
      if (!isSafeSkillName(name)) {
        return {
          content: [{
            type: "text" as const,
            text: "Invalid skill name. Use a skill returned by the catalog or search_skills.",
          }],
          details: undefined,
        };
      }
      const rawPart = (params as { part?: unknown }).part;
      const part = rawPart === "all" ? "all" : typeof rawPart === "number" ? rawPart : undefined;
      return {
        content: [{
          type: "text" as const,
          text: await loadSkillInstructions(name, process.env.OMI_WORKSPACE ?? "", part === undefined ? {} : { part }),
        }],
        details: undefined,
      };
    },
  });
}

function searchSkillsTool() {
  return defineTool({
    name: "search_skills",
    label: "Search Skills",
    description: "Search installed skill names and compact descriptions for a workflow relevant to the user's request.",
    promptSnippet: "search_skills - Find a relevant specialized workflow before loading it",
    promptGuidelines: [
      "Use only when the current user request plausibly needs a specialized workflow.",
      "Do not browse skills merely to explore options or because a related term appears in conversation context.",
    ],
    parameters: Type.Object({
      query: Type.String({ description: "Short description of the user's request" }),
    }, { additionalProperties: false }),
    async execute(_toolCallId, params) {
      const query = String((params as { query?: unknown }).query ?? "").trim();
      return {
        content: [{
          type: "text" as const,
          text: await searchSkills(query),
        }],
        details: undefined,
      };
    },
  });
}

export function omiToolProjectionContextFromEnv(
  env: Record<string, string | undefined> = process.env,
): OmiToolProjectionContext {
  const chatFirstControlGeneration = Number(env.OMI_CHAT_FIRST_CONTROL_GENERATION);
  return {
    executionRole: env.OMI_EXECUTION_ROLE === "leaf" ? "leaf" : "coordinator",
    surfaceKind: env.OMI_SURFACE_KIND,
    chatFirstUi: env.OMI_CHAT_FIRST_UI === "true" && env.OMI_SURFACE_KIND === "main_chat",
    controlGeneration: Number.isSafeInteger(chatFirstControlGeneration) && chatFirstControlGeneration >= 0
      ? chatFirstControlGeneration
      : null,
    // Only an explicit string true can widen the client-side catalog. The
    // backend still authorizes every relay independently.
    jitKnowledgeToolsEnabled: env.OMI_JIT_KNOWLEDGE_TOOLS_ENABLED === "true",
  };
}

const projectionContext = omiToolProjectionContextFromEnv();

export function omiToolsForExecutionRole(role: "coordinator" | "leaf") {
  return omiToolsForProjectionContext({ executionRole: role });
}

export function omiToolsForProjectionContext(context: OmiToolProjectionContext) {
  return toolsForAdapter("pi-mono", context).map((tool) => {
    if (tool.name === "load_skill") return loadSkillTool();
    if (tool.name === "search_skills") return searchSkillsTool();
    return omiManifestTool(tool);
  });
}

export const OMI_TOOLS = omiToolsForProjectionContext(projectionContext);

async function registerOmiTools(pi: ExtensionAPI): Promise<void> {
  const pipePath = process.env.OMI_BRIDGE_PIPE;
  if (!pipePath) {
    process.stderr.write("[omi-tools] OMI_BRIDGE_PIPE not set — Omi tools unavailable\n");
    return;
  }
  try {
    await connectOmiPipe(pipePath);
  } catch (err) {
    process.stderr.write(`[omi-tools] Failed to connect: ${err instanceof Error ? err.message : err}\n`);
    return;
  }
  for (const tool of OMI_TOOLS) {
    pi.registerTool(tool);
  }
  const snapshot = buildToolAvailabilitySnapshot("pi-mono", projectionContext);
  if (process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH) {
    try {
      await writeFile(process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH, `${JSON.stringify(snapshot, null, 2)}\n`);
    } catch (err) {
      process.stderr.write(
        `[omi-tools] Failed to write tool availability snapshot: ${err instanceof Error ? err.message : err}\n`,
      );
    }
  }
  process.stderr.write(
    `[omi-tools] adapter=pi-mono advertisedToolCount=${snapshot.advertisedToolCount} advertisedTools=${snapshot.advertisedToolNames.join(",")}\n`,
  );
}

export async function __registerOmiToolsForTest(pi: ExtensionAPI): Promise<void> {
  await registerOmiTools(pi);
}

// ---------------------------------------------------------------------------
// User-added MCP servers (~/.omi/mcp.json, managed from the desktop Apps page)
//
// Progressive disclosure. The servers are NOT registered tool-by-tool: a user
// with a handful of servers would put hundreds of verbatim descriptions and
// JSON schemas into the default tools payload before the model has expressed
// any interest in one of them. Exactly two proxy tools are registered instead:
//
//   mcp_tools_info — discovery. The stable, sorted index of server names and
//     tool names is embedded in the proxy descriptions below, so identifying
//   a candidate needs no extra turn; calling it returns full descriptions
//     and JSON input schemas on demand.
//   mcp_call — dispatch. Runs a server's tool (or published prompt) by its
//     REAL names and returns the result content faithfully.
//
// The old `mcp_<server>_<tool>` mangling is gone from the model's surface
// entirely. Everything a server returns is untrusted tool-result data: it is
// handed back as tool output and never interpolated into system instructions.
// ---------------------------------------------------------------------------

type McpServerStatus = "connecting" | "ready" | "failed";

interface McpServerEntry {
  readonly name: string;
  readonly client: McpClient;
  /** 30s for stdio (a first `npx <package>` run downloads it), 10s remote. */
  readonly discoveryBudgetMs: number;
  /** stdio servers spawn a child process at start; remote ones open a connection. */
  readonly kind: "stdio" | "remote";
  status: McpServerStatus;
  error?: string;
  tools: McpRemoteTool[];
  prompts: McpPrompt[];
}

/** Every configured server, sorted by name; the proxy tools read this live. */
let mcpServers: McpServerEntry[] = [];

/**
 * Ceiling on one MCP tool or prompt call. Nothing else settles these: an SSE
 * server's reply arrives on a stream that may simply never carry it, and a stdio
 * server's only other terminal event is the child exiting. Without this the
 * user's turn spins with no way out short of quitting the app.
 */
const CALL_TIMEOUT_MS = 120_000;

/**
 * How long the first prompt waits for servers to connect before the proxies
 * register with whatever has landed so far. This is the only MCP wait on the
 * turn path — the per-server budgets below are connection timeouts, not
 * prompt-blocking gates. Servers still connecting keep connecting in the
 * background: pi's registerTool cannot revise a description after the fact,
 * but the proxies read live state, so a late server becomes callable anyway
 * and mcp_tools_info reports its true status.
 */
const DEFAULT_MCP_FIRST_TURN_BUDGET_MS = 3_000;

function firstTurnBudgetMs(): number {
  const raw = Number(process.env.OMI_MCP_FIRST_TURN_BUDGET_MS);
  return Number.isSafeInteger(raw) && raw >= 0 ? raw : DEFAULT_MCP_FIRST_TURN_BUDGET_MS;
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => {
      const timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
      timer.unref?.();
    }),
  ]);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    timer.unref?.();
  });
}

function byName(a: { name: string }, b: { name: string }): number {
  return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
}

function createMcpClient(server: UserMcpServer): McpClient {
  if (isStdioServer(server)) {
    return new McpStdioClient(server.command, server.args, server.env);
  }
  // Headers pass through as configured. `loadLocalMcpConfig` has already turned a
  // `token` or a stored OAuth `access_token` into an Authorization header, so
  // unwrapping one here only to have the client rebuild it corrupted any scheme
  // that was not Bearer.
  const headers = Object.fromEntries((server.headers ?? []).map((h) => [h.name, h.value]));
  // An `sse` server publishes a long-lived event stream, not a POST target;
  // driving it as Streamable HTTP is a 404 on every message.
  return server.type === "sse"
    ? new McpSseClient(server.url, headers)
    : new McpHttpClient(server.url, headers);
}

/**
 * At most this many stdio servers start at once. Every stdio start is a child
 * process — often `npx`, which may download a package first — and a large
 * config used to fire all of those spawns in the same instant. Remote servers
 * (http/sse) open lightweight connections and deliberately stay unbounded; only
 * the process-spawning lane shares the bound.
 */
export const MCP_STDIO_START_CONCURRENCY = 8;

/**
 * Start discovery for every entry, returning the promises for the caller to
 * race against the first-turn budget. stdio entries share the concurrency
 * bound above — a worker pool claims the next entry as each discovery
 * settles — while remote entries start immediately. Never rejects: the start
 * function is responsible for its own error handling.
 */
export function startMcpDiscoveries<T extends { kind: "stdio" | "remote" }>(
  entries: readonly T[],
  start: (entry: T) => Promise<void>,
): Promise<unknown>[] {
  const stdio = entries.filter((entry) => entry.kind === "stdio");
  let cursor = 0;
  const workers = Array.from(
    { length: Math.min(MCP_STDIO_START_CONCURRENCY, stdio.length) },
    async () => {
      // The event loop is single-threaded, so claiming the next index before
      // the first await cannot race another worker.
      while (cursor < stdio.length) {
        await start(stdio[cursor++]);
      }
    },
  );
  return [
    ...workers,
    ...entries.filter((entry) => entry.kind !== "stdio").map((entry) => start(entry)),
  ];
}

/**
 * One server's tool and prompt discovery under a single budget — the two calls
 * share one deadline: charging each its own turned a single wedged stdio server
 * into a minute of blocked startup. Never rejects; the outcome lands on the
 * entry the proxy tools read.
 */
function startMcpDiscovery(entry: McpServerEntry): Promise<void> {
  return (async () => {
    const deadline = Date.now() + entry.discoveryBudgetMs;
    try {
      const tools = await withTimeout(entry.client.listTools(), entry.discoveryBudgetMs);
      const prompts = entry.client.supports("prompts")
        ? await withTimeout(entry.client.listPrompts(), Math.max(1_000, deadline - Date.now()))
        : [];
      entry.tools = [...tools].sort(byName);
      entry.prompts = [...prompts].sort(byName);
      entry.status = "ready";
      process.stderr.write(
        `[user-mcp] ${entry.name}: discovered ${entry.tools.length} tools, ${entry.prompts.length} prompts\n`,
      );
      if (entry.tools.length === 0 && entry.prompts.length === 0) {
        // Nothing to call means nothing holds this client, and nothing will ever
        // close it: an SSE server's GET stream and a stdio server's child would
        // stay open for the whole session with no way to reach them.
        entry.client.dispose();
      }
    } catch (err) {
      entry.status = "failed";
      entry.error = err instanceof Error ? err.message : String(err);
      entry.client.dispose();
      process.stderr.write(
        `[user-mcp] ${entry.name}: server unavailable: ${entry.error}\n`,
      );
    }
  })();
}

/** Tool names listed inline per server before the index defers to mcp_tools_info. */
const MCP_INDEX_NAME_CAP = 40;
const MCP_INDEX_PROMPT_CAP = 10;
/**
 * Tool and prompt names are the server's to choose (`listTools` accepts any
 * non-empty string), so each name is clipped before it rides in the proxy
 * tools' frozen descriptions — the name caps bound the count, not the size.
 * A clipped name is still findable: the live mcp_tools_info results always
 * carry the real, full name.
 */
const MCP_INDEX_NAME_WIDTH = 64;
/** Server lines embedded in the frozen descriptions before deferring to the live index. */
const MCP_INDEX_SERVER_LINE_CAP = 20;

function clippedName(name: string): string {
  return name.length <= MCP_INDEX_NAME_WIDTH ? name : `${name.slice(0, MCP_INDEX_NAME_WIDTH)}…`;
}

function nameList(names: string[], cap: number): string {
  const clipped = names.map(clippedName);
  if (clipped.length <= cap) return clipped.join(", ");
  return `${clipped.slice(0, cap).join(", ")} … +${names.length - cap} more`;
}

/**
 * The discovery index: one line per configured server — name, one-line
 * description if the server declares one, live status, tool names. Sorted and
 * name-only, because this text rides in the proxy tools' descriptions on every
 * turn: it must stay compact and never carry tool descriptions or schemas.
 * Server lines are bounded too: past the cap the description defers to the
 * live mcp_tools_info index instead of growing with the user's config.
 */
function mcpIndexText(): string {
  if (mcpServers.length === 0) return "No user MCP servers are configured.";
  const lines = mcpServers.slice(0, MCP_INDEX_SERVER_LINE_CAP).map((entry) => {
    const hint = entry.client.serverDescription;
    if (entry.status === "connecting") {
      // Neutral wording: pi cannot revise a registered description, so a
      // literal "connecting…" here would outlive the connection it described.
      // The live index — mcp_tools_info with no arguments — reports real status.
      return `- ${entry.name}: status at registration — call mcp_tools_info with no arguments for live status`;
    }
    if (entry.status === "failed") {
      return `- ${entry.name}: unavailable (${entry.error ?? "unknown error"})`;
    }
    const tools = `tools (${entry.tools.length}): ${nameList(entry.tools.map((tool) => tool.name), MCP_INDEX_NAME_CAP)}`;
    const prompts = entry.prompts.length
      ? `; prompts (${entry.prompts.length}): ${nameList(entry.prompts.map((prompt) => prompt.name), MCP_INDEX_PROMPT_CAP)}`
      : "";
    return `- ${entry.name}${hint ? ` — ${hint}` : ""}: ${tools}${prompts}`;
  });
  if (mcpServers.length > MCP_INDEX_SERVER_LINE_CAP) {
    lines.push(
      `… +${mcpServers.length - MCP_INDEX_SERVER_LINE_CAP} more — call mcp_tools_info with no arguments for the live index`,
    );
  }
  return lines.join("\n");
}

/**
 * Server names for the mcp_call description: names only, count-bounded. The
 * full name-only tool index rides once, in mcp_tools_info's description —
 * duplicating it in both proxies cost its size again on every turn. Server
 * names need no clipping: loadLocalMcpConfig admits 1-64 chars only.
 */
function mcpServerNameLine(): string {
  if (mcpServers.length === 0) return "none";
  const names = mcpServers.slice(0, MCP_INDEX_SERVER_LINE_CAP).map((entry) => entry.name);
  if (mcpServers.length > MCP_INDEX_SERVER_LINE_CAP) {
    names.push(
      `… +${mcpServers.length - MCP_INDEX_SERVER_LINE_CAP} more — call mcp_tools_info with no arguments for the live index`,
    );
  }
  return names.join(", ");
}

function mcpTextResult(text: string) {
  return { content: [{ type: "text" as const, text }], details: undefined };
}

function findServer(name: string): McpServerEntry | undefined {
  return mcpServers.find((entry) => entry.name === name);
}

function mcpToolsInfoTool() {
  return defineTool({
    name: "mcp_tools_info",
    label: "MCP Tools Info",
    description:
      "Discover the user's MCP servers. With no arguments, returns the live index of configured servers " +
      "and their tool names. Pass server (and optionally tool) to get full descriptions and JSON input " +
      "schemas for one server or one tool. Run this before mcp_call whenever the index below is not enough.\n\n" +
      `Configured servers right now:\n${mcpIndexText()}`,
    parameters: Type.Object({
      server: Type.Optional(Type.String({ description: "A server name from the index" })),
      tool: Type.Optional(Type.String({ description: "A tool or prompt name on that server" })),
    }, { additionalProperties: false }),
    async execute(_toolCallId, params) {
      const serverName = typeof params.server === "string" ? params.server : undefined;
      const toolName = typeof params.tool === "string" ? params.tool : undefined;
      if (!serverName) {
        return mcpTextResult(JSON.stringify({ servers: mcpServerSummaries() }, null, 2));
      }
      const entry = findServer(serverName);
      if (!entry) {
        return mcpTextResult(`Error: unknown MCP server '${serverName}'. ${mcpIndexText()}`);
      }
      if (entry.status === "connecting") {
        return mcpTextResult(`MCP server '${serverName}' is still connecting; call again in a moment.`);
      }
      if (entry.status === "failed") {
        return mcpTextResult(`MCP server '${serverName}' is unavailable: ${entry.error ?? "unknown error"}`);
      }
      if (toolName) {
        const tool = entry.tools.find((candidate) => candidate.name === toolName);
        if (tool) {
          return mcpTextResult(JSON.stringify({
            server: entry.name,
            kind: "tool",
            name: tool.name,
            description: tool.description,
            inputSchema: tool.inputSchema,
          }, null, 2));
        }
        const prompt = entry.prompts.find((candidate) => candidate.name === toolName);
        if (prompt) {
          return mcpTextResult(JSON.stringify({
            server: entry.name,
            kind: "prompt",
            name: prompt.name,
            description: prompt.description,
            arguments: prompt.arguments,
          }, null, 2));
        }
        return mcpTextResult(
          `Error: server '${serverName}' has no tool or prompt named '${toolName}'. ` +
            `Tools: ${nameList(entry.tools.map((candidate) => candidate.name), MCP_INDEX_NAME_CAP)}.`,
        );
      }
      return mcpTextResult(JSON.stringify({
        server: entry.name,
        status: entry.status,
        ...(entry.client.serverDescription ? { description: entry.client.serverDescription } : {}),
        tools: entry.tools.map((tool) => ({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        })),
        prompts: entry.prompts.map((prompt) => ({
          name: prompt.name,
          description: prompt.description,
          arguments: prompt.arguments,
        })),
      }, null, 2));
    },
  });
}

interface McpServerSummary {
  name: string;
  status: McpServerStatus;
  description?: string;
  error?: string;
  tools?: string[];
  prompts?: string[];
}

/** The live no-argument mcp_tools_info view: names and status, never schemas. */
function mcpServerSummaries(): McpServerSummary[] {
  return mcpServers.map((entry) => ({
    name: entry.name,
    status: entry.status,
    ...(entry.client.serverDescription ? { description: entry.client.serverDescription } : {}),
    ...(entry.error ? { error: entry.error } : {}),
    ...(entry.status === "ready"
      ? {
          tools: entry.tools.map((tool) => tool.name),
          prompts: entry.prompts.map((prompt) => prompt.name),
        }
      : {}),
  }));
}

function mcpCallTool() {
  return defineTool({
    name: "mcp_call",
    label: "MCP Call",
    description:
      "Run a tool (or a published prompt) on one of the user's MCP servers, by its real server and tool " +
      "names, and get the result content back as text.\n\n" +
      // Server names only: the tool index rides once, in mcp_tools_info's
      // description — duplicating it here cost its full size again per turn.
      `Configured servers right now: ${mcpServerNameLine()}\n` +
      "Call mcp_tools_info first for the tool index and, when you need it, a tool's full description and input schema.",
    parameters: Type.Object({
      server: Type.String({ description: "Server name from the mcp_tools_info index" }),
      tool: Type.String({ description: "Tool (or prompt) name on that server" }),
      arguments: Type.Optional(Type.Unknown({
        description: "Arguments object matching the tool's JSON input schema",
      })),
    }, { additionalProperties: false }),
    async execute(_toolCallId, params) {
      const entry = findServer(params.server);
      if (!entry) {
        return mcpTextResult(
          `Error: unknown MCP server '${params.server}'. ` +
            `Configured servers: ${mcpServers.map((candidate) => candidate.name).join(", ") || "none"}.`,
        );
      }
      if (entry.status === "connecting") {
        return mcpTextResult(`Error: MCP server '${entry.name}' is still connecting; call again in a moment.`);
      }
      if (entry.status === "failed") {
        return mcpTextResult(`Error: MCP server '${entry.name}' is unavailable: ${entry.error ?? "unknown error"}`);
      }
      const args = (params.arguments ?? {}) as Record<string, unknown>;
      let text: string;
      if (entry.tools.some((candidate) => candidate.name === params.tool)) {
        // A tool and a prompt sharing a name resolve to the tool; the prompt
        // stays reachable through its own listing.
        try {
          text = await withTimeout(entry.client.callTool(params.tool, args), CALL_TIMEOUT_MS);
        } catch (err) {
          text = `Error calling ${entry.name}/${params.tool}: ${err instanceof Error ? err.message : err}`;
        }
      } else if (entry.prompts.some((candidate) => candidate.name === params.tool)) {
        try {
          text = await withTimeout(entry.client.getPrompt(params.tool, args), CALL_TIMEOUT_MS);
        } catch (err) {
          text = `Error getting prompt ${entry.name}/${params.tool}: ${err instanceof Error ? err.message : err}`;
        }
      } else {
        text =
          `Error: server '${entry.name}' has no tool or prompt named '${params.tool}'. ` +
          "Call mcp_tools_info with this server's name for the full list.";
      }
      return mcpTextResult(text);
    },
  });
}

/**
 * Connect every configured server, then register the two proxy tools.
 *
 * Deterministic: servers are sorted by name, their tools and prompts are
 * sorted by name, and the proxies go in in one pass after the await window —
 * there are no per-tool registrations left to race, and the index text is
 * built from that sorted snapshot.
 *
 * Non-blocking first turn: the turn path waits at most the short global
 * budget above, not any server's own connection timeout. Whatever landed by
 * then is in the embedded index; the rest finishes in the background and is
 * picked up live by the proxies, which report each server's true state.
 */
async function registerUserMcpTools(pi: ExtensionAPI): Promise<void> {
  const logErr = (msg: string) => process.stderr.write(`[user-mcp] ${msg}\n`);
  const servers = loadLocalMcpConfig(process.env.OMI_LOCAL_MCP_FILE, new Set(), logErr)
    .sort(byName);
  mcpServers = servers.map((config) => ({
    name: config.name,
    client: createMcpClient(config),
    discoveryBudgetMs: isStdioServer(config) ? 30_000 : 10_000,
    kind: isStdioServer(config) ? "stdio" : "remote",
    status: "connecting",
    tools: [],
    prompts: [],
  }));
  // stdio spawns share the bounded start pool; remote connects are unbounded.
  const probes = startMcpDiscoveries(mcpServers, startMcpDiscovery);
  await Promise.race([Promise.allSettled(probes), sleep(firstTurnBudgetMs())]);
  pi.registerTool(mcpToolsInfoTool());
  pi.registerTool(mcpCallTool());
  // Stragglers keep connecting; startMcpDiscovery never rejects, and each
  // completion updates the entry the proxies read and logs its outcome.
}

export async function __registerUserMcpToolsForTest(pi: ExtensionAPI): Promise<void> {
  await registerUserMcpTools(pi);
}

/** Test-only: dispose every client and drop the registry between tests. */
export function __resetUserMcpForTest(): void {
  for (const entry of mcpServers) entry.client.dispose();
  mcpServers = [];
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default async function omiProvider(pi: ExtensionAPI): Promise<void> {
  installOmiJitFetchGuard();
  // Best-effort, never fatal: tighten a pre-existing audit log to owner-only.
  void restrictAuditLogPermissions();

  const baseUrl = process.env.OMI_API_BASE_URL || "https://api.omi.me/v2";
  const apiKey = process.env.OMI_API_KEY || "";

  // BYOK: the Swift app sets OMI_BYOK_* env vars for the selected LLM provider and
  // optional Deepgram key. Attach configured capabilities as X-BYOK-* headers on
  // every request so the backend applies the LLM BYOK quota exemption and routes
  // inference through the selected provider key instead of Omi's server key.
  const byokMap: Array<[string, string]> = [
    ["OMI_BYOK_OPENROUTER", "X-BYOK-OpenRouter"],
    ["OMI_BYOK_OPENAI", "X-BYOK-OpenAI"],
    ["OMI_BYOK_ANTHROPIC", "X-BYOK-Anthropic"],
    ["OMI_BYOK_GEMINI", "X-BYOK-Gemini"],
    ["OMI_BYOK_DEEPGRAM", "X-BYOK-Deepgram"],
  ];
  const byokHeaders: Record<string, string> = {};
  for (const [envName, headerName] of byokMap) {
    const value = process.env[envName];
    if (value && value.length > 0) byokHeaders[headerName] = value;
  }
  const byokActive = Object.keys(byokHeaders).length > 0;
  if (byokActive) {
    process.stderr.write(`[omi-provider] BYOK active — attaching ${Object.keys(byokHeaders).length} X-BYOK headers\n`);
  }

  pi.registerProvider("omi", {
    api: "openai-completions",
    baseUrl,
    apiKey,
    ...(byokActive ? { headers: byokHeaders } : {}),
    models: [
      {
        id: "omi-sonnet",
        name: "Omi Sonnet",
        reasoning: true,
        input: ["text", "image"],
        contextWindow: 200_000,
        maxTokens: 16_384,
        // Cost set to 0 client-side — tracked server-side by the backend
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      },
    ],
  });

  // Pi asks for headers once per provider request and keeps them for retries,
  // which preserves one safe correlation id across an upstream retry chain.
  pi.on("before_provider_headers", async (event) => {
    const raw = await omiRelayContextRaw();
    // Per-turn effort lane: typed chat runs "adaptive" (the model decides its
    // own thinking depth), PTT runs "fast" (thinking off, low effort). The
    // gateway translates this into Anthropic thinking/effort parameters.
    applyOmiProviderHeaders(event.headers, raw);
  });

  pi.on("tool_call", async (event): Promise<ToolCallEventResult | void> => {
    let decision: DenyDecision | null = null;
    let builtInToolPolicy: OmiBuiltInToolPolicy = "read_only";
    try {
      const relayContext = await omiRelayContextRaw();
      builtInToolPolicy = relayContext === undefined
        ? "read_only"
        : omiBuiltInToolPolicyFromRelayContext(relayContext);
    } catch (err) {
      // Authority transport failures fail closed for adapter mutations.
      const msg = err instanceof Error ? err.message : String(err);
      void appendAudit({
        ts: new Date().toISOString(),
        phase: "before",
        tool: event.toolName,
        decision: "error",
        reason: `classifier threw: ${msg}`,
        summary: summarizeInput(event),
      });
    }
    decision = inspectToolCall(event, builtInToolPolicy);

    void appendAudit({
      ts: new Date().toISOString(),
      phase: "before",
      tool: event.toolName,
      decision: decision ? "deny" : "allow",
      reason: decision?.reason,
      summary: summarizeInput(event),
    });

    if (decision) {
      return { block: true, reason: decision.reason };
    }
    return undefined;
  });

  pi.on("tool_result", async (event: ToolResultEvent): Promise<void> => {
    void appendAudit({
      ts: new Date().toISOString(),
      phase: "after",
      tool: event.toolName,
      decision: event.isError ? "error" : "ok",
      summary: summarizeInput({
        type: "tool_call",
        toolName: event.toolName,
        toolCallId: event.toolCallId,
        input: event.input,
      } as ToolCallEvent),
    });
  });

  // Register Omi-specific tools (execute_sql, semantic_search, etc.)
  // These forward to Swift via the OMI_BRIDGE_PIPE Unix socket.
  void registerOmiTools(pi);

  // User MCP servers from the Apps page, exposed through the two proxy tools
  // (progressive disclosure). Awaited (pi waits for async extension factories)
  // but bounded by a short global budget — a wedged server delays the first
  // turn by that budget once, never by its own connection timeout, and
  // stragglers are picked up live afterwards. A failing server is reported
  // through the proxies, never fatal.
  await registerUserMcpTools(pi);
}

// ---------------------------------------------------------------------------
// Test-only exports — relay internals for unit tests
// ---------------------------------------------------------------------------

/** Test-only: connect the pipe relay to a socket path. */
export const __connectOmiPipeForTest = connectOmiPipe;

/** Test-only: call a Swift tool through the pipe relay. */
export const __callSwiftToolForTest = callSwiftTool;
export const __omiRelayCapabilityRefForTest = omiRelayCapabilityRef;

/** Test-only: access to pending calls map for assertions. */
export const __omiPendingCallsForTest = omiPendingCalls;

/** Test-only: reset pipe state between tests. */
export function __resetOmiPipeForTest(): void {
  if (omiPipeConnection) {
    omiPipeConnection.destroy();
    omiPipeConnection = null;
  }
  omiPipeBuffer = "";
  omiCallIdCounter = 0;
  omiPendingCalls.clear();
}
