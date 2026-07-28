import AppKit
import Combine
import SwiftUI

/// Five screens, one thought each: who I am, whose account this is, what I need, who I tell, and
/// where I live.
///
/// `@MainActor` on the whole view, not on the handful of members that read `OmiAuth`: `body` is
/// already main-actor isolated, so every computed screen and every step function is reached from
/// the main actor anyway, and annotating them one at a time only invites the next one to be missed.
@MainActor
struct OnboardingView: View {
    /// Four screens, and only the first two ask anything of the user. `setup` runs itself.
    private enum Step {
        case intro, signIn, setup, done
    }

    /// Fixed order. Microphone first because it is the one people expect; the system tap second
    /// because it only makes sense once the mic has been explained.
    private let capabilities: [Capability] = [.microphone, .systemAudio, .screen]

    /// Owned by the auth layer, observed here. Everything Earshot records lands in this account, so
    /// the step machine asks it who the user is before it asks macOS for a microphone.
    @ObservedObject private var auth = OmiAuth.shared

    @State private var step: Step = .intro
    @State private var settled = false

    @State private var granted: [Capability: Bool] = [:]
    @State private var asked: Set<Capability> = []
    @State private var requesting: Set<Capability> = []
    @State private var reported = false
    @State private var needsRelaunch = false

    @State private var registration: String?
    @State private var modelProgress: Double?
    @State private var warmingModels = false

    @State private var granting = false
    @State private var openedScreenSettings = false
    @State private var cueDrift = false
    @State private var finale = false

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
        case .intro: intro
        case .signIn: signIn
        case .setup: setup
        case .done: done
        }
    }

    // MARK: - 1. Intro

    private var intro: some View {
        VStack(spacing: 24) {
            RandomizedText(
                segments: [
                    ("Hi, I’m Earshot. I keep ", .plain),
                    ("Claude", .bold),
                    (" caught up on what you ", .plain),
                    ("see and say", .bold),
                    (".", .plain),
                ],
                style: .introHero
            )
            .multilineTextAlignment(.center)
            .foregroundStyle(Ink.cream)
            .shadow(color: .black.opacity(0.45), radius: 12, y: 1)

            // The button arrives after the last word does; offering it mid-sentence invites a
            // click before the sentence has been read.
            InkButton("Turn me on") { go(to: firstAsk) }
                .opacity(settled ? 1 : 0)
                .animation(stepAnimation, value: settled)
        }
    }

    // MARK: - 2. Sign in — before anything is recorded, not after

    /// The one screen with a real choice on it. It exists because everything Earshot hears lands in
    /// an Omi account, and starting to record before knowing which account that is would be wrong.
    private var signIn: some View {
        VStack(spacing: 14) {
            Text("Which account is this?")
                .inkStyle(.stepHeadline)
                .foregroundStyle(Ink.cream)

            Text("Everything I hear and see goes into your Omi account — nowhere else.")
                .inkStyle(.prose)
                .foregroundStyle(Ink.creamHint)
                .fixedSize(horizontal: false, vertical: true)

            if isWaitingForBrowser {
                VStack(spacing: 12) {
                    Text("Waiting for your browser…")
                        .inkStyle(.statusLabel)
                        .foregroundStyle(Ink.creamDim)

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
                go(to: .setup)
            } catch {
                guard step == .signIn else { return }
                signInError = error.localizedDescription
            }
        }
    }

    // MARK: - 3. Setup — one click, then it runs itself

    private var setup: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(setupTitle)
                .inkStyle(.firstTitle)
                .foregroundStyle(Ink.cream)

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

            if let registration {
                Text(registration)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(Ink.creamDim)
                    .fixedSize(horizontal: false, vertical: true)
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

    private var setupTitle: String {
        // "First…" only survives for a run that never signed in; once the account is known, the
        // permissions are no longer the first thing being asked for.
        if !granting { return auth.isSignedIn ? "Now the permissions." : "First…" }
        return "Say yes and I\u{2019}m yours."
    }

    // MARK: - 4. Done

    private var done: some View {
        VStack(spacing: 14) {
            Text(isGranted(.screen) ? "I’m listening." : "One more thing.")
                .inkStyle(.stepHeadline)
                .foregroundStyle(Ink.cream)

            Text(isGranted(.screen)
                 ? homeLine
                 : "Switch me on under Screen Recording — I just opened it for you. I’ll take it from there.")
                .inkStyle(.prose)
                .foregroundStyle(Ink.creamHint)
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

    /// Where I live, and — once there is an account — where the recordings go. Said once, here,
    /// because it is the last thing on screen and the only place it is still news.
    private var homeLine: String {
        auth.isSignedIn ? "I live up here, and everything lands in your Omi account." : "I live up here."
    }

    /// The window sits inside `visibleFrame`, so its top-trailing corner is directly beneath the
    /// menu bar item. A drifting chevron points at it; a drawn menu bar would be a lie.
    private var menuBarCue: some View {
        Image(systemName: "chevron.up")
            .font(.system(size: 17, weight: .medium))
            .foregroundStyle(Ink.creamHint)
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

    private func edgeGlow(in size: CGSize) -> some View {
        RadialGradient(
            gradient: Gradient(stops: [
                .init(color: Ink.cream.opacity(0), location: 0.3),
                .init(color: Ink.cream.opacity(0.14), location: 0.7),
                .init(color: Ink.cream.opacity(0.6), location: 1),
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

    private var columnWidth: CGFloat {
        step == .setup ? InkLayout.permissionsMaxWidth : InkLayout.contentMaxWidth
    }
    private var columnAlignment: Alignment { step == .setup ? .leading : .center }

    /// What the single button on the first screen actually starts. A restored session skips the
    /// question entirely, so a reinstall stays one click.
    private var firstAsk: Step {
        auth.isSignedIn ? .setup : .signIn
    }

    /// The backdrop drifts only while something is genuinely happening. Waiting on a browser counts,
    /// and it keeps drifting through a cancelled wait, because the round trip is still open.
    private var working: Bool {
        switch step {
        case .signIn: return auth.isSigningIn
        case .setup: return granting || warmingModels
        case .intro, .done: return false
        }
    }

    private var stepAnimation: Animation? {
        InkReduceMotion.isEnabled ? nil : .easeOut(duration: 0.24)
    }

    private func transition(in size: CGSize) -> AnyTransition {
        guard !InkReduceMotion.isEnabled else { return .opacity }
        return .opacity.combined(with: .offset(y: size.height * 0.015))
    }

    private func go(to next: Step) {
        settled = false
        withAnimation(stepAnimation) { step = next }
        beginStep()
    }

    private func beginStep() {
        switch step {
        case .intro:
            // The word-by-word reveal runs for 1200 ms; the step is not settled until it lands.
            scheduleSettle(after: 1.2)
        case .signIn:
            scheduleSettle(after: 0.34)
        case .setup:
            refreshPermissions()
            runSetup()
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
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            guard step == target else { return }
            withAnimation(.easeOut(duration: 0.28)) { settled = true }
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
        granted = next
        needsRelaunch = Permissions.screenNeedsRelaunch
        reported = true

        // No continue button anywhere: the step ends the moment the grants are real.
        guard step == .setup, !granting, capabilities.allSatisfy({ next[$0] == true }) else { return }
        go(to: .done)
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
    /// The permissions are requested one at a time rather than all at once: macOS shows one TCC
    /// alert at a time, and firing three concurrently stacks dialogs the user answers blind. Each
    /// grant is re-read before moving on so a refusal is visible immediately in its row.
    ///
    /// Registration and the login item happen at the end, whether or not every permission landed —
    /// Claude should be able to reach Earshot and report the gap, which is far better than Earshot
    /// being invisible because a microphone was declined.
    private func runSetup() {
        guard !granting else { return }
        granting = true

        Task { @MainActor in
            for capability in capabilities where !isGranted(capability) {
                asked.insert(capability)
                requesting.insert(capability)
                _ = await Permissions.request(capability)
                requesting.remove(capability)
                refreshPermissions()
            }

            startRegistration()
            if !LoginItem.isEnabled { _ = LoginItem.enable() }
            warmModels()

            granting = false
            // Give the last row's checkmark a beat to land before the card changes under it.
            try? await Task.sleep(nanoseconds: 600_000_000)
            refreshPermissions()

            // Screen Recording is granted in System Settings and only takes effect in a new
            // process, so it never satisfies `refreshPermissions` in this one. Move on anyway and
            // let the last screen offer the restart.
            if step == .setup { go(to: .done) }
        }
    }

    // MARK: - Registration and models

    private func startRegistration() {
        Task { @MainActor in
            let message = await Task.detached(priority: .userInitiated) {
                ClaudeRegistrar.register().message
            }.value
            registration = message
            EarshotLog.info("claude registration: \(message)", "onboarding")
        }
    }

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
                EarshotLog.error("transcription model warm-up failed: \(error)", "onboarding")
            }
            warmingModels = false
            modelProgress = nil
        }
    }

    // MARK: - Finale

    private func finish() {
        if !LoginItem.enable() {
            EarshotLog.error("could not register as a login item", "onboarding")
        }
        UserDefaults.standard.set(true, forKey: "earshot.onboarded")

        // Screen Recording is the one grant macOS will not take from a dialog — it has to be
        // switched on in System Settings, and it only takes effect in a new process. Dismissing
        // here would leave the user believing setup finished with a third of it dead, so the card
        // stays, opens the right pane itself, and waits.
        guard isGranted(.screen) else {
            openScreenSettingsOnce()
            return
        }

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_600_000_000)
            guard step == .done, isGranted(.screen) else { return }
            withAnimation(.easeOut(duration: InkReduceMotion.isEnabled ? 0 : 0.55)) { finale = true }
            OnboardingWindow.dismiss()
        }
    }

    /// Opens the Screen Recording pane once, then watches for the grant and relaunches into it —
    /// so the user's part is one toggle, with no button to find afterwards.
    private func openScreenSettingsOnce() {
        guard !openedScreenSettings else { return }
        openedScreenSettings = true
        Permissions.openSettings(for: .screen)

        Task { @MainActor in
            while step == .done, !Permissions.check(.screen) {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
            guard step == .done, Permissions.check(.screen) else { return }
            granted[.screen] = true
            // The grant is real but this process cannot use it. Relaunching is the whole remedy.
            try? await Task.sleep(nanoseconds: 700_000_000)
            Permissions.relaunchApp()
        }
    }
}
