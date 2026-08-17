import { describe, it, expect } from 'vitest'
import { DeviceCommandQueue, DeviceCommandQueueError } from './deviceCommandQueue'

const deferred = <T = void,>(): {
  promise: Promise<T>
  resolve: (v: T) => void
  reject: (e: Error) => void
} => {
  let resolve!: (v: T) => void
  let reject!: (e: Error) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const tick = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

describe('DeviceCommandQueue', () => {
  it('runs operations strictly in FIFO order', async () => {
    const queue = new DeviceCommandQueue()
    const firstGate = deferred()
    const starts: string[] = []
    const first = queue.run(async () => {
      starts.push('first')
      await firstGate.promise
      return 'one'
    })
    const second = queue.run(async () => {
      starts.push('second')
      return 'two'
    })
    await tick()
    expect(starts).toEqual(['first'])
    firstGate.resolve()
    await expect(first).resolves.toBe('one')
    await expect(second).resolves.toBe('two')
    expect(starts).toEqual(['first', 'second'])
  })

  it('a failed operation does not block its successors', async () => {
    const queue = new DeviceCommandQueue()
    const first = queue.run(() => Promise.reject(new Error('boom')))
    const second = queue.run(() => 'ok')
    await expect(first).rejects.toThrow('boom')
    await expect(second).resolves.toBe('ok')
  })

  it('run on a closed queue throws closed', async () => {
    const queue = new DeviceCommandQueue()
    await queue.close()
    await expect(queue.run(() => 'x')).rejects.toBeInstanceOf(DeviceCommandQueueError)
  })

  it('close cancels queued operations without running them', async () => {
    const queue = new DeviceCommandQueue()
    const activeGate = deferred()
    let queuedRan = false
    const active = queue.run(async () => {
      await activeGate.promise
      return 'active'
    })
    await tick()
    const queued = queue.run(() => {
      queuedRan = true
      return 'queued'
    })
    const closing = queue.close()
    await expect(queued).rejects.toBeInstanceOf(DeviceCommandQueueError)
    expect(queuedRan).toBe(false)
    activeGate.resolve()
    await expect(active).resolves.toBe('active')
    await closing
  })

  it('close aborts the active operation and awaits the chain', async () => {
    const queue = new DeviceCommandQueue()
    let sawAbort = false
    const activeGate = deferred()
    const active = queue.run(async (signal) => {
      signal.addEventListener('abort', () => {
        sawAbort = true
        activeGate.resolve()
      })
      await activeGate.promise
      return 'done'
    })
    await tick()
    await queue.close()
    expect(sawAbort).toBe(true)
    await expect(active).resolves.toBe('done')
  })
})
