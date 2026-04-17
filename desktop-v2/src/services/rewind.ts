/**
 * Rewind service — wraps the Tauri screen-capture plugin IPC commands.
 *
 * The plugin is registered as "screen-capture" on the Rust side, so every
 * command is invoked via `plugin:screen-capture|<command_name>`.
 */

import { invoke } from "@tauri-apps/api/core";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A captured screenshot with metadata and optional OCR text. */
export interface Screenshot {
  id: string;
  /** Base64-encoded JPEG data. */
  data: string;
  /** ISO-8601 timestamp of when the screenshot was taken. */
  timestamp: string;
  width: number;
  height: number;
  /** Name of the application that was focused at capture time. */
  appName: string;
  /** Title of the focused window at capture time. */
  windowTitle: string;
  /** OCR-extracted text, populated asynchronously after capture. */
  ocrText?: string;
}

/** Configuration passed to the Tauri capture commands. */
export interface CaptureConfig {
  /** Interval between captures in milliseconds. */
  interval_ms?: number;
  /** JPEG quality (1-100). */
  quality?: number;
  /** Maximum width in pixels; wider images are scaled down. */
  max_width?: number;
}

/** Response from take_screenshot_with_ocr containing image, OCR text, and DB ID. */
export interface ScreenshotWithOcr {
  /** Base64-encoded JPEG image data. */
  image: string;
  /** Full OCR text extracted from the screenshot. */
  ocr_text: string;
  /** Database row ID assigned after the Rust side persists the screenshot (null if frame was deduped). */
  db_id: number | null;
}

/** Runtime state returned by the Tauri capture plugin. */
export interface CaptureState {
  is_capturing: boolean;
  screenshot_count: number;
  last_capture: string | null;
}

/** Information about the currently focused window. */
export interface ActiveWindow {
  app_name: string;
  window_title: string;
  pid: number;
}

/** Metadata-only screenshot row from the database (no image data). */
export interface ScreenshotRow {
  id: number;
  timestamp: string;
  app_name: string;
  window_title: string;
  ocr_text: string | null;
  dhash: string | null;
  width: number;
  height: number;
}

// ---------------------------------------------------------------------------
// IPC wrappers
// ---------------------------------------------------------------------------

/**
 * Take a single screenshot and return the base64-encoded JPEG string.
 *
 * The Rust command returns only the base64 data — the caller is responsible
 * for enriching it with window info, timestamps, etc.
 */
export async function takeScreenshot(config?: CaptureConfig): Promise<string> {
  return invoke<string>("plugin:screen-capture|take_screenshot", {
    config: config ?? null,
  });
}

/**
 * Take a screenshot and run OCR, returning both the base64 image and extracted text.
 * The Rust side now persists the screenshot to SQLite and returns its db_id.
 */
export async function takeScreenshotWithOcr(config?: CaptureConfig): Promise<ScreenshotWithOcr> {
  return invoke<ScreenshotWithOcr>("plugin:screen-capture|take_screenshot_with_ocr", {
    config: config ?? null,
  });
}

/** Start continuous screen capture on the Rust side. */
export async function startCapture(config?: CaptureConfig): Promise<void> {
  await invoke<void>("plugin:screen-capture|start_screen_capture", {
    config: config ?? null,
  });
}

/** Stop continuous screen capture. */
export async function stopCapture(): Promise<void> {
  await invoke<void>("plugin:screen-capture|stop_screen_capture");
}

/** Get information about the currently active (focused) window. */
export async function getActiveWindow(): Promise<ActiveWindow> {
  return invoke<ActiveWindow>("plugin:screen-capture|get_active_window_info");
}

/** Get the current capture state from the Rust plugin. */
export async function getCaptureState(): Promise<CaptureState> {
  return invoke<CaptureState>("plugin:screen-capture|get_screen_capture_state");
}

/** Save a screenshot to the database. */
export async function saveScreenshot(params: {
  timestamp: string;
  app_name: string;
  window_title: string;
  image_b64: string;
  ocr_text: string | null;
  ocr_blocks_json: string | null;
  dhash: string | null;
  width: number;
  height: number;
}): Promise<number> {
  return invoke<number>("plugin:screen-capture|save_screenshot", params);
}

/** FTS5 full-text search on OCR text, window title, app name. */
export async function searchScreenshots(query: string, limit?: number): Promise<ScreenshotRow[]> {
  return invoke<ScreenshotRow[]>("plugin:screen-capture|search_screenshots", {
    query,
    limit: limit ?? 50,
  });
}

/** Get recent screenshots (metadata only, no image data). */
export async function getRecentScreenshots(limit?: number, offset?: number): Promise<ScreenshotRow[]> {
  return invoke<ScreenshotRow[]>("plugin:screen-capture|get_recent_screenshots", {
    limit: limit ?? 100,
    offset: offset ?? 0,
  });
}

/** Get the full image data (base64) for a specific screenshot. */
export async function getScreenshotImage(id: number): Promise<string> {
  return invoke<string>("plugin:screen-capture|get_screenshot_image", { id });
}

/** Get a single screenshot by database ID. */
export async function getScreenshotById(id: number): Promise<ScreenshotRow | null> {
  return invoke<ScreenshotRow | null>("plugin:screen-capture|get_screenshot_by_id", { id });
}

/** Delete screenshots older than the given ISO timestamp. */
export async function deleteOldScreenshots(beforeTimestamp: string): Promise<number> {
  return invoke<number>("plugin:screen-capture|delete_old_screenshots", {
    before_timestamp: beforeTimestamp,
  });
}

/** Delete a single screenshot by database ID. */
export async function deleteScreenshotById(id: number): Promise<boolean> {
  return invoke<boolean>("plugin:screen-capture|delete_screenshot_by_id", { id });
}

/** Delete ALL screenshots from the database. */
export async function deleteAllScreenshots(): Promise<number> {
  return invoke<number>("plugin:screen-capture|delete_all_screenshots");
}

// ---------------------------------------------------------------------------
// Semantic search (Gemini gemini-embedding-001, 3072-dim, L2-normalized).
// Embedding generation happens in TypeScript; the plugin only stores the
// vector and performs cosine similarity over the SQLite BLOB column.
// ---------------------------------------------------------------------------

/** A single semantic-search hit (screenshot id + cosine similarity). */
export interface SemanticHit {
  id: number;
  similarity: number;
}

/** A screenshot row that still needs an embedding computed. */
export interface EmbeddingBacklogItem {
  id: number;
  ocr_text: string;
  app_name: string;
  window_title: string;
}

/** Persist an embedding (3072 f32 values) against a screenshot row. */
export async function saveScreenshotEmbedding(
  id: number,
  embedding: Float32Array,
): Promise<void> {
  await invoke("plugin:screen-capture|save_screenshot_embedding", {
    id,
    // Tauri IPC serializes Float32Array as an object, not an array — convert.
    embedding: Array.from(embedding),
  });
}

/** Cosine-similarity search over stored embeddings. Default threshold 0.5. */
export async function searchScreenshotsSemantic(
  queryEmbedding: Float32Array,
  limit = 50,
  minSimilarity = 0.5,
): Promise<SemanticHit[]> {
  return invoke<SemanticHit[]>("plugin:screen-capture|search_screenshots_semantic", {
    queryEmbedding: Array.from(queryEmbedding),
    limit,
    minSimilarity,
  });
}

/** List screenshots missing an embedding (for backfill). */
export async function screenshotsMissingEmbeddings(
  limit = 200,
): Promise<EmbeddingBacklogItem[]> {
  return invoke<EmbeddingBacklogItem[]>(
    "plugin:screen-capture|screenshots_missing_embeddings",
    { limit },
  );
}
