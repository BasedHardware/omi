// Per-chat task serializer for the AI-clone responder. One task runs per chat
// at a time; a task submitted while one is in flight is PARKED and run after
// the current one finishes — never dropped (a plain in-flight guard silently
// lost messages that arrived during reply generation). Parking coalesces:
// only the newest parked task per chat runs, matching the one-draft-per-chat
// semantics — a superseded message still reaches the model as transcript
// context of the newer reply. Different chats run concurrently.
export class ChatTaskQueue {
  private inFlight = new Set<string>()
  private parked = new Map<string, () => Promise<void>>()

  /** Reservation happens synchronously, so two same-tick submits can't race. */
  submit(chatId: string, task: () => Promise<void>): void {
    if (this.inFlight.has(chatId)) {
      this.parked.set(chatId, task) // newest wins
      return
    }
    this.inFlight.add(chatId)
    void (async () => {
      try {
        await task()
      } catch (e) {
        // Tasks own their error reporting (respond() records failures in the
        // activity feed); this catch only stops a throw from becoming an
        // unhandled rejection or blocking the drain below.
        console.error(`[ai-clone] task failed for chat ${chatId}:`, e)
      } finally {
        this.inFlight.delete(chatId)
        const next = this.parked.get(chatId)
        if (next) {
          this.parked.delete(chatId)
          this.submit(chatId, next)
        }
      }
    })()
  }
}
