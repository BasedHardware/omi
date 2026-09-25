import Foundation

//  **What the flow is allowed to say once asking again cannot work.**
//
//  Every permission surface in this app is a loop by construction: it names a switch, sends the user
//  to it, and polls until the answer changes. That is right while flipping the switch would change
//  the answer. It is a trap when it would not — and there is a real, shipped state where it does not.
//
//  Observed on a user's Mac on 15 August 2026, after this app was re-released under a notarized
//  Developer ID identity (team 9536L8KLMP) where it had previously been ad-hoc signed:
//
//  ```
//  tccd: Failed to match existing code requirement for subject com.omi.context-for-claude
//        and service kTCCServiceScreenCapture
//  ```
//
//  A TCC record carries the code requirement of the binary that earned it. After a re-sign the
//  daemon refuses the app against the stored requirement, while System Settings goes on rendering
//  the row from the record it still holds — so the switch reads **on**, the user grants it again,
//  and the grant is inert. Reported behaviour: several grants, a switch plainly on, and an app that
//  still could not capture. Every surface in the flow answered that by repeating itself.
//
//  So the rule this file holds is a bound on repetition, not a diagnosis: **the same dead
//  instruction is never shown a third time.** After that the surface says something new — and
//  something true whether the cause is a stale requirement or a user who simply never flipped the
//  switch, because the app cannot tell those apart from the outside and must not claim to.
//
//  The tally is persisted because one of the instructions being bounded is *reopen me*, and a
//  counter that lives in memory is a counter the remedy resets.

// MARK: - The tally

/// How many times the app has told the user to fix a capability without it taking.
///
/// A value over an injected `UserDefaults` rather than a singleton, so the whole rule can be driven
/// from a test with no shared state and no live TCC record.
struct PermissionAskLedger {
    let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// Times the app has sent the user at a switch — the prompt, the pane, a row's tap.
    func asks(_ c: Capability) -> Int { defaults.integer(forKey: Key.asks(c)) }

    /// Times the app has told the user to reopen it for this capability. Only the screen has one.
    func relaunches(_ c: Capability) -> Int { defaults.integer(forKey: Key.relaunches(c)) }

    func noteAsked(_ c: Capability) {
        let count = asks(c) + 1
        defaults.set(count, forKey: Key.asks(c))
        guard count == PermissionDeadEnd.askLimit else { return }
        // `milestone` rather than `info`: this is the line that explains why a user's surfaces
        // stopped repeating themselves, and `info` is evicted from the unified log within minutes.
        ContextLog.milestone(
            "\(c.rawValue) has been asked for \(count) times without landing — the flow stops "
                + "repeating the instruction from here",
            "permissions")
    }

    func noteRelaunched(_ c: Capability) {
        defaults.set(relaunches(c) + 1, forKey: Key.relaunches(c))
        ContextLog.milestone(
            "reopened for the \(c.rawValue) grant — if it is still refused afterwards, reopening is "
                + "not the remedy and will not be offered again",
            "permissions")
    }

    /// The capability is genuinely usable, so nothing is stuck and the tally is spent.
    ///
    /// **Not the same event as a grant appearing in TCC** — see `PermissionDeadEnd.isWorking`.
    func noteWorking(_ c: Capability) {
        guard asks(c) != 0 || relaunches(c) != 0 else { return }
        defaults.removeObject(forKey: Key.asks(c))
        defaults.removeObject(forKey: Key.relaunches(c))
    }

    private enum Key {
        static func asks(_ c: Capability) -> String { "context.permission.\(c.rawValue).fruitlessAsks" }
        static func relaunches(_ c: Capability) -> String { "context.permission.\(c.rawValue).reopens" }
    }
}

// MARK: - The rule

/// When a surface has to stop asking, and what it says instead.
///
/// Pure, and separate from the tally, for the reason every other decision in this flow is separated
/// from the machine it reads: the counting is bookkeeping, and the *bound* is the part with a wrong
/// answer available in both directions — too high and the user meets the same dead instruction
/// again, too low and a first-time user who was merely slow is told the app is broken.
enum PermissionDeadEnd {
    /// Fruitless asks before the instruction has to change. Two, so the third presentation is a
    /// different one — which is exactly the bar.
    static let askLimit = 2

    /// Reopens before the relaunch has to stop being prescribed. **One**, and lower than `askLimit`
    /// on purpose: reopening the pane again costs a click, while reopening the *app* again ends the
    /// process the user is reading the instruction in. A remedy that expensive gets one attempt.
    static let relaunchLimit = 1

    static func asksAreSpent(_ asks: Int) -> Bool { asks >= askLimit }

    /// Whether a relaunch may still be offered. Once one has been spent and the capability is still
    /// refused, the relaunch has demonstrably not helped and offering it again is the loop.
    static func mayRelaunch(after relaunches: Int) -> Bool { relaunches < relaunchLimit }

    /// **Whether `c` is genuinely usable right now**, which is what ends a tally — and is not the
    /// same question as whether TCC holds a record for it.
    ///
    /// The distinction is the whole of the relaunch loop. `CGPreflightScreenCaptureAccess()` reads
    /// **true** for a process the window server is refusing outright, so a tally cleared on the
    /// record alone would be cleared on every poll of exactly the state it exists to bound, and the
    /// "Restart to finish" button would come straight back after every restart.
    static func isWorking(_ c: Capability, granted: Bool, screenNeedsRelaunch: Bool) -> Bool {
        guard granted else { return false }
        return !(c == .screen && screenNeedsRelaunch)
    }

    /// **The sentence that replaces the instruction.**
    ///
    /// It claims nothing about *why*. The app cannot tell a stale code requirement from a user who
    /// never flipped the switch — both look identical from a preflight — so the opening reports what
    /// the app itself has done, which is the only half it can vouch for, and the remedy is written
    /// as a conditional on what the user can see.
    ///
    /// The remedy is off-and-back-on rather than on, for the reason `Permissions.staleGrantReason`
    /// gives at length: telling somebody to switch on a switch they are looking at is what turns
    /// "this needs a click" into "this app is broken". Turning it off and on is what makes macOS
    /// write the record against the signature this build actually has.
    ///
    /// **And it yields outright when `Permissions` knows more than this does.** A screen record that
    /// is unusable — this process started holding the grant and macOS refused it anyway — cannot be
    /// repaired by a switch or a reopen at all, and `ScreenBlock.recordUnusable` is the one sentence
    /// in the app that names what can. A bound on repetition that repeated a *different* dead
    /// instruction would have missed its own point.
    static func sentence(for c: Capability, reopened: Bool, screenRecordIsUnusable: Bool = false)
        -> String
    {
        if c == .screen, screenRecordIsUnusable {
            return Permissions.ScreenBlock.recordUnusable.reason
        }
        let opening =
            reopened
            ? "Reopening didn’t help."
            : "I’ve sent you there twice and macOS still won’t give it to me."
        return opening
            + " If the switch already looks on, turn it off and back on in \(c.settingsLocation), "
            + "then reopen me."
    }

    /// **The one line a glance surface adds once it has spent its asks**, or nil while asking again
    /// is still worth something.
    ///
    /// Takes its inputs as closures for the reason `MenuBarCapabilityRow` takes `isGranted` as one:
    /// every fact here is a live TCC answer or a persisted count, and the interesting claim is about
    /// the *combination* — which nothing hermetic can arrange on a real machine.
    ///
    /// - Parameter screenRecordIsUnusable: whether the screen row already has a control of its own.
    ///   `ScreenRepairControl` carries a note **and a press** for that state; this line is words with
    ///   nothing to press, so it stands down rather than saying a second thing about one row.
    static func note(
        for capabilities: [Capability],
        granted: (Capability) -> Bool,
        screenNeedsRelaunch: Bool,
        screenRecordIsUnusable: Bool = false,
        asks: (Capability) -> Int,
        relaunches: (Capability) -> Int
    ) -> String? {
        for c in capabilities {
            guard !isWorking(c, granted: granted(c), screenNeedsRelaunch: screenNeedsRelaunch) else {
                continue
            }
            if c == .screen, screenRecordIsUnusable { continue }
            let reopened = !mayRelaunch(after: relaunches(c))
            guard reopened || asksAreSpent(asks(c)) else { continue }
            return sentence(for: c, reopened: reopened)
        }
        return nil
    }
}
