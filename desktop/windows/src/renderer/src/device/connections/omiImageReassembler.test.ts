import { describe, it, expect } from 'vitest'
import { OmiImageReassembler, compareFirmwareVersions } from './omiImageReassembler'

const chunk = (frameIndex: number, ...payload: number[]): Uint8Array =>
  Uint8Array.from([frameIndex & 0xff, (frameIndex >> 8) & 0xff, ...payload])

const END = 0xffff

describe('compareFirmwareVersions', () => {
  it('compares numerically with missing parts as zero', () => {
    expect(compareFirmwareVersions('2.1.1', '2.1.1')).toBe(0)
    expect(compareFirmwareVersions('2.1.0', '2.1.1')).toBe(-1)
    expect(compareFirmwareVersions('2.10.0', '2.9.9')).toBe(1)
    expect(compareFirmwareVersions('2.1', '2.1.0')).toBe(0)
    expect(compareFirmwareVersions('1.0.2', '2.1.1')).toBe(-1)
  })
})

describe('OmiImageReassembler', () => {
  it('assembles an in-order image on new firmware with the orientation byte', () => {
    const r = new OmiImageReassembler(() => '2.1.1')
    expect(r.push(chunk(0, 1, 10, 11))).toBeNull() // orientation byte 1 = 90 degrees
    expect(r.push(chunk(1, 12, 13))).toBeNull()
    const image = r.push(chunk(END))
    expect(image).not.toBeNull()
    expect(image!.orientationDegrees).toBe(90)
    expect(Array.from(image!.imageData)).toEqual([10, 11, 12, 13])
  })

  it('older firmware forces 180 degrees and keeps byte 2 as image data', () => {
    const r = new OmiImageReassembler(() => '1.0.2')
    r.push(chunk(0, 10, 11))
    const image = r.push(chunk(END))
    expect(image!.orientationDegrees).toBe(180)
    expect(Array.from(image!.imageData)).toEqual([10, 11])
  })

  it('discards the whole image on an out-of-order frame', () => {
    const r = new OmiImageReassembler(() => '2.1.1')
    r.push(chunk(0, 0, 1))
    r.push(chunk(2, 9)) // expected 1
    expect(r.push(chunk(END))).toBeNull()
  })

  it('frames while not transferring are ignored; end without data yields nothing', () => {
    const r = new OmiImageReassembler(() => '2.1.1')
    expect(r.push(chunk(3, 1, 2))).toBeNull()
    expect(r.push(chunk(END))).toBeNull()
  })

  it('a fresh frame 0 restarts an in-progress image', () => {
    const r = new OmiImageReassembler(() => '2.1.1')
    r.push(chunk(0, 0, 99))
    r.push(chunk(0, 2, 42)) // restart with orientation byte 2 = 180
    const image = r.push(chunk(END))
    expect(image!.orientationDegrees).toBe(180)
    expect(Array.from(image!.imageData)).toEqual([42])
  })

  it('chunks under 2 bytes are skipped', () => {
    const r = new OmiImageReassembler(() => '2.1.1')
    expect(r.push(Uint8Array.from([0]))).toBeNull()
    r.push(chunk(0, 0, 7))
    const image = r.push(chunk(END))
    expect(Array.from(image!.imageData)).toEqual([7])
  })

  it('resets when the buffer exceeds the 200 KiB cap', () => {
    const r = new OmiImageReassembler(() => '2.1.1')
    const big = new Array(60 * 1024).fill(1)
    r.push(chunk(0, 0, ...big))
    r.push(chunk(1, ...big))
    r.push(chunk(2, ...big))
    r.push(chunk(3, ...big)) // crosses 200 KiB -> reset
    expect(r.push(chunk(END))).toBeNull()
  })
})
