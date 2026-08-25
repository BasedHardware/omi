/**
 * Friend Pendant, Fieldy, and Frame: the families whose whole client is a
 * decode rule plus a set of deliberate no-ops.
 */

import { describe, it, expect } from 'vitest'
import { FriendPendantConnection } from './friendPendantConnection'
import { FieldyDeviceConnection } from './fieldyDeviceConnection'
import { FrameDeviceConnection } from './frameDeviceConnection'
import { createDeviceConnection } from './deviceConnectionFactory'
import { makeBtDevice } from '../protocol/btDevice'
import {
  BATTERY_UUIDS,
  DEVICE_INFO_UUIDS,
  FIELDY_UUIDS,
  FRIEND_PENDANT_UUIDS
} from '../protocol/uuids'
import { FakeTransport, ManualClock, characteristicKey as k, tick } from '../testing/fakes'
import { OmiDeviceConnection } from './omiDeviceConnection'
import { BeeDeviceConnection } from './beeDeviceConnection'
import { PlaudDeviceConnection } from './plaudDeviceConnection'
import { LimitlessDeviceConnection } from './limitlessDeviceConnection'

const text = (value: string): Uint8Array => new TextEncoder().encode(value)

describe('FriendPendantConnection', () => {
  const setup = async (): Promise<{
    transport: FakeTransport
    clock: ManualClock
    connection: FriendPendantConnection
  }> => {
    const transport = new FakeTransport()
    const clock = new ManualClock()
    const connection = new FriendPendantConnection({
      device: makeBtDevice({ id: 'friend-1', name: 'friend_ab', type: 'friendPendant' }),
      transport,
      clock
    })
    const connecting = connection.connect()
    await tick()
    clock.advance(1_000)
    await connecting
    return { transport, clock, connection }
  }

  it('strips the 5-byte footer and emits only exact 30-byte LC3 frames', async () => {
    const { transport, connection } = await setup()
    const frames: Uint8Array[] = []
    connection.getAudioStream({ onValue: (f) => frames.push(f), onFinish: () => undefined })

    // 95 bytes = 3 x 30-byte frames + 5-byte footer. Every payload byte is
    // its own index, so a frame sliced from the wrong offset (for example a
    // footer stripped from the head) fails on content, not just on length.
    const packet = new Uint8Array(95)
    for (let i = 0; i < 90; i += 1) packet[i] = i
    packet.fill(0xff, 90)
    transport.notify(FRIEND_PENDANT_UUIDS.service, FRIEND_PENDANT_UUIDS.audioCharacteristic, packet)
    expect(frames.length).toBe(3)
    expect(frames.every((f) => f.length === 30)).toBe(true)
    expect(frames[0][0]).toBe(0)
    expect(frames[2][0]).toBe(60)
    expect(frames[2][29]).toBe(89)
    // The 0xff footer never reaches a frame.
    expect(frames.some((f) => f.includes(0xff))).toBe(false)

    // A short tail after the footer strip is dropped, not padded.
    const partial = new Uint8Array(45)
    transport.notify(
      FRIEND_PENDANT_UUIDS.service,
      FRIEND_PENDANT_UUIDS.audioCharacteristic,
      partial
    )
    expect(frames.length).toBe(4)

    // Packets at or under the footer size yield nothing.
    transport.notify(FRIEND_PENDANT_UUIDS.service, FRIEND_PENDANT_UUIDS.audioCharacteristic, [1, 2])
    expect(frames.length).toBe(4)
  })

  it('reports the fixed codec, hardcoded info, and a faked 90% battery on an interval', async () => {
    const { clock, connection } = await setup()
    expect(await connection.getAudioCodec()).toBe('lc3FS1030')
    expect(connection.device.modelNumber).toBe('Friend Pendant')
    expect(await connection.getBatteryLevel()).toBe(90)

    const levels: number[] = []
    const subscription = connection.getBatteryLevelStream({
      onValue: (level) => levels.push(level),
      onFinish: () => undefined
    })
    expect(levels).toEqual([90])
    clock.advance(30_000)
    await tick()
    expect(levels).toEqual([90, 90])
    subscription.cancel()
    clock.advance(30_000)
    await tick()
    expect(levels.length).toBe(2)
  })
})

describe('FieldyDeviceConnection', () => {
  const setup = async (): Promise<{
    transport: FakeTransport
    connection: FieldyDeviceConnection
  }> => {
    const transport = new FakeTransport()
    const clock = new ManualClock()
    const connection = new FieldyDeviceConnection({
      device: makeBtDevice({ id: 'fieldy-1', name: 'compass', type: 'fieldy' }),
      transport,
      clock
    })
    const connecting = connection.connect()
    await tick()
    clock.advance(1_000)
    await connecting
    return { transport, connection }
  }

  it('splits notifications into 40-byte frames and keeps a valid-TOC tail', async () => {
    const { transport, connection } = await setup()
    const frames: Uint8Array[] = []
    connection.getAudioStream({ onValue: (f) => frames.push(f), onFinish: () => undefined })

    const packet = new Uint8Array(80)
    packet[0] = 0xb8
    packet[40] = 0xb8
    transport.notify(FIELDY_UUIDS.service, FIELDY_UUIDS.controlAndAudio, packet)
    expect(frames.length).toBe(2)
    expect(frames.every((f) => f.length === 40)).toBe(true)

    // A partial tail starting with the Opus TOC still ships.
    const withTail = new Uint8Array(60)
    withTail[0] = 0xb8
    withTail[40] = 0xb8
    transport.notify(FIELDY_UUIDS.service, FIELDY_UUIDS.controlAndAudio, withTail)
    expect(frames.length).toBe(4)
    expect(frames[3].length).toBe(20)

    // A partial tail without the TOC is dropped.
    const badTail = new Uint8Array(60)
    badTail[0] = 0xb8
    badTail[40] = 0x11
    transport.notify(FIELDY_UUIDS.service, FIELDY_UUIDS.controlAndAudio, badTail)
    expect(frames.length).toBe(5)
  })

  it('fills only the device-info fields the DIS did not provide', async () => {
    const transport = new FakeTransport()
    const clock = new ManualClock()
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.modelNumber),
      text('Compass Pro')
    )
    const connection = new FieldyDeviceConnection({
      device: makeBtDevice({ id: 'fieldy-2', name: 'compass', type: 'fieldy' }),
      transport,
      clock
    })
    const connecting = connection.connect()
    await tick()
    clock.advance(1_000)
    await connecting
    expect(connection.device.modelNumber).toBe('Compass Pro')
    expect(connection.device.hardwareRevision).toBe('Fieldy Hardware')
    expect(await connection.getAudioCodec()).toBe('opusFS320')
  })
})

describe('FrameDeviceConnection', () => {
  const setup = async (): Promise<{
    transport: FakeTransport
    connection: FrameDeviceConnection
  }> => {
    const transport = new FakeTransport()
    const connection = new FrameDeviceConnection({
      device: makeBtDevice({ id: 'frame-1', name: 'Frame', type: 'frame' }),
      transport,
      clock: new ManualClock()
    })
    await connection.connect()
    return { transport, connection }
  }

  it('hardcodes device info, letting a DIS read override the firmware', async () => {
    const transport = new FakeTransport()
    transport.reads.set(
      k(DEVICE_INFO_UUIDS.service, DEVICE_INFO_UUIDS.firmwareRevision),
      text('v24.111.1421')
    )
    const connection = new FrameDeviceConnection({
      device: makeBtDevice({ id: 'frame-2', name: 'Frame', type: 'frame' }),
      transport,
      clock: new ManualClock()
    })
    await connection.connect()
    expect(connection.device.firmwareRevision).toBe('v24.111.1421')
    expect(connection.device.hardwareRevision).toBe('Brilliant Labs Frame')
  })

  it('falls back to the last known battery level and only yields changes', async () => {
    const { transport, connection } = await setup()
    transport.reads.set(k(BATTERY_UUIDS.service, BATTERY_UUIDS.level), Uint8Array.from([64]))
    expect(await connection.getBatteryLevel()).toBe(64)
    transport.reads.set(k(BATTERY_UUIDS.service, BATTERY_UUIDS.level), new Error('unavailable'))
    expect(await connection.getBatteryLevel()).toBe(64)

    const levels: number[] = []
    connection.getBatteryLevelStream({
      onValue: (level) => levels.push(level),
      onFinish: () => undefined
    })
    transport.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [64])
    transport.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [63])
    transport.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [63])
    expect(levels).toEqual([63])
  })

  it('advertises photo hardware but keeps the SDK-dependent paths inert', async () => {
    const { connection } = await setup()
    expect(await connection.hasPhotoStreaming()).toBe(true)
    expect(await connection.startPhotoCapture()).toBe(false)
    expect(await connection.getAudioCodec()).toBe('pcm8')

    let finished = false
    connection.getAudioStream({
      onValue: () => expect.unreachable('Frame audio must not emit'),
      onFinish: () => {
        finished = true
      }
    })
    expect(finished).toBe(true)
    expect(await connection.playHaptic(1)).toBe(false)
    expect(await connection.getStorageList()).toEqual([])
  })
})

describe('createDeviceConnection', () => {
  it('maps every family to its client and leaves Apple Watch unbuilt', () => {
    const build = (type: Parameters<typeof makeBtDevice>[0]['type']): unknown =>
      createDeviceConnection({
        device: makeBtDevice({ id: 'x', name: null, type }),
        transport: new FakeTransport(),
        clock: new ManualClock()
      })

    expect(build('omi')).toBeInstanceOf(OmiDeviceConnection)
    expect(build('openglass')).toBeInstanceOf(OmiDeviceConnection)
    expect(build('bee')).toBeInstanceOf(BeeDeviceConnection)
    expect(build('plaud')).toBeInstanceOf(PlaudDeviceConnection)
    expect(build('limitless')).toBeInstanceOf(LimitlessDeviceConnection)
    expect(build('fieldy')).toBeInstanceOf(FieldyDeviceConnection)
    expect(build('friendPendant')).toBeInstanceOf(FriendPendantConnection)
    expect(build('frame')).toBeInstanceOf(FrameDeviceConnection)
    expect(build('appleWatch')).toBeNull()
  })
})
