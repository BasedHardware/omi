export const DEVICE_AUDIO_LIMITS = {
  maxBytes: 8_388_608,
  maxOutputBytes: 17_825_792,
  maxPackets: 65_536,
  maxDurationSeconds: 3600,
  maxFrameBytes: 61_440,
} as const;

export type DeviceAudioErrorCode =
  | "unsupported_codec"
  | "invalid_packet"
  | "packet_gap"
  | "invalid_opus"
  | "audio_too_large"
  | "empty_audio";

export class DeviceAudioError extends Error {
  constructor(readonly code: DeviceAudioErrorCode) {
    super(code);
    this.name = "DeviceAudioError";
  }
}

export type DeviceAudio = {
  bytes: Uint8Array;
  contentType: "audio/wav" | "audio/ogg";
  durationSeconds: number;
  discardedLeadingPackets: number;
};

function fail(code: DeviceAudioErrorCode): never {
  throw new DeviceAudioError(code);
}

function concat(parts: readonly Uint8Array[]): Uint8Array {
  const size = parts.reduce((sum, part) => sum + part.length, 0);
  if (size > DEVICE_AUDIO_LIMITS.maxOutputBytes) fail("audio_too_large");
  const output = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function reassemble(packets: readonly Uint8Array[]) {
  if (packets.length > DEVICE_AUDIO_LIMITS.maxPackets) fail("audio_too_large");
  const frames: Uint8Array[] = [];
  let parts: Uint8Array[] = [];
  let frameBytes = 0;
  let lastSequence: number | null = null;
  let lastFragment = -1;
  let totalBytes = 0;
  let discardedLeadingPackets = 0;
  for (const packet of packets) {
    totalBytes += packet.length;
    if (totalBytes > DEVICE_AUDIO_LIMITS.maxBytes) fail("audio_too_large");
    if (packet.length < 4) fail("invalid_packet");
    const sequence = packet[0]! | (packet[1]! << 8);
    const fragment = packet[2]!;
    if (lastSequence === null && fragment !== 0) {
      discardedLeadingPackets += 1;
      continue;
    }
    if (lastSequence !== null && sequence !== ((lastSequence + 1) & 0xffff)) {
      fail("packet_gap");
    }
    if (fragment === 0) {
      if (parts.length > 0) frames.push(concat(parts));
      parts = [];
      frameBytes = 0;
    } else if (fragment !== lastFragment + 1) {
      fail("packet_gap");
    }
    const payload = packet.subarray(3);
    frameBytes += payload.length;
    if (frameBytes > DEVICE_AUDIO_LIMITS.maxFrameBytes) fail("audio_too_large");
    parts.push(payload);
    lastSequence = sequence;
    lastFragment = fragment;
  }
  if (parts.length > 0) frames.push(concat(parts));
  if (frames.length === 0) fail("empty_audio");
  return { frames, discardedLeadingPackets };
}

function opusSamples(packet: Uint8Array): number {
  const toc = packet[0];
  if (toc === undefined || (toc & 4) !== 0) fail("invalid_opus");
  const config = toc >> 3;
  const frameSamples =
    config >= 16
      ? 120 << (config & 3)
      : config >= 12
      ? 480 << (config & 1)
      : (config & 3) === 3
      ? 2880
      : 480 << (config & 3);
  const code = toc & 3;
  let offset = 1;
  let end = packet.length;
  let count = code === 0 ? 1 : 2;
  const readSize = () => {
    if (offset >= end) fail("invalid_opus");
    const first = packet[offset++]!;
    if (first < 252) return first;
    if (offset >= end) fail("invalid_opus");
    return first + 4 * packet[offset++]!;
  };
  let variable = code === 2;
  if (code === 3) {
    if (offset >= end) fail("invalid_opus");
    const control = packet[offset++]!;
    count = control & 63;
    variable = (control & 128) !== 0;
    if ((control & 64) !== 0) {
      let padding = 0;
      let size: number;
      do {
        if (offset >= end) fail("invalid_opus");
        size = packet[offset++]!;
        padding += size === 255 ? 254 : size;
      } while (size === 255);
      end -= padding;
    }
  }
  if (count === 0 || count * frameSamples > 5760 || end < offset)
    fail("invalid_opus");
  if (variable) {
    let sizedBytes = 0;
    for (let index = 0; index < count - 1; index += 1) sizedBytes += readSize();
    const lastSize = end - offset - sizedBytes;
    if (lastSize < 0 || lastSize > 1275) fail("invalid_opus");
  } else {
    const size = (end - offset) / count;
    if (!Number.isInteger(size) || size > 1275) fail("invalid_opus");
  }
  return count * frameSamples;
}

function oggPage(
  packet: Uint8Array,
  sequence: number,
  granule: number,
  flags: number
): Uint8Array {
  const segments = Math.floor(packet.length / 255) + 1;
  if (segments > 255) fail("invalid_opus");
  const page = new Uint8Array(27 + segments + packet.length);
  const view = new DataView(page.buffer);
  page.set(new TextEncoder().encode("OggS"));
  page[5] = flags;
  view.setBigUint64(6, BigInt(granule), true);
  view.setUint32(14, 1, true);
  view.setUint32(18, sequence, true);
  page[26] = segments;
  page.fill(255, 27, 27 + segments - 1);
  page[26 + segments] = packet.length % 255;
  page.set(packet, 27 + segments);
  let crc = 0;
  for (const byte of page) {
    crc ^= byte << 24;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc << 1) ^ ((crc & 0x80000000) !== 0 ? 0x04c11db7 : 0);
    }
  }
  view.setUint32(22, crc >>> 0, true);
  return page;
}

export function buildDeviceAudio(
  codec: number,
  packets: readonly Uint8Array[]
): DeviceAudio {
  if (codec !== 1 && codec !== 20 && codec !== 21) fail("unsupported_codec");
  const { frames, discardedLeadingPackets } = reassemble(packets);
  if (codec === 1) {
    const pcm = concat(frames);
    if (
      pcm.length / 16000 > DEVICE_AUDIO_LIMITS.maxDurationSeconds ||
      44 + pcm.length * 2 > DEVICE_AUDIO_LIMITS.maxOutputBytes
    )
      fail("audio_too_large");
    const bytes = new Uint8Array(44 + pcm.length * 2);
    const view = new DataView(bytes.buffer);
    bytes.set(new TextEncoder().encode("RIFF"));
    view.setUint32(4, bytes.length - 8, true);
    bytes.set(new TextEncoder().encode("WAVEfmt "), 8);
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true);
    view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    bytes.set(new TextEncoder().encode("data"), 36);
    view.setUint32(40, pcm.length * 2, true);
    for (let index = 0; index < pcm.length; index += 1)
      view.setInt16(44 + index * 2, (pcm[index]! - 128) * 256, true);
    return {
      bytes,
      contentType: "audio/wav",
      durationSeconds: pcm.length / 16000,
      discardedLeadingPackets,
    };
  }
  const head = new Uint8Array(19);
  head.set(new TextEncoder().encode("OpusHead"));
  head[8] = 1;
  head[9] = 1;
  new DataView(head.buffer).setUint32(12, 16000, true);
  const tags = new Uint8Array(16);
  tags.set(new TextEncoder().encode("OpusTags"));
  const pages = [oggPage(head, 0, 0, 2), oggPage(tags, 1, 0, 0)];
  let granule = 0;
  let outputBytes = pages.reduce((sum, page) => sum + page.length, 0);
  for (let index = 0; index < frames.length; index += 1) {
    const frame = frames[index]!;
    granule += opusSamples(frame);
    if (granule / 48000 > DEVICE_AUDIO_LIMITS.maxDurationSeconds)
      fail("audio_too_large");
    const page = oggPage(
      frame,
      index + 2,
      granule,
      index === frames.length - 1 ? 4 : 0
    );
    outputBytes += page.length;
    if (outputBytes > DEVICE_AUDIO_LIMITS.maxOutputBytes)
      fail("audio_too_large");
    pages.push(page);
  }
  return {
    bytes: concat(pages),
    contentType: "audio/ogg",
    durationSeconds: granule / 48000,
    discardedLeadingPackets,
  };
}
