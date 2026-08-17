import { describe, it, expect } from 'vitest'
import { DeviceController, LOW_BATTERY_PERCENT, type BluetoothAccess } from './deviceController'
import type { DeviceEvent, DeviceSettings, WearableDeviceInfo } from '../../../shared/types'
import type { BlePhysicalDriver } from './transport/blePhysicalDriver'
import { OMI_UUIDS, BATTERY_UUIDS, DEVICE_INFO_UUIDS } from './protocol/uuids'
import { tick } from './testing/fakes'

const OMI_CODEC = OMI_UUIDS.audioCodec

/** A driver backed by a scripted GATT table, enough for a full connect. */
class ScriptedDriver implements BlePhysicalDriver {
  connected = false
  disconnectCalls = 0
  private notifyHandlers = new Map<string, (data: Uint8Array) => void>()
  private disconnectListeners = new Set<() => void>()

  constructor(
    public id = 'device-1',
    public name: string | null = 'Omi CV1',
    private readonly failConnect = false
  ) {}

  isConnected(): boolean {
    return this.connected
  }

  async connect(): Promise<void> {
    if (this.failConnect) throw new Error('gatt connect failed')
    this.connected = true
  }

  disconnect(): void {
    this.disconnectCalls += 1
    this.connected = false
  }

  async discoverServices(): Promise<Array<{ uuid: string }>> {
    return [
      { uuid: OMI_UUIDS.mainService },
      { uuid: BATTERY_UUIDS.service },
      { uuid: DEVICE_INFO_UUIDS.service }
    ]
  }

  async discoverCharacteristics(serviceUuid: string): Promise<Array<{ uuid: string }>> {
    if (serviceUuid === OMI_UUIDS.mainService) {
      return [{ uuid: OMI_UUIDS.audioDataStream }, { uuid: OMI_UUIDS.audioCodec }]
    }
    if (serviceUuid === BATTERY_UUIDS.service) return [{ uuid: BATTERY_UUIDS.level }]
    return [
      { uuid: DEVICE_INFO_UUIDS.modelNumber },
      { uuid: DEVICE_INFO_UUIDS.firmwareRevision },
      { uuid: DEVICE_INFO_UUIDS.hardwareRevision },
      { uuid: DEVICE_INFO_UUIDS.manufacturerName }
    ]
  }

  async readValue(_serviceUuid: string, characteristicUuid: string): Promise<Uint8Array> {
    if (characteristicUuid === OMI_CODEC) return Uint8Array.from([1]) // pcm8
    if (characteristicUuid === BATTERY_UUIDS.level) return Uint8Array.from([80])
    if (characteristicUuid === OMI_UUIDS.imageDataStream) throw new Error('no camera')
    return new TextEncoder().encode('omi')
  }

  async writeValue(): Promise<void> {
    // Writes always succeed in this harness.
  }

  async startNotifications(
    serviceUuid: string,
    characteristicUuid: string,
    onValue: (data: Uint8Array) => void
  ): Promise<void> {
    this.notifyHandlers.set(`${serviceUuid}:${characteristicUuid}`.toLowerCase(), onValue)
  }

  notify(serviceUuid: string, characteristicUuid: string, bytes: number[]): void {
    this.notifyHandlers.get(`${serviceUuid}:${characteristicUuid}`.toLowerCase())?.(
      Uint8Array.from(bytes)
    )
  }

  onDisconnected(listener: () => void): () => void {
    this.disconnectListeners.add(listener)
    return () => this.disconnectListeners.delete(listener)
  }

  fireDisconnected(): void {
    this.connected = false
    for (const l of Array.from(this.disconnectListeners)) l()
  }
}

interface Harness {
  controller: DeviceController
  events: DeviceEvent[]
  settings: DeviceSettings
  driver: ScriptedDriver
  saved: Array<Partial<DeviceSettings>>
  lane: {
    startCalls: number
    stopCalls: number
    fed: number
    blocked: boolean
  }
}

const harness = (
  options: {
    paired?: WearableDeviceInfo | null
    listen?: boolean
    driver?: ScriptedDriver
    requestDevice?: BluetoothAccess['requestDevice']
    laneBlocked?: boolean
    /** Runs while lane.start() is in flight, to simulate a racing change. */
    duringLaneStart?: (settings: DeviceSettings) => void
    /** Forces the audio service to refuse the session. */
    audioStartResult?: boolean
  } = {}
): Harness => {
  const driver = options.driver ?? new ScriptedDriver()
  const events: DeviceEvent[] = []
  const saved: Array<Partial<DeviceSettings>> = []
  const settings: DeviceSettings = {
    pairedDevice: options.paired ?? null,
    autoReconnect: true,
    deviceListenEnabled: options.listen ?? false
  }
  const lane = { startCalls: 0, stopCalls: 0, fed: 0, blocked: options.laneBlocked ?? false }

  const audioService =
    options.audioStartResult === false
      ? ({
          isProcessing: false,
          startProcessing: async () => false,
          stopProcessing: () => null
        } as never)
      : undefined

  const controller = new DeviceController({
    audioService,
    bluetooth: {
      requestDevice:
        options.requestDevice ?? (async () => ({ driver, serviceUuids: [OMI_UUIDS.mainService] })),
      reacquire: async (deviceId) =>
        deviceId === driver.id ? { driver, serviceUuids: [OMI_UUIDS.mainService] } : null
    },
    emit: (event) => events.push(event),
    settings: () => settings,
    saveSettings: async (patch) => {
      saved.push(patch)
      Object.assign(settings, patch)
    },
    createLane: () =>
      ({
        start: async () => {
          lane.startCalls += 1
          options.duringLaneStart?.(settings)
          return !lane.blocked
        },
        stop: () => {
          lane.stopCalls += 1
        },
        feed: () => {
          lane.fed += 1
        },
        currentState: lane.blocked ? 'blocked' : 'streaming'
      }) as never
  })

  return { controller, events, settings, driver, saved, lane }
}

const states = (events: DeviceEvent[]): string[] =>
  events.filter((e) => e.type === 'device-state').map((e) => (e as { state: string }).state)

describe('DeviceController pairing', () => {
  it('pairs a supported device, persists it, and connects', async () => {
    const h = harness()
    await h.controller.handleCommand({ type: 'device-pair' })
    expect(h.saved[0].pairedDevice).toMatchObject({ id: 'device-1', type: 'omi' })
    expect(h.events.some((e) => e.type === 'device-paired')).toBe(true)
    expect(states(h.events)).toContain('scanning')
    expect(states(h.events)).toContain('connected')
    expect(h.driver.connected).toBe(true)
  })

  it('refuses a device that is not a supported wearable', async () => {
    const unknown = new ScriptedDriver('x', 'Some Bluetooth Speaker')
    const h = harness({
      driver: unknown,
      requestDevice: async () => ({ driver: unknown, serviceUuids: [] })
    })
    await h.controller.handleCommand({ type: 'device-pair' })
    expect(h.saved.length).toBe(0)
    expect(
      h.events.some(
        (e) => e.type === 'device-error' && e.message.includes('not a supported Omi wearable')
      )
    ).toBe(true)
    expect(states(h.events)).toEqual(['scanning', 'idle'])
  })

  it('a cancelled chooser leaves nothing paired', async () => {
    const h = harness({ requestDevice: async () => null })
    await h.controller.handleCommand({ type: 'device-pair' })
    expect(h.saved.length).toBe(0)
    expect(states(h.events)).toEqual(['scanning', 'idle'])
  })

  it('reports a failed connect as an error state', async () => {
    const failing = new ScriptedDriver('device-1', 'Omi CV1', true)
    const h = harness({
      driver: failing,
      requestDevice: async () => ({ driver: failing, serviceUuids: [OMI_UUIDS.mainService] })
    })
    await h.controller.handleCommand({ type: 'device-pair' })
    expect(h.events.some((e) => e.type === 'device-error')).toBe(true)
    expect(states(h.events)).toContain('error')
  })
})

describe('DeviceController sessions', () => {
  it('connects a remembered device without a chooser', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' } })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    expect(states(h.events)).toContain('connected')
  })

  it('reports the device as unavailable when it cannot be reacquired', async () => {
    const h = harness({ paired: { id: 'other-device', name: 'Omi', type: 'omi' } })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'other-device' })
    expect(
      h.events.some(
        (e) => e.type === 'device-error' && e.message.includes('not currently available')
      )
    ).toBe(true)
  })

  it('refuses to connect with nothing paired', async () => {
    const h = harness()
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    expect(
      h.events.some((e) => e.type === 'device-error' && e.message === 'No device is paired yet.')
    ).toBe(true)
  })

  it('publishes battery levels and latches the low-battery warning', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' } })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })

    h.driver.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [55])
    h.driver.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [LOW_BATTERY_PERCENT - 1])
    h.driver.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [LOW_BATTERY_PERCENT - 2])
    const lowWarnings = h.events.filter(
      (e) => e.type === 'device-error' && e.message.includes('battery is at')
    )
    // Latched: hovering below the threshold warns once, not per notification.
    expect(lowWarnings.length).toBe(1)
    expect(h.events.filter((e) => e.type === 'device-battery').length).toBe(3)

    // Charging back above the threshold re-arms the warning.
    h.driver.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [50])
    h.driver.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [5])
    expect(
      h.events.filter((e) => e.type === 'device-error' && e.message.includes('battery is at'))
        .length
    ).toBe(2)
  })

  it('forgets a device: stops the session, clears the pairing, and reports it', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' }, listen: true })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await h.controller.handleCommand({ type: 'device-forget' })
    expect(h.saved[h.saved.length - 1]).toEqual({ pairedDevice: null })
    expect(h.events.some((e) => e.type === 'device-forgotten')).toBe(true)
    expect(h.lane.stopCalls).toBeGreaterThan(0)
  })
})

describe('DeviceController listening', () => {
  it('does not open the lane while listening is off', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' }, listen: false })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    expect(h.lane.startCalls).toBe(0)
  })

  it('opens the lane and reports the negotiated codec when listening is on', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' }, listen: true })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await tick()
    expect(h.lane.startCalls).toBe(1)
    expect(h.events.some((e) => e.type === 'device-codec' && e.codec === 'pcm8')).toBe(true)
  })

  it('does not start decoding when the conversation slot is taken', async () => {
    const h = harness({
      paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' },
      listen: true,
      laneBlocked: true
    })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await tick()
    expect(h.lane.startCalls).toBe(1)
    expect(h.events.some((e) => e.type === 'device-listen-state')).toBe(true)
    // No codec is read, so nothing was decoded into a lane that cannot exist.
    expect(h.events.some((e) => e.type === 'device-codec')).toBe(false)
  })

  it('toggling listening on and off starts and stops the lane on a live session', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' }, listen: false })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    expect(h.lane.startCalls).toBe(0)

    h.settings.deviceListenEnabled = true
    await h.controller.handleCommand({
      type: 'device-settings',
      settings: { ...h.settings, deviceListenEnabled: true }
    })
    await tick()
    expect(h.lane.startCalls).toBe(1)

    await h.controller.handleCommand({
      type: 'device-settings',
      settings: { ...h.settings, deviceListenEnabled: false }
    })
    expect(h.lane.stopCalls).toBe(1)
  })

  it('turning auto-reconnect off stops the retry ladder', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' } })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await h.controller.handleCommand({
      type: 'device-settings',
      settings: { ...h.settings, autoReconnect: false }
    })
    expect(h.controller.sessionCoordinator.autoReconnectEnabled).toBe(false)

    h.driver.fireDisconnected()
    await tick()
    expect(h.controller.sessionCoordinator.snapshot.phase.kind).not.toBe('waitingToReconnect')
  })

  it('does not open a lane for a device that cannot stream audio', async () => {
    // Frame has no audio path on this client, so a lane would create an empty
    // conversation and immediately tear it down.
    const h = harness({ paired: { id: 'device-1', name: 'Frame', type: 'frame' }, listen: true })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await tick()
    expect(h.lane.startCalls).toBe(0)
    expect(
      h.events.some((e) => e.type === 'device-listen-state' && e.state === 'unsupported')
    ).toBe(true)
  })

  it('stops the lane when listening is turned off while it was opening', async () => {
    const h = harness({
      paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' },
      listen: true,
      duringLaneStart: (settings) => {
        settings.deviceListenEnabled = false
      }
    })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await tick()
    expect(h.lane.startCalls).toBe(1)
    // The socket opened, so it must be closed rather than left recording for a
    // setting the user just turned off.
    expect(h.lane.stopCalls).toBe(1)
    expect(h.events.some((e) => e.type === 'device-codec')).toBe(false)
  })

  it('stops the lane when audio decoding fails to start', async () => {
    const h = harness({
      paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' },
      listen: true,
      audioStartResult: false
    })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await tick()
    expect(h.lane.startCalls).toBe(1)
    // Otherwise the conversation stays open with nothing feeding it.
    expect(h.lane.stopCalls).toBe(1)
  })

  it('republishes the current state so a late UI is not shown a stale device', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' } })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    h.driver.notify(BATTERY_UUIDS.service, BATTERY_UUIDS.level, [42])
    const before = h.events.length

    await h.controller.handleCommand({ type: 'device-request-state' })
    const replayed = h.events.slice(before)
    expect(replayed.some((e) => e.type === 'device-state' && e.state === 'connected')).toBe(true)
    expect(replayed.some((e) => e.type === 'device-battery' && e.level === 42)).toBe(true)
  })

  it('an unexpected drop ends the session and schedules a reconnect', async () => {
    const h = harness({ paired: { id: 'device-1', name: 'Omi CV1', type: 'omi' }, listen: true })
    await h.controller.handleCommand({ type: 'device-connect', deviceId: 'device-1' })
    await tick()
    h.driver.fireDisconnected()
    await tick()
    expect(h.lane.stopCalls).toBeGreaterThan(0)
    expect(states(h.events)).toContain('reconnecting')
  })
})
