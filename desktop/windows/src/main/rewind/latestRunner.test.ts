import { describe, it, expect } from 'vitest'
import { createLatestRunner } from './latestRunner'

/** A deferred promise so a test can control exactly when a task "finishes". */
function deferred<T = void>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

describe('createLatestRunner', () => {
  it('runs a single submission once', async () => {
    const seen: number[] = []
    const submit = createLatestRunner<number>(async (n) => {
      seen.push(n)
    })
    submit(1)
    await Promise.resolve()
    await Promise.resolve()
    expect(seen).toEqual([1])
  })

  // The core regression: while a task is in flight, the LATEST submission must
  // still be processed once the current one finishes — never dropped. (The old
  // "skip if busy" guard dropped it, stranding the cache on the previous screen.)
  it('processes the latest submission after the in-flight one completes', async () => {
    const seen: number[] = []
    const gate = deferred()
    const submit = createLatestRunner<number>(async (n) => {
      seen.push(n)
      if (n === 1) await gate.promise // hold the first task open
    })

    submit(1) // starts, blocks on the gate
    await Promise.resolve()
    submit(2) // arrives while 1 is in flight
    submit(3) // supersedes 2 — only the newest matters
    expect(seen).toEqual([1]) // 2 and 3 are still queued

    gate.resolve() // let 1 finish → trailing edge should run 3 (not 2)
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(seen).toEqual([1, 3])
  })

  it('runs sequential idle submissions each time', async () => {
    const seen: number[] = []
    const submit = createLatestRunner<number>(async (n) => {
      seen.push(n)
    })
    submit(1)
    await Promise.resolve()
    await Promise.resolve()
    submit(2)
    await Promise.resolve()
    await Promise.resolve()
    expect(seen).toEqual([1, 2])
  })

  it('keeps running the trailing task even if the in-flight task throws', async () => {
    const seen: number[] = []
    const gate = deferred()
    const submit = createLatestRunner<number>(async (n) => {
      seen.push(n)
      if (n === 1) {
        await gate.promise
        throw new Error('boom')
      }
    })
    submit(1)
    await Promise.resolve()
    submit(2)
    gate.resolve()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(seen).toEqual([1, 2])
  })
})
