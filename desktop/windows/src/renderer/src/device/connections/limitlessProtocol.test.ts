import { describe, it, expect } from 'vitest'
import {
  boundedFieldLength,
  commandBodies,
  decodeVarint,
  encodeBytesField,
  encodeCommand,
  encodeVarint,
  encodeVarintField,
  extractOpusFrames,
  extractOpusFramesFromFlashPage,
  extractOpusRecursive,
  parseBlePacket,
  parseFlashPageInfo,
  parseStorageStateFromDeviceStatus,
  tryParseButtonStatus,
  tryParseDeviceStatus
} from './limitlessProtocol'

const bytes = (...values: number[]): Uint8Array => Uint8Array.from(values)

/** A 12-byte frame starting with a valid Opus TOC. */
const opusFrame = (toc = 0xb8): Uint8Array =>
  Uint8Array.from([toc, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])

describe('varint', () => {
  it('round-trips small and multi-byte values', () => {
    for (const value of [0, 1, 127, 128, 300, 16_383, 16_384, 2 ** 31, 1_700_000_000_000]) {
      const encoded = encodeVarint(value)
      const decoded = decodeVarint(encoded, 0)
      expect(decoded).not.toBeNull()
      expect(decoded!.value).toBe(value)
      expect(decoded!.next).toBe(encoded.length)
    }
  })

  it('caps malformed varints at 10 bytes', () => {
    const endless = new Uint8Array(12).fill(0x80)
    expect(decodeVarint(endless, 0)).toBeNull()
  })

  it('boundedFieldLength clamps to the remaining buffer', () => {
    expect(boundedFieldLength(5, 2, 10)).toBe(5)
    expect(boundedFieldLength(50, 8, 10)).toBe(2)
    expect(boundedFieldLength(0, 2, 10)).toBe(0)
    expect(boundedFieldLength(5, 10, 10)).toBe(0)
    expect(boundedFieldLength(5, -1, 10)).toBe(0)
  })
})

describe('command encoding', () => {
  it('wraps commands so they parse back as BLE packets', () => {
    const command = encodeCommand(7, 3, 6, commandBodies.timeSync(1_700_000_000_000))
    const packet = parseBlePacket(command)
    expect(packet).not.toBeNull()
    expect(packet!.index).toBe(7)
    expect(packet!.seq).toBe(0)
    expect(packet!.numFrags).toBe(1)
    // The payload starts with the message field (msg 6, wire 2 -> tag 0x32).
    expect(packet!.payload[0]).toBe((6 << 3) | 2)
    // ...and ends with request-data field 30 (tag 0xf2 0x01).
    const tail = packet!.payload
    const requestTag = decodeVarint(tail, indexOfRequestField(tail))
    expect(requestTag!.value).toBe((30 << 3) | 2)
  })

  it('encodes the documented command bodies', () => {
    expect(commandBodies.enableDataStream(true)).toEqual(
      bytes((1 << 3) | 0, 0x00, (2 << 3) | 0, 0x01)
    )
    expect(commandBodies.downloadFlashPages(true, false)).toEqual(
      bytes((1 << 3) | 0, 0x01, (2 << 3) | 0, 0x00)
    )
    expect(commandBodies.getDeviceStatus().length).toBe(0)
    expect(commandBodies.setLedBrightness(150)).toEqual(bytes((1 << 3) | 0, 100))
    expect(commandBodies.unpairBluetooth()).toEqual(bytes((1 << 3) | 0, 0x01))
  })
})

const indexOfRequestField = (payload: Uint8Array): number => {
  // Walk fields until field 30 is reached.
  let pos = 0
  while (pos < payload.length) {
    const tag = decodeVarint(payload, pos)!
    if (tag.value >> 3 === 30) return pos
    const length = decodeVarint(payload, tag.next)!
    pos = length.next + length.value
  }
  return -1
}

describe('parseBlePacket', () => {
  it('requires index, numFrags, and payload', () => {
    expect(parseBlePacket(encodeVarintField(1, 5))).toBeNull()
    const full = Uint8Array.from([
      ...encodeVarintField(1, 5),
      ...encodeVarintField(3, 1),
      ...encodeBytesField(4, bytes(1, 2, 3))
    ])
    const packet = parseBlePacket(full)
    expect(packet).toMatchObject({ index: 5, seq: 0, numFrags: 1 })
    expect(Array.from(packet!.payload)).toEqual([1, 2, 3])
  })
})

describe('opus extraction', () => {
  it('extractOpusRecursive takes valid TOC fields in the length window and recurses otherwise', () => {
    const frame = opusFrame()
    const nested = encodeBytesField(1, encodeBytesField(2, frame))
    const frames = extractOpusRecursive(nested)
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })

  it('rejects frames outside the 10-200 byte window', () => {
    const tiny = encodeBytesField(1, bytes(0xb8, 1, 2))
    expect(extractOpusRecursive(tiny)).toEqual([])
  })

  it('extractOpusFramesFromFlashPage skips the leading varints and walks 0x1a wrappers', () => {
    const frame = opusFrame(0x78)
    // Wrapper (field 3, tag 0x1a) holding an offset varint and the audio
    // bytes field (field 2) that contains a nested frame.
    const inner = Uint8Array.from([
      ...encodeVarintField(1, 42),
      ...encodeBytesField(2, encodeBytesField(1, frame))
    ])
    const page = Uint8Array.from([
      ...encodeVarintField(1, 1_700_000_000_000),
      ...encodeVarintField(2, 9),
      ...encodeBytesField(3, inner)
    ])
    const frames = extractOpusFramesFromFlashPage(page)
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })

  it('extractOpusFrames falls back to raw 0x22 marker scanning', () => {
    const frame = opusFrame(0xf8)
    const raw = Uint8Array.from([0x00, 0x22, frame.length, ...frame, 0x99])
    const frames = extractOpusFrames(raw)
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })

  it('extractOpusFrames resumes scanning after an invalid marker', () => {
    const frame = opusFrame(0xb0)
    const raw = Uint8Array.from([0x22, 0xff, 0x22, frame.length, ...frame])
    const frames = extractOpusFrames(raw)
    expect(frames.length).toBe(1)
  })
})

describe('flash page info', () => {
  it('parses the timestamp and lifecycle flags', () => {
    const storageStatus = bytes(0x08, 0x01, 0x10, 0x00)
    const audioStatus = bytes(0x40, 0x01, 0x48, 0x01)
    const chunk = Uint8Array.from([
      0x62,
      storageStatus.length,
      ...storageStatus,
      0x12,
      audioStatus.length,
      ...audioStatus
    ])
    const page = Uint8Array.from([
      ...encodeVarintField(1, 1_700_000_123_456),
      0x1a,
      chunk.length,
      ...chunk
    ])
    const info = parseFlashPageInfo(page)
    expect(info.timestampMs).toBe(1_700_000_123_456)
    expect(info.didStartSession).toBe(true)
    expect(info.didStopSession).toBe(false)
    expect(info.didStartRecording).toBe(true)
    expect(info.didStopRecording).toBe(true)
  })
})

describe('button status scan', () => {
  const buttonFrame = (eventValue: number): Uint8Array => {
    const button = bytes(0x08, eventValue)
    const payload = Uint8Array.from([0x42, button.length, ...button])
    return Uint8Array.from([0x00, 0x00, 0x22, payload.length, ...payload, 0x00, 0x00, 0x00])
  }

  it('finds the event value inside the nested structure', () => {
    expect(tryParseButtonStatus(buttonFrame(3))).toBe(3)
    expect(tryParseButtonStatus(buttonFrame(1))).toBe(1)
  })

  it('rejects short frames and out-of-range events', () => {
    expect(tryParseButtonStatus(bytes(0x22, 0x02, 0x42))).toBeNull()
    expect(tryParseButtonStatus(buttonFrame(9))).toBeNull()
  })
})

describe('device status scan', () => {
  it('parses storage state markers from the nested status', () => {
    // Values above 127 must be real multi-byte varints (200 -> 0xC8 0x01).
    const inner = Uint8Array.from([
      0x08,
      ...encodeVarint(5),
      0x10,
      ...encodeVarint(12),
      0x18,
      ...encodeVarint(2),
      0x20,
      ...encodeVarint(100),
      0x28,
      ...encodeVarint(200)
    ])
    const status = Uint8Array.from([0x00, 0x2a, inner.length, ...inner])
    const payload = Uint8Array.from([0x2a, status.length, ...status, 0x00, 0x00, 0x00])
    const frame = Uint8Array.from([0x22, payload.length, ...payload, ...new Uint8Array(8)])
    const state = tryParseDeviceStatus(frame)
    expect(state).toEqual({
      oldestFlashPage: 5,
      newestFlashPage: 12,
      currentStorageSession: 2,
      freeCapturePages: 100,
      totalCapturePages: 200
    })
  })

  it('parseStorageStateFromDeviceStatus returns null with no markers', () => {
    expect(parseStorageStateFromDeviceStatus(bytes(0x2a, 3, 0x99, 0x98, 0x97))).toBeNull()
  })
})
