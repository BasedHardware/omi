import { describe, expect, test } from "bun:test";
import {
  buildDeviceAudio,
  DeviceAudioError,
  type DeviceAudioErrorCode,
  DEVICE_AUDIO_LIMITS,
} from "../src/device-audio";

function packet(sequence: number, fragment: number, payload: number[]) {
  return Uint8Array.from([sequence & 255, sequence >> 8, fragment, ...payload]);
}

function expectError(
  codec: number,
  packets: Uint8Array[],
  code: DeviceAudioErrorCode
) {
  try {
    buildDeviceAudio(codec, packets);
    throw new Error("audio unexpectedly accepted");
  } catch (error) {
    expect(error).toBeInstanceOf(DeviceAudioError);
    expect((error as DeviceAudioError).code).toBe(code);
  }
}

function pages(bytes: Uint8Array) {
  const result: Array<{
    header: number;
    granule: bigint;
    sequence: number;
    payload: Uint8Array;
    lacing: number[];
  }> = [];
  for (let offset = 0; offset < bytes.length; ) {
    const view = new DataView(bytes.buffer, bytes.byteOffset + offset);
    expect(new TextDecoder().decode(bytes.subarray(offset, offset + 4))).toBe(
      "OggS"
    );
    const count = bytes[offset + 26]!;
    const lacing = [...bytes.subarray(offset + 27, offset + 27 + count)];
    const size = 27 + count + lacing.reduce((sum, value) => sum + value, 0);
    const page = bytes.slice(offset, offset + size);
    const expectedCrc = view.getUint32(22, true);
    page.fill(0, 22, 26);
    let crc = 0;
    for (const byte of page) {
      for (let bit = 7; bit >= 0; bit -= 1) {
        const xor = ((crc >>> 31) ^ ((byte >>> bit) & 1)) !== 0;
        crc = (crc << 1) ^ (xor ? 0x04c11db7 : 0);
      }
    }
    expect(crc >>> 0).toBe(expectedCrc);
    result.push({
      header: bytes[offset + 5]!,
      granule: view.getBigUint64(6, true),
      sequence: view.getUint32(18, true),
      payload: bytes.slice(offset + 27 + count, offset + size),
      lacing,
    });
    offset += size;
  }
  return result;
}

describe("device audio containers", () => {
  test("reassembles fragments including counter rollover into unsigned8 to signed16 PCM WAV", () => {
    const audio = buildDeviceAudio(1, [
      packet(65534, 0, [0]),
      packet(65535, 1, [128]),
      packet(0, 0, [255]),
    ]);
    expect(audio.contentType).toBe("audio/wav");
    expect(audio.durationSeconds).toBe(3 / 16000);
    const view = new DataView(audio.bytes.buffer);
    expect(new TextDecoder().decode(audio.bytes.subarray(0, 4))).toBe("RIFF");
    expect(new TextDecoder().decode(audio.bytes.subarray(8, 16))).toBe(
      "WAVEfmt "
    );
    expect(view.getUint32(4, true)).toBe(audio.bytes.length - 8);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(40, true)).toBe(6);
    expect(
      [0, 1, 2].map((index) => view.getInt16(44 + index * 2, true))
    ).toEqual([-32768, 0, 32512]);
  });

  test("reports discarded initial partial frame without guessing its missing bytes", () => {
    const audio = buildDeviceAudio(1, [
      packet(40, 2, [5]),
      packet(41, 0, [128]),
    ]);
    expect(audio.discardedLeadingPackets).toBe(1);
    expect(audio.bytes.length).toBe(46);
    expectError(1, [packet(40, 2, [5])], "empty_audio");
  });

  test.each([20, 21])(
    "codec %i produces valid Ogg headers, CRCs and cumulative 48k granules",
    (codec) => {
      const frames = [
        [0xf8, 0xff, 0xfe],
        [0xf8, 0xff, 0xfe],
      ];
      const audio = buildDeviceAudio(codec, [
        packet(4, 0, frames[0]!.slice(0, 1)),
        packet(5, 1, frames[0]!.slice(1)),
        packet(6, 0, frames[1]!),
      ]);
      const parsed = pages(audio.bytes);
      expect(audio.contentType).toBe("audio/ogg");
      expect(audio.durationSeconds).toBe(0.04);
      expect(parsed.map((page) => page.sequence)).toEqual([0, 1, 2, 3]);
      expect(parsed.map((page) => page.header)).toEqual([2, 0, 0, 4]);
      expect(parsed.map((page) => page.granule)).toEqual([0n, 0n, 960n, 1920n]);
      expect(new TextDecoder().decode(parsed[0]!.payload.subarray(0, 8))).toBe(
        "OpusHead"
      );
      expect(parsed[0]!.payload[9]).toBe(1);
      expect(new DataView(parsed[0]!.payload.buffer).getUint32(12, true)).toBe(
        16000
      );
      expect(new TextDecoder().decode(parsed[1]!.payload.subarray(0, 8))).toBe(
        "OpusTags"
      );
      expect(parsed.slice(2).map((page) => [...page.payload])).toEqual(frames);
    }
  );

  test("terminates an Opus packet whose size is an exact 255-byte segment", () => {
    const frame = [0xf8, ...new Array<number>(254).fill(0)];
    const parsed = pages(buildDeviceAudio(20, [packet(0, 0, frame)]).bytes);
    expect(parsed[2]!.lacing).toEqual([255, 0]);
    expect([...parsed[2]!.payload]).toEqual(frame);
  });

  test("uses Opus TOC duration and validates CBR/VBR packet framing", () => {
    expect(
      buildDeviceAudio(20, [packet(0, 0, [0x80, 0])]).durationSeconds
    ).toBe(0.0025);
    expect(
      buildDeviceAudio(20, [packet(0, 0, [0x18, 0])]).durationSeconds
    ).toBe(0.06);
    expect(
      buildDeviceAudio(20, [packet(0, 0, [0xf9, 0, 0])]).durationSeconds
    ).toBe(0.04);
    expect(
      buildDeviceAudio(20, [packet(0, 0, [0xfa, 1, 0, 0])]).durationSeconds
    ).toBe(0.04);
    expect(
      buildDeviceAudio(20, [packet(0, 0, [0xfb, 3, 0, 0, 0])]).durationSeconds
    ).toBe(0.06);
    for (const payload of [
      [0xfc],
      [0xf9, 0],
      [0xfa, 7, 0],
      [0xfb, 0],
      [0xfb, 7],
      [0xfb, 0x41, 255],
      [0xfb, 0x81, ...new Array<number>(1276).fill(0)],
    ]) {
      expectError(20, [packet(0, 0, payload)], "invalid_opus");
    }
  });

  test("rejects corrupt, missing, duplicate, oversized or unsupported capture input", () => {
    expectError(22, [], "unsupported_codec");
    expectError(1, [], "empty_audio");
    expectError(1, [new Uint8Array([0, 0, 0])], "invalid_packet");
    expectError(1, [packet(1, 0, [1]), packet(3, 0, [2])], "packet_gap");
    expectError(1, [packet(1, 0, [1]), packet(1, 0, [2])], "packet_gap");
    expectError(1, [packet(1, 0, [1]), packet(2, 2, [2])], "packet_gap");
    expectError(
      1,
      [new Uint8Array(DEVICE_AUDIO_LIMITS.maxBytes + 1)],
      "audio_too_large"
    );
    expectError(
      1,
      new Array<Uint8Array>(DEVICE_AUDIO_LIMITS.maxPackets + 1).fill(
        packet(0, 0, [128])
      ),
      "audio_too_large"
    );
  });
});
