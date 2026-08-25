/**
 * Minimal multicast subject (the mac stack's PassthroughSubject equivalent):
 * device connections push decoded frames/events into one of these and hand
 * subscribers out of it. finish() is terminal and idempotent; late
 * subscribers on a finished subject are finished immediately.
 */

export interface SubjectSubscriber<T> {
  onValue(value: T): void
  onFinish(error: Error | null): void
}

export interface SubjectSubscription {
  cancel(): void
}

export class Subject<T> {
  private subscribers = new Map<number, SubjectSubscriber<T>>()
  private nextId = 1
  private finished: { error: Error | null } | null = null

  subscribe(subscriber: SubjectSubscriber<T>): SubjectSubscription {
    if (this.finished !== null) {
      subscriber.onFinish(this.finished.error)
      return { cancel: () => undefined }
    }
    const id = this.nextId++
    this.subscribers.set(id, subscriber)
    return { cancel: () => this.subscribers.delete(id) }
  }

  get subscriberCount(): number {
    return this.subscribers.size
  }

  next(value: T): void {
    if (this.finished !== null) return
    for (const subscriber of Array.from(this.subscribers.values())) {
      subscriber.onValue(value)
    }
  }

  finish(error: Error | null = null): void {
    if (this.finished !== null) return
    this.finished = { error }
    const subscribers = Array.from(this.subscribers.values())
    this.subscribers.clear()
    for (const subscriber of subscribers) {
      subscriber.onFinish(error)
    }
  }
}
