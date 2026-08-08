export const OMI_AUDIO_HEADER_BYTES = 3;
export const OMI_MAX_FRAME_BYTES = 256 * 1024;
export const OMI_FORWARD_QUEUE_FRAMES = 8;
export const OMI_RECONNECT_GRACE_MS = 20_000;

export type RelayRole = 'mobile_owner' | 'desktop_observer' | 'web_observer';
export type Codec = 'pcm8' | 'opus' | 'opus_fs320' | 'unknown';

export function codecFromFirmwareId(id: number): Codec {
  if (id === 1) return 'pcm8';
  if (id === 20) return 'opus';
  if (id === 21) return 'opus_fs320';
  return 'unknown';
}

export type AudioPacket = {
  packetId: number;
  packetIndex: number;
  payload: Uint8Array;
};

export type RelayFrame = {
  kind: 'frame';
  firstPacketId: number;
  lastPacketId: number;
  payload: Uint8Array;
};

export type RelayGap = {
  kind: 'gap';
  previousPacketId: number;
  nextPacketId: number;
  reason: 'packet_id' | 'fragment_index' | 'too_large';
};

export type RelayEvent = RelayFrame | RelayGap;

function nextPacketId(id: number): number {
  return (id + 1) & 0xffff;
}

export function decodeAudioPacket(raw: Uint8Array): AudioPacket | null {
  if (raw.length <= OMI_AUDIO_HEADER_BYTES) return null;
  return {
    packetId: raw[0] | (raw[1] << 8),
    packetIndex: raw[2],
    payload: raw.slice(OMI_AUDIO_HEADER_BYTES),
  };
}

/** Omi-v4-compatible packet reassembly. It emits explicit gaps and never splices across them. */
export class AudioReassembler {
  private parts: Uint8Array[] = [];
  private bytes = 0;
  private firstPacketId: number | undefined;
  private previous: AudioPacket | undefined;

  push(raw: Uint8Array): RelayEvent[] {
    const packet = decodeAudioPacket(raw);
    if (!packet) return [];

    const events: RelayEvent[] = [];
    const previous = this.previous;
    const startsFrame = packet.packetIndex === 0;

    if (startsFrame && previous && this.parts.length > 0) {
      if (packet.packetId !== nextPacketId(previous.packetId)) {
        events.push({ kind: 'gap', previousPacketId: previous.packetId, nextPacketId: packet.packetId, reason: 'packet_id' });
        this.reset();
      } else {
        events.push(this.flush());
      }
    }

    if (!startsFrame) {
      const contiguous = previous && this.parts.length > 0 &&
        packet.packetId === nextPacketId(previous.packetId) &&
        packet.packetIndex === previous.packetIndex + 1;
      if (!contiguous) {
        if (previous && this.parts.length > 0) {
          events.push({ kind: 'gap', previousPacketId: previous.packetId, nextPacketId: packet.packetId, reason: 'fragment_index' });
        }
        this.reset();
        this.previous = packet;
        return events;
      }
    }

    if (this.bytes + packet.payload.length > OMI_MAX_FRAME_BYTES) {
      events.push({ kind: 'gap', previousPacketId: previous?.packetId ?? packet.packetId, nextPacketId: packet.packetId, reason: 'too_large' });
      this.reset();
      this.previous = packet;
      return events;
    }

    if (this.firstPacketId === undefined) this.firstPacketId = packet.packetId;
    this.parts.push(packet.payload);
    this.bytes += packet.payload.length;
    this.previous = packet;
    return events;
  }

  flush(): RelayFrame {
    if (!this.previous || this.firstPacketId === undefined) throw new Error('cannot flush empty frame');
    const payload = new Uint8Array(this.bytes);
    let offset = 0;
    for (const part of this.parts) {
      payload.set(part, offset);
      offset += part.length;
    }
    const frame = { kind: 'frame' as const, firstPacketId: this.firstPacketId, lastPacketId: this.previous.packetId, payload };
    this.reset();
    return frame;
  }

  finish(): RelayEvent[] {
    return this.parts.length > 0 ? [this.flush()] : [];
  }

  private reset(): void {
    this.parts = [];
    this.bytes = 0;
    this.firstPacketId = undefined;
  }
}

export class BoundedFrameQueue {
  private readonly frames: RelayFrame[] = [];
  private readonly capacity: number;

  constructor(capacity = OMI_FORWARD_QUEUE_FRAMES) {
    this.capacity = capacity;
  }

  push(frame: RelayFrame): boolean {
    if (this.frames.length >= this.capacity) return false;
    this.frames.push(frame);
    return true;
  }

  shift(): RelayFrame | undefined { return this.frames.shift(); }
  get length(): number { return this.frames.length; }
}

export class RelaySession {
  private streamGeneration = 0;
  private disconnectedAt: number | undefined;
  readonly role: RelayRole;

  constructor(role: RelayRole) {
    this.role = role;
  }

  canControlDevice(): boolean { return this.role === 'mobile_owner'; }
  disconnect(atMs: number): void { this.disconnectedAt = atMs; }
  reconnect(atMs: number): { accepted: boolean; streamGeneration: number } {
    const withinGrace = this.disconnectedAt !== undefined && atMs - this.disconnectedAt <= OMI_RECONNECT_GRACE_MS;
    if (!withinGrace) this.streamGeneration += 1;
    this.disconnectedAt = undefined;
    return { accepted: true, streamGeneration: this.streamGeneration };
  }
}
