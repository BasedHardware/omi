#!/usr/bin/env node

import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";
import WebSocket from "ws";

import { omiToolManifest } from "../dist/runtime/omi-tool-manifest.js";

const execFileAsync = promisify(execFile);
const defaultCases = new URL("../evals/realtime-routing-cases.json", import.meta.url);
const defaultPlist = "/Applications/Omi Dev.app/Contents/Resources/GoogleService-Info.plist";
const defaultBackend = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app";

const originalCard = "Send a difficult question through Omi's full typed-chat model and tools, then receive its final answer to speak. Use it when the user is dissatisfied with your previous answer, or when a complicated question needs deeper reasoning, memories, or other tools unavailable in the realtime lane. Use web_search instead for current public information or an explicit web lookup. Before calling it, say a short varied wait-line such as 'let me think about that' or 'give me a second'; do not use a fixed script, do not answer before the tool returns, and do not call it for chit-chat or simple creative requests. When it returns, read its answer faithfully; you may lightly adapt phrasing for speech but must not invent a different answer.";

const strongerCard = [
  "Use Omi's full Chat model and tools to think deeply before answering, then return a spoken answer.",
  "ALWAYS call this before answering when the user asks you to think carefully, go deep, reason it out, take your time, not guess, advise what they should do, compare tradeoffs, make a multi-step plan, or reconsider a weak prior answer.",
  "Also call it proactively on the first turn when a good answer requires complicated reasoning, consequential judgment, personalized synthesis across the user's data, or would be shallow as a quick realtime response.",
  "If unsure whether the question needs deeper thought, call it.",
  "Skip only for chit-chat, short confirmations, obvious stable facts, or a single fast realtime tool that fully answers the request.",
  "For questions needing both current facts and judgment, call web_search first and pass its result as context here.",
  "Give a brief request-specific wait-line and call immediately without answering first. Speak the returned conclusion faithfully.",
].join(" ");

const conciseCard = [
  "Call Omi's full Chat model and tools before answering any request that needs deeper thought.",
  "ALWAYS call for explicit think-hard language, advice about what to do, tradeoffs, multi-step plans, consequential judgment, personalized synthesis, complicated first-turn questions, or pushback on a weak answer.",
  "If unsure whether a quick realtime answer would be shallow, call it.",
  "Skip only chit-chat, short confirmations, obvious stable facts, and a single fast realtime tool that fully answers.",
  "When current facts are also needed, call web_search first and pass its result as context.",
  "Say a short varied wait-line, call immediately without answering first, and speak the result faithfully.",
].join(" ");

const reinforcedCard = [
  "Use Omi's full Chat model and tools to think deeply before answering, then return a spoken answer.",
  "ALWAYS call this tool before answering when the user says 'think carefully', 'think about this', 'go deep', 'reason it out', 'take your time', 'don't just guess', or 'what should I do', or otherwise asks for advice, tradeoffs, a multi-step plan, or reconsideration of a weak answer.",
  "A short, vague, or first-turn request still counts: call the tool with the question as given instead of answering or asking a clarifying question first.",
  "Also call proactively on the first turn for complicated reasoning, consequential judgment, personalized synthesis across the user's data, or any answer that would be shallow in one or two realtime sentences.",
  "If unsure whether deeper thought would improve the answer, call it.",
  "Skip only chit-chat, short confirmations, obvious stable facts, or a single fast realtime tool that fully answers the request.",
  "When current public facts and judgment are both needed, call web_search first and pass its result as context here.",
  "Give a brief request-specific wait-line and call immediately without answering first. Speak the returned conclusion faithfully.",
].join(" ");

const variants = {
  production: {
    card: null,
    latency: "Keep latency low for simple requests. Never skip a tool call required by its declaration just to answer faster.",
  },
  baseline: {
    card: originalCard,
    latency: "Keep latency low: prefer answering directly when you can.",
  },
  card_only: {
    card: strongerCard,
    latency: "Keep latency low: prefer answering directly when you can.",
  },
  balanced: {
    card: strongerCard,
    latency: "Be fast for genuinely easy requests, but never choose a shallow direct answer merely to save latency. Use the declared tool that materially improves answer quality.",
  },
  targeted: {
    card: strongerCard,
    latency: "Keep latency low for simple requests. Never skip a tool call required by its declaration just to answer faster.",
  },
  reinforced: {
    card: reinforcedCard,
    latency: "Keep latency low for simple requests. Never skip a tool call required by its declaration just to answer faster.",
  },
  concise: {
    card: conciseCard,
    latency: "Be fast for genuinely easy requests, but never choose a shallow direct answer merely to save latency. Use the declared tool that materially improves answer quality.",
  },
};

function parseArgs(argv) {
  const options = { variants: ["production"], repeat: 1 };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = () => {
      const next = argv[++i];
      if (!next) throw new Error(`${arg} requires a value`);
      return next;
    };
    if (arg === "--variant") options.variants = value().split(",");
    else if (arg === "--case") options.caseIds = new Set(value().split(","));
    else if (arg === "--repeat") options.repeat = Number.parseInt(value(), 10);
    else if (arg === "--auth-export") options.authExport = value();
    else if (arg === "--firebase-plist") options.firebasePlist = value();
    else if (arg === "--backend") options.backend = value();
    else if (arg === "--cases") options.cases = value();
    else if (arg === "--json") options.json = true;
    else if (arg === "--help") options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!Number.isInteger(options.repeat) || options.repeat < 1) throw new Error("--repeat must be a positive integer");
  for (const name of options.variants) if (!variants[name]) throw new Error(`unknown variant: ${name}`);
  return options;
}

function usage() {
  return `Usage: npm run eval:realtime-routing -- --auth-export /private/tmp/desktop-auth.json [options]

Runs text-only tool-choice trials against the real managed Gemini Live endpoint, using the
same manifest projection as macOS but without rebuilding the app.

  --variant production,baseline,card_only,balanced,targeted,reinforced,concise  variants to compare
  --case id,id                                 selected fixture cases
  --repeat N                                   repetitions per case (default 1)
  --auth-export PATH                           output from scripts/omi-auth-dump.sh
  --firebase-plist PATH                        Firebase plist (default: Omi Dev)
  --backend URL                                token-mint backend
  --cases PATH                                 alternate case JSON
  --json                                       emit JSONL only
`;
}

const realtimeControlTools = new Set([
  "list_agent_sessions", "get_agent_run", "cancel_agent_run", "inspect_agent_artifacts",
  "update_agent_artifact_lifecycle", "spawn_agent", "set_desktop_attention_override",
]);
const unsupportedSchemaKeys = new Set(["additionalProperties", "$schema", "default", "title", "pattern", "const"]);

function hasRealtimeSurface(tool) {
  if (tool.surfaces?.includes("realtime_voice")) return true;
  return Object.values(tool.aliasCapabilityDocs ?? {}).some((doc) =>
    (doc.surfaces ?? tool.surfaces ?? []).includes("realtime_voice"));
}

function shouldExpose(tool) {
  if (tool.voice?.realtimeExpose === false) return false;
  if (tool.voice?.realtimeExpose === true) return true;
  if (tool.executor?.kind === "runtimeControl") return realtimeControlTools.has(tool.name) && hasRealtimeSurface(tool);
  return hasRealtimeSurface(tool);
}

function exposedName(tool) {
  const alias = Object.entries(tool.aliasCapabilityDocs ?? {}).find(([, doc]) =>
    (doc.surfaces ?? tool.surfaces ?? []).includes("realtime_voice"));
  return alias?.[0] ?? tool.name;
}

function geminiSchema(value) {
  if (Array.isArray(value)) return value.map(geminiSchema);
  if (!value || typeof value !== "object") return value;
  const out = {};
  for (const [key, child] of Object.entries(value)) {
    if (unsupportedSchemaKeys.has(key)) continue;
    if (key === "properties" && child && typeof child === "object" && !Array.isArray(child)) {
      out[key] = Object.fromEntries(Object.entries(child).map(([name, schema]) => [name, geminiSchema(schema)]));
    } else {
      out[key] = key === "type" && typeof child === "string" ? child.toUpperCase() : geminiSchema(child);
    }
  }
  return out;
}

function declarationsFor(variant) {
  return omiToolManifest.filter(shouldExpose).map((tool) => {
    let parameters = tool.voice?.schemaOverride ?? tool.inputSchema;
    if (tool.name === "spawn_agent") {
      parameters = {
        type: "object",
        properties: {
          brief: { type: "string", description: "The user's raw delegation intent or proposed task." },
          title: { type: "string", description: "A short Title Case label for the task pill." },
        },
        required: ["brief"],
      };
    }
    const name = exposedName(tool);
    return {
      name,
      description: name === "think_deeper" && variant.card
        ? variant.card
        : (tool.voice?.realtimeDescription ?? tool.description),
      parameters: geminiSchema(parameters),
    };
  });
}

function systemInstruction(variant) {
  return [
    "You are Omi, a fast spoken-voice assistant on the user's Mac. Reply conversationally in one or two sentences by default.",
    "The declared tools describe the capabilities available on this surface. A tool call is only a proposal; the kernel makes the authoritative route and permission decision.",
    "When a request needs a tool, ordinarily give a brief request-specific spoken heads-up and call the tool in the same turn. The think_deeper and web_search cards are exceptions: call them silently and immediately because the app acknowledges the accepted tool. record_interject_feedback is also silent and immediate, but the app does not play a canned acknowledgement for it. Do not answer before a required tool returns.",
    variant.latency,
  ].join("\n\n");
}

async function firebaseIdToken(options) {
  if (process.env.OMI_AUTH_TOKEN) return process.env.OMI_AUTH_TOKEN;
  if (!options.authExport) throw new Error("set OMI_AUTH_TOKEN or pass --auth-export");
  const auth = JSON.parse(await readFile(options.authExport, "utf8"));
  const refreshToken = auth.auth_refreshToken?.value;
  if (!refreshToken) throw new Error("auth export does not contain auth_refreshToken.value");
  const { stdout: apiKey } = await execFileAsync("/usr/libexec/PlistBuddy", [
    "-c", "Print :API_KEY", options.firebasePlist ?? defaultPlist,
  ]);
  const body = new URLSearchParams({ grant_type: "refresh_token", refresh_token: refreshToken });
  const response = await fetch(`https://securetoken.googleapis.com/v1/token?key=${encodeURIComponent(apiKey.trim())}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error(`Firebase refresh failed (${response.status})`);
  const refreshed = await response.json();
  if (!refreshed.id_token) throw new Error("Firebase refresh returned no id_token");
  return refreshed.id_token;
}

async function mintGeminiToken(options, idToken) {
  const response = await fetch(`${options.backend ?? process.env.OMI_DESKTOP_API_URL ?? defaultBackend}/v2/realtime/session`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ provider: "gemini" }),
  });
  if (!response.ok) throw new Error(`Gemini token mint failed (${response.status}): ${await response.text()}`);
  const payload = await response.json();
  if (!payload.token) throw new Error("Gemini token mint returned no token");
  return payload.token;
}

async function runTrial({ prompt, variant, options, idToken }) {
  const token = await mintGeminiToken(options, idToken);
  const url = new URL("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained");
  url.searchParams.set("access_token", token);
  const ws = new WebSocket(url);
  let transcript = "";
  let settled = false;
  return new Promise((resolve) => {
    const timeout = setTimeout(() => finish({ route: "timeout", transcript }), 30_000);
    function finish(result) {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve(result);
      ws.close();
    }
    ws.on("open", () => {
      ws.send(JSON.stringify({
        setup: {
          model: "models/gemini-3.1-flash-live-preview",
          generationConfig: {
            responseModalities: ["AUDIO"], temperature: 0.3,
            speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: "Charon" } } },
          },
          systemInstruction: { parts: [{ text: systemInstruction(variant) }] },
          tools: [{ functionDeclarations: declarationsFor(variant) }],
          outputAudioTranscription: {},
          contextWindowCompression: { slidingWindow: {} },
        },
      }));
    });
    ws.on("message", (data) => {
      const message = JSON.parse(Buffer.from(data).toString("utf8"));
      if (message.setupComplete) {
        ws.send(JSON.stringify({
          clientContent: { turns: [{ role: "user", parts: [{ text: prompt }] }], turnComplete: true },
        }));
      }
      const calls = message.toolCall?.functionCalls;
      if (Array.isArray(calls) && calls.length > 0) finish({ route: calls[0].name, args: calls[0].args ?? {}, transcript });
      const text = message.serverContent?.outputTranscription?.text;
      if (typeof text === "string") transcript += text;
      if (message.serverContent?.turnComplete === true) finish({ route: "direct", transcript });
    });
    ws.on("error", (error) => finish({ route: "socket_error", error: error.message, transcript }));
    ws.on("close", (code, reason) => {
      if (!settled) finish({ route: `closed_${code}`, error: reason.toString("utf8"), transcript });
    });
  });
}

const options = parseArgs(process.argv.slice(2));
if (options.help) {
  process.stdout.write(usage());
  process.exit(0);
}
const caseList = JSON.parse(await readFile(options.cases ?? defaultCases, "utf8"))
  .filter((testCase) => !options.caseIds || options.caseIds.has(testCase.id));
if (caseList.length === 0) throw new Error("no routing cases selected");
const idToken = await firebaseIdToken(options);
const rows = [];
for (const variantName of options.variants) {
  for (const testCase of caseList) {
    for (let repetition = 1; repetition <= options.repeat; repetition += 1) {
      const started = Date.now();
      const result = await runTrial({ prompt: testCase.prompt, variant: variants[variantName], options, idToken });
      const row = {
        variant: variantName,
        case: testCase.id,
        kind: testCase.kind,
        repetition,
        expected: testCase.expected,
        actual: result.route,
        pass: testCase.expected.includes(result.route)
          && Object.entries(testCase.expectedArgsContain ?? {}).every(([key, expectedValues]) =>
            expectedValues.every((value) => String(result.args?.[key] ?? "").includes(value))),
        elapsedMs: Date.now() - started,
        ...(result.args ? { args: result.args } : {}),
        ...(result.error ? { error: result.error } : {}),
      };
      rows.push(row);
      if (options.json) process.stdout.write(`${JSON.stringify(row)}\n`);
      else {
        const args = testCase.expectedArgsContain ? ` args=${JSON.stringify(result.args ?? {})}` : "";
        process.stdout.write(`${row.pass ? "PASS" : "FAIL"}  ${variantName.padEnd(10)} ${testCase.id.padEnd(28)} expected=${testCase.expected.join("|")} actual=${result.route}${args} ${row.elapsedMs}ms\n`);
      }
    }
  }
}
const summary = options.variants.map((variant) => {
  const selected = rows.filter((row) => row.variant === variant);
  const hardMisses = selected.filter((row) => row.kind === "hard" && !row.pass).length;
  return { variant, passed: selected.filter((row) => row.pass).length, total: selected.length, hardMisses };
});
if (options.json) process.stdout.write(`${JSON.stringify({ summary })}\n`);
else {
  process.stdout.write("\nSummary\n");
  for (const item of summary) process.stdout.write(`${item.variant.padEnd(10)} ${item.passed}/${item.total} pass, ${item.hardMisses} hard misses\n`);
}
process.exitCode = rows.some((row) => !row.pass) ? 1 : 0;
