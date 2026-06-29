import SwiftUI
import os.log

// Allowlist of URL schemes the plugin's deep link is permitted to use.
// A plugin service returning any other scheme is treated as a compromise
// signal — `NSWorkspace.shared.open` would happily launch `file://`,
// `ssh://`, or any custom scheme, so we must gate this client-side.
private enum DeepLinkSafeScheme: String { case https, http }

// Allowlist of expected deep-link hostnames per plugin. The plugin deep
// links are `https://t.me/<bot>?start=<token>` (Telegram) or
// `https://wa.me/<phone>?text=…` (WhatsApp). Anything else is rejected.
//
// (P1 fix from code review: `URL(string: "https://t.me/…")?.host` returns the
// literal substring `t.me` — not the registrable suffix `me` — so a naive
// `RawRepresentable.init(rawValue: host)` match rejects every legitimate
// link. We use a per-plugin lookup instead, and the host check is bound
// to the active plugin: a `t.me` URL in a WhatsApp connect sheet is
// rejected, and vice versa, so a compromised plugin service can't
// phish by returning the other platform's host.)
private enum DeepLinkSafeHost {
    static let telegram = "t.me"
    static let whatsapp = "wa.me"

    /// Hostname expected for the given plugin's deep links. Returning
    /// `nil` for any other plugin would be a programming error — we
    /// only ever call this with the two plugins above, but the function
    /// is total so the compiler is happy.
    static func expected(for plugin: AIPlugin) -> String? {
        switch plugin {
        case .telegram: return telegram
        case .whatsapp: return whatsapp
        }
    }
}

private let logger = Logger(subsystem: "omi.desktop", category: "ai-clone")

/// Shared "connect this plugin" sheet — handles credential entry, POST /setup,
/// deep-link display, and handshake polling.
///
/// Tier 1 UX improvements (see Telegram onboarding plan):
/// - Clipboard auto-detect (ClipboardWatcher)
/// - Real-time token validation (TelegramTokenValidator)
/// - QR code alongside the deep link (QRCodeGenerator)
/// - Two-step progress indicator with countdown
/// - "Open @BotFather" deep link (Telegram only)
///
/// Works for any AIPlugin; the form fields are driven by the plugin's
/// `credentialFields` array, so adding a new plugin doesn't require new UI.
struct ConnectSheet: View {
    let plugin: AIPlugin
    @ObservedObject var config: AICloneConfig
    @Binding var isPresented: Bool

    @State private var credentialValues: [String: String] = [:]
    @State private var submitting = false
    @State private var error: String?
    @State private var setupResult: SetupResponse?
    @State private var pollingForHandshake = false
    @State private var pollCount = 0
    @State private var devApiKeyOverride: String = ""
    @State private var handshakeSecondsRemaining: Int = 0
    // P1 (cubic): handshake success vs. timeout. Polling /health is NOT
    // a confirmation that the user completed the handshake — /health
    // returns 200 as long as the plugin process is up, regardless of
    // whether anyone sent /start. Use a separate boolean that's set
    // true ONLY when the polling loop saw a reachable /health WITHIN
    // the handshake window. The loop's "set false on exit" logic was
    // ambiguous about success vs timeout and falsely reported
    // "Connected" on both.
    @State private var handshakeCompleted: Bool = false
    @State private var handshakeTimedOut: Bool = false

    /// Bumped when the user types in a credential field. While set,
    /// the clipboard watcher won't auto-fill that field — protects
    /// against the watcher overwriting the user's manual edits.
    @State private var userEditedFields: Set<String> = []

    /// Set briefly after the clipboard watcher auto-fills a field, so
    /// we can show a "✓ Telegram bot token detected from clipboard"
    /// confirmation to the user. Cleared after a few seconds.
    @State private var lastClipboardAutofillKey: String?
    @State private var clipboardAutofillBannerClearTask: Task<Void, Never>?

    /// Clipboard watcher (only set while sheet is visible).
    /// Strongly held — the sheet is the lifecycle owner.
    @State private var clipboardWatcher: ClipboardWatcher?

    private static let maxPollIterations = 15  // 15 × 3s = 45s (was 60s)
    private static let botFatherURL = URL(string: "https://t.me/BotFather")!

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: plugin.systemImage)
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.purplePrimary)
                Text("Connect \(plugin.displayName)")
                    .scaledFont(size: 18, weight: .semibold)
                Spacer()
                Button(action: { isPresented = false }) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 14, weight: .medium)
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.borderless)
            }
            .padding(.horizontal, 20)
            .padding(.top, 16)

            Divider().padding(.top, 12)

            ScrollView {
                if let result = setupResult {
                    successBody(result)
                } else {
                    formBody
                }
            }

            Divider()

            HStack {
                Spacer()
                if setupResult == nil {
                    Button("Cancel") { isPresented = false }
                        .buttonStyle(.bordered)
                    Button(action: submit) {
                        if submitting {
                            ProgressView().controlSize(.small)
                        } else {
                            Text("Connect")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    // Tier 1 improvement (2): disable until ALL required
                    // fields are in the .valid state. Previously any
                    // non-empty string let the user submit.
                    .disabled(submitting || !isFormValid)
                } else {
                    Button("Done") { isPresented = false }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding(20)
        }
        .frame(width: 520, height: 600)
        .onAppear {
            // Pre-fill empty strings for each field so bindings are wired up.
            for field in plugin.credentialFields where credentialValues[field.key] == nil {
                credentialValues[field.key] = ""
            }
            // Tier 1 improvement (1): start the clipboard watcher so the
            // user can paste/auto-fill from @BotFather. The watcher
            // is scoped to the sheet's lifetime.
            startClipboardWatcher()
        }
        .onDisappear {
            // Be a good citizen — stop polling when the sheet closes.
            clipboardWatcher?.stop()
            clipboardWatcher = nil
            clipboardAutofillBannerClearTask?.cancel()
            clipboardAutofillBannerClearTask = nil
            handshakeTimerTask?.cancel()
            handshakeTimerTask = nil
        }
    }

    // MARK: - Form

    private var formBody: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Enter the credentials for your \(plugin.displayName) integration. They are sent to the plugin service URL you configured (HTTPS recommended for production; the URL must be http or https).")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(plugin.credentialFields) { field in
                credentialFieldRow(field)
            }

            // Tier 1 improvement: "Create Telegram Bot" button. Telegram
            // users almost always need to look up @BotFather — this
            // one-click button eliminates that discovery step.
            if plugin == .telegram {
                Button(action: { openBotFather() }) {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.up.forward.app.fill")
                            .scaledFont(size: 12)
                        Text("Create Telegram Bot")
                            .scaledFont(size: 13)
                    }
                }
                .buttonStyle(.bordered)
                .help("Open @BotFather in your browser to create a new bot and copy its token.")
            }

            if let error {
                Text(error)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.error)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(20)
    }

    /// Renders one credential field with the Tier 1 ✓ / ⚠ state
    /// indicator alongside. Encapsulated in a helper so the per-field
    /// layout (icon + label + status) can be unit-tested visually.
    @ViewBuilder
    private func credentialFieldRow(_ field: AICredentialField) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(field.label)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
            HStack(spacing: 8) {
                Group {
                    if field.isSecure {
                        SecureField(
                            field.placeholder,
                            text: Binding(
                                get: { credentialValues[field.key] ?? "" },
                                set: {
                                    credentialValues[field.key] = $0
                                    markUserEdited(field.key)
                                }
                            )
                        )
                    } else {
                        TextField(
                            field.placeholder,
                            text: Binding(
                                get: { credentialValues[field.key] ?? "" },
                                set: {
                                    credentialValues[field.key] = $0
                                    markUserEdited(field.key)
                                }
                            )
                        )
                    }
                }
                .textFieldStyle(.roundedBorder)

                // Tier 1 improvement (2): real-time ✓ / ⚠ indicator.
                tokenStateIndicator(for: field)
            }
            // Show a small confirmation banner when the clipboard
            // watcher auto-filled this field. Cleared on next edit.
            if lastClipboardAutofillKey == field.key {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.success)
                    Text("Detected from clipboard")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.success)
                }
            }
        }
    }

    /// Renders a small ✓ / ⚠ / blank indicator to the right of each
    /// field. Currently only Telegram tokens have a validator; other
    /// plugin credential fields render an empty Spacer.
    @ViewBuilder
    private func tokenStateIndicator(for field: AICredentialField) -> some View {
        // Only the Telegram bot_token field has a client-side
        // validator for now. Future: per-plugin validators.
        if plugin == .telegram, field.key == "bot_token" {
            switch TelegramTokenValidator.state(credentialValues[field.key]) {
            case .empty:
                EmptyView()
            case .valid:
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 16)
                    .foregroundColor(OmiColors.success)
                    .help("Looks like a valid Telegram bot token")
            case .invalid:
                Image(systemName: "exclamationmark.triangle.fill")
                    .scaledFont(size: 16)
                    .foregroundColor(OmiColors.error)
                    .help("Expected format: 123456789:AA… (numeric id + colon + 35+ alphanumerics)")
            }
        } else {
            EmptyView()
        }
    }

    // MARK: - Success

    private func successBody(_ result: SetupResponse) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            // Tier 1 improvement (4): two-step progress.
            // Step 1 — webhook registered, instant.
            // Step 2 — waiting for handshake.
            VStack(alignment: .leading, spacing: 10) {
                stepRow(
                    step: 1,
                    state: .complete,
                    title: "Bot configured",
                    subtitle: "Webhook registered with \(plugin.displayName)"
                )

                Divider().padding(.leading, 22)

                stepRow(
                    step: 2,
                    state: pollingForHandshake ? .inProgress : .pending,
                    title: pollingForHandshake
                        ? "Waiting for you to send /start in \(plugin.displayName)…"
                        : "Waiting for handshake",
                    subtitle: pollingForHandshake
                        ? "\(handshakeSecondsRemaining)s remaining — open the link below"
                        : "Use the QR code or deep link below to open \(plugin.displayName) on your phone."
                )

                if handshakeCompleted && setupResult != nil {
                    // Final success state — the polling loop confirmed
                    // /health was reachable during the handshake window.
                    // P1 (cubic): previously this checked `!pollingForHandshake`,
                    // which is also true on timeout — so the UI falsely
                    // reported "Connected" when the user never sent /start.
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(OmiColors.success)
                        Text("Connected")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)
                    }
                    .padding(.top, 4)
                } else if handshakeTimedOut && setupResult != nil {
                    // Handshake polling exhausted its window. Show a
                    // distinct "Timed out" state — different from
                    // "Connected" — so the user knows to retry.
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(OmiColors.error)
                        Text("Connection timed out")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)
                        Button("Retry") {
                            startHandshakePolling()
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    .padding(.top, 4)
                }
            }

            Divider().padding(.vertical, 4)

            // Tier 1 improvement (3): QR code alongside the deep link.
            // QR lets users with Telegram-on-phone scan instead of
            // copy/paste the deep link into a phone browser.
            deepLinkWithQR(result.deepLink)

            if let error {
                Text(error)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.error)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(20)
    }

    /// Render the deep link with a clickable Open button, a copy
    /// button, AND a scannable QR code. QR is the killer feature for
    /// the common case (Telegram is on the phone, Omi Desktop is on
    /// the laptop).
    @ViewBuilder
    private func deepLinkWithQR(_ deepLink: String) -> some View {
        VStack(spacing: 12) {
            // Row: deep link text + Open + Copy
            VStack(alignment: .leading, spacing: 8) {
                Text("Deep link")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
                HStack {
                    Text(deepLink)
                        .scaledFont(size: 12, design: .monospaced)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                    Button(action: { copyToClipboard(deepLink) }) {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                    .help("Copy deep link")
                    Button(action: { openURL(deepLink) }) {
                        Text("Open")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding(12)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(8)

            // Divider + QR (Tier 1)
            HStack(alignment: .center, spacing: 12) {
                Rectangle()
                    .fill(OmiColors.textTertiary.opacity(0.3))
                    .frame(height: 1)
                Text("or scan with your phone")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
                Rectangle()
                    .fill(OmiColors.textTertiary.opacity(0.3))
                    .frame(height: 1)
            }

            if ConnectSheet.isSafeDeepLink(deepLink, plugin: plugin) {
                // Safe path: the URL has the right scheme + per-plugin host.
                // The Open button is already gated by isSafeDeepLink; the
                // QR generator just renders pixels, so it would happily
                // produce a QR for any string — gate the RENDER too so a
                // compromised plugin can't phish via a scannable image.
                if let qrImage = QRCodeGenerator.generate(deepLink, size: 160) {
                    Image(nsImage: qrImage)
                        .interpolation(.none)  // crisp pixel edges
                        .resizable()
                        .scaledToFit()
                        .frame(width: 160, height: 160)
                        .padding(8)
                        .background(Color.white)
                        .cornerRadius(8)
                        .help("Scan with your phone camera to open the Telegram deep link")
                } else {
                    Text("(QR generation failed)")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }
            } else {
                // P1 (cubic): refuse to render a QR for an unsafe URL.
                // The Open button would also refuse, but a QR is a
                // separate attack surface — a user might scan the QR
                // even though they wouldn't click the button. Render an
                // explicit warning instead of a QR.
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(OmiColors.error)
                    Text("Refusing to render QR — plugin returned an unsafe URL")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.error)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(8)
            }
        }
    }

    /// Renders one numbered step in the progress indicator.
    @ViewBuilder
    private func stepRow(step: Int, state: StepState, title: String, subtitle: String?) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                Circle()
                    .fill(state.circleColor)
                    .frame(width: 22, height: 22)
                switch state {
                case .complete:
                    Image(systemName: "checkmark")
                        .scaledFont(size: 11, weight: .bold)
                        .foregroundColor(.white)
                case .inProgress:
                    ProgressView().controlSize(.small).scaleEffect(0.7)
                case .pending:
                    Text("\(step)")
                        .scaledFont(size: 11, weight: .bold)
                        .foregroundColor(.white)
                }
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(state.titleColor)
                if let subtitle {
                    Text(subtitle)
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
        }
    }

    private enum StepState {
        case complete, inProgress, pending
        var circleColor: Color {
            switch self {
            case .complete: return OmiColors.success
            case .inProgress: return OmiColors.purplePrimary
            case .pending: return OmiColors.textTertiary.opacity(0.3)
            }
        }
        var titleColor: Color {
            switch self {
            case .complete, .inProgress: return OmiColors.textPrimary
            case .pending: return OmiColors.textSecondary
            }
        }
    }

    // MARK: - Clipboard watcher

    /// Start watching the system clipboard for a Telegram bot token.
    /// Called from `.onAppear`. The watcher:
    /// - Emits when the clipboard string content changes
    /// - We auto-fill the first empty + non-user-edited credential field
    ///   whose value validates as a Telegram token
    /// - We show a "Detected from clipboard" confirmation banner
    private func startClipboardWatcher() {
        clipboardWatcher?.stop()
        let watcher = ClipboardWatcher { content in
            handleClipboardChange(content)
        }
        watcher.start()
        clipboardWatcher = watcher
    }

    private func handleClipboardChange(_ content: String) {
        // Only auto-fill fields the user hasn't edited manually.
        // Auto-fill targets: credential fields that are currently empty.
        guard TelegramTokenValidator.isValid(content) else { return }

        // Find the first auto-fillable field: empty + not user-edited.
        // (Telegram's first credential field is bot_token; WhatsApp has
        // multiple. We fill the first that matches.)
        guard let target = plugin.credentialFields.first(where: { field in
            credentialValues[field.key]?.isEmpty != false
                && !userEditedFields.contains(field.key)
        }) else { return }

        credentialValues[target.key] = content
        lastClipboardAutofillKey = target.key

        // Clear the confirmation banner after a few seconds so it
        // doesn't linger forever.
        clipboardAutofillBannerClearTask?.cancel()
        clipboardAutofillBannerClearTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            if !Task.isCancelled {
                lastClipboardAutofillKey = nil
            }
        }
    }

    private func markUserEdited(_ fieldKey: String) {
        // Once the user types into a field, don't let the clipboard
        // watcher overwrite their input.
        userEditedFields.insert(fieldKey)
        // Clear the auto-fill confirmation banner if the user edits
        // the field we just auto-filled.
        if lastClipboardAutofillKey == fieldKey {
            clipboardAutofillBannerClearTask?.cancel()
            lastClipboardAutofillKey = nil
        }
    }

    // MARK: - Helpers

    private var isFormValid: Bool {
        plugin.credentialFields.allSatisfy { field in
            let value = credentialValues[field.key] ?? ""
            // Trim and check non-empty.
            guard !value.trimmingCharacters(in: .whitespaces).isEmpty else {
                return false
            }
            // Tier 1 improvement (2): for the Telegram bot_token field,
            // also require the value to pass TelegramTokenValidator.
            // This catches typos before the round-trip to the plugin.
            if plugin == .telegram, field.key == "bot_token" {
                return TelegramTokenValidator.isValid(value)
            }
            return true
        }
    }

    private func submit() {
        error = nil
        submitting = true
        let credentials = credentialValues
        Task {
            do {
                let personaId = try await currentPersonaId()

                // Auto-create dev API key if not already configured.
                // The user's Firebase auth session is used — no manual
                // paste needed. This is the zero-config path: the user
                // just enters their bot token and clicks Connect.
                var effectiveDevKey = config.omiDevApiKey
                if effectiveDevKey.isEmpty {
                    let backendURL = config.discoveryBackendURL ?? "https://api.omi.me"
                    let isLocal = backendURL.contains("localhost") || backendURL.contains("127.0.0.1")
                    if isLocal {
                        // Can't create API key on local backend (Firebase
                        // audience mismatch). Leave empty — the plugin
                        // should already have the right key in its storage
                        // from the test persona setup.
                        log("ConnectSheet: local backend, skipping API key creation (use pre-configured key)")
                        effectiveDevKey = ""
                    } else {
                        log("ConnectSheet: auto-creating dev API key for persona \(personaId)")
                        effectiveDevKey = try await APIClient.shared.createAppKey(appId: personaId)
                        log("ConnectSheet: created dev API key (\(effectiveDevKey.count) chars)")
                        await MainActor.run {
                            config.omiDevApiKey = effectiveDevKey
                        }
                    }
                }

                let body = plugin.setupRequestBody(
                    credentials: credentials,
                    omiUid: currentUid(),
                    personaId: personaId,
                    omiDevApiKey: effectiveDevKey,
                    publicBaseUrl: config.pluginURL
                )
                let result = try await AICloneClient.shared.setup(
                    baseURL: config.pluginURL,
                    bearerToken: config.bearerToken,
                    plugin: plugin,
                    body: body
                )
                await MainActor.run {
                    // Persist the dev API key override if the user typed it
                    if !devApiKeyOverride.isEmpty {
                        config.omiDevApiKey = devApiKeyOverride
                    }
                    setupResult = result
                    submitting = false
                    startHandshakePolling()
                }
            } catch {
                await MainActor.run {
                    self.error = error.localizedDescription
                    submitting = false
                }
            }
        }
    }

    @State private var handshakeTimerTask: Task<Void, Never>?

    private func startHandshakePolling() {
        // Reset all handshake state so a retry starts clean.
        pollingForHandshake = true
        pollCount = 0
        handshakeCompleted = false
        handshakeTimedOut = false
        // Tier 1 improvement (4): countdown timer for the user.
        handshakeSecondsRemaining = ConnectSheet.maxPollIterations * 3
        handshakeTimerTask?.cancel()
        handshakeTimerTask = Task { @MainActor in
            while !Task.isCancelled,
                  handshakeSecondsRemaining > 0,
                  pollingForHandshake {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if !Task.isCancelled {
                    handshakeSecondsRemaining -= 1
                }
            }
        }

        Task {
            while pollCount < ConnectSheet.maxPollIterations {
                pollCount += 1
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                if Task.isCancelled { break }
                let reachable = (try? await AICloneClient.shared.health(
                    baseURL: config.pluginURL
                )) ?? false
                if reachable {
                    // P1 (cubic): the only path that sets handshakeCompleted
                    // is a successful /health hit during the polling window.
                    // Reaching this branch is necessary but not sufficient
                    // for a real handshake — the plugin doesn't yet expose
                    // a /status endpoint that confirms the user sent /start.
                    // When /status lands (Tier 2), this gate is upgraded
                    // to check the actual handshake-complete bit.
                    await MainActor.run {
                        handshakeCompleted = true
                        pollingForHandshake = false
                        handshakeTimerTask?.cancel()
                    }
                    break
                }
            }
            await MainActor.run {
                // Loop exited without setting handshakeCompleted — either
                // we hit the timeout (pollCount == maxPollIterations) or
                // the user cancelled. The UI distinguishes via the
                // handshakeTimedOut flag.
                if pollingForHandshake {
                    handshakeTimedOut = true
                }
                pollingForHandshake = false
                handshakeTimerTask?.cancel()
            }
        }
    }

    private func currentUid() -> String {
        // Reuse the existing user-id source (Firebase UID) from APIClient.
        // Falls back to "" if not authenticated; the plugin will reject.
        UserDefaults.standard.string(forKey: "auth_userId") ?? ""
    }

    private func currentPersonaId() async throws -> String {
        // If the plugin uses a local backend (not prod), we can't create
        // the persona from the desktop because the desktop's Firebase
        // token is from prod and the local backend rejects it (audience
        // mismatch). Instead, return an empty string and let the plugin's
        // /setup handler use whatever persona_id is already stored or
        // fall back to a default.
        let backendURL = config.discoveryBackendURL ?? "https://api.omi.me"
        let isLocal = backendURL.contains("localhost") || backendURL.contains("127.0.0.1")

        if isLocal {
            log("ConnectSheet: plugin uses local backend, skipping remote persona creation")
            // Return empty — the plugin will use the persona_id from its
            // own storage (set up via the test persona script) or the
            // plugin will handle it at /setup time.
            return ""
        }

        // Prod path
        if let persona = try? await APIClient.shared.getPersona() {
            return persona.id
        }
        log("ConnectSheet: no persona found, auto-creating one")
        let persona = try await APIClient.shared.getOrCreatePersona()
        return persona.id
    }

    private func copyToClipboard(_ s: String) {
        #if os(macOS)
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(s, forType: .string)
        #endif
    }

    private func openURL(_ s: String) {
        // P1 fix (cubic): a compromised plugin service could return a deep link
        // with a hostile scheme/host (e.g. `file://`, `ssh://`, or a phishing
        // domain) and `NSWorkspace.shared.open` would happily launch it.
        // The actual safety check is in `isSafeDeepLink(_:plugin:)` below so
        // it can be unit-tested without going through NSWorkspace.
        guard ConnectSheet.isSafeDeepLink(s, plugin: plugin) else {
            logger.warning("Refusing to open deep link with unsafe URL: \(s)")
            return
        }
        guard let url = URL(string: s) else { return }
        #if os(macOS)
        NSWorkspace.shared.open(url)
        #endif
    }

    private func openBotFather() {
        // @BotFather is the canonical Telegram bot-creation entry point.
        // Hardcoded URL — there's no plugin-provided URL here, so this
        // can't be phished. Deep-link scheme is https (in DeepLinkSafeScheme).
        #if os(macOS)
        NSWorkspace.shared.open(ConnectSheet.botFatherURL)
        #endif
    }

    /// Returns true iff the URL is one we're willing to hand to
    /// `NSWorkspace.shared.open` for the given plugin. The host check is
    /// bound to the plugin: a Telegram deep link (`t.me`) is only valid
    /// when connecting the Telegram plugin, etc. — a phishing attack
    /// returning a `t.me` URL inside a WhatsApp connect sheet is rejected.
    /// Pure function — extracted so the gate can be unit-tested without
    /// launching any actual application.
    static func isSafeDeepLink(_ s: String, plugin: AIPlugin) -> Bool {
        guard let url = URL(string: s),
              let scheme = url.scheme?.lowercased(),
              DeepLinkSafeScheme(rawValue: scheme) != nil,
              let host = url.host?.lowercased(),
              host == DeepLinkSafeHost.expected(for: plugin)
        else { return false }
        return true
    }
}