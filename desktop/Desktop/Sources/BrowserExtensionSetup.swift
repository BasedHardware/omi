import SwiftUI

/// Standalone multi-phase onboarding view for setting up the Playwright MCP Chrome extension.
/// Can be presented as a sheet, overlay, or full page from any context.
struct BrowserExtensionSetup: View {
    var onComplete: () -> Void
    var onSkip: (() -> Void)? = nil
    var onDismiss: (() -> Void)? = nil

    /// Optional ChatProvider for running the connection test.
    /// When nil, Phase 3 is skipped (token is saved and we go straight to Done).
    var chatProvider: ChatProvider? = nil

    enum Phase: Int, CaseIterable {
        case welcome = 0
        case connect = 1
        case verify = 2
        case done = 3
    }

    @State private var phase: Phase = .welcome
    @State private var tokenInput: String = ""
    @State private var isVerifying = false
    @State private var verifyError: String? = nil
    @State private var verifySuccess = false

    var body: some View {
        VStack(spacing: 0) {
            // Top bar: progress dots + dismiss button
            HStack {
                Spacer()

                // Progress dots
                HStack(spacing: 8) {
                    ForEach(Phase.allCases, id: \.rawValue) { p in
                        Circle()
                            .fill(p.rawValue <= phase.rawValue ? OmiColors.purplePrimary : OmiColors.textTertiary.opacity(0.3))
                            .frame(width: 8, height: 8)
                    }
                }

                Spacer()

                // Dismiss button (always visible)
                DismissButton(action: dismissSheet, showBackground: false)
            }
            .padding(.top, 16)
            .padding(.horizontal, 16)
            .padding(.bottom, 12)

            // Phase content
            Group {
                switch phase {
                case .welcome:
                    welcomePhase
                case .connect:
                    connectPhase
                case .verify:
                    verifyPhase
                case .done:
                    donePhase
                }
            }
            .frame(maxWidth: .infinity)

            Spacer()

            // Bottom buttons
            VStack(spacing: 8) {
                Button(action: handlePrimaryAction) {
                    Text(primaryButtonTitle)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(isPrimaryDisabled)

                if let onSkip = onSkip, phase == .welcome {
                    Button(action: onSkip) {
                        Text("Skip for now")
                            .scaledFont(size: 13)
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 24)
        }
        .frame(width: 480)
        .frame(minHeight: 400)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundSecondary)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
                )
        )
    }

    // MARK: - Phase Views

    private var welcomePhase: some View {
        VStack(spacing: 16) {
            Image(systemName: "globe")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.purplePrimary)

            Text("Set up browser access")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("This lets the AI use your Chrome browser with all your logged-in sessions — search the web, fill forms, and interact with sites on your behalf.")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            VStack(alignment: .leading, spacing: 8) {
                featureRow(icon: "checkmark.shield", text: "Uses a Chrome extension for secure access")
                featureRow(icon: "key", text: "One-time auth token setup")
                featureRow(icon: "bolt", text: "No more Allow/Reject popups")
            }
            .padding(.horizontal, 40)
            .padding(.top, 8)
        }
        .padding(.horizontal, 20)
    }

    private var connectPhase: some View {
        VStack(spacing: 16) {
            Image(systemName: "puzzlepiece.extension")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.purplePrimary)

            Text("Connect the extension")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            // Step 1: Open extension
            HStack(alignment: .top, spacing: 12) {
                stepBadge("1")

                VStack(alignment: .leading, spacing: 6) {
                    Text("Open the extension settings in Chrome")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)

                    Button(action: {
                        ClaudeAgentBridge.ensureChromeExtensionInstalled()
                        Self.openExtensionInChrome()
                    }) {
                        HStack(spacing: 5) {
                            Image(systemName: "arrow.up.right.square")
                                .scaledFont(size: 11)
                            Text("Open Extension Settings")
                                .scaledFont(size: 12)
                        }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 40)

            // Step 2: Copy token
            HStack(alignment: .top, spacing: 12) {
                stepBadge("2")

                Text("Copy the auth token shown on that page")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 40)

            // Step 3: Paste token
            HStack(alignment: .top, spacing: 12) {
                stepBadge("3")

                VStack(alignment: .leading, spacing: 6) {
                    Text("Paste it here")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)

                    TextField("Paste token here...", text: $tokenInput)
                        .textFieldStyle(.plain)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.backgroundPrimary.opacity(0.5))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(OmiColors.textTertiary.opacity(0.3), lineWidth: 1)
                                )
                        )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 40)
        }
        .padding(.horizontal, 20)
    }

    private var verifyPhase: some View {
        VStack(spacing: 16) {
            if isVerifying {
                ProgressView()
                    .scaleEffect(1.5)
                    .frame(height: 48)

                Text("Testing connection...")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("Sending a test request to verify the extension is working.")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            } else if verifySuccess {
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 48)
                    .foregroundColor(.green)

                Text("Connected!")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("The browser extension is working. The AI can now use your Chrome browser.")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            } else if let error = verifyError {
                Image(systemName: "exclamationmark.triangle.fill")
                    .scaledFont(size: 48)
                    .foregroundColor(OmiColors.warning)

                Text("Connection failed")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text(error)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)

                Text("Make sure Chrome is open and the extension page shows \"Connected\".")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textQuaternary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
        }
        .padding(.horizontal, 20)
    }

    private var donePhase: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .scaledFont(size: 48)
                .foregroundColor(.green)

            Text("All set!")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Browser access is configured. The AI can now browse the web, fill forms, and interact with sites using your Chrome sessions.")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .padding(.horizontal, 20)
    }

    // MARK: - Helpers

    private func featureRow(icon: String, text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.purplePrimary)
                .frame(width: 20)
            Text(text)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
        }
    }

    private func stepBadge(_ number: String) -> some View {
        Text(number)
            .scaledFont(size: 11, weight: .bold)
            .foregroundColor(.white)
            .frame(width: 22, height: 22)
            .background(Circle().fill(OmiColors.textTertiary.opacity(0.5)))
    }

    /// Open the extension status page explicitly in Chrome (macOS doesn't handle chrome-extension:// URLs natively)
    static func openExtensionInChrome() {
        let extensionURL = URL(string: "chrome-extension://mmlmfjhmonkocbjadbfplnigmagldckm/status.html")!
        let chromeURL = URL(fileURLWithPath: "/Applications/Google Chrome.app")

        if FileManager.default.fileExists(atPath: chromeURL.path) {
            NSWorkspace.shared.open(
                [extensionURL],
                withApplicationAt: chromeURL,
                configuration: NSWorkspace.OpenConfiguration()
            )
        } else {
            // Fallback: try default browser (unlikely to work for chrome-extension:// but better than nothing)
            NSWorkspace.shared.open(extensionURL)
        }
    }

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            onComplete()
        }
    }

    // MARK: - Button Logic

    private var primaryButtonTitle: String {
        switch phase {
        case .welcome:
            return "Set Up"
        case .connect:
            return "Continue"
        case .verify:
            if isVerifying { return "Testing..." }
            if verifySuccess { return "Continue" }
            return "Try Again"
        case .done:
            return "Done"
        }
    }

    private var isPrimaryDisabled: Bool {
        switch phase {
        case .connect:
            return tokenInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .verify:
            return isVerifying
        default:
            return false
        }
    }

    private func handlePrimaryAction() {
        switch phase {
        case .welcome:
            ClaudeAgentBridge.ensureChromeExtensionInstalled()
            withAnimation(.easeInOut(duration: 0.2)) {
                phase = .connect
            }

        case .connect:
            // Save token
            let token = tokenInput.trimmingCharacters(in: .whitespacesAndNewlines)
            UserDefaults.standard.set(token, forKey: "playwrightExtensionToken")
            log("BrowserExtensionSetup: Token saved (\(token.prefix(8))...)")

            if chatProvider != nil {
                withAnimation(.easeInOut(duration: 0.2)) {
                    phase = .verify
                }
                runConnectionTest()
            } else {
                // No provider available — skip verification, go to done
                withAnimation(.easeInOut(duration: 0.2)) {
                    phase = .done
                }
            }

        case .verify:
            if verifySuccess {
                withAnimation(.easeInOut(duration: 0.2)) {
                    phase = .done
                }
            } else {
                // Try again
                runConnectionTest()
            }

        case .done:
            onComplete()
        }
    }

    private func runConnectionTest() {
        guard let provider = chatProvider else { return }
        isVerifying = true
        verifyError = nil
        verifySuccess = false

        Task {
            do {
                let connected = try await provider.testPlaywrightConnection()
                await MainActor.run {
                    isVerifying = false
                    if connected {
                        verifySuccess = true
                        log("BrowserExtensionSetup: Connection test succeeded")
                    } else {
                        verifyError = "Could not connect to the Chrome extension. Make sure Chrome is open and try again."
                        log("BrowserExtensionSetup: Connection test returned false")
                    }
                }
            } catch {
                await MainActor.run {
                    isVerifying = false
                    let msg = error.localizedDescription
                    if msg.contains("timeout") || msg.contains("Extension connection timeout") {
                        verifyError = "Connection timed out. Make sure Chrome is running and the extension is installed, then try again."
                    } else {
                        verifyError = msg
                    }
                    log("BrowserExtensionSetup: Connection test error: \(error)")
                }
            }
        }
    }
}
