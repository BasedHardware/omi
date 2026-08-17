import { describe, it, expect } from 'vitest'
import {
  DeviceAudioStreamController,
  type AudioStreamSubscriber
} from './deviceAudioStreamController'

const deferred = (): { promise: Promise<void>; resolve: () => void; reject: (e: Error) => void } => {
  let resolve!: () => void
  let reject!: (e: Error) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const tick = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

interface Recorder extends AudioStreamSubscriber {
  frames: Uint8Array[]
  finished: { error: Error | null } | null
}

const recorder = (): Recorder => {
  const rec: Recorder = {
    frames: [],
    finished: null,
    onFrame: (frame) => rec.frames.push(frame),
    onFinish: (error) => {
      rec.finished = { error }
    }
  }
  return rec
}

/** Controller harness with controllable start/stop actions. */
const harness = (): {
  controller: DeviceAudioStreamController
  starts: Array<ReturnType<typeof deferred>>
  stops: Array<ReturnType<typeof deferred>>
} => {
  const starts: Array<ReturnType<typeof deferred>> = []
  const stops: Array<ReturnType<typeof deferred>> = []
  const controller = new DeviceAudioStreamController({
    start: () => {
      const d = deferred()
      starts.push(d)
      return d.promise
    },
    stop: () => {
      const d = deferred()
      stops.push(d)
      return d.promise
    }
  })
  return { controller, starts, stops }
}

describe('DeviceAudioStreamController', () => {
  it('first subscriber starts the session once; frames flow only while active', async () => {
    const { controller, starts } = harness()
    const sub1 = recorder()
    controller.subscribe(sub1)
    expect(starts.length).toBe(1)
    expect(controller.phaseKind).toBe('starting')

    // Setup-phase frames are dropped.
    controller.yieldFrame(Uint8Array.from([1]))
    expect(sub1.frames.length).toBe(0)

    starts[0].resolve()
    await tick()
    expect(controller.phaseKind).toBe('active')

    const sub2 = recorder()
    controller.subscribe(sub2)
    expect(starts.length).toBe(1)

    controller.yieldFrame(Uint8Array.from([2]))
    expect(sub1.frames.length).toBe(1)
    expect(sub2.frames.length).toBe(1)
  })

  it('last subscriber leaving stops; re-subscribing during the stop restarts after it', async () => {
    const { controller, starts, stops } = harness()
    const sub1 = recorder()
    const subscription = controller.subscribe(sub1)
    starts[0].resolve()
    await tick()

    subscription.cancel()
    expect(controller.phaseKind).toBe('stopping')
    expect(stops.length).toBe(1)

    // Teardown-phase frames are dropped.
    controller.yieldFrame(Uint8Array.from([9]))
    expect(sub1.frames.length).toBe(0)

    const sub2 = recorder()
    controller.subscribe(sub2)
    expect(starts.length).toBe(1)

    stops[0].resolve()
    await tick()
    expect(starts.length).toBe(2)
    starts[1].resolve()
    await tick()
    expect(controller.phaseKind).toBe('active')
    controller.yieldFrame(Uint8Array.from([3]))
    expect(sub2.frames.length).toBe(1)
  })

  it('a subscriber leaving mid-start joins the setup first, then stops', async () => {
    const { controller, starts, stops } = harness()
    const sub = recorder()
    const subscription = controller.subscribe(sub)
    subscription.cancel()
    expect(stops.length).toBe(0)
    starts[0].resolve()
    await tick()
    expect(stops.length).toBe(1)
    stops[0].resolve()
    await tick()
    expect(controller.phaseKind).toBe('idle')
  })

  it('start failure finishes subscribers with the error and unwinds through stop', async () => {
    const { controller, starts, stops } = harness()
    const sub = recorder()
    controller.subscribe(sub)
    starts[0].reject(new Error('device did not acknowledge'))
    await tick()
    expect(sub.finished?.error?.message).toBe('device did not acknowledge')
    expect(stops.length).toBe(1)
    stops[0].resolve()
    await tick()
    expect(controller.isClosed).toBe(false)
  })

  it('stop failure closes the controller permanently with a terminal error', async () => {
    const { controller, starts, stops } = harness()
    const sub = recorder()
    const subscription = controller.subscribe(sub)
    starts[0].resolve()
    await tick()
    subscription.cancel()
    stops[0].reject(new Error('mute lost'))
    await tick()
    expect(controller.isClosed).toBe(true)

    const late = recorder()
    controller.subscribe(late)
    expect(late.finished?.error?.message).toBe('mute lost')
  })

  it('finish closes, finishes subscribers, and awaits the stop action', async () => {
    const { controller, starts, stops } = harness()
    const sub = recorder()
    controller.subscribe(sub)
    starts[0].resolve()
    await tick()

    let finishResolved = false
    const finishing = controller.finish().then(() => {
      finishResolved = true
    })
    await tick()
    expect(sub.finished).toEqual({ error: null })
    expect(stops.length).toBe(1)
    expect(finishResolved).toBe(false)
    stops[0].resolve()
    await finishing
    expect(controller.isClosed).toBe(true)

    const late = recorder()
    controller.subscribe(late)
    expect(late.finished).toEqual({ error: null })
  })

  it('finish during starting joins the start, then stops', async () => {
    const { controller, starts, stops } = harness()
    controller.subscribe(recorder())
    const finishing = controller.finish(new Error('session torn down'))
    await tick()
    expect(stops.length).toBe(0)
    starts[0].resolve()
    await tick()
    expect(stops.length).toBe(1)
    stops[0].resolve()
    await finishing
  })
})
