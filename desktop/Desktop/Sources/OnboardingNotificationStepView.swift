import AppKit
import CoreGraphics
import SwiftUI
import UserNotifications

// MARK: - Onboarding Notification Step View (Step 2)

struct OnboardingNotificationStepView: View {
    let onContinue: () -> Void
    let onSkip: () -> Void

    @State private var tipHeadline: String = ""
    @State private var tipBody: String = ""
    @State private var isLoading = true
    @State private var showNotification = false
    @State private var showConfirmation = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 28) {
                // Title
                Text("Smart notifications")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(OmiColors.textPrimary)

                Text("omi watches your screen and sends helpful tips")
                    .font(.system(size: 15))
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)

                // Notification area with purple glow
                ZStack {
                    // Subtle purple radial glow
                    RadialGradient(
                        colors: [
                            OmiColors.purplePrimary.opacity(0.15),
                            Color.clear,
                        ],
                        center: .center,
                        startRadius: 20,
                        endRadius: 200
                    )
                    .frame(width: 400, height: 200)

                    if isLoading {
                        NotificationShimmer()
                            .transition(.opacity)
                    }

                    if showNotification {
                        MacOSNotificationBanner(
                            headline: tipHeadline,
                            message: tipBody
                        )
                        .transition(.move(edge: .top).combined(with: .opacity))
                    }
                }
                .frame(height: 120)
                .animation(.spring(response: 0.5, dampingFraction: 0.8), value: showNotification)
                .animation(.easeInOut(duration: 0.3), value: isLoading)

                // Confirmation text
                if showConfirmation {
                    HStack(spacing: 6) {
                        Image(systemName: "bell.badge.fill")
                            .foregroundColor(OmiColors.purplePrimary)
                            .font(.system(size: 13))
                        Text("Notification sent to your Mac")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(OmiColors.textSecondary)
                    }
                    .transition(.opacity)
                }
            }

            Spacer()

            // Bottom buttons
            VStack(spacing: 12) {
                Button(action: onContinue) {
                    Text("Continue")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(maxWidth: 220)
                        .padding(.vertical, 12)
                        .background(OmiColors.purplePrimary)
                        .cornerRadius(12)
                }
                .buttonStyle(.plain)

                Button(action: onSkip) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.bottom, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            await generateTip()
        }
    }

    // MARK: - Screen Capture & Tip Generation

    private func generateTip() async {
        // Capture the screen behind the omi window
        let imageData = captureScreenBehindOmiWindow()

        if let imageData = imageData {
            // Try Gemini for a contextual tip
            do {
                let tip = try await requestGeminiTip(imageData: imageData)
                await MainActor.run {
                    tipHeadline = tip.headline
                    tipBody = tip.body
                    revealNotification()
                }
                return
            } catch {
                log("OnboardingNotification: Gemini tip failed: \(error.localizedDescription)")
            }
        }

        // Fallback: generic but useful tip
        await MainActor.run {
            tipHeadline = "Tip"
            tipBody = "omi will send tips like this based on what's on your screen"
            revealNotification()
        }
    }

    private func revealNotification() {
        withAnimation {
            isLoading = false
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            withAnimation {
                showNotification = true
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            withAnimation(.easeIn(duration: 0.4)) {
                showConfirmation = true
            }
            sendRealNotification()
        }
    }

    private func sendRealNotification() {
        let content = UNMutableNotificationContent()
        content.title = "omi"
        content.subtitle = tipHeadline
        content.body = tipBody
        let request = UNNotificationRequest(identifier: "onboarding-tip", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    // MARK: - Capture Behind Window

    private func captureScreenBehindOmiWindow() -> Data? {
        // Find the omi onboarding window
        guard let omiWindow = NSApp.windows.first(where: { window in
            window.isVisible && (window.title.contains("Omi") || window.title.contains("omi"))
        }) else {
            // Fallback: capture main display
            return captureFullScreen()
        }

        let windowNumber = CGWindowID(omiWindow.windowNumber)

        // Capture everything on screen BELOW the omi window (excludes the omi window itself)
        guard
            let cgImage = CGWindowListCreateImage(
                CGRect.null,
                .optionOnScreenBelowWindow,
                windowNumber,
                [.bestResolution, .nominalResolution]
            )
        else {
            return captureFullScreen()
        }

        return jpegData(from: cgImage, quality: 0.5)
    }

    private func captureFullScreen() -> Data? {
        guard
            let cgImage = CGWindowListCreateImage(
                CGRect.null,
                .optionOnScreenOnly,
                kCGNullWindowID,
                [.bestResolution]
            )
        else {
            return nil
        }
        return jpegData(from: cgImage, quality: 0.5)
    }

    private func jpegData(from cgImage: CGImage, quality: CGFloat) -> Data? {
        let bitmapRep = NSBitmapImageRep(cgImage: cgImage)
        return bitmapRep.representation(using: .jpeg, properties: [.compressionFactor: quality])
    }

    // MARK: - Gemini API

    private struct TipResult {
        let headline: String
        let body: String
    }

    private func requestGeminiTip(imageData: Data) async throws -> TipResult {
        let systemPrompt = """
            You are omi, an always-on AI assistant that watches the user's screen. \
            The user just installed omi and you're showing them what smart notifications look like. \
            Look at the screenshot of their desktop and generate ONE useful, specific, non-obvious tip \
            about what they're working on right now.

            Rules:
            - Reference specific things visible on screen (filenames, tab titles, app names, content)
            - Be observational and casual: "hey, heads up..." tone, not commands
            - Non-obvious — something they wouldn't figure out themselves easily
            - Under 100 characters for the body text
            - Do NOT comment on omi, the onboarding, or the setup process itself
            - Do NOT say generic things like "I see you're setting up notifications"
            - If you see code, reference the specific file/function/pattern
            - If you see a browser, reference the specific page/content
            - If you see nothing useful, give a genuinely helpful macOS productivity tip

            Respond with ONLY a JSON object: {"headline": "short label", "body": "the tip text"}
            headline should be 1-3 words like "Tip", "Heads up", "Quick note", etc.
            """

        let prompt = "Analyze this screenshot and generate a contextual notification tip."

        let base64 = imageData.base64EncodedString()

        let request = GeminiRequest(
            contents: [
                GeminiRequest.Content(parts: [
                    GeminiRequest.Part(text: prompt),
                    GeminiRequest.Part(mimeType: "image/jpeg", data: base64),
                ])
            ],
            systemInstruction: GeminiRequest.SystemInstruction(
                parts: [GeminiRequest.SystemInstruction.TextPart(text: systemPrompt)]
            ),
            generationConfig: GeminiRequest.GenerationConfig(
                responseMimeType: "application/json",
                responseSchema: GeminiRequest.GenerationConfig.ResponseSchema(
                    type: "object",
                    properties: [
                        "headline": GeminiRequest.GenerationConfig.ResponseSchema.Property(
                            type: "string", description: "Short 1-3 word label"),
                        "body": GeminiRequest.GenerationConfig.ResponseSchema.Property(
                            type: "string", description: "The tip text, under 100 chars"),
                    ],
                    required: ["headline", "body"]
                )
            )
        )

        let requestBody = try JSONEncoder().encode(request)

        guard let apiKey = getenv("GEMINI_API_KEY").flatMap({ String(validatingUTF8: $0) }) else {
            throw NSError(domain: "OnboardingTip", code: 1, userInfo: [NSLocalizedDescriptionKey: "No API key"])
        }

        let url = URL(
            string:
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=\(apiKey)"
        )!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 15
        urlRequest.httpBody = requestBody

        let (data, _) = try await URLSession.shared.data(for: urlRequest)

        let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

        guard let text = response.candidates?.first?.content?.parts?.first?.text else {
            throw NSError(
                domain: "OnboardingTip", code: 2, userInfo: [NSLocalizedDescriptionKey: "No response text"])
        }

        // Parse JSON response
        guard let jsonData = text.data(using: .utf8) else {
            throw NSError(
                domain: "OnboardingTip", code: 3, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
        }

        struct TipJSON: Decodable {
            let headline: String
            let body: String
        }

        let tipJSON = try JSONDecoder().decode(TipJSON.self, from: jsonData)
        return TipResult(headline: tipJSON.headline, body: tipJSON.body)
    }
}

// MARK: - macOS Notification Banner Component

struct MacOSNotificationBanner: View {
    let headline: String
    let message: String

    var body: some View {
        HStack(spacing: 12) {
            // App icon
            Image(nsImage: NSApp.applicationIconImage)
                .resizable()
                .frame(width: 32, height: 32)
                .clipShape(RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("omi")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.primary)
                    Text(headline)
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                    Spacer()
                    Text("now")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }

                Text(message)
                    .font(.system(size: 12))
                    .foregroundColor(.primary.opacity(0.85))
                    .lineLimit(2)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(width: 360)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.25), radius: 20, x: 0, y: 8)
        .shadow(color: .black.opacity(0.1), radius: 4, x: 0, y: 2)
    }
}

// MARK: - Shimmer Skeleton

struct NotificationShimmer: View {
    @State private var shimmerOffset: CGFloat = -1

    var body: some View {
        HStack(spacing: 12) {
            // Icon placeholder
            RoundedRectangle(cornerRadius: 7)
                .fill(Color.white.opacity(0.06))
                .frame(width: 32, height: 32)

            VStack(alignment: .leading, spacing: 6) {
                // Title line
                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.white.opacity(0.06))
                    .frame(width: 80, height: 10)

                // Body line 1
                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.white.opacity(0.06))
                    .frame(width: 260, height: 10)

                // Body line 2
                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.white.opacity(0.06))
                    .frame(width: 180, height: 10)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(width: 360)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.white.opacity(0.04))
        )
        .overlay(
            shimmerGradient
                .mask(
                    RoundedRectangle(cornerRadius: 16)
                )
        )
        .onAppear {
            withAnimation(
                .linear(duration: 1.5)
                    .repeatForever(autoreverses: false)
            ) {
                shimmerOffset = 2
            }
        }
    }

    private var shimmerGradient: some View {
        GeometryReader { geo in
            LinearGradient(
                colors: [
                    Color.clear,
                    Color.white.opacity(0.05),
                    Color.clear,
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(width: geo.size.width * 0.6)
            .offset(x: geo.size.width * shimmerOffset)
        }
    }
}
