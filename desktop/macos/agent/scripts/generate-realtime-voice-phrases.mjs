#!/usr/bin/env node

/**
 * Generate the native realtime acknowledgement pack.
 *
 * This deliberately uses the same managed realtime session surface as the app rather than the
 * unrelated batch-TTS voice picker. It asks Gemini/Charon or OpenAI/cedar to read each fixed phrase,
 * captures the provider's 24 kHz PCM output, validates the provider output transcription, and only
 * then writes deterministic PCM16 WAV files under Desktop/Sources/Resources/VoicePhrases/.
 *
 * No token or credential is written to the output. The manifest contains only provider/model/voice,
 * phrase/transcription, format, and audio hashes. The generated WAV bytes are intentionally not
 * committed by this script; review and add them explicitly after a successful run.
 *
 * Usage:
 *   node scripts/generate-realtime-voice-phrases.mjs \
 *     --auth-export desktop/tmp/desktop-auth.json --provider both
 *
 * Use --plan to inspect the exact filenames and provider voices without any network calls.
 */

import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import WebSocket from "ws";

const execFileAsync = promisify(execFile);
const defaultOutput = fileURLToPath(new URL("../../Desktop/Sources/Resources/VoicePhrases/", import.meta.url));
const defaultFirebasePlist = "/Applications/Omi Dev.app/Contents/Resources/GoogleService-Info.plist";
const defaultBackend = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app";

const phrasesByKind = {
  "deeper-thinking": [
    "Let me think that through.",
    "Give me a moment to think that through.",
    "Let me dig into that.",
    "I'll take a closer look.",
  ],
  "public-web-search": [
    "Let me look that up.",
    "I'll check the latest on that.",
    "Let me verify that.",
    "Checking the latest now.",
  ],
};

const profiles = {
  gemini: {
    provider: "gemini",
    voiceName: "Charon",
    model: "models/gemini-3.1-flash-live-preview",
    websocket:
      "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained",
  },
  openai: {
    provider: "openai",
    voiceName: "cedar",
    model: "gpt-realtime-2",
    websocket: "wss://api.openai.com/v1/realtime?model=gpt-realtime-2",
  },
};

function parseArgs(argv) {
  const options = {
    providers: ["gemini", "openai"],
    output: defaultOutput,
    timeoutMs: 60_000,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = () => {
      const next = argv[++i];
      if (!next) throw new Error(`${arg} requires a value`);
      return next;
    };
    if (arg === "--provider") options.providers = value().split(",");
    else if (arg === "--auth-export") options.authExport = value();
    else if (arg === "--firebase-plist") options.firebasePlist = value();
    else if (arg === "--backend") options.backend = value();
    else if (arg === "--out") options.output = value();
    else if (arg === "--kind") options.kinds = new Set(value().split(","));
    else if (arg === "--phrase") options.phrase = value();
    else if (arg === "--timeout-ms") options.timeoutMs = Number.parseInt(value(), 10);
    else if (arg === "--plan") options.plan = true;
    else if (arg === "--help") options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (options.providers.length === 1 && options.providers[0] === "both") {
    options.providers = ["gemini", "openai"];
  }
  if (options.providers.some((provider) => !profiles[provider])) {
    throw new Error("--provider must contain gemini, openai, or both");
  }
  if (!Number.isInteger(options.timeoutMs) || options.timeoutMs < 1) {
    throw new Error("--timeout-ms must be a positive integer");
  }
  const kinds = Object.keys(phrasesByKind).filter((kind) => !options.kinds || options.kinds.has(kind));
  if (kinds.length === 0) throw new Error("no acknowledgement kinds selected");
  if (options.kinds && [...options.kinds].some((kind) => !phrasesByKind[kind])) {
    throw new Error("--kind must contain deeper-thinking or public-web-search");
  }
  options.kinds = kinds;
  return options;
}

function usage() {
  return `Usage: node scripts/generate-realtime-voice-phrases.mjs --auth-export PATH [options]

Generate native realtime acknowledgement clips with the exact managed provider voices:
  gemini -> Charon
  openai -> cedar

  --provider gemini,openai,both  providers to generate (default: both)
  --auth-export PATH              output from scripts/omi-auth-dump.sh
  --firebase-plist PATH           Firebase plist (default: Omi Dev app)
  --backend URL                   Omi backend (default: development desktop backend)
  --out PATH                      VoicePhrases output directory
  --kind KIND[,KIND]              deeper-thinking and/or public-web-search
  --phrase TEXT                   generate only one exact phrase
  --timeout-ms N                  per-session timeout (default: 60000)
  --plan                          print filenames/voices without auth or network calls
`;
}

function slug(phrase) {
  return phrase
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\u0027\u2019]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function fileName(profile, kind, phrase) {
  return `${profile.provider}-${profile.voiceName.toLowerCase()}-${kind}-${slug(phrase)}.wav`;
}

function normalizeTranscript(value) {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\u0027\u2019]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function writeWav(pcm) {
  if (pcm.length === 0 || pcm.length % 2 !== 0) {
    throw new Error(`provider returned invalid PCM16 payload (${pcm.length} bytes)`);
  }
  const header = Buffer.alloc(44);
  header.write("RIFF", 0, "ascii");
  header.writeUInt32LE(36 + pcm.length, 4);
  header.write("WAVE", 8, "ascii");
  header.write("fmt ", 12, "ascii");
  header.writeUInt32LE(16, 16); // PCM fmt chunk size
  header.writeUInt16LE(1, 20); // WAVE_FORMAT_PCM
  header.writeUInt16LE(1, 22); // mono
  header.writeUInt32LE(24_000, 24);
  header.writeUInt32LE(24_000 * 2, 28); // byte rate
  header.writeUInt16LE(2, 32); // block alignment
  header.writeUInt16LE(16, 34); // bits per sample
  header.write("data", 36, "ascii");
  header.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([header, pcm]);
}

function parseJSON(data) {
  try {
    return JSON.parse(Buffer.from(data).toString("utf8"));
  } catch {
    return null;
  }
}

async function firebaseIDToken(options) {
  if (process.env.OMI_AUTH_TOKEN) return process.env.OMI_AUTH_TOKEN;
  if (!options.authExport) throw new Error("set OMI_AUTH_TOKEN or pass --auth-export");
  const auth = JSON.parse(await readFile(options.authExport, "utf8"));
  const refreshToken = auth.auth_refreshToken?.value;
  if (!refreshToken) throw new Error("auth export does not contain auth_refreshToken.value");
  const { stdout: apiKey } = await execFileAsync("/usr/libexec/PlistBuddy", [
    "-c", "Print :API_KEY", options.firebasePlist ?? defaultFirebasePlist,
  ]);
  const body = new URLSearchParams({ grant_type: "refresh_token", refresh_token: refreshToken });
  const response = await fetch(
    `https://securetoken.googleapis.com/v1/token?key=${encodeURIComponent(apiKey.trim())}`,
    { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body },
  );
  if (!response.ok) throw new Error(`Firebase refresh failed (${response.status})`);
  const refreshed = await response.json();
  if (!refreshed.id_token) throw new Error("Firebase refresh returned no id_token");
  return refreshed.id_token;
}

async function mintManagedRealtimeToken(options, idToken, provider) {
  const backend = options.backend ?? process.env.OMI_DESKTOP_API_URL ?? defaultBackend;
  const response = await fetch(`${backend.replace(/\/$/, "")}/v2/realtime/session`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (!response.ok) throw new Error(`${provider} token mint failed (${response.status})`);
  const payload = await response.json();
  if (typeof payload.token !== "string" || payload.token.length === 0) {
    throw new Error(`${provider} token mint returned no token`);
  }
  return payload.token;
}

function websocketFor(profile, token) {
  if (profile.provider === "gemini") {
    const url = new URL(profile.websocket);
    url.searchParams.set("access_token", token);
    return new WebSocket(url);
  }
  return new WebSocket(profile.websocket, { headers: { Authorization: `Bearer ${token}` } });
}

function geminiSetup(profile) {
  return {
    setup: {
      model: profile.model,
      generationConfig: {
        responseModalities: ["AUDIO"],
        temperature: 0,
        speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: profile.voiceName } } },
      },
      systemInstruction: {
        parts: [{ text: "Read the user's sentence verbatim exactly once, with no preamble or trailing words." }],
      },
      outputAudioTranscription: {},
    },
  };
}

function openAISetup(profile) {
  return {
    type: "session.update",
    session: {
      type: "realtime",
      model: profile.model,
      output_modalities: ["audio"],
      instructions: "Read the user's sentence verbatim exactly once, with no preamble or trailing words.",
      audio: {
        output: { format: { type: "audio/pcm", rate: 24_000 }, voice: profile.voiceName },
      },
    },
  };
}

function openAIRequest(phrase) {
  return [
    {
      type: "conversation.item.create",
      item: { type: "message", role: "user", content: [{ type: "input_text", text: phrase }] },
    },
    { type: "response.create", response: { output_modalities: ["audio"] } },
  ];
}

async function generateAudio(profile, token, phrase, timeoutMs) {
  const socket = websocketFor(profile, token);
  return new Promise((resolve, reject) => {
    const audio = [];
    let transcript = "";
    let settled = false;
    const timeout = setTimeout(() => finish(new Error(`${profile.provider} session timed out`)), timeoutMs);

    function finish(error, result) {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      try { socket.close(); } catch { /* socket may not have opened */ }
      if (error) reject(error);
      else resolve({ pcm: Buffer.concat(audio), transcript });
    }

    socket.on("open", () => {
      socket.send(JSON.stringify(profile.provider === "gemini" ? geminiSetup(profile) : openAISetup(profile)));
    });
    socket.on("message", (data) => {
      const message = parseJSON(data);
      if (!message) return;

      if (profile.provider === "gemini") {
        if (message.error) {
          finish(new Error(`Gemini realtime error: ${message.error.message ?? "unknown error"}`));
          return;
        }
        if (message.setupComplete) {
          socket.send(JSON.stringify({
            clientContent: { turns: [{ role: "user", parts: [{ text: phrase }] }], turnComplete: true },
          }));
        }
        const server = message.serverContent;
        const output = server?.outputTranscription?.text;
        if (typeof output === "string") transcript += output;
        for (const part of server?.modelTurn?.parts ?? []) {
          const inline = part.inlineData;
          if (inline?.mimeType?.includes("audio/pcm") && typeof inline.data === "string") {
            const chunk = Buffer.from(inline.data, "base64");
            if (chunk.length > 0) audio.push(chunk);
          }
        }
        if (server?.turnComplete === true) finish(null, { pcm: Buffer.concat(audio), transcript });
        return;
      }

      if (message.type === "error") {
        finish(new Error(`OpenAI realtime error: ${message.error?.message ?? "unknown error"}`));
      } else if (message.type === "session.updated") {
        for (const request of openAIRequest(phrase)) socket.send(JSON.stringify(request));
      } else if (message.type === "response.output_audio.delta" && typeof message.delta === "string") {
        const chunk = Buffer.from(message.delta, "base64");
        if (chunk.length > 0) audio.push(chunk);
      } else if (message.type === "response.output_audio_transcript.delta" && typeof message.delta === "string") {
        transcript += message.delta;
      } else if (message.type === "response.done") {
        finish(null, { pcm: Buffer.concat(audio), transcript });
      }
    });
    socket.on("error", (error) => finish(error));
    socket.on("close", (code, reason) => {
      if (!settled) finish(new Error(`${profile.provider} socket closed (${code}): ${reason.toString()}`));
    });
  });
}

function selectedPhrases(options) {
  return options.kinds.flatMap((kind) => {
    const phrases = phrasesByKind[kind];
    return options.phrase ? phrases.filter((phrase) => phrase === options.phrase).map((phrase) => ({ kind, phrase })) : phrases.map((phrase) => ({ kind, phrase }));
  });
}

function plan(options) {
  return options.providers.flatMap((provider) => {
    const profile = profiles[provider];
    return selectedPhrases(options).map(({ kind, phrase }) => ({
      provider,
      voiceName: profile.voiceName,
      model: profile.model,
      kind,
      phrase,
      file: fileName(profile, kind, phrase),
    }));
  });
}

const options = parseArgs(process.argv.slice(2));
if (options.help) {
  process.stdout.write(usage());
  process.exit(0);
}
const work = plan(options);
if (work.length === 0) throw new Error("no phrases selected");
if (options.plan) {
  process.stdout.write(`${JSON.stringify({ output: options.output, assets: work }, null, 2)}\n`);
  process.exit(0);
}

const idToken = await firebaseIDToken(options);
const generated = [];
for (const provider of options.providers) {
  const profile = profiles[provider];
  for (const { kind, phrase } of selectedPhrases(options)) {
    // The backend mints one-use Gemini tokens (and short-lived OpenAI client secrets), so mint a
    // fresh managed session token for every phrase rather than attempting to reuse a spent token.
    const token = await mintManagedRealtimeToken(options, idToken, provider);
    process.stderr.write(`Generating ${provider}/${profile.voiceName}: ${phrase}\n`);
    const result = await generateAudio(profile, token, phrase, options.timeoutMs);
    const expected = normalizeTranscript(phrase);
    const actual = normalizeTranscript(result.transcript);
    if (actual !== expected) {
      throw new Error(`${provider} transcription mismatch for ${JSON.stringify(phrase)}: got ${JSON.stringify(result.transcript)}`);
    }
    const wav = writeWav(result.pcm);
    generated.push({
      file: fileName(profile, kind, phrase),
      provider,
      voiceName: profile.voiceName,
      model: profile.model,
      kind,
      phrase,
      transcription: result.transcript,
      sha256: createHash("sha256").update(wav).digest("hex"),
      bytes: wav.length,
      wav,
    });
  }
}

await mkdir(options.output, { recursive: true });
for (const item of generated) {
  await writeFile(`${options.output}/${item.file}`, item.wav);
}
const manifest = {
  schemaVersion: 1,
  generator: "desktop/macos/agent/scripts/generate-realtime-voice-phrases.mjs",
  generationMethod: "managed_realtime_session",
  sessionRoute: "/v2/realtime/session",
  format: { container: "WAV", encoding: "PCM_S16LE", sampleRateHz: 24_000, channels: 1 },
  assets: generated.map(({ wav: _wav, ...metadata }) => metadata),
};
await writeFile(`${options.output}/manifest.json`, `${JSON.stringify(manifest, null, 2)}\n`);
process.stdout.write(`Generated ${generated.length} realtime voice phrase assets in ${options.output}\n`);
