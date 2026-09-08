import Foundation
import os

/// First-result-wins race for awaits that may never return.
///
/// `withTaskGroup` cannot bound a non-cooperative child: leaving the group
/// awaits every child, cancelled or not, so a stalled cancellation-insensitive
/// call (SCShareableContent resolution is one) blocks the caller indefinitely.
/// This race resumes on whichever branch finishes first and ABANDONS the
/// other — the loser keeps running in the background and its result is
/// dropped. Use only where an orphaned straggler is acceptable.
enum AsyncFirstResolved {
  static func run<T: Sendable>(
    _ a: @escaping @Sendable () async -> T?,
    _ b: @escaping @Sendable () async -> T?
  ) async -> T? {
    let resumed = OSAllocatedUnfairLock(initialState: false)
    return await withCheckedContinuation { continuation in
      let finish: @Sendable (T?) -> Void = { value in
        let first = resumed.withLock { state -> Bool in
          if state { return false }
          state = true
          return true
        }
        if first { continuation.resume(returning: value) }
      }
      Task { finish(await a()) }
      Task { finish(await b()) }
    }
  }
}
