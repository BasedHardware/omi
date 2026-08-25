import { describe, it, expect } from 'vitest'
import {
  DeviceSessionCoordinator,
  RECONNECT_DELAY_MS,
  type DeviceReconnectRequest,
  type DeviceSessionSnapshot
} from './deviceSessionCoordinator'
import { makeBtDevice, type BtDevice } from '../protocol/btDevice'
import type { DeviceConnection } from '../connections/deviceConnection'
import { ManualClock, tick } from '../testing/fakes'

const DEVICE = makeBtDevice({ id: 'dev-1', name: 'omi', type: 'omi' })

class StubConnection {
  connectCalls = 0
  disconnectCalls = 0
  unpairCalls = 0
  connectError: Error | null = null
  private gate: Promise<void> | null = null

  constructor(
    public device: BtDevice = DEVICE,
    gate?: Promise<void>
  ) {
    this.gate = gate ?? null
  }

  async connect(): Promise<void> {
    this.connectCalls += 1
    if (this.gate !== null) await this.gate
    if (this.connectError !== null) throw this.connectError
  }

  async disconnect(): Promise<void> {
    this.disconnectCalls += 1
  }

  async unpair(): Promise<void> {
    this.unpairCalls += 1
  }

  as(): DeviceConnection {
    return this as unknown as DeviceConnection
  }
}

const setup = (
  options: {
    connection?: StubConnection | null
    paired?: BtDevice | null
    factory?: (device: BtDevice, generation: number) => DeviceConnection | null
  } = {}
): {
  coordinator: DeviceSessionCoordinator
  clock: ManualClock
  snapshots: DeviceSessionSnapshot[]
  reconnects: DeviceReconnectRequest[]
  discoveries: number[]
  endings: number[]
} => {
  const clock = new ManualClock()
  const snapshots: DeviceSessionSnapshot[] = []
  const reconnects: DeviceReconnectRequest[] = []
  const discoveries: number[] = []
  const endings: number[] = []
  const connection = options.connection
  const coordinator = new DeviceSessionCoordinator(
    {
      connectionFactory: options.factory ?? (() => (connection == null ? null : connection.as())),
      onSnapshot: (snapshot) => snapshots.push(snapshot),
      onReconnectRequested: (request) => reconnects.push(request),
      onDiscoveryRequested: () => discoveries.push(discoveries.length),
      onSessionEnded: () => endings.push(endings.length)
    },
    { pairedDevice: options.paired ?? null, clock }
  )
  return { coordinator, clock, snapshots, reconnects, discoveries, endings }
}

describe('DeviceSessionCoordinator connect', () => {
  it('walks idle to ready and records the paired and connected device', async () => {
    const connection = new StubConnection()
    const { coordinator, snapshots } = setup({ connection })
    await coordinator.connect(DEVICE)
    expect(coordinator.snapshot.phase.kind).toBe('ready')
    expect(coordinator.snapshot.connectedDevice?.id).toBe('dev-1')
    expect(coordinator.snapshot.pairedDevice?.id).toBe('dev-1')
    expect(coordinator.snapshot.failureMessage).toBeNull()
    expect(snapshots.map((s) => s.phase.kind)).toEqual(['connecting', 'ready'])
    expect(coordinator.connection).not.toBeNull()
  })

  it('refuses a second connect while one is in flight', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const connection = new StubConnection(DEVICE, gate)
    const { coordinator } = setup({ connection })
    const first = coordinator.connect(DEVICE)
    await expect(coordinator.connect(DEVICE)).rejects.toMatchObject({
      kind: 'connectionAlreadyActive',
      message: 'A device connection is already active'
    })
    release()
    await first
  })

  it('an unreachable device fails with connectionUnavailable and records it', async () => {
    const { coordinator } = setup({ connection: null })
    await expect(coordinator.connect(DEVICE)).rejects.toMatchObject({
      kind: 'connectionUnavailable',
      message: 'The device is not currently available over Bluetooth'
    })
    expect(coordinator.snapshot.phase.kind).toBe('idle')
    expect(coordinator.snapshot.failureMessage).toBe(
      'The device is not currently available over Bluetooth'
    )
  })

  it('a failing connect records the reason and disconnects the half-built session', async () => {
    const connection = new StubConnection()
    connection.connectError = new Error('device went away')
    const { coordinator } = setup({ connection })
    await expect(coordinator.connect(DEVICE)).rejects.toThrow('device went away')
    expect(coordinator.snapshot.phase.kind).toBe('idle')
    expect(coordinator.snapshot.failureMessage).toBe('device went away')
    expect(connection.disconnectCalls).toBe(1)
    expect(coordinator.connection).toBeNull()
  })
})

describe('DeviceSessionCoordinator reconnect', () => {
  it('an unexpected disconnect ends the session and retries immediately without scanning', async () => {
    const connection = new StubConnection()
    const { coordinator, reconnects, discoveries, endings } = setup({ connection })
    await coordinator.connect(DEVICE)

    coordinator.handleUnexpectedDisconnect(connection.as())
    expect(coordinator.snapshot.failureMessage).toBe('Device disconnected unexpectedly')
    expect(endings.length).toBe(1)
    expect(coordinator.snapshot.phase).toEqual({ kind: 'waitingToReconnect', attempt: 1 })
    await tick()
    expect(reconnects.length).toBe(1)
    // Scanning would clear the cached peripheral the direct retry needs.
    expect(discoveries.length).toBe(0)
  })

  it('ignores an unexpected disconnect from a superseded connection', async () => {
    const connection = new StubConnection()
    const { coordinator, endings } = setup({ connection })
    await coordinator.connect(DEVICE)
    coordinator.handleUnexpectedDisconnect(new StubConnection().as())
    expect(coordinator.snapshot.phase.kind).toBe('ready')
    expect(endings.length).toBe(0)
  })

  it('a failed immediate retry falls back to the delayed path, which scans first', async () => {
    const { coordinator, clock, reconnects, discoveries } = setup({
      connection: null,
      paired: DEVICE
    })
    coordinator.startReconnecting()
    await tick()
    expect(reconnects.length).toBe(1)
    expect(discoveries.length).toBe(0)

    // The scheduled attempt runs and cannot build a connection.
    await expect(coordinator.connect(DEVICE, reconnects[0])).rejects.toMatchObject({
      kind: 'connectionUnavailable'
    })
    expect(coordinator.snapshot.phase).toEqual({ kind: 'waitingToReconnect', attempt: 2 })
    expect(discoveries.length).toBe(1)

    // Fixed cadence, no backoff growth.
    clock.advance(RECONNECT_DELAY_MS - 1)
    await tick()
    expect(reconnects.length).toBe(1)
    clock.advance(1)
    await tick()
    expect(reconnects.length).toBe(2)
    expect(reconnects[1].attempt).toBe(2)
  })

  it('retries forever at a fixed delay', async () => {
    const { coordinator, clock, reconnects } = setup({ connection: null, paired: DEVICE })
    coordinator.startReconnecting()
    await tick()
    for (let i = 0; i < 4; i += 1) {
      await expect(
        coordinator.connect(DEVICE, reconnects[reconnects.length - 1])
      ).rejects.toMatchObject({ kind: 'connectionUnavailable' })
      clock.advance(RECONNECT_DELAY_MS)
      await tick()
    }
    expect(reconnects.length).toBe(5)
    expect(reconnects[4].attempt).toBe(5)
  })

  it('a successful connect resets the attempt counter labelling the wait', async () => {
    const connection = new StubConnection()
    let reachable = false
    const { coordinator, clock, reconnects } = setup({
      paired: DEVICE,
      factory: () => (reachable ? connection.as() : null)
    })
    coordinator.startReconnecting()
    await tick()
    // Two failed retries push the attempt counter to 3.
    for (let i = 0; i < 2; i += 1) {
      await expect(
        coordinator.connect(DEVICE, reconnects[reconnects.length - 1])
      ).rejects.toBeDefined()
      clock.advance(RECONNECT_DELAY_MS)
      await tick()
    }
    expect(coordinator.snapshot.phase).toEqual({ kind: 'waitingToReconnect', attempt: 3 })

    reachable = true
    await coordinator.connect(DEVICE, reconnects[reconnects.length - 1])
    expect(coordinator.snapshot.phase.kind).toBe('ready')

    // The next drop starts counting from one again.
    coordinator.handleUnexpectedDisconnect(connection.as())
    expect(coordinator.snapshot.phase).toEqual({ kind: 'waitingToReconnect', attempt: 1 })
  })

  it('a stale reconnect request is superseded', async () => {
    const connection = new StubConnection()
    const { coordinator, reconnects } = setup({ connection, paired: DEVICE })
    coordinator.startReconnecting()
    await tick()
    const request = reconnects[0]
    // Something else advanced the session in the meantime.
    await coordinator.connect(DEVICE)
    await expect(coordinator.connect(DEVICE, request)).rejects.toMatchObject({
      kind: 'superseded',
      message: 'The device connection was superseded'
    })
  })

  it('stopReconnecting cancels the pending retry and returns to idle', async () => {
    const { coordinator, clock, reconnects } = setup({ connection: null, paired: DEVICE })
    coordinator.startReconnecting()
    await tick()
    await expect(coordinator.connect(DEVICE, reconnects[0])).rejects.toBeDefined()
    expect(coordinator.snapshot.phase.kind).toBe('waitingToReconnect')

    coordinator.stopReconnecting()
    expect(coordinator.snapshot.phase.kind).toBe('idle')
    clock.advance(RECONNECT_DELAY_MS * 3)
    await tick()
    expect(reconnects.length).toBe(1)
  })

  it('does not schedule a retry with auto-reconnect off or no paired device', async () => {
    const off = setup({ connection: null, paired: DEVICE })
    off.coordinator.autoReconnectEnabled = false
    off.coordinator.startReconnecting()
    await tick()
    expect(off.reconnects.length).toBe(0)
    expect(off.coordinator.snapshot.phase.kind).toBe('idle')

    const unpaired = setup({ connection: null, paired: null })
    unpaired.coordinator.startReconnecting()
    await tick()
    expect(unpaired.reconnects.length).toBe(0)
  })
})

describe('DeviceSessionCoordinator disconnect and unpair', () => {
  it('disconnect tears down and immediately schedules a direct reconnect', async () => {
    const connection = new StubConnection()
    const { coordinator, reconnects, discoveries, endings } = setup({ connection })
    await coordinator.connect(DEVICE)
    await coordinator.disconnect()
    expect(connection.disconnectCalls).toBe(1)
    expect(endings.length).toBe(1)
    expect(coordinator.snapshot.connectedDevice).toBeNull()
    await tick()
    expect(reconnects.length).toBe(1)
    expect(discoveries.length).toBe(0)
  })

  it('disconnect(null) stays disconnected', async () => {
    const connection = new StubConnection()
    const { coordinator, reconnects } = setup({ connection })
    await coordinator.connect(DEVICE)
    await coordinator.disconnect(null)
    expect(coordinator.snapshot.phase.kind).toBe('idle')
    await tick()
    expect(reconnects.length).toBe(0)
  })

  it('a delayed disconnect scans before retrying', async () => {
    const connection = new StubConnection()
    const { coordinator, clock, reconnects, discoveries } = setup({ connection })
    await coordinator.connect(DEVICE)
    await coordinator.disconnect(30_000)
    expect(discoveries.length).toBe(1)
    clock.advance(30_000)
    await tick()
    expect(reconnects.length).toBe(1)
  })

  it('unpair forgets the device and stops reconnecting', async () => {
    const connection = new StubConnection()
    const { coordinator, clock, reconnects, endings } = setup({ connection })
    await coordinator.connect(DEVICE)
    await coordinator.unpair()
    expect(connection.unpairCalls).toBe(1)
    expect(coordinator.snapshot.pairedDevice).toBeNull()
    expect(coordinator.snapshot.phase.kind).toBe('idle')
    expect(endings.length).toBe(1)
    clock.advance(RECONNECT_DELAY_MS * 2)
    await tick()
    expect(reconnects.length).toBe(0)
  })

  it('unpair with no active connection just clears the pairing', async () => {
    const { coordinator } = setup({ connection: null, paired: DEVICE })
    await coordinator.unpair()
    expect(coordinator.snapshot.pairedDevice).toBeNull()
    expect(coordinator.snapshot.phase.kind).toBe('idle')
  })
})
