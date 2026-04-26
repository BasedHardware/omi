/**
 * Companion Assistant — orchestrates the PTT → screen capture → Gemini →
 * overlay animation pipeline.
 *
 * Called by `companion.ts` event listeners:
 *   - handleCompanionStart(): invoked on `companion:start`
 *   - handleCompanionStop():  invoked on `companion:stop`
 *
 * Rust side (Phase 2 Rust subagent — not yet landed):
 *   - `plugin:audio-capture|start_recording` with `{ mic_only: true }` returns
 *     a session handle and starts recording mic audio only.
 *   - `plugin:audio-capture|stop_recording` returns
 *     `{ wav_path, duration_ms, sample_rate, channels }` for mic_only sessions.
 *   - `plugin:screen-capture|take_screenshot_with_ocr` response now includes a
 *     `display` field with `{ display_id, capture_width_px, capture_height_px,
 *      display_width_px, display_height_px, display_scale_factor,
 *      display_origin_pt, display_size_pt }`.
 *
 * Until those land, the calls are guarded defensively — missing fields log
 * and abort gracefully without throwing.
 */

import { invoke } from "@tauri-apps/api/core";
import { emit, listen, type UnlistenFn } from "@tauri-apps/api/event";

import { useCompanionStore } from "@/stores/companionStore";
import type { CaptureDisplayMeta } from "@/services/coordinateMap";
import { imageToOverlayPoint } from "@/services/coordinateMap";
import type { OcrBlock } from "@/services/rewind";
import { takeScreenshotWithOcr } from "@/services/rewind";
import { useCompanionSettingsStore } from "@/stores/companionSettingsStore";

// ---------------------------------------------------------------------------
// Error mapping
// ---------------------------------------------------------------------------

/**
 * Maps a Gemini HTTP status code (or a caught error) to a short, actionable
 * one-line message suitable for display in the speech bubble / error badge.
 *
 * Rules:
 *   - 401 → API key missing or invalid
 *   - 429 → rate-limited
 *   - 5xx → transient server error
 *   - network / unknown → generic retry message
 */
export function mapGeminiErrorToMessage(status: number | null, err: unknown): string {
  if (status === 401) return "AI key missing or invalid — check Settings.";
  if (status === 429) return "AI rate limit hit — wait a moment and try again.";
  if (status !== null && status >= 500 && status < 600) return "AI service error — try again shortly.";
  if (status !== null && status >= 400 && status < 500) return "AI request failed — please try again.";
  // Network / fetch error (status is null or 0)
  const msg = err instanceof Error ? err.message : String(err);
  if (/timeout|timed out/i.test(msg)) return "Request timed out — check your connection.";
  if (/network|fetch|Failed to fetch/i.test(msg)) return "Couldn't reach AI — check your connection.";
  return "Couldn't reach AI — try again.";
}

/** Duration (ms) before an error message is automatically cleared from the store. */
const ERROR_CLEAR_DELAY_MS = 5_000;

/**
 * Set an error message on the store, speak a brief TTS notification (if
 * speakError is true), and auto-clear after ERROR_CLEAR_DELAY_MS.
 */
function setErrorAndAutoClear(message: string, speakError: boolean): void {
  const store = useCompanionStore.getState();
  store.setErrorMessage(message);
  store.setState("idle");

  if (speakError) {
    invoke("plugin:tts|tts_speak", { text: "I couldn't answer that — please try again." }).catch(
      () => {
        // TTS sidecar may not be running yet on first session — safe to swallow.
      },
    );
  }

  window.setTimeout(() => {
    // Only clear if the message hasn't already been replaced by a new error.
    if (useCompanionStore.getState().errorMessage === message) {
      useCompanionStore.getState().setErrorMessage(null);
    }
  }, ERROR_CLEAR_DELAY_MS);
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";

/**
 * Duration (ms) to display overlay points before fading them out.
 * Passed to CompanionOverlay via the `companion:points` event.
 */
const OVERLAY_DURATION_MS = 2500;

// ---------------------------------------------------------------------------
// Types — mic-only session wire shape (Rust Phase 2)
// ---------------------------------------------------------------------------

/**
 * Response shape of `plugin:audio-capture|stop_recording`.
 *
 * The Rust side always returns the flattened `CaptureState` fields and
 * *optionally* `companion_recording` — populated only when the session was
 * started with `mic_only: true`. Non-mic-only callers (Whispr meeting
 * capture) get `companion_recording: null` and use the flat fields.
 */
interface StopRecordingResult {
  is_capturing: boolean;
  device_name: string | null;
  sample_rate: number;
  system_audio_active: boolean;
  mic_samples_total: number;
  sys_samples_total: number;
  companion_recording: CompanionRecording | null;
}

interface CompanionRecording {
  wav_path: string;
  duration_ms: number;
  sample_rate: number;
  channels: number;
}

// ---------------------------------------------------------------------------
// Gemini API key (reuse the same invoke used by focusAssistant)
// ---------------------------------------------------------------------------

let cachedApiKey: string | null = null;

async function getGeminiApiKey(): Promise<string> {
  if (cachedApiKey) return cachedApiKey;
  const key = await invoke<string | null>("get_gemini_api_key");
  if (!key) throw new Error("GEMINI_API_KEY not configured");
  cachedApiKey = key;
  return key;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Encode a Uint8Array to a base64 string without DOM APIs. */
function uint8ToBase64(bytes: Uint8Array): string {
  // Node/browser-compatible approach using btoa + charCodeAt.
  let binary = "";
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Read a file from the filesystem via Tauri IPC.
 *
 * We call the Rust `read_file_bytes` command rather than importing
 * @tauri-apps/plugin-fs (not in package.json) to keep the dep footprint small.
 * This command is already implemented in the Tauri backend as a utility for
 * other features; if it's not yet there, we fall back gracefully.
 */
async function readFileBytesViaIpc(path: string): Promise<Uint8Array> {
  const bytes = await invoke<number[]>("read_file_bytes", { path });
  return new Uint8Array(bytes);
}

/** Mirror a diagnostic message to the Rust stderr terminal (via the
 *  `term_log` command) so we can trace the post-stop pipeline without
 *  needing devtools open. Fire-and-forget. */
function termLog(msg: string): void {
  invoke("term_log", { msg }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Gemini companion call
// ---------------------------------------------------------------------------

interface GeminiCompanionResponse {
  answer: string;
  points: Array<{ x: number; y: number; label: string }>;
  /** When the user's question implies a sequence of clicks, Gemini returns
   *  up to 4 steps here. Required field but may be an empty array for Mode A
   *  single-shot answers — making it required forces Gemini to actively
   *  decide each call instead of defaulting to "single answer" by omission. */
  steps: Array<{ instruction: string; target_label: string }>;
  /** Gemini's transcription of the user's spoken question. Used for the
   *  procedural-retry heuristic (if `steps` is empty but the question was
   *  a how-to, retry once with explicit chain-mode directive). Best-effort —
   *  may be empty if Gemini doesn't transcribe. */
  transcript?: string;
}

/** Hard cap on chain length. Keeps the experience tight and bounds latency
 *  (each step costs one AX lookup or one Gemini grounding call). */
const MAX_CHAIN_STEPS = 4;

/**
 * Call Gemini with a combined audio + image request and return structured
 * `{ answer, points }` where points are in capture pixel space.
 */
async function askCompanion(
  imageBase64: string,
  wavBase64: string,
  captureMeta: { width: number; height: number },
  displayMeta: CaptureDisplayMeta | null,
  ocrBlocks: OcrBlock[],
): Promise<GeminiCompanionResponse> {
  const [dockIcons, activeApp] = await Promise.all([fetchDockIcons(), fetchActiveApp()]);
  let result = await callGeminiStructured([
    { text: companionSystemPrompt(dockIcons, activeApp) },
    { inline_data: { mime_type: "image/jpeg", data: imageBase64 } },
    { inline_data: { mime_type: "audio/wav", data: wavBase64 } },
  ]);
  result = await maybeRetryAsChain(result, dockIcons, activeApp, [
    { inline_data: { mime_type: "image/jpeg", data: imageBase64 } },
    { inline_data: { mime_type: "audio/wav", data: wavBase64 } },
  ]);
  const denorm = denormalizePoints(result, captureMeta);
  const dockGrounded = groundDockPoints(denorm, dockIcons, captureMeta, displayMeta);
  return groundOcrPoints(dockGrounded, ocrBlocks, captureMeta);
}

/**
 * Text-only variant of askCompanion — same image + structured output but the
 * question comes as a string instead of inline audio.  Used by the Settings
 * "Run test task" button so the whole pipeline can be exercised without a
 * microphone.
 */
async function askCompanionText(
  imageBase64: string,
  question: string,
  captureMeta: { width: number; height: number },
  displayMeta: CaptureDisplayMeta | null,
  ocrBlocks: OcrBlock[],
): Promise<GeminiCompanionResponse> {
  const [dockIcons, activeApp] = await Promise.all([fetchDockIcons(), fetchActiveApp()]);
  let result = await callGeminiStructured([
    { text: `${companionSystemPrompt(dockIcons, activeApp)}\n\nQuestion: ${question}` },
    { inline_data: { mime_type: "image/jpeg", data: imageBase64 } },
  ]);
  // Inject the question into the transcript field so the retry heuristic has
  // something to inspect (the text variant doesn't get audio transcription).
  if (!result.transcript) result = { ...result, transcript: question };
  result = await maybeRetryAsChain(
    result,
    dockIcons,
    activeApp,
    [{ inline_data: { mime_type: "image/jpeg", data: imageBase64 } }],
    question,
  );
  const denorm = denormalizePoints(result, captureMeta);
  const dockGrounded = groundDockPoints(denorm, dockIcons, captureMeta, displayMeta);
  return groundOcrPoints(dockGrounded, ocrBlocks, captureMeta);
}

/** Procedural-question retry: when Gemini's first call returned `steps: []`
 *  but the transcript or answer reads like a how-to, send a second call with
 *  a hard-coded "use chain mode" directive. Catches the case where Gemini
 *  parrots the summary phrasing from the prompt example but skips the chain.
 *
 *  Only fires when there's strong evidence of procedural intent — a single
 *  bad guess wastes a Gemini call but is bounded to one retry. */
async function maybeRetryAsChain(
  initial: GeminiCompanionResponse,
  _dockIcons: DockIcon[],
  _activeApp: ActiveApp,
  mediaParts: Array<Record<string, unknown>>,
  questionOverride?: string,
): Promise<GeminiCompanionResponse> {
  if (initial.steps && initial.steps.length > 0) return initial;

  const transcript = (questionOverride || initial.transcript || "").toLowerCase();
  const answer = (initial.answer || "").toLowerCase();
  const proceduralPattern =
    /\bhow (do|can) i\b|\bhow to\b|\bwhere (do|can) i\b|\bwhere is\b|\bshow me how\b|\bwalk me through\b|\bsteps? to\b|\bteach me\b|\bguide me\b/;
  const summaryPattern =
    /\bhere'?s how\b|\bi'?ll walk you through\b|\bstep by step\b|\blet me show\b|\bfollow these steps\b/;

  const looksProcedural =
    proceduralPattern.test(transcript) || summaryPattern.test(answer);
  if (!looksProcedural) return initial;

  termLog(
    `mode-mismatch retry: transcript="${transcript.slice(0, 60)}…" answer="${answer.slice(0, 60)}…" — re-asking with explicit chain directive`,
  );

  const retryPrompt =
    `The user asked a procedural / "how-to" question. Your previous response did not include ` +
    `a chain. Re-answer the same question, but this time you MUST return a non-empty "steps" ` +
    `array (1-${MAX_CHAIN_STEPS} entries) walking the user through the actions click-by-click.\n\n` +
    `Their question was: "${questionOverride || initial.transcript || "(see audio)"}"\n\n` +
    `Rules:\n` +
    `- The dock is always visible at the bottom of the screen — you can ALWAYS chain through ` +
    `a dock icon as step 1 (e.g., "System Settings").\n` +
    `- Steps 2-${MAX_CHAIN_STEPS} do NOT need to be visible in the current screenshot. The ` +
    `system re-screenshots after each click. Plan the full sequence anyway.\n` +
    `- Each step: { instruction: "Click ...", target_label: "exact dock name OR exact visible text" }.\n` +
    `- Set "answer" to a brief summary like "Here's how to back up your Mac — I'll walk you through it."\n` +
    `- Leave "points" as []. Set "transcript" to the question above.`;

  try {
    const retried = await callGeminiStructured([{ text: retryPrompt }, ...mediaParts]);
    if (retried.steps && retried.steps.length > 0) {
      termLog(`retry produced ${retried.steps.length}-step chain — using it`);
      return retried;
    }
    termLog(`retry still returned empty steps — keeping original Mode A answer`);
  } catch (e) {
    termLog(`retry failed: ${e instanceof Error ? e.message : String(e)}`);
  }
  return initial;
}

/**
 * Companion system prompt. Mirrors clicky's tone: short, direct.
 * Uses Gemini's native normalized [0..1000] coordinate space (Google's PaLI
 * grounding format).
 *
 * Shape-aware grounding: empirically, Gemini Flash + Pro both pick the wrong
 * specific icon (e.g. Calendar instead of System Settings) when given just
 * "find this icon", because the model defaults to typical-position priors
 * rather than verifying visual appearance. Naming the actual visual cues for
 * confusable icons cuts the error from "completely wrong icon" to "within
 * pixels of the correct icon" in our tests. The label-with-shape requirement
 * also acts as self-verification: the model has to commit to what it sees
 * before emitting coords. Client-side `denormalizePoints` converts to pixels.
 */
function companionSystemPrompt(dockIcons: DockIcon[], activeApp: ActiveApp): string {
  const dockList =
    dockIcons.length > 0
      ? `The user's macOS dock currently contains, in order from left to right:\n` +
        dockIcons.map((d) => `  - ${d.name}`).join("\n") +
        `\n\nIMPORTANT: when referring to a dock icon, use its EXACT name from the list above ` +
        `as the "label" field (case-sensitive). We will look up its precise position from macOS — ` +
        `you do not need to estimate dock-icon coordinates accurately, just emit any reasonable x/y ` +
        `near the bottom of the image and the system will snap to the correct icon. If you use any ` +
        `other label (paraphrase, generic word, partial match), we will NOT snap and will fall back ` +
        `to your raw pixel coordinates. If the target is NOT in the dock list above, do not point ` +
        `at the dock at all — point at where it actually appears (a menu, a window, a webpage) or ` +
        `leave points empty.\n\n`
      : "";

  // Active-app guidance: when the user is in a browser asking about a website,
  // they almost never want a dock click — they want help inside the browser.
  // Reminding Gemini of the active app and the browser-specific rule cuts
  // dock hallucinations dramatically.
  //
  // Skip the hint entirely when the active app is our own (Nooto / Companion)
  // — the user is testing the feature inside the debug pane and is asking
  // about something else; pinning Gemini to "you are in Nooto" misleads it.
  const appContext =
    activeApp.name && !isOwnApp(activeApp)
      ? `The user is currently in **${activeApp.name}**. Their question is most likely about ` +
        `something in this app, not about launching a different one. Only point at a dock ` +
        `icon if the user explicitly needs to LAUNCH or SWITCH to another app.${
          isBrowser(activeApp)
            ? ` ${activeApp.name} is a web browser — for navigation questions ("how do I get to X site", ` +
              `"open Y page"), the answer is usually to click the address bar, type a URL, and press ` +
              `Enter. Point at the address bar, not the dock.`
            : ""
        }\n\n`
      : "";

  return (
    `You are an AI assistant. You can see the user's screen. They have a question for you.\n\n` +
    `Be concise. 2-3 sentences max.\n\n` +
    appContext +
    dockList +
    `## Response modes — pick exactly one\n\n` +
    `Mode A — single answer:\n` +
    `  Use ONLY for "what is this?" / "what does this do?" / "summarize this" — questions ` +
    `with a single fact answer or no action to take. Fill "answer" + at most one "points" ` +
    `entry. Leave "steps" empty.\n\n` +
    `Mode B — guided multi-step chain (DEFAULT for ANY "how do I…", "where do I…", ` +
    `"show me how", "open … and …", "walk me through" question):\n` +
    `  When the user is asking how to DO something, even if you think they could figure it ` +
    `out from one hint, USE A CHAIN. The user wants to be walked through it click-by-click. ` +
    `One ring at a time appears on the right target, the user clicks it, the next ring ` +
    `appears, and so on.\n` +
    `  Fill "steps" with up to ${MAX_CHAIN_STEPS} sequential actions. Each step has:\n` +
    `    - "instruction": one sentence telling the user what to click NEXT, in second ` +
    `person ("Click …" / "Tap …" / "Type …"). Spoken aloud when the step appears.\n` +
    `    - "target_label": the EXACT name of the dock icon (preferred — snaps to macOS-reported ` +
    `coordinates), OR the EXACT visible text of the on-screen UI element ("Time Machine", ` +
    `"Users & Groups", "Sign In"). Use the label that's literally written on screen so ` +
    `OCR can ground it precisely.\n` +
    `  Set "answer" to a one-sentence summary ("Here's how to back up your Mac — I'll walk ` +
    `you through it.") and leave "points" empty.\n\n` +
    `### CRITICAL chain-mode rules\n\n` +
    `1. **The dock is ALWAYS visible at the bottom of the screen.** Even if the rest of the ` +
    `screen shows an unrelated app, you can ALWAYS plan a chain that starts by clicking a ` +
    `dock icon (System Settings, Finder, etc.). Never refuse to chain because "the right ` +
    `panel isn't open" — open it as step 1.\n` +
    `2. **Only step 1's target needs to be visible right now.** Steps 2-${MAX_CHAIN_STEPS} ` +
    `do NOT need to exist on the current screen. The system takes a fresh screenshot AFTER ` +
    `the user clicks each step, then re-locates the next target on the new screen. Trust ` +
    `that — plan the full sequence even if only step 1 is currently visible.\n` +
    `3. **For "how do I do X in macOS" questions, ALWAYS chain through the System Settings ` +
    `dock icon as step 1**, even if Settings isn't open. Example for "How do I back up my Mac?":\n` +
    `   steps: [\n` +
    `     { instruction: "Click System Settings in your dock.", target_label: "System Settings" },\n` +
    `     { instruction: "Click General in the sidebar.", target_label: "General" },\n` +
    `     { instruction: "Click Time Machine.", target_label: "Time Machine" },\n` +
    `     { instruction: "Click Back Up Now.", target_label: "Back Up Now" }\n` +
    `   ]\n` +
    `   Notice: only step 1 (the dock icon) is visible in the current screenshot. Steps 2-4 ` +
    `live inside Settings, which isn't open yet. Return them ANYWAY.\n\n` +
    `Other examples that MUST use chain mode (Mode B), never Mode A:\n` +
    `  - "How do I change my password?" → [System Settings → Users & Groups → Change Password]\n` +
    `  - "Where do I turn on dark mode?" → [System Settings → Appearance → Dark]\n` +
    `  - "How do I share this file?" → [Right-click → Share → AirDrop]\n\n` +
    `### Install / download / sign-up flows: plan the FULL flow, not just the launch step.\n\n` +
    `Don't emit a 1-step chain that ends at "open browser/app" and trusts the user to figure ` +
    `out the rest. Walk them through to the actual completion of the task. Examples:\n` +
    `  - "How do I install Node.js?" → [\n` +
    `      { instruction: "Click Google Chrome in your dock.", target_label: "Google Chrome" },\n` +
    `      { instruction: "Click the address bar and type nodejs.org, then press Enter.", target_label: "Address bar" },\n` +
    `      { instruction: "Click the LTS download button.", target_label: "Download Node.js (LTS)" },\n` +
    `      { instruction: "Open the downloaded .pkg in Finder and follow the installer.", target_label: "node-v" }\n` +
    `    ]\n` +
    `  - "How do I sign up for Notion?" → [Open browser → notion.so → Sign Up → Email field]\n` +
    `  - "How do I download a file from this page?" → [Find the download link → Click Download → Open Downloads folder]\n` +
    `Aim for 3-${MAX_CHAIN_STEPS} steps for install/download/sign-up tasks. A 1-step chain ` +
    `that stops at "open the app" is almost always wrong for a "how do I install X" question.\n\n` +
    `Single-step chains (1 entry in "steps") are valid for trivially-short tasks like ` +
    `"open Settings" or "show me the dock", where the user just needs one click. For ` +
    `anything with multiple click-able stages, plan all the stages.\n\n` +
    `Coordinates in "points" must be normalized 0-1000 where (0,0) is top-left and (1000,1000) ` +
    `is bottom-right. Never return both "points" and "steps" — pick one mode per question.`
  );
}

/**
 * Convert Gemini's normalized [0..1000] points to image-pixel coordinates so
 * the rest of the pipeline (coordinateMap.ts → overlay sprites) keeps working
 * unchanged. Clamps into [0, dim] to defend against the occasional out-of-range
 * value Gemini still emits.
 */
function denormalizePoints(
  resp: GeminiCompanionResponse,
  capture: { width: number; height: number },
): GeminiCompanionResponse {
  return {
    ...resp,
    points: resp.points.map((p) => ({
      x: Math.max(0, Math.min(capture.width, (p.x / 1000) * capture.width)),
      y: Math.max(0, Math.min(capture.height, (p.y / 1000) * capture.height)),
      label: p.label,
    })),
  };
}

/**
 * Dock-icon grounding via macOS Accessibility.
 *
 * Gemini's pixel-grounding for dock icons is unreliable — even with shape-
 * aware prompts and two-pass zoom, it often picks the wrong specific icon.
 * macOS exposes the dock's actual UI tree via `AXUIElement` though, which
 * gives us deterministic icon names + pixel positions. The Rust side
 * `get_dock_icons` shells out to `osascript` once per session and returns
 * `[{ name, x, y, w, h }, ...]` in screen-point coordinates.
 *
 * Strategy:
 *   1. Pre-fetch the dock list once per Gemini call and embed the names in
 *      the prompt as known anchors. Gemini is told "use the exact name as
 *      the label and we'll snap to the right icon".
 *   2. Post-Gemini, for each point we received, fuzzy-match its label
 *      against the dock list. On match, replace the LLM's coordinates with
 *      the AX-derived center (converted from screen points → image pixels
 *      using the captured display's scale + bounds).
 *
 * Result: dock pointing accuracy goes from "right area, wrong specific icon"
 * to pixel-perfect, with no extra Gemini round-trip.
 */
interface DockIcon {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

let dockIconsCache: { ts: number; icons: DockIcon[] } | null = null;
const DOCK_CACHE_TTL_MS = 5_000;

/** Fetch the macOS dock icon list, with a tiny in-memory cache so we don't
 *  spawn osascript on every Gemini call when the user holds PTT in rapid
 *  succession. The dock changes rarely; 5s of staleness is fine. */
async function fetchDockIcons(): Promise<DockIcon[]> {
  const now = Date.now();
  if (dockIconsCache && now - dockIconsCache.ts < DOCK_CACHE_TTL_MS) {
    return dockIconsCache.icons;
  }
  try {
    const icons = await invoke<DockIcon[]>("get_dock_icons");
    dockIconsCache = { ts: now, icons };
    return icons;
  } catch (e) {
    console.warn("[companionAssistant] get_dock_icons failed:", e);
    return [];
  }
}

interface ActiveApp {
  name: string;
  bundle_id: string;
}

/** Frontmost macOS app at PTT-press time. Used by the prompt to keep Gemini's
 *  answer in-context — when the user is in Chrome and asks about a website,
 *  we don't want a dock-icon answer. No cache: the active app changes faster
 *  than the dock and 30 ms per call is acceptable. */
async function fetchActiveApp(): Promise<ActiveApp> {
  try {
    return await invoke<ActiveApp>("get_active_app");
  } catch (e) {
    console.warn("[companionAssistant] get_active_app failed:", e);
    return { name: "", bundle_id: "" };
  }
}

/** Bundle ids of common web browsers. When the active app is a browser, the
 *  prompt gets an extra hint that the answer probably involves the browser
 *  window (address bar, tab, page content) and not a dock icon. */
const BROWSER_BUNDLE_IDS = new Set([
  "com.google.Chrome",
  "com.google.Chrome.canary",
  "com.apple.Safari",
  "org.mozilla.firefox",
  "com.microsoft.edgemac",
  "com.brave.Browser",
  "company.thebrowser.Browser", // Arc
  "com.vivaldi.Vivaldi",
  "com.operasoftware.Opera",
]);

function isBrowser(app: ActiveApp): boolean {
  if (BROWSER_BUNDLE_IDS.has(app.bundle_id)) return true;
  // Fallback heuristic for browsers we don't enumerate by bundle id.
  return /chrome|safari|firefox|edge|brave|arc|vivaldi|opera|browser/i.test(app.name);
}

/** Is the active app our own Companion / Nooto window? When the user is
 *  testing the feature inside the Settings → Companion debug pane, the
 *  frontmost app IS Nooto — telling Gemini "the user is in nooto-desktop-v2"
 *  anchors its answer to the wrong context. Treat these as "no specific app
 *  context" and let Gemini infer from the visible screen instead. */
function isOwnApp(app: ActiveApp): boolean {
  const id = app.bundle_id.toLowerCase();
  const name = app.name.toLowerCase();
  return (
    id.startsWith("com.togodynamics.nooto") ||
    id.startsWith("com.omi.") ||
    name.includes("nooto") ||
    name.includes("companion") ||
    name === "omi" ||
    name === "omi dev" ||
    name === "omi beta"
  );
}

/** Replace any Gemini point whose label matches a dock-icon name with the
 *  exact AX-derived center for that icon, converted to image-pixel space. */
function groundDockPoints(
  resp: GeminiCompanionResponse,
  dockIcons: DockIcon[],
  capture: { width: number; height: number },
  displayMeta: CaptureDisplayMeta | null,
): GeminiCompanionResponse {
  if (dockIcons.length === 0 || !displayMeta) return resp;

  const points = resp.points.map((p) => {
    const match = matchDockIcon(p.label, dockIcons);
    if (!match) return p;

    // AX gives us screen-point top-origin coords (relative to the global
    // screen layout). Subtract the display origin to get display-local
    // points, scale up to physical pixels, then scale down to image pixels.
    const localXPt = match.x + match.w / 2 - displayMeta.display_origin_pt.x;
    const localYPt = match.y + match.h / 2 - displayMeta.display_origin_pt.y;
    const displayPxX = localXPt * displayMeta.display_scale_factor;
    const displayPxY = localYPt * displayMeta.display_scale_factor;
    const imageScaleX = capture.width / displayMeta.display_width_px;
    const imageScaleY = capture.height / displayMeta.display_height_px;
    const imgX = displayPxX * imageScaleX;
    const imgY = displayPxY * imageScaleY;
    termLog(
      `dock-ground "${p.label}" → "${match.name}" @ AX(${Math.round(match.x + match.w / 2)},${Math.round(match.y + match.h / 2)}) → img_px(${Math.round(imgX)},${Math.round(imgY)})`,
    );
    return {
      x: Math.max(0, Math.min(capture.width, imgX)),
      y: Math.max(0, Math.min(capture.height, imgY)),
      label: match.name,
    };
  });

  return { ...resp, points };
}

/** Snap each point to the on-screen text it's referring to, when possible.
 *
 *  Gemini routinely returns coordinates that are "almost there" — the right
 *  area but offset by 20-80 px from the actual UI element. OCR runs against
 *  the same screenshot and gives us pixel-exact bounding boxes for every
 *  visible piece of text. If Gemini's `label` matches an OCR block's text,
 *  we replace the LLM's coordinates with the OCR box center.
 *
 *  Distance gate: we only accept a snap if the matched OCR block is within
 *  `OCR_SNAP_RADIUS_PX` of Gemini's original guess. Without that gate, a
 *  short label like "Open" could snap to any "Open" anywhere on screen.
 *
 *  Works in any app — including web browsers where AX-based grounding is
 *  unreliable. Free, since OCR already runs on every screenshot.
 */
const OCR_SNAP_RADIUS_PX = 200;
const OCR_MIN_LABEL_LEN = 3;

function groundOcrPoints(
  resp: GeminiCompanionResponse,
  ocrBlocks: OcrBlock[],
  capture: { width: number; height: number },
): GeminiCompanionResponse {
  if (ocrBlocks.length === 0) return resp;

  const points = resp.points.map((p) => {
    const snapped = snapToOcrText(p, ocrBlocks);
    if (!snapped) return p;
    termLog(
      `ocr-snap "${p.label}" → "${snapped.text}" px(${Math.round(p.x)},${Math.round(p.y)}) → (${Math.round(snapped.x)},${Math.round(snapped.y)})`,
    );
    return {
      x: Math.max(0, Math.min(capture.width, snapped.x)),
      y: Math.max(0, Math.min(capture.height, snapped.y)),
      label: p.label,
    };
  });

  return { ...resp, points };
}

/** Find the OCR block whose text best matches `point.label` and is closest
 *  to the LLM's guessed coordinates. Returns the block's bbox center, or
 *  null if no good candidate is found. */
function snapToOcrText(
  point: { x: number; y: number; label: string },
  blocks: OcrBlock[],
): { x: number; y: number; text: string } | null {
  const norm = point.label.trim().toLowerCase();
  if (norm.length < OCR_MIN_LABEL_LEN) return null;

  let best: { x: number; y: number; text: string; distance: number } | null = null;

  for (const block of blocks) {
    const blockText = block.text.trim().toLowerCase();
    if (!blockText) continue;

    // Match: exact, label⊂text, or text⊂label (substring either way).
    const matches =
      blockText === norm || blockText.includes(norm) || norm.includes(blockText);
    if (!matches) continue;

    const cx = (block.bbox[0] + block.bbox[2]) / 2;
    const cy = (block.bbox[1] + block.bbox[3]) / 2;
    const distance = Math.hypot(cx - point.x, cy - point.y);
    if (distance > OCR_SNAP_RADIUS_PX) continue;

    if (!best || distance < best.distance) {
      best = { x: cx, y: cy, text: block.text, distance };
    }
  }

  return best;
}

/** Match Gemini's label against the dock icon list — strictly.
 *
 *  We previously used substring + token-overlap fallbacks to be forgiving
 *  about Gemini's wording, but that mis-snapped browser/in-app answers to
 *  the dock when a label happened to share a token with a dock icon name
 *  (e.g. "Send message" → Messages icon while the user was in Chrome).
 *  The system prompt instructs Gemini to use the EXACT dock name when it
 *  wants AX snapping, so we hold the line: anything else falls through to
 *  Gemini's pixel coordinates.
 */
function matchDockIcon(label: string, icons: DockIcon[]): DockIcon | null {
  const norm = label.trim().toLowerCase();
  if (!norm) return null;
  return icons.find((d) => d.name.toLowerCase() === norm) ?? null;
}

// ---------------------------------------------------------------------------
// Multi-step guided chains
// ---------------------------------------------------------------------------

/** Click hit-area inflation (in screen points) so a slightly off-center click
 *  on a dock icon still counts as advance. AX-reported icon frame is 57×73 pt;
 *  inflating by 12 pt on each side absorbs fat-finger drift without overlapping
 *  adjacent icons. */
const HIT_TEST_MARGIN_PT = 12;

interface StepBounds {
  /** Top-origin global screen points. */
  x: number;
  y: number;
  w: number;
  h: number;
}

interface GroundedStep {
  /** Image-pixel coords for `imageToOverlayPoint` → overlay sprite. */
  imagePoint: { x: number; y: number };
  /** Screen-point bounds for `companion:click-at` hit-testing (margin baked in). */
  bounds: StepBounds;
  /** Display the step lives on (used for image→overlay-pt mapping). */
  displayMeta: CaptureDisplayMeta;
  /** Which path produced these coords — telemetry for the session row. */
  method: "ax" | "ocr" | "gemini" | "none";
}

/** Ground a chain step's `target_label` to a screen position.
 *
 *  Tries three paths in order, fastest-first:
 *    1. AX dock match — instant, zero IPC. The dock list is cached 5 s.
 *    2. OCR text match — free, OCR already ran with the screenshot.
 *    3. Gemini grounding call — slow (~1.5-3 s), last resort.
 *
 *  AX returns deterministic bounds (the icon frame). OCR returns the bbox
 *  of the matched text. Gemini returns just a center point — we inflate a
 *  64×64 square for hit-testing. */
async function groundStep(
  step: { instruction: string; target_label: string },
  displayMeta: CaptureDisplayMeta,
  imageBase64: string | null,
  captureMeta: { width: number; height: number },
  ocrBlocks: OcrBlock[],
): Promise<GroundedStep | null> {
  // 1. AX dock match — instant.
  const dockIcons = await fetchDockIcons();
  const dockMatch = matchDockIcon(step.target_label, dockIcons);
  if (dockMatch) {
    const localXPt = dockMatch.x + dockMatch.w / 2 - displayMeta.display_origin_pt.x;
    const localYPt = dockMatch.y + dockMatch.h / 2 - displayMeta.display_origin_pt.y;
    const displayPxX = localXPt * displayMeta.display_scale_factor;
    const displayPxY = localYPt * displayMeta.display_scale_factor;
    const imageScaleX = captureMeta.width / displayMeta.display_width_px;
    const imageScaleY = captureMeta.height / displayMeta.display_height_px;
    return {
      imagePoint: {
        x: displayPxX * imageScaleX,
        y: displayPxY * imageScaleY,
      },
      bounds: {
        x: dockMatch.x - HIT_TEST_MARGIN_PT,
        y: dockMatch.y - HIT_TEST_MARGIN_PT,
        w: dockMatch.w + HIT_TEST_MARGIN_PT * 2,
        h: dockMatch.h + HIT_TEST_MARGIN_PT * 2,
      },
      displayMeta,
      method: "ax",
    };
  }

  // 2. OCR text match — match step.target_label against the on-screen text
  //    we already extracted with the screenshot. Way faster than asking
  //    Gemini and just as accurate when the target is rendered text (sidebar
  //    entries, buttons, menu items).
  const ocrMatch = matchOcrLabel(step.target_label, ocrBlocks);
  if (ocrMatch) {
    const overlayPt = imageToOverlayPoint(
      { x: (ocrMatch.bbox[0] + ocrMatch.bbox[2]) / 2, y: (ocrMatch.bbox[1] + ocrMatch.bbox[3]) / 2 },
      displayMeta,
    );
    const screenX = displayMeta.display_origin_pt.x + overlayPt.x;
    const screenY = displayMeta.display_origin_pt.y + overlayPt.y;
    // Use the OCR bbox dimensions converted to screen-pt for tight bounds.
    const scale = displayMeta.display_scale_factor;
    const imageScaleX = displayMeta.display_width_px / captureMeta.width;
    const imageScaleY = displayMeta.display_height_px / captureMeta.height;
    const wPt = ((ocrMatch.bbox[2] - ocrMatch.bbox[0]) * imageScaleX) / scale;
    const hPt = ((ocrMatch.bbox[3] - ocrMatch.bbox[1]) * imageScaleY) / scale;
    return {
      imagePoint: {
        x: (ocrMatch.bbox[0] + ocrMatch.bbox[2]) / 2,
        y: (ocrMatch.bbox[1] + ocrMatch.bbox[3]) / 2,
      },
      bounds: {
        x: screenX - wPt / 2 - HIT_TEST_MARGIN_PT,
        y: screenY - hPt / 2 - HIT_TEST_MARGIN_PT,
        w: wPt + HIT_TEST_MARGIN_PT * 2,
        h: hPt + HIT_TEST_MARGIN_PT * 2,
      },
      displayMeta,
      method: "ocr",
    };
  }

  // 3. Gemini fallback — slow last resort, needs an image.
  if (!imageBase64) return null;
  const point = await groundLabel(step.target_label, imageBase64, captureMeta);
  if (!point) return null;
  // Convert image-px → screen-pt (top-origin global) for hit-testing.
  const overlayPt = imageToOverlayPoint(point, displayMeta);
  const screenX = displayMeta.display_origin_pt.x + overlayPt.x;
  const screenY = displayMeta.display_origin_pt.y + overlayPt.y;
  // We don't know the target's actual size — inflate a generous square.
  const half = 32 + HIT_TEST_MARGIN_PT;
  return {
    imagePoint: point,
    bounds: { x: screenX - half, y: screenY - half, w: half * 2, h: half * 2 },
    displayMeta,
    method: "gemini",
  };
}

/** Match a chain step's `target_label` against OCR blocks. Strict-first to
 *  avoid the failure mode where a label like "General" snaps to whichever
 *  longer block happens to contain it ("General Help", "Generally", etc.).
 *
 *  Order: exact case-insensitive equality → block starts with the label
 *  (e.g. "Time Machine" matches "Time Machine…" with truncation) →
 *  label starts with the block → no match (let Gemini grounding handle it).
 *  We deliberately DON'T accept generic-substring containment because it's
 *  too easy for short labels to snap to the wrong instance.
 */
function matchOcrLabel(label: string, blocks: OcrBlock[]): OcrBlock | null {
  const norm = label.trim().toLowerCase();
  if (norm.length < OCR_MIN_LABEL_LEN) return null;

  // 1. Exact match.
  for (const b of blocks) {
    if (b.text.trim().toLowerCase() === norm) return b;
  }
  // 2. Block starts with the label (handles trailing OCR garbage / ellipsis).
  for (const b of blocks) {
    const t = b.text.trim().toLowerCase();
    if (t.startsWith(norm) && t.length <= norm.length + 4) return b;
  }
  // 3. Label starts with the block (handles OCR truncating long labels).
  for (const b of blocks) {
    const t = b.text.trim().toLowerCase();
    if (t.length >= 4 && norm.startsWith(t) && norm.length <= t.length + 4) return b;
  }
  return null;
}

/** Lightweight one-shot grounding call: "where is the {label} element?".
 *  Used for chain steps whose target isn't a dock icon (sidebar entries,
 *  buttons inside windows, menu items). */
async function groundLabel(
  label: string,
  imageBase64: string,
  capture: { width: number; height: number },
): Promise<{ x: number; y: number } | null> {
  const prompt =
    `Find the on-screen UI element labeled "${label}". Return one normalized ` +
    `0-1000 point at its center. (0,0) is top-left, (1000,1000) is bottom-right. ` +
    `If the element is not visible, leave "points" empty.`;

  // Downscale to ~1024 wide before sending — for a single-label "where is this"
  // call we don't need 2048 of detail, and the smaller payload uploads + decodes
  // notably faster.
  const smaller = await downscaleJpegBase64(imageBase64, 1024).catch(() => imageBase64);

  const t0 = Date.now();
  try {
    // flash-lite: ~3× faster than full flash for short single-label grounding.
    const res = await callGeminiStructured(
      [{ text: prompt }, { inline_data: { mime_type: "image/jpeg", data: smaller } }],
      "gemini-2.5-flash-lite",
    );
    termLog(`groundLabel("${label}") via flash-lite took ${Date.now() - t0}ms`);
    if (!res.points || res.points.length === 0) return null;
    const p = res.points[0];
    return {
      x: Math.max(0, Math.min(capture.width, (p.x / 1000) * capture.width)),
      y: Math.max(0, Math.min(capture.height, (p.y / 1000) * capture.height)),
    };
  } catch (e) {
    termLog(`groundLabel("${label}") failed: ${e instanceof Error ? e.message : String(e)}`);
    return null;
  }
}

/** Downscale a base64-encoded JPEG via canvas. Used to send smaller images
 *  to flash-lite for grounding calls. ~1024 wide is enough for "where is X"
 *  questions and uploads ~3× faster than the full 2048-wide capture. */
async function downscaleJpegBase64(b64: string, targetWidth: number): Promise<string> {
  const img = new Image();
  img.src = `data:image/jpeg;base64,${b64}`;
  await img.decode();
  if (img.naturalWidth <= targetWidth) return b64;
  const ratio = targetWidth / img.naturalWidth;
  const w = targetWidth;
  const h = Math.round(img.naturalHeight * ratio);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return b64;
  ctx.drawImage(img, 0, 0, w, h);
  const blob: Blob = await new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob null"))), "image/jpeg", 0.78),
  );
  const buf = await blob.arrayBuffer();
  return uint8ToBase64(new Uint8Array(buf));
}

/** Wait for the user to either click within `bounds` (advance) or trigger a
 *  cancel via Esc / `companion:chain-cancel` (abort). Returns true on advance,
 *  false on cancel. */
async function waitForAdvance(bounds: StepBounds): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    let resolved = false;
    const unlisteners: Array<() => void> = [];
    const finish = (advanced: boolean) => {
      if (resolved) return;
      resolved = true;
      for (const fn of unlisteners) {
        try {
          fn();
        } catch {
          /* ignore */
        }
      }
      resolve(advanced);
    };

    listen<[number, number]>("companion:click-at", ({ payload }) => {
      const [x, y] = payload;
      const inBounds =
        x >= bounds.x && x < bounds.x + bounds.w && y >= bounds.y && y < bounds.y + bounds.h;
      termLog(
        `chain click @ (${Math.round(x)},${Math.round(y)}) ${inBounds ? "IN bounds → advance" : "OUT of bounds → ignore"}`,
      );
      if (inBounds) finish(true);
    })
      .then((fn) => (resolved ? fn() : unlisteners.push(fn)))
      .catch(() => {});

    listen("companion:chain-cancel", () => {
      termLog("chain cancelled via Esc");
      finish(false);
    })
      .then((fn) => (resolved ? fn() : unlisteners.push(fn)))
      .catch(() => {});
  });
}

/** Run a guided multi-step chain to completion (or cancellation).
 *  Owns the chain lifecycle: store mutation, per-step grounding, ring/TTS
 *  emission, click-or-cancel waits, cleanup. Caller awaits this and, when it
 *  returns, the companion is back in `idle` state with no ring on screen. */
interface ChainTelemetry {
  /** Row id from save_companion_session — used to UPDATE the row at chain end. */
  sessionRowId: number | null;
  /** Wall-clock at PTT-stop (used for total interaction duration). */
  interactionStart: number;
}

async function runChain(
  steps: Array<{ instruction: string; target_label: string }>,
  initialDisplayMeta: CaptureDisplayMeta,
  initialImageBase64: string,
  initialCaptureMeta: { width: number; height: number },
  initialOcrBlocks: OcrBlock[],
  telemetry: ChainTelemetry,
): Promise<void> {
  let truncated = steps;
  if (steps.length > MAX_CHAIN_STEPS) {
    termLog(`chain truncated from ${steps.length} to ${MAX_CHAIN_STEPS} steps`);
    truncated = steps.slice(0, MAX_CHAIN_STEPS);
  }

  const store = useCompanionStore.getState();
  store.setChain({ steps: truncated, currentIndex: 0 });
  store.setState("speaking");
  await emit("companion:chain-active", { active: true });
  // Push initial chain state to the overlay HUD so it appears as soon as the
  // first ring renders. Re-emitted on each step advance below.
  await emit("companion:chain-state", { steps: truncated, currentIndex: 0 });
  termLog(`chain start (${truncated.length} steps)`);

  // Per-step telemetry — appended as each step is grounded so the post-chain
  // UPDATE can record the full picture (which methods fired, how far the user
  // got, success vs cancel).
  const groundingMethods: string[] = [];
  let stepsCompleted = 0;
  let chainError: string | null = null;
  let cancelled = false;

  try {
    for (let i = 0; i < truncated.length; i++) {
      const step = truncated[i];
      useCompanionStore.getState().setChain({ steps: truncated, currentIndex: i });
      // Re-emit so the overlay HUD highlights the new "current" step (and
      // marks earlier ones done). For step 1 (i === 0) the screenshot +
      // grounding already ran in the planning call — no loading state. For
      // steps 2-N we re-screenshot + ground inline below; emit `loading=true`
      // first so the HUD shows a spinner while that work runs (otherwise the
      // 1-3s gap between click and ring feels frozen).
      void emit("companion:chain-state", {
        steps: truncated,
        currentIndex: i,
        loading: i > 0,
      });

      // Steps 2+: try to skip the slow re-screenshot when we don't need it.
      // The dock is always visible and never changes from one step to the
      // next, so if `target_label` matches a dock icon we can ground directly
      // off AX with zero IPC. Re-screenshot only fires for non-dock targets.
      let displayMeta = initialDisplayMeta;
      let imageBase64: string | null = initialImageBase64;
      let captureMeta = initialCaptureMeta;
      let ocrBlocks: OcrBlock[] = initialOcrBlocks;
      if (i > 0) {
        const dockIcons = await fetchDockIcons();
        const willHitAx = matchDockIcon(step.target_label, dockIcons) !== null;
        if (willHitAx) {
          termLog(`chain step ${i + 1}: AX dock match — skipping re-screenshot`);
        } else {
          // 700 ms grace for the new pane to render before we screenshot.
          // 250 ms (the original) was too short for System Settings + most
          // app cold-starts: OCR ran against half-drawn UI and matched the
          // wrong instance, causing "totally wrong" sprite placement.
          await new Promise((r) => setTimeout(r, 700));
          const t0 = Date.now();
          try {
            const fresh = await takeScreenshotWithOcr({ max_width: 2048, quality: 78 });
            termLog(`chain step ${i + 1}: re-screenshot+OCR took ${Date.now() - t0}ms`);
            if (fresh.display) {
              displayMeta = {
                display_id: fresh.display.display_id,
                capture_width_px: fresh.display.capture_width_px,
                capture_height_px: fresh.display.capture_height_px,
                display_width_px: fresh.display.display_width_px,
                display_height_px: fresh.display.display_height_px,
                display_scale_factor: fresh.display.display_scale_factor,
                display_origin_pt: fresh.display.display_origin_pt,
                display_size_pt: fresh.display.display_size_pt,
              };
              captureMeta = {
                width: fresh.display.capture_width_px,
                height: fresh.display.capture_height_px,
              };
            }
            imageBase64 = fresh.image;
            ocrBlocks = fresh.ocr_blocks ?? [];
          } catch (e) {
            termLog(`chain step ${i + 1}: re-screenshot failed: ${e}`);
          }
        }
      }

      const tGround = Date.now();
      const grounded = await groundStep(
        step,
        displayMeta,
        imageBase64,
        captureMeta,
        ocrBlocks,
      );
      termLog(
        `chain step ${i + 1}: groundStep took ${Date.now() - tGround}ms (method=${grounded?.method ?? "none"})`,
      );
      if (!grounded) {
        chainError = `failed to ground "${step.target_label}" at step ${i + 1}`;
        groundingMethods.push("none");
        termLog(`chain step ${i + 1}: failed to ground "${step.target_label}" — ending`);
        invoke("plugin:tts|tts_speak", {
          text: `I couldn't find ${step.target_label}. Try again from where you are.`,
        }).catch(() => {});
        break;
      }
      groundingMethods.push(grounded.method);

      const overlayPt = imageToOverlayPoint(grounded.imagePoint, displayMeta);
      termLog(
        `chain step ${i + 1}/${truncated.length}: "${step.target_label}" → overlay(${Math.round(overlayPt.x)},${Math.round(overlayPt.y)}) [${grounded.method}]`,
      );

      await emit("companion:points", {
        points: [{ x: overlayPt.x, y: overlayPt.y, label: step.target_label }],
        duration_ms: -1,
      });
      // Ring is now visible — flip the HUD out of "loading" so the spinner
      // becomes a solid blue dot and the footer text reverts to "Press Esc".
      void emit("companion:chain-state", {
        steps: truncated,
        currentIndex: i,
        loading: false,
      });

      // Speak the instruction. Cancel any previous step's speech first so a
      // fast advance doesn't pile up overlapping utterances.
      invoke("plugin:tts|tts_stop").catch(() => {});
      invoke<string>("plugin:tts|tts_speak", { text: step.instruction }).catch((e) => {
        termLog(`chain tts_speak failed: ${e}`);
      });

      const advanced = await waitForAdvance(grounded.bounds);
      if (!advanced) {
        cancelled = true;
        break;
      }
      stepsCompleted++;
    }
  } finally {
    invoke("plugin:tts|tts_stop").catch(() => {});
    useCompanionStore.getState().setChain(null);
    useCompanionStore.getState().setState("idle");
    useCompanionStore.getState().setPoints([], null);
    await emit("companion:chain-active", { active: false });
    // Clear any remaining ring (zero-duration emit acts as "show nothing").
    await emit("companion:points", { points: [], duration_ms: 0 });

    const completed = stepsCompleted === truncated.length && !chainError;
    termLog(
      `chain done: ${stepsCompleted}/${truncated.length} steps, completed=${completed}${cancelled ? " (cancelled)" : ""}${chainError ? ` error="${chainError}"` : ""}`,
    );

    // Patch the session row with the chain outcome so the SQLite log shows the
    // full interaction, not just Gemini's planning step.
    if (telemetry.sessionRowId !== null) {
      invoke("plugin:screen-capture|update_companion_session", {
        patch: {
          id: telemetry.sessionRowId,
          chain_completed: completed,
          chain_steps_completed: stepsCompleted,
          grounding_methods_json: JSON.stringify(groundingMethods),
          duration_ms: Date.now() - telemetry.interactionStart,
          error: chainError,
        },
      }).catch((e) => {
        console.warn("[companionAssistant] update_companion_session failed:", e);
      });
    }
  }
}

/**
 * Shared Gemini `generateContent` call with the Companion JSON schema.
 * Accepts the `parts` array directly so callers can mix text / image / audio.
 *
 * Model is selectable per call — defaults to `gemini-2.5-flash` (good balance
 * for the initial planning call). Step-grounding callers pass `flash-lite`
 * which is roughly 3× faster for "find this label in this image" prompts
 * where the prompt is small and we don't need deep reasoning.
 */
type GeminiModel = "gemini-2.5-flash" | "gemini-2.5-flash-lite";

async function callGeminiStructured(
  parts: Array<Record<string, unknown>>,
  model: GeminiModel = "gemini-2.5-flash",
): Promise<GeminiCompanionResponse> {
  const apiKey = await getGeminiApiKey();
  const url = `${GEMINI_BASE}/models/${model}:generateContent?key=${apiKey}`;
  const callStart = Date.now();

  const body = {
    contents: [{ parts }],
    generationConfig: {
      response_mime_type: "application/json",
      response_schema: {
        type: "object",
        properties: {
          // Gemini reflects back what it transcribed from the audio — used
          // by the client-side mode-mismatch retry heuristic. Empty string
          // when there's no audio (e.g. the test-task variant).
          transcript: { type: "string" },
          answer: { type: "string" },
          points: {
            type: "array",
            items: {
              type: "object",
              properties: {
                x: { type: "integer" },
                y: { type: "integer" },
                label: { type: "string" },
              },
              required: ["x", "y", "label"],
            },
          },
          // Required so Gemini has to actively decide each call — when it
          // was optional, Gemini defaulted to "single answer" by simply
          // omitting `steps`, regardless of how strong the prompt was.
          // Empty array is the Mode A signal.
          steps: {
            type: "array",
            items: {
              type: "object",
              properties: {
                instruction: { type: "string" },
                target_label: { type: "string" },
              },
              required: ["instruction", "target_label"],
            },
          },
        },
        required: ["answer", "points", "steps", "transcript"],
      },
    },
  };

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (fetchErr) {
    // Network-level failure (offline, DNS error, etc.). Attach status null so
    // mapGeminiErrorToMessage produces the right network message.
    const mapped = Object.assign(
      fetchErr instanceof Error ? fetchErr : new Error(String(fetchErr)),
      { httpStatus: null as number | null },
    );
    throw mapped;
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "(no body)");
    const err = Object.assign(new Error(`Gemini returned ${response.status}: ${text}`), {
      httpStatus: response.status,
    });
    throw err;
  }

  const json = await response.json();
  const rawText: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
  termLog(`gemini ${model} request took ${Date.now() - callStart}ms`);

  if (!rawText) throw new Error("Unexpected Gemini response shape");

  const parsed = JSON.parse(rawText) as Partial<GeminiCompanionResponse>;
  if (typeof parsed.answer !== "string") throw new Error("Gemini response missing 'answer'");

  return {
    answer: parsed.answer,
    points: Array.isArray(parsed.points) ? parsed.points : [],
    steps: Array.isArray(parsed.steps) ? parsed.steps : [],
    transcript: typeof parsed.transcript === "string" ? parsed.transcript : "",
  };
}

// ---------------------------------------------------------------------------
// Overlay routing
// ---------------------------------------------------------------------------

/**
 * Show the overlay window(s), broadcast `companion:points`, then hide after the
 * animation finishes.
 *
 * Broadcasts (not routed per-window) because the label naming uses monitor
 * index in Rust (`companion-overlay-0`, `-1`) but the frontend only knows the
 * CGDirectDisplayID — they don't match. Each overlay covers one display and
 * clips off-bounds coordinates via `overflow: hidden`, so the wrong display
 * won't actually show the sprites.
 */
async function showOverlayPoints(
  _displayId: number,
  points: Array<{ x: number; y: number; label?: string }>,
): Promise<void> {
  if (points.length === 0) return;

  // Overlay windows stay always-visible (transparent + click-through), so
  // there's no show/hide step. Just broadcast the points event; the React
  // CompanionOverlay component renders sprites for `duration_ms` then clears
  // them. When the user enables "keep pointer until clicked", we send a
  // sentinel duration of -1 so the overlay never auto-clears — instead the
  // `companion:click-dismiss` event from the rdev listener clears it.
  const persist = useCompanionSettingsStore.getState().persistPointer;
  try {
    await emit("companion:points", {
      points,
      duration_ms: persist ? -1 : OVERLAY_DURATION_MS,
    });
  } catch (e) {
    console.warn("[companionAssistant] companion:points emit failed:", e);
  }
}

// ---------------------------------------------------------------------------
// Main handlers
// ---------------------------------------------------------------------------

/**
 * Called when the user starts PTT (Fn key down).
 * Starts mic recording and takes an immediate screenshot so we capture the
 * state of the screen at question time (not after the user releases).
 */
export async function handleCompanionStart(): Promise<void> {
  const store = useCompanionStore.getState();
  store.setState("listening");

  // Fire TTS stop and start_recording in parallel immediately so the mic opens
  // with minimum latency from keypress. tts_stop is fire-and-forget (it
  // rarely has anything to interrupt on a fresh PTT press). The screenshot
  // runs in parallel too — it captures the screen at PTT-start time so a user
  // moving the mouse during their question doesn't shift the image.
  invoke("plugin:tts|tts_stop").catch(() => {
    // Sidecar may not be running yet on first press — safe to swallow.
  });

  const micPromise = invoke("plugin:audio-capture|start_recording", {
    config: { mic_only: true, sample_rate: 16000, channels: 1 },
  }).catch((e) => {
    const errMsg = e instanceof Error ? e.message : String(e);
    if (/denied|permission|access|unauthorized|not allowed|restricted/i.test(errMsg)) {
      console.error("[companionAssistant] mic permission denied:", e);
      const userMsg = /busy|in use|another/i.test(errMsg)
        ? "Microphone is in use by another app."
        : "Microphone access denied. Enable it in System Settings.";
      store.resetSession();
      setErrorAndAutoClear(userMsg, /* speakError */ false);
      throw e; // propagate so the stop handler skips Gemini
    }
    console.warn("[companionAssistant] start_recording failed:", e);
    throw e;
  });

  const screenshotPromise = takeScreenshotWithOcr({ max_width: 2048, quality: 78 })
    .then((capture) => {
      const displayMeta: CaptureDisplayMeta | null = capture.display
        ? {
            display_id: capture.display.display_id,
            capture_width_px: capture.display.capture_width_px,
            capture_height_px: capture.display.capture_height_px,
            display_width_px: capture.display.display_width_px,
            display_height_px: capture.display.display_height_px,
            display_scale_factor: capture.display.display_scale_factor,
            display_origin_pt: capture.display.display_origin_pt,
            display_size_pt: capture.display.display_size_pt,
          }
        : null;
      store.setSessionCapture({ capture, display_meta: displayMeta });
      console.log(
        `[companionAssistant] screenshot captured; display_meta ${displayMeta ? "present" : "absent"}`,
      );
    })
    .catch((e) => {
      console.error("[companionAssistant] screenshot failed:", e);
      // Proceed without a screenshot — Gemini will just get audio.
    });

  // Wait for mic to be open before returning so the stop handler doesn't try
  // to stop before start is done. Screenshot is also awaited so we have the
  // frame before Gemini. Use allSettled so a screenshot failure doesn't nuke
  // the whole session.
  await Promise.allSettled([micPromise, screenshotPromise]);
}

/**
 * Called when the user releases PTT (Fn key up).
 * Stops recording, reads the WAV, and sends everything to Gemini.
 */
export async function handleCompanionStop(requestId: number): Promise<void> {
  const store = useCompanionStore.getState();
  store.setState("thinking");

  // Wall-clock start: used to record total interaction duration on the session
  // row. Set as early as possible (before stop_recording adds latency).
  const interactionStart = Date.now();
  // Active app at PTT-stop time — captured early so it reflects what the user
  // was looking at when they asked, not where they are after the chain runs.
  const activeAppPromise = fetchActiveApp();

  // --- Stop recording ---
  let wavBase64: string | null = null;
  try {
    const stopResult = await invoke<StopRecordingResult>("plugin:audio-capture|stop_recording");
    const companionRec = stopResult.companion_recording;

    if (!companionRec?.wav_path) {
      console.warn(
        "[companionAssistant] stop_recording returned no companion_recording — " +
          "the session may not have been started with mic_only: true.",
      );
      store.setState("idle");
      store.resetSession();
      return;
    }

    termLog(
      `WAV ready at ${companionRec.wav_path} (${companionRec.duration_ms}ms, ${companionRec.sample_rate}Hz)`,
    );

    // Read the WAV file and base64-encode it.
    try {
      const bytes = await readFileBytesViaIpc(companionRec.wav_path);
      wavBase64 = uint8ToBase64(bytes);
      termLog(`WAV read OK, ${bytes.length} bytes → ${wavBase64.length} b64 chars`);
    } catch (e) {
      termLog(`WAV read FAILED: ${e instanceof Error ? e.message : String(e)}`);
      console.error("[companionAssistant] failed to read WAV file:", companionRec.wav_path, e);
      store.setState("idle");
      store.resetSession();
      return;
    }
  } catch (e) {
    console.warn("[companionAssistant] stop_recording failed:", e);
    store.setState("idle");
    store.resetSession();
    return;
  }

  // --- Check for stale request ---
  if (useCompanionStore.getState().requestId !== requestId) {
    console.log("[companionAssistant] stale request — discarding");
    return;
  }

  // --- Get session capture ---
  const sessionCapture = useCompanionStore.getState().sessionCapture;
  const imageBase64 = sessionCapture?.capture.image ?? null;

  if (!imageBase64) {
    termLog("no screenshot available — aborting Gemini call");
    console.warn("[companionAssistant] no screenshot available — cannot call Gemini");
    store.setState("idle");
    store.resetSession();
    return;
  }
  termLog(`screenshot ready, ${imageBase64.length} b64 chars; calling Gemini...`);

  // --- Call Gemini ---
  const displayMeta = sessionCapture?.display_meta ?? null;
  const captureMeta = displayMeta
    ? { width: displayMeta.capture_width_px, height: displayMeta.capture_height_px }
    : { width: 1280, height: 800 }; // fallback if display_meta absent

  const ocrBlocks = sessionCapture?.capture.ocr_blocks ?? [];

  let geminiResult: GeminiCompanionResponse;
  try {
    geminiResult = await askCompanion(
      imageBase64,
      wavBase64,
      captureMeta,
      displayMeta,
      ocrBlocks,
    );
    termLog(
      `Gemini OK: answer="${geminiResult.answer.slice(0, 80)}…" points=${geminiResult.points.length} steps=${geminiResult.steps?.length ?? 0} ocrBlocks=${ocrBlocks.length}`,
    );
  } catch (e) {
    termLog(`Gemini FAILED: ${e instanceof Error ? e.message : String(e)}`);
    console.error("[companionAssistant] Gemini call failed:", e);
    // Extract the HTTP status if our structured error attached one.
    const httpStatus: number | null =
      e !== null && typeof e === "object" && "httpStatus" in e
        ? (e as { httpStatus: number | null }).httpStatus
        : null;
    const humanMessage = mapGeminiErrorToMessage(httpStatus, e);
    store.resetSession();
    setErrorAndAutoClear(humanMessage, /* speakError */ true);
    return;
  }

  // --- Check for stale request again (Gemini call takes time) ---
  if (useCompanionStore.getState().requestId !== requestId) {
    console.log("[companionAssistant] stale response after Gemini — discarding");
    return;
  }

  // --- Chain mode: when Gemini returned a sequence, hand off to the chain
  // controller and skip the single-shot path. The summary `answer` is still
  // saved to the session row for Rewind history, but we don't speak it —
  // each step has its own spoken instruction.
  const chainSteps = geminiResult.steps ?? [];
  const activeApp = await activeAppPromise;
  const geminiRawJson = JSON.stringify(geminiResult);

  if (chainSteps.length > 0 && displayMeta) {
    store.setAnswer(geminiResult.answer);
    // Save synchronously so we have the row id for the chain-end UPDATE.
    let sessionRowId: number | null = null;
    try {
      sessionRowId = await invoke<number>("plugin:screen-capture|save_companion_session", {
        session: {
          timestamp: Date.now(),
          transcript: "",
          answer: geminiResult.answer,
          points_json: JSON.stringify(chainSteps),
          screenshot_id: sessionCapture?.capture.db_id ?? null,
          display_id: displayMeta.display_id,
          mode: "chain",
          steps_json: JSON.stringify(chainSteps),
          gemini_raw_json: geminiRawJson,
          active_app: activeApp.name || null,
          active_bundle_id: activeApp.bundle_id || null,
          duration_ms: null, // filled in by the post-chain UPDATE
        },
      });
    } catch (e) {
      console.warn("[companionAssistant] save_companion_session failed (non-fatal):", e);
    }
    await runChain(chainSteps, displayMeta, imageBase64, captureMeta, ocrBlocks, {
      sessionRowId,
      interactionStart,
    });
    return;
  }

  // --- Map points to overlay space and emit ---
  store.setAnswer(geminiResult.answer);
  store.setState("speaking");

  termLog(
    `points=${geminiResult.points.length} displayMeta=${displayMeta ? "present" : "ABSENT"}`,
  );

  if (geminiResult.points.length > 0 && displayMeta) {
    const overlayPoints = geminiResult.points.map((p) => ({
      ...imageToOverlayPoint(p, displayMeta),
      label: p.label,
    }));
    store.setPoints(overlayPoints, displayMeta.display_id);
    termLog(
      `overlay points mapped: ${overlayPoints.map((p) => `(${Math.round(p.x)},${Math.round(p.y)})`).join(" ")}`,
    );

    await showOverlayPoints(displayMeta.display_id, overlayPoints);
    termLog("showOverlayPoints completed");
  } else if (geminiResult.points.length > 0) {
    // display_meta absent — fall back to broadcasting raw image-space points so
    // we still get *something* on screen. The overlay sprite will be at the
    // image pixel coordinate which won't perfectly match the cursor target on
    // multi-display setups, but it beats no animation at all.
    termLog("displayMeta absent — falling back to raw image-space coords");
    const fallback = geminiResult.points.map((p) => ({ x: p.x, y: p.y, label: p.label }));
    store.setPoints(fallback, null);
    await showOverlayPoints(0, fallback);
    termLog("fallback overlay broadcast completed");
  }

  // --- Persist the Q&A session (fire-and-forget; never blocks the user-visible flow) ---
  // screenshot_id is the Rewind DB row id returned by take_screenshot_with_ocr.
  // It may be null when the frame was a dHash duplicate (not persisted) or when
  // the Phase 2 Rust display field isn't yet present.
  const dbId = sessionCapture?.capture.db_id ?? null;
  invoke<number>("plugin:screen-capture|save_companion_session", {
    session: {
      timestamp: Date.now(),
      // transcript is empty for now — Gemini does not return the transcribed
      // question in the current response schema.  A future follow-up can add
      // "transcript": { type: "string" } to the schema and pluck it here.
      transcript: "",
      answer: geminiResult.answer,
      points_json: JSON.stringify(geminiResult.points),
      screenshot_id: dbId,
      display_id: displayMeta?.display_id ?? 0,
      mode: "single",
      steps_json: null,
      gemini_raw_json: geminiRawJson,
      active_app: activeApp.name || null,
      active_bundle_id: activeApp.bundle_id || null,
      duration_ms: Date.now() - interactionStart,
    },
  }).catch((e) => {
    console.warn("[companionAssistant] save_companion_session failed (non-fatal):", e);
  });

  // --- Speak the answer via TTS sidecar ---
  // tts_speak returns an opaque session ID echoed back by tts:willSpeakRange so
  // we can ignore stale range events from a previous (interrupted) utterance.
  const { ttsVoiceId } = useCompanionSettingsStore.getState();
  termLog(`state→speaking; calling tts_speak (voice="${ttsVoiceId || "default"}")...`);
  invoke<string>("plugin:tts|tts_speak", {
    text: geminiResult.answer,
    ...(ttsVoiceId ? { voice: ttsVoiceId } : {}),
  })
    .then((ttsId) => {
      termLog(`tts_speak OK, ttsId=${ttsId}`);
      useCompanionStore.getState().setCurrentTtsId(ttsId);
    })
    .catch((e) => {
      termLog(`tts_speak FAILED: ${e instanceof Error ? e.message : String(e)}`);
      console.warn("[companionAssistant] tts_speak failed:", e);
    });
}

// ---------------------------------------------------------------------------
// Module-init: TTS event listeners
//
// On didFinish / didCancel → transition back to idle and clear points.
// On willSpeakRange → no-op for Phase 3 (word-sync is Phase 5 polish).
// ---------------------------------------------------------------------------

function onTtsComplete() {
  const store = useCompanionStore.getState();
  // Only transition if we're still in speaking state (don't clobber a
  // subsequent session that may already be in listening/thinking).
  if (store.state === "speaking") {
    store.setState("idle");
    store.setPoints([], null);
  }
  // Hide the buddy now that speech is done — but ONLY when there's no active
  // chain. Chain steps stop the previous utterance via tts_stop on each
  // advance, which fires tts:didCancel → us; we mustn't hide the buddy
  // between steps. The chain controller's `finally` block handles the final
  // hide after the last step completes (or is cancelled).
  if (!store.chain) {
    invoke("companion_hide_buddy").catch(() => {});
  }
  // Always clear word-highlight state and TTS id on finish/cancel regardless of
  // companion state — a new PTT press may have already advanced state to
  // listening/thinking before the previous utterance fires didFinish.
  store.setSpeakingRange(null);
  store.setCurrentTtsId(null);
}

// HMR-safe TTS event listener registration.
//
// Critical: capture the listen() Promises synchronously, not just the resolved
// unlisteners. The previous version did `listen().then(fn => array.push(fn))`
// which was racy — if Vite fired dispose() before the promise resolved, the
// unlistener never made it into the array, the OLD module's listener stayed
// active on the Rust side, and the NEW module then registered another. After
// 16 HMR reloads the user saw 16x `tts:didStart` per utterance.
//
// Fix: store the Promises, await them in dispose, then call each unlistener.
const _ttsListenPromises: Array<Promise<UnlistenFn>> = [];

// Each `listen()` returns a Promise<UnlistenFn>. We attach a no-op `.catch`
// so the promise never rejects unhandled — important for non-Tauri contexts
// like the test harness (jsdom) where the IPC bridge isn't wired up. The
// dispose path uses `Promise.allSettled` so it doesn't care about rejections.
const _swallow = (p: Promise<UnlistenFn>) => {
  p.catch(() => {
    /* listen() not available in this environment */
  });
  return p;
};

_ttsListenPromises.push(
  _swallow(
    listen("tts:didStart", () => {
      termLog("tts:didStart received from sidecar — speech IS playing");
    }),
  ),
);
_ttsListenPromises.push(
  _swallow(
    listen("tts:didFinish", () => {
      termLog("tts:didFinish received from sidecar");
      onTtsComplete();
    }),
  ),
);
_ttsListenPromises.push(
  _swallow(
    listen("tts:didCancel", () => {
      termLog("tts:didCancel received from sidecar");
      onTtsComplete();
    }),
  ),
);
// Wire word-boundary highlighting: the Swift sidecar emits
// `tts:willSpeakRange` with `{ id: string, range: { location, length } }`.
// We ignore events whose id doesn't match the current utterance so stale
// ranges from an interrupted session can never bleed into a new one.
_ttsListenPromises.push(
  _swallow(
    listen<{ id: string; range: { location: number; length: number } }>(
      "tts:willSpeakRange",
      ({ payload }) => {
        const store = useCompanionStore.getState();
        if (payload.id !== store.currentTtsId) return;
        store.setSpeakingRange({
          start: payload.range.location,
          end: payload.range.location + payload.range.length,
        });
      },
    ),
  ),
);

// Vite HMR — tear down the listeners this module instance registered before
// the next module instance takes over. No-op in production builds. Awaits
// every listen() promise so we always get the unlistener even if HMR fires
// before subscription was confirmed by the Tauri runtime.
if (import.meta.hot) {
  import.meta.hot.dispose(async () => {
    const results = await Promise.allSettled(_ttsListenPromises);
    for (const r of results) {
      if (r.status === "fulfilled") {
        try {
          r.value();
        } catch {
          /* already unsubscribed */
        }
      }
    }
    _ttsListenPromises.length = 0;
  });
}

// ---------------------------------------------------------------------------
// Diagnostic: run the whole pipeline with a canned prompt, no microphone.
//
// Exposed as a "Run test task" button in Settings → Companion so the full flow
// (screenshot → Gemini → pointer animation + TTS) can be exercised without
// holding the PTT key.  Skips audio capture and the companion_sessions write
// so diagnostic runs don't pollute Rewind history.
// ---------------------------------------------------------------------------

const TEST_QUESTION =
  "Describe what you can see on this screen in 1-2 sentences. " +
  "Then point at 3 interesting elements — buttons, text, or icons worth calling out.";

export async function runCompanionTestTask(): Promise<void> {
  const store = useCompanionStore.getState();
  if (store.state !== "idle") {
    console.warn("[companionAssistant] test task skipped — companion busy in state:", store.state);
    return;
  }

  // Bump the request id so any stale in-flight promise from a real PTT session
  // is discarded by the staleness checks in handleCompanionStop.
  store.nextRequestId();
  store.setState("listening");

  // Cut off any in-flight speech so the test answer starts clean.
  invoke("plugin:tts|tts_stop").catch(() => {});

  // Show the buddy + overlays (the user hasn't pressed PTT, so nothing is visible yet).
  try {
    await invoke("companion_show_buddy");
    await invoke("companion_ensure_overlays");
  } catch (e) {
    console.warn("[companionAssistant] test task: failed to show buddy/overlays:", e);
  }

  // Brief pause so the buddy visibly pops in before we transition to thinking.
  await new Promise((r) => setTimeout(r, 300));
  store.setState("thinking");

  // --- Screenshot ---
  let imageBase64: string | null = null;
  let displayMeta: CaptureDisplayMeta | null = null;
  let ocrBlocks: OcrBlock[] = [];
  try {
    const capture = await takeScreenshotWithOcr({ max_width: 2048, quality: 78 });
    imageBase64 = capture.image ?? null;
    ocrBlocks = capture.ocr_blocks ?? [];
    displayMeta = capture.display
      ? {
          display_id: capture.display.display_id,
          capture_width_px: capture.display.capture_width_px,
          capture_height_px: capture.display.capture_height_px,
          display_width_px: capture.display.display_width_px,
          display_height_px: capture.display.display_height_px,
          display_scale_factor: capture.display.display_scale_factor,
          display_origin_pt: capture.display.display_origin_pt,
          display_size_pt: capture.display.display_size_pt,
        }
      : null;
  } catch (e) {
    console.error("[companionAssistant] test task screenshot failed:", e);
  }

  if (!imageBase64) {
    store.resetSession();
    setErrorAndAutoClear("Couldn't capture your screen — check Screen Recording permission.", false);
    return;
  }

  const captureMeta = displayMeta
    ? { width: displayMeta.capture_width_px, height: displayMeta.capture_height_px }
    : { width: 1280, height: 800 };

  // --- Gemini call (text variant — no audio) ---
  let result: GeminiCompanionResponse;
  try {
    result = await askCompanionText(imageBase64, TEST_QUESTION, captureMeta, displayMeta, ocrBlocks);
  } catch (e) {
    console.error("[companionAssistant] test task Gemini call failed:", e);
    const httpStatus: number | null =
      e !== null && typeof e === "object" && "httpStatus" in e
        ? (e as { httpStatus: number | null }).httpStatus
        : null;
    const humanMessage = mapGeminiErrorToMessage(httpStatus, e);
    store.resetSession();
    setErrorAndAutoClear(humanMessage, /* speakError */ true);
    return;
  }

  // --- Render answer + points + TTS (same shape as handleCompanionStop tail) ---
  store.setAnswer(result.answer);
  store.setState("speaking");

  if (result.points.length > 0 && displayMeta) {
    const overlayPoints = result.points.map((p) => ({
      ...imageToOverlayPoint(p, displayMeta!),
      label: p.label,
    }));
    store.setPoints(overlayPoints, displayMeta.display_id);
    await showOverlayPoints(displayMeta.display_id, overlayPoints);
  }

  const { ttsVoiceId } = useCompanionSettingsStore.getState();
  invoke<string>("plugin:tts|tts_speak", {
    text: result.answer,
    ...(ttsVoiceId ? { voice: ttsVoiceId } : {}),
  })
    .then((ttsId) => useCompanionStore.getState().setCurrentTtsId(ttsId))
    .catch((e) => console.warn("[companionAssistant] test task tts_speak failed:", e));
}
