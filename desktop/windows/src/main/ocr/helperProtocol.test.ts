import { describe, it, expect } from 'vitest'
import { encodeRequest, FrameDecoder, OP_OCR, OP_WINDOW } from './helperProtocol'

describe('encodeRequest', () => {
  it('prefixes length and opcode for an OCR request', () => {
    const frame = encodeRequest(OP_OCR, Buffer.from([1, 2, 3]))
    // 4-byte LE length (1 opcode + 3 payload = 4), then opcode, then payload.
    expect(frame.readUInt32LE(0)).toBe(4)
    expect(frame[4]).toBe(OP_OCR)
    expect([...frame.subarray(5)]).toEqual([1, 2, 3])
  })

  it('encodes an empty-payload window request', () => {
    const frame = encodeRequest(OP_WINDOW, Buffer.alloc(0))
    expect(frame.readUInt32LE(0)).toBe(1)
    expect(frame[4]).toBe(OP_WINDOW)
    expect(frame.length).toBe(5)
  })
})

describe('FrameDecoder', () => {
  it('reassembles a response split across chunks', () => {
    const json = JSON.stringify({ ok: true })
    const body = Buffer.from(json, 'utf8')
    const header = Buffer.alloc(4)
    header.writeUInt32LE(body.length, 0)
    const full = Buffer.concat([header, body])

    const seen: string[] = []
    const dec = new FrameDecoder((s) => seen.push(s))
    dec.push(full.subarray(0, 2))
    dec.push(full.subarray(2, 6))
    dec.push(full.subarray(6))
    expect(seen).toEqual([json])
  })

  it('handles two frames in one chunk', () => {
    const mk = (o: object): Buffer => {
      const b = Buffer.from(JSON.stringify(o))
      const h = Buffer.alloc(4)
      h.writeUInt32LE(b.length, 0)
      return Buffer.concat([h, b])
    }
    const seen: string[] = []
    const dec = new FrameDecoder((s) => seen.push(s))
    dec.push(Buffer.concat([mk({ a: 1 }), mk({ b: 2 })]))
    expect(seen).toEqual(['{"a":1}', '{"b":2}'])
  })
})
