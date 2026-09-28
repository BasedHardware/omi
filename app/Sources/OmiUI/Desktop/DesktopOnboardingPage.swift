import OmiKit
import SwiftUI

// Port of `DesktopOnboarding.tsx`: the signed-out window. Introduces data use
// before sign-in, offers optional permissions without starting capture, and
// requires explicit setup completion (docs/desktop-app.md). Window sizing is
// the host's job (onboarding ≥ 640×620); this surface draws the content.
// The step vocabulary and itinerary come from the shared `DesktopOnboardingStep`
// (`App/OnboardingFlow.swift`).

struct DesktopOnboardingPage: View {
    @EnvironmentObject var store: AppStore
    let returning: Bool

    @Environment(\.desktopTokens) private var tokens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var step: DesktopOnboardingStep

    init(returning: Bool) {
        self.returning = returning
        _step = State(initialValue: returning ? DesktopOnboardingStep.signIn : DesktopOnboardingStep.welcome)
    }

    var body: some View {
        VStack(spacing: 0) {
            progressHeader
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(title(for: step))
                        .font(.system(size: 28, weight: .medium))
                        .foregroundStyle(tokens.ink)
                    stepBody
                }
                .padding(28)
                .frame(maxWidth: 480, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            footer
        }
        .padding(.top, DesktopLayout.omnibarHeight)
        .accessibilityLabel("Omi onboarding")
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

    // MARK: Progress header (OnboardingProgress)

    private var progressHeader: some View {
        HStack(spacing: 8) {
            ForEach(
                desktopProgressSteps(signedIn: store.authState == AuthUiState.signedIn),
                id: \.self
            ) { candidate in
                let reached = candidate.rank <= step.rank
                Capsule()
                    .fill(reached ? tokens.ink : tokens.glassSelected)
                    .frame(width: reached ? 22 : 12, height: 5)
                    .animation(DesktopMotion.smoothOut(DesktopMotion.settleMs), value: step)
                    .accessibilityLabel(label(for: candidate))
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 28)
        .padding(.top, 18)
    }

    // MARK: Steps

    @ViewBuilder
    private var stepBody: some View {
        switch step {
        case DesktopOnboardingStep.welcome:
            VStack(alignment: .leading, spacing: 12) {
                OmiAvatarShape()
                    .frame(width: 64, height: 64)
                    .foregroundStyle(tokens.ink)
                Text(
                    "Omi listens to your day, remembers what matters, and answers when you ask — right on your Mac."
                )
                .font(.system(size: 14))
                .foregroundStyle(tokens.inkMuted)
            }
        case DesktopOnboardingStep.value:
            VStack(alignment: .leading, spacing: 12) {
                valueClaim(
                    icon: DesktopIcon.history,
                    title: "Recall anything you saw",
                    detail: "Omi keeps a private, local record of your screen so you can find anything again."
                )
                valueClaim(
                    icon: DesktopIcon.chatBubble,
                    title: "Ask about your day",
                    detail: "Conversations, meetings, and tasks become memories you can search and question."
                )
                valueClaim(
                    icon: DesktopIcon.checklist,
                    title: "Stay on top of tasks",
                    detail: "Commitments surface as tasks before they slip."
                )
            }
        case DesktopOnboardingStep.signIn:
            VStack(alignment: .leading, spacing: 12) {
                Text("Sign in to load your conversations, memories, and tasks.")
                    .font(.system(size: 14))
                    .foregroundStyle(tokens.inkMuted)
                if let error = store.signInErrorCopy {
                    Text(error)
                        .font(.system(size: 12))
                        .foregroundStyle(tokens.red)
                }
                Button {
                    Task { await store.startSignIn() }
                } label: {
                    HStack {
                        if store.authState == AuthUiState.signingIn {
                            OmiLoadingMark(size: 16, ink: tokens.surfaceInk)
                        } else {
                            Text(returning ? "Welcome back — sign in" : "Sign in")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(tokens.surfaceInk)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 40)
                    .background(RoundedRectangle(cornerRadius: 12).fill(tokens.ink))
                }
                .buttonStyle(GlassPressableStyle())
                .disabled(store.authState == AuthUiState.signingIn)
                .accessibilityLabel("Sign in")
            }
        case DesktopOnboardingStep.permissions:
            // Optional permissions without starting capture; a newly granted
            // permission requires relaunch before capture can run.
            VStack(alignment: .leading, spacing: 10) {
                Text("Optional. Omi asks macOS for each of these; nothing starts until you turn capture on yourself.")
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.inkMuted)
                permissionRow(PermissionKind.screen, "Screen", "Remember what you're working on.")
                permissionRow(PermissionKind.microphone, "Microphone", "Turn conversations into memories.")
                permissionRow(PermissionKind.notifications, "Notifications", "A nudge when something needs you.")
            }
        case DesktopOnboardingStep.harnesses:
            valueClaim(
                icon: DesktopIcon.chatBubble,
                title: "Your assistants stay in the loop",
                detail: "Connect the AI helpers you already use; Omi shares only what you allow."
            )
        case DesktopOnboardingStep.data:
            valueClaim(
                icon: DesktopIcon.timeline,
                title: "Your world, connected",
                detail: "Calendars, notes, and apps plug in under Apps — and stay under your control."
            )
        case DesktopOnboardingStep.tutorial:
            VStack(alignment: .leading, spacing: 12) {
                valueClaim(
                    icon: DesktopIcon.home,
                    title: "Home is your day",
                    detail: "One timeline of conversations, memories, tasks, and recall captures."
                )
                valueClaim(
                    icon: DesktopIcon.search,
                    title: "Search recalls anything",
                    detail: "The omnibar searches what you've seen and heard."
                )
            }
        case DesktopOnboardingStep.finish:
            VStack(alignment: .leading, spacing: 12) {
                Text("Everything has its place: Home for your day, Search to recall, and the omnibar to ask.")
                    .font(.system(size: 14))
                    .foregroundStyle(tokens.inkMuted)
                Button {
                    Task { await store.completeOnboarding() }
                } label: {
                    Text("Get started")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(tokens.surfaceInk)
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .background(RoundedRectangle(cornerRadius: 12).fill(tokens.ink))
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel("Complete setup")
            }
        }
    }

    private func valueClaim(icon: DesktopIcon, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            icon
                .frame(width: 18, height: 18)
                .foregroundStyle(tokens.ink)
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 12).fill(tokens.glassQuiet))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(tokens.ink)
                Text(detail)
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.inkMuted)
            }
        }
    }

    private func permissionRow(
        _ kind: PermissionKind, _ title: String, _ detail: String
    ) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(tokens.ink)
                Text(detail)
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
            }
            Spacer(minLength: 0)
            Button("Allow") {
                Task { await store.requestPermission(kind) }
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(tokens.blue)
            .accessibilityLabel("Allow \(title)")
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12).fill(tokens.glassQuiet))
    }

    // MARK: Footer nav

    private var footer: some View {
        HStack {
            if previousDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) != nil {
                Button("Back") {
                    previous()
                }
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(tokens.inkMuted)
                .accessibilityLabel("Back")
            }
            Spacer(minLength: 0)
            if nextDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) != nil {
                Button("Continue") {
                    advance()
                }
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(tokens.blue)
                .accessibilityLabel("Continue")
            }
        }
        .padding(.horizontal, 28)
        .padding(.vertical, 16)
    }

    private func advance() {
        guard let next = nextDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) else {
            return
        }
        withAnimation(DesktopMotion.stepAnimation(reduceMotion)) {
            step = next
        }
    }

    private func previous() {
        guard let back = previousDesktopStep(step, signedIn: store.authState == AuthUiState.signedIn) else {
            return
        }
        withAnimation(DesktopMotion.stepAnimation(reduceMotion)) {
            step = back
        }
    }
}
