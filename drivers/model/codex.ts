/** Codex-subscription transport: the GLM edge's prompts/parsers/retries over `codex exec`.
 *
 * GlmModel already isolates its transport behind an injectable `fetch`. This module
 * provides a fetch-shaped function that, instead of POSTing to an OpenAI-compatible
 * endpoint, spawns `codex exec -m <model>` (ChatGPT-subscription auth from ~/.codex)
 * and wraps the agent's final message in a chat-completion response payload. Every
 * strategy edge (prompt construction, JSON parsing, repair-hint retries, per-strategy
 * timeouts) is reused verbatim from glm.ts.
 *
 * Notes:
 *  - `--ignore-user-config` is load-bearing: the user-level config.toml sets
 *    model_reasoning_effort=xhigh and session hooks, which turn a 3s call into 17s+.
 *  - `-s read-only --ephemeral --skip-git-repo-check` keep each call a pure,
 *    stateless completion; prompts here never ask the agent to touch the filesystem.
 *  - No response_format knob exists, so JSON discipline rests on the edge prompts +
 *    the existing malformed-JSON retry loop. Measured (2026-08-06): gpt-5.3-codex-spark
 *    ≈150 output tok/s, ~2-3s spawn overhead per call.
 *
 * Env: OMI_CODEX_MODEL (default gpt-5.3-codex-spark), OMI_CODEX_REASONING (default low),
 *      OMI_CODEX_BIN (default codex).
 */
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GlmModel } from "./glm";

export const DEFAULT_CODEX_MODEL = "gpt-5.3-codex-spark";

interface ChatBody { model?: string; messages?: readonly { role?: string; content?: string }[] }

/** Multi-turn messages (agentic retrieval) flatten into one prompt with role fences. */
const promptFromMessages = (messages: ChatBody["messages"]): string => {
  const turns = (messages ?? []).filter((message) => typeof message?.content === "string");
  if (turns.length === 1) return turns[0]!.content!;
  return turns.map((message) => `[${message.role ?? "user"}]\n${message.content}`).join("\n\n");
};

const runCodexExec = (input: { prompt: string; model: string; binary: string; reasoning: string; signal?: AbortSignal }): Promise<string> =>
  new Promise((resolve, reject) => {
    const dir = mkdtempSync(join(tmpdir(), "codex-edge-"));
    const outFile = join(dir, "last-message.txt");
    const child = spawn(input.binary, [
      "exec",
      "-m", input.model,
      "--ignore-user-config",
      "-c", `model_reasoning_effort="${input.reasoning}"`,
      "--ephemeral",
      "--skip-git-repo-check",
      "-s", "read-only",
      "--color", "never",
      "--output-last-message", outFile,
      "-",
    ], { stdio: ["pipe", "ignore", "pipe"], cwd: dir });
    let stderr = "";
    child.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });
    const onAbort = () => child.kill("SIGKILL");
    input.signal?.addEventListener("abort", onAbort, { once: true });
    child.on("error", (error) => {
      input.signal?.removeEventListener("abort", onAbort);
      rmSync(dir, { recursive: true, force: true });
      reject(error);
    });
    child.on("close", (code) => {
      input.signal?.removeEventListener("abort", onAbort);
      try {
        if (input.signal?.aborted) throw new Error("codex exec aborted (timeout)");
        if (code !== 0) throw new Error(`codex exec exited ${code}: ${stderr.slice(-500)}`);
        const message = readFileSync(outFile, "utf8").trim();
        if (!message) throw new Error(`codex exec produced no final message: ${stderr.slice(-500)}`);
        resolve(message);
      } catch (error) {
        reject(error);
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });
    child.stdin.end(input.prompt);
  });

/** fetch-shaped adapter: chat-completion request in, chat-completion response out. */
export const codexChatFetch = (options: { model?: string; binary?: string; reasoning?: string } = {}): typeof fetch => {
  const model = options.model ?? process.env.OMI_CODEX_MODEL ?? DEFAULT_CODEX_MODEL;
  const binary = options.binary ?? process.env.OMI_CODEX_BIN ?? "codex";
  const reasoning = options.reasoning ?? process.env.OMI_CODEX_REASONING ?? "low";
  const adapter = (async (_url: unknown, init?: { body?: unknown; signal?: AbortSignal }) => {
    const body = JSON.parse(String(init?.body ?? "{}")) as ChatBody;
    const content = await runCodexExec({ prompt: promptFromMessages(body.messages), model, binary, reasoning, signal: init?.signal ?? undefined });
    return new Response(JSON.stringify({ model, choices: [{ message: { role: "assistant", content } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return adapter;
};

/** Drop-in ModelPort over the Codex subscription. Same edges, different transport. */
export class CodexModel extends GlmModel {
  constructor(options: { model?: string; binary?: string; reasoning?: string } = {}) {
    super({
      apiKey: "codex-subscription", // satisfies the GlmModel key guard; never sent anywhere
      baseUrl: "codex://exec",
      model: options.model ?? process.env.OMI_CODEX_MODEL ?? DEFAULT_CODEX_MODEL,
      fetch: codexChatFetch(options),
    });
  }
}
