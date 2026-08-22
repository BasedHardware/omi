/**
 * Limitless pendant wire protocol — pure encode/parse port of the protobuf
 * layer in macOS Connections/LimitlessDeviceConnection.swift. The pendant
 * speaks hand-rolled varint protobuf over BLE; every length is clamped
 * through boundedFieldLength so corrupt packets can never crash or hang the
 * parsers.
 */

export const VALID_OPUS_TOC_BYTES: ReadonlySet<number> = new Set([
  0xb8, 0x78, 0xf8, 0xb0, 0x70, 0xf0
])

const VARINT_MAX_BYTES = 10
const OPUS_FRAME_MIN_BYTES = 10
const OPUS_FRAME_MAX_BYTES = 200
/** 2020-01-01 in epoch milliseconds: flash-page timestamp sanity floor. */
export const FLASH_TIMESTAMP_SANITY_FLOOR_MS = 1_577_836_800_000

export const LIMITLESS_MSG = {
  timeSync: 6,
  acknowledgeProcessedData: 7,
  dataStream: 8,
  unpairBluetooth: 15,
  getDeviceStatus: 21,
  setLedBrightness: 26
} as const

// --- varint -----------------------------------------------------------------

export const encodeVarint = (value: number): Uint8Array => {
  let big = BigInt(Math.trunc(value))
  const out: number[] = []
  do {
    let byte = Number(big & 0x7fn)
    big >>= 7n
    if (big > 0n) byte |= 0x80
    out.push(byte)
  } while (big > 0n)
  return Uint8Array.from(out)
}

export interface VarintResult {
  value: number
  next: number
}

export const decodeVarint = (data: Uint8Array, pos: number): VarintResult | null => {
  let result = 0n
  let shift = 0n
  let index = pos
  let bytesRead = 0
  while (index < data.length && bytesRead < VARINT_MAX_BYTES) {
    const byte = data[index]
    result |= BigInt(byte & 0x7f) << shift
    index += 1
    bytesRead += 1
    if ((byte & 0x80) === 0) return { value: Number(result), next: index }
    shift += 7n
  }
  return null
}

/** Clamp a length-delimited field before slicing: zero unless the length is
 *  positive and the position is inside the buffer, else clamped to what
 *  actually remains. */
export const boundedFieldLength = (length: number, pos: number, count: number): number => {
  if (!(length > 0 && pos >= 0 && pos < count)) return 0
  return Math.min(length, count - pos)
}

// --- encoding ---------------------------------------------------------------

const concatBytes = (...parts: Uint8Array[]): Uint8Array => {
  const total = parts.reduce((sum, p) => sum + p.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

export const encodeVarintField = (fieldNum: number, value: number): Uint8Array =>
  concatBytes(encodeVarint((fieldNum << 3) | 0), encodeVarint(value))

export const encodeBytesField = (fieldNum: number, bytes: Uint8Array): Uint8Array =>
  concatBytes(encodeVarint((fieldNum << 3) | 2), encodeVarint(bytes.length), bytes)

/** Every outbound command is wrapped: field1 = messageIndex, field2 = seq 0,
 *  field3 = numFrags 1, field4 = payload. */
export const encodeBleWrapper = (messageIndex: number, payload: Uint8Array): Uint8Array =>
  concatBytes(
    encodeVarintField(1, messageIndex),
    encodeVarintField(2, 0),
    encodeVarintField(3, 1),
    encodeBytesField(4, payload)
  )

/** Request-data trailer appended to every command: message field 30 with
 *  {field1 = requestId, field2 = 0}. */
export const encodeRequestData = (requestId: number): Uint8Array =>
  encodeBytesField(30, concatBytes(encodeVarintField(1, requestId), encodeVarintField(2, 0)))

export const encodeCommand = (
  messageIndex: number,
  requestId: number,
  msgNum: number,
  body: Uint8Array
): Uint8Array =>
  encodeBleWrapper(
    messageIndex,
    concatBytes(encodeBytesField(msgNum, body), encodeRequestData(requestId))
  )

export const commandBodies = {
  timeSync: (epochMs: number): Uint8Array => encodeVarintField(1, epochMs),
  enableDataStream: (enable = true): Uint8Array =>
    concatBytes(encodeVarintField(1, 0), encodeVarintField(2, enable ? 1 : 0)),
  getDeviceStatus: (): Uint8Array => new Uint8Array(0),
  downloadFlashPages: (batchMode: boolean, realTime: boolean): Uint8Array =>
    concatBytes(encodeVarintField(1, batchMode ? 1 : 0), encodeVarintField(2, realTime ? 1 : 0)),
  acknowledgeProcessedData: (upToIndex: number): Uint8Array => encodeVarintField(1, upToIndex),
  setLedBrightness: (value: number): Uint8Array =>
    encodeVarintField(1, Math.max(0, Math.min(100, Math.round(value)))),
  unpairBluetooth: (doNotReset = true): Uint8Array => encodeVarintField(1, doNotReset ? 1 : 0)
}

// --- inbound packet parsing -------------------------------------------------

export interface BlePacket {
  index: number
  seq: number
  numFrags: number
  payload: Uint8Array
}

export const parseBlePacket = (data: Uint8Array): BlePacket | null => {
  let pos = 0
  let index: number | null = null
  let seq = 0
  let numFrags: number | null = null
  let payload: Uint8Array | null = null
  while (pos < data.length) {
    const tag = decodeVarint(data, pos)
    if (tag === null) break
    const fieldNum = tag.value >> 3
    const wireType = tag.value & 7
    pos = tag.next
    if (wireType === 0) {
      const value = decodeVarint(data, pos)
      if (value === null) break
      pos = value.next
      if (fieldNum === 1) index = value.value
      else if (fieldNum === 2) seq = value.value
      else if (fieldNum === 3) numFrags = value.value
    } else if (wireType === 2) {
      const length = decodeVarint(data, pos)
      if (length === null) break
      pos = length.next
      const bounded = boundedFieldLength(length.value, pos, data.length)
      if (fieldNum === 4) payload = data.slice(pos, pos + bounded)
      pos += bounded
    } else {
      break
    }
  }
  if (index === null || numFrags === null || payload === null) return null
  return { index, seq, numFrags, payload }
}

// --- flash page parsing -----------------------------------------------------

export interface FlashPageInfo {
  timestampMs: number | null
  didStartSession: boolean
  didStopSession: boolean
  didStartRecording: boolean
  didStopRecording: boolean
}

export const parseFlashPageInfo = (data: Uint8Array): FlashPageInfo => {
  const info: FlashPageInfo = {
    timestampMs: null,
    didStartSession: false,
    didStopSession: false,
    didStartRecording: false,
    didStopRecording: false
  }
  let pos = 0
  if (data.length > 0 && data[0] === 0x08) {
    const ts = decodeVarint(data, 1)
    if (ts !== null) {
      info.timestampMs = ts.value
      pos = ts.next
    }
  }
  let scan = pos
  while (scan < data.length) {
    if (data[scan] !== 0x1a) {
      scan += 1
      continue
    }
    const length = decodeVarint(data, scan + 1)
    if (length === null) {
      scan += 1
      continue
    }
    const chunkStart = length.next
    const chunkLength = boundedFieldLength(length.value, chunkStart, data.length)
    if (chunkLength === 0) {
      scan += 1
      continue
    }
    const chunk = data.subarray(chunkStart, chunkStart + chunkLength)
    let cpos = 0
    while (cpos < chunk.length) {
      const tagByte = chunk[cpos]
      if (tagByte !== 0x62 && tagByte !== 0x12) {
        cpos += 1
        continue
      }
      const innerLength = decodeVarint(chunk, cpos + 1)
      if (innerLength === null) {
        cpos += 1
        continue
      }
      const innerStart = innerLength.next
      const innerBounded = boundedFieldLength(innerLength.value, innerStart, chunk.length)
      const inner = chunk.subarray(innerStart, innerStart + innerBounded)
      if (tagByte === 0x62) {
        // Storage-status submessage: 0x08 = session started, 0x10 = stopped.
        for (let i = 0; i + 1 < inner.length; i += 1) {
          if (inner[i] === 0x08 && inner[i + 1] !== 0) info.didStartSession = true
          if (inner[i] === 0x10 && inner[i + 1] !== 0) info.didStopSession = true
        }
      } else {
        // Audio submessage: 0x40 = recording started, 0x48 = stopped.
        for (let i = 0; i + 1 < inner.length; i += 1) {
          if (inner[i] === 0x40 && inner[i + 1] !== 0) info.didStartRecording = true
          if (inner[i] === 0x48 && inner[i + 1] !== 0) info.didStopRecording = true
        }
      }
      cpos = innerStart + innerBounded
    }
    scan = chunkStart + chunkLength
  }
  return info
}

// --- opus extraction --------------------------------------------------------

export const extractOpusRecursive = (data: Uint8Array): Uint8Array[] => {
  const frames: Uint8Array[] = []
  let pos = 0
  while (pos < data.length) {
    const tag = decodeVarint(data, pos)
    if (tag === null) break
    const wireType = tag.value & 7
    pos = tag.next
    if (wireType === 2) {
      const length = decodeVarint(data, pos)
      if (length === null) break
      const start = length.next
      const bounded = boundedFieldLength(length.value, start, data.length)
      const field = data.subarray(start, start + bounded)
      if (
        bounded >= OPUS_FRAME_MIN_BYTES &&
        bounded <= OPUS_FRAME_MAX_BYTES &&
        VALID_OPUS_TOC_BYTES.has(field[0])
      ) {
        frames.push(field.slice())
      } else if (bounded > OPUS_FRAME_MIN_BYTES) {
        frames.push(...extractOpusRecursive(field))
      }
      pos = start + bounded
    } else if (wireType === 0) {
      const value = decodeVarint(data, pos)
      if (value === null) break
      pos = value.next
    } else if (wireType === 1) {
      pos += 8
    } else if (wireType === 5) {
      pos += 4
    } else {
      break
    }
  }
  return frames
}

export const extractOpusFramesFromFlashPage = (data: Uint8Array): Uint8Array[] => {
  let pos = 0
  if (pos < data.length && data[pos] === 0x08) {
    const v = decodeVarint(data, pos + 1)
    if (v !== null) pos = v.next
  }
  if (pos < data.length && data[pos] === 0x10) {
    const v = decodeVarint(data, pos + 1)
    if (v !== null) pos = v.next
  }
  const frames: Uint8Array[] = []
  while (pos < data.length) {
    if (data[pos] !== 0x1a) {
      pos += 1
      continue
    }
    const length = decodeVarint(data, pos + 1)
    if (length === null) {
      pos += 1
      continue
    }
    const start = length.next
    const bounded = boundedFieldLength(length.value, start, data.length)
    if (bounded === 0) {
      pos += 1
      continue
    }
    const wrapper = data.subarray(start, start + bounded)
    let wpos = 0
    while (wpos < wrapper.length) {
      const tag = decodeVarint(wrapper, wpos)
      if (tag === null) break
      const fieldNum = tag.value >> 3
      const wireType = tag.value & 7
      wpos = tag.next
      if (wireType === 0) {
        const value = decodeVarint(wrapper, wpos)
        if (value === null) break
        wpos = value.next
      } else if (wireType === 2) {
        const fieldLength = decodeVarint(wrapper, wpos)
        if (fieldLength === null) break
        const fieldStart = fieldLength.next
        const fieldBounded = boundedFieldLength(fieldLength.value, fieldStart, wrapper.length)
        if (fieldNum === 2) {
          frames.push(
            ...extractOpusRecursive(wrapper.subarray(fieldStart, fieldStart + fieldBounded))
          )
        }
        wpos = fieldStart + fieldBounded
      } else if (wireType === 1) {
        // A fixed64/fixed32 field before the audio field must be stepped over,
        // not treated as the end of the wrapper, or the frames after it are lost.
        wpos += 8
      } else if (wireType === 5) {
        wpos += 4
      } else {
        break
      }
    }
    pos = start + bounded
  }
  return frames
}

/** Raw fallback scan: 0x22 marker, varint length in the Opus window, valid
 *  TOC first byte. */
export const extractOpusFrames = (data: Uint8Array): Uint8Array[] => {
  const frames: Uint8Array[] = []
  let pos = 0
  while (pos < data.length) {
    if (data[pos] !== 0x22) {
      pos += 1
      continue
    }
    const length = decodeVarint(data, pos + 1)
    if (
      length !== null &&
      length.value >= OPUS_FRAME_MIN_BYTES &&
      length.value <= OPUS_FRAME_MAX_BYTES &&
      length.next + length.value <= data.length &&
      VALID_OPUS_TOC_BYTES.has(data[length.next])
    ) {
      frames.push(data.slice(length.next, length.next + length.value))
      pos = length.next + length.value
    } else {
      pos += 1
    }
  }
  return frames
}

// --- heuristic status scans -------------------------------------------------

/** Button events: 0 notPressed, 1 shortPress, 2 longPress, 3 doublePress. */
export const tryParseButtonStatus = (data: Uint8Array): number | null => {
  if (data.length < 10) return null
  for (let pos = 0; pos < data.length; pos += 1) {
    if (data[pos] !== 0x22) continue
    const payloadLength = decodeVarint(data, pos + 1)
    if (payloadLength === null || payloadLength.value < 2) continue
    if (payloadLength.next + payloadLength.value > data.length) continue
    if (data[payloadLength.next] !== 0x42) continue
    const buttonLength = decodeVarint(data, payloadLength.next + 1)
    if (buttonLength === null || buttonLength.value < 2 || buttonLength.value > 50) continue
    if (buttonLength.next + buttonLength.value > data.length) continue
    const button = data.subarray(buttonLength.next, buttonLength.next + buttonLength.value)
    for (let i = 0; i < button.length; i += 1) {
      if (button[i] !== 0x08) continue
      const event = decodeVarint(button, i + 1)
      if (event === null) continue
      if (event.value >= 0 && event.value <= 4) return event.value
    }
  }
  return null
}

export interface LimitlessStorageState {
  oldestFlashPage: number | null
  newestFlashPage: number | null
  currentStorageSession: number | null
  freeCapturePages: number | null
  totalCapturePages: number | null
}

export const parseStorageStateFromDeviceStatus = (
  data: Uint8Array
): LimitlessStorageState | null => {
  for (let pos = 0; pos < data.length; pos += 1) {
    if (data[pos] !== 0x2a) continue
    const length = decodeVarint(data, pos + 1)
    if (length === null || length.value > 200) continue
    const start = length.next
    const bounded = boundedFieldLength(length.value, start, data.length)
    if (bounded === 0) continue
    const inner = data.subarray(start, start + bounded)
    const state: LimitlessStorageState = {
      oldestFlashPage: null,
      newestFlashPage: null,
      currentStorageSession: null,
      freeCapturePages: null,
      totalCapturePages: null
    }
    const markers: Record<number, keyof LimitlessStorageState> = {
      0x08: 'oldestFlashPage',
      0x10: 'newestFlashPage',
      0x18: 'currentStorageSession',
      0x20: 'freeCapturePages',
      0x28: 'totalCapturePages'
    }
    let ipos = 0
    while (ipos < inner.length) {
      const field = markers[inner[ipos]]
      if (field !== undefined) {
        const value = decodeVarint(inner, ipos + 1)
        if (value !== null) {
          state[field] = value.value
          ipos = value.next
          continue
        }
      }
      ipos += 1
    }
    if (
      state.oldestFlashPage !== null ||
      state.newestFlashPage !== null ||
      state.currentStorageSession !== null ||
      state.freeCapturePages !== null ||
      state.totalCapturePages !== null
    ) {
      return state
    }
  }
  return null
}

export const tryParseDeviceStatus = (data: Uint8Array): LimitlessStorageState | null => {
  if (data.length < 20) return null
  for (let pos = 0; pos < data.length; pos += 1) {
    if (data[pos] !== 0x22) continue
    const payloadLength = decodeVarint(data, pos + 1)
    if (payloadLength === null || payloadLength.value < 10) continue
    const payloadStart = payloadLength.next
    const payloadBounded = boundedFieldLength(payloadLength.value, payloadStart, data.length)
    if (payloadBounded < 10) continue
    const payload = data.subarray(payloadStart, payloadStart + payloadBounded)
    for (let ipos = 0; ipos < payload.length; ipos += 1) {
      if (payload[ipos] !== 0x2a) continue
      const statusLength = decodeVarint(payload, ipos + 1)
      if (statusLength === null || statusLength.value < 5 || statusLength.value > 500) continue
      const statusStart = statusLength.next
      const statusBounded = boundedFieldLength(statusLength.value, statusStart, payload.length)
      if (statusBounded < 5) continue
      const state = parseStorageStateFromDeviceStatus(
        payload.subarray(statusStart, statusStart + statusBounded)
      )
      if (state !== null) return state
    }
  }
  return null
}
