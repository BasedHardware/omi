export const DEVICE_SESSION_STATES = ["open", "complete", "failed"] as const;

export type DeviceSessionState = (typeof DEVICE_SESSION_STATES)[number];

export type DeviceSessionCodecId = number;

export interface DeviceSession {
  id: string;
  deviceId: string;
  deviceName: string | null;
  codec: DeviceSessionCodecId;
  state: DeviceSessionState;
  byteCount: number;
  chunkCount: number;
  startedAt: number;
  endedAt: number | null;
  capturedAtMs?: number;
}

export type DeviceSessionCreate = {
  captureId: string;
  capturedAtMs?: number;
  deviceId: string;
  deviceName?: string;
  codec: DeviceSessionCodecId;
};

export type DeviceSessionAudioAppend = {
  chunks: Array<{
    chunkIndex: number;
    bytesBase64: string;
  }>;
};
