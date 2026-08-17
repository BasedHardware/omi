import AppKit
import Combine
import SwiftUI

// MARK: - The flow

/// The cards, in the order they are visited: welcome, what I do, whose account this is, what I need,
/// who I tell, and how it works.
///
/// A value rather than a private enum inside the view, because the ordering is the part of onboarding
/// with wrong answers available — a permission asked before the account it lands in, a back button
/// that walks into a consent flow that has already run — and none of that is testable from inside a
/// `View`.
///
/// The order changed deliberately. Registering the Claude connector used to come first, on the
/// reasoning that the first product action should be the one that makes Claude useful. That is a good
/// argument for a different app: everything this one records lands in an Omi account, and the
/// permissions are what start the recording, so the account has to be known *before* macOS is asked
/// for a microphone. The connector is local configuration and can be done at any point; consent
/// cannot. `docs/first-run-experience.md` (Phase 4) is the spec this follows.
enum OnboardingStep: Int, CaseIterable, Sendable {
    case welcome, value, signIn, permissions, connector, tutorial, done

    /// The cards this run will actually visit.
    ///
    /// Sign-in drops out when a session was restored, which is what keeps a reinstall one click —
    /// `Engine.start()` has already called `OmiAuth.restore()` by the time this window is presented,
    /// so a returning user arrives here already known.
    static func itinerary(signedIn: Bool) -> [OnboardingStep] {
        allCases.filter { step in
            step == .signIn ? !signedIn : true
        }
    }

    /// The next card, or nil at the end. Nil at `.done` is what makes "the flow is over" a fact about
    /// the machine rather than a convention every call site has to remember.
    ///
    /// The itinerary is recomputed on every call, so it can change *while the user is standing on a
    /// card* — and one card deletes itself by succeeding. `.signIn` is on the itinerary only while
    /// `signedIn` is false, and the moment it does its job that becomes true, so the very call that
    /// asks "where does a completed sign-in go" asks it of an itinerary `.signIn` is no longer on.
    /// Answering nil there meant "the flow is over", which returned the user to the card they had
    /// just finished. A step that has dropped out is not the end of the flow: hand it the first card
    /// that still comes after it.
    static func next(after step: OnboardingStep, signedIn: Bool) -> OnboardingStep? {
        let itinerary = itinerary(signedIn: signedIn)
        guard let index = itinerary.firstIndex(of: step) else {
            // `allCases` order *is* itinerary order, and `itinerary` only filters, so the first
            // remaining card of higher rank is the one that would have followed this step.
            return itinerary.first { $0.rawValue > step.rawValue }
        }
        guard index + 1 < itinerary.count else { return nil }
        return itinerary[index + 1]
    }

    /// Where back goes, and nil where it must not exist.
    ///
    /// Back is offered only while nothing irreversible has happened. From `.permissions` onward there
    /// is nothing to go back to: TCC has been asked and will not un-ask, macOS shows each prompt
    /// exactly once, and a "back" that walked into a completed consent run would put up a card that
    /// cannot do anything. Offering a button that cannot work is worse than not offering one.
    static func back(from step: OnboardingStep, signedIn: Bool) -> OnboardingStep? {
        switch step {
        case .welcome, .permissions, .connector, .tutorial, .done: return nil
        case .value: return .welcome
        case .signIn: return signedIn ? nil : .value
        }
    }

    /// The cards a progress dot stands for.
    ///
    /// Not the whole itinerary: the welcome card is before the flow starts and `.done` is after it
    /// ends, and a progress indicator on either is counting something the user is not doing.
    static func progressSteps(signedIn: Bool) -> [OnboardingStep] {
        itinerary(signedIn: signedIn).filter { $0 != .welcome && $0 != .done }
    }

    /// Which dot is lit, or nil on a card that has none.
    static func progressIndex(of step: OnboardingStep, signedIn: Bool) -> Int? {
        progressSteps(signedIn: signedIn).firstIndex(of: step)
    }

    /// **A recorded card, corrected to the itinerary the run actually has.**
    ///
    /// `OnboardingResume` records a card, and the itinerary is recomputed on every launch from a fact
    /// the record knows nothing about: whether a session was restored. So the two can disagree, and
    /// the disagreement has exactly one shape — a run that recorded `.signIn` and came back to a
    /// process that had already restored an account. Opening on that card asks somebody who is signed
    /// in to sign in again, under a progress band with no lit dot (`.signIn` is not on the itinerary
    /// to be indexed in) and a back arrow that is refused. Nothing is broken; the card is simply not
    /// one this run has.
    ///
    /// The correction is the same rule `next(after:)` already applies to a step that dropped out
    /// mid-run: hand back the first card that still comes after it. `.done` is the floor, because a
    /// resume point past every remaining card is a run that finished.
    static func resumed(_ step: OnboardingStep, signedIn: Bool) -> OnboardingStep {
        let itinerary = itinerary(signedIn: signedIn)
        guard !itinerary.contains(step) else { return step }
        return itinerary.first { $0.rawValue > step.rawValue } ?? .done
    }
}

// MARK: - The last card, as a value

/// **What the closing card does on arrival and offers to be pressed**, given the state the run
/// finished in.
///
/// A value rather than three `if`s inside a `View`, because this is where the flow's one hard
/// stranding lived and a `private var` on a `View` is not something a test can hold — the same
/// argument `OnboardingStep` and `homeLine(chord:)` are hoisted on.
///
/// The stranding: the ungranted card offered "Open Screen Recording" and nothing else, on every
/// ungranted run. That is the right control for somebody who has not answered the screen row yet and
/// a trap for somebody who answered "I'll do this later" — `finish()` deliberately does not reopen
/// the pane over a deliberate deferral, so the watch that notices a grant was never armed either, so
/// nothing on the card could change its own state. No grant, no "Done", and a borderless window with
/// no Dock icon behind it: the flow was over and its last screen could not be closed.
///
/// Two separate facts came out of that, and they are separate fields here for the same reason:
/// *whether to watch* is about the card being able to stop being wrong, and *whether to open the
/// pane* is about not taking back an answer the user gave.
struct OnboardingFinale: Equatable {
    /// The one control on the card. There is always exactly one, because a final screen with no
    /// control is a screen that has to close on a timer.
    enum Action: Equatable {
        /// The grant is missing and undecided: the route to the pane.
        case openScreenRecording
        /// Granted, but this process was not holding it when it connected to the window server.
        case restart
        /// Nothing left to do here.
        case close
    }

    var action: Action
    /// Whether to poll TCC for the grant. **Whenever it is missing**, however it came to be missing:
    /// a card that cannot notice a grant is a card that cannot stop being wrong.
    var watchesForTheGrant: Bool
    /// Whether to open the pane and point at the row. Never over somebody who said later.
    var opensThePane: Bool
    /// Whether the closing beat — the ring on the real status item, under the line naming it —
    /// belongs on this arrival. It does whenever the run is genuinely over, which a deliberate
    /// deferral is and a run still waiting on a switch is not.
    var ringsTheMenuBar: Bool
    /// **Whether this card has already said its piece and been ignored by the machine.**
    ///
    /// The second stranding, and the one the postponed fix did not reach: an undecided run is sent
    /// to the pane with *no other button on the card*, so a user whose grant does not take — the
    /// stale-code-requirement state `PermissionDeadEnd` documents — presses "Open Screen Recording",
    /// flips a switch that is already on, comes back to the identical card, and presses it again.
    /// Nothing about the flow bounds that, and there is no door.
    ///
    /// When it is set the card stops asking: the action becomes the door, the pane is not reopened,
    /// and the copy says what the app actually knows instead of repeating the instruction.
    var askIsSpent: Bool = false

    /// - Parameters:
    ///   - askIsSpent: the pane has been opened for the screen grant `PermissionDeadEnd.askLimit`
    ///     times and it still has not landed.
    ///   - relaunchIsSpent: the app has already been reopened for this grant and is still refused,
    ///     so "Restart to finish" is an instruction that has demonstrably failed for this user.
    ///   - screenRecordIsUnusable: `Permissions.ScreenBlock.recordUnusable` — this process started
    ///     holding the grant and macOS refused it anyway. Reopening is known *in advance* not to
    ///     help, so the restart is withheld on the first press rather than the second: window-server
    ///     capture rights are settled at connection time, and the successor connects the same way.
    static func of(
        screenGranted: Bool, needsRelaunch: Bool, screenWasPostponed: Bool,
        askIsSpent: Bool = false, relaunchIsSpent: Bool = false,
        screenRecordIsUnusable: Bool = false
    ) -> OnboardingFinale {
        guard screenGranted else {
            // Two different reasons the card is done asking, and they want the same card: an answer
            // the user gave on purpose, and an ask this app has spent. Both leave the watch armed —
            // a switch flipped by hand still has to reach the card — and neither reopens the pane.
            let settled = screenWasPostponed || askIsSpent
            return OnboardingFinale(
                action: settled ? .close : .openScreenRecording,
                watchesForTheGrant: true,
                opensThePane: !settled,
                ringsTheMenuBar: settled,
                askIsSpent: askIsSpent)
        }
        let restartCannotHelp = relaunchIsSpent || screenRecordIsUnusable
        let restartWouldRepeat = needsRelaunch && restartCannotHelp
        return OnboardingFinale(
            action: needsRelaunch && !restartCannotHelp ? .restart : .close,
            watchesForTheGrant: false,
            opensThePane: false,
            ringsTheMenuBar: true,
            askIsSpent: restartWouldRepeat)
    }
}

// MARK: - The view

/// Six screens, one thought each, and the choreography that gets the permissions granted.
///
/// `@MainActor` on the whole view, not on the handful of members that read `OmiAuth`: `body` is
/// already main-actor isolated, so every computed screen and every step function is reached from
/// the main actor anyway, and annotating them one at a time only invites the next one to be missed.
@MainActor
struct OnboardingView: View {
    /// Where the tutorial takes over (`docs/first-run-experience.md`, Phase 6). Nil until that
    /// surface exists, and a nil handoff finishes the flow rather than dead-ending on a button that
    /// does nothing — onboarding is never blocked by a piece of it that is not there.
    var onTutorial: (() -> Void)?

    init(onTutorial: (() -> Void)? = nil) {
        self.onTutorial = onTutorial
    }

    /// The rows, in the order the card lists them: screen, Accessibility, microphone, system audio.
    ///
    /// **The order and the reason for it are `PermissionInvitations.listed`'s**, and this deliberately
    /// does not restate either. It used to — "microphone first because it is the one people expect" —
    /// and that sentence outlived the ordering it described by a whole rewrite: the screen went first
    /// so that granting it makes every later pane's row findable, which is an argument about two
    /// locators needing each other's grant and cannot be summarised here without going stale again.
    /// One owner for the order, one owner for the required subset `canLeaveStep` quantifies over.
    private var capabilities: [Capability] { invitations.listed }

    /// Owned by the auth layer, observed here. Everything Context for Claude records lands in this
    /// account, so the step machine asks it who the user is before it asks macOS for a microphone.
    @ObservedObject private var auth = OmiAuth.shared

    /// The probe opens straight onto the permissions card.
    ///
    /// Not a shortcut for its own sake: the choreography sits behind sign-in, and the account state of
    /// the machine a build is being checked on is not something a self-test should have to change. It
    /// only ever *skips forward past* cards, and only when the environment variable is set.
    /// A relaunch mid-flow resumes on the card it left; only a genuine first run starts at
    /// `.welcome`. See `OnboardingResume` for why that record has to exist at all — granting Screen
    /// Recording ends this process *by design*, so "the app restarted" is an ordinary event in the
    /// middle of onboarding rather than a crash to recover from.
    ///
    /// A resumed card is put through `OnboardingStep.resumed` rather than opened as recorded: the
    /// itinerary is recomputed from this launch's account state, and a card that has dropped off it
    /// is not one this run can stand on.
    @State private var step: OnboardingStep = openingStep(
        probe: PermissionChoreography.probedCapability,
        resume: OnboardingResume().step,
        signedIn: OmiAuth.shared.isSignedIn)

    /// The card this run opens on. Hoisted out of the `@State` default for the same reason
    /// `OnboardingStep` is hoisted out of the view: it has a wrong answer available in three
    /// directions — the probe, a fresh install, and a resume point the itinerary no longer holds —
    /// and none of them can be asserted from inside a `View`.
    nonisolated static func openingStep(
        probe: Capability?, resume: OnboardingStep?, signedIn: Bool
    ) -> OnboardingStep {
        guard probe == nil else { return .permissions }
        guard let resume else { return .welcome }
        return OnboardingStep.resumed(resume, signedIn: signedIn)
    }

    /// Who asks, when the user says to, and who decides whether this card may be left. Not the view,
    /// and not a clock: an answer is terminal only when the user authored it — a grant, or an
    /// explicit "I'll do this later".
    @StateObject private var invitations = PermissionInvitations()

    @State private var granted: [Capability: Bool] = [:]
    @State private var reported = false
    @State private var needsRelaunch = false
    /// Whether System Settings is the app the user is looking at. The card steps aside for the pane
    /// it opened and comes straight back when the pane is not what they are reading — this app has no
    /// Dock icon, so a card hidden on a phase alone would be a card with no way back.
    @State private var settingsIsFrontmost = false

    @State private var connectorSurfaces: Set<ClaudeSurface> = []
    @State private var connectorMessage: String?
    @State private var configuringConnector = false
    @State private var modelProgress: Double?
    @State private var warmingModels = false

    @State private var openedScreenSettings = false
    /// How many times this install has been sent at the Screen Recording switch, and how many times
    /// it has been told to reopen the app for it. Read from `PermissionAskLedger`; see
    /// `readAskLedger()` for why the card keeps a copy.
    @State private var screenAsks = 0
    @State private var screenReopens = 0
    /// `Permissions.ScreenBlock.recordUnusable`: the grant is on, this process started holding it,
    /// and macOS refused it anyway. Read on the same poll as the grants — it is a fact about *this*
    /// process, so it can only become true while the app is running.
    @State private var screenRecordIsUnusable = false
    /// The finale's grant watch. Held so it can be ended: it is an unbounded poll and the card
    /// closing is what owns its end.
    @State private var screenWatch: Task<Void, Never>?
    @State private var cueDrift = false
    @State private var finale = false

    /// The capability the overlay is currently pointing at on the gate's behalf. See `syncSpotlight`.
    @State private var spotlit: Capability?
    @State private var spotlightTask: Task<Void, Never>?

    /// Whatever the sign-in attempt threw, shown as-is. A preamble in front of it would be a
    /// sentence that says nothing the error does not.
    @State private var signInError: String?
    /// The user pressed Cancel while the browser round trip was still open. There is no way to
    /// call the round trip off — the browser has it — so this only puts the buttons back.
    @State private var abandonedWait = false

    /// The card, and nothing under it.
    ///
    /// There was a `Backdrop` here — a near-opaque sheet with a nine-blob wash drifting over it — and
    /// it is gone rather than moved. The window is frosted glass now (`InkGlass`), so the
    /// ground already has depth and already picks up the desktop; a blob field on top of it would be
    /// a second ground competing with the first, which is exactly the "ugly hue" the sheet was
    /// reported as. One ground, owned by the window, and the card draws only type.
    var body: some View {
        GeometryReader { geometry in
            // The dots are laid out *under* the column, not over it. They were an
            // `.overlay(alignment: .bottom)` on the full card with 62 pt of bottom padding, which is
            // a position and not a reservation: the permissions column is taller than 62 pt from the
            // foot leaves room for, so the dots landed inside the fourth permission row, over the
            // consequence line beside "I'll do this later", and — invisibly, `Ink.primary` on a
            // near-black pill — on top of "Show me the row". A `VStack` is the whole fix: the band
            // is subtracted from the height the column is offered, so there is nothing for the dots
            // to collide with. `InkLayout.progressBandHeight` is the same subtraction the layout
            // tests measure against.
            VStack(spacing: 0) {
                ZStack(alignment: .topTrailing) {
                    column
                        .id(step)
                        .transition(transition(in: geometry.size))

                    if step == .done {
                        menuBarCue
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                progressBand
            }
            .overlay(alignment: .topLeading) { backCue }
            .frame(width: geometry.size.width, height: geometry.size.height)
            .overlay {
                if finale {
                    edgeGlow(in: geometry.size)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // `Engine.start()` has already called `OmiAuth.restore()` by the time this window is
        // presented, so a reinstall arrives here knowing whose account it is. Nothing restores it a
        // second time here — observing `auth` covers a session that lands late anyway.
        .onAppear { beginStep() }
        // The card floats over everything, so any moment the user has to click something *else* —
        // the Google account chooser, a TCC prompt, the Screen Recording pane — it takes itself off
        // screen rather than being an obstacle to work around.
        .onChange(of: yieldsScreen) { _, yields in OnboardingWindow.setHidden(yields) }
    }

    /// True whenever the next thing the user must click belongs to another app.
    ///
    /// It used to be true from the instant the run decided to ask — which is *before* the 900 ms
    /// lead-in the card exists to be read during, so the preamble explaining what macOS was about to
    /// ask for was on screen for roughly zero frames and the card blinked out three times. The gate's
    /// phase is what answers this now: only a dialog genuinely being up, or the user genuinely
    /// standing in System Settings. Every route to a prompt goes through an invitation, so there is
    /// one phase to consult rather than a phase plus a set of hand-tapped rows plus a `guiding` flag.
    private var yieldsScreen: Bool {
        if auth.isSigningIn { return true }
        if PermissionGate.cardYields(to: invitations.phase, settingsIsFrontmost: settingsIsFrontmost) {
            return true
        }
        // The Screen Recording grant happens entirely in System Settings, and the app relaunches
        // itself the moment it lands — there is nothing here worth covering it for.
        if step == .done, !isGranted(.screen), openedScreenSettings { return true }
        return false
    }

    private var column: some View {
        content
            .frame(maxWidth: columnWidth, alignment: columnAlignment)
            .padding(.horizontal, InkLayout.pagePaddingHorizontal)
            .padding(.vertical, InkLayout.pagePaddingVertical)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome: welcome
        case .value: value
        case .signIn: signIn
        case .permissions: permissions
        case .connector: connector
        case .tutorial: tutorial
        case .done: done
        }
    }

    // MARK: - 1. Welcome

    private var welcome: some View {
        VStack(spacing: 24) {
            says(Self.welcomeLead, style: .introHero)

            // Live on the first frame. It used to wait out the word-by-word reveal — 1200 ms of a
            // button drawn at zero opacity — on the theory that offering it mid-sentence invites a
            // click before the sentence is read. But a reader who is ready is the only judge of
            // that, and hiding the control does not make them read; it makes them wait.
            InkButton("Turn me on") { advance() }
        }
    }

    /// The first line anyone ever sees, set in the largest role in the system.
    ///
    /// A named value rather than a literal inside `welcome`, because it is the widest thing the
    /// reading column is ever asked to hold and the one card that has actually overflowed: the fit
    /// test measures *this*, so it cannot pass against a copy of the copy that has since drifted.
    static let welcomeLead: [(String, Emphasis)] = [
        ("I keep ", .plain),
        ("Claude", .bold),
        (" caught up on what you ", .plain),
        ("see and say", .bold),
        (".", .plain),
    ]

    /// The card's own words, said by the mark.
    ///
    /// Every card with a headline goes through here, which is the point: the copy has always been
    /// written in the mark's first person — "I keep Claude caught up", "Here's what I do", "I'm
    /// listening" — and a character that speaks on one screen and vanishes on the next is a
    /// flourish rather than a character. One call site shape, one character, the whole flow.
    ///
    /// The words arriving *are* this card's entrance. That is the only thing on a card that is still
    /// timed, and it is timed because it is an animation rather than a gate: no button waits on it,
    /// and `SpokenCadence.maximumPhrase` caps a phrase at the duration the welcome hero already took.
    private func says(
        _ lead: [(String, Emphasis)],
        style: InkTextStyle,
        aside: String? = nil
    ) -> some View {
        TalkingMark(lead: lead, leadStyle: style, aside: aside)
    }

    // MARK: - 2. What I do — said before anything is asked for

    /// The three sources, then where it all goes. Plain sentences rather than a feature list,
    /// because the honest version of this screen is short and a padded one reads as a pitch.
    ///
    /// The destination line is the one that has to be here and not later: the next screen asks for
    /// an account, and a user who has not been told what leaves the machine cannot meaningfully
    /// agree to it.
    private var value: some View {
        VStack(alignment: .leading, spacing: 16) {
            says(
                [("Here's what I do.", .plain)],
                style: .firstTitle,
                aside: "Three things I take in, and one place they go.")

            // The list and the button are here from the first frame. They used to fade in behind
            // the mark on a 340 ms timer; the mark still speaks first, because its own text
            // animates, but nothing the user can press is waiting on a clock.
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 9) {
                    ForEach(Self.valueClaims, id: \.copy) { claim in
                        Label {
                            Text(claim.copy)
                                .inkStyle(.rowCopy)
                                .foregroundStyle(Ink.primary)
                                .fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: claim.glyph)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(Ink.secondary)
                                .frame(width: 16)
                        }
                        .labelStyle(.titleAndIcon)
                    }
                }

                InkButton("Continue") { advance() }
                    .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The three claims, each one a thing the app genuinely does — two sources and the destination.
    ///
    /// Written as claims rather than features because every one of them is something the user is about
    /// to be asked to allow, and the ask is only meaningful if it was described first. The destination
    /// line is the one that has to be here and not later: the next card asks for an account, and a
    /// user who has not been told what leaves the machine cannot meaningfully agree to it.
    ///
    /// **The destination line names both readers**, and it did not always. It said "and Claude reads it
    /// from there", which was the whole truth back when every retrieval surface in the product was
    /// Claude over MCP. It is not now: the account is also where the app's own Activity panel reads
    /// conversations, memories and tasks back from, so a user consenting on the strength of that line
    /// was being told about one of the two things their account is for.
    private static let valueClaims: [(glyph: String, copy: String)] = [
        ("rectangle.on.rectangle", "I watch your screen — the frames, and the text in your windows."),
        ("waveform", "I listen — your microphone, and the audio of your calls."),
        ("lock", "It lands in your Omi account, and you and Claude both read it back from there."),
    ]

    // MARK: - 3. Sign in — before anything is recorded, not after

    /// The one screen with a real choice on it. It exists because everything Context for Claude hears
    /// lands in an Omi account, and starting to record before knowing which account that is would be
    /// wrong. The OAuth round trip is untouched from the version that shipped; only the card around
    /// it changed.
    private var signIn: some View {
        VStack(spacing: 14) {
            says(
                [("Which account is this?", .plain)],
                style: .stepHeadline,
                aside: "It all lands in your Omi account.")

            if isWaitingForBrowser {
                VStack(spacing: 12) {
                    Text("Waiting for your browser…")
                        .inkStyle(.statusLabel)
                        .foregroundStyle(Ink.secondary)

                    InkButton("Cancel", kind: .secondary) { abandonedWait = true }
                }
                .padding(.top, 4)
            } else {
                if let signInError {
                    Text(signInError)
                        .inkStyle(.rowCopy)
                        .foregroundStyle(Ink.errorRed)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 12) {
                    InkButton("Continue with Google") { beginSignIn(with: .google) }
                    InkButton("Continue with Apple", kind: .secondary) { beginSignIn(with: .apple) }
                }
                .padding(.top, 4)
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
        .animation(stepAnimation, value: isWaitingForBrowser)
    }

    /// The buttons are gone only while the round trip is genuinely open and the user has not asked
    /// for them back.
    private var isWaitingForBrowser: Bool {
        auth.isSigningIn && !abandonedWait
    }

    /// Opens the browser and waits. A press while a round trip is already open cannot start a
    /// second one — it puts the waiting line back, which is the only honest answer to it.
    private func beginSignIn(with provider: OmiAuthProvider) {
        signInError = nil
        abandonedWait = false
        guard !auth.isSigningIn else { return }

        Task { @MainActor in
            do {
                try await auth.signIn(provider: provider)
                guard step == .signIn else { return }
                advance()
            } catch {
                guard step == .signIn else { return }
                signInError = error.localizedDescription
            }
        }
    }

    // MARK: - 4. Permissions — one at a time, and never before the user says so

    private var permissions: some View {
        PermissionsCard(
            title: setupTitle,
            preamble: setupPreamble,
            rows: permissionRows,
            rowsDisabled: invitations.isBusy,
            postponing: invitations.postponing,
            canContinue: invitations.canLeaveStep,
            // The click is the whole interaction now, so it gets the app's click — but only when it
            // did something. A sound over a press the board refused is the card claiming to have
            // heard something it ignored.
            onRow: { if invitations.invite($0) { Sound.effect(.click) } },
            onPostpone: { invitations.postpone($0) },
            onContinue: { leavePermissions() },
            onDeferRest: { deferTheRest() }
        )
        // The watch is unbounded on purpose, so it needs an owner that ends it. Leaving the card is
        // that owner — and the card can only be left once every required capability is answered.
        .onDisappear {
            invitations.cancel()
            // The overlay is a window over another application. It outlives this view unless
            // something takes it down, and a spotlight left pointing at System Settings after
            // onboarding has moved on is worse than one that never appeared.
            spotlightTask?.cancel()
            spotlit = nil
            PermissionOverlay.hide()
        }
        // **The gate's wait is what the spotlight is for.** Every other route to the overlay is a
        // special case; this is the one every capability takes once its pane is open — which now
        // includes the one macOS never prompts for, because a click on its row runs the same episode.
        .onChange(of: invitations.phase, initial: true) { _, phase in syncSpotlight(to: phase) }
        .onReceive(permissionTick) { _ in
            refreshPermissions()
            // **Polled as well as observed, because the notification does not cover the case that
            // matters.** `didActivateApplicationNotification` fires on a *change* of frontmost app,
            // so when System Settings is already frontmost and the pane is reopened underneath the
            // card — the second capability in the sequence, or the re-click path — macOS posts
            // nothing and this flag keeps whatever it last held. That is the state the card floats
            // over the pane in, and it is the reported one. The poll is already running for grant
            // detection and this is the same kind of fact: something only the user can cause, that
            // the system will not announce.
            settingsIsFrontmost = Permissions.systemSettingsIsFrontmost
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissions()
        }
        .onReceive(
            NSWorkspace.shared.notificationCenter.publisher(
                for: NSWorkspace.didActivateApplicationNotification)
        ) { _ in
            settingsIsFrontmost = Permissions.systemSettingsIsFrontmost
        }
    }

    /// The four rows, as the card draws them. The card owns the drawing; this owns the state.
    private var permissionRows: [PermissionsCardRow] {
        capabilities.map {
            PermissionsCardRow(capability: $0, granted: isGranted($0), status: status(for: $0))
        }
    }

    /// One subscription for the life of the view, not a fresh publisher on every body pass.
    /// `permissions` is a computed property, so a `Timer.publish(…)` written inline there built a new
    /// `TimerPublisher` every time the card re-rendered — and this card re-renders on model-download
    /// progress. Matches `StatusView`'s own pattern.
    ///
    /// It is spelled through `Permissions.grantWatchPollSeconds` rather than a bare `1.5` so it is
    /// visibly the *permitted* kind of clock: it detects a switch the user flipped in System Settings,
    /// and all it may do on noticing is redraw the rows. `refreshPermissions` deliberately does not
    /// advance the card — see the note there.
    private let permissionTick = Timer
        .publish(every: Permissions.grantWatchPollSeconds, on: .main, in: .common)
        .autoconnect()

    /// What is about to happen, in the order it happens, before any of it happens.
    ///
    /// Standing still it is an instruction; mid-episode it is the gate's caption for the phase.
    ///
    /// **One sentence.** It carried three, explaining that macOS asks separately, that we take them
    /// one at a time, and that Accessibility has no dialog. All true, all unread: the four rows below
    /// already say what each permission is, and a paragraph above them is a wall to get past rather
    /// than a thing anyone reads. Reported as "don't explain so much."
    ///
    /// What survives is the only claim the rows cannot make for themselves — that the card is waiting
    /// on the reader rather than the other way round. Accessibility's missing dialog is no longer
    /// pre-announced; its own row says "Open Settings", which is the same fact delivered at the moment
    /// it matters instead of three rows early.
    private var setupPreamble: String {
        // The gate says where the episode is, including the sentence that has to be on screen while
        // the user is standing in System Settings deciding.
        if let caption = invitations.caption { return caption }
        return "Click one when you’re ready. Nothing is asked until you do."
    }

    private var setupTitle: String {
        // "First…" only survives for a run that never signed in; once the account is known, the
        // permissions are no longer the first thing being asked for.
        guard invitations.isBusy else {
            if auth.isSignedIn {
                return HostArchitecture.usesLocalSTT
                    ? "Now the permissions."
                    : "Now the permissions — transcripts use your Omi account."
            }
            return "First…"
        }
        return "Say yes."
    }

    // MARK: The choreography

    /// Opens the pane and holds the overlay up for `CONTEXT_CHOREOGRAPHY_PROBE`.
    ///
    /// The probe exists because the choreography is the hardest thing here to see: it needs a
    /// capability that is *not* granted, on a machine where checking a build means all of them are.
    /// So it forces the pane open and points, with no grant to wait for — the positioning is the
    /// whole of what is being checked, and it stays up until the card is dismissed by hand.
    ///
    /// It is the one path on this card that opens a pane without a click, and it can only ever
    /// *show* the overlay: the grant still has to be given by hand, exactly as it would be otherwise.
    private func probeChoreography(_ capability: Capability) {
        Task { @MainActor in
            // Through the door, like every other pane in the app. This is the call site that was
            // observed stomping the Screen Recording pane the user had just been sent to, 1.9 s
            // after they tapped the row that opened it.
            await PermissionBroker.shared.openSettings(for: capability)
            // System Settings has to be up before there is anything to find. Waiting for it to come
            // forward, rather than sleeping a fixed 1200 ms and hoping, is what keeps the overlay off
            // the previous pane's rows on a cold launch.
            await Permissions.waitForSettingsFrontmost()
            guard step == .permissions else { return }
            PermissionOverlay.show(
                for: capability,
                caption: "Switch on \(PermissionChoreography.appDisplayName).")
        }
    }

    /// **Points at the row for whichever capability the gate is standing in System Settings for.**
    ///
    /// The gate's own `waitingInSettings` phase is what drives this, and that is the fix: the
    /// spotlight used to be reachable only from a "Show me the row" button offered for Accessibility
    /// alone, and from the finale. Every other capability reached System Settings through
    /// `PermissionGate.waitInSettings`, which opens the pane and polls and never asked for an overlay
    /// at all. `PermissionGate.spotlightSubject` is the predicate; this is only the wiring, and it is
    /// deliberately the *only* wiring, so there is one answer to "should something be pointing right
    /// now" rather than one per call site.
    ///
    /// It is also what makes the showing **automatic**. There is no longer a button on our card that
    /// asks permission to point at System Settings — a card asking to be allowed to help is one more
    /// thing to read and dismiss before the actual instruction. The pane opening is the trigger.
    private func syncSpotlight(to phase: PermissionGate.Phase) {
        let subject = PermissionGate.spotlightSubject(of: phase)
        guard subject != spotlit else { return }
        let previous = spotlit
        spotlit = subject
        spotlightTask?.cancel()
        spotlightTask = nil

        guard let subject else {
            guard previous != nil else { return }
            // A grant that landed gets its confirmation witnessed on the overlay — the user sees the
            // thing they just did register. Anything else takes it straight down.
            if case .confirming = phase {
                PermissionOverlay.confirmGranted()
            } else {
                PermissionOverlay.hide()
            }
            return
        }

        spotlightTask = Task { @MainActor in
            // The pane has to be up before there is anything to find. Pointing before it exists is
            // how an overlay ends up ringing the last pane's rows — the same reason the probe waits,
            // and now the same condition rather than the same guessed duration.
            await Permissions.waitForSettingsFrontmost()
            guard !Task.isCancelled, spotlit == subject else { return }
            PermissionOverlay.show(
                for: subject,
                caption: "Switch on \(PermissionChoreography.appDisplayName).")
        }
    }

    // MARK: - 5. Claude connector

    /// Local configuration, after consent rather than before it. The registration itself is
    /// untouched — only the card around it moved and was restyled.
    private var connector: some View {
        let copy = OnboardingConnectorCopy(surfaces: connectorSurfaces)
        return VStack(alignment: .leading, spacing: 18) {
            says([(copy.title, .plain)], style: .firstTitle, aside: copy.detail)

            VStack(alignment: .leading, spacing: 18) {
                if let connectorMessage {
                    Text(connectorMessage)
                        .inkStyle(.statusLabel)
                        .foregroundStyle(Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 12) {
                    InkButton(configuringConnector ? "Setting up…" : copy.action) { configureConnectorOrContinue() }
                        .disabled(configuringConnector)
                    if connectorMessage != nil, connectorSurfaces.isEmpty {
                        InkButton("Continue without Claude", kind: .secondary) { advance() }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func configureConnectorOrContinue() {
        guard connectorSurfaces.isEmpty else {
            advance()
            return
        }
        guard !configuringConnector else { return }
        configuringConnector = true
        Task { @MainActor in
            let result = await Task.detached(priority: .userInitiated) { ClaudeRegistrar.register() }.value
            connectorSurfaces = configuredSurfaces(from: result)
            connectorMessage = connectorSurfaces.isEmpty
                ? "No local Claude configuration was changed. You can continue and connect it later."
                : "The connector was configured locally. It will be available when you open Claude."
            configuringConnector = false
        }
    }

    private func configuredSurfaces(from result: ClaudeRegistrar.Result) -> Set<ClaudeSurface> {
        configuredSurfaces(claudeCode: result.claudeCode, claudeDesktop: result.claudeDesktop)
    }

    private func configuredSurfaces(claudeCode: Bool, claudeDesktop: Bool) -> Set<ClaudeSurface> {
        var surfaces: Set<ClaudeSurface> = []
        if claudeCode { surfaces.insert(.claudeCode) }
        if claudeDesktop { surfaces.insert(.claudeDesktop) }
        return surfaces
    }

    private func refreshConnectorStatus() {
        Task { @MainActor in
            let status = await Task.detached(priority: .utility) { ClaudeRegistrar.status() }.value
            guard step == .connector else { return }
            connectorSurfaces = configuredSurfaces(
                claudeCode: status.claudeCode, claudeDesktop: status.claudeDesktop)
        }
    }

    // MARK: - 6. Tutorial intro

    /// The handoff card. It offers the tutorial and nothing else, because the tutorial itself is a
    /// separate surface — and until that surface exists both buttons finish the flow, so a missing
    /// piece of the product cannot strand anyone on a card with no way out.
    ///
    /// **The aside describes the walkthrough that exists.** It promised "a minute, and it ends with
    /// Claude answering a question about your own screen" — written when the tutorial was a short
    /// hop from a captured page straight into Claude. `TutorialStep.flow` is eleven beats now, and the
    /// middle of it is this app's own surfaces: the chord, the timeline, the search panel. A card that
    /// under-describes what it is about to start is a card people press "Not now" on.
    private var tutorial: some View {
        VStack(alignment: .leading, spacing: 18) {
            says(
                [("Want to see it work?", .plain)],
                style: .firstTitle,
                aside: "A few minutes. You’ll open my window, travel back through your own screen, "
                    + "and finish with Claude answering a question about it.")

            HStack(spacing: 12) {
                InkButton("Show me") { startTutorial() }
                InkButton("Not now", kind: .secondary) { advance() }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// **"Show me" is an exit from the flow, so it has to close the flow's books.**
    ///
    /// It did not, and the two buttons on this card disagreed about whether onboarding had happened.
    /// "Not now" advances to `.done`, whose `finish()` writes `context.onboarded`, clears the resume
    /// point and registers the login item. "Show me" hands over to a surface that never comes back
    /// here — `OnboardingWindow.startTutorial` dismisses this card and `Tutorial` keeps no record of
    /// its own — so `finish()` was simply never reached. The user who took the walkthrough got no
    /// login item, and the next launch read `context.onboarded` false with a resume point still
    /// pointing at `.tutorial` and put this card back up, offering the tutorial they had just done.
    ///
    /// Sealing here rather than making the tutorial call back is what keeps one owner for the flag:
    /// both exits from the last card of onboarding go through `sealTheRun()`, and the tutorial stays a
    /// surface onboarding hands off to rather than a step that has to report in.
    ///
    /// Only the bookkeeping runs. `.done`'s other work — reopening the Screen Recording pane, ringing
    /// the menu bar — is deliberately left behind, because the tutorial owns both of those beats
    /// itself (`TutorialStep.screenAccess`, `.menuBar`) and doing them here would put a System
    /// Settings pane over the walkthrough as it starts.
    private func startTutorial() {
        Sound.effect(.click)
        guard let onTutorial else {
            advance()
            return
        }
        sealTheRun()
        onTutorial()
    }

    // MARK: - 7. Done

    /// The last card, and the only one that used to end itself.
    ///
    /// Exactly one button, whichever state the run finished in — there is always something to press,
    /// because a final screen with no control is a screen that has to close on a timer.
    private var done: some View {
        VStack(spacing: 14) {
            says(
                [(doneHeadline, .plain)],
                style: .stepHeadline,
                aside: doneAside)

            Group {
                switch lastCard.action {
                case .restart:
                    InkButton("Restart to finish") { restartForScreenGrant() }
                case .close:
                    InkButton("Done") { closeOnboarding() }
                case .openScreenRecording:
                    InkButton("Open Screen Recording", kind: .secondary) {
                        // Counted, because this is the card's whole affordance and pressing it
                        // twice for nothing is what turns the last screen of the flow into a room
                        // with no door. The second press flips `lastCard` to the state above.
                        noteScreenAsked()
                        Permissions.openSettings(for: .screen)
                    }
                }
            }
            .padding(.top, 4)
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
    }

    /// Whether the user said "later" to the screen row on purpose, rather than simply not having
    /// answered yet. The two states look identical from `isGranted(.screen)` and the last card owes
    /// them different things: a route to the pane, or the door.
    private var screenWasPostponed: Bool { invitations.answers[.screen] == .deferred }

    /// What this card does and offers, given the state the run finished in.
    private var lastCard: OnboardingFinale {
        finale(asks: screenAsks, reopens: screenReopens)
    }

    /// The same decision over explicit counts, so a caller holding fresher ones than `@State` has
    /// published can use them. `finish()` is that caller: it reads the tally and decides on the same
    /// turn, and a card that opened the pane off a stale count would be the loop arriving by the one
    /// route the tally was added to close.
    private func finale(asks: Int, reopens: Int) -> OnboardingFinale {
        OnboardingFinale.of(
            screenGranted: isGranted(.screen),
            needsRelaunch: needsRelaunch,
            screenWasPostponed: screenWasPostponed,
            askIsSpent: PermissionDeadEnd.asksAreSpent(asks),
            relaunchIsSpent: !PermissionDeadEnd.mayRelaunch(after: reopens),
            screenRecordIsUnusable: screenRecordIsUnusable)
    }

    /// Re-reads the persisted tally into the card.
    ///
    /// The authority is `UserDefaults` — one of the instructions being bounded is *reopen me*, which
    /// ends this process — and this is the copy the card draws from. It has to be `@State` because
    /// the closing card has no poll of its own: nothing else on `.done` changes when the tally does,
    /// so a press that adds to it would otherwise redraw nothing at all.
    private func readAskLedger() {
        let ledger = PermissionAskLedger()
        screenAsks = ledger.asks(.screen)
        screenReopens = ledger.relaunches(.screen)
    }

    /// One more fruitless trip to the pane, recorded and reflected back into the card.
    private func noteScreenAsked() {
        PermissionAskLedger().noteAsked(.screen)
        readAskLedger()
    }

    private var doneHeadline: String {
        // The card has run out of true things to ask for. Saying "One more thing" over an
        // instruction this user has already followed is the sentence that reads as the app being
        // broken rather than the permission being stuck.
        if lastCard.askIsSpent { return "That isn’t taking." }
        guard isGranted(.screen) else {
            return screenWasPostponed ? "Whenever you’re ready." : "One more thing."
        }
        return needsRelaunch ? "Almost." : "I’m listening."
    }

    private var doneAside: String {
        if lastCard.askIsSpent {
            // `reopened` is the distinction between the two dead ends this card can reach: a pane
            // that was opened twice for nothing, and a restart that was spent and did not help.
            let reopened = !PermissionDeadEnd.mayRelaunch(after: screenReopens)
            return PermissionDeadEnd.sentence(
                for: .screen, reopened: reopened, screenRecordIsUnusable: screenRecordIsUnusable)
                + " " + homeLine
        }
        if !isGranted(.screen) {
            // A card that closes is a card that has to say where the app went, the same as the
            // granted one — and it must not ask again for something already answered.
            guard !screenWasPostponed else {
                return "Switch Screen Recording on whenever you like. \(homeLine)"
            }
            return "Switch me on in Settings. I’ll do the rest."
        }
        // Naming the reason matters: "restart" with no cause reads as something having gone wrong.
        // macOS decides what a process may capture when it starts, so this one has to start again.
        return needsRelaunch
            ? "macOS gives screen access to a program when it starts, so I need to start again."
            : homeLine
    }

    /// **Where I live, and how to summon me.** The last thing on screen, and the only place either is
    /// still news.
    ///
    /// It was "I live up here." and nothing else, from when the menu bar was the only way in and the
    /// timeline was the only window. The app's advertised way in is the chord now — it opens the
    /// Activity panel, and `StatusView` prints the same chord beside the same row — so a final card
    /// that taught only the menu bar was teaching the slower of two routes and omitting the one the
    /// product is arranged around. The menu bar stays: it is what the ring is pointing at while this
    /// is read, and it is the route that works when the chord cannot.
    ///
    /// Not conditional on the account. It used to be written as a ternary whose two branches were the
    /// same string, under a comment promising a signed-in variant about where the recordings go —
    /// which is to say the app paid to observe sign-in state and rendered the same words either way.
    /// Where the recordings go is already said on the value card, before consent is taken, which is
    /// the only place saying it changes anything.
    ///
    /// It **is** conditional on the chord being armed, and that is not the same kind of condition. A
    /// gesture binding needs Accessibility to fire at all, Accessibility is the one permission this
    /// flow lists and never requires, and a closing sentence promising a keystroke that does nothing
    /// is worse than one that says less. `GlobalShortcuts` is asked rather than assumed, so a rebound
    /// chord prints as whatever the user bound.
    private var homeLine: String {
        let shortcuts = GlobalShortcuts.shared
        let armed = shortcuts.readiness(for: .openActivity) == .armed
        return Self.homeLine(chord: armed ? shortcuts.display(for: .openActivity) : nil)
    }

    /// The sentence itself, as a function of the one fact it turns on — `nil` for "there is no chord
    /// to promise". Hoisted out of the view for the same reason `OnboardingStep` is: whether the last
    /// card of the flow advertises a keystroke has a wrong answer available in both directions, and a
    /// `View` is not a place that can be asserted.
    static func homeLine(chord: String?) -> String {
        guard let chord else { return "I live up here." }
        return "I live up here. Press \(chord) to see what I’ve caught."
    }

    /// The window sits inside `visibleFrame`, so its top-trailing corner is directly beneath the
    /// menu bar item. A drifting chevron points at it; a drawn menu bar would be a lie.
    private var menuBarCue: some View {
        Image(systemName: "chevron.up")
            .font(.system(size: 17, weight: .medium))
            .foregroundStyle(Ink.secondary)
            .offset(y: cueDrift ? -12 : 0)
            .opacity(cueDrift ? 0 : 1)
            .padding(.trailing, 18)
            .padding(.top, 16)
            .allowsHitTesting(false)
            .onAppear {
                guard !InkReduceMotion.isEnabled else { return }
                withAnimation(.easeOut(duration: 1.1).repeatForever(autoreverses: false)) {
                    cueDrift = true
                }
            }
    }

    // MARK: - Chrome

    /// Back, only where back is real. `OnboardingStep.back` is what decides that; this only draws it.
    @ViewBuilder
    private var backCue: some View {
        if let target = OnboardingStep.back(from: step, signedIn: auth.isSignedIn) {
            Button {
                go(to: target)
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Ink.secondary)
                    .frame(width: 26, height: 26)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Text("Back"))
            .padding(.leading, 16)
            .padding(.top, 14)
        }
    }

    /// The strip at the foot of the card the dots live in — always the same height, whether or not
    /// this card has dots, so the column above is offered the same room on every step and the copy
    /// does not shift by 40 pt between the welcome card and the one after it.
    private var progressBand: some View {
        progressDots
            .frame(height: InkLayout.progressBandHeight)
            .frame(maxWidth: .infinity)
            .allowsHitTesting(false)
    }

    /// One dot per card of actual work, the current one filled.
    ///
    /// Deliberately not a percentage or a "step 3 of 6": the count changes with the itinerary — a
    /// restored session has one card fewer — and a number that moves is worse than no number.
    @ViewBuilder
    private var progressDots: some View {
        let steps = OnboardingStep.progressSteps(signedIn: auth.isSignedIn)
        if let index = OnboardingStep.progressIndex(of: step, signedIn: auth.isSignedIn) {
            HStack(spacing: 6) {
                ForEach(steps.indices, id: \.self) { dot in
                    Circle()
                        .fill(dot == index ? Ink.primary : Ink.primary.opacity(0.22))
                        .frame(width: 5, height: 5)
                }
            }
            .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: index)
        }
    }

    /// The finale: the sheet burns out from its edges. `plusLighter` with `Ink.glow` — white, the
    /// only value bright enough for an additive blend to have anywhere to go — drives the outer ring
    /// to white, so the card reads as overexposing on its way out rather than fading. On a light
    /// sheet a fade to transparent would just be the surface becoming the surface.
    private func edgeGlow(in size: CGSize) -> some View {
        RadialGradient(
            gradient: Gradient(stops: [
                .init(color: Ink.glow.opacity(0), location: 0.3),
                .init(color: Ink.glow.opacity(0.14), location: 0.7),
                .init(color: Ink.glow.opacity(0.6), location: 1),
            ]),
            center: .center,
            startRadius: 0,
            endRadius: hypot(size.width, size.height) / 2
        )
        .blendMode(.plusLighter)
        .allowsHitTesting(false)
        .transition(.opacity)
    }

    // MARK: - Step machine

    /// `value` reads as a list, the same as `permissions`, so it takes the same full column and the
    /// same left edge. Centring a three-line list gives every line a different left margin.
    private var isLeftAligned: Bool {
        step == .permissions || step == .value || step == .connector || step == .tutorial
    }

    private var columnWidth: CGFloat {
        isLeftAligned ? InkLayout.permissionsMaxWidth : InkLayout.contentMaxWidth
    }
    private var columnAlignment: Alignment { isLeftAligned ? .leading : .center }

    private var stepAnimation: Animation? {
        InkReduceMotion.isEnabled ? nil : .easeOut(duration: InkMotion.stepTransition)
    }

    private func transition(in size: CGSize) -> AnyTransition {
        guard !InkReduceMotion.isEnabled else { return .opacity }
        return .opacity.combined(with: .offset(y: size.height * 0.015))
    }

    /// The next card on this run's itinerary. Every "continue" goes through here, so the ordering
    /// lives in exactly one place and no card can advance to a step the itinerary skipped.
    private func advance() {
        guard let next = OnboardingStep.next(after: step, signedIn: auth.isSignedIn) else { return }
        go(to: next)
    }

    private func go(to next: OnboardingStep) {
        // Chrome, and gated as chrome: `Sound` already honours the system UI-sound setting for this
        // cue, and a failure to play it can never stop the card from changing.
        Sound.effect(.click)
        // Written *before* the card changes, and on the transition rather than on arrival. Screen
        // Recording ends this process to take effect, so the very next thing after some of these
        // transitions is a relaunch — a resume point recorded afterwards would be recorded by a
        // process that is already gone.
        OnboardingResume().record(next)
        // Every "continue" goes through here, so the funnel is measured at the one place the
        // ordering lives. Ordinal only: the step *names* are product copy that changes every
        // release, and a funnel keyed on copy resets every release.
        ContextAnalytics.recordOnboardingStep(
            index: next.rawValue, of: OnboardingStep.allCases.count)
        withAnimation(stepAnimation) { step = next }
        beginStep()
    }

    /// Arrival work only. **Nothing scheduled, nothing deferred.**
    ///
    /// Every card used to hand its own furniture to a timer — `scheduleSettle(after: 0.34)`, and a
    /// full 1200 ms on the welcome card so the button waited out the word-by-word reveal. The
    /// buttons were drawn at `opacity(0)` until it fired, so for between a third of a second and a
    /// second and a half the only control on screen was invisible and unclickable. Reported as the
    /// rule this file now keeps: *"During onboarding have no time based triggers. Only after clicks
    /// or user pressing continue or grant permission."*
    ///
    /// A fade-in is not worth a control the user cannot press. The text still animates — that is the
    /// card's entrance, and it gates nothing — but every button is live on the first frame.
    private func beginStep() {
        switch step {
        case .welcome, .value, .signIn, .tutorial:
            break
        case .permissions:
            // Reading the current grants is the *only* thing that happens on arrival now. There is
            // no ordering hazard left to comment on: nothing here can advance the card, because the
            // card is left by pressing a button.
            refreshPermissions()
            warmModels()
            if let probe = PermissionChoreography.probedCapability { probeChoreography(probe) }
        case .connector:
            refreshConnectorStatus()
        case .done:
            finish()
        }
    }

    // MARK: - Permissions

    private func isGranted(_ capability: Capability) -> Bool {
        granted[capability] ?? false
    }

    /// The word at the end of a row, which on this card is also the row's only affordance.
    ///
    /// It is an **imperative** wherever there is still something to do. "Open" was a state, and a
    /// state was honest while a run was walking the rows for the user; now the user is the only thing
    /// that starts an ask, so a row that describes itself instead of asking to be clicked is a row
    /// nobody clicks. "Allow" is macOS's own word for the button on the dialog it raises, and
    /// "Open Settings" is the truth about a second click: TCC spends each prompt exactly once.
    private func status(for capability: Capability) -> String {
        Self.statusWord(
            for: capability,
            granted: isGranted(capability),
            screenNeedsRelaunch: needsRelaunch,
            reported: reported,
            asking: invitations.subject == capability,
            answer: invitations.answers[capability],
            offered: invitations.offered.contains(capability))
    }

    /// The word itself, as a function of the seven facts that decide it.
    ///
    /// Hoisted out of the view for the same reason `homeLine(chord:)` is: this is the only affordance
    /// on the card, every one of these words is a promise about what the next click does, and a
    /// `private var` on a `View` is not something a test can hold.
    ///
    /// **Accessibility never says "Allow", and never says "Asking…".** macOS has no dialog for it at
    /// any point in its life — `Permissions.request(.accessibility)` opens the pane, because
    /// `AXIsProcessTrustedWithOptions` only nags with a dialog that leads there — so a row promising
    /// a prompt is promising something that cannot arrive, and a row claiming macOS is asking is
    /// claiming something nothing is doing. This was already the documented intent of the preamble
    /// ("its own row says Open Settings"); the row said "Allow" until it had been clicked once, which
    /// is exactly the one click the sentence was written to save.
    nonisolated static func statusWord(
        for capability: Capability,
        granted: Bool,
        screenNeedsRelaunch: Bool,
        reported: Bool,
        asking: Bool,
        answer: PermissionGate.Answer?,
        offered: Bool
    ) -> String {
        // **The relaunch state now has two halves, and they are not the same sentence.**
        //
        // These used to be one case: `screenNeedsRelaunch` implied a true preflight, which implied
        // `granted`. It no longer does — the offer is now also armed by a *stale* preflight, where
        // whether the user flipped the switch is exactly what this process cannot know.
        //
        // `granted` — TCC vouches for it and this process still cannot use it. That is a definite
        // claim about a definite state, and "Action required" is right.
        //
        // `!granted` — the preflight denies us and we have no idea whether that is true. Saying
        // "Action required" here would put a demand on the row the moment the pane opened, before
        // the user had touched anything, and leave it there whether they granted, declined or walked
        // away. But the row is not idle either: it is the control that performs the reopen, and the
        // caption has just asked them to click it. "Asking…" was the reported dead end and is the one
        // word this must not fall through to.
        if capability == .screen, screenNeedsRelaunch {
            return granted ? "Action required" : "Reopen"
        }
        if granted { return "Granted" }
        if capability == .accessibility, reported, answer != .deferred { return "Open Settings" }
        if asking { return "Asking…" }
        if !reported { return "Checking" }
        if answer == .deferred { return "Later" }
        return offered ? "Open Settings" : "Allow"
    }

    private func refreshPermissions() {
        let report = Permissions.report()
        var next: [Capability: Bool] = [:]
        for capability in capabilities {
            next[capability] = report.first { $0.name == capability.rawValue }?.granted
                ?? Permissions.check(capability)
        }
        // One place for the success cue, so a grant sounds the same however it was obtained — a
        // click on a row, or the switch flipped under the overlay's ring in System Settings.
        let landed = capabilities.filter { next[$0] == true && granted[$0] != true }
        granted = next
        needsRelaunch = Permissions.screenNeedsRelaunch
        screenRecordIsUnusable = Permissions.screenRecordIsUnusable
        if reported, !landed.isEmpty { Sound.effect(.chime) }
        reported = true

        // **A capability that is genuinely working ends its tally**, so a later, honest ask starts
        // from zero rather than inheriting a dead end somebody else's session reached. Genuinely
        // working, and not merely present in TCC: the screen's record reads granted for a process
        // the window server is refusing, and clearing on that would rearm the restart loop.
        let ledger = PermissionAskLedger()
        for capability in capabilities
        where PermissionDeadEnd.isWorking(
            capability, granted: next[capability] ?? false, screenNeedsRelaunch: needsRelaunch)
        {
            ledger.noteWorking(capability)
        }

        // Deliberately does not advance. This poll used to be a second exit from the card, and a
        // poll cannot tell a grant the user made from a question they never answered. The button
        // owns the exit; this only keeps the rows honest.
    }

    // MARK: - The two ways off this card

    /// **The one exit from the permissions card**, and it is a button.
    ///
    /// `invitations.canLeaveStep` is the whole predicate: every required capability answered, and
    /// every answer authored by the user — granted, or postponed by pressing a button that says so.
    /// No timeout reaches this and neither does a poll. The guard is kept even though the button is
    /// already disabled without it, because "may this card be left" must have exactly one answer and
    /// a disabled button is a drawing rather than an assertion.
    private func leavePermissions() {
        guard step == .permissions, invitations.canLeaveStep else { return }
        advance()
    }

    /// "I'll do these later": answers everything still outstanding, deliberately, and moves on.
    ///
    /// This exists *because* nothing is asked automatically. The per-capability escape only appears
    /// once an episode has reached System Settings, so a user who simply does not want to click any
    /// of these had no answer to give and no way forward — which is the dead end the postpone escape
    /// was written to prevent, reappearing one level up.
    /// It goes through the same exit predicate as Continue rather than advancing on its own. The
    /// board refuses a card-wide skip while an episode is in flight — that episode has its own
    /// escape on screen — and a button that advanced anyway would leave the card with a required
    /// capability unanswered, which is the one thing this step is arranged to make impossible.
    private func deferTheRest() {
        guard step == .permissions else { return }
        invitations.deferRest()
        guard invitations.canLeaveStep else { return }
        advance()
    }

    // MARK: - Models

    /// The first model pull is ~600 MB. Warming it behind this step costs the user nothing;
    /// leaving it to the first conversation costs them the conversation.
    private func warmModels() {
        // Intel has no ANE / Parakeet path — cloud `/v4/listen` is the only ASR.
        guard HostArchitecture.usesLocalSTT else { return }
        guard !Transcriber.isModelReady else { return }
        warmingModels = true
        modelProgress = 0
        Task { @MainActor in
            do {
                try await Transcriber.prepareModels { value in
                    Task { @MainActor in modelProgress = min(max(value, 0), 1) }
                }
            } catch {
                ContextLog.error("transcription model warm-up failed: \(error)", "onboarding")
            }
            warmingModels = false
            modelProgress = nil
        }
    }

    // MARK: - Finale

    /// **Everything that makes this install a set-up one**, and nothing that draws.
    ///
    /// Split out of `finish()` because `.done` stopped being the only way out of the flow: the
    /// tutorial hand-off leaves from `.tutorial` and never returns, so both exits call this and
    /// exactly one of them goes on to do the finale. Idempotent — every line is a set, a clear, or a
    /// stop with a no-op case — which is what lets the two paths share it without either having to
    /// know whether the other ran.
    private func sealTheRun() {
        if !LoginItem.enable() {
            ContextLog.error("could not register as a login item", "onboarding")
        }
        UserDefaults.standard.set(true, forKey: "context.onboarded")
        // The run is over, so the resume point is spent. Left behind it would reopen this card over
        // a user who has finished — and `ContextApp` presents the window on *either* signal, so a
        // stale one outlives the flag that was supposed to close the flow.
        OnboardingResume().clear()
        // The bed is the cinematic's, and the cinematic is over. Fades rather than cuts; a stop with
        // no music playing is a no-op, so this is safe however the run got here.
        Sound.music.stop()
        // **The line above is a precondition of the Accessibility ask, so the ask is re-evaluated
        // here rather than left to the next app activation.** `GlobalShortcuts.askForAccessibility()`
        // refuses to raise the system alert until onboarding has finished — otherwise it would race
        // the flow's own permission choreography — and the only thing that re-evaluates it is
        // `reapply()`, which ran at launch when this flag was still false. Without this the user
        // who finishes onboarding and stays in the app is never asked at all, and `⌘ + ⌘` goes on
        // doing nothing until they happen to switch away and back. Idempotent like the rest of this
        // method: `reapply()` re-registers what is already registered, and the ask is once per launch.
        GlobalShortcuts.shared.refresh()
    }

    private func finish() {
        ContextAnalytics.recordOnboardingFinished()
        sealTheRun()

        // Screen Recording is the one grant macOS will not take from a dialog — it has to be
        // switched on in System Settings, and it only takes effect in a new process. Dismissing
        // here would leave the user believing setup finished with a third of it dead, so the card
        // stays, opens the right pane itself, and waits.
        //
        // **The watch and the pane are separate decisions**, and conflating them is what stranded a
        // postponed run — see `OnboardingFinale`. **And neither is offered unconditionally**: a run
        // that has already spent its asks reaches this card with nothing left to ask for, so it gets
        // the watch and the door rather than the pane and the same sentence again.
        let ledger = PermissionAskLedger()
        let asks = ledger.asks(.screen)
        let reopens = ledger.relaunches(.screen)
        let lastCard = finale(asks: asks, reopens: reopens)
        screenAsks = asks
        screenReopens = reopens
        if lastCard.watchesForTheGrant { watchForScreenGrant(openingPane: lastCard.opensThePane) }
        // "I live up here" is only useful if the user can find "here". Ring the real status item
        // and walk the pointer to it while the line is still on screen. The ring comes down when the
        // user closes the card, not on a timer of its own.
        if lastCard.ringsTheMenuBar { MenuBarSpotlight.show() }
    }

    /// **The last click of the flow.** The card used to close itself 1.6 s after arriving here, and
    /// take the menu-bar ring down 2.5 s after that — so the final screen, the one naming where the
    /// app now lives, was the one screen the user was given the least control over. Reading it
    /// slowly was indistinguishable from not reading it, and either way it left.
    ///
    /// Now it waits. The glow and the dismissal are the same gesture as the press, so the finale is
    /// still seen; it is just no longer scheduled.
    private func closeOnboarding() {
        Sound.effect(.click)
        withAnimation(.easeOut(duration: InkReduceMotion.duration(InkMotion.finaleGlow))) { finale = true }
        // Everything this card put on top of other applications, taken back off. The watch is a poll
        // with no deadline — the card being closed is what ends it — and the overlay is a window over
        // System Settings that would otherwise outlive the flow that raised it.
        endScreenWatch()
        MenuBarSpotlight.hide()
        OnboardingWindow.dismiss()
    }

    /// Restarts into the Screen Recording grant, from a button.
    ///
    /// The window server fixes what a process may capture when that process connects, so a grant
    /// made while this app is running belongs to the *next* one. That was previously done for the
    /// user 1.5 s after the grant landed — the app replacing itself while they were still in System
    /// Settings looking at the switch they had just flipped. The remedy is the same; who starts it
    /// is not.
    private func restartForScreenGrant() {
        Sound.effect(.click)
        // Written down *before* the process ends, because the process ending is the whole point of
        // this button and an in-memory tally would come back at zero. A successor that finds itself
        // still refused reads this and offers the door instead of the same restart.
        PermissionAskLedger().noteRelaunched(.screen)
        endScreenWatch()
        MenuBarSpotlight.hide()
        Permissions.relaunchApp()
    }

    /// **Watches for the Screen Recording switch, and — unless the user already said later — opens
    /// the pane and points at the row.**
    ///
    /// The watch is a poll because macOS posts no notification for a TCC grant — it is how this app
    /// *detects the user's action*, which is the one thing a clock here is allowed to do. It starts
    /// nothing on its own: when the grant lands the card offers a button and stops.
    ///
    /// Two things it no longer gets wrong, both of them the same mistake — treating "we opened the
    /// pane" as the thing being waited on rather than a courtesy on the way:
    ///
    /// - **A grant that landed before System Settings came forward used to be dropped.** The guard
    ///   after the wait returned on `Permissions.check(.screen)` being *true*, which is the good case;
    ///   the card then sat on "One more thing" over a permission the user had just given. The wait now
    ///   only decides whether there is anything to point at, and the loop below is what answers.
    /// - **A postponed run had no watch at all**, so nothing on the last card could ever change its
    ///   own state. See `finish()`.
    private func watchForScreenGrant(openingPane: Bool) {
        guard !openedScreenSettings else { return }
        openedScreenSettings = true
        if openingPane {
            noteScreenAsked()
            Permissions.openSettings(for: .screen)
        }

        screenWatch = Task { @MainActor in
            if openingPane {
                // Nothing to point at until the pane is up. Waiting for System Settings to actually
                // come forward, rather than assuming it takes 1200 ms, means the overlay lands on the
                // pane that is really there — on a slow launch the fixed sleep rang the previous
                // pane's rows.
                await Permissions.waitForSettingsFrontmost()
                guard !Task.isCancelled, step == .done else { return }
                if !Permissions.check(.screen) {
                    PermissionOverlay.show(
                        for: .screen,
                        caption: "Switch on \(PermissionChoreography.appDisplayName).")
                }
            }

            while !Task.isCancelled, step == .done, !Permissions.check(.screen) {
                try? await Task.sleep(for: Permissions.grantWatchPoll)
            }
            guard !Task.isCancelled, step == .done, Permissions.check(.screen) else {
                PermissionOverlay.hide()
                return
            }
            granted[.screen] = true
            needsRelaunch = Permissions.screenNeedsRelaunch
            Sound.effect(.chime)
            // Witness the grant on the overlay, then stop. The restart is the user's to press.
            if openingPane {
                PermissionOverlay.confirmGranted()
            } else {
                PermissionOverlay.hide()
            }
        }
    }

    /// Ends the watch and takes down anything it raised. The poll is unbounded by design, so leaving
    /// this card is the only thing that can stop it.
    private func endScreenWatch() {
        screenWatch?.cancel()
        screenWatch = nil
        PermissionOverlay.hide()
    }
}
