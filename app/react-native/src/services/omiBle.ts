/**
 * omi wearable over BLE.
 *
 * Ported from the Flutter connector at
 * app/lib/services/devices/connectors/omi_connection.dart and the UUID table in
 * app/lib/services/devices/models.dart. The UUIDs are the firmware's, not ours --
 * they are the one part of this file that cannot be inferred.
 *
 * Scope of this first slice: discover, connect, identify, read battery, read the
 * audio codec, sync time, and count audio notifications. Audio is *counted*, not
 * decoded or forwarded to STT yet -- see subscribeToAudio.
 */
import { BleManager, Device, Subscription, State } from 'react-native-ble-plx';

/**
 * Base64 -> bytes, without Buffer.
 *
 * react-native-ble-plx hands every characteristic value back as base64. Node's
 * Buffer is not in a React Native runtime, so this uses the atob Hermes exposes
 * (RN >= 0.74) and falls back to a hand-rolled decoder if it is missing, rather
 * than pulling in a polyfill for one function.
 */
function toBase64(bytes: Uint8Array): string {
  const g = globalThis as { btoa?: (s: string) => string };
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i] ?? 0);
  if (typeof g.btoa === 'function') return g.btoa(binary);
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const at = (n: number): string => alphabet[n] ?? '=';
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const n = ((bytes[i] ?? 0) << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0);
    out += at((n >> 18) & 63) + at((n >> 12) & 63);
    out += i + 1 < bytes.length ? at((n >> 6) & 63) : '=';
    out += i + 2 < bytes.length ? at(n & 63) : '=';
  }
  return out;
}

function fromBase64(value: string): Uint8Array {
  const g = globalThis as { atob?: (s: string) => string };
  if (typeof g.atob === 'function') {
    const binary = g.atob(value);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  }
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const clean = value.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let p = 0;
  // noUncheckedIndexedAccess: indexing a string yields string | undefined, so the
  // alphabet lookups are coerced. A missing char becomes -1 and contributes 0,
  // which is the correct behaviour for the padding we already stripped.
  const at = (i: number): number => alphabet.indexOf(clean[i] ?? 'A');
  for (let i = 0; i < clean.length; i += 4) {
    const n = (at(i) << 18) | (at(i + 1) << 12) | ((at(i + 2) & 63) << 6) | (at(i + 3) & 63);
    if (p < out.length) out[p++] = (n >> 16) & 255;
    if (p < out.length) out[p++] = (n >> 8) & 255;
    if (p < out.length) out[p++] = n & 255;
  }
  return out;
}

/** Firmware UUIDs. Do not edit without a device to test against. */
export const OMI = {
  service: '19b10000-e8f2-537e-4f6c-d104768a1214',
  audioDataStream: '19b10001-e8f2-537e-4f6c-d104768a1214',
  audioCodec: '19b10002-e8f2-537e-4f6c-d104768a1214',

  timeSyncService: '19b10030-e8f2-537e-4f6c-d104768a1214',
  timeSyncWrite: '19b10031-e8f2-537e-4f6c-d104768a1214',

  settingsService: '19b10010-e8f2-537e-4f6c-d104768a1214',
  settingsMicGain: '19b10012-e8f2-537e-4f6c-d104768a1214',

  batteryService: '0000180f-0000-1000-8000-00805f9b34fb',
  batteryLevel: '00002a19-0000-1000-8000-00805f9b34fb',

  deviceInfoService: '0000180a-0000-1000-8000-00805f9b34fb',
  modelNumber: '00002a24-0000-1000-8000-00805f9b34fb',
  firmwareRevision: '00002a26-0000-1000-8000-00805f9b34fb',
  hardwareRevision: '00002a27-0000-1000-8000-00805f9b34fb',
  manufacturer: '00002a29-0000-1000-8000-00805f9b34fb',
  serialNumber: '00002a25-0000-1000-8000-00805f9b34fb',
} as const;

/** Codec ids as written by the firmware. Mirrors the Flutter switch. */
export type OmiCodec = 'pcm8' | 'pcm16' | 'opus' | 'opusFS320' | 'unknown';

const CODEC_BY_ID: Record<number, OmiCodec> = {
  1: 'pcm8',
  2: 'pcm16',
  20: 'opus',
  21: 'opusFS320',
};

/** Every codec the firmware reports maps to 16 kHz, as in bt_device.dart. */
export const SAMPLE_RATE = 16000;

/**
 * Wire names for the STT websocket, from mapCodecToName() in bt_device.dart.
 *
 * Not the Dart enum names: the backend is sent 'opus_fs320', not
 * 'BleAudioCodec.opusFS320'. OmiCodec is kept camelCase to match the enum; this
 * is the only place the two vocabularies meet.
 */
const WIRE_CODEC: Record<OmiCodec, string | null> = {
  pcm8: 'pcm8',
  pcm16: 'pcm16',
  opus: 'opus',
  opusFS320: 'opus_fs320',
  unknown: null,
};

/** The codec name the backend expects, or null for one it cannot decode. */
export function sttCodecName(codec: OmiCodec): string | null {
  return WIRE_CODEC[codec] ?? null;
}

/**
 * Channel count the backend expects. Flutter sends 2 for opus and 1 for pcm
 * (capture_controller.dart), which is a quirk rather than a derivation -- there
 * is nothing wrong with single-channel opus -- but the backend is written against
 * it, so matching it is what works.
 */
export function sttChannels(codec: OmiCodec): 1 | 2 {
  return codec === 'opus' || codec === 'opusFS320' ? 2 : 1;
}

export interface OmiScanResult {
  id: string;
  name: string | null;
  rssi: number | null;
}

export interface OmiIdentity {
  name: string | null;
  manufacturer: string | null;
  model: string | null;
  hardware: string | null;
  firmware: string | null;
  serial: string | null;
  batteryPct: number | null;
  codec: OmiCodec;
}

export type OmiState = 'unsupported' | 'unauthorized' | 'poweredOff' | 'ready';

export class OmiBle {
  private manager: BleManager | null = null;
  private device: Device | null = null;
  private scanning = false;
  private lastAudioError: string | null = null;
  private batterySub: Subscription | null = null;
  private audioSub: Subscription | null = null;

  /** Lazily constructed: constructing BleManager eagerly at import time reads
   *  native state that is not ready while the module is still autolinking. */
  private mgr(): BleManager {
    this.manager ??= new BleManager();
    return this.manager;
  }

  async state(): Promise<OmiState> {
    const s = await this.mgr().state();
    switch (s) {
      case State.Unsupported:
        return 'unsupported';
      case State.Unauthorized:
        return 'unauthorized';
      case State.PoweredOff:
      case State.Resetting:
        return 'poweredOff';
      default:
        return 'ready';
    }
  }

  /**
   * Scans for peripherals that advertise the omi service.
   *
   * Refuses rather than scanning into a void when the adapter is off or
   * unauthorized. Verified on an SM-A145F: with Bluetooth off, startDeviceScan
   * resolves happily and simply reports nothing for the full duration, which
   * reads exactly like "my device is broken" rather than "turn Bluetooth on".
   */
  async scan(seconds = 10): Promise<OmiScanResult[]> {
    const state = await this.state();
    if (state !== 'ready') {
      throw new Error(
        state === 'unauthorized'
          ? 'bluetooth permission not granted'
          : state === 'poweredOff'
            ? 'bluetooth is off -- enable it and scan again'
            : 'this device has no bluetooth adapter'
      );
    }
    const found = new Map<string, OmiScanResult>();
    const manager = this.mgr();
    this.scanning = true;
    // DuplicatesAllowed so RSSI updates for a device already in the map still
    // arrive; DisallowDuplicates would report each device exactly once.
    await manager.startDeviceScan([OMI.service], null, (error, device) => {
      if (error || !device) return;
      found.set(device.id, {
        id: device.id,
        name: device.name ?? device.localName ?? null,
        rssi: device.rssi ?? null,
      });
    });

    await new Promise((r) => setTimeout(r, seconds * 1000));
    await manager.stopDeviceScan();
    this.scanning = false;
    return [...found.values()].sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999));
  }

  async connect(id: string): Promise<Device> {
    const manager = this.mgr();
    if (this.scanning) {
      // Connecting mid-scan leaves the radio scanning on some devices and the
      // connect then times out.
      await manager.stopDeviceScan();
      this.scanning = false;
    }
    if (this.device) {
      await this.disconnect();
    }
    // autoConnect:false so a stale GATT entry cannot silently attach us to a
    // device the user did not just pick.
    this.device = await manager.connectToDevice(id, { autoConnect: false, timeout: 15000 });
    await this.device.discoverAllServicesAndCharacteristics();
    return this.device;
  }

  async disconnect(): Promise<void> {
    await this.stopAudio();
    this.stopBattery();
    if (this.device) {
      const d = this.device;
      this.device = null;
      await manager_disconnect(d);
    }
  }

  async isConnected(): Promise<boolean> {
    return this.device ? await this.device.isConnected() : false;
  }

  /** Reads the standard Device Information characteristics plus battery and codec. */
  async readIdentity(): Promise<OmiIdentity> {
    const d = this.requireDevice();
    // readCharacteristicForService resolves a Characteristic whose `value` is
    // base64 or null; the library does not hand back a bare string.
    const text = async (uuid: string): Promise<string | null> => {
      try {
        const ch = await d.readCharacteristicForService(OMI.deviceInfoService, uuid);
        if (!ch.value) return null;
        const decoded = new TextDecoder()
          .decode(fromBase64(ch.value))
          .replace(/\0/g, '')
          .trim();
        return decoded.length ? decoded : null;
      } catch {
        // A characteristic the firmware does not implement is normal, not an error.
        return null;
      }
    };
    const bytes = async (uuid: string, service: string): Promise<Uint8Array | null> => {
      try {
        const ch = await d.readCharacteristicForService(service, uuid);
        return ch.value ? fromBase64(ch.value) : null;
      } catch {
        return null;
      }
    };

    const battery = await bytes(OMI.batteryLevel, OMI.batteryService);
    const codecRaw = await bytes(OMI.audioCodec, OMI.service);
    const codecId: number = codecRaw && codecRaw.length ? (codecRaw[0] ?? 1) : 1;

    return {
      name: this.device?.name ?? this.device?.localName ?? null,
      manufacturer: await text(OMI.manufacturer),
      model: await text(OMI.modelNumber),
      hardware: await text(OMI.hardwareRevision),
      firmware: await text(OMI.firmwareRevision),
      serial: await text(OMI.serialNumber),
      batteryPct: battery && battery.length ? (battery[0] ?? null) : null,
      codec: CODEC_BY_ID[codecId] ?? 'unknown',
    };
  }

  /**
   * Writes epoch seconds as a 4-byte little-endian uint32.
   *
   * The device stamps recordings with this, so a device whose clock has drifted
   * files every clip against the wrong date. Done on connect, as Flutter does.
   */
  async syncTime(): Promise<boolean> {
    const d = this.requireDevice();
    const epoch = Math.floor(Date.now() / 1000) >>> 0;
    // 4-byte little-endian, as the firmware expects. Hand-encoded rather than
    // Buffer.writeUInt32LE, since Buffer is not available in a RN runtime.
    const bytes = new Uint8Array([
      epoch & 0xff,
      (epoch >>> 8) & 0xff,
      (epoch >>> 16) & 0xff,
      (epoch >>> 24) & 0xff,
    ]);
    try {
      await d.writeCharacteristicWithResponseForService(
        OMI.timeSyncService,
        OMI.timeSyncWrite,
        toBase64(bytes)
      );
      return true;
    } catch {
      return false;
    }
  }

  onBattery(onChange: (pct: number) => void): void {
    const d = this.requireDevice();
    this.batterySub = d.monitorCharacteristicForService(
      OMI.batteryService,
      OMI.batteryLevel,
      (error, chunk) => {
        if (error || !chunk) return;
        if (!chunk.value) return;
        const bytes = fromBase64(chunk.value);
        const pct = bytes[0];
        if (pct !== undefined) onChange(pct);
      }
    );
  }

  stopBattery(): void {
    this.batterySub?.remove();
    this.batterySub = null;
  }

  /**
   * Subscribes to the device's audio notifications.
   *
   * This hands raw firmware bytes to `onBytes` and does not decode them. The
   * backend expects the codec declared and 16 kHz for all of them, so the next
   * step is to forward these chunks to the same websocket the phone mic uses --
   * not to unpack PCM here.
   */
  onAudio(onBytes: (bytes: Uint8Array) => void, onError?: (e: unknown) => void): void {
    const d = this.requireDevice();
    this.audioSub = d.monitorCharacteristicForService(
      OMI.service,
      OMI.audioDataStream,
      (error, chunk) => {
        if (error) {
          this.lastAudioError = error.message || String(error);
          onError?.(error);
          return;
        }
        if (!chunk || !chunk.value) return;
        onBytes(fromBase64(chunk.value));
      }
    );
  }

  /**
   * Confirms the device is connected and ready to stream.
   *
   * There is deliberately NO descriptor write here, and I had this wrong twice.
   * react-native-ble-plx exposes writeDescriptorForService, but it throws:
   * "Cannot write to descriptor 00002902-... It's not allowed by iOS and
   * therefore forbidden on Android as well." That block is correct behaviour --
   * writing the CCCD by hand is the wrong route, because the library already does
   * it. In BleModule.safeMonitorCharacteristicForDevice it calls
   * connection.setupNotification(gattCharacteristic, QUICK_SETUP) when the CCCD
   * exists, and setupNotification writes the descriptor.
   *
   * The logcat evidence that misled me was real but misleading:
   * setCharacteristicNotification() appears with no descriptor write after it,
   * but the CCCD write goes through a different code path that does not log that
   * line. Audio was in fact arriving while I believed it was not.
   *
   * So subscribing via onAudio() is the whole mechanism. This only guards the
   * precondition.
   */
  async startAudio(): Promise<boolean> {
    try {
      this.requireDevice();
      this.lastAudioError = null;
      return true;
    } catch (e) {
      this.lastAudioError = e instanceof Error ? e.message : String(e);
      return false;
    }
  }

  /** The real reason startAudio failed, rather than a flattened boolean. */
  startAudioError(): string | null {
    return this.lastAudioError;
  }

  stopAudio(): void {
    this.audioSub?.remove();
    this.audioSub = null;
  }

  get connectedDeviceId(): string | null {
    return this.device?.id ?? null;
  }

  private requireDevice(): Device {
    if (!this.device) throw new Error('omi: not connected');
    return this.device;
  }
}

async function manager_disconnect(d: Device): Promise<void> {
  try {
    await d.cancelConnection();
  } catch {
    // Already gone. cancelConnection rejects when there is no live GATT link, and
    // that is the state we wanted.
  }
}

export const omiBle = new OmiBle();

/**
 * The query parameters for a device capture, derived from what the firmware
 * reported. Lives here rather than in captureStore so it can be asserted without
 * importing that store, which pulls in the native microphone module. Getting
 * these wrong fails silently: the socket still opens and then returns no
 * transcripts, which looks like a network fault rather than a formatting one.
 */
export function omiStreamParams(codec: OmiCodec): Record<string, string> | null {
  const wire = sttCodecName(codec);
  if (!wire) return null;
  return {
    codec: wire,
    sample_rate: String(SAMPLE_RATE),
    channels: String(sttChannels(codec)),
    language: 'multi',
  };
}
