import Foundation

/// Single-entry reentrancy gate for preventing overlapping async operations.
///
/// Use when two independent triggers (e.g. `didBecomeActive` + Cmd+R) can fire
/// back-to-back and would otherwise cause duplicate fetches/inserts. Call
/// `tryEnter()` at the start of the critical section — if it returns `false`,
/// another caller is already in-flight and the current caller should bail out.
/// Always pair `tryEnter()` with `exit()` via `defer` so the gate reopens even
/// on thrown errors or early returns.
///
/// Tested in `ReentrancyGateTests`.
@MainActor
final class ReentrancyGate {
    private var isInFlight = false

    /// Attempts to enter the critical section.
    /// - Returns: `true` if the caller acquired the gate (must call `exit()` when done),
    ///   `false` if another operation is already in-flight (caller should skip its work).
    func tryEnter() -> Bool {
        guard !isInFlight else { return false }
        isInFlight = true
        return true
    }

    /// Releases the gate. Safe to call even if `tryEnter()` returned `false`
    /// (no-op in that case — but callers should only `exit()` when their matching
    /// `tryEnter()` returned `true`).
    func exit() {
        isInFlight = false
    }
}
