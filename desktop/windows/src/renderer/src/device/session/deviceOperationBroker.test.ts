import { describe, it, expect } from 'vitest'
import {
  DeviceOperationBroker,
  DeviceOperationBrokerError,
  UncorrelatedOperationGate,
  type DeviceOperationClock,
  type DeviceOperationTermination
} from './deviceOperationBroker'

class ManualClock implements DeviceOperationClock {
  private pending: Array<(r: 'elapsed' | 'aborted') => void> = []

  sleep(_ms: number, signal: AbortSignal): Promise<'elapsed' | 'aborted'> {
    return new Promise((resolve) => {
      if (signal.aborted) {
        resolve('aborted')
        return
      }
      this.pending.push(resolve)
      signal.addEventListener(
        'abort',
        () => {
          const index = this.pending.indexOf(resolve)
          if (index >= 0) this.pending.splice(index, 1)
          resolve('aborted')
        },
        { once: true }
      )
    })
  }

  fireAll(): void {
    for (const resolve of this.pending.splice(0)) resolve('elapsed')
  }
}

const deferred = (): {
  promise: Promise<void>
  resolve: () => void
  reject: (e: Error) => void
} => {
  let resolve!: () => void
  let reject!: (e: Error) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('UncorrelatedOperationGate', () => {
  it('one live attempt per key, released by the callback claim', () => {
    const gate = new UncorrelatedOperationGate()
    expect(gate.canStart('k')).toBe(true)
    const handle = gate.register('k')
    expect(handle).not.toBeNull()
    expect(gate.canStart('k')).toBe(false)
    expect(gate.register('k')).toBeNull()
    expect(gate.takeHandleForCallback('k')).toEqual(handle)
    expect(gate.takeHandleForCallback('k')).toBeNull()
    expect(gate.canStart('k')).toBe(true)
  })

  it('non-success termination poisons the key until reset', () => {
    const gate = new UncorrelatedOperationGate()
    const handle = gate.register('k')!
    gate.terminal(handle, 'timedOut')
    expect(gate.isPoisoned('k')).toBe(true)
    expect(gate.canStart('k')).toBe(false)
    expect(gate.register('k')).toBeNull()
    expect(gate.takeHandleForCallback('k')).toBeNull()
    gate.reset()
    expect(gate.canStart('k')).toBe(true)
  })

  it('successful termination keeps the key clean', () => {
    const gate = new UncorrelatedOperationGate()
    const handle = gate.register('k')!
    gate.takeHandleForCallback('k')
    gate.terminal(handle, 'succeeded')
    expect(gate.canStart('k')).toBe(true)
  })

  it('a stale terminal poisons the key but never evicts a newer attempt handle', () => {
    const gate = new UncorrelatedOperationGate()
    const first = gate.register('k')!
    gate.takeHandleForCallback('k')
    gate.terminal(first, 'succeeded')
    const second = gate.register('k')!
    gate.terminal(first, 'failed')
    expect(gate.isPoisoned('k')).toBe(true)
    // The newer live handle is untouched (token mismatch) even though the
    // key is now poisoned for future callbacks.
    expect(gate.takeHandleForCallback('k')).toBeNull()
    gate.reset()
    expect(second.token).not.toBe(first.token)
  })
})

describe('DeviceOperationBroker', () => {
  it('rejects a second operation with the same key while one is pending', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const first = broker.perform<number>({ key: 'k', start: () => undefined })
    await expect(broker.perform({ key: 'k', start: () => undefined })).rejects.toMatchObject({
      kind: 'operationAlreadyPending'
    })
    broker.succeed('k', 1)
    await expect(first).resolves.toBe(1)
  })

  it('resolves through succeed with onTerminal firing before the caller resumes', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const events: string[] = []
    const promise = broker
      .perform<number>({
        key: 'k',
        onTerminal: (t: DeviceOperationTermination) => events.push(`terminal:${t}`),
        start: () => {
          events.push('started')
        }
      })
      .then((v) => {
        events.push('resumed')
        return v
      })
    broker.succeed('k', 7)
    await expect(promise).resolves.toBe(7)
    expect(events).toEqual(['started', 'terminal:succeeded', 'resumed'])
  })

  it('succeed after a failed start throws the start error instead of the value', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const terminations: DeviceOperationTermination[] = []
    const startError = new Error('write rejected')
    const promise = broker.perform<number>({
      key: 'k',
      onTerminal: (t) => terminations.push(t),
      start: () => Promise.reject(startError)
    })
    broker.succeed('k', 7)
    await expect(promise).rejects.toBe(startError)
    expect(terminations).toEqual(['failed'])
  })

  it('times out on the injected clock and ignores a late succeed', async () => {
    const clock = new ManualClock()
    const broker = new DeviceOperationBroker(clock)
    const terminations: DeviceOperationTermination[] = []
    const promise = broker.perform<number>({
      key: 'k',
      timeoutMs: 5000,
      onTerminal: (t) => terminations.push(t),
      start: () => undefined
    })
    clock.fireAll()
    await expect(promise).rejects.toMatchObject({ kind: 'timedOut' })
    broker.succeed('k', 9)
    expect(terminations).toEqual(['timedOut'])
  })

  it('a claimed succeed beats a later timeout and fail', async () => {
    const clock = new ManualClock()
    const broker = new DeviceOperationBroker(clock)
    const start = deferred()
    const promise = broker.perform<number>({
      key: 'k',
      timeoutMs: 5000,
      start: () => start.promise
    })
    broker.succeed('k', 3)
    clock.fireAll()
    broker.fail('k', new Error('late error'))
    start.resolve()
    await expect(promise).resolves.toBe(3)
  })

  it('cancelAll supersedes even a claimed completion still awaiting its start task', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const start = deferred()
    const terminations: DeviceOperationTermination[] = []
    const promise = broker.perform<number>({
      key: 'k',
      onTerminal: (t) => terminations.push(t),
      start: () => start.promise
    })
    broker.succeed('k', 3)
    broker.cancelAll('disconnected')
    start.resolve()
    await expect(promise).rejects.toMatchObject({
      kind: 'disconnected',
      message: 'Device disconnected before the operation completed'
    })
    expect(terminations).toEqual(['disconnected'])
  })

  it('fail rejects the pending operation', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const promise = broker.perform<number>({ key: 'k', start: () => undefined })
    broker.fail('k', new DeviceOperationBrokerError('failed', 'callback error'))
    await expect(promise).rejects.toMatchObject({ kind: 'failed', message: 'callback error' })
  })

  it('a settled key is free for a new operation', async () => {
    const clock = new ManualClock()
    const broker = new DeviceOperationBroker(clock)
    const first = broker.perform<number>({ key: 'k', timeoutMs: 1000, start: () => undefined })
    clock.fireAll()
    await expect(first).rejects.toMatchObject({ kind: 'timedOut' })
    const second = broker.perform<number>({ key: 'k', start: () => undefined })
    broker.succeed('k', 11)
    await expect(second).resolves.toBe(11)
  })

  it('cancelAll cancels every pending key', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const a = broker.perform<number>({ key: 'a', start: () => undefined })
    const b = broker.perform<number>({ key: 'b', start: () => undefined })
    broker.cancelAll()
    await expect(a).rejects.toMatchObject({ kind: 'cancelled' })
    await expect(b).rejects.toMatchObject({ kind: 'cancelled' })
    expect(broker.hasPending('a')).toBe(false)
  })
})
