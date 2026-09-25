import Combine
import Foundation

/// **Nothing is asked for until the user asks for it.**
///
/// The permissions card used to start `PermissionGate.run()` the instant it appeared, and the gate
/// walked every required capability back to back: microphone, then the audio of your calls, then the
/// screen, each separated by a 900 ms lead-in and a 1.1 s confirmation beat. The pacing was real —
/// it was a deliberate earlier fix — but the *sequencing* was not the user's, and that is what made
/// the card unreadable. Three system dialogs arrived over about five seconds, each one covering the
/// sentence that explained it. Reported verbatim: "the user gets no time to read what the window is
/// saying while asking for permissions … it pops up the permission before the user can even read".
///
/// A longer lead-in would not have fixed it. The problem is not how long the sentence is on screen,
/// it is that the moment was chosen by a timer rather than by the person reading. So the run is gone
/// and **a click is the only trigger**.
///
/// Every listed capability keeps its **own** `PermissionGate`, which is the same episode engine as
/// before — one hold on `PermissionBroker`, the same lead-in, the same confirmation beat, the same
/// unbounded watch on a grant made in System Settings, the same two terminal answers. A gate whose
/// `required` list is a single capability runs exactly one episode and stops, so "one at a time" is a
/// consequence of the shape rather than a rule every call site has to remember.
///
/// The alternative was a flag on the gate that made `run()` stop after the first capability. That
/// would have left the sequencing in the tree, un-run, waiting for the next person who did not read
/// this comment to switch it back on.
@MainActor
final class PermissionInvitations: ObservableObject {

    /// Every capability the card lists, in the order it lists them.
    ///
    /// **The order is load-bearing, and the screen is first.** Not for its own sake — because it is
    /// the only order in which the *Accessibility* row can be pointed at, and because it is the only
    /// order in which the optional permission stops gating the precision of the required ones.
    ///
    /// The constraint is a cycle, and naming it is most of the argument. `PermissionChoreography` has
    /// two locators. `SettingsRowLocator` walks System Settings' accessibility tree, which is
    /// hard-gated on this app being AX-trusted — so **pointing at the screen row needs Accessibility
    /// already granted**. `SettingsRowSighting` reads the row out of a screenshot of the pane, which
    /// is gated on Screen Recording — so **pointing at the Accessibility row needs the screen already
    /// granted**. Each of the two needs the other's grant. Exactly one of them has to go first with no
    /// overlay of its own; there is no third arrangement, and an ordering that pretends otherwise is
    /// an ordering that has not been checked.
    ///
    /// Accessibility used to be first, and by count that looked equal: one dark step either way. Two
    /// things break the tie, and both point the same direction.
    ///
    /// - **The optional one is the one that must be findable.** Accessibility is listed and never
    ///   required — a user who cannot find the row simply never grants it, and the app runs OCR-only
    ///   for good. A required grant is one people push through; an optional one they cannot see is one
    ///   they abandon.
    /// - **Accessibility-first makes an optional grant a precondition for three required ones.** With
    ///   it first and *skipped*, every pane after it — microphone, system audio, screen — fell back to
    ///   a boundary round the whole System Settings window, because the walk was the only locator
    ///   there was. Reported verbatim, twice, from exactly that state: *"the blue dotted line
    ///   highlight the entire settings window, not specifically the screen and system audio recording
    ///   one"*, and *"it does not give me an option to drop something in this or highlighting only the
    ///   area where the accessibility stuff is there, highlights the entire settings window."*
    ///   Screen-first removes the coupling outright: once the screen is granted the pixels are
    ///   readable, so microphone and system audio are pointed at whether or not Accessibility is ever
    ///   given.
    ///
    /// What it costs is the screen's own step, which now has neither locator and shows the boundary
    /// and the sentence. That is the bootstrap the cycle guarantees somebody has to be, it is the one
    /// step macOS itself opens with a dialog carrying an "Open System Settings" button, and it is the
    /// one the finale re-opens and re-points at (`openScreenSettingsOnce`) by which time Accessibility
    /// may well be granted.
    ///
    /// The screen grant only reaches a process that had it when it connected to the window server, so
    /// the sighting starts working after the relaunch the card already asks for — and if the user
    /// skips that relaunch, the Accessibility step degrades to precisely what it does today. The
    /// ordering can lose nothing that was working; it can only add.
    let listed: [Capability]

    /// The ones without which the app does nothing, and therefore the only ones that hold the card
    /// shut. `canLeaveStep` quantifies over exactly this list and nothing else.
    ///
    /// Accessibility is listed and deliberately not required. macOS has no dialog for it — it is a
    /// switch flipped by hand in System Settings — so gating the card on it would strand anyone
    /// unwilling to leave the flow on a step with no button that could finish it. Capture degrades to
    /// OCR-only without it: a worse product, and a working one.
    let required: [Capability]

    /// The capability whose episode is in flight, and `nil` the rest of the time.
    ///
    /// At most one, ever. `PermissionBroker` would serialise two anyway, but queueing a second ask
    /// behind the first is the *sequencing* this type exists to remove: the user would click a second
    /// row, see nothing happen, and then meet a dialog minutes later with no idea what asked for it.
    @Published private(set) var inFlight: Capability?

    /// The capabilities the user has already clicked once.
    ///
    /// What separates "Allow" from "Open Settings" on a row. TCC shows each prompt exactly once, so
    /// after the first click the pane is the only route left, and a row that still says "Allow" is a
    /// row promising a dialog that will never appear.
    @Published private(set) var offered: Set<Capability> = []

    /// The capability the user pressed last, and the only one the card may report a dead end about.
    ///
    /// Published because the sentence is drawn from it: without this the card would keep rendering
    /// the frame the press landed on.
    @Published private(set) var lastAsked: Capability?

    private let gates: [Capability: PermissionGate]
    private let granted: @MainActor (Capability) -> Bool
    private let openSettings: @MainActor (Capability) -> Void
    private let ledger: PermissionAskLedger
    private let screenRecordIsUnusable: @MainActor () -> Bool
    private let screenNeedsRelaunch: @MainActor () -> Bool
    private let relaunch: @MainActor () -> Void
    private var runs: [Capability: Task<Void, Never>] = [:]
    private var relays: [AnyCancellable] = []

    /// Everything defaults to the live path. `gate` is a factory rather than a list so a test can
    /// build the whole board over one fake `PermissionAsking` and one private broker, which is the
    /// only way the click-to-ask claims below can be asserted without touching real TCC state.
    ///
    /// The three closures are `@MainActor` because everything they can be handed is: a
    /// `PermissionGate` is main-actor isolated and so is any test double of `PermissionAsking`, and
    /// a bare `(Capability) -> …` could not call either.
    init(
        listed: [Capability] = [.screen, .accessibility, .microphone, .systemAudio],
        required: [Capability] = [.microphone, .systemAudio, .screen],
        granted: @escaping @MainActor (Capability) -> Bool = { Permissions.check($0) },
        openSettings: @escaping @MainActor (Capability) -> Void = { Permissions.openSettings(for: $0) },
        ledger: PermissionAskLedger = PermissionAskLedger(),
        screenRecordIsUnusable: @escaping @MainActor () -> Bool = {
            Permissions.screenRecordIsUnusable
        },
        // Injected for the same reason as the three above, and with more riding on it: the live one
        // terminates the process. A test that reached the real `Permissions.relaunchApp()` would not
        // fail, it would kill the test runner — so the seam is what makes the relaunch bound
        // assertable at all.
        screenNeedsRelaunch: @escaping @MainActor () -> Bool = { Permissions.screenNeedsRelaunch },
        relaunch: @escaping @MainActor () -> Void = { Permissions.relaunchApp() },
        gate: @MainActor (Capability) -> PermissionGate = { PermissionGate(required: [$0]) }
    ) {
        self.listed = listed
        self.required = required
        self.granted = granted
        self.openSettings = openSettings
        self.ledger = ledger
        self.screenRecordIsUnusable = screenRecordIsUnusable
        self.screenNeedsRelaunch = screenNeedsRelaunch
        self.relaunch = relaunch

        var built: [Capability: PermissionGate] = [:]
        for capability in listed { built[capability] = gate(capability) }
        gates = built

        // A nested `ObservableObject` does not republish through its owner on its own, and
        // everything the card draws — the caption, the status words, whether Continue is live — is a
        // gate's `@Published` state one level down. Without this relay the card would render the
        // first frame of an episode and then sit still through the whole of it.
        //
        // The sink is not `@Sendable`, so it inherits this initialiser's main-actor isolation and
        // may touch `self`. That is also why it must stay a plain closure literal here rather than
        // being moved to a method reference.
        for gate in built.values {
            gate.objectWillChange
                .sink { [weak self] _ in self?.objectWillChange.send() }
                .store(in: &relays)
        }
    }

    // MARK: - What the card draws

    /// The phase of the episode in flight, or `.idle` when the card is waiting on the user — which is
    /// now its resting state rather than a moment between two dialogs.
    var phase: PermissionGate.Phase {
        guard let inFlight, let gate = gates[inFlight] else { return .idle }
        return gate.phase
    }

    /// The capability the card is currently about, if any.
    var subject: Capability? {
        guard let inFlight else { return nil }
        return gates[inFlight]?.subject
    }

    /// The gate's own sentence for the phase it is in. `nil` when nothing is in flight, and the card
    /// says its own opening line instead.
    ///
    /// **The dead end outranks the gate**, and that is the whole of the loop fix on this card. The
    /// gate's `waitingInSettings` caption — "System Settings is open on the right row. Switch it on
    /// and I'll notice" — is correct the first time and a lie the third, because the user has
    /// switched it on and this app was not given it. See `PermissionDeadEnd`.
    var caption: String? {
        if let deadEnd { return deadEnd }
        guard let inFlight else { return nil }
        return gates[inFlight]?.caption
    }

    /// **The sentence for a capability the card has sent the user at twice with nothing to show.**
    ///
    /// Non-nil outside an episode as well as inside one, and that matters: a second click on a row
    /// the user already postponed takes `invite`'s open-the-pane branch, which sets nothing in
    /// flight — so before this the card answered a press by silently reopening a pane and saying
    /// exactly what it said before the press.
    /// **An unusable screen record reports itself on the first spent ask, not the second**, because
    /// there is nothing to wait for: `Permissions` already knows the record cannot be repaired from
    /// the pane at all, so the switch-it-off-and-on sentence would be one more dead instruction.
    var deadEnd: String? {
        guard let capability = lastAsked, !granted(capability) else { return nil }
        let unusable = capability == .screen && screenRecordIsUnusable()
        guard unusable || PermissionDeadEnd.asksAreSpent(ledger.asks(capability)) else { return nil }
        return PermissionDeadEnd.sentence(
            for: capability, reopened: false, screenRecordIsUnusable: unusable)
    }

    /// True while an episode owns the screen — the rows must not be a second entrance to it.
    ///
    /// **Except when the episode cannot end.** The screen wait polls for a grant that, once made,
    /// this process is incapable of observing — window-server capture rights are fixed at connect
    /// time — so it is the one episode with no self-terminating condition. Leaving the rows disabled
    /// through it is what made the card a dead end: the caption asks for a click that the card was
    /// refusing, over a row reading "Asking…" that had nothing left to ask. When a reopen is the only
    /// thing that can still change the answer, the row has to be the way out.
    var isBusy: Bool {
        guard let inFlight else { return false }
        if inFlight == .screen, screenNeedsRelaunch() { return false }
        return true
    }

    /// Every terminal answer, merged — **including the grants macOS was already holding before the
    /// card appeared.**
    ///
    /// A capability is answered when the system grants it, or when the user postponed it. Each gate
    /// only ever answers for its own capability, and a gate answers nothing until its row is clicked
    /// — which is the whole of the defect this shape exists for. Installing over an existing install
    /// arrives with every permission already given, so the card drew four rows reading "Granted"
    /// above a Continue button that could never enable. Reported verbatim: "it knows i have granted
    /// all these and still does not allow me to continue." The only way off the step was "I'll do
    /// these later", which would have written *Later* over three permissions the user already gave.
    ///
    /// It is folded in **here** rather than into `canLeaveStep`, because `unanswered` — and through
    /// it `deferRest` — asks the same question. Consulting the grant at the exit predicate alone
    /// would light the button up and leave the card-wide skip still stamping a deferral over a live
    /// grant, which is the same incoherence one layer down.
    ///
    /// Nothing is copied and nothing is seeded: the grant is read live through `granted`, the
    /// deferral stays the gate's own record, and each fact keeps exactly one owner. A snapshot taken
    /// when the step began would be a second copy of the grant state, wrong the moment a switch moved
    /// under it. The reads cost the same TCC preflights the card already runs on its 1.5 s tick, and
    /// a memo that can go stale is worse than repeating them.
    ///
    /// A live grant outranks a recorded deferral. Someone who postponed a row and then flipped the
    /// switch by hand has answered twice, and the answer on the machine is the later one.
    var answers: [Capability: PermissionGate.Answer] {
        var merged: [Capability: PermissionGate.Answer] = [:]
        for (capability, gate) in gates {
            merged[capability] = granted(capability) ? .granted : gate.answers[capability]
        }
        return merged
    }

    /// **The single exit predicate**, unchanged in meaning: every required capability answered, and
    /// every answer the user's — a grant they gave macOS, whenever they gave it, or a postponement
    /// they pressed a button to make. No timeout reaches this, and neither does a click.
    ///
    /// What it never required, despite reading that way for one release, is an answer *authored in
    /// this session*. The gate exists to keep a clock from answering for the user, not to make them
    /// re-give a permission they are already looking at a checkmark beside.
    var canLeaveStep: Bool {
        required.allSatisfy { answers[$0] != nil }
    }

    /// The required capabilities the system is not holding and the user has not postponed. What
    /// "I'll do these later" would defer, and the reason it can be offered as one button rather than
    /// four.
    var unanswered: [Capability] {
        required.filter { answers[$0] == nil }
    }

    /// The capability whose wait may be escaped: the gate is standing in System Settings for it.
    var postponing: Capability? {
        guard case .waitingInSettings(let capability) = phase else { return nil }
        return capability
    }

    // MARK: - The click

    /// **The only thing that starts an ask.**
    ///
    /// Three refusals, and each one is a state a click can genuinely arrive in:
    ///
    /// - Already granted. There is nothing to ask for, and re-running the episode would put a
    ///   checkmark through a beat of "Checking" for no reason.
    /// - Something else is in flight. A second dialog cannot be stacked on the first, and queueing it
    ///   would reintroduce exactly the surprise this type removes.
    /// - Already answered and still not granted. The user postponed it and has changed their mind;
    ///   TCC spends each prompt exactly once, so the pane is the only route left.
    ///
    /// Returns whether the click did anything, so the card can decline to make a noise about a press
    /// that changed nothing. A click sound over a refused click is the interface claiming to have
    /// heard something it ignored.
    @discardableResult
    func invite(_ capability: Capability) -> Bool {
        guard let gate = gates[capability], !granted(capability) else { return false }

        // **The reopen, when that is the only thing left that can work.**
        //
        // Screen Recording rights are settled when a process connects to the window server, so a
        // grant made while this card is open belongs to the next process and no amount of asking
        // will surface it here — `Permissions.screenNeedsRelaunch` is that state. Without this
        // branch the row's only behaviour was to start another episode, which reopens the pane the
        // user has already used and leaves them exactly where they were: the reported *"permission
        // is already on but it's still asking for it"*. The menu bar has offered this reopen for a
        // while; onboarding is where people actually meet the state.
        //
        // **Ahead of the `inFlight` guard, deliberately.** The screen episode never ends by itself,
        // so it is still in flight at the exact moment this is the only useful thing a click can do.
        // Testing the guard first is how the caption ends up asking for a click the card discards —
        // the same shape of bug one layer up from the one being fixed. `isBusy` opens the row for
        // this; this lets the click through once it arrives.
        //
        // **The bound is not optional, and this branch getting it wrong was worse than the bug it
        // fixes.** `screenNeedsRelaunch` is now true for any process that has merely opened the
        // pane, so without a bound a user who declines Screen Recording could restart the app
        // indefinitely — two clicks a time, forever, since `OnboardingResume` faithfully brings them
        // back to this row. The same three conditions the menu bar's row already applies
        // (`StatusView.handle`) apply here, for the same reasons written there: a reopen is spent
        // once, it is recorded so every other surface's tally agrees, and it is never offered for a
        // record no reopen can repair.
        if capability == .screen, screenNeedsRelaunch() {
            lastAsked = capability
            if !screenRecordIsUnusable(),
                PermissionDeadEnd.mayRelaunch(after: ledger.relaunches(capability))
            {
                ledger.noteRelaunched(capability)
                relaunch()
                return true
            }
            // Spent, or unusable. The pane is the honest remainder, and `deadEndNote` is what
            // explains why the reopen is no longer on offer.
            ledger.noteAsked(capability)
            openSettings(capability)
            return true
        }

        guard inFlight == nil else { return false }

        offered.insert(capability)
        // Counted here rather than where the pane is actually opened, because both branches below
        // end up at the same switch and the tally is about *asks the user was sent on*, not about
        // which of the two routes carried them. `PermissionGate.waitInSettings` opens the pane on
        // the episode branch; this call opens it directly on the other.
        lastAsked = capability
        ledger.noteAsked(capability)

        guard gate.answers[capability] == nil else {
            openSettings(capability)
            return true
        }

        inFlight = capability
        runs[capability] = Task { @MainActor [weak self] in
            await gate.run()
            guard let self, self.inFlight == capability else { return }
            self.inFlight = nil
        }
        return true
    }

    /// The escape from one capability's wait, and the only thing other than a grant that ends it.
    ///
    /// The run is cancelled as well as answered. `waitInSettings` re-asks the system on a poll, so
    /// without the cancel the phase — and with it the panel the user just pressed — would linger for
    /// up to one poll after the press, which reads as a button that did not work.
    func postpone(_ capability: Capability) {
        gates[capability]?.postpone(capability)
        runs[capability]?.cancel()
        // A postponement is an answer, so there is no longer an unmet ask to report a dead end
        // about; the card goes back to its resting line. Clicking the row again re-arms it, which is
        // the case that most needs the sentence — a second click on an answered row only reopens the
        // pane, and used to do so under copy that had not changed since the first.
        if lastAsked == capability { lastAsked = nil }
    }

    /// **The escape from the card.**
    ///
    /// Nothing is asked automatically any more, which means a user who clicks nothing at all would
    /// otherwise sit on this card forever with no answer to give: the per-capability escape only
    /// exists once an episode has reached System Settings. This is the same deliberate, named,
    /// never-automatic answer applied to everything still outstanding.
    ///
    /// Refused while an episode is in flight, because that episode has its own escape on screen and
    /// two escapes offering different scopes at once is a choice nobody can make correctly.
    func deferRest() {
        guard inFlight == nil else { return }
        for capability in unanswered {
            gates[capability]?.postpone(capability)
        }
        lastAsked = nil
    }

    /// Ends every watch. The card owns this: `waitInSettings` is unbounded by design, so leaving the
    /// step is the only thing that can stop it.
    func cancel() {
        for task in runs.values { task.cancel() }
        runs.removeAll()
        inFlight = nil
    }
}
