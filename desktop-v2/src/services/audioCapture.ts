/**
 * Audio capture service — wraps the Tauri `audio-capture` plugin.
 *
 * The plugin is registered as "audio-capture" on the Rust side, so every
 * command is invoked via `plugin:audio-capture|<command_name>`.
 */

import { invoke } from "@tauri-apps/api/core";

// ---------------------------------------------------------------------------
// Types (mirror Rust `models.rs`)
// ---------------------------------------------------------------------------

export interface AudioDevice {
  id: string;
  name: string;
  is_default: boolean;
  is_input: boolean;
}

export type CaptureMode = "conversation" | "ptt";

/**
 * VAD sensitivity preset. Rust serializes as lowercase (`VadMode::Off` → `"off"`).
 *   - `"off"`         — no gating; stream raw mic to Deepgram (best quality, most bandwidth)
 *   - `"sensitive"`   — catches soft/quiet speech (threshold ~0.30, 2 frames)
 *   - `"balanced"`    — middle ground (threshold ~0.40, 2 frames)
 *   - `"aggressive"`  — loud/clear speech only, today's "VAD on" behavior (threshold 0.50, 3 frames)
 */
export type VadMode = "off" | "sensitive" | "balanced" | "aggressive";

export interface CaptureConfig {
  sample_rate: number;
  channels: number;
  device_id?: string | null;
  language?: string;
  mode?: CaptureMode;
  capture_system_audio?: boolean;
  vad_mode?: VadMode;
}

export interface CaptureState {
  is_capturing: boolean;
  device_name: string | null;
  sample_rate: number;
}

// ---------------------------------------------------------------------------
// Local persistence types (mirror Rust `storage.rs` / `lib.rs` return types)
// ---------------------------------------------------------------------------

export type LocalSessionStatus =
  | "recording"
  | "pending_upload"
  | "uploading"
  | "completed"
  | "failed";

export interface LocalSession {
  id: number;
  started_at: string;
  finished_at: string | null;
  source: string;
  language: string;
  timezone: string;
  input_device_name: string | null;
  status: LocalSessionStatus;
  backend_id: string | null;
  last_error: string | null;
  retry_count: number;
  next_retry_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LocalSegment {
  id: number;
  session_id: number;
  text: string;
  speaker: string;
  speaker_id: number;
  is_user: boolean;
  start_time: number;
  end_time: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// IPC wrappers
// ---------------------------------------------------------------------------

export async function listDevices(): Promise<AudioDevice[]> {
  return invoke<AudioDevice[]>("plugin:audio-capture|list_devices");
}

export async function startRecording(config?: CaptureConfig): Promise<CaptureState> {
  return invoke<CaptureState>("plugin:audio-capture|start_recording", {
    config: config ?? null,
  });
}

export async function stopRecording(): Promise<CaptureState> {
  return invoke<CaptureState>("plugin:audio-capture|stop_recording");
}

export async function getCaptureState(): Promise<CaptureState> {
  return invoke<CaptureState>("plugin:audio-capture|get_capture_state");
}

// ---------------------------------------------------------------------------
// Local persistence wrappers (Swift-parity retry/offline support)
// ---------------------------------------------------------------------------

export async function listLocalSessions(): Promise<LocalSession[]> {
  return invoke<LocalSession[]>("plugin:audio-capture|list_local_sessions");
}

export async function getLocalSegments(sessionId: number): Promise<LocalSegment[]> {
  return invoke<LocalSegment[]>("plugin:audio-capture|get_local_segments", {
    sessionId,
  });
}

export async function retrySyncNow(sessionId: number): Promise<void> {
  await invoke("plugin:audio-capture|retry_sync_now", { sessionId });
}

export async function deleteLocalSession(sessionId: number): Promise<void> {
  await invoke("plugin:audio-capture|delete_local_session", { sessionId });
}
