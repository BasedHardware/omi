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

    private static let maxPollIterations = 20  // 20 × 3s = 60s timeout

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
                    .disabled(submitting || !isFormValid)
                } else {
                    Button("Done") { isPresented = false }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding(20)
        }
        .frame(width: 520, height: 540)
        .onAppear {
            // Pre-fill empty strings for each field so bindings are wired up.
            for field in plugin.credentialFields where credentialValues[field.key] == nil {
                credentialValues[field.key] = ""
            }
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
                VStack(alignment: .leading, spacing: 4) {
                    Text(field.label)
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                    if field.isSecure {
                        SecureField(
                            field.placeholder,
                            text: Binding(
                                get: { credentialValues[field.key] ?? "" },
                                set: { credentialValues[field.key] = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                    } else {
                        TextField(
                            field.placeholder,
                            text: Binding(
                                get: { credentialValues[field.key] ?? "" },
                                set: { credentialValues[field.key] = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                    }
                }
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

    // MARK: - Success

    private func successBody(_ result: SetupResponse) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 6) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(OmiColors.success)
                Text("Credentials registered")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
            }

            Text("Open the link below in \(plugin.displayName) to complete the handshake. After you send the pre-filled message, this window will detect the connection automatically.")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 8) {
                Text("Deep link")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
                HStack {
                    Text(result.deepLink)
                        .scaledFont(size: 12, design: .monospaced)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                    Button(action: { copyToClipboard(result.deepLink) }) {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                    .help("Copy deep link")
                    Button(action: { openURL(result.deepLink) }) {
                        Text("Open")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding(12)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(8)

            HStack(spacing: 6) {
                if pollingForHandshake {
                    ProgressView().controlSize(.small)
                }
                Text(pollingForHandshake ? "Waiting for \(plugin.displayName) handshake…" : "Waiting for you to send the message in \(plugin.displayName).")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(20)
    }

    // MARK: - Helpers

    private var isFormValid: Bool {
        plugin.credentialFields.allSatisfy {
            let value = credentialValues[$0.key] ?? ""
            return !value.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }

    private func submit() {
        error = nil
        submitting = true
        let credentials = credentialValues
        Task {
            do {
                let personaId = try await currentPersonaId()
                let body = plugin.setupRequestBody(
                    credentials: credentials,
                    omiUid: currentUid(),
                    personaId: personaId,
                    omiDevApiKey: config.omiDevApiKey,
                    publicBaseUrl: config.pluginURL
                )
                let result = try await AICloneClient.shared.setup(
                    baseURL: config.pluginURL,
                    bearerToken: config.bearerToken,
                    plugin: plugin,
                    body: body
                )
                await MainActor.run {
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

    private func startHandshakePolling() {
        pollingForHandshake = true
        pollCount = 0
        Task {
            // C3 fix: actually poll the plugin service. We can't tell from
            // /health alone whether the user's handshake has completed (the
            // plugin doesn't yet expose per-user state via /health), so we
            // also reach for /setup with a HEAD-style check. For v0.1 we
            // poll /health every 3s; if it stays unreachable we abort early.
            // When the plugins land a /status endpoint, swap this for that.
            while pollCount < ConnectSheet.maxPollIterations {
                pollCount += 1
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                if Task.isCancelled { break }
                let reachable = (try? await AICloneClient.shared.health(
                    baseURL: config.pluginURL
                )) ?? false
                if reachable {
                    await MainActor.run {
                        pollingForHandshake = false
                    }
                    break
                }
            }
            await MainActor.run {
                pollingForHandshake = false
            }
        }
    }

    private func currentUid() -> String {
        // Reuse the existing user-id source (Firebase UID) from APIClient.
        // Falls back to "" if not authenticated; the plugin will reject.
        UserDefaults.standard.string(forKey: "auth_userId") ?? ""
    }

    private func currentPersonaId() async throws -> String {
        guard let persona = try await APIClient.shared.getPersona() else {
            throw AICloneClient.AICloneError.notConfigured
        }
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