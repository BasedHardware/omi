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
    @State private var tokenError: String? = nil
    @State private var isVerifying = false
    @State private var verifyError: String? = nil
    @State private var verifySuccess = false
    @State private var chromeInstalled = false
    @State private var extensionStepDone = false
    @State private var tokenStepDone = false
    @State private var chromeCheckTimer: Timer? = nil
    @State private var extensionCheckTimer: Timer? = nil

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
        .frame(width: phase == .connect ? 880 : 480, height: phase == .connect ? 520 : 420)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundSecondary)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
                )
        )
        .animation(.easeInOut(duration: 0.3), value: phase)
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

    private static let chromeWebStoreURL = "https://chromewebstore.google.com/detail/playwright-mcp-bridge/mmlmfjhmonkocbjadbfplnigmagldckm"

    /// Which GIF to show based on the current active step.
    private var activeGifName: String? {
        if !chromeInstalled { return nil }
        if !extensionStepDone { return "installing_extension" }
        return "enabling_token"
    }

    private var connectPhase: some View {
        HStack(spacing: 16) {
            // Left side: steps
            VStack(spacing: 16) {
                Text("Connect the extension")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                // Step 1: Install Chrome
                HStack(alignment: .top, spacing: 12) {
                    stepBadge("1", done: chromeInstalled)

                    VStack(alignment: .leading, spacing: 6) {
                        Text(chromeInstalled ? "Google Chrome is installed" : "Install Google Chrome")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(chromeInstalled ? OmiColors.textTertiary : OmiColors.textPrimary)

                        if !chromeInstalled {
                            Button(action: {
                                if let url = URL(string: "https://www.google.com/chrome/") {
                                    NSWorkspace.shared.open(url)
                                }
                                startChromeCheckTimer()
                            }) {
                                HStack(spacing: 5) {
                                    Image(systemName: "arrow.down.circle")
                                        .scaledFont(size: 11)
                                    Text("Download Chrome")
                                        .scaledFont(size: 12)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Step 2: Install extension from Chrome Web Store
                HStack(alignment: .top, spacing: 12) {
                    stepBadge("2", done: extensionStepDone)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Install the extension from Chrome Web Store")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(extensionStepDone ? OmiColors.textTertiary : OmiColors.textPrimary)

                        Button(action: {
                            Self.openURLInChrome(Self.chromeWebStoreURL)
                            startExtensionCheckTimer()
                        }) {
                            HStack(spacing: 5) {
                                Image(systemName: extensionStepDone ? "checkmark" : "arrow.up.right.square")
                                    .scaledFont(size: 11)
                                Text(extensionStepDone ? "Installed" : "Add to Chrome")
                                    .scaledFont(size: 12)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(!chromeInstalled || extensionStepDone)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Step 3: Open extension settings & copy token
                HStack(alignment: .top, spacing: 12) {
                    stepBadge("3", done: tokenStepDone)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Open the extension and copy the auth token")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(tokenStepDone ? OmiColors.textTertiary : OmiColors.textPrimary)

                        Button(action: {
                            Self.openExtensionInChrome()
                            withAnimation(.easeInOut(duration: 0.2)) {
                                tokenStepDone = true
                            }
                        }) {
                            HStack(spacing: 5) {
                                Image(systemName: tokenStepDone ? "checkmark" : "key")
                                    .scaledFont(size: 11)
                                Text(tokenStepDone ? "Opened" : "Open Extension Settings")
                                    .scaledFont(size: 12)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(!chromeInstalled)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Step 4: Paste token
                HStack(alignment: .top, spacing: 12) {
                    stepBadge("4", done: isTokenValid)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Paste it here")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(isTokenValid ? OmiColors.textTertiary : OmiColors.textPrimary)

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
                                            .stroke(
                                                tokenError != nil ? OmiColors.error.opacity(0.5) :
                                                isTokenValid ? Color.green.opacity(0.5) :
                                                OmiColors.textTertiary.opacity(0.3),
                                                lineWidth: 1
                                            )
                                    )
                            )
                            .disabled(!chromeInstalled)
                            .onChange(of: tokenInput) { _, _ in
                                tokenError = nil
                            }

                        if let error = tokenError {
                            Text(error)
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.error)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.leading, 40)
            .padding(.trailing, 8)
            .frame(maxWidth: .infinity)

            // Right side: GIF guide
            guidePanel
                .frame(maxWidth: .infinity)
                .padding(.trailing, 24)
        }
        .onAppear {
            chromeInstalled = Self.isChromeInstalled
            extensionStepDone = Self.isExtensionInstalled
        }
        .onDisappear {
            chromeCheckTimer?.invalidate()
            chromeCheckTimer = nil
            extensionCheckTimer?.invalidate()
            extensionCheckTimer = nil
        }
    }

    /// Right-side guide panel showing the appropriate GIF for the current step.
    private var guidePanel: some View {
        VStack(spacing: 12) {
            if let gifName = activeGifName {
                AnimatedGIFView(gifName: gifName)
                    .id(gifName)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(OmiColors.textTertiary.opacity(0.2), lineWidth: 1)
                    )
            } else if !chromeInstalled {
                VStack(spacing: 12) {
                    Image(systemName: "desktopcomputer")
                        .scaledFont(size: 40)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))
                    Text("Install Chrome to get started")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundPrimary.opacity(0.5))
        )
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

    private func stepBadge(_ number: String, done: Bool = false) -> some View {
        Group {
            if done {
                Image(systemName: "checkmark")
                    .scaledFont(size: 11, weight: .bold)
                    .foregroundColor(.white)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(Color.green))
            } else {
                Text(number)
                    .scaledFont(size: 11, weight: .bold)
                    .foregroundColor(.white)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(OmiColors.textTertiary.opacity(0.5)))
            }
        }
    }

    /// Strip the "PLAYWRIGHT_MCP_EXTENSION_TOKEN=" prefix if the user copied the full env var line.
    static func parseToken(_ input: String) -> String {
        var token = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if let eqIndex = token.firstIndex(of: "="), token.hasPrefix("PLAYWRIGHT") {
            token = String(token[token.index(after: eqIndex)...])
        }
        return token
    }

    /// Validate that a parsed token looks like a real extension auth token.
    /// Returns an error message if invalid, nil if valid.
    static func validateToken(_ token: String) -> String? {
        if token.isEmpty {
            return "Please paste the token from the extension page."
        }
        if token.count < 20 {
            return "Token is too short. Copy the full token from the extension page."
        }
        // Extension tokens are base64url: alphanumeric + hyphen + underscore
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
        if token.unicodeScalars.contains(where: { !allowed.contains($0) }) {
            return "Token contains invalid characters. Copy the token value only, not the surrounding text."
        }
        return nil
    }

    /// Check if Google Chrome is installed.
    static var isChromeInstalled: Bool {
        FileManager.default.fileExists(atPath: "/Applications/Google Chrome.app")
    }

    /// Open a URL explicitly in Chrome (not the default browser).
    static func openURLInChrome(_ urlString: String) {
        guard let url = URL(string: urlString) else { return }
        let chromeURL = URL(fileURLWithPath: "/Applications/Google Chrome.app")

        if FileManager.default.fileExists(atPath: chromeURL.path) {
            NSWorkspace.shared.open(
                [url],
                withApplicationAt: chromeURL,
                configuration: NSWorkspace.OpenConfiguration()
            )
        } else {
            // Fallback: try default browser
            NSWorkspace.shared.open(url)
        }
    }

    /// Open the extension status page in Chrome.
    static func openExtensionInChrome() {
        openURLInChrome("chrome-extension://mmlmfjhmonkocbjadbfplnigmagldckm/status.html")
    }

    private static let extensionId = "mmlmfjhmonkocbjadbfplnigmagldckm"

    /// Check if the Playwright MCP Bridge extension is installed in any Chrome profile.
    static var isExtensionInstalled: Bool {
        let chromeSupport = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Google/Chrome")
        guard let profiles = try? FileManager.default.contentsOfDirectory(
            at: chromeSupport, includingPropertiesForKeys: nil
        ) else { return false }
        for profile in profiles {
            let extDir = profile.appendingPathComponent("Extensions/\(extensionId)")
            if FileManager.default.fileExists(atPath: extDir.path) {
                return true
            }
        }
        return false
    }

    /// Poll every 2 seconds to detect Chrome installation.
    private func startChromeCheckTimer() {
        guard chromeCheckTimer == nil else { return }
        chromeCheckTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            if Self.isChromeInstalled {
                withAnimation(.easeInOut(duration: 0.2)) {
                    chromeInstalled = true
                }
                chromeCheckTimer?.invalidate()
                chromeCheckTimer = nil
            }
        }
    }

    /// Poll every 2 seconds to detect extension installation.
    private func startExtensionCheckTimer() {
        guard extensionCheckTimer == nil else { return }
        extensionCheckTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            if Self.isExtensionInstalled {
                withAnimation(.easeInOut(duration: 0.2)) {
                    extensionStepDone = true
                }
                extensionCheckTimer?.invalidate()
                extensionCheckTimer = nil
            }
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

    /// Whether the current token input parses and validates successfully.
    private var isTokenValid: Bool {
        let token = Self.parseToken(tokenInput)
        return Self.validateToken(token) == nil
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
            withAnimation(.easeInOut(duration: 0.2)) {
                phase = .connect
            }

        case .connect:
            let token = Self.parseToken(tokenInput)
            if let error = Self.validateToken(token) {
                tokenError = error
                return
            }
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
