/**
 * Multicast audio stream that owns the device-side recording session —
 * Windows port of macOS Session/DeviceAudioStreamController.swift. Used by
 * families where audio requires an explicit start/stop command (Bee, PLAUD):
 * the first subscriber triggers the start action, the last one leaving
 * triggers the stop action, and generation fencing keeps overlapping
 * start/stop transitions from cross-talking.
 */

export interface AudioStreamSubscriber {
  onFrame(frame: Uint8Array): void
  /** Exactly once; null on a normal finish. */
  onFinish(error: Error | null): void
}

export interface AudioStreamSubscription {
  cancel(): void
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'starting'; generation: number }
  | { kind: 'active'; generation: number }
  | { kind: 'stopping'; generation: number }

export class DeviceAudioStreamController {
  private phase: Phase = { kind: 'idle' }
  private generation = 0
  private subscribers = new Map<number, AudioStreamSubscriber>()
  private nextSubscriberId = 1
  private closed = false
  private terminalError: Error | null = null
  private startTask: Promise<void> | null = null
  private stopTask: Promise<void> | null = null

  constructor(
    private readonly actions: {
      start: () => Promise<void> | void
      stop: () => Promise<void> | void
    }
  ) {}

  get phaseKind(): Phase['kind'] {
    return this.phase.kind
  }

  get isClosed(): boolean {
    return this.closed
  }

  /** On a closed controller the subscriber is finished immediately — with the
   *  terminal error when the controller died on a failed stop. */
  subscribe(subscriber: AudioStreamSubscriber): AudioStreamSubscription {
    if (this.closed) {
      subscriber.onFinish(this.terminalError)
      return { cancel: () => undefined }
    }
    const id = this.nextSubscriberId++
    this.subscribers.set(id, subscriber)
    if (this.phase.kind === 'idle') {
      this.beginStart()
    }
    // starting/active: frames flow (or will) — nothing to do.
    // stopping: the clean-stop completion notices subscribers re-appeared
    // and starts a fresh generation.
    return {
      cancel: () => {
        if (!this.subscribers.delete(id)) return
        this.stopIfAbandoned()
      }
    }
  }

  /** Delivers a device frame to subscribers. Frames arriving outside the
   *  active phase are setup/teardown noise and are dropped. */
  yieldFrame(frame: Uint8Array): void {
    if (this.phase.kind !== 'active') return
    for (const subscriber of this.subscribers.values()) {
      subscriber.onFrame(frame)
    }
  }

  /** Session teardown: closes the controller, finishes subscribers (with the
   *  given error if any), and runs/awaits the stop action to release the
   *  device-side session. */
  async finish(error: Error | null = null): Promise<void> {
    if (this.closed) {
      await this.startTask?.catch(() => undefined)
      await this.stopTask?.catch(() => undefined)
      return
    }
    this.closed = true
    this.finishSubscribers(error)
    if (this.phase.kind === 'starting') {
      await this.startTask?.catch(() => undefined)
    }
    if (this.phase.kind === 'active') {
      this.beginStop(this.phase.generation)
    }
    await this.stopTask?.catch(() => undefined)
  }

  private beginStart(): void {
    const generation = ++this.generation
    this.phase = { kind: 'starting', generation }
    this.startTask = (async () => {
      let startError: unknown = null
      try {
        await this.actions.start()
      } catch (error) {
        startError = error
      }
      if (this.generation !== generation) return
      // The physical steps may have partially run either way, so the phase
      // becomes active and a failed start unwinds through a normal stop.
      this.phase = { kind: 'active', generation }
      if (startError !== null) {
        this.finishSubscribers(toError(startError))
        this.beginStop(generation)
        return
      }
      if (this.closed) {
        this.beginStop(generation)
        return
      }
      this.stopIfAbandoned()
    })()
  }

  private stopIfAbandoned(): void {
    if (this.subscribers.size > 0) return
    if (this.phase.kind === 'active') {
      this.beginStop(this.phase.generation)
    }
    // starting: the start completion re-checks and stops then (join-first).
  }

  private beginStop(generation: number): void {
    if (this.phase.kind !== 'active' || this.phase.generation !== generation) return
    this.phase = { kind: 'stopping', generation }
    this.stopTask = (async () => {
      let stopError: unknown = null
      try {
        await this.actions.stop()
      } catch (error) {
        stopError = error
      }
      if (this.generation !== generation) return
      if (stopError !== null) {
        // A device left in an unknown recording state cannot be reused.
        this.terminalError = toError(stopError)
        this.closed = true
        this.phase = { kind: 'idle' }
        this.finishSubscribers(this.terminalError)
        return
      }
      this.phase = { kind: 'idle' }
      if (!this.closed && this.subscribers.size > 0) {
        this.beginStart()
      }
    })()
  }

  private finishSubscribers(error: Error | null): void {
    const subscribers = Array.from(this.subscribers.values())
    this.subscribers.clear()
    for (const subscriber of subscribers) {
      subscriber.onFinish(error)
    }
  }
}

function toError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value))
}
