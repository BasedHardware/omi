import { describe, it, expect } from 'vitest'
import { LimitlessDeviceConnection } from './limitlessDeviceConnection'
import { makeBtDevice } from '../protocol/btDevice'
import { LIMITLESS_UUIDS } from '../protocol/uuids'
import { FakeTransport, ManualClock, tick } from '../testing/fakes'
import {
  encodeBytesField,
  encodeVarint,
  encodeVarintField,
  parseBlePacket
} from './limitlessProtocol'

const opusFrame = (toc = 0xb8, fill = 7): Uint8Array =>
  Uint8Array.from([toc, ...new Array(11).fill(fill)])

/** Wraps a payload the way the pendant frames outbound BLE packets. */
const pendantPacket = (
  index: number,
  seq: number,
  numFrags: number,
  payload: Uint8Array
): number[] =>
  Array.from(
    Uint8Array.from([
      ...encodeVarintField(1, index),
      ...encodeVarintField(2, seq),
      ...encodeVarintField(3, numFrags),
      ...encodeBytesField(4, payload)
    ])
  )

const setup = async (): Promise<{
  transport: FakeTransport
  clock: ManualClock
  connection: LimitlessDeviceConnection
}> => {
  const transport = new FakeTransport()
  const clock = new ManualClock()
  const connection = new LimitlessDeviceConnection({
    device: makeBtDevice({ id: 'limitless-1', name: 'Pendant', type: 'limitless' }),
    transport,
    clock
  })
  const connecting = connection.connect()
  await tick()
  // Post-connect settle, RX subscribe gap, then the two initialize gaps.
  for (let i = 0; i < 4; i += 1) {
    clock.advance(1_000)
    await tick()
  }
  await connecting
  return { transport, clock, connection }
}

const txWrites = (transport: FakeTransport): Uint8Array[] =>
  transport.writesTo(LIMITLESS_UUIDS.service, LIMITLESS_UUIDS.txCharacteristic)

describe('LimitlessDeviceConnection', () => {
  it('hardcodes device info and runs the initialize handshake', async () => {
    const { transport, connection } = await setup()
    expect(connection.device.modelNumber).toBe('Limitless Pendant')
    expect(connection.device.manufacturerName).toBe('Limitless')
    expect(
      transport.subscriberCount(LIMITLESS_UUIDS.service, LIMITLESS_UUIDS.rxCharacteristic)
    ).toBe(1)
    const writes = txWrites(transport)
    expect(writes.length).toBe(2)
    // Both commands parse as single-fragment BLE packets with rising indexes.
    const first = parseBlePacket(writes[0])!
    const second = parseBlePacket(writes[1])!
    expect(first.index).toBe(0)
    expect(second.index).toBe(1)
    expect(first.numFrags).toBe(1)
    // Message numbers: 6 = time sync, 8 = enable data stream.
    expect(first.payload[0]).toBe((6 << 3) | 2)
    expect(second.payload[0]).toBe((8 << 3) | 2)
  })

  it('reassembles multi-fragment real-time packets into Opus frames', async () => {
    const { transport, connection } = await setup()
    const frames: Uint8Array[] = []
    connection.getAudioStream({ onValue: (f) => frames.push(f), onFinish: () => undefined })

    const frame = opusFrame()
    // Raw 0x22-marker payload split across two fragments of one index.
    const payload = Uint8Array.from([0x22, frame.length, ...frame])
    const half = Math.floor(payload.length / 2)
    transport.notify(
      LIMITLESS_UUIDS.service,
      LIMITLESS_UUIDS.rxCharacteristic,
      pendantPacket(0, 0, 2, payload.subarray(0, half))
    )
    expect(frames.length).toBe(0)
    transport.notify(
      LIMITLESS_UUIDS.service,
      LIMITLESS_UUIDS.rxCharacteristic,
      pendantPacket(0, 1, 2, payload.subarray(half))
    )
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })

  it('emits only double-press button events, as 4 little-endian bytes', async () => {
    const { transport, connection } = await setup()
    const events: number[][] = []
    connection.getButtonStream({
      onValue: (e) => events.push(Array.from(e)),
      onFinish: () => undefined
    })

    const buttonFrame = (eventValue: number): number[] => {
      const button = Uint8Array.from([0x08, ...encodeVarint(eventValue)])
      const payload = Uint8Array.from([0x42, button.length, ...button])
      return [0x00, 0x00, 0x22, payload.length, ...payload, 0, 0, 0]
    }

    transport.notify(LIMITLESS_UUIDS.service, LIMITLESS_UUIDS.rxCharacteristic, buttonFrame(1))
    transport.notify(LIMITLESS_UUIDS.service, LIMITLESS_UUIDS.rxCharacteristic, buttonFrame(2))
    expect(events.length).toBe(0)
    transport.notify(LIMITLESS_UUIDS.service, LIMITLESS_UUIDS.rxCharacteristic, buttonFrame(3))
    expect(events).toEqual([[0x02, 0x00, 0x00, 0x00]])
  })

  it('drops the oldest incomplete fragment index instead of growing forever', async () => {
    const { transport, connection } = await setup()
    const frames: Uint8Array[] = []
    connection.getAudioStream({ onValue: (f) => frames.push(f), onFinish: () => undefined })

    // 200 indexes that each announce two fragments and deliver one: without a
    // bound every one of them would be retained for the whole session.
    for (let index = 0; index < 200; index += 1) {
      transport.notify(
        LIMITLESS_UUIDS.service,
        LIMITLESS_UUIDS.rxCharacteristic,
        pendantPacket(index, 0, 2, Uint8Array.from([0x22, 2, 1, 2]))
      )
    }
    expect(frames.length).toBe(0)

    // A fresh index still reassembles normally after the eviction.
    const frame = opusFrame()
    const payload = Uint8Array.from([0x22, frame.length, ...frame])
    transport.notify(
      LIMITLESS_UUIDS.service,
      LIMITLESS_UUIDS.rxCharacteristic,
      pendantPacket(500, 0, 1, payload)
    )
    expect(frames.length).toBe(1)
  })

  it('led brightness clamps and reads back the last written value', async () => {
    const { connection } = await setup()
    expect(await connection.getLedDimRatio()).toBeNull()
    expect(await connection.setLedDimRatio(180)).toBe(true)
    expect(await connection.getLedDimRatio()).toBe(100)
    expect(await connection.getFeatures()).toEqual(['ledDimming'])
  })

  it('unpair sends the unpair command before teardown', async () => {
    const { transport, connection } = await setup()
    const before = txWrites(transport).length
    await connection.unpair()
    const writes = txWrites(transport)
    expect(writes.length).toBe(before + 1)
    const packet = parseBlePacket(writes[writes.length - 1])!
    expect(packet.payload[0]).toBe((15 << 3) | 2)
    expect(transport.disposed).toBe(true)
  })
})
