import { describe, it, expect } from 'vitest'
import { PlaudDeviceConnection } from './plaudDeviceConnection'
import { makeBtDevice } from '../protocol/btDevice'
import { PLAUD_UUIDS } from '../protocol/uuids'
import { FakeTransport, ManualClock, tick } from '../testing/fakes'

const setup = async (): Promise<{
  transport: FakeTransport
  clock: ManualClock
  connection: PlaudDeviceConnection
}> => {
  const transport = new FakeTransport()
  const clock = new ManualClock()
  const connection = new PlaudDeviceConnection({
    device: makeBtDevice({ id: 'plaud-1', name: 'PLAUD NotePin', type: 'plaud' }),
    transport,
    clock
  })
  const connecting = connection.connect()
  await tick()
  clock.advance(2_000)
  await connecting
  return { transport, clock, connection }
}

const lastWrite = (transport: FakeTransport): number[] => {
  const writes = transport.writesTo(PLAUD_UUIDS.service, PLAUD_UUIDS.writeCharacteristic)
  return Array.from(writes[writes.length - 1])
}

const respond = (transport: FakeTransport, cmdId: number, payload: number[] = []): void => {
  transport.notify(PLAUD_UUIDS.service, PLAUD_UUIDS.notifyCharacteristic, [
    0x01,
    cmdId & 0xff,
    (cmdId >> 8) & 0xff,
    ...payload
  ])
}

describe('PlaudDeviceConnection', () => {
  it('battery response is [is_charging, level] — reversed relative to Bee', async () => {
    const { transport, connection } = await setup()
    const statePromise = connection.getBatteryState()
    await tick()
    expect(lastWrite(transport)).toEqual([0x01, 9, 0x00])
    respond(transport, 9, [1, 88])
    await expect(statePromise).resolves.toEqual({ level: 88, isCharging: true })
  })

  it('runs the recording session command sequence on the first audio subscriber', async () => {
    const { transport, clock, connection } = await setup()
    const chunks: Uint8Array[] = []
    connection.getAudioStream({ onValue: (c) => chunks.push(c), onFinish: () => undefined })
    await tick()

    // stopRecord(0) for a clean slate.
    expect(lastWrite(transport)).toEqual([0x01, 23, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    respond(transport, 23)
    await tick()
    clock.advance(500)
    await tick()

    // startRecord: 12-byte payload starting with LE 1.
    expect(lastWrite(transport)).toEqual([0x01, 20, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    respond(transport, 20, [7, 0, 0, 0, 100, 0, 0, 0, 0, 0])
    await tick()
    clock.advance(1_000)
    await tick()

    // startSync: sessionId(8 LE) + start(8 LE) + end sentinel 0x7FFFFFFF.
    expect(lastWrite(transport)).toEqual([
      0x01, 28, 0, 7, 0, 0, 0, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xff, 0xff, 0x7f, 0, 0,
      0, 0
    ])
    respond(transport, 28)
    await tick()

    // Audio: type-2 packets rechunked into exact 80-byte output.
    const opus = new Array(80).fill(0x42)
    transport.notify(PLAUD_UUIDS.service, PLAUD_UUIDS.notifyCharacteristic, [
      0x02,
      9,
      9,
      9,
      9, // session id (unused)
      1,
      0,
      0,
      0, // position
      80, // length
      ...opus
    ])
    expect(chunks.length).toBe(1)
    expect(chunks[0].length).toBe(80)
  })

  it('drops the end-of-stream marker and truncated audio packets', async () => {
    const { transport, connection } = await setup()
    const chunks: Uint8Array[] = []
    connection.getAudioStream({ onValue: (c) => chunks.push(c), onFinish: () => undefined })
    await tick()
    respond(transport, 23)
    await tick()

    transport.notify(
      PLAUD_UUIDS.service,
      PLAUD_UUIDS.notifyCharacteristic,
      [0x02, 0, 0, 0, 0, 0xff, 0xff, 0xff, 0xff, 10, 1, 2]
    )
    transport.notify(
      PLAUD_UUIDS.service,
      PLAUD_UUIDS.notifyCharacteristic,
      [0x02, 0, 0, 0, 0, 1, 0, 0, 0, 50, 1, 2, 3]
    )
    expect(chunks.length).toBe(0)
  })

  it('stopSync writes the raw uncorrelated frame', async () => {
    const { transport, clock, connection } = await setup()
    const subscription = connection.getAudioStream({
      onValue: () => undefined,
      onFinish: () => undefined
    })
    await tick()
    respond(transport, 23)
    await tick()
    clock.advance(500)
    await tick()
    respond(transport, 20, [7, 0, 0, 0, 100, 0, 0, 0, 0, 0])
    await tick()
    clock.advance(1_000)
    await tick()
    respond(transport, 28)
    await tick()

    const writesBeforeStop = transport.writesTo(
      PLAUD_UUIDS.service,
      PLAUD_UUIDS.writeCharacteristic
    ).length
    subscription.cancel()
    await tick()
    // Teardown order is stopSync (raw, uncorrelated) then stopRecord.
    const teardownWrites = transport
      .writesTo(PLAUD_UUIDS.service, PLAUD_UUIDS.writeCharacteristic)
      .slice(writesBeforeStop)
      .map((w) => Array.from(w))
    expect(teardownWrites[0]).toEqual([0x01, 0x1e, 0x00, 0x01])
    expect(teardownWrites[1]).toEqual([0x01, 23, 0, 7, 0, 0, 0, 0, 0, 0, 0])
    respond(transport, 23)
    await tick()
  })
})
