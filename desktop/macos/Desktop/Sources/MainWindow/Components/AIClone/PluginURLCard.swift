import SwiftUI
import OmiTheme

/// Card showing the configured AI Clone plugin service URL + credentials.
///
/// Shows a green "auto-discovered" banner when the plugin was found via
/// the discovery file (~/.config/omi/ai-clone-plugin.json). Includes a
/// health-check indicator that pings the plugin's /health endpoint.
struct PluginURLCard: View {
    @ObservedObject var config: AICloneConfig
    @State private var showingEditor = false
    @State private var healthStatus: HealthStatus = .unknown

    enum HealthStatus {
        case unknown, reachable, unreachable
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header row
            HStack(spacing: 8) {
                Image(systemName: "server.rack")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)
                Text("Plugin Service")
                    .scaledFont(size: 17, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                healthIndicator
                Button(action: { showingEditor = true }) {
                    Text(config.isFullyConfigured ? "Edit" : "Configure")
                        .scaledFont(size: 13, weight: .medium)
                }
                .buttonStyle(.borderless)
                .foregroundColor(OmiColors.purplePrimary)
            }

            // Auto-discovery banner
            if config.isAutoDiscovered && config.isFullyConfigured {
                HStack(spacing: 6) {
                    Image(systemName: "sparkles")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.success)
                    Text("Auto-discovered from local plugin")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.success)
                    Spacer()
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(OmiColors.success.opacity(0.08))
                .cornerRadius(8)
            }

            // Status rows
            if config.isFullyConfigured {
                statusRow(
                    icon: "link",
                    label: "URL",
                    value: maskedURL(config.pluginURL),
                    isOK: true
                )
                statusRow(
                    icon: "key.fill",
                    label: "Bearer Token",
                    value: String(repeating: "•", count: 8),
                    isOK: config.isBearerTokenConfigured
                )
                if !config.pluginDevMode {
                    statusRow(
                        icon: "person.crop.square.fill",
                        label: "Dev API Key",
                        value: config.isDevApiKeyConfigured ? String(repeating: "•", count: 8) : "Required",
                        isOK: config.isDevApiKeyConfigured
                    )
                }
            } else {
                Text(config.pluginURL.isEmpty
                     ? "Start the plugin service on your machine. If it's already running, the settings will be auto-detected."
                     : "Configure your self-hosted AI Clone plugin service. You'll need: the service URL, the bearer token, and your omi_dev_… developer API key.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(20)
        .background(OmiColors.backgroundSecondary)
        .cornerRadius(12)
        .sheet(isPresented: $showingEditor) {
            PluginServiceEditorSheet(config: config, isPresented: $showingEditor)
        }
        .task {
            await checkHealth()
        }
    }

    // MARK: - Health indicator

    @ViewBuilder
    private var healthIndicator: some View {
        switch healthStatus {
        case .unknown:
            Circle()
                .fill(OmiColors.textTertiary.opacity(0.3))
                .frame(width: 8, height: 8)
        case .reachable:
            HStack(spacing: 4) {
                Circle().fill(OmiColors.success).frame(width: 8, height: 8)
                Text("Online")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.success)
            }
        case .unreachable:
            HStack(spacing: 4) {
                Circle().fill(OmiColors.error).frame(width: 8, height: 8)
                Text("Offline")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.error)
            }
        }
    }

    @MainActor
    private func checkHealth() async {
        guard config.isPluginURLConfigured else {
            healthStatus = .unknown
            return
        }
        do {
            let ok = try await AICloneClient.shared.health(baseURL: config.pluginURL)
            healthStatus = ok ? .reachable : .unreachable
        } catch {
            healthStatus = .unreachable
        }
    }

    // MARK: - Helpers

    private func statusRow(icon: String, label: String, value: String, isOK: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: 16)
            Text(label)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .frame(width: 110, alignment: .leading)
            Text(value)
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(OmiColors.textPrimary)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer()
            Image(systemName: isOK ? "checkmark.circle.fill" : "circle")
                .foregroundColor(isOK ? OmiColors.success : OmiColors.textTertiary)
        }
    }

    private func maskedURL(_ raw: String) -> String {
        guard let url = URL(string: raw) else { return raw }
        return "\(url.scheme ?? "https")://\(url.host ?? raw)\(url.path.isEmpty ? "" : "/…")"
    }
}

/// Sheet for editing the three plugin service values.
struct PluginServiceEditorSheet: View {
    @ObservedObject var config: AICloneConfig
    @Binding var isPresented: Bool

    @State private var draftURL: String = ""
    @State private var draftBearer: String = ""
    @State private var draftDevKey: String = ""
    @State private var testingConnection = false
    @State private var testResult: TestResult?

    enum TestResult: Equatable {
        case success
        case failure(String)
        var isSuccess: Bool { if case .success = self { return true }; return false }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Plugin Service")
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
                VStack(alignment: .leading, spacing: 16) {
                    fieldRow(
                        title: "Plugin Service URL",
                        text: $draftURL,
                        placeholder: "https://my-omi-clone.example.com",
                        isSecure: false,
                        helpText: "HTTPS URL of your self-hosted plugin service."
                    )
                    fieldRow(
                        title: "Bearer Token",
                        text: $draftBearer,
                        placeholder: "Token set as AI_CLONE_PLUGIN_TOKEN on the plugin service",
                        isSecure: true,
                        helpText: "Sent as Authorization: Bearer on every request to the plugin service."
                    )
                    fieldRow(
                        title: "Omi Dev API Key",
                        text: $draftDevKey,
                        placeholder: "omi_dev_…",
                        isSecure: true,
                        helpText: config.pluginDevMode
                            ? "Optional in dev mode — the local mock persona doesn't validate it."
                            : "Forwarded to the plugin so it can call the backend persona chat API on your behalf. Create one in Omi Settings → Developer."
                    )

                    if let result = testResult {
                        HStack(spacing: 6) {
                            Image(systemName: result.isSuccess ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                .foregroundColor(result.isSuccess ? OmiColors.success : OmiColors.error)
                            Text(testResultMessage(result))
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textSecondary)
                        }
                    }
                }
                .padding(20)
            }

            Divider()

            HStack(spacing: 8) {
                Button(action: testConnection) {
                    if testingConnection {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Test Connection")
                            .scaledFont(size: 13)
                    }
                }
                .buttonStyle(.bordered)
                .disabled(testingConnection || draftURL.isEmpty)

                Spacer()

                Button("Cancel") { isPresented = false }
                    .buttonStyle(.bordered)
                Button("Save") {
                    config.pluginURL = draftURL
                    config.bearerToken = draftBearer
                    config.omiDevApiKey = draftDevKey
                    isPresented = false
                }
                .buttonStyle(.borderedProminent)
                .disabled(!isValid)
            }
            .padding(20)
        }
        .frame(width: 560, height: 560)
        .onAppear {
            draftURL = config.pluginURL
            draftBearer = config.bearerToken
            draftDevKey = config.omiDevApiKey
        }
    }

    private var isValid: Bool {
        guard !draftURL.isEmpty,
              let url = URL(string: draftURL),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https"
        else { return false }
        return true
    }

    private func fieldRow(title: String, text: Binding<String>, placeholder: String, isSecure: Bool, helpText: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
            if isSecure {
                SecureField("", text: text, prompt: Text(placeholder).foregroundColor(OmiColors.textTertiary))
                    .textFieldStyle(.roundedBorder)
            } else {
                TextField("", text: text, prompt: Text(placeholder).foregroundColor(OmiColors.textTertiary))
                    .textFieldStyle(.roundedBorder)
            }
            Text(helpText)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func testConnection() {
        testingConnection = true
        testResult = nil
        Task {
            do {
                let ok = try await AICloneClient.shared.health(baseURL: draftURL)
                await MainActor.run {
                    testResult = ok ? .success : .failure("Plugin returned non-200")
                    testingConnection = false
                }
            } catch {
                await MainActor.run {
                    testResult = .failure(error.localizedDescription)
                    testingConnection = false
                }
            }
        }
    }

    private func testResultMessage(_ result: TestResult) -> String {
        switch result {
        case .success: return "Plugin service reachable."
        case .failure(let msg): return msg
        }
    }
}