import type {
  INativePacketBoundary,
  NativeCapabilities,
  PacketNormalizationResult,
} from '../contracts/NativeBoundaryContract.ts';

/**
 * TypeScript Mock / Host implementation of the narrow C++ Native Boundary.
 * Implements identical CRC32 checksum calculation, packet frame parsing,
 * sync byte validation, and capability queries matching omi_native_boundary.cpp.
 */
export class MockNativeBoundary implements INativePacketBoundary {
  calculateChecksum(data: Uint8Array): number {
    if (!data || data.length === 0) {
      return 0;
    }
    let crc = 0xffffffff;
    for (let i = 0; i < data.length; i++) {
      crc ^= data[i];
      for (let j = 0; j < 8; j++) {
        crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
      }
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  normalizePacket(rawData: Uint8Array): PacketNormalizationResult {
    if (!rawData || rawData.length < 6) {
      return { status: 'ERR_INVALID_PARAM' };
    }

    // Framing sync check: 0xAA 0x55
    if (rawData[0] !== 0xaa || rawData[1] !== 0x55) {
      return { status: 'ERR_SYNC_BYTES' };
    }

    const payloadLen = rawData.length - 6;
    const expectedCrc =
      ((rawData[rawData.length - 4] << 24) |
        (rawData[rawData.length - 3] << 16) |
        (rawData[rawData.length - 2] << 8) |
        rawData[rawData.length - 1]) >>>
      0;

    const payload = rawData.subarray(2, 2 + payloadLen);
    const computedCrc = this.calculateChecksum(payload);

    if (computedCrc !== expectedCrc) {
      return { status: 'ERR_CHECKSUM' };
    }

    return {
      status: 'SUCCESS',
      payload: new Uint8Array(payload),
      checksum: computedCrc,
    };
  }

  getCapabilities(): NativeCapabilities {
    return {
      simd: true,
      abiVersion: 1,
      maxPacketBytes: 4096,
    };
  }
}
