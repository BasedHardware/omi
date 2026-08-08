export interface NativeCapabilities {
  simd: boolean;
  abiVersion: number;
  maxPacketBytes: number;
}

export type NormalizationStatus =
  | 'SUCCESS'
  | 'ERR_INVALID_PARAM'
  | 'ERR_SYNC_BYTES'
  | 'ERR_CHECKSUM'
  | 'ERR_BUFFER_OVERFLOW';

export interface PacketNormalizationResult {
  status: NormalizationStatus;
  payload?: Uint8Array;
  checksum?: number;
}

export interface INativePacketBoundary {
  calculateChecksum(data: Uint8Array): number;
  normalizePacket(rawData: Uint8Array): PacketNormalizationResult;
  getCapabilities(): NativeCapabilities;
}
