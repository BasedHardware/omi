import { describe, it, expect } from 'vitest'
import { OmiDeviceConnection } from './omiDeviceConnection'
import { makeBtDevice } from '../protocol/btDevice'
import { DEVICE_INFO_UUIDS, OMI_UUIDS, STORAGE_UUIDS } from '../protocol/uuids'
import { FakeTransport, ManualClock, characteristicKey as k, tick } from '../testing/fakes'
import type { OrientedImage } from './deviceConnection'

const text = (value: string): Uint8Array => new TextEncoder().encode(value)

const setup = (): {
  transport: FakeTransport
  clock: ManualClock
  connection: OmiDeviceConnection
} => {
  const transport = new FakeTransport()
  const clock = new ManualClock()
  const connection = new OmiDeviceConnection({
    device: makeBtDevice({ id: 'dev', name: 'omi', type: 'omi' }),
    transport,
    clock
  })
  return { transport, clock, connection }
}

describe('OmiDeviceConnection', () => {
  it('promotes to OpenGlass when the image characteristic is readable', async () => {
    const { transport, connection } = setup()
    transport.reads.set(
      k(OMI_UUIDS.mainService, OMI_UUIDS.imageDataStream),
      Uint8Array.from([0x00])
    )
    await connection.connect()
    expect(connection.device.type).toBe('openglass')
  })

  it('stays omi without a readable image characteristic', async () => {
    const { connection } = setup()
    await connection.connect()
    expect(connection.device.type).toBe('omi')
  })

  it('camera commands write the verbatim control bytes', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    await connection.startPhotoCapture()
    await connection.stopPhotoCapture()
    await connection.takePhoto()
    const written = transport.writesTo(OMI_UUIDS.mainService, OMI_UUIDS.imageCaptureControl)
    expect(written.map((w) => Array.from(w))).toEqual([[0x05], [0x00], [0xff]])
  })

  it('settings clamp to 0-100 and read back single bytes', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    await connection.setLedDimRatio(150)
    await connection.setMicGain(-5)
    const dim = transport.writesTo(OMI_UUIDS.settingsService, OMI_UUIDS.settingsDimRatio)
    const gain = transport.writesTo(OMI_UUIDS.settingsService, OMI_UUIDS.settingsMicGain)
    expect(Array.from(dim[0])).toEqual([100])
    expect(Array.from(gain[0])).toEqual([0])
    transport.reads.set(
      k(OMI_UUIDS.settingsService, OMI_UUIDS.settingsMicGain),
      Uint8Array.from([55])
    )
    expect(await connection.getMicGain()).toBe(55)
  })

  it('reassembles image chunks with new-firmware orientation', async () => {
    const { transport, connection } = setup()
    transport.reads.set(k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.modelNumber), text('omi'))
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.firmwareRevision),
      text('2.1.1')
    )
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.hardwareRevision),
      text('hw')
    )
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.manufacturerName),
      text('mfr')
    )
    await connection.connect()
    const images: OrientedImage[] = []
    connection.getImageStream({ onValue: (image) => images.push(image), onFinish: () => undefined })
    transport.notify(OMI_UUIDS.mainService, OMI_UUIDS.imageDataStream, [0, 0, 1, 10, 11])
    transport.notify(OMI_UUIDS.mainService, OMI_UUIDS.imageDataStream, [1, 0, 12])
    transport.notify(OMI_UUIDS.mainService, OMI_UUIDS.imageDataStream, [0xff, 0xff])
    expect(images.length).toBe(1)
    expect(images[0].orientationDegrees).toBe(90)
    expect(Array.from(images[0].imageData)).toEqual([10, 11, 12])
  })

  it('wifi setup subscribes before writing and maps the response code', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    const resultPromise = connection.setupWifiSync('home', 'password1')
    expect(transport.subscriberCount(STORAGE_UUIDS.service, STORAGE_UUIDS.wifi)).toBe(1)
    const written = transport.writesTo(STORAGE_UUIDS.service, STORAGE_UUIDS.wifi)
    expect(written.length).toBe(1)
    const ssid = new TextEncoder().encode('home')
    const password = new TextEncoder().encode('password1')
    expect(Array.from(written[0])).toEqual([
      0x01,
      ssid.length,
      ...ssid,
      password.length,
      ...password
    ])
    await tick()
    transport.notify(STORAGE_UUIDS.service, STORAGE_UUIDS.wifi, [0x05])
    await expect(resultPromise).resolves.toEqual({ code: 'sessionAlreadyRunning' })
  })

  it('wifi setup times out on the injected clock', async () => {
    const { transport, clock, connection } = setup()
    await connection.connect()
    const resultPromise = connection.setupWifiSync('home', 'password1')
    resultPromise.catch(() => undefined)
    await tick()
    clock.advance(5_000)
    await expect(resultPromise).rejects.toMatchObject({
      message: 'WiFi setup response timed out'
    })
    expect(transport.subscriberCount(STORAGE_UUIDS.service, STORAGE_UUIDS.wifi)).toBe(0)
  })

  it('wifi start and stop write the control bytes', async () => {
    const { transport, connection } = setup()
    await connection.connect()
    await connection.startWifiSync()
    await connection.stopWifiSync()
    const written = transport.writesTo(STORAGE_UUIDS.service, STORAGE_UUIDS.wifi)
    expect(written.map((w) => Array.from(w))).toEqual([[0x02], [0x03]])
  })
})
