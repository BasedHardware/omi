/**
 * Wire protocol for draining recordings the Omi device stored while it was away
 * from a phone or laptop. Three firmware generations coexist and all share the
 * storage service: control and data on `30295781`, status on `30295782`. Pure
 * parsing and encoding so every byte-level rule is testable without a device.
 *
 * Ported from the Flutter authority: `ring_protocol.dart`, `storage_sync.dart`
 * and `sdcard_wal_sync.dart`.
 *
 * The one rule that repeats everywhere and is easy to get wrong: a packed audio
 * payload stops at `offset + 1 + size >= 440`. Not `>`. A size byte sitting on
 * the boundary describes a frame that lives in the NEXT payload, so reading it
 * here would emit a truncated frame and shift everything after it.
 */

/** Bytes of packed audio in one storage payload. */
export const PAYLOAD_BYTES = 440
/** A ring record is a timestamp plus one payload. */
export const RING_RECORD_BYTES = 444
/** Marks an embedded capture time inside a payload (firmware 3.0.16+). */
export const TIMESTAMP_MARKER = 0xff

// --- shared payload unpacking ------------------------------------------------

export interface UnpackedPayload {
  frames: Uint8Array[]
  /** Capture times embedded mid-payload, with the frame index they apply from. */
  timestamps: Array<{ frameIndex: number; epochSeconds: number }>
}

/**
 * Unpacks `[size u8][frame bytes]` records out of a payload.
 *
 * `size == 0` is padding and skips one byte. `size == 0xFF` introduces a four
 * byte little-endian capture time rather than a frame. Parsing stops at the
 * boundary rule above, so trailing bytes are left for the next payload.
 */
export function unpackPayload(payload: Uint8Array): UnpackedPayload {
  const frames: Uint8Array[] = []
  const timestamps: UnpackedPayload['timestamps'] = []
  const limit = Math.min(payload.length, PAYLOAD_BYTES)
  let offset = 0

  while (offset < limit) {
    const size = payload[offset]
    if (size === 0) {
      offset += 1
      continue
    }
    if (size === TIMESTAMP_MARKER) {
      // Marker plus a four byte epoch; a truncated marker ends the payload.
      if (offset + 5 > limit) break
      const epochSeconds =
        payload[offset + 1] |
        (payload[offset + 2] << 8) |
        (payload[offset + 3] << 16) |
        (payload[offset + 4] << 24)
      timestamps.push({ frameIndex: frames.length, epochSeconds: epochSeconds >>> 0 })
      offset += 5
      continue
    }
    // The boundary rule: a frame that would run to or past the payload end
    // belongs to the next payload.
    if (offset + 1 + size >= PAYLOAD_BYTES) break
    frames.push(payload.slice(offset + 1, offset + 1 + size))
    offset += 1 + size
  }

  return { frames, timestamps }
}

// --- ring buffer (firmware 3.0.20 and later) ---------------------------------

export const RING_CMD = {
  stop: 0x03,
  info: 0x10,
  read: 0x11,
  advance: 0x12,
  clear: 0x13
} as const

export const RING_OPCODE = {
  ack: 0x01,
  info: 0x02,
  data: 0x03,
  done: 0x04,
  readBegin: 0x05
} as const

const writeUint64BE = (value: bigint): Uint8Array => {
  const out = new Uint8Array(8)
  let remaining = value
  for (let i = 7; i >= 0; i -= 1) {
    out[i] = Number(remaining & 0xffn)
    remaining >>= 8n
  }
  return out
}

const readUint64BE = (bytes: Uint8Array, offset: number): bigint => {
  let value = 0n
  for (let i = 0; i < 8; i += 1) value = (value << 8n) | BigInt(bytes[offset + i])
  return value
}

const readUint32BE = (bytes: Uint8Array, offset: number): number =>
  ((bytes[offset] << 24) |
    (bytes[offset + 1] << 16) |
    (bytes[offset + 2] << 8) |
    bytes[offset + 3]) >>>
  0

const readUint32LE = (bytes: Uint8Array, offset: number): number =>
  (bytes[offset] |
    (bytes[offset + 1] << 8) |
    (bytes[offset + 2] << 16) |
    (bytes[offset + 3] << 24)) >>>
  0

/** `[0x11][start_seq u64 BE]`, optionally `[count u32 BE]` to bound the read. */
export function encodeRingRead(startSeq: bigint, count?: number): Uint8Array {
  const seq = writeUint64BE(startSeq)
  if (count === undefined) return Uint8Array.from([RING_CMD.read, ...seq])
  return Uint8Array.from([
    RING_CMD.read,
    ...seq,
    (count >>> 24) & 0xff,
    (count >>> 16) & 0xff,
    (count >>> 8) & 0xff,
    count & 0xff
  ])
}

/** `[0x12][new_read_seq u64 BE]`. Durably commits consumer progress. */
export function encodeRingAdvance(newReadSeq: bigint): Uint8Array {
  return Uint8Array.from([RING_CMD.advance, ...writeUint64BE(newReadSeq)])
}

export const encodeRingInfo = (): Uint8Array => Uint8Array.from([RING_CMD.info])
export const encodeRingClear = (): Uint8Array => Uint8Array.from([RING_CMD.clear])
export const encodeStorageStop = (): Uint8Array => Uint8Array.from([RING_CMD.stop])

export interface RingStatus {
  usedBytes: number
  unreadPackets: number
  freeBytes: number
  /** False when the device clock is unreliable, so record times cannot be trusted. */
  rtcValid: boolean
}

/** The 16 byte status read: four little-endian u32s, unlike everything else. */
export function parseRingStatus(bytes: Uint8Array): RingStatus | null {
  if (bytes.length < 16) return null
  return {
    usedBytes: readUint32LE(bytes, 0),
    unreadPackets: readUint32LE(bytes, 4),
    freeBytes: readUint32LE(bytes, 8),
    rtcValid: readUint32LE(bytes, 12) !== 0
  }
}

export type RingNotification =
  | { kind: 'ack'; ok: boolean; status: number }
  | {
      kind: 'info'
      readSeq: bigint
      writeSeq: bigint
      capacity: number
      dropped: bigint
      packetSize: number
    }
  | { kind: 'data'; bytes: Uint8Array }
  | { kind: 'done'; ok: boolean; status: number; nextSeq: bigint }
  | { kind: 'readBegin'; startSeq: bigint; packetCount: number }
  | { kind: 'unknown'; opcode: number }

export function parseRingNotification(bytes: Uint8Array): RingNotification | null {
  if (bytes.length === 0) return null
  switch (bytes[0]) {
    case RING_OPCODE.ack:
      if (bytes.length < 2) return null
      return { kind: 'ack', ok: bytes[1] === 0, status: bytes[1] }
    case RING_OPCODE.info:
      if (bytes.length < 31) return null
      return {
        kind: 'info',
        readSeq: readUint64BE(bytes, 1),
        writeSeq: readUint64BE(bytes, 9),
        capacity: readUint32BE(bytes, 17),
        dropped: readUint64BE(bytes, 21),
        packetSize: (bytes[29] << 8) | bytes[30]
      }
    case RING_OPCODE.data:
      return { kind: 'data', bytes: bytes.slice(1) }
    case RING_OPCODE.done:
      if (bytes.length < 10) return null
      return { kind: 'done', ok: bytes[1] === 0, status: bytes[1], nextSeq: readUint64BE(bytes, 2) }
    case RING_OPCODE.readBegin:
      if (bytes.length < 13) return null
      return {
        kind: 'readBegin',
        startSeq: readUint64BE(bytes, 1),
        packetCount: readUint32BE(bytes, 9)
      }
    default:
      return { kind: 'unknown', opcode: bytes[0] }
  }
}

export interface RingRecord {
  /** Device capture time for this record, epoch seconds. */
  epochSeconds: number
  payload: Uint8Array
}

/**
 * Data notifications are not aligned to record boundaries, so bytes are
 * accumulated and sliced into fixed records. A partial tail waits for the next
 * notification instead of being emitted short.
 */
export class RingRecordReassembler {
  private buffer = new Uint8Array(0)

  get bufferedBytes(): number {
    return this.buffer.length
  }

  push(bytes: Uint8Array): RingRecord[] {
    if (bytes.length > 0) {
      const merged = new Uint8Array(this.buffer.length + bytes.length)
      merged.set(this.buffer, 0)
      merged.set(bytes, this.buffer.length)
      this.buffer = merged
    }
    const records: RingRecord[] = []
    while (this.buffer.length >= RING_RECORD_BYTES) {
      const record = this.buffer.subarray(0, RING_RECORD_BYTES)
      records.push({
        epochSeconds: readUint32BE(record, 0),
        payload: record.slice(4, RING_RECORD_BYTES)
      })
      this.buffer = this.buffer.subarray(RING_RECORD_BYTES)
    }
    return records
  }

  reset(): void {
    this.buffer = new Uint8Array(0)
  }
}

// --- multi-file storage (LittleFS) -------------------------------------------

export const FILE_CMD = {
  stop: 0x03,
  list: 0x10,
  read: 0x11,
  delete: 0x12
} as const

export const encodeListFiles = (): Uint8Array => Uint8Array.from([FILE_CMD.list])

/** Read uses the legacy six byte shape: `[cmd][index][offset u32 BE]`. */
export function encodeReadFile(fileIndex: number, offset: number): Uint8Array {
  return Uint8Array.from([
    FILE_CMD.read,
    fileIndex & 0xff,
    (offset >>> 24) & 0xff,
    (offset >>> 16) & 0xff,
    (offset >>> 8) & 0xff,
    offset & 0xff
  ])
}

export const encodeDeleteFile = (fileIndex: number): Uint8Array =>
  Uint8Array.from([FILE_CMD.delete, fileIndex & 0xff])

export interface StoredFile {
  /** Position in the listing, which is what read and delete address. */
  index: number
  epochSeconds: number
  sizeBytes: number
}

/** `[count u8]` then `[timestamp u32 BE][size u32 BE]` per file. */
export function parseFileList(bytes: Uint8Array): StoredFile[] | null {
  if (bytes.length < 1) return null
  const count = bytes[0]
  // The firmware caps its table at 128; a larger count is a corrupt frame, not
  // a listing, and trusting it would read past the notification.
  if (count > 128) return null
  const files: StoredFile[] = []
  for (let i = 0; i < count; i += 1) {
    const offset = 1 + i * 8
    if (offset + 8 > bytes.length) return null
    files.push({
      index: i,
      epochSeconds: readUint32BE(bytes, offset),
      sizeBytes: readUint32BE(bytes, offset + 4)
    })
  }
  return files
}

/**
 * Order for deleting a set of files. The firmware re-indexes what remains
 * downward after each delete, so removing the highest index first keeps every
 * other index valid.
 */
export function deletionOrder(indices: number[]): number[] {
  return [...new Set(indices)].sort((a, b) => b - a)
}

// --- legacy SD card ----------------------------------------------------------

export const SDCARD_CMD = {
  read: 0x00,
  clear: 0x01,
  stop: 0x03
} as const

/** Legacy command frame: `[command][fileNum][offset u32 BE]`. */
export function encodeSdcardCommand(command: number, fileNum: number, offset: number): Uint8Array {
  return Uint8Array.from([
    command & 0xff,
    fileNum & 0xff,
    (offset >>> 24) & 0xff,
    (offset >>> 16) & 0xff,
    (offset >>> 8) & 0xff,
    offset & 0xff
  ])
}

export interface SdcardStatus {
  totalBytes: number
  /** Bytes already drained, so a resumed sync does not re-read them. */
  syncedOffset: number
  /** Recording start, epoch seconds. Firmware 3.0.16 and later. */
  recordingStartEpoch: number | null
}

/** Status read: consecutive little-endian u32s. */
export function parseSdcardStatus(bytes: Uint8Array): SdcardStatus | null {
  if (bytes.length < 8) return null
  return {
    totalBytes: readUint32LE(bytes, 0),
    syncedOffset: readUint32LE(bytes, 4),
    recordingStartEpoch: bytes.length >= 12 ? readUint32LE(bytes, 8) : null
  }
}

/** Single byte replies shared by the legacy and multi-file protocols. */
export type StorageStatusByte =
  | { kind: 'ok' }
  | { kind: 'badFileSize' }
  | { kind: 'empty' }
  | { kind: 'complete' }
  | { kind: 'error'; code: number }

export function parseStatusByte(code: number): StorageStatusByte {
  switch (code) {
    case 0:
      return { kind: 'ok' }
    case 3:
      return { kind: 'badFileSize' }
    case 4:
      return { kind: 'empty' }
    case 100:
      return { kind: 'complete' }
    default:
      // Anything unrecognized ends the transfer: continuing would read frames
      // the device is no longer sending.
      return { kind: 'error', code }
  }
}

/** True when a status byte means the transfer is over, however it ended. */
export function isTerminalStatus(status: StorageStatusByte): boolean {
  return status.kind !== 'ok'
}

/** Bytes of file consumed per legacy 83 byte packet. */
export const LEGACY_PACKET_ADVANCE = 80
export const LEGACY_PACKET_BYTES = 83

/**
 * Legacy packet: `[packet_id u16 LE][fragment u8][frame_len u8][frame]`. A
 * declared length that would run past the packet is corrupt and yields nothing
 * rather than a truncated frame.
 */
export function parseLegacyPacket(
  bytes: Uint8Array
): { packetId: number; fragment: number; frame: Uint8Array } | null {
  if (bytes.length !== LEGACY_PACKET_BYTES) return null
  const frameLength = bytes[3]
  if (frameLength <= 0 || 4 + frameLength > LEGACY_PACKET_BYTES) return null
  return {
    packetId: bytes[0] | (bytes[1] << 8),
    fragment: bytes[2],
    frame: bytes.slice(4, 4 + frameLength)
  }
}
