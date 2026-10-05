import OmiKit
import SwiftUI

// Mobile onboarding, port of `react-native/src/ui/Onboarding.tsx` in the
// OnBoardingKit/OnboardingKit card style: one centered card floating on the
// calm full-bleed background, hero tile + title + body, progress dots, a
// primary CTA, Back where applicable, and a direction-aware quick beat
// between steps. The step vocabulary and ordering come from the shared
// `MobileOnboardingStep` (`App/OnboardingFlow.swift`) — never a parallel one.
//
// Every step performs a real action through the store: consent/name/language/
// source/speech/knowledge persist through `AppStore.setPreference` (the same
// `SettingsStoring` write path the desktop explore checklist uses), the
// permissions step calls `store.requestPermission`, and completion calls
// `store.completeOnboarding()` (the explicit `completeSetup` port).

// MARK: - Page

public struct MobileOnboardingPage: View {
    @EnvironmentObject private var store: AppStore
    /// Completed setup before → Welcome-back sign-in card first.
    let returning: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var step: MobileOnboardingStep
    /// +1 forward, −1 back — picks the card-content drift direction.
    @State private var navigationDirection = 1
    @State private var localError: String?
    @State private var savingStep = false

    // Step answers.
    @State private var consentAt: String?
    @State private var name = ""
    @State private var languageCode = "en"
    @State private var source: String?
    @State private var otherSource = ""
    @State private var permissionStates: [PermissionKind: PermissionState] = [:]
    @State private var pendingPermission: PermissionKind?
    @State private var speechChoice: String?
    @State private var knowledgeOptIn = true

    private let itinerary = mobileOnboardingItinerary()

    public init(returning: Bool) {
        self.returning = returning
        _step = State(
            initialValue: MobileOnboardingStep.welcome)
    }

    private var setupIndex: Int { mobileOnboardingRank(step, itinerary: itinerary) }

    public var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 0)
            onboardingCard
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(MobilePalette.background)
        .accessibilityLabel("Omi onboarding")
    }

    // MARK: The card

    private var onboardingCard: some View {
        VStack(spacing: 20) {
            stepStage
            progressDots
            navigationRow
        }
        .padding(24)
        .frame(maxWidth: 440)
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(Color(red: 0.102, green: 0.110, blue: 0.094))
                .overlay(
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.14), lineWidth: 1)
                )
                .shadow(color: Color.black.opacity(0.45), radius: 28, x: 0, y: 16)
        )
        .padding(.horizontal, MobileSpace.xl)
    }

    /// Fixed stage so steps of different heights never resize the card
    /// mid-transition.
    private var stepStage: some View {
        ZStack {
            stepContent
                .id(step)
                .transition(stepBeat)
        }
        .frame(minHeight: 320)
    }

    /// Direction-aware step beat (DesktopOnboardingPage's `stepBeat`, mobile
    /// sized): crossfade over a 12pt drift in the navigation direction at 98%
    /// scale. Reduce Motion settles in place with no transition.
    private var stepBeat: AnyTransition {
        if reduceMotion { return .opacity }
        return AnyTransition
            .opacity
            .combined(with: .offset(x: 0, y: 12 * CGFloat(navigationDirection)))
            .combined(with: .scale(scale: 0.98))
    }

    private var stepAnimation: Animation? {
        reduceMotion ? nil : Animation.easeOut(duration: 0.25)
    }

    // MARK: Progress dots

    private var progressDots: some View {
        HStack(spacing: 8) {
            ForEach(itinerary, id: \.self) { candidate in
                let reached = mobileOnboardingRank(
                    MobileOnboardingStep.setup(candidate), itinerary: itinerary)
                    <= setupIndex
                Capsule()
                    .fill(reached ? MobilePalette.text : MobilePalette.surfaceRaised)
                    .frame(width: reached ? 22.0 : 12.0, height: 5.0)
                    .animation(stepAnimation, value: step)
                    .accessibilityLabel(label(for: .setup(candidate)))
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityLabel("Onboarding progress")
    }

    // MARK: Card navigation

    private var navigationRow: some View {
        HStack {
            if canGoBack {
                Button(action: goBack) {
                    HStack(spacing: 4) {
                        KitIcon(.chevronLeft, size: 16, color: MobilePalette.textMuted)
                        Text("Back")
                            .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                            .foregroundColor(MobilePalette.textMuted)
                    }
                    .frame(minHeight: 44)
                }
                .buttonStyle(KitPressableStyle())
                .accessibilityLabel("Back")
            }
            Spacer(minLength: 0)
        }
    }

    private var canGoBack: Bool {
        guard store.authState != AuthUiState.signingIn else { return false }
        guard case .setup(let setup) = step, setup != .consent, setup != .complete else {
            return false
        }
        return previousMobileSetupStep(setup, itinerary: itinerary) != nil
    }

    private func goBack() {
        guard case .setup(let setup) = step,
            let back = previousMobileSetupStep(setup, itinerary: itinerary)
        else { return }
        localError = nil
        navigationDirection = -1
        withAnimation(stepAnimation) { step = .setup(back) }
    }

    private func advance(from setup: MobileSetupStep) {
        guard let next = nextMobileSetupStep(setup, itinerary: itinerary) else {
            return
        }
        localError = nil
        navigationDirection = 1
        withAnimation(stepAnimation) { step = .setup(next) }
    }

    // MARK: Step content

    @ViewBuilder
    private var stepContent: some View {
        VStack(spacing: 16) {
            heroTile
            Text(title(for: step))
                .font(TypeStyle(size: 26, lineHeight: 32, weight: .semibold).font)
                .foregroundColor(Color(red: 0.965, green: 0.957, blue: 0.933))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            stepBody
            if let error = localError {
                Text(error)
                    .font(MobileType.caption.font)
                    .foregroundColor(Palette.danger)
                    .multilineTextAlignment(.center)
                    .accessibilityLabel(error)
            }
            primaryCTA
        }
    }

    @ViewBuilder
    private var heroTile: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 18)
                .fill(MobilePalette.surfaceRaised)
            heroIcon
                .frame(width: 26, height: 26)
                .foregroundColor(MobilePalette.text)
        }
        .frame(width: 64, height: 64)
    }

    @ViewBuilder
    private var heroIcon: some View {
        switch step {
        case .welcome:
            OmiAvatarShape()
        case .setup(let setup):
            switch setup {
            case .consent:
                KitIcon(.check, size: 26, color: MobilePalette.text)
            case .name:
                OmiAvatarShape()
            case .language:
                KitIcon(.chatBubble, size: 26, color: MobilePalette.text)
            case .source:
                KitIcon(.search, size: 26, color: MobilePalette.text)
            case .permissions:
                KitIcon(.settings, size: 26, color: MobilePalette.text)
            case .speech:
                KitIcon(.mic, size: 26, color: MobilePalette.text)
            case .knowledge:
                KitIcon(.puzzle, size: 26, color: MobilePalette.text)
            case .complete:
                KitIcon(.check, size: 26, color: MobilePalette.text)
            }
        }
    }

    private func title(for step: MobileOnboardingStep) -> String {
        switch step {
        case .welcome: return "A little less to remember."
        case .setup(let setup):
            switch setup {
            case .consent: return "Data & Privacy"
            case .name: return "What should Omi call you?"
            case .language: return "Select your primary language"
            case .source: return "How did you find us?"
            case .permissions: return "Grant permissions"
            case .speech: return "Teach Omi your voice"
            case .knowledge: return "Help Omi learn"
            case .complete: return "You are all set!"
            }
        }
    }

    private func label(for step: MobileOnboardingStep) -> String {
        switch step {
        case .welcome: return "Welcome"
        case .setup(let setup):
            switch setup {
            case .consent: return "Data & Privacy"
            case .name: return "Your name"
            case .language: return "Language"
            case .source: return "Discovery"
            case .permissions: return "Permissions"
            case .speech: return "Voice"
            case .knowledge: return "Learning"
            case .complete: return "Get started"
            }
        }
    }

    @ViewBuilder
    private var stepBody: some View {
        switch step {
        case .welcome:
            welcomeBody
        case .setup(let setup):
            switch setup {
            case .consent:
                consentBody
            case .name:
                nameBody
            case .language:
                languageBody
            case .source:
                sourceBody
            case .permissions:
                permissionsBody
            case .speech:
                speechBody
            case .knowledge:
                knowledgeBody
            case .complete:
                completeBody
            }
        }
    }

    private var welcomeBody: some View {
        Text(
            "Omi listens to your day, remembers what matters, and answers when you ask — right from your phone."
        )
        .font(MobileType.body.font)
        .foregroundColor(MobilePalette.textMuted)
        .multilineTextAlignment(.center)
    }

    /// Port of the consent copy (Onboarding.tsx `consent` step).
    private var consentBody: some View {
        VStack(spacing: 10) {
            Text(
                "By continuing, your conversations, recordings, and personal information will be securely stored on our servers. Your audio recordings and transcripts are processed by third-party AI services — Deepgram for transcription and OpenAI for analysis — to provide you with AI-powered insights and enable all app features."
            )
            .font(TypeStyle(size: 13, lineHeight: 19, weight: .regular).font)
            .foregroundColor(MobilePalette.textMuted)
            .multilineTextAlignment(.center)
            Text(
                "Your data is protected and governed by our Privacy Policy and Terms of Service."
            )
            .font(TypeStyle(size: 13, lineHeight: 19, weight: .regular).font)
            .foregroundColor(MobilePalette.textMuted)
            .multilineTextAlignment(.center)
            HStack(spacing: MobileSpace.lg) {
                Link("Privacy Policy", destination: URL(string: onboardingPrivacyURL)!)
                Link("Terms of Service", destination: URL(string: onboardingTermsURL)!)
            }
            .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
            .foregroundColor(Palette.focus)
            .accessibilityLabel("Privacy Policy and Terms of Service links")
        }
    }

    private var nameBody: some View {
        TextField(
            "Your name (optional)",
            text: $name,
            prompt: Text("Your name (optional)")
                .foregroundColor(MobilePalette.textSubtle)
        )
        .font(MobileType.body.font)
        .foregroundColor(MobilePalette.text)
        .padding(.horizontal, MobileSpace.md)
        .frame(minHeight: 44)
        .background(MobilePalette.surfaceQuiet)
        .overlay(
            RoundedRectangle(cornerRadius: MobileRadius.chip)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
        .accessibilityLabel("Your name")
    }

    /// Primary languages (`onboardingPrimaryLanguages`), selection committed
    /// by the Continue CTA.
    private var languageBody: some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], spacing: 8
        ) {
            ForEach(onboardingPrimaryLanguages, id: \.code) { item in
                let selected = languageCode == item.code
                Button(action: { languageCode = item.code }) {
                    Text(item.name)
                        .font(MobileType.caption.font)
                        .foregroundColor(
                            selected ? MobilePalette.background : MobilePalette.text
                        )
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(KitPressableStyle())
                .background(
                    RoundedRectangle(cornerRadius: MobileRadius.chip)
                        .fill(selected ? MobilePalette.text : MobilePalette.surfaceQuiet)
                )
                .accessibilityLabel(item.name)
                .accessibilityAddTraits(selected ? [.isSelected] : [])
            }
        }
    }

    private var sourceBody: some View {
        VStack(spacing: MobileSpace.md) {
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], spacing: 8
            ) {
                ForEach(onboardingAcquisitionSources, id: \.self) { item in
                    let selected = source == item
                    Button(action: { source = item }) {
                        Text(item)
                            .font(MobileType.caption.font)
                            .foregroundColor(
                                selected ? MobilePalette.background : MobilePalette.text
                            )
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(KitPressableStyle())
                    .background(
                        RoundedRectangle(cornerRadius: MobileRadius.chip)
                            .fill(selected ? MobilePalette.text : MobilePalette.surfaceQuiet)
                    )
                    .accessibilityLabel(item)
                    .accessibilityAddTraits(selected ? [.isSelected] : [])
                }
            }
            if source == "Other" {
                TextField(
                    "Where did you hear about us?",
                    text: $otherSource,
                    prompt: Text("Where did you hear about us?")
                        .foregroundColor(MobilePalette.textSubtle)
                )
                .font(MobileType.body.font)
                .foregroundColor(MobilePalette.text)
                .padding(.horizontal, MobileSpace.md)
                .frame(minHeight: 44)
                .background(MobilePalette.surfaceQuiet)
                .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
                .accessibilityLabel("Please specify")
            }
        }
    }

    /// Permissions (`PermissionRow` port). OmiKit's `PermissionKind` carries
    /// microphone + notifications on this path; Bluetooth is not a member
    /// (host-owned on phones).
    private var permissionsBody: some View {
        VStack(spacing: 10) {
            Text("Tap one when you're ready. Nothing is asked until you do.")
                .font(TypeStyle(size: 13, lineHeight: 19, weight: .regular).font)
                .foregroundColor(MobilePalette.textMuted)
                .multilineTextAlignment(.center)
            permissionRow(
                .notifications, "Notifications",
                "Notify you when something needs you.")
            permissionRow(
                .microphone, "Microphone",
                "Hear what you talk about, so Omi can help.")
        }
    }

    private func permissionRow(
        _ kind: PermissionKind, _ title: String, _ detail: String
    ) -> some View {
        let state = permissionStates[kind] ?? .unknown
        let granted = state == .granted
        let busy = pendingPermission == kind
        let status = busy ? "Asking…" : granted ? "Granted" : "Allow"
        return HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(TypeStyle(size: 14, lineHeight: 20, weight: .medium).font)
                    .foregroundColor(MobilePalette.text)
                Text(detail)
                    .font(TypeStyle(size: 12, lineHeight: 18, weight: .regular).font)
                    .foregroundColor(MobilePalette.textMuted)
            }
            Spacer(minLength: 0)
            Button(action: { Task { await requestPermission(kind) } }) {
                Text(status)
                    .font(TypeStyle(size: 12, lineHeight: 18, weight: .semibold).font)
                    .foregroundColor(granted ? MobilePalette.textMuted : Palette.focus)
                    .frame(minHeight: 44)
                    .padding(.horizontal, MobileSpace.sm)
            }
            .buttonStyle(KitPressableStyle())
            .disabled(granted || pendingPermission != nil)
            .accessibilityLabel("\(status) \(title)")
        }
        .padding(10)
        .background(MobilePalette.surfaceQuiet)
        .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
    }

    /// The upstream speech step records a 5-second voice print through
    /// getUserMedia + `uploadVoicePrint`. OmiKit has no voice-print capture
    /// or upload facade yet, so this card records the explicit skip through
    /// the real settings store instead of faking enrollment.
    private var speechBody: some View {
        Text(
            "So Omi knows which voice is yours — voice enrollment arrives with a firmware update. You can skip for now."
        )
        .font(MobileType.body.font)
        .foregroundColor(MobilePalette.textMuted)
        .multilineTextAlignment(.center)
    }

    /// The upstream tree has no knowledge step; this card is an explicit
    /// local preference (memory-learning opt-in) the Settings surface can
    /// surface later. It writes through the real settings store.
    private var knowledgeBody: some View {
        Button(action: { knowledgeOptIn.toggle() }) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Help Omi learn what matters")
                        .font(TypeStyle(size: 14, lineHeight: 20, weight: .medium).font)
                        .foregroundColor(MobilePalette.text)
                    Text("Omi highlights memories it thinks you'll need.")
                        .font(TypeStyle(size: 12, lineHeight: 18, weight: .regular).font)
                        .foregroundColor(MobilePalette.textMuted)
                }
                Spacer(minLength: 0)
                Text(knowledgeOptIn ? "On" : "Off")
                    .font(TypeStyle(size: 12, lineHeight: 18, weight: .semibold).font)
                    .foregroundColor(knowledgeOptIn ? Palette.focus : MobilePalette.textMuted)
            }
            .frame(minHeight: 44)
            .padding(10)
        }
        .buttonStyle(KitPressableStyle())
        .background(MobilePalette.surfaceQuiet)
        .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
        .accessibilityLabel("Help Omi learn what matters")
    }

    private var completeBody: some View {
        Text(
            "Just use Omi in the background for 2 days and you'll start getting useful feedback after."
        )
        .font(MobileType.body.font)
        .foregroundColor(MobilePalette.textMuted)
        .multilineTextAlignment(.center)
    }

    // MARK: Primary CTA (each step's bottom action)

    @ViewBuilder
    private var primaryCTA: some View {
        let busy = savingStep || store.completingSetup
        Button(action: { Task { await primaryAction() } }) {
            HStack(spacing: 8) {
                if busy || store.signingIn {
                    OmiLoadingMark(size: 16.0, ink: MobilePalette.background)
                } else {
                    Text(primaryLabel)
                        .font(TypeStyle(size: 15, lineHeight: 20, weight: .semibold).font)
                        .foregroundColor(MobilePalette.background)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(
                RoundedRectangle(cornerRadius: MobileRadius.chip)
                    .fill(MobilePalette.text)
            )
        }
        .buttonStyle(KitPressableStyle())
        .disabled(busy || store.signingIn)
        .accessibilityLabel(primaryLabel)
    }

    private var primaryLabel: String {
        switch step {
        case .welcome:
            if store.authState == AuthUiState.onboarding { return "Continue" }
            return store.signingIn ? "Signing in…"
                : (returning ? "Welcome back — sign in" : "Sign in")
        case .setup(let setup):
            switch setup {
            case .consent: return "Agree & Continue"
            case .name, .language: return "Continue"
            case .source: return savingStep ? "Saving…" : "Continue"
            case .permissions: return "I'll do these later"
            case .speech: return "Skip for now"
            case .knowledge: return "Continue"
            case .complete:
                return store.completingSetup ? "Saving…" : "Start using Omi"
            }
        }
    }

    @MainActor
    private func primaryAction() async {
        switch step {
        case .welcome:
            if store.authState == AuthUiState.onboarding {
                advance(from: itinerary.first ?? .consent)
            } else {
                await store.startSignIn()
            }
        case .setup(let setup):
            await commit(setup)
        }
    }

    /// The real action each setup step performs before moving on.
    @MainActor
    private func commit(_ setup: MobileSetupStep) async {
        localError = nil
        savingStep = true
        defer { savingStep = false }
        switch setup {
        case .consent:
            // Explicit consent timestamp through the real settings store.
            let stamp = ISO8601DateFormatter().string(from: Date())
            await store.recordMobileOnboarding(.consent, value: stamp)
            consentAt = stamp
        case .name:
            await store.recordMobileOnboarding(.name, value: mobileOnboardingName(name))
        case .language:
            await store.recordMobileOnboarding(.language, value: languageCode)
        case .source:
            guard let chosen = mobileChosenSource(
                selected: source, otherDetail: otherSource)
            else {
                localError = "Choose how you found Omi to continue."
                return
            }
            await store.recordMobileOnboarding(.source, value: chosen)
        case .permissions:
            // "I'll do these later" — nothing is asked until the user taps.
            break
        case .speech:
            await store.recordMobileOnboarding(.speech, value: "skipped")
            speechChoice = "skipped"
        case .knowledge:
            await store.recordMobileOnboarding(
                .knowledge, value: knowledgeOptIn ? "on" : "off")
        case .complete:
            await store.completeOnboarding()
            return
        }
        advance(from: setup)
    }

    @MainActor
    private func requestPermission(_ kind: PermissionKind) async {
        guard pendingPermission == nil else { return }
        pendingPermission = kind
        localError = nil
        defer { pendingPermission = nil }
        let state = await store.requestPermission(kind)
        permissionStates[kind] = state
    }
}
