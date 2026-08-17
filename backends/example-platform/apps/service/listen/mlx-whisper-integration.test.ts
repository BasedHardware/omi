// domain-pending(DIV-DOMCORE-012)

import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";

import { createLocalDevService } from "../app-facing";
import { createEmptyChatGenerationContextSource } from "../chat/generation-context";
import { createScriptedChatGenerationSource } from "../chat/generation-source";
import { resolveDevSttConfig } from "./mlx-whisper-boot";
import { createMlxWhisperTranscriptionSource } from "./mlx-whisper-transcription-source";

const ACCOUNT = "listen-stt-integration";
const SESSION = "b3c1d8e0-4a2f-4c11-9d77-2f0c1a9b7e10";

const sttConfig = (() => {
  try {
    return resolveDevSttConfig({
      OMI_STT_ENGINE: process.env.OMI_STT_ENGINE,
      OMI_STT_MODEL: process.env.OMI_STT_MODEL,
      OMI_STT_VENV: process.env.OMI_STT_VENV,
    });
  } catch {
    return { kind: "scripted" as const };
  }
})();

const it = sttConfig.kind === "mlx-whisper" ? test : test.skip;

const pcmFromWav = (bytes: Uint8Array): Uint8Array => {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.byteLength < 12 || String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!) !== "RIFF") {
    throw new Error("fixture is not a RIFF WAV");
  }
  let offset = 12;
  while (offset + 8 <= bytes.byteLength) {
    const id = String.fromCharCode(bytes[offset]!, bytes[offset + 1]!, bytes[offset + 2]!, bytes[offset + 3]!);
    const size = view.getUint32(offset + 4, true);
    if (id === "data") return bytes.subarray(offset + 8, offset + 8 + size);
    offset += 8 + size + (size % 2);
  }
  throw new Error("WAV data chunk missing");
};

const spokenFixture = (directory: string): Uint8Array => {
  const aiff = join(directory, "fixture.aiff");
  const wav = join(directory, "fixture.wav");
  const spoken = "Harborline cafe on cedar loop opens at eight in the morning and the lamps are already lit.";
  const say = Bun.spawnSync(["say", "-o", aiff, spoken], {
    stdout: "pipe",
    stderr: "pipe",
  });
  if (say.exitCode !== 0) {
    throw new Error(`say failed: ${say.stderr.toString()}`);
  }
  const convert = Bun.spawnSync(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", aiff, wav], {
    stdout: "pipe",
    stderr: "pipe",
  });
  if (convert.exitCode !== 0) {
    throw new Error(`afconvert failed: ${convert.stderr.toString()}`);
  }
  return pcmFromWav(readFileSync(wav));
};

it("mlx whisper transcribes a spoken fixture through /v4/listen", async () => {
  if (sttConfig.kind !== "mlx-whisper") return;
  const directory = mkdtempSync(join(tmpdir(), "omi-stt-fixture-"));
  const pcm = spokenFixture(directory);
  const source = createMlxWhisperTranscriptionSource({
    subprocess: {
      pythonPath: sttConfig.pythonPath,
      workerPath: sttConfig.workerPath,
      model: sttConfig.model,
      hfHome: sttConfig.hfHome,
    },
    windowSeconds: 3,
    idleFlushMs: 400,
  });
  const db = new Database(":memory:");
  const service = createLocalDevService({
    db,
    ownerAccountId: ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: "listen-stt-integration",
    transcriptionSource: source,
    generationSource: createScriptedChatGenerationSource(),
    generationContext: createEmptyChatGenerationContextSource(),
    listenDefaultUnmetered: true,
  });
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch: service.app.fetch,
    websocket: service.websocket,
  });
  const frames: unknown[] = [];
  try {
    await source.engine.waitUntilReady();
    const socket = new WebSocket(
      `ws://127.0.0.1:${server.port}/v4/listen?client_conversation_id=${SESSION}`
      + "&codec=pcm16&sample_rate=16000&channels=1",
      { headers: { authorization: `Bearer ${service.devToken}` } },
    );
    const opened = new Promise<void>((resolve, reject) => {
      socket.addEventListener("open", () => resolve(), { once: true });
      socket.addEventListener("error", () => reject(new Error("listen socket failed")), {
        once: true,
      });
    });
    socket.addEventListener("message", (event) => {
      frames.push(JSON.parse(String(event.data)));
    });
    await opened;
    const chunk = 4_096;
    for (let offset = 0; offset < pcm.byteLength; offset += chunk) {
      socket.send(pcm.subarray(offset, Math.min(offset + chunk, pcm.byteLength)));
    }
    const deadline = Date.now() + 60_000;
    let sawTranscript = false;
    while (Date.now() < deadline) {
      const transcripts = frames.filter((frame) => Array.isArray(frame) && frame.length > 0);
      if (transcripts.length > 0) {
        if (!sawTranscript) {
          sawTranscript = true;
          // Keep the socket open so idle-flush of the remainder can emit.
          await Bun.sleep(1_500);
          break;
        }
      }
      await Bun.sleep(50);
    }
    const transcripts = frames.filter((frame): frame is readonly { readonly text: string }[] => (
      Array.isArray(frame) && frame.length > 0 && typeof frame[0]?.text === "string"
    ));
    const text = transcripts.flat().map((segment) => segment.text).join(" ").trim();
    expect(text.length).toBeGreaterThan(0);
    socket.close(1000, "done");
    const settings = await service.app.request("/v1/settings", {
      headers: { authorization: `Bearer ${service.devToken}` },
    });
    const body = await settings.json() as {
      readonly entitlement: { readonly used: number };
    };
    expect(body.entitlement.used).toBeGreaterThan(0);
    process.stdout.write(`${JSON.stringify({
      transcripts,
      meteredSeconds: body.entitlement.used,
      pcmBytes: pcm.byteLength,
    })}\n`);
  } finally {
    server.stop(true);
    await source.dispose();
    db.close();
    rmSync(directory, { recursive: true, force: true });
  }
}, 120_000);
