import Foundation

/// Counter-based multi-holder gate for tracking in-flight persistence
/// operations. Companion to `ReentrancyGate` — that type is single-entry
/// (one holder at a time); this one allows multiple concurrent holders
/// and reports "is anything in flight right now?" via `isActive`.
///
/// Used by `ChatProvider` to prevent the cross-platform message poll
/// from running while any `saveMessage(...)` is mid-flight. The poll
/// reads backend state to detect messages sent from other devices; if
/// it fires between a local save's request and its response, it can
/// observe the just-saved message and treat it as new. The existing
/// 200-char text-prefix merge at `pollForNewMessages` catches most of
/// these, but a counter-based suppression is defense-in-depth —
/// eliminates the race window entirely instead of relying on text
/// heuristics that fail on short common replies ("Yes", "Got it").
///
/// Caller contract:
/// ```swift
/// counter.begin()
/// Task {
///     do {
///         let response = try await APIClient.shared.saveMessage(...)
///         await MainActor.run {
///             // … sync state update …
///             self.counter.end()
///         }
///     } catch {
///         await MainActor.run { self.counter.end() }
///         logError(...)
///     }
/// }
/// ```
///
/// Both success and failure paths MUST call `end()`. Missing an `end()`
/// causes the counter to leak upward and permanently suppresses the
/// poll. `end()` is no-op when the counter is already at 0, so an
/// extra (defensive) `end()` is safe but masks bugs — prefer matched
/// pairs.
///
/// Tested in `PendingSaveCounterTests`.
@MainActor
final class PendingSaveCounter {
    private var count: Int = 0

    /// Invoked each time the count returns to 0 (the last in-flight save
    /// completed). Lets the owner re-run any work that was suppressed
    /// while saves were active — e.g. a `pollForNewMessages` cycle that
    /// was deferred so it wouldn't observe a half-saved message.
    var onDrained: (() -> Void)?

    /// True when at least one save is in flight.
    var isActive: Bool { count > 0 }

    /// Visible only for tests. Production code should compare against
    /// `isActive` rather than reading the raw count.
    var currentCount: Int { count }

    /// Increment the count. Call before launching a save Task (or
    /// before `await`ing the inline save).
    func begin() {
        count += 1
    }

    /// Decrement the count. Bounded at 0 — stray calls cannot drive
    /// the counter negative, which would otherwise permanently
    /// indicate "no saves in flight" even when there are. The `assert`
    /// surfaces an unbalanced `begin()`/`end()` pair in debug builds
    /// (zero cost in release) instead of failing silently.
    func end() {
        assert(count > 0, "PendingSaveCounter: unbalanced end() — no matching begin()")
        guard count > 0 else { return }
        count -= 1
        if count == 0 { onDrained?() }
    }
}
