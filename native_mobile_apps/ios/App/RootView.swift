import AuthFeature
import OmiDesign
import OmiService
import OnboardingFeature
import SwiftUI

/// Switches between the app's top-level phases.
struct RootView: View {
    @Environment(SessionStore.self) private var session
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        ZStack {
            switch session.phase {
            case .launching:
                DS.Palette.background.ignoresSafeArea()
            case .signedOut:
                SignInScreen(googleSignIn: FirebaseAuthService.supportsGoogle ? { try await FirebaseAuthService.googleCredential() } : nil)
                    .transition(.opacity)
            case .consent:
                ConsentScreen().transition(.opacity)
            case .onboarding:
                OnboardingScreen(store: environment.makeOnboarding()).transition(.opacity)
            case .ready:
                MainTabView().transition(.opacity)
            }
        }
        .dsAnimation(DS.Motion.standard, value: session.phase)
        .onChange(of: session.phase, initial: true) { _, phase in DebugLaunchOptions.recordPhase(phase) }
        .task {
            if DebugLaunchOptions.current.resetsSession { session.signOut() }
            session.restore()
            // -omiGiveConsent YES also answers the consent screen of a restored session.
            if DebugLaunchOptions.current.givesConsent, case .consent = session.phase { session.giveConsent() }
            // -omiSkipOnboarding YES also ends an onboarding a previous launch replayed.
            if DebugLaunchOptions.current.skipsOnboarding, case .onboarding = session.phase { session.completeOnboarding() }
            // -omiOnboardingStep on a signed-in install replays onboarding from that step.
            if DebugLaunchOptions.current.onboardingStep != nil { session.replayOnboarding() }
            if session.phase == .signedOut, let uid = DebugLaunchOptions.current.autoSignInUserID {
                await session.signInLocalDev(uid: uid)
                if DebugLaunchOptions.current.givesConsent { session.giveConsent() }
                if DebugLaunchOptions.current.skipsOnboarding {
                    session.giveConsent()
                    session.completeOnboarding()
                }
            }
        }
    }
}
