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
    static func next(after step: OnboardingStep, signedIn: Bool) -> OnboardingStep? {
        let itinerary = itinerary(signedIn: signedIn)
        guard let index = itinerary.firstIndex(of: step), index + 1 < itinerary.count else { return nil }
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
    private let capabilities: [Capability] = [.microphone, .systemAudio, .screen, .accessibility]

    /// The grants without which the app does nothing, and therefore the only ones the sequence asks
    /// for.
    ///
    /// Accessibility is deliberately outside this list. It cannot be prompted — macOS grants it by
    /// hand in System Settings and offers no dialog at all — so gating completion on it would strand
    /// anyone unwilling to leave the flow on a step with no button that could finish it. Capture
    /// degrades to OCR-only without it: a worse product, and a working one. It gets the choreography
    /// instead, which is a better offer than a prompt that does not exist.
    private var requiredCapabilities: [Capability] { [.microphone, .systemAudio, .screen] }

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

    @State private var granted: [Capability: Bool] = [:]
    @State private var asked: Set<Capability> = []
    @State private var requesting: Set<Capability> = []
    @State private var reported = false
    @State private var needsRelaunch = false

    @State private var connectorSurfaces: Set<ClaudeSurface> = []
    @State private var connectorMessage: String?
    @State private var configuringConnector = false
    @State private var modelProgress: Double?
    @State private var warmingModels = false

    @State private var granting = false
    @State private var openedScreenSettings = false
    @State private var cueDrift = false
    @State private var finale = false

    /// The by-hand grant the choreography is currently offering, and how far along it is.
    @State private var handGrant: Capability?
    @State private var guiding = false

    /// Whatever the sign-in attempt threw, shown as-is. A preamble in front of it would be a
    /// sentence that says nothing the error does not.
    @State private var signInError: String?
    /// The user pressed Cancel while the browser round trip was still open. There is no way to
    /// call the round trip off — the browser has it — so this only puts the buttons back.
    @State private var abandonedWait = false

    var body: some View {
        Backdrop(working: working, settled: settled) {
            GeometryReader { geometry in
                ZStack(alignment: .topTrailing) {
                    column
                        .id(step)
                        .transition(transition(in: geometry.size))

                    if step == .done {
                        menuBarCue
                    }
                }
                .overlay(alignment: .topLeading) { backCue }
                .overlay(alignment: .bottom) { progressDots }
                .frame(width: geometry.size.width, height: geometry.size.height)
                .overlay {
                    if finale {
                        edgeGlow(in: geometry.size)
                    }
                }
            }
        }
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
    private var yieldsScreen: Bool {
        if auth.isSigningIn { return true }
        if !requesting.isEmpty { return true }
        // The choreography is pointing at a row in System Settings. Covering the thing we just spent
        // a card teaching them to recognise would be the one unforgivable version of this step.
        if guiding { return true }
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
            RandomizedText(
                segments: [
                    ("I keep ", .plain),
                    ("Claude", .bold),
                    (" caught up on what you ", .plain),
                    ("see and say", .bold),
                    (".", .plain),
                ],
                style: .introHero,
                // Colour is a parameter here, not the environment — `RandomizedText` builds one
                // concatenated `Text` and per-word opacity has to ride on each run's colour.
                color: Ink.primary
            )
            .multilineTextAlignment(.center)

            // The button arrives after the last word does; offering it mid-sentence invites a
            // click before the sentence has been read.
            InkButton("Turn me on") { advance() }
                .opacity(settled ? 1 : 0)
                .animation(stepAnimation, value: settled)
        }
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
            Text("Here's what I do.")
                .inkStyle(.firstTitle)
                .foregroundStyle(Ink.primary)

            Text("Three things I take in, and one place they go.")
                .inkStyle(.prose)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

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
                            .foregroundStyle(Ink.tertiary)
                            .frame(width: 16)
                    }
                    .labelStyle(.titleAndIcon)
                }
            }

            InkButton("Continue") { advance() }
                .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(settled ? 1 : 0)
        .animation(stepAnimation, value: settled)
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
            Text("Which account is this?")
                .inkStyle(.stepHeadline)
                .foregroundStyle(Ink.primary)

            Text("It all lands in your Omi account.")
                .inkStyle(.prose)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if isWaitingForBrowser {
                VStack(spacing: 12) {
                    Text("Waiting for your browser…")
                        .inkStyle(.statusLabel)
                        .foregroundStyle(Ink.tertiary)

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

    // MARK: - 4. Permissions — one at a time, then the one macOS will not prompt for

    private var permissions: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(setupTitle)
                .inkStyle(.firstTitle)
                .foregroundStyle(Ink.primary)

            // Said before the first dialog, never after. macOS asks in its own words — terse,
            // system-voiced, and identical to the prompt of every app that ever abused the same
            // permission — and a user meeting that cold has only the app's reputation to go on.
            // Screen-recording tools die at exactly this prompt. Naming what is coming, in order,
            // in the app's own voice, is the difference between consenting and being startled.
            Text(setupPreamble)
                .inkStyle(.prose)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(spacing: 8) {
                ForEach(capabilities, id: \.self) { capability in
                    InkPermissionRow(
                        title: capability.title,
                        granted: isGranted(capability),
                        status: status(for: capability),
                        // The sequence asks for each of these itself. The row stays tappable only
                        // as the way back for someone who said no and changed their mind.
                        action: { request(capability) }
                    )
                }
            }

            if let handGrant {
                handGrantPanel(for: handGrant)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onReceive(Timer.publish(every: 1.5, on: .main, in: .common).autoconnect()) { _ in
            refreshPermissions()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissions()
        }
    }

    /// What is about to happen, in the order it happens, before any of it happens.
    ///
    /// Changes once the run starts: standing still, it is a warning; running, it is a caption for
    /// the row that is lit. Accessibility is named as optional here rather than discovered as an
    /// unaskable fourth row later.
    private var setupPreamble: String {
        if handGrant != nil {
            return """
            That's the three macOS will ask about. The fourth has no dialog — it is a switch you \
            flip yourself, and this is what it looks like.
            """
        }
        if granting {
            return "One at a time. Answer each one and I’ll wait for it to land before the next."
        }
        return """
        macOS will ask three times — microphone, then the audio of your calls, then your screen. \
        Each one is a separate question and I’ll ask them one at a time. The fourth, window text, \
        only System Settings can grant; it makes me quote exactly instead of guessing, and I work \
        without it.
        """
    }

    private var setupTitle: String {
        if handGrant != nil { return "One you flip yourself." }
        // "First…" only survives for a run that never signed in; once the account is known, the
        // permissions are no longer the first thing being asked for.
        if !granting { return auth.isSignedIn ? "Now the permissions." : "First…" }
        return "Say yes."
    }

    // MARK: The choreography

    /// The by-hand grant, offered with a replica of what is about to be shown.
    ///
    /// The replica is ours and is captioned as ours. What it previews is System Settings' own
    /// affordance — on macOS 26 a dashed row with an instruction to drag it up into the list — which
    /// no application can draw and this one does not try to. Half a second of a likeness on our card
    /// is what makes the real thing recognised rather than puzzled over.
    @ViewBuilder
    private func handGrantPanel(for capability: Capability) -> some View {
        HStack(alignment: .top, spacing: 16) {
            GhostRowReplica()
                .frame(width: 168)

            VStack(alignment: .leading, spacing: 12) {
                Text(guiding ? "Look for the ring." : "I’ll show you the row.")
                    .inkStyle(.rowCopy)
                    .foregroundStyle(Ink.primary)

                Text(
                    guiding
                        ? "System Settings is open and I’m pointing at the row. Flip it and I’ll notice."
                        : "It opens System Settings and rings the row so you don’t have to hunt for it."
                )
                .inkStyle(.statusLabel)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    InkButton(guiding ? "Waiting…" : "Show me the row") { beginHandGrant(capability) }
                        .disabled(guiding)
                    InkButton("Skip it", kind: .secondary) { finishHandGrant() }
                }
            }
        }
        .padding(.top, 2)
    }

    /// Opens the pane, waits for it to arrive, then points at the real row — and keeps watching for
    /// the grant so the user's part ends at the switch.
    private func beginHandGrant(_ capability: Capability) {
        guard !guiding else { return }
        Sound.effect(.click)
        guiding = true
        Permissions.openSettings(for: capability)

        Task { @MainActor in
            // System Settings has to be up, and on the right pane, before there is anything to find.
            // Pointing before it exists is how an overlay ends up ringing the last pane's rows.
            try? await Task.sleep(for: .milliseconds(1_200))
            guard guiding else { return }
            PermissionOverlay.show(
                for: capability,
                caption: "Switch on \(PermissionChoreography.appDisplayName).")

            // The probe points at a row that is already on, so there is no grant coming and nothing
            // to wait for. It holds the ring up until it is dismissed by hand, which is the whole
            // point of it: the positioning is what is being checked.
            guard PermissionChoreography.probedCapability == nil else { return }

            while guiding, !Permissions.check(capability) {
                try? await Task.sleep(for: .milliseconds(500))
            }
            guard guiding else { return }
            PermissionOverlay.confirmGranted()
            refreshPermissions()
            try? await Task.sleep(for: .milliseconds(900))
            finishHandGrant()
        }
    }

    /// Ends the choreography and moves on, whether the grant landed or the user skipped it. This
    /// step is never allowed to be a dead end: window text is an improvement, not a requirement.
    private func finishHandGrant() {
        guiding = false
        PermissionOverlay.hide()
        handGrant = nil
        guard step == .permissions else { return }
        advance()
    }

    // MARK: - 5. Claude connector

    /// Local configuration, after consent rather than before it. The registration itself is
    /// untouched — only the card around it moved and was restyled.
    private var connector: some View {
        let copy = OnboardingConnectorCopy(surfaces: connectorSurfaces)
        return VStack(alignment: .leading, spacing: 18) {
            Text(copy.title)
                .inkStyle(.firstTitle)
                .foregroundStyle(Ink.primary)

            Text(copy.detail)
                .inkStyle(.prose)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if let connectorMessage {
                Text(connectorMessage)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(Ink.tertiary)
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
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(settled ? 1 : 0)
        .animation(stepAnimation, value: settled)
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
            Text("Want to see it work?")
                .inkStyle(.firstTitle)
                .foregroundStyle(Ink.primary)

            Text("A minute, and it ends with Claude answering a question about your own screen.")
            .inkStyle(.prose)
            .foregroundStyle(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 12) {
                InkButton("Show me") { startTutorial() }
                InkButton("Not now", kind: .secondary) { advance() }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(settled ? 1 : 0)
        .animation(stepAnimation, value: settled)
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
            Text(isGranted(.screen) ? "I’m listening." : "One more thing.")
                .inkStyle(.stepHeadline)
                .foregroundStyle(Ink.primary)

            Text(isGranted(.screen)
                 ? homeLine
                 : "Switch me on in Settings. I’ll do the rest.")
                .inkStyle(.prose)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

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
                    .foregroundStyle(Ink.tertiary)
                    .frame(width: 26, height: 26)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Text("Back"))
            .padding(.leading, 16)
            .padding(.top, 14)
        }
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
            // Inside the legible area, not at the window's edge: the outer third of this window is
            // the mask's falloff, and dots drawn down there dissolve along with it.
            .padding(.bottom, 62)
            .allowsHitTesting(false)
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

    /// The backdrop drifts only while something is genuinely happening. Waiting on a browser counts,
    /// and it keeps drifting through a cancelled wait, because the round trip is still open.
    private var working: Bool {
        switch step {
        case .signIn: return auth.isSigningIn
        case .permissions: return granting || warmingModels || guiding
        case .connector: return configuringConnector
        case .welcome, .value, .tutorial, .done: return false
        }
    }

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
            // `runSetup` first, and the order matters. It claims the step synchronously by setting
            // `granting`, and `refreshPermissions` advances the moment it sees the required grants in
            // with no run in flight — so refreshing first means a machine that already has all three
            // grants leaves this card before the run has decided whether the by-hand grant still
            // needs offering. Observed live: the card skipped straight to the connector.
            runSetup()
            refreshPermissions()
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

    private func status(for capability: Capability) -> String {
        if capability == .screen, needsRelaunch { return "Action required" }
        if isGranted(capability) { return "Granted" }
        if requesting.contains(capability) || !reported { return "Checking" }
        return asked.contains(capability) ? "Action required" : "Open"
    }

    private func refreshPermissions() {
        let report = Permissions.report()
        var next: [Capability: Bool] = [:]
        for capability in capabilities {
            next[capability] = report.first { $0.name == capability.rawValue }?.granted
                ?? Permissions.check(capability)
        }
        // One place for the success cue, so a grant sounds the same however it was obtained — the
        // one-at-a-time run, a tap on a row, or the switch flipped under the overlay's ring.
        let landed = capabilities.filter { next[$0] == true && granted[$0] != true }
        granted = next
        needsRelaunch = Permissions.screenNeedsRelaunch
        if reported, !landed.isEmpty { Sound.effect(.chime) }
        reported = true

        // No continue button anywhere: the step ends the moment the grants are real — unless the
        // choreography is still offering the one macOS will not prompt for, which is a card the user
        // is in the middle of and must not be pulled out from under them.
        guard step == .permissions, !granting, handGrant == nil,
            requiredCapabilities.allSatisfy({ next[$0] == true })
        else { return }
        advance()
    }

    /// First tap raises the system prompt; once macOS has answered, a second tap can only be
    /// resolved in System Settings.
    private func request(_ capability: Capability) {
        guard !isGranted(capability), !requesting.contains(capability) else { return }
        guard !asked.contains(capability) else {
            Permissions.openSettings(for: capability)
            return
        }
        asked.insert(capability)
        requesting.insert(capability)
        Task { @MainActor in
            _ = await Permissions.request(capability)
            requesting.remove(capability)
            refreshPermissions()
        }
    }

    // MARK: - The one click

    /// Everything the single button on the first screen is responsible for, in order.
    ///
    /// The sequencing itself lives in `PermissionRun` — one at a time, with the lead-in and
    /// after-grant pacing that was a deliberate earlier fix — so it can be asserted without TCC.
    /// This is only the wiring: which capabilities, and what the rows do as the run moves.
    ///
    /// Registration and the login item happen at the end, whether or not every permission landed —
    /// Claude should be able to reach Context for Claude and report the gap, which is far better than
    /// Context for Claude being invisible because a microphone was declined.
    private func runSetup() {
        guard !granting else { return }
        granting = true

        Task { @MainActor in
            // Only the promptable ones. Asking for Accessibility inside this loop would throw System
            // Settings over the card mid-sequence, with no dialog to answer and nothing to come back
            // to — the run has to stay inside the window it started in. It gets the choreography
            // below instead, once the run is finished and there is nothing left to interrupt.
            await PermissionRun(asking: LivePermissionAsking()).run(
                requiredCapabilities,
                callbacks: .init(
                    // The row lights up first, alone, before anything covers it. Without this the
                    // dialogs arrive stacked on each other and the user answers three prompts having
                    // read none of them.
                    willAsk: { capability in
                        requesting.insert(capability)
                        asked.insert(capability)
                    },
                    didAnswer: { capability, _ in
                        requesting.remove(capability)
                        refreshPermissions()
                    }))

            if !LoginItem.isEnabled { _ = LoginItem.enable() }
            warmModels()

            // The by-hand offer is decided *before* the run is released, and this ordering is
            // load-bearing. `refreshPermissions` runs on a 1.5 s poll and advances the step as soon as
            // it sees the required grants in with no run in flight and no offer pending — so setting
            // `granting = false` first opens a window in which a tick can skip the choreography
            // entirely. It did, on the first live run: the card went straight to the connector.
            //
            // The one macOS will not prompt for is offered here rather than skipped, because the
            // choreography is a better answer than a row the user can only discover is unaskable. The
            // probe is how this path is exercised on a machine whose grants are all already in,
            // without revoking one to get at it.
            handGrant =
                PermissionChoreography.probedCapability
                ?? (Permissions.check(.accessibility) ? nil : .accessibility)
            granting = false

            // Give the last row's checkmark a beat to land before the card changes under it.
            try? await Task.sleep(for: .milliseconds(600))
            refreshPermissions()
            guard step == .permissions, handGrant == nil else { return }

            // Screen Recording is granted in System Settings and only takes effect in a new
            // process, so it never satisfies `refreshPermissions` in this one. Move on anyway and
            // let the last screen offer the restart.
            advance()
        }
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
            openScreenSettingsOnce()
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
