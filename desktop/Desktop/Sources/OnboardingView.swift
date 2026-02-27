import SwiftUI
import AppKit
import AVKit

struct OnboardingView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: (() -> Void)? = nil
    @AppStorage("onboardingStep") private var currentStep = 0

    let steps = ["Video", "Chat"]

    var body: some View {
        ZStack {
            // Full dark background
            OmiColors.backgroundPrimary
                .ignoresSafeArea()

            Group {
                if appState.hasCompletedOnboarding {
                    Color.clear
                        .onAppear {
                            log("OnboardingView: hasCompletedOnboarding=true, starting monitoring")
                            if !ProactiveAssistantsPlugin.shared.isMonitoring {
                                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
                            }
                            if let onComplete = onComplete {
                                log("OnboardingView: Calling onComplete handler")
                                onComplete()
                            } else {
                                log("OnboardingView: No onComplete handler, view will transition via DesktopHomeView")
                            }
                        }
                } else {
                    onboardingContent
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            // If currentStep is beyond the new 2-step flow (e.g. user was on old step 3+),
            // clamp to step 1 (chat) so they don't get stuck
            if currentStep > 1 {
                currentStep = 1
            }
        }
    }

    private var onboardingContent: some View {
        Group {
            if currentStep == 0 {
                // Step 0: Full-window video
                ZStack {
                    OnboardingVideoView()
                        .aspectRatio(16.0 / 9.0, contentMode: .fit)
                        .frame(maxWidth: 960)
                        .clipShape(RoundedRectangle(cornerRadius: 16))

                    VStack {
                        Spacer()
                        Button(action: {
                            AnalyticsManager.shared.onboardingStepCompleted(step: 0, stepName: "Video")
                            currentStep = 1
                        }) {
                            Text("Continue")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundColor(.white)
                                .frame(maxWidth: 220)
                                .padding(.vertical, 12)
                                .background(OmiColors.purplePrimary)
                                .cornerRadius(12)
                        }
                        .buttonStyle(.plain)
                        .padding(.bottom, 32)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Step 1: Interactive AI Chat
                OnboardingChatView(
                    appState: appState,
                    chatProvider: chatProvider,
                    onComplete: {
                        AnalyticsManager.shared.onboardingStepCompleted(step: 1, stepName: "Chat")
                        if let onComplete = onComplete {
                            onComplete()
                        }
                    },
                    onSkip: {
                        handleSkip()
                    }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    /// Skip onboarding — complete with minimal setup
    private func handleSkip() {
        log("OnboardingView: User skipped onboarding chat")
        AnalyticsManager.shared.onboardingStepCompleted(step: 1, stepName: "Chat_Skipped")
        AnalyticsManager.shared.onboardingCompleted()

        // Stop the AI if it's still running
        chatProvider.stopAgent()

        appState.hasCompletedOnboarding = true
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")

        // Start essential services
        Task {
            await AgentVMService.shared.startPipeline()
        }
        if LaunchAtLoginManager.shared.setEnabled(true) {
            AnalyticsManager.shared.launchAtLoginChanged(enabled: true, source: "onboarding_skip")
        }
        ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
        appState.startTranscription()

        // Clean up onboarding session key
        chatProvider.onboardingSessionKey = nil

        if let onComplete = onComplete {
            onComplete()
        }
    }
}

// MARK: - Onboarding Video View

struct OnboardingVideoView: NSViewRepresentable {
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> AVPlayerView {
        let playerView = AVPlayerView()
        if let url = Bundle.resourceBundle.url(forResource: "omi-demo", withExtension: "mp4") {
            let player = AVPlayer(url: url)
            playerView.player = player
            playerView.controlsStyle = .none
            playerView.showsFullScreenToggleButton = false
            playerView.showsSharingServiceButton = false
            player.play()

            NotificationCenter.default.addObserver(
                context.coordinator,
                selector: #selector(Coordinator.playerDidFinishPlaying(_:)),
                name: .AVPlayerItemDidPlayToEndTime,
                object: player.currentItem
            )
            context.coordinator.player = player
        }
        return playerView
    }

    func updateNSView(_ nsView: AVPlayerView, context: Context) {}

    class Coordinator: NSObject {
        var player: AVPlayer?

        @objc func playerDidFinishPlaying(_ notification: Notification) {
            player?.seek(to: .zero)
            player?.play()
        }
    }
}

// MARK: - Animated GIF View

struct AnimatedGIFView: NSViewRepresentable {
    let gifName: String

    func makeNSView(context: Context) -> NSImageView {
        let imageView = NSImageView()
        imageView.imageScaling = .scaleProportionallyDown
        imageView.animates = true
        imageView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        imageView.setContentCompressionResistancePriority(.defaultLow, for: .vertical)

        if let url = Bundle.resourceBundle.url(forResource: gifName, withExtension: "gif"),
           let image = NSImage(contentsOf: url) {
            imageView.image = image
        }

        return imageView
    }

    func updateNSView(_ nsView: NSImageView, context: Context) {
        nsView.animates = true
    }
}

// MARK: - Onboarding Privacy Sheet

struct OnboardingPrivacySheet: View {
    @Binding var isPresented: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Image(systemName: "shield.lefthalf.filled")
                    .scaledFont(size: 16)
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Data & Privacy")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: { isPresented = false }) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 18)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(20)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Encryption
                    privacyCard {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Encryption", systemImage: "lock.shield")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.circle.fill")
                                    .scaledFont(size: 11)
                                    .foregroundColor(.green)
                                Text("Server-side encryption")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("Active")
                                    .scaledFont(size: 10, weight: .semibold)
                                    .foregroundColor(.green)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.green.opacity(0.15))
                                    .cornerRadius(3)
                            }

                            Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.top, 2)
                        }
                    }

                    // What We Track
                    privacyCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("What We Track", systemImage: "list.bullet")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            VStack(alignment: .leading, spacing: 4) {
                                sheetTrackingItem("Onboarding steps completed")
                                sheetTrackingItem("Settings changes")
                                sheetTrackingItem("App installations and usage")
                                sheetTrackingItem("Device connection status")
                                sheetTrackingItem("Transcript processing events")
                                sheetTrackingItem("Conversation creation and updates")
                                sheetTrackingItem("Memory extraction events")
                                sheetTrackingItem("Chat interactions")
                                sheetTrackingItem("Speech profile creation")
                                sheetTrackingItem("Focus session events")
                                sheetTrackingItem("App open/close events")
                            }
                        }
                    }

                    // Privacy Guarantees
                    privacyCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Privacy Guarantees", systemImage: "hand.raised.fill")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            VStack(alignment: .leading, spacing: 5) {
                                sheetBullet("Anonymous tracking with randomly generated IDs")
                                sheetBullet("No personal info stored in analytics")
                                sheetBullet("Data is never sold or shared with third parties")
                                sheetBullet("Opt out of tracking at any time")
                            }
                        }
                    }
                }
                .padding(20)
            }
        }
        .frame(width: 400, height: 480)
        .background(OmiColors.backgroundSecondary)
    }

    private func privacyCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
                    )
            )
    }

    private func sheetTrackingItem(_ text: String) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(OmiColors.textTertiary.opacity(0.5))
                .frame(width: 3, height: 3)
            Text(text)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func sheetBullet(_ text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark")
                .scaledFont(size: 8, weight: .bold)
                .foregroundColor(.green)
            Text(text)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textSecondary)
        }
    }
}
