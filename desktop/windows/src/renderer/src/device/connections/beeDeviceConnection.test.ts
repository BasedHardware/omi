import { describe, it, expect } from 'vitest'
import { BeeDeviceConnection } from './beeDeviceConnection'
import { makeBtDevice } from '../protocol/btDevice'
import { BEE_UUIDS } from '../protocol/uuids'
import { FakeTransport, ManualClock, tick } from '../testing/fakes'

const adtsFrame = (length: number, fill: number): Uint8Array => {
  const frame = new Uint8Array(length)
  frame[0] = 0xff
  frame[1] = 0xf1
  frame[3] = (length >> 11) & 0x03
  frame[4] = (length >> 3) & 0xff
  frame[5] = (length & 0x07) << 5
  frame.fill(fill, 6)
  return frame
}

const setup = async (): Promise<{
  transport: FakeTransport
  clock: ManualClock
  connection: BeeDeviceConnection
}> => {
  const transport = new FakeTransport()
  const clock = new ManualClock()
  const connection = new BeeDeviceConnection({
    device: makeBtDevice({ id: 'bee-1', name: 'Bee', type: 'bee' }),
    transport,
    clock
  })
  const connecting = connection.connect()
  await tick()
  clock.advance(1_000)
  await connecting
  return { transport, clock, connection }
}

describe('BeeDeviceConnection', () => {
  it('hardcodes device info and subscribes control and audio after the settle', async () => {
    const { transport, connection } = await setup()
    expect(connection.device.modelNumber).toBe('Bee')
    expect(connection.device.manufacturerName).toBe('Bee')
    expect(transport.subscriberCount(BEE_UUIDS.service, BEE_UUIDS.control)).toBe(1)
    expect(transport.subscriberCount(BEE_UUIDS.service, BEE_UUIDS.audio)).toBe(1)
  })

  it('battery command correlates a direct response as [level, charging]', async () => {
    const { transport, connection } = await setup()
    const statePromise = connection.getBatteryState()
    await tick()
    const written = transport.writesTo(BEE_UUIDS.service, BEE_UUIDS.control)
    expect(Array.from(written[0])).toEqual([0x0f, 0xc0])
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.control, [0x0f, 0xc0, 77, 1])
    await expect(statePromise).resolves.toEqual({ level: 77, isCharging: true })
  })

  it('unwraps 0x8000 echo frames to the echoed command id', async () => {
    const { transport, connection } = await setup()
    const statePromise = connection.getBatteryState()
    await tick()
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.control, [0x00, 0x80, 0x0f, 0xc0, 66, 0])
    await expect(statePromise).resolves.toEqual({ level: 66, isCharging: false })
  })

  it('a command timeout resolves null and poisons the id for the next send', async () => {
    const { clock, connection } = await setup()
    const first = connection.getBatteryState()
    await tick()
    clock.advance(5_000)
    await expect(first).resolves.toBeNull()
    // The poisoned identity turns the next battery query into null too
    // (getBatteryState swallows the identity error).
    await expect(connection.getBatteryState()).resolves.toBeNull()
  })

  it('first audio subscriber unmutes; frames drain through ADTS; last subscriber mutes', async () => {
    const { transport, connection } = await setup()
    const frames: Uint8Array[] = []
    const subscription = connection.getAudioStream({
      onValue: (frame) => frames.push(frame),
      onFinish: () => undefined
    })
    await tick()
    let control = transport.writesTo(BEE_UUIDS.service, BEE_UUIDS.control)
    expect(Array.from(control[0])).toEqual([0x06, 0xc0, 0x01])
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.control, [0x06, 0xc0])
    await tick()

    const adts = adtsFrame(14, 0x2a)
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.audio, [0x00, 0x00, ...adts])
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(adts)

    subscription.cancel()
    await tick()
    control = transport.writesTo(BEE_UUIDS.service, BEE_UUIDS.control)
    expect(Array.from(control[control.length - 1])).toEqual([0x06, 0xc0, 0x00])
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.control, [0x06, 0xc0])
    await tick()
  })

  it('audio packets shorter than the 2-byte header are ignored', async () => {
    const { transport, connection } = await setup()
    const frames: Uint8Array[] = []
    connection.getAudioStream({ onValue: (f) => frames.push(f), onFinish: () => undefined })
    await tick()
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.control, [0x06, 0xc0])
    await tick()
    transport.notify(BEE_UUIDS.service, BEE_UUIDS.audio, [0x01])
    expect(frames.length).toBe(0)
  })
})
