import Foundation

/// Single-entry reentrancy gate for preventing overlapping async operations.
///
/// Use when two independent triggers (e.g. `didBecomeActive` + Cmd+R) can fire
/// back-to-back and would otherwise cause duplicate fetches/inserts. Call
/// `tryEnter()` at the start of the critical section — if it returns `false`,
/// another caller is already in-flight and the current caller should bail out
/// **without** calling `exit()`. Only the caller that got `true` from
/// `tryEnter()` owns the gate and must release it.
///
/// The canonical usage is a `guard` + `defer` pair, which ensures `exit()` is
/// only scheduled once the guard has admitted the caller:
///
/// ```swift
/// guard gate.tryEnter() else { return }  // non-owners return here, no exit()
/// defer { gate.exit() }                  // only the owner reaches this line
/// // … critical section …
/// ```
///
/// `exit()` does not validate ownership — a stray call will reopen the gate
/// while another caller is still inside the critical section. Follow the
/// `guard`/`defer` pattern above and the contract holds.
///
/// Tested in `ReentrancyGateTests`.
@MainActor
final class ReentrancyGate {
    private var isInFlight = false

    /// Attempts to enter the critical section.
    /// - Returns: `true` if the caller acquired the gate (must call `exit()` when done),
    ///   `false` if another operation is already in-flight (caller must **not** call `exit()`).
    func tryEnter() -> Bool {
        guard !isInFlight else { return false }
        isInFlight = true
        return true
    }

    /// Releases the gate. **Caller contract:** only call this after a matching
    /// `tryEnter()` returned `true`. Calling `exit()` without ownership will
    /// reopen the gate while another caller is still inside the critical section.
    func exit() {
        isInFlight = false
    }
}
