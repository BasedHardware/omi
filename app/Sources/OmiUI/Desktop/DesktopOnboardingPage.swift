import OmiKit
import SwiftUI
#if !SKIP
// danielsaidi/OnboardingKit (MIT) powers the USP list and the primary
// button on Apple platforms. Skip cannot transpile it, so Android uses
// the native path below.
import OnboardingKit
#if DEBUG
import Inject
#endif
#endif

// Port of `DesktopOnboarding.tsx`: the signed-out window. Introduces data use
// before sign-in, offers optional permissions without starting capture, and
// requires explicit setup completion (docs/desktop-app.md). Window sizing is
// the host's job; this surface draws one centered card.
// The step vocabulary and itinerary come from the shared `DesktopOnboardingStep`
// (`App/OnboardingFlow.swift`).

struct DesktopOnboardingPage: View {
    #if !SKIP && DEBUG
    @ObserveInjection var inject
    #endif
    @EnvironmentObject var store: AppStore
    let returning: Bool

    @Environment(\.desktopTokens) private var tokens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var step: DesktopOnboardingStep
    /// +1 moving forward, -1 moving back — picks the card-content slide edge.
    @State private var navigationDirection = 1
    @State private var permissionStates: [PermissionKind: PermissionState] = [:]
    @State private var pendingPermission: PermissionKind?

    init(returning: Bool) {
        self.returning = returning
        // `-omiOnboardingStep <rank>` (host debug affordance, mirroring
        // `-omiDemoData`): open the signed-out flow directly on a step so
        // screenshot verification can reach every card without driving the
        // UI. Ignored unless it names a valid signed-out step.
        let arguments = ProcessInfo.processInfo.arguments
        if let index = arguments.firstIndex(of: "-omiOnboardingStep"),
            index + 1 < arguments.count,
            let rank = Int(arguments[index + 1]),
            let named = desktopItinerary(signedIn: false).first(where: { $0.rank == rank })
        {
            _step = State(initialValue: named)
        } else if let saved = UserDefaults.standard.string(forKey: Self.stepKey),
            let named = DesktopOnboardingStep(rawValue: saved),
            named != .welcome, named != .signIn
        {
            // A permission grant can force a relaunch. Come back to the
            // step that was open, not Welcome.
            _step = State(initialValue: named)
        } else {
            _step = State(
                initialValue: returning
                    ? DesktopOnboardingStep.signIn : DesktopOnboardingStep.welcome)
        }
    }

    var body: some View {
        // No stage fill. The host window is transparent; the card is the
        // only painted surface.
        VStack(spacing: 0) {
            Spacer(minLength: 0)
            onboardingCard
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
        .onChange(of: store.authState) { _, state in
            // A finished sign-in used to leave this card on the sign-in
            // step, which looks exactly like a silent failure. A relaunch
            // after a permission grant must land here too, not on Welcome.
            if state == .onboarding || state == .signedIn {
                advancePastSignIn()
            }
        }
        .task {
            if store.authState == .onboarding || store.authState == .signedIn {
                advancePastSignIn()
            }
            if step == .permissions {
                await askOutstandingPermissions()
            }
        }
        .task(id: step) {
            guard step == .permissions else { return }
            await askOutstandingPermissions()
            while !Task.isCancelled {
                let latest = await store.permissionStatus()
                if latest != permissionStates {
                    permissionStates = latest
                }
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
        .accessibilityLabel("Omi onboarding")
        #if !SKIP && DEBUG
        .enableInjection()
        #endif
    }

    // MARK: The card

    private var onboardingCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            cardHeader
            stepStage
                .padding(.top, 22)
            progressCapsules
                .padding(.top, 22)
            navigationRow
                .padding(.top, 14)
        }
        .padding(28)
        .frame(maxWidth: 480)
        .background(cardPlate)
        .padding(.horizontal, 28)
    }

    /// Opaque plate. The shared glass tokens are 8–14% white, which is why
    /// the previous card washed out against the desktop. Onboarding needs
    /// a real surface so title, body, and corners hold.
    private var cardPlate: some View {
        let fill = tokens.isLight
            ? Color(red: 1, green: 0.992, blue: 0.973)
            : Color(red: 0.102, green: 0.110, blue: 0.094)
        let stroke = tokens.isLight
            ? Color.black.opacity(0.10)
            : Color.white.opacity(0.14)
        return RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(fill)
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .strokeBorder(stroke, lineWidth: 1)
            )
            .shadow(
                color: Color.black.opacity(tokens.isLight ? 0.18 : 0.28),
                radius: 18, x: 0, y: 10)
    }

    private var cardHeader: some View {
        HStack(spacing: 10) {
            OmiMark(
                ink: tokens.isLight
                    ? Color(red: 0.11, green: 0.12, blue: 0.10) : Color.white,
                animated: !reduceMotion
            )
            .frame(width: 28, height: 28)
            Text("OMI")
                .font(.system(size: 13, weight: .semibold))
                .tracking(1.6)
                .foregroundStyle(cardInk)
            Spacer(minLength: 0)
            Text(label(for: step))
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(cardInk.opacity(0.55))
        }
    }

    /// Title ink that does not depend on the translucent glass tokens.
    private var cardInk: Color {
        tokens.isLight
            ? Color(red: 0.11, green: 0.12, blue: 0.10)
            : Color(red: 0.965, green: 0.957, blue: 0.933)
    }

    private var cardMuted: Color {
        cardInk.opacity(0.82)
    }

    /// Fixed stage so steps of different heights never resize the card or
    /// fight for layout mid-transition.
    private var stepStage: some View {
        ZStack(alignment: .topLeading) {
            stepContent
                .id(step)
                .transition(stepBeat)
        }
        .frame(minHeight: 220, alignment: .topLeading)
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    /// Direction-aware step beat: content crossfades over a 10pt drift.
    /// SkipUI has no `AnyTransition.modifier`, so this composes the
    /// built-in offset/opacity transitions.
    private var stepBeat: AnyTransition {
        if reduceMotion { return .opacity }
        return AnyTransition
            .opacity
            .combined(with: .offset(x: 0, y: 10 * CGFloat(navigationDirection)))
    }

    @ViewBuilder
    private var stepContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title(for: step))
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(cardInk)
                .fixedSize(horizontal: false, vertical: true)
            stepBody
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Step titles (DesktopOnboarding.tsx `titles`).
    private func title(for step: DesktopOnboardingStep) -> String {
        switch step {
        case DesktopOnboardingStep.welcome: return "A little less to remember."
        case DesktopOnboardingStep.value: return "Here's what I do."
        case DesktopOnboardingStep.signIn: return "Make yourself at home."
        case DesktopOnboardingStep.permissions: return "Now the permissions."
        case DesktopOnboardingStep.harnesses: return "Meet your next collaborators."
        case DesktopOnboardingStep.data: return "Your world, connected."
        case DesktopOnboardingStep.tutorial: return "Everything has its place."
        case DesktopOnboardingStep.finish: return "Ready when you are."
        }
    }

    /// Step labels (DesktopOnboarding.tsx `stepLabels`).
    private func label(for step: DesktopOnboardingStep) -> String {
        switch step {
        case DesktopOnboardingStep.welcome: return "Welcome"
        case DesktopOnboardingStep.value: return "Meet Omi"
        case DesktopOnboardingStep.signIn: return "Your account"
        case DesktopOnboardingStep.permissions: return "Permissions"
        case DesktopOnboardingStep.harnesses: return "AI assistants"
        case DesktopOnboardingStep.data: return "Connect data"
        case DesktopOnboardingStep.tutorial: return "A quick look"
        case DesktopOnboardingStep.finish: return "Get started"
        }
    }

    // MARK: Progress capsules

    private var progressCapsules: some View {
        HStack(spacing: 6) {
            ForEach(
                desktopProgressSteps(signedIn: store.authState == AuthUiState.signedIn),
                id: \.self
            ) { candidate in
                let reached = candidate.rank <= step.rank
                Capsule()
                    .fill(reached ? cardInk : cardInk.opacity(0.32))
                    .frame(width: reached ? 22 : 8, height: 4)
                    .animation(DesktopMotion.smoothOut(DesktopMotion.settleMs), value: step)
                    .accessibilityLabel(label(for: candidate))
            }
            Spacer(minLength: 0)
        }
        .accessibilityLabel("Onboarding progress")
    }

    // MARK: Steps

    @ViewBuilder
    private var stepBody: some View {
        switch step {
        case DesktopOnboardingStep.welcome:
            Text(
                "Omi listens to your day, remembers what matters, and answers when you ask — right on your Mac."
            )
            .font(.system(size: 15))
            .foregroundStyle(cardMuted)
            .fixedSize(horizontal: false, vertical: true)
        case DesktopOnboardingStep.value:
            claimList([
                OnboardingClaim(
                    icon: DesktopIcon.history,
                    title: "Recall anything you saw",
                    detail: "Omi keeps a private, local record of your screen so you can find anything again."
                ),
                OnboardingClaim(
                    icon: DesktopIcon.chatBubble,
                    title: "Ask about your day",
                    detail: "Conversations, meetings, and tasks become memories you can search and question."
                ),
                OnboardingClaim(
                    icon: DesktopIcon.checklist,
                    title: "Stay on top of tasks",
                    detail: "Commitments surface as tasks before they slip."
                ),
            ])
        case DesktopOnboardingStep.signIn:
            VStack(alignment: .leading, spacing: 16) {
                Text("Sign in to load your conversations, memories, and tasks.")
                    .font(.system(size: 15))
                    .foregroundStyle(cardMuted)
                    .fixedSize(horizontal: false, vertical: true)
                if let error = store.signInErrorCopy {
                    Text(error)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(tokens.red)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel(error)
                }
                signInButton
            }
        case DesktopOnboardingStep.permissions:
            VStack(alignment: .leading, spacing: 10) {
                Text("Optional. Omi asks macOS for each of these; nothing starts until you turn capture on yourself.")
                    .font(.system(size: 14))
                    .foregroundStyle(cardMuted)
                    .fixedSize(horizontal: false, vertical: true)
                permissionRow(PermissionKind.screen, "Screen", "Remember what you're working on.")
                permissionRow(PermissionKind.microphone, "Microphone", "Turn conversations into memories.")
                permissionRow(PermissionKind.bluetooth, "Bluetooth", "Connect to your Omi device.")
                permissionRow(PermissionKind.notifications, "Notifications", "A nudge when something needs you.")
            }
        case DesktopOnboardingStep.harnesses:
            claimList([
                OnboardingClaim(
                    icon: DesktopIcon.chatBubble,
                    title: "Your assistants stay in the loop",
                    detail: "Connect the AI helpers you already use; Omi shares only what you allow."
                ),
            ])
        case DesktopOnboardingStep.data:
            claimList([
                OnboardingClaim(
                    icon: DesktopIcon.timeline,
                    title: "Your world, connected",
                    detail: "Calendars, notes, and apps plug in under Apps — and stay under your control."
                ),
            ])
        case DesktopOnboardingStep.tutorial:
            claimList([
                OnboardingClaim(
                    icon: DesktopIcon.home,
                    title: "Home is your day",
                    detail: "One timeline of conversations, memories, tasks, and recall captures."
                ),
                OnboardingClaim(
                    icon: DesktopIcon.search,
                    title: "Search recalls anything",
                    detail: "The omnibar searches what you've seen and heard."
                ),
            ])
        case DesktopOnboardingStep.finish:
            VStack(alignment: .leading, spacing: 16) {
                Text("Everything has its place: Home for your day, Search to recall, and the omnibar to ask.")
                    .font(.system(size: 15))
                    .foregroundStyle(cardMuted)
                    .fixedSize(horizontal: false, vertical: true)
                primaryButton("Get started", label: "Complete setup") {
                    Task { await store.completeOnboarding() }
                }
            }
        }
    }

    private var signInButton: some View {
        let busy = store.authState == AuthUiState.signingIn
        let title = busy
            ? "Signing in…"
            : (returning ? "Welcome back — sign in" : "Continue with Google")
        return primaryButton(title, label: "Sign in", busy: busy) {
            Task { await store.startSignIn() }
        }
        .disabled(busy)
    }

    #if !SKIP
    /// Claim rows ride OnboardingKit's staggered USP list, restyled onto
    /// the opaque card so the library's default light-on-light type cannot
    /// wash out.
    private func claimList(_ claims: [OnboardingClaim]) -> some View {
        OnboardingUspList(
            usps: claims.map { claim in
                OnboardingUsp(
                    title: LocalizedStringResource(stringLiteral: claim.title),
                    text: LocalizedStringResource(stringLiteral: claim.detail),
                    icon: {
                        claim.icon
                            .frame(width: 16, height: 16)
                            .foregroundStyle(cardInk)
                            .frame(width: 36, height: 36)
                            .background(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(cardInk.opacity(0.08))
                            )
                    }
                )
            }
        )
        .onboardingUspListStyle(
            OnboardingUspListStyle(
                padding: 0,
                itemSpacing: 14,
                itemPresentationDuration: reduceMotion ? 0 : 0.22,
                itemPresentationDelay: reduceMotion ? 0 : 0.05
            )
        )
        .onboardingUspListItemStyle(
            OnboardingUspListItemStyle(
                iconSize: 36,
                titleColor: cardInk,
                titleFont: .system(size: 15, weight: .semibold),
                textColor: cardMuted,
                textFont: .system(size: 13)
            )
        )
    }
    #else
    private func claimList(_ claims: [OnboardingClaim]) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Array(claims.enumerated()), id: \.offset) { _, claim in
                valueClaim(icon: claim.icon, title: claim.title, detail: claim.detail)
            }
        }
    }

    private func valueClaim(icon: DesktopIcon, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            icon
                .frame(width: 16, height: 16)
                .foregroundStyle(cardInk)
                .frame(width: 36, height: 36)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(cardInk.opacity(0.08))
                )
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(cardInk)
                Text(detail)
                    .font(.system(size: 13))
                    .foregroundStyle(cardMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
    #endif

    private func permissionRow(
        _ kind: PermissionKind, _ title: String, _ detail: String
    ) -> some View {
        let state = permissionStates[kind] ?? .unknown
        let busy = pendingPermission == kind
        let label = busy ? "Asking…" : state == .granted ? "Allowed" : "Allow"
        return HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(cardInk)
                Text(detail)
                    .font(.system(size: 12))
                    .foregroundStyle(cardMuted)
            }
            Spacer(minLength: 8)
            Button(label) {
                Task { await askPermission(kind) }
            }
            .buttonStyle(.plain)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(state == .granted ? Color.white : cardInk)
            .padding(.horizontal, 12)
            .frame(minHeight: 32)
            .background(
                Capsule()
                    .fill(state == .granted ? Color(red: 0.09, green: 0.55, blue: 0.36) : Color.clear)
                    .overlay(
                        Capsule().strokeBorder(
                            state == .granted
                                ? Color.clear : cardInk.opacity(0.28),
                            lineWidth: 1)
                    )
            )
            .disabled(busy || state == .granted)
            .accessibilityLabel("Allow \(title)")
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(cardInk.opacity(0.06))
        )
    }

    // MARK: Card navigation

    private var navigationRow: some View {
        HStack(spacing: 12) {
            if previousDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) != nil {
                Button("Back") {
                    previous()
                }
                .buttonStyle(.plain)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(cardMuted)
                .frame(minHeight: 36)
                .accessibilityLabel("Back")
            }
            Spacer(minLength: 0)
            if nextDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) != nil,
                step != DesktopOnboardingStep.signIn,
                step != DesktopOnboardingStep.finish
            {
                primaryButton("Continue", label: "Continue", compact: true) {
                    advance()
                }
            }
        }
    }

    /// Solid primary. OnboardingKit's glass button is a system glass style
    /// that disappears on this card; the library still drives the USP list.
    private func primaryButton(
        _ title: String,
        label: String,
        busy: Bool = false,
        compact: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        let ink = tokens.isLight ? Color.white : Color(red: 0.09, green: 0.10, blue: 0.08)
        let fill = tokens.isLight
            ? Color(red: 0.11, green: 0.12, blue: 0.10)
            : Color(red: 0.965, green: 0.957, blue: 0.933)
        return Button(action: action) {
            HStack(spacing: 8) {
                if busy {
                    OmiLoadingMark(size: 16, ink: ink)
                }
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(ink)
            }
            .frame(maxWidth: compact ? nil : .infinity, minHeight: 42)
            .padding(.horizontal, compact ? 18 : 16)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous).fill(fill)
            )
        }
        .buttonStyle(GlassPressableStyle())
        .accessibilityLabel(label)
    }

    /// The permissions step asks itself. Allow stays for a retry; the
    /// system prompt is the only UI, and Settings is never opened.
    private func askOutstandingPermissions() async {
        let current = await store.permissionStatus()
        permissionStates = current
        for kind in [PermissionKind.screen, .microphone, .bluetooth, .notifications]
        where current[kind] != .granted {
            await askPermission(kind)
        }
    }

    private func askPermission(_ kind: PermissionKind) async {
        guard pendingPermission == nil else { return }
        pendingPermission = kind
        defer { pendingPermission = nil }
        let state = await store.requestPermission(kind)
        permissionStates[kind] = state
    }

    private func advancePastSignIn() {
        guard step == .signIn else { return }
        guard let next = nextDesktopStep(step, signedIn: true) else { return }
        navigationDirection = 1
        withAnimation(DesktopMotion.stepAnimation(reduceMotion)) {
            step = next
        }
        rememberStep()
    }

    private static let stepKey = "omi.onboarding.desktopStep"

    private func rememberStep() {
        if step == .welcome || step == .signIn {
            UserDefaults.standard.removeObject(forKey: Self.stepKey)
        } else {
            UserDefaults.standard.set(step.rawValue, forKey: Self.stepKey)
        }
    }

    private func advance() {
        guard let next = nextDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) else {
            return
        }
        navigationDirection = 1
        withAnimation(DesktopMotion.stepAnimation(reduceMotion)) {
            step = next
        }
        rememberStep()
    }

    private func previous() {
        guard let back = previousDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) else {
            return
        }
        navigationDirection = -1
        withAnimation(DesktopMotion.stepAnimation(reduceMotion)) {
            step = back
        }
        rememberStep()
    }
}

/// One onboarding claim. A struct, not a labeled tuple — Skip's Kotlin
/// tuples forbid the same label at different positions.
struct OnboardingClaim: Identifiable {
    let icon: DesktopIcon
    let title: String
    let detail: String
    var id: String { title }
}

/// Eight-dot Omi mark. Positions are the 260-canvas centers from
/// `OmiAvatar.tsx`. When animated, a brightness lap walks the ring the
/// way the product mark does (900 ms, idle at half brightness).
struct OmiMark: View {
    var ink: Color
    var animated = false

    @State private var phase: Double = 0

    private static let centers: [(CGFloat, CGFloat)] = [
        (129.5, 42.8), (194.5, 64.5), (216.2, 129.5), (194.5, 194.5),
        (129.5, 216.2), (64.5, 194.5), (42.8, 129.5), (64.5, 64.5),
    ]

    var body: some View {
        GeometryReader { proxy in
            let scale = min(proxy.size.width, proxy.size.height) / 260
            ZStack(alignment: .topLeading) {
                ForEach(Array(OmiMark.centers.enumerated()), id: \.offset) { index, center in
                    Circle()
                        .fill(ink)
                        .opacity(brightness(index))
                        .frame(width: 34.4 * scale, height: 34.4 * scale)
                        .offset(
                            x: (center.0 - 17.2) * scale,
                            y: (center.1 - 17.2) * scale)
                }
            }
        }
        .onAppear {
            guard animated else { return }
            phase = 0
            withAnimation(.linear(duration: 0.9).repeatForever(autoreverses: false)) {
                phase = 1
            }
        }
        .accessibilityHidden(true)
    }

    /// Port of `omiMarkBrightness`: a pulse walks the eight dots.
    private func brightness(_ index: Int) -> Double {
        guard animated else { return 1 }
        let peak = Double(index) / 8
        var distance = abs(phase - peak)
        if distance > 0.5 { distance = 1 - distance }
        let bump = max(0, 1 - distance / 0.22)
        // Stay readable at 22pt. The old 0.5 floor made the mark look broken.
        return 0.72 + 0.28 * bump
    }
}
