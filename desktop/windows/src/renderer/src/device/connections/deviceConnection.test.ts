import { describe, it, expect, vi } from 'vitest'
import { BaseDeviceConnection, DeviceConnectionError } from './deviceConnection'
import { makeBtDevice } from '../protocol/btDevice'
import {
  ACCELEROMETER_UUIDS,
  BATTERY_UUIDS,
  DEVICE_INFO_UUIDS,
  OMI_UUIDS,
  STORAGE_UUIDS
} from '../protocol/uuids'
import { FakeTransport, ManualClock, characteristicKey as k, tick } from '../testing/fakes'

const text = (value: string): Uint8Array => new TextEncoder().encode(value)

const setup = (): { transport: FakeTransport; connection: BaseDeviceConnection } => {
  const transport = new FakeTransport()
  const connection = new BaseDeviceConnection({
    device: makeBtDevice({ id: 'dev', name: 'omi', type: 'omi' }),
    transport,
    clock: new ManualClock()
  })
  return { transport, connection }
}

describe('BaseDeviceConnection lifecycle', () => {
  it('connects once, reads device info, and rejects a second connect', async () => {
    const { transport, connection } = setup()
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.modelNumber),
      text('omi CV1')
    )
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.firmwareRevision),
      text('2.1.1')
    )
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.hardwareRevision),
      text('Seeed')
    )
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.manufacturerName),
      text('Based Hardware')
    )
    await connection.connect()
    expect(connection.device.modelNumber).toBe('omi CV1')
    expect(connection.device.firmwareRevision).toBe('2.1.1')
    expect(connection.lastPongAt).not.toBeNull()
    await expect(connection.connect()).rejects.toMatchObject({ kind: 'alreadyConnected' })
  })

  it('a failing device-info read aborts the remaining reads silently', async () => {
    const { transport, connection } = setup()
    transport.reads.set(k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.modelNumber), text('omi'))
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.firmwareRevision),
      new Error('read failed')
    )
    await connection.connect()
    expect(connection.device.modelNumber).toBe('omi')
    const hardwareKey = k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.hardwareRevision)
    expect(transport.readLog).not.toContain(hardwareKey)
  })

  it('an unexpected transport drop after ready notifies the delegate and disposes', async () => {
    const { transport, connection } = setup()
    const delegate = { didDisconnectUnexpectedly: vi.fn(), didDetectFall: vi.fn() }
    connection.delegate = delegate
    await connection.connect()
    transport.fireUnexpectedDisconnect()
    await tick()
    expect(delegate.didDisconnectUnexpectedly).toHaveBeenCalledTimes(1)
    expect(transport.disposed).toBe(true)
  })

  it('a setup-phase failure surfaces as a connect error, not an unexpected disconnect', async () => {
    class FailingPrepare extends BaseDeviceConnection {
      protected override async prepareDeviceAfterConnect(): Promise<void> {
        throw new Error('prepare exploded')
      }
    }
    const transport = new FakeTransport()
    const delegate = { didDisconnectUnexpectedly: vi.fn(), didDetectFall: vi.fn() }
    const connection = new FailingPrepare({
      device: makeBtDevice({ id: 'dev', name: 'omi', type: 'omi' }),
      transport,
      clock: new ManualClock()
    })
    connection.delegate = delegate
    await expect(connection.connect()).rejects.toMatchObject({
      kind: 'connectionFailed',
      message: 'prepare exploded'
    })
    expect(delegate.didDisconnectUnexpectedly).not.toHaveBeenCalled()
    expect(transport.disposed).toBe(true)
  })

  it('disconnect tears down exactly once and joins concurrent calls', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    await Promise.all([connection.disconnect(), connection.disconnect()])
    expect(transport.disposed).toBe(true)
  })
})

describe('BaseDeviceConnection GATT defaults', () => {
  it('battery level reads the first byte with -1 fallback', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    transport.reads.set(k(BATTERY_UUIDS.service, BATTERY_UUIDS.level), Uint8Array.from([73]))
    expect(await connection.getBatteryLevel()).toBe(73)
    transport.reads.set(k(BATTERY_UUIDS.service, BATTERY_UUIDS.level), new Error('nope'))
    expect(await connection.getBatteryLevel()).toBe(-1)
  })

  it('audio codec maps the characteristic byte with pcm8 fallback', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    transport.reads.set(k(OMI_UUIDS.mainService, OMI_UUIDS.audioCodec), Uint8Array.from([21]))
    expect(await connection.getAudioCodec()).toBe('opusFS320')
    transport.reads.delete(k(OMI_UUIDS.mainService, OMI_UUIDS.audioCodec))
    expect(await connection.getAudioCodec()).toBe('pcm8')
  })

  it('features decode the little-endian bitmask and cache on success only', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    const featuresKey = k(OMI_UUIDS.featuresService, OMI_UUIDS.featuresCharacteristic)
    transport.reads.set(featuresKey, Uint8Array.from([0x49, 0x02, 0x00, 0x00]))
    expect(await connection.getFeatures()).toEqual(['speaker', 'battery', 'offlineStorage', 'wifi'])
    const readsBefore = transport.readLog.length
    transport.reads.set(featuresKey, new Error('gone'))
    expect(await connection.getFeatures()).toEqual(['speaker', 'battery', 'offlineStorage', 'wifi'])
    expect(transport.readLog.length).toBe(readsBefore)
  })

  it('storage list parses little-endian int32 lengths; storage writes use big-endian offsets', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    transport.reads.set(
      k(STORAGE_UUIDS.service, STORAGE_UUIDS.readControl),
      Uint8Array.from([0x10, 0, 0, 0, 0x00, 0x01, 0, 0])
    )
    expect(await connection.getStorageList()).toEqual([16, 256])

    await connection.writeToStorage(2, 3, 0x01020304)
    const written = transport.writesTo(STORAGE_UUIDS.service, STORAGE_UUIDS.dataStream)
    expect(Array.from(written[0])).toEqual([3, 2, 1, 2, 3, 4])
  })

  it('accelerometer packets decode six signed LE int16s and detect falls', async () => {
    const { transport, connection } = setup()
    const delegate = { didDisconnectUnexpectedly: vi.fn(), didDetectFall: vi.fn() }
    connection.delegate = delegate
    await connection.connect()
    const samples: number[][] = []
    connection.getAccelerometerStream({
      onValue: (s) => samples.push([s.accelX, s.accelY, s.gyroZ]),
      onFinish: () => undefined
    })
    transport.notify(
      ACCELEROMETER_UUIDS.service,
      ACCELEROMETER_UUIDS.dataStream,
      [0x9c, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0]
    )
    expect(samples).toEqual([[-100, 0, 5]])
    expect(delegate.didDetectFall).toHaveBeenCalledTimes(1)

    transport.notify(ACCELEROMETER_UUIDS.service, ACCELEROMETER_UUIDS.dataStream, [7])
    expect(samples[1]).toEqual([7, 0, 0])
    expect(delegate.didDetectFall).toHaveBeenCalledTimes(1)
  })

  it('wifi defaults validate credentials then report missing hardware', async () => {
    const { connection } = setup()
    await connection.connect()
    expect(await connection.isWifiSyncSupported()).toBe(false)
    expect((await connection.setupWifiSync('', 'password1')).code).toBe('ssidLengthInvalid')
    expect((await connection.setupWifiSync('home', 'password1')).code).toBe(
      'wifiHardwareNotAvailable'
    )
  })
})

describe('DeviceConnectionError', () => {
  it('carries the mac-verbatim messages', () => {
    expect(DeviceConnectionError.alreadyConnected().message).toBe(
      'This connection session has already started'
    )
    expect(DeviceConnectionError.notConnected().message).toBe('Device is not connected')
  })
})
