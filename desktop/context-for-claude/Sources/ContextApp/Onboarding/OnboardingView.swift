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

    /// Fixed order. Microphone first because it is the one people expect; the system tap second
    /// because it only makes sense once the mic has been explained; screen, and then the window text
    /// that sharpens it, because the second is worth nothing without the first.
    ///
    /// The order and the required subset both live on `PermissionInvitations`, because that is what
    /// they are *for*: the set `canLeaveStep` quantifies over. Two copies would be two answers to
    /// "may this card be left".
    private var capabilities: [Capability] { invitations.listed }

    /// Owned by the auth layer, observed here. Everything Context for Claude records lands in this
    /// account, so the step machine asks it who the user is before it asks macOS for a microphone.
    @ObservedObject private var auth = OmiAuth.shared

    /// The probe opens straight onto the permissions card.
    ///
    /// Not a shortcut for its own sake: the choreography sits behind sign-in, and the account state of
    /// the machine a build is being checked on is not something a self-test should have to change. It
    /// only ever *skips forward past* cards, and only when the environment variable is set.
    @State private var step: OnboardingStep =
        PermissionChoreography.probedCapability == nil ? .welcome : .permissions
    @State private var settled = false

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

            // The button arrives after the last word does; offering it mid-sentence invites a
            // click before the sentence has been read.
            InkButton("Turn me on") { advance() }
                .opacity(settled ? 1 : 0)
                .animation(stepAnimation, value: settled)
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
    /// It deliberately does **not** gate on `settled`: the words arriving *are* this card's
    /// entrance, and the rest of the card settles in behind them. Nothing here delays a button —
    /// `scheduleSettle` is untouched, and `SpokenCadence.maximumPhrase` caps a phrase at the
    /// duration the welcome hero already took.
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

            // The list and the button settle in behind the mark, rather than the whole card waiting
            // for one timer: the character speaks first and its furniture follows, which is the
            // order those two things happen in.
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
            .opacity(settled ? 1 : 0)
            .animation(stepAnimation, value: settled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The three claims, each one a thing the app genuinely does — two sources and the destination.
    ///
    /// Written as claims rather than features because every one of them is something the user is about
    /// to be asked to allow, and the ask is only meaningful if it was described first. The destination
    /// line is the one that has to be here and not later: the next card asks for an account, and a
    /// user who has not been told what leaves the machine cannot meaningfully agree to it.
    private static let valueClaims: [(glyph: String, copy: String)] = [
        ("rectangle.on.rectangle", "I watch your screen — the frames, and the text in your windows."),
        ("waveform", "I listen — your microphone, and the audio of your calls."),
        ("lock", "It lands in your Omi account, and Claude reads it from there."),
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
        .onReceive(permissionTick) { _ in refreshPermissions() }
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
    private let permissionTick = Timer.publish(every: 1.5, on: .main, in: .common).autoconnect()

    /// What is about to happen, in the order it happens, before any of it happens.
    ///
    /// Standing still it is an instruction; mid-episode it is the gate's caption for the phase.
    ///
    /// The resting copy is the part that changed, and it changed because the behaviour did. It used
    /// to open "macOS will ask three times", which was a promise the card kept the moment it
    /// appeared — three dialogs, on a timer, over this sentence. Nothing is asked now until a row is
    /// clicked, so the sentence has to say that: it is the only thing telling the reader that the
    /// card is waiting for them rather than the other way round. Accessibility is named here as the
    /// one with no dialog rather than discovered later as an unaskable fourth row.
    private var setupPreamble: String {
        // The gate says where the episode is, including the sentence that has to be on screen while
        // the user is standing in System Settings deciding.
        if let caption = invitations.caption { return caption }
        return """
        Nothing is asked until you click it. Read these, then click whichever you’re ready for — \
        macOS asks separately for each, and I take them one at a time. Window text is the odd one: \
        it has no dialog at all, so clicking it opens System Settings and I’ll show you the switch.
        """
    }

    private var setupTitle: String {
        // "First…" only survives for a run that never signed in; once the account is known, the
        // permissions are no longer the first thing being asked for.
        guard invitations.isBusy else { return auth.isSignedIn ? "Now the permissions." : "First…" }
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
            // System Settings has to be up, and on the right pane, before there is anything to find.
            // Pointing before it exists is how an overlay ends up ringing the last pane's rows.
            try? await Task.sleep(for: .milliseconds(1_200))
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
            // and the same duration.
            try? await Task.sleep(for: .milliseconds(1_200))
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
            .opacity(settled ? 1 : 0)
            .animation(stepAnimation, value: settled)
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
    private var tutorial: some View {
        VStack(alignment: .leading, spacing: 18) {
            says(
                [("Want to see it work?", .plain)],
                style: .firstTitle,
                aside: "A minute, and it ends with Claude answering a question about your own screen.")

            HStack(spacing: 12) {
                InkButton("Show me") { startTutorial() }
                InkButton("Not now", kind: .secondary) { advance() }
            }
            .opacity(settled ? 1 : 0)
            .animation(stepAnimation, value: settled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func startTutorial() {
        Sound.effect(.click)
        guard let onTutorial else {
            advance()
            return
        }
        onTutorial()
    }

    // MARK: - 7. Done

    private var done: some View {
        VStack(spacing: 14) {
            says(
                [(isGranted(.screen) ? "I’m listening." : "One more thing.", .plain)],
                style: .stepHeadline,
                aside: isGranted(.screen) ? homeLine : "Switch me on in Settings. I’ll do the rest.")

            if !isGranted(.screen) {
                InkButton("Open Screen Recording", kind: .secondary) {
                    Permissions.openSettings(for: .screen)
                }
                .padding(.top, 4)
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
    }

    /// Where I live. Said once, here, because it is the last thing on screen and the only place it is
    /// still news.
    ///
    /// Not conditional on the account. It used to be written as a ternary whose two branches were the
    /// same string, under a comment promising a signed-in variant about where the recordings go —
    /// which is to say the app paid to observe sign-in state and rendered the same words either way.
    /// Where the recordings go is already said on the value card, before consent is taken, which is
    /// the only place saying it changes anything.
    private let homeLine = "I live up here."

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
        settled = false
        withAnimation(stepAnimation) { step = next }
        beginStep()
    }

    private func beginStep() {
        switch step {
        case .welcome:
            // The word-by-word reveal runs for 1200 ms; the step is not settled until it lands.
            scheduleSettle(after: InkMotion.wordReveal)
        case .value:
            scheduleSettle(after: 0.34)
        case .signIn:
            scheduleSettle(after: 0.34)
        case .permissions:
            // Reading the current grants is the *only* thing that happens on arrival now. There is
            // no ordering hazard left to comment on: nothing here can advance the card, because the
            // card is left by pressing a button.
            refreshPermissions()
            warmModels()
            if let probe = PermissionChoreography.probedCapability { probeChoreography(probe) }
            scheduleSettle(after: 0.34)
        case .connector:
            refreshConnectorStatus()
            scheduleSettle(after: 0.34)
        case .tutorial:
            scheduleSettle(after: 0.34)
        case .done:
            finish()
            scheduleSettle(after: 0.34)
        }
    }

    private func scheduleSettle(after seconds: Double) {
        guard !InkReduceMotion.isEnabled else {
            settled = true
            return
        }
        let target = step
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(seconds))
            guard step == target else { return }
            withAnimation(.easeOut(duration: InkMotion.settle)) { settled = true }
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
        if capability == .screen, needsRelaunch { return "Action required" }
        if isGranted(capability) { return "Granted" }
        if invitations.subject == capability { return "Asking…" }
        if !reported { return "Checking" }
        if invitations.answers[capability] == .deferred { return "Later" }
        return invitations.offered.contains(capability) ? "Open Settings" : "Allow"
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
        if reported, !landed.isEmpty { Sound.effect(.chime) }
        reported = true

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

    private func finish() {
        if !LoginItem.enable() {
            ContextLog.error("could not register as a login item", "onboarding")
        }
        UserDefaults.standard.set(true, forKey: "context.onboarded")
        // The bed is the cinematic's, and the cinematic is over. Fades rather than cuts; a stop with
        // no music playing is a no-op, so this is safe however the run got here.
        Sound.music.stop()

        // Screen Recording is the one grant macOS will not take from a dialog — it has to be
        // switched on in System Settings, and it only takes effect in a new process. Dismissing
        // here would leave the user believing setup finished with a third of it dead, so the card
        // stays, opens the right pane itself, and waits.
        guard isGranted(.screen) else {
            // "I'll do this later" was a real answer, given deliberately on the permissions card.
            // Opening the pane over them again here would take it back. The button on this card is
            // still the route forward whenever they want it.
            if invitations.answers[.screen] != .deferred { openScreenSettingsOnce() }
            return
        }

        // "I live up here" is only useful if the user can find "here". Ring the real status item
        // and walk the pointer to it while the line is still on screen.
        MenuBarSpotlight.show()

        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(1_600))
            guard step == .done, isGranted(.screen) else { return }
            withAnimation(.easeOut(duration: InkReduceMotion.duration(InkMotion.finaleGlow))) { finale = true }
            OnboardingWindow.dismiss()
            // Outlive the card briefly: the ring is the last thing left pointing at the icon, and
            // clearing it with the window would take the answer away with the question.
            try? await Task.sleep(for: .milliseconds(2_500))
            MenuBarSpotlight.hide()
        }
    }

    /// Opens the Screen Recording pane once, points at the real row, then watches for the grant and
    /// relaunches into it — so the user's part is one switch, with no button to find afterwards.
    private func openScreenSettingsOnce() {
        guard !openedScreenSettings else { return }
        openedScreenSettings = true
        Permissions.openSettings(for: .screen)

        Task { @MainActor in
            // Same reason as the by-hand grant: nothing to point at until the pane is up.
            try? await Task.sleep(for: .milliseconds(1_200))
            guard step == .done, !Permissions.check(.screen) else { return }
            PermissionOverlay.show(
                for: .screen,
                caption: "Switch on \(PermissionChoreography.appDisplayName).")

            while step == .done, !Permissions.check(.screen) {
                try? await Task.sleep(for: .milliseconds(1_000))
            }
            guard step == .done, Permissions.check(.screen) else {
                PermissionOverlay.hide()
                return
            }
            granted[.screen] = true
            Sound.effect(.chime)
            PermissionOverlay.confirmGranted()
            // The grant is real but this process cannot use it. Relaunching is the whole remedy.
            try? await Task.sleep(for: .milliseconds(1_500))
            PermissionOverlay.hide()
            Permissions.relaunchApp()
        }
    }
}
