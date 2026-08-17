import { describe, it, expect } from 'vitest'
import {
  LEGACY_PACKET_BYTES,
  PAYLOAD_BYTES,
  RING_RECORD_BYTES,
  RingRecordReassembler,
  deletionOrder,
  encodeDeleteFile,
  encodeListFiles,
  encodeReadFile,
  encodeRingAdvance,
  encodeRingRead,
  encodeSdcardCommand,
  isTerminalStatus,
  parseFileList,
  parseLegacyPacket,
  parseRingNotification,
  parseRingStatus,
  parseSdcardStatus,
  parseStatusByte,
  unpackPayload
} from './storageProtocol'

/** Builds a payload from packed `[size][frame]` records, zero padded. */
const packed = (parts: Array<number[] | { epoch: number }>): Uint8Array => {
  const out: number[] = []
  for (const part of parts) {
    if (Array.isArray(part)) {
      out.push(part.length, ...part)
    } else {
      const e = part.epoch
      out.push(0xff, e & 0xff, (e >> 8) & 0xff, (e >> 16) & 0xff, (e >> 24) & 0xff)
    }
  }
  const payload = new Uint8Array(PAYLOAD_BYTES)
  payload.set(out.slice(0, PAYLOAD_BYTES))
  return payload
}

describe('unpackPayload', () => {
  it('reads consecutive frames and skips zero padding', () => {
    const { frames, timestamps } = unpackPayload(
      packed([
        [1, 2, 3],
        [4, 5]
      ])
    )
    expect(frames.map((f) => Array.from(f))).toEqual([
      [1, 2, 3],
      [4, 5]
    ])
    expect(timestamps).toEqual([])
  })

  it('stops at the boundary rather than emitting a truncated frame', () => {
    // A size byte at offset 438 declares a frame that cannot fit: its bytes
    // live in the NEXT payload, so reading it here would emit a short frame
    // and shift every frame after it.
    const payload = new Uint8Array(PAYLOAD_BYTES)
    payload[0] = 2
    payload[1] = 0xaa
    payload[2] = 0xbb
    payload[438] = 10
    const { frames } = unpackPayload(payload)
    expect(frames.length).toBe(1)
    expect(Array.from(frames[0])).toEqual([0xaa, 0xbb])
  })

  it('treats a frame ending exactly at the boundary as belonging to the next payload', () => {
    // offset + 1 + size === 440 must stop: the rule is >=, not >. A size byte
    // holds at most 255, so the exact-boundary case only arises near the end,
    // which is precisely where it happens in practice.
    const payload = new Uint8Array(PAYLOAD_BYTES)
    payload[0] = 1
    payload[1] = 0x11
    const boundaryOffset = 300
    payload[boundaryOffset] = PAYLOAD_BYTES - 1 - boundaryOffset
    expect(boundaryOffset + 1 + payload[boundaryOffset]).toBe(PAYLOAD_BYTES)
    const { frames } = unpackPayload(payload)
    expect(frames.map((f) => Array.from(f))).toEqual([[0x11]])
  })

  it('accepts a frame that ends one byte inside the boundary', () => {
    // The neighbouring case must still be read, or every payload would lose
    // its last frame.
    const payload = new Uint8Array(PAYLOAD_BYTES)
    const offset = 300
    payload[offset] = PAYLOAD_BYTES - 2 - offset
    payload.fill(0x5a, offset + 1, offset + 1 + payload[offset])
    const { frames } = unpackPayload(payload)
    expect(frames.length).toBe(1)
    expect(frames[0].length).toBe(PAYLOAD_BYTES - 2 - offset)
  })

  it('reads embedded capture times and remembers which frames they precede', () => {
    const { frames, timestamps } = unpackPayload(packed([[1], { epoch: 1_723_800_000 }, [2], [3]]))
    expect(frames.length).toBe(3)
    expect(timestamps).toEqual([{ frameIndex: 1, epochSeconds: 1_723_800_000 }])
  })

  it('ignores a truncated timestamp marker at the end', () => {
    const payload = new Uint8Array(PAYLOAD_BYTES)
    payload[0] = 0xff
    payload[1] = 1
    const { frames, timestamps } = unpackPayload(payload.subarray(0, 3))
    expect(frames).toEqual([])
    expect(timestamps).toEqual([])
  })

  it('an all-padding payload yields nothing', () => {
    expect(unpackPayload(new Uint8Array(PAYLOAD_BYTES)).frames).toEqual([])
  })
})

describe('ring commands', () => {
  it('encodes a read with a big-endian sequence', () => {
    expect(Array.from(encodeRingRead(1n))).toEqual([0x11, 0, 0, 0, 0, 0, 0, 0, 1])
    expect(Array.from(encodeRingRead(0x0102030405060708n))).toEqual([0x11, 1, 2, 3, 4, 5, 6, 7, 8])
  })

  it('encodes an optional packet count', () => {
    expect(Array.from(encodeRingRead(0n, 5))).toEqual([0x11, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5])
  })

  it('encodes an advance', () => {
    expect(Array.from(encodeRingAdvance(258n))).toEqual([0x12, 0, 0, 0, 0, 0, 0, 1, 2])
  })
})

describe('ring status', () => {
  it('reads the four little-endian counters', () => {
    const bytes = new Uint8Array(16)
    new DataView(bytes.buffer).setUint32(0, 1000, true)
    new DataView(bytes.buffer).setUint32(4, 7, true)
    new DataView(bytes.buffer).setUint32(8, 2000, true)
    new DataView(bytes.buffer).setUint32(12, 1, true)
    expect(parseRingStatus(bytes)).toEqual({
      usedBytes: 1000,
      unreadPackets: 7,
      freeBytes: 2000,
      rtcValid: true
    })
  })

  it('reports an unreliable clock, which makes record times untrustworthy', () => {
    const bytes = new Uint8Array(16)
    expect(parseRingStatus(bytes)?.rtcValid).toBe(false)
  })

  it('refuses a short read', () => {
    expect(parseRingStatus(new Uint8Array(8))).toBeNull()
  })
})

describe('ring notifications', () => {
  it('parses an ack', () => {
    expect(parseRingNotification(Uint8Array.from([0x01, 0]))).toEqual({
      kind: 'ack',
      ok: true,
      status: 0
    })
    expect(parseRingNotification(Uint8Array.from([0x01, 9]))).toMatchObject({ ok: false })
  })

  it('parses info', () => {
    const bytes = new Uint8Array(31)
    bytes[0] = 0x02
    bytes[8] = 4 // read_seq low byte
    bytes[16] = 9 // write_seq low byte
    bytes[20] = 200 // capacity low byte
    bytes[28] = 3 // dropped low byte
    bytes[29] = 0x01
    bytes[30] = 0xbc // packet_size 444
    const parsed = parseRingNotification(bytes)
    expect(parsed).toMatchObject({
      kind: 'info',
      readSeq: 4n,
      writeSeq: 9n,
      capacity: 200,
      dropped: 3n,
      packetSize: 444
    })
  })

  it('parses done with the sequence to commit', () => {
    const bytes = new Uint8Array(10)
    bytes[0] = 0x04
    bytes[1] = 0
    bytes[9] = 42
    expect(parseRingNotification(bytes)).toEqual({
      kind: 'done',
      ok: true,
      status: 0,
      nextSeq: 42n
    })
  })

  it('parses read-begin and data', () => {
    const begin = new Uint8Array(13)
    begin[0] = 0x05
    begin[8] = 7
    begin[12] = 3
    expect(parseRingNotification(begin)).toEqual({
      kind: 'readBegin',
      startSeq: 7n,
      packetCount: 3
    })

    const data = parseRingNotification(Uint8Array.from([0x03, 1, 2, 3]))
    expect(data).toMatchObject({ kind: 'data' })
    expect(Array.from((data as { bytes: Uint8Array }).bytes)).toEqual([1, 2, 3])
  })

  it('reports an unknown opcode instead of guessing', () => {
    expect(parseRingNotification(Uint8Array.from([0x7f]))).toEqual({
      kind: 'unknown',
      opcode: 0x7f
    })
    expect(parseRingNotification(new Uint8Array(0))).toBeNull()
  })

  it('refuses a truncated frame rather than reading past it', () => {
    expect(parseRingNotification(Uint8Array.from([0x02, 1, 2]))).toBeNull()
    expect(parseRingNotification(Uint8Array.from([0x04, 0]))).toBeNull()
    expect(parseRingNotification(Uint8Array.from([0x05, 0]))).toBeNull()
  })
})

describe('RingRecordReassembler', () => {
  const record = (epoch: number, fill: number): Uint8Array => {
    const out = new Uint8Array(RING_RECORD_BYTES)
    new DataView(out.buffer).setUint32(0, epoch, false)
    out.fill(fill, 4)
    return out
  }

  it('slices records out of unaligned data notifications', () => {
    const reassembler = new RingRecordReassembler()
    const first = record(100, 1)
    const second = record(200, 2)
    const stream = new Uint8Array(RING_RECORD_BYTES * 2)
    stream.set(first, 0)
    stream.set(second, RING_RECORD_BYTES)

    // Deliberately split mid-record: the transport does not align to records.
    expect(reassembler.push(stream.subarray(0, 100))).toEqual([])
    expect(reassembler.push(stream.subarray(100, 500))).toHaveLength(1)
    const rest = reassembler.push(stream.subarray(500))
    expect(rest).toHaveLength(1)
    expect(rest[0].epochSeconds).toBe(200)
    expect(reassembler.bufferedBytes).toBe(0)
  })

  it('holds a partial tail instead of emitting a short record', () => {
    const reassembler = new RingRecordReassembler()
    expect(reassembler.push(record(1, 1).subarray(0, RING_RECORD_BYTES - 1))).toEqual([])
    expect(reassembler.bufferedBytes).toBe(RING_RECORD_BYTES - 1)
  })

  it('reset drops buffered bytes', () => {
    const reassembler = new RingRecordReassembler()
    reassembler.push(new Uint8Array(10))
    reassembler.reset()
    expect(reassembler.bufferedBytes).toBe(0)
  })
})

describe('multi-file storage', () => {
  it('encodes list, read and delete', () => {
    expect(Array.from(encodeListFiles())).toEqual([0x10])
    expect(Array.from(encodeReadFile(2, 0x01020304))).toEqual([0x11, 2, 1, 2, 3, 4])
    expect(Array.from(encodeDeleteFile(3))).toEqual([0x12, 3])
  })

  it('parses a listing into indexed files', () => {
    const bytes = new Uint8Array(1 + 16)
    bytes[0] = 2
    const view = new DataView(bytes.buffer)
    view.setUint32(1, 1_723_800_000, false)
    view.setUint32(5, 4096, false)
    view.setUint32(9, 1_723_900_000, false)
    view.setUint32(13, 8192, false)
    expect(parseFileList(bytes)).toEqual([
      { index: 0, epochSeconds: 1_723_800_000, sizeBytes: 4096 },
      { index: 1, epochSeconds: 1_723_900_000, sizeBytes: 8192 }
    ])
  })

  it('parses an empty listing', () => {
    expect(parseFileList(Uint8Array.from([0]))).toEqual([])
  })

  it('rejects a listing that would read past the frame', () => {
    // A corrupt count must not make the parser read beyond the notification.
    expect(parseFileList(Uint8Array.from([5, 1, 2, 3]))).toBeNull()
    expect(parseFileList(Uint8Array.from([200]))).toBeNull()
    expect(parseFileList(new Uint8Array(0))).toBeNull()
  })

  it('deletes the highest index first because the firmware re-indexes', () => {
    // Deleting 0 first would shift 1 and 2 down, so the next delete would take
    // the wrong file.
    expect(deletionOrder([0, 1, 2])).toEqual([2, 1, 0])
    expect(deletionOrder([2, 0, 2, 1])).toEqual([2, 1, 0])
    expect(deletionOrder([])).toEqual([])
  })
})

describe('legacy SD card', () => {
  it('encodes the six byte command with a big-endian offset', () => {
    expect(Array.from(encodeSdcardCommand(0, 1, 0x0000_0140))).toEqual([0, 1, 0, 0, 1, 0x40])
  })

  it('parses status, including the capture time on newer firmware', () => {
    const bytes = new Uint8Array(12)
    const view = new DataView(bytes.buffer)
    view.setUint32(0, 5000, true)
    view.setUint32(4, 1200, true)
    view.setUint32(8, 1_723_800_000, true)
    expect(parseSdcardStatus(bytes)).toEqual({
      totalBytes: 5000,
      syncedOffset: 1200,
      recordingStartEpoch: 1_723_800_000
    })
  })

  it('tolerates older firmware with no capture time', () => {
    const bytes = new Uint8Array(8)
    new DataView(bytes.buffer).setUint32(0, 10, true)
    expect(parseSdcardStatus(bytes)).toMatchObject({ recordingStartEpoch: null })
    expect(parseSdcardStatus(new Uint8Array(4))).toBeNull()
  })

  it('parses an 83 byte packet', () => {
    const bytes = new Uint8Array(LEGACY_PACKET_BYTES)
    bytes[0] = 0x34
    bytes[1] = 0x12
    bytes[2] = 1
    bytes[3] = 3
    bytes.set([7, 8, 9], 4)
    expect(parseLegacyPacket(bytes)).toEqual({
      packetId: 0x1234,
      fragment: 1,
      frame: Uint8Array.from([7, 8, 9])
    })
  })

  it('rejects a packet whose declared frame does not fit', () => {
    const bytes = new Uint8Array(LEGACY_PACKET_BYTES)
    bytes[3] = 200
    expect(parseLegacyPacket(bytes)).toBeNull()
    bytes[3] = 0
    expect(parseLegacyPacket(bytes)).toBeNull()
    expect(parseLegacyPacket(new Uint8Array(50))).toBeNull()
  })
})

describe('status bytes', () => {
  it('names each reply and treats anything unknown as the end', () => {
    expect(parseStatusByte(0)).toEqual({ kind: 'ok' })
    expect(parseStatusByte(3)).toEqual({ kind: 'badFileSize' })
    expect(parseStatusByte(4)).toEqual({ kind: 'empty' })
    expect(parseStatusByte(100)).toEqual({ kind: 'complete' })
    // Continuing past an unrecognized reply would read frames the device is no
    // longer sending.
    expect(parseStatusByte(77)).toEqual({ kind: 'error', code: 77 })
  })

  it('only ok continues the transfer', () => {
    expect(isTerminalStatus(parseStatusByte(0))).toBe(false)
    for (const code of [3, 4, 100, 77]) {
      expect(isTerminalStatus(parseStatusByte(code))).toBe(true)
    }
  })
})
