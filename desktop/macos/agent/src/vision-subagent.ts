/**
 * Vision subagent support (local provider only).
 *
 * pi-subagents (loaded as a Pi package — see pi-mono-extension) resolves
 * custom agent roles from markdown files with YAML frontmatter under
 * ~/.pi/agent/agents/. The model a role is pinned to has no env-var
 * indirection in that frontmatter, so the resolved "omi-local-vision/<id>"
 * string has to be baked into the file at bridge-start time, since the id
 * is a Settings-time choice and isn't knowable at build time.
 *
 * Extracted to a separate module (like mime-detect.ts) so index.ts and
 * runtime/jsonl-transport.ts can share it without a circular import.
 */
import { homedir, tmpdir } from "os";
import { join } from "path";
import { mkdirSync, unlinkSync, writeFileSync } from "fs";

const PI_USER_AGENTS_DIR = join(homedir(), ".pi", "agent", "agents");
const VISION_AGENT_PATH = join(PI_USER_AGENTS_DIR, "omi-vision.md");

/** Writes (or removes) the "vision" subagent definition. Called once per
 *  bridge start with the current OMI_LOCAL_VISION_MODEL_ID. Removing the
 *  file when the setting is unset keeps behavior identical to today for
 *  anyone who hasn't configured a vision model.
 *
 *  `async: false` pins this role to foreground (synchronous) execution.
 *  pi-subagents' background-child runner resolves its host peer packages
 *  (including `@earendil-works/chord`) from whatever `@earendil-works/
 *  pi-coding-agent` Node's module resolution finds on this machine — which,
 *  via the user's own separately-installed global `pi` CLI, is currently
 *  0.84.3. `chord` only exists starting at pi-coding-agent 0.85.0, so any
 *  async/background subagent call fails before it can spawn. Foreground
 *  execution never touches that machinery, so pinning async off here
 *  sidesteps the version gap entirely without touching the user's global
 *  pi install or ~/.pi/agent/settings.json.
 *
 *  `extensions: <path>` explicitly loads pi-mono-extension for this child
 *  session. A foreground subagent does NOT automatically inherit the parent
 *  pi process's "ambient" extensions unless told to — without this, the
 *  child's own model registry never learns about the "omi-local-vision"
 *  provider (registered by that same extension file), and model resolution
 *  fails with `Model "omi-local-vision/<id>" not found`. */
export function syncVisionSubagentFile(
  visionModelId: string | undefined,
  extensionPath: string,
  logErr: (message: string) => void,
): void {
  if (!visionModelId) {
    try {
      unlinkSync(VISION_AGENT_PATH);
    } catch {
      // Not present — nothing to clean up.
    }
    return;
  }
  const frontmatter = `---
name: vision
description: Interprets on-screen screenshots and images. Delegate to this agent whenever you need to see or describe what is on screen.
tools: read
model: omi-local-vision/${visionModelId}
systemPromptMode: replace
inheritProjectContext: false
inheritGlobalContext: false
inheritSkills: false
async: false
extensions: ${extensionPath}
---

You are a vision specialist. You will be given the absolute path to an image file (a screenshot). Use the read tool to load it, then answer the requesting agent's question or describe what it shows in enough detail for them to act on it without seeing the image themselves.
`;
  try {
    mkdirSync(PI_USER_AGENTS_DIR, { recursive: true });
    writeFileSync(VISION_AGENT_PATH, frontmatter);
    logErr(`Pi-mono: wrote vision subagent definition (model=${visionModelId})`);
  } catch (err) {
    logErr(`Pi-mono: failed to write vision subagent definition: ${err}`);
  }
}

/** Extension used for the on-disk screenshot handed to the vision subagent.
 *  Falls back to png for any mime type detectImageMimeType doesn't return. */
const SCREENSHOT_EXT_BY_MIME: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
};

/** Directory the vision screenshot is written into. Exported so
 *  pi-mono-extension's read-gate (classifyVisionScreenshotRead) can confine
 *  its deny rule to this exact location instead of matching any file on disk
 *  that happens to share the screenshot's basename. Single source of truth
 *  for "where the screenshot lives," shared by the writer here and the
 *  reader there. */
export function visionScreenshotDirectory(): string {
  return tmpdir();
}

/** Writes a screenshot to a fixed path (overwritten per query — pi-mono RPC
 *  only handles one prompt at a time, so there's no concurrent-write race)
 *  and returns the absolute path for the model to hand to the vision
 *  subagent instead of the raw image bytes. */
export function writeScreenshotForVisionSubagent(base64Data: string, mimeType: string): string {
  const ext = SCREENSHOT_EXT_BY_MIME[mimeType] ?? "png";
  const path = join(visionScreenshotDirectory(), `omi-screen.${ext}`);
  writeFileSync(path, Buffer.from(base64Data, "base64"));
  return path;
}
