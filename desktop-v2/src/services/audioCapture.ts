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

export interface CaptureConfig {
  sample_rate: number;
  channels: number;
  device_id?: string | null;
}

export interface CaptureState {
  is_capturing: boolean;
  device_name: string | null;
  sample_rate: number;
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
