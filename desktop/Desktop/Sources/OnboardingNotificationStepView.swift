import SwiftUI

/// Onboarding step that demonstrates the value of proactive notifications.
/// Captures a screenshot, analyzes it with Gemini, fires a real notification,
/// and shows a macOS notification-style preview so the user sees real value.
struct OnboardingNotificationStepView: View {
    @ObservedObject var appState: AppState
    var onContinue: () -> Void
    var onSkip: () -> Void

    @State private var analysisState: AnalysisState = .idle
    @State private var tipText: String = ""
    @State private var tipHeadline: String = ""
    @State private var showNotification = false
    @State private var notificationSent = false
    @State private var pulseAnimation = false

    private enum AnalysisState {
        case idle
        case capturing
        case analyzing
        case done
        case error(String)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Notifications")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onSkip) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            Spacer()

            // Content
            VStack(spacing: 32) {
                // Icon with glow
                ZStack {
                    // Glow
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.15))
                        .frame(width: 100, height: 100)
                        .blur(radius: 20)
                        .scaleEffect(pulseAnimation ? 1.2 : 1.0)
                        .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

                    Image(systemName: "bell.badge.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [OmiColors.purplePrimary, OmiColors.purpleSecondary],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                }
                .onAppear { pulseAnimation = true }

                VStack(spacing: 10) {
                    Text("Proactive Intelligence")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("omi watches your screen and catches things you'd miss —\nwrong recipients, stale data, hidden shortcuts.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }

                // Analysis status / notification preview
                switch analysisState {
                case .idle:
                    EmptyView()

                case .capturing:
                    HStack(spacing: 10) {
                        ProgressView()
                            .scaleEffect(0.7)
                            .tint(OmiColors.purplePrimary)
                        Text("Capturing your screen...")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                    }

                case .analyzing:
                    HStack(spacing: 10) {
                        ProgressView()
                            .scaleEffect(0.7)
                            .tint(OmiColors.purplePrimary)
                        Text("Analyzing what you're working on...")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                    }

                case .done:
                    if showNotification {
                        notificationPreview
                            .transition(.asymmetric(
                                insertion: .move(edge: .top).combined(with: .opacity).combined(with: .scale(scale: 0.95)),
                                removal: .opacity
                            ))
                    }

                case .error(let message):
                    VStack(spacing: 12) {
                        Text(message)
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                            .multilineTextAlignment(.center)

                        Button("Try again") {
                            startAnalysis()
                        }
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(OmiColors.purplePrimary)
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            // Bottom button
            if notificationSent {
                VStack(spacing: 12) {
                    Text("Check the top-right of your screen for the real notification")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textTertiary)

                    Button(action: onContinue) {
                        Text("Continue")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(maxWidth: 280)
                            .padding(.vertical, 12)
                            .background(OmiColors.purplePrimary)
                            .cornerRadius(12)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.bottom, 32)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            // Auto-start analysis after a short delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                if case .idle = analysisState {
                    startAnalysis()
                }
            }
        }
    }

    // MARK: - macOS Notification Preview

    private var notificationPreview: some View {
        HStack(spacing: 12) {
            // App icon
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(
                        LinearGradient(
                            colors: [OmiColors.purplePrimary, OmiColors.purpleAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 36, height: 36)

                Text("omi")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text("omi")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.black)

                    Spacer()

                    Text("now")
                        .font(.system(size: 11))
                        .foregroundColor(.gray)
                }

                Text(tipHeadline.isEmpty ? "Tip from omi" : tipHeadline)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.black.opacity(0.85))
                    .lineLimit(1)

                Text(tipText)
                    .font(.system(size: 12))
                    .foregroundColor(.black.opacity(0.7))
                    .lineLimit(2)
                    .lineSpacing(1)
            }
        }
        .padding(12)
        .frame(maxWidth: 380, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(.white)
                .shadow(color: .black.opacity(0.15), radius: 12, x: 0, y: 4)
                .shadow(color: .black.opacity(0.05), radius: 1, x: 0, y: 1)
        )
    }

    // MARK: - Analysis

    private func startAnalysis() {
        analysisState = .capturing

        Task {
            // Step 1: Capture screenshot
            let screenCapture = ScreenCaptureService()
            let screenshotData = await screenCapture.captureActiveWindowAsync()
            guard let jpegData = screenshotData else {
                await MainActor.run {
                    analysisState = .error("Could not capture screen. Make sure Screen Recording permission is granted.")
                }
                return
            }

            await MainActor.run {
                analysisState = .analyzing
            }

            // Step 2: Analyze with Gemini using production-quality prompt
            do {
                let gemini = try GeminiClient(model: "gemini-2.0-flash")

                let prompt = """
                Look at this screenshot and find ONE specific, high-value insight the user would NOT figure out on their own. \
                The goal is to IMPRESS them — make them think "wow, I'm glad I have this."

                CORE QUESTION: Is the user about to make a mistake, missing something non-obvious, or unaware of a \
                shortcut that would significantly help with what they're doing right now?

                WHAT QUALIFIES:
                - User is about to make a visible mistake (wrong recipient, wrong date, sensitive info exposed)
                - A specific, lesser-known tool/feature that solves what they're doing
                - A concrete error, misconfiguration, or stale state they may not have noticed
                - Something non-obvious about what's on screen that saves them time or prevents an issue

                WHAT DOES NOT QUALIFY:
                - Anything obvious the user can see themselves
                - Generic advice ("take a break", "consider adding tests", "remember to commit")
                - Basic shortcuts everyone knows
                - Pointing at UI elements already visible
                - If you see the omi app onboarding, look at the OTHER windows behind it instead

                TONE: Write like a knowledgeable friend glancing at your screen — an observation, not a command. \
                Say what you noticed and why it matters.

                GOOD EXAMPLES of the quality bar:
                - "That draft is saved in /tmp — gets wiped on reboot"
                - "Replying to the group thread, not the DM — double-check the recipient"
                - "This regex misses Unicode — \\p{L} catches accented characters that [a-zA-Z] drops"
                - "Your branch is 12 commits behind main — rebase before the PR or you'll get conflicts"
                """

                let systemPrompt = """
                You are omi, an AI that runs in the background on the user's Mac analyzing their screen to catch things they'd miss. \
                This is during onboarding — the user is seeing their first notification. Make it count. \
                Give a genuinely impressive, specific observation about what you see. \
                If the only visible content is the omi onboarding window, look for any other visible windows, menu bar items, \
                or desktop state. If there's truly nothing else, give a specific observation about their system setup \
                (number of displays, apps in dock, etc.) — but never generic advice.
                """

                let schema = GeminiRequest.GenerationConfig.ResponseSchema(
                    type: "object",
                    properties: [
                        "headline": .init(type: "string", description: "Short 3-6 word headline — an observation, not an instruction. Example: 'Draft saved in /tmp' not 'Move file from /tmp'"),
                        "tip": .init(type: "string", description: "The insight in 1-2 sentences. Specific to what's on screen. Under 100 characters if possible."),
                    ],
                    required: ["headline", "tip"]
                )

                let responseText = try await gemini.sendRequest(
                    prompt: prompt,
                    imageData: jpegData,
                    systemPrompt: systemPrompt,
                    responseSchema: schema
                )

                // Parse JSON response
                if let data = responseText.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let tip = json["tip"] as? String {
                    let headline = json["headline"] as? String ?? "Tip from omi"

                    await MainActor.run {
                        tipText = tip
                        tipHeadline = headline
                        analysisState = .done

                        // Animate the notification preview in
                        withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) {
                            showNotification = true
                        }

                        // Send real notification
                        NotificationService.shared.sendNotification(
                            title: headline,
                            message: tip,
                            assistantId: "onboarding"
                        )

                        withAnimation(.easeInOut(duration: 0.3)) {
                            notificationSent = true
                        }
                    }
                } else {
                    await MainActor.run {
                        analysisState = .error("Couldn't parse the AI response. Try again.")
                    }
                }
            } catch {
                await MainActor.run {
                    analysisState = .error("AI analysis failed: \(error.localizedDescription)")
                }
            }
        }
    }
}
