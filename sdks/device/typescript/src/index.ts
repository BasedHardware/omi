/** Omi device BLE protocol helpers. See sdks/device/PROTOCOL.md */

export const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
export const AUDIO_DATA_UUID = '19b10001-e8f2-537e-4f6c-d104768a1214';
export const AUDIO_CODEC_UUID = '19b10002-e8f2-537e-4f6c-d104768a1214';
export const BATTERY_SERVICE_UUID = '0000180f-0000-1000-8000-00805f9b34fb';
export const BATTERY_LEVEL_UUID = '00002a19-0000-1000-8000-00805f9b34fb';

export const PACKET_HEADER_BYTES = 3;
export const PCM_SAMPLE_RATE_HZ = 16000;
export const OPUS_FRAME_SAMPLES = 960;
export const PCM_CHANNELS = 1;

export enum BleAudioCodec {
  Pcm16 = 0,
  Pcm8 = 1,
  Opus = 20,
}

export function mapCodecId(id: number): BleAudioCodec | number {
  if (id === 0) return BleAudioCodec.Pcm16;
  if (id === 1) return BleAudioCodec.Pcm8;
  if (id === 20) return BleAudioCodec.Opus;
  return id;
}

/** Strip the 3-byte Omi audio packet header. Empty if payload too short. */
export function stripPacketHeader(packet: Uint8Array): Uint8Array {
  if (packet.byteLength <= PACKET_HEADER_BYTES) {
    return new Uint8Array(0);
  }
  return packet.subarray(PACKET_HEADER_BYTES);
}

/**
 * BLE transport is platform-specific (Web Bluetooth, noble, react-native-ble-plx).
 * Inject a notify subscription that yields raw packets.
 */
export type AudioPacketHandler = (packet: Uint8Array) => void;

export interface BleTransport {
  startAudioNotifications(handler: AudioPacketHandler): Promise<void> | void;
  stopAudioNotifications?(): Promise<void> | void;
}

export class OmiDeviceSession {
  constructor(private readonly transport: BleTransport) {}

  async listen(handler: AudioPacketHandler): Promise<void> {
    await this.transport.startAudioNotifications(handler);
  }

  async listenPayload(handler: AudioPacketHandler): Promise<void> {
    await this.transport.startAudioNotifications((packet) => {
      handler(stripPacketHeader(packet));
    });
  }
}

export {
  createTranscriber,
  createDeepgramTranscriber,
  createParakeetTranscriber,
  createWhisperTranscriber,
  deepgramWsUrl,
  parakeetWsUrl,
} from './stt/index';
export type { SttEngine, StreamingTranscriber, TranscriptHandler } from './stt/index';

export {
  createNobleTransport,
  connectAndListen,
  scanForDevices,
  findFirstDevice,
  requireNoble,
  NOBLE_MISSING,
} from './ble/index';
export type { ScannedDevice } from './ble/index';
