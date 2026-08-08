/**
 * Benchmark Adapter Paths
 *
 * Three adapter shapes for comparing local controller/adapter overhead:
 *
 * (A) Current TypeScript controller/adapter (spike shape)
 * (B) React Native native-module bridge path (simulated JSI/TurboModule boundary)
 * (C) Web TypeScript adapter path (modeled on crepuscularity.tsc.hk + Moonshine)
 *
 * All use deterministic synthetic inputs. No network, no browser, no ASR.
 * Moonshine is documented as an external speech/voice integration boundary,
 * NOT a dependency of this benchmark.
 */

import type {
  INativePacketBoundary,
  PacketNormalizationResult,
  NativeCapabilities,
} from '../contracts/NativeBoundaryContract.ts';
import { MockNativeBoundary } from '../cpp-bridge/MockNativeBoundary.ts';

// ─── Shared synthetic input generation ───────────────────────────────────────

export function buildSyntheticPacket(payloadSize: number): Uint8Array {
  const boundary = new MockNativeBoundary();
  const payload = new Uint8Array(payloadSize);
  for (let i = 0; i < payloadSize; i++) {
    // Deterministic: same payload every run
    payload[i] = (i * 7 + 3) & 0xff;
  }
  const crc = boundary.calculateChecksum(payload);
  const frame = new Uint8Array(2 + payloadSize + 4);
  frame[0] = 0xaa;
  frame[1] = 0x55;
  frame.set(payload, 2);
  frame[2 + payloadSize] = (crc >>> 24) & 0xff;
  frame[2 + payloadSize + 1] = (crc >>> 16) & 0xff;
  frame[2 + payloadSize + 2] = (crc >>> 8) & 0xff;
  frame[2 + payloadSize + 3] = crc & 0xff;
  return frame;
}

// ─── (A) Current TS Controller/Adapter ───────────────────────────────────────

export class CurrentTsAdapter implements INativePacketBoundary {
  private inner = new MockNativeBoundary();

  calculateChecksum(data: Uint8Array): number {
    return this.inner.calculateChecksum(data);
  }
  normalizePacket(rawData: Uint8Array): PacketNormalizationResult {
    return this.inner.normalizePacket(rawData);
  }
  getCapabilities(): NativeCapabilities {
    return this.inner.getCapabilities();
  }
}

// ─── (B) React Native Native-Module Bridge Path ─────────────────────────────

/**
 * Simulates the overhead of crossing a JSI/TurboModule boundary:
 * - Serialization of Uint8Array to a typed transfer format
 * - Function dispatch through a module registry
 * - Deserialization of result back to TypeScript types
 *
 * This measures the adapter layer cost, NOT actual JNI/ObjC overhead.
 */
export class ReactNativeNativeModuleAdapter implements INativePacketBoundary {
  private inner = new MockNativeBoundary();
  private moduleRegistry: Map<string, Function> = new Map();

  constructor() {
    // Simulate TurboModule registration
    this.moduleRegistry.set('calculateChecksum', this.inner.calculateChecksum.bind(this.inner));
    this.moduleRegistry.set('normalizePacket', this.inner.normalizePacket.bind(this.inner));
    this.moduleRegistry.set('getCapabilities', this.inner.getCapabilities.bind(this.inner));
  }

  calculateChecksum(data: Uint8Array): number {
    // Simulate JSI bridge: serialize → dispatch → deserialize
    const serialized = this.serializeTypedArray(data);
    const fn = this.moduleRegistry.get('calculateChecksum')!;
    const result = fn(this.deserializeTypedArray(serialized));
    return result as number;
  }

  normalizePacket(rawData: Uint8Array): PacketNormalizationResult {
    const serialized = this.serializeTypedArray(rawData);
    const fn = this.moduleRegistry.get('normalizePacket')!;
    const result = fn(this.deserializeTypedArray(serialized));
    return result as PacketNormalizationResult;
  }

  getCapabilities(): NativeCapabilities {
    const fn = this.moduleRegistry.get('getCapabilities')!;
    return fn() as NativeCapabilities;
  }

  /** Simulates typed array serialization across a bridge boundary */
  private serializeTypedArray(data: Uint8Array): ArrayBuffer {
    const buf = new ArrayBuffer(data.length);
    new Uint8Array(buf).set(data);
    return buf;
  }

  /** Simulates typed array deserialization from a bridge boundary */
  private deserializeTypedArray(buf: ArrayBuffer): Uint8Array {
    return new Uint8Array(buf);
  }
}

// ─── (C) Web TypeScript Adapter (crepuscularity + Moonshine boundary) ───────

/**
 * Models a web TypeScript adapter path inspired by the crepuscularity.tsc.hk
 * architecture, where:
 *
 * - The adapter owns template/data rendering (like crepuscularity's renderer
 *   contracts: "Each backend maps the same template semantics into its native
 *   output")
 * - Moonshine is an EXTERNAL speech/voice integration boundary — it is NOT
 *   a dependency. We model its boundary as a typed async-capable contract
 *   that the adapter can dispatch to, without importing or invoking it.
 * - The adapter uses a DOM-free rendering path suitable for web workers or
 *   SSR contexts
 *
 * This measures: adapter instantiation, packet processing through a web-style
 * renderer contract, and Moonshine boundary stub dispatch overhead.
 */

/** Moonshine integration boundary type (external, not a dependency) */
export interface MoonshineBoundaryStub {
  /** Would dispatch audio frames to Moonshine ASR — here it's a no-op stub */
  readonly available: boolean;
  dispatchAudioFrame(pcm16: Uint8Array): { accepted: boolean; boundaryLabel: string };
}

export class WebTypescriptAdapter implements INativePacketBoundary {
  private inner = new MockNativeBoundary();
  private renderCache: Map<string, string> = new Map();

  /**
   * Moonshine boundary: documents the integration point without adding a
   * dependency. The stub returns deterministic results for benchmarking.
   */
  readonly moonshine: MoonshineBoundaryStub = {
    available: false,
    dispatchAudioFrame(_pcm16: Uint8Array) {
      return {
        accepted: false,
        boundaryLabel: 'moonshine-external-stub (not-a-dependency)',
      };
    },
  };

  calculateChecksum(data: Uint8Array): number {
    return this.inner.calculateChecksum(data);
  }

  normalizePacket(rawData: Uint8Array): PacketNormalizationResult {
    const result = this.inner.normalizePacket(rawData);

    // Web adapter overhead: simulate renderer contract serialization
    if (result.status === 'SUCCESS' && result.payload) {
      const cacheKey = `pkt:${result.checksum}`;
      if (!this.renderCache.has(cacheKey)) {
        // Simulate lightweight render contract output (DOM-free)
        this.renderCache.set(
          cacheKey,
          `[web-render] payload=${result.payload.length}b crc=0x${(result.checksum ?? 0).toString(16)}`
        );
      }
    }

    // Touch the Moonshine boundary stub (measures dispatch overhead only)
    if (result.status === 'SUCCESS' && result.payload) {
      this.moonshine.dispatchAudioFrame(result.payload);
    }

    return result;
  }

  getCapabilities(): NativeCapabilities {
    return {
      ...this.inner.getCapabilities(),
      // Web adapter reports SIMD availability differently
      simd: typeof globalThis !== 'undefined' && 'crossOriginIsolated' in globalThis,
    };
  }

  /** Clears render cache between benchmark runs for fair comparison */
  resetRenderCache(): void {
    this.renderCache.clear();
  }
}
