import SwiftUI
import OmiTheme

/// Standalone multi-phase onboarding view for setting up the Playwright MCP browser extension.
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
    @State private var selectedTarget =
        BrowserAutomationTargetResolver.preferredTarget() ?? BrowserAutomationTargetResolver.knownTargets[0]
    @State private var browserInstalled = false
    @State private var extensionStepDone = false
    @State private var tokenStepDone = false
    @State private var browserCheckTimer: Timer? = nil
    @State private var extensionCheckTimer: Timer? = nil

    var body: some View {
        VStack(spacing: 0) {
            // Top bar: progress dots + dismiss button
            HStack {
                Spacer()

                // Progress dots
                HStack(spacing: OmiSpacing.sm) {
                    ForEach(Phase.allCases, id: \.rawValue) { p in
                        Circle()
                            .fill(p.rawValue <= phase.rawValue ? OmiColors.accent : OmiColors.textTertiary.opacity(0.3))
                            .frame(width: 8, height: 8)
                    }
                }

                Spacer()

                // Dismiss button (always visible)
                DismissButton(action: dismissSheet, showBackground: false)
            }
            .padding(.top, OmiSpacing.lg)
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.bottom, OmiSpacing.md)

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
            VStack(spacing: OmiSpacing.sm) {
                Button(action: handlePrimaryAction) {
                    Text(primaryButtonTitle)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, OmiSpacing.sm)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(isPrimaryDisabled)

                if let onSkip = onSkip, phase == .welcome {
                    Button(action: onSkip) {
                        Text("Skip for now")
                            .scaledFont(size: OmiType.body)
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, OmiSpacing.page)
            .padding(.bottom, OmiSpacing.xxl)
        }
        .frame(width: phase == .connect ? 880 : 480, height: phase == .connect ? 520 : 420)
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                .fill(OmiColors.backgroundSecondary)
                .overlay(
                    RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                        .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
                )
        )
        .omiAnimation(.easeInOut(duration: 0.3), value: phase)
    }

    // MARK: - Phase Views

    private var welcomePhase: some View {
        VStack(spacing: OmiSpacing.lg) {
            Image(systemName: "globe")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.accent)

            Text("Set up browser access")
                .scaledFont(size: OmiType.heading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("This lets the AI use your signed-in browser session — search the web, fill forms, and interact with sites on your behalf.")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, OmiSpacing.page)

            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
                featureRow(icon: "checkmark.shield", text: "Uses a Chromium browser extension for secure access")
                featureRow(icon: "key", text: "One-time auth token setup")
                featureRow(icon: "bolt", text: "No more Allow/Reject popups")
            }
            .padding(.horizontal, OmiSpacing.page)
            .padding(.top, OmiSpacing.sm)
        }
        .padding(.horizontal, OmiSpacing.xl)
    }

    /// Which GIF to show based on the current active step.
    private var activeGifName: String? {
        if !browserInstalled { return nil }
        if !extensionStepDone { return "installing_extension" }
        return "enabling_token"
    }

    private var connectPhase: some View {
        HStack(spacing: OmiSpacing.lg) {
            // Left side: steps
            VStack(spacing: OmiSpacing.lg) {
                Text("Connect the extension")
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                browserPicker

                // Step 1: Install the selected browser
                HStack(alignment: .top, spacing: OmiSpacing.md) {
                    stepBadge("1", done: browserInstalled)

                    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                        Text(browserInstalled ? "\(selectedTarget.name) is installed" : "Install \(selectedTarget.name)")
                            .scaledFont(size: OmiType.body, weight: .medium)
                            .foregroundColor(browserInstalled ? OmiColors.textTertiary : OmiColors.textPrimary)

                        if !browserInstalled {
                            Button(action: {
                                if let url = selectedTarget.installURL {
                                    NSWorkspace.shared.open(url)
                                }
                                startBrowserCheckTimer()
                            }) {
                                HStack(spacing: OmiSpacing.xxs) {
                                    Image(systemName: "arrow.down.circle")
                                        .scaledFont(size: OmiType.caption)
                                    Text("Download \(selectedTarget.name)")
                                        .scaledFont(size: OmiType.caption)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Step 2: Install extension from the browser's extension store
                HStack(alignment: .top, spacing: OmiSpacing.md) {
                    stepBadge("2", done: extensionStepDone)

                    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                        Text("Install the Playwright MCP Bridge extension")
                            .scaledFont(size: OmiType.body, weight: .medium)
                            .foregroundColor(extensionStepDone ? OmiColors.textTertiary : OmiColors.textPrimary)

                        Button(action: {
                            if let url = selectedTarget.extensionInstallURL() {
                                BrowserAutomationTargetResolver.open(url, in: selectedTarget)
                            }
                            startExtensionCheckTimer()
                        }) {
                            HStack(spacing: OmiSpacing.xxs) {
                                Image(systemName: extensionStepDone ? "checkmark" : "arrow.up.right.square")
                                    .scaledFont(size: OmiType.caption)
                                Text(extensionStepDone ? "Installed" : "Add Extension")
                                    .scaledFont(size: OmiType.caption)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(!browserInstalled || extensionStepDone)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Step 3: Open extension settings & copy token
                HStack(alignment: .top, spacing: OmiSpacing.md) {
                    stepBadge("3", done: tokenStepDone)

                    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                        Text("Open the extension and copy the auth token")
                            .scaledFont(size: OmiType.body, weight: .medium)
                            .foregroundColor(tokenStepDone ? OmiColors.textTertiary : OmiColors.textPrimary)

                        Button(action: {
                            if let url = selectedTarget.extensionStatusURL() {
                                BrowserAutomationTargetResolver.open(url, in: selectedTarget)
                            }
                            OmiMotion.withGated(.easeInOut(duration: 0.2)) {
                                tokenStepDone = true
                            }
                        }) {
                            HStack(spacing: OmiSpacing.xxs) {
                                Image(systemName: tokenStepDone ? "checkmark" : "key")
                                    .scaledFont(size: OmiType.caption)
                                Text(tokenStepDone ? "Opened" : "Open Extension Settings")
                                    .scaledFont(size: OmiType.caption)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(!browserInstalled)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Step 4: Paste token
                HStack(alignment: .top, spacing: OmiSpacing.md) {
                    stepBadge("4", done: isTokenValid)

                    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                        Text("Paste it here")
                            .scaledFont(size: OmiType.body, weight: .medium)
                            .foregroundColor(isTokenValid ? OmiColors.textTertiary : OmiColors.textPrimary)

                        TextField("Paste token here...", text: $tokenInput)
                            .textFieldStyle(.plain)
                            .scaledFont(size: OmiType.body)
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(OmiSpacing.sm)
                            .background(
                                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                                    .fill(OmiColors.backgroundPrimary.opacity(0.5))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                                            .stroke(
                                                tokenError != nil ? OmiColors.error.opacity(0.5) :
                                                isTokenValid ? Color.green.opacity(0.5) :
                                                OmiColors.textTertiary.opacity(0.3),
                                                lineWidth: 1
                                            )
                                    )
                            )
                            .disabled(!browserInstalled)
                            .onChange(of: tokenInput) { _, _ in
                                tokenError = nil
                            }

                        if let error = tokenError {
                            Text(error)
                                .scaledFont(size: OmiType.caption)
                                .foregroundColor(OmiColors.error)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.leading, OmiSpacing.page)
            .padding(.trailing, OmiSpacing.sm)
            .frame(maxWidth: .infinity)

            // Right side: GIF guide
            guidePanel
                .frame(maxWidth: .infinity)
                .padding(.trailing, OmiSpacing.xxl)
        }
        .onAppear {
            refreshBrowserState()
        }
        .onDisappear {
            browserCheckTimer?.invalidate()
            browserCheckTimer = nil
            extensionCheckTimer?.invalidate()
            extensionCheckTimer = nil
        }
    }

    private var browserPicker: some View {
        HStack(alignment: .center, spacing: OmiSpacing.sm) {
            Text("Browser")
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)

            Picker("", selection: $selectedTarget) {
                ForEach(BrowserAutomationTargetResolver.knownTargets) { target in
                    Text(target.name).tag(target)
                }
            }
            .labelsHidden()
            .controlSize(.small)
            .onChange(of: selectedTarget) { _, target in
                BrowserAutomationTargetStore.select(target)
                resetConnectionStateForSelectedBrowser()
                refreshBrowserState()
            }

            Spacer()

            if let defaultTarget = BrowserAutomationTargetResolver.defaultTarget(),
               defaultTarget.bundleIdentifier == selectedTarget.bundleIdentifier
            {
                Text("Default")
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundColor(OmiColors.success)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Right-side guide panel showing the appropriate GIF for the current step.
    private var guidePanel: some View {
        VStack(spacing: OmiSpacing.md) {
            if let gifName = activeGifName {
                AnimatedGIFView(gifName: gifName)
                    .id(gifName)
                    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))
                    .overlay(
                        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                            .stroke(OmiColors.textTertiary.opacity(0.2), lineWidth: 1)
                    )
            } else if !browserInstalled {
                VStack(spacing: OmiSpacing.md) {
                    Image(systemName: "desktopcomputer")
                        .scaledFont(size: OmiType.hero)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))
                    Text("Install \(selectedTarget.name) to get started")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, OmiSpacing.sm)
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(OmiColors.backgroundPrimary.opacity(0.5))
        )
    }

    private var verifyPhase: some View {
        VStack(spacing: OmiSpacing.lg) {
            if isVerifying {
                ProgressView()
                    .scaleEffect(1.5)
                    .frame(height: 48)

                Text("Testing connection...")
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("Sending a test request to verify the extension is working.")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, OmiSpacing.page)
            } else if verifySuccess {
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 48)
                    .foregroundColor(.green)

                Text("Connected")
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("The browser extension is working. The AI can now use \(selectedTarget.name).")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, OmiSpacing.page)
            } else if let error = verifyError {
                Image(systemName: "exclamationmark.triangle.fill")
                    .scaledFont(size: 48)
                    .foregroundColor(OmiColors.warning)

                Text("Connection failed")
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text(error)
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, OmiSpacing.page)

                Text("Make sure \(selectedTarget.name) is open and the extension page shows \"Connected\".")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textQuaternary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, OmiSpacing.page)
            }
        }
        .padding(.horizontal, OmiSpacing.xl)
    }

    private var donePhase: some View {
        VStack(spacing: OmiSpacing.lg) {
            Image(systemName: "checkmark.circle.fill")
                .scaledFont(size: 48)
                .foregroundColor(.green)

            Text("All set")
                .scaledFont(size: OmiType.heading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Browser access is configured. The AI can now browse the web, fill forms, and interact with sites using your \(selectedTarget.name) sessions.")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, OmiSpacing.page)
        }
        .padding(.horizontal, OmiSpacing.xl)
    }

    // MARK: - Helpers

    private func featureRow(icon: String, text: String) -> some View {
        HStack(spacing: OmiSpacing.sm) {
            Image(systemName: icon)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.accent)
                .frame(width: 20)
            Text(text)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)
        }
    }

    private func stepBadge(_ number: String, done: Bool = false) -> some View {
        Group {
            if done {
                Image(systemName: "checkmark")
                    .scaledFont(size: OmiType.caption, weight: .bold)
                    .foregroundColor(.white)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(Color.green))
            } else {
                Text(number)
                    .scaledFont(size: OmiType.caption, weight: .bold)
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

    private func resetConnectionStateForSelectedBrowser() {
        tokenInput = ""
        tokenError = nil
        tokenStepDone = false
        verifyError = nil
        verifySuccess = false
    }

    private func refreshBrowserState() {
        browserInstalled = BrowserAutomationTargetResolver.isInstalled(selectedTarget)
        extensionStepDone = BrowserAutomationTargetResolver.isExtensionInstalled(in: selectedTarget)
    }

    /// Poll every 2 seconds to detect selected browser installation.
    private func startBrowserCheckTimer() {
        guard browserCheckTimer == nil else { return }
        browserCheckTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            if BrowserAutomationTargetResolver.isInstalled(selectedTarget) {
                OmiMotion.withGated(.easeInOut(duration: 0.2)) {
                    browserInstalled = true
                }
                browserCheckTimer?.invalidate()
                browserCheckTimer = nil
            }
        }
    }

    /// Poll every 2 seconds to detect extension installation.
    private func startExtensionCheckTimer() {
        guard extensionCheckTimer == nil else { return }
        extensionCheckTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            if BrowserAutomationTargetResolver.isExtensionInstalled(in: selectedTarget) {
                OmiMotion.withGated(.easeInOut(duration: 0.2)) {
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
            OmiMotion.withGated(.easeInOut(duration: 0.2)) {
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
                OmiMotion.withGated(.easeInOut(duration: 0.2)) {
                    phase = .verify
                }
                runConnectionTest()
            } else {
                // No provider available — skip verification, go to done
                OmiMotion.withGated(.easeInOut(duration: 0.2)) {
                    phase = .done
                }
            }

        case .verify:
            if verifySuccess {
                OmiMotion.withGated(.easeInOut(duration: 0.2)) {
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
                        verifyError = "Could not connect to the extension. Make sure \(selectedTarget.name) is open and try again."
                        log("BrowserExtensionSetup: Connection test returned false")
                    }
                }
            } catch {
                await MainActor.run {
                    isVerifying = false
                    let msg = error.localizedDescription
                    if msg.contains("timeout") || msg.contains("Extension connection timeout") {
                        verifyError = "Connection timed out. Make sure \(selectedTarget.name) is running and the extension is installed, then try again."
                    } else {
                        verifyError = UserFacingErrorPresentation.message(for: error, while: .browserExtension)
                    }
                    log("BrowserExtensionSetup: Connection test error: \(error)")
                }
            }
        }
    }
}
