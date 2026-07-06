import SwiftUI
import OmiTheme

/// Per-plugin connection card for the AI Clone page.
struct PluginCard: View {
    let plugin: AIPlugin
    @ObservedObject var config: AICloneConfig
    @State private var showingConnect = false
    @State private var connectionState: ConnectionState = .notConnected
    @State private var autoReplyEnabled = false
    @State private var toggleInFlight = false
    @State private var checkingStatus = false
    @State private var connectedChatId: String? = nil
    @State private var connectedBotName: String? = nil

    enum ConnectionState: Equatable {
        case notConnected
        case connected(since: Date)
        case error(String)

        var isConnected: Bool { if case .connected = self { return true }; return false }
        var displayStatus: String {
            switch self {
            case .notConnected: return "Not connected"
            case .connected: return "Connected"
            case .error(let msg): return "Error: \(msg)"
            }
        }
    }

    var body: some View {
        pluginCardChrome { content }
            .sheet(isPresented: $showingConnect, onDismiss: {
                // Re-check status after ConnectSheet closes
                Task { await checkStatus() }
            }) {
                ConnectSheet(plugin: plugin, config: config, isPresented: $showingConnect)
            }
            .task {
                await checkStatus()
            }
    }

    // MARK: - Content

    private var content: some View {
        VStack(alignment: .leading, spacing: 14) {
            statusHeader
            if connectionState.isConnected {
                connectedControls
            } else {
                notConnectedControls
            }
        }
    }

    private var statusHeader: some View {
        HStack(spacing: 12) {
            Image(systemName: plugin.systemImage)
                .scaledFont(size: 22)
                .foregroundColor(.white)
                .frame(width: 40, height: 40)
                .background(plugin.accentColor)
                .clipShape(RoundedRectangle(cornerRadius: 10))

            VStack(alignment: .leading, spacing: 2) {
                Text(plugin.displayName)
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                HStack(spacing: 4) {
                    if checkingStatus {
                        ProgressView().controlSize(.mini)
                    } else {
                        Circle()
                            .fill(connectionState.isConnected ? OmiColors.success : OmiColors.textTertiary)
                            .frame(width: 6, height: 6)
                    }
                    Text(connectionState.displayStatus)
                        .scaledFont(size: 12)
                        .foregroundColor(statusColor)
                    if let botName = connectedBotName, !botName.isEmpty, connectionState.isConnected {
                        Text("\u{00B7} @\(botName)")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
            }

            Spacer()
        }
    }

    private var notConnectedControls: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(plugin.tagline)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            Button(action: { showingConnect = true }) {
                Label("Connect", systemImage: "link.badge.plus")
                    .scaledFont(size: 13, weight: .medium)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!config.isPluginReady)
            .help(config.isPluginReady ? "" : "Plugin service not configured")
        }
    }

    private var connectedControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Auto-reply")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                    Text(autoReplyEnabled ? "Omi replies to messages automatically" : "Omi won't reply until you enable this")
                        .scaledFont(size: 11)
                        .foregroundColor(autoReplyEnabled ? OmiColors.success : OmiColors.textTertiary)
                }
                Spacer()
                if toggleInFlight {
                    ProgressView().controlSize(.small)
                }
                Toggle("", isOn: $autoReplyEnabled)
                    .labelsHidden()
                    .disabled(toggleInFlight)
                    .onChange(of: autoReplyEnabled) { _, newValue in
                        Task { await flipAutoReply(enabled: newValue) }
                    }
            }

            Divider()

            HStack {
                Spacer()
                Button("Disconnect", role: .destructive) {
                    connectionState = .notConnected
                    autoReplyEnabled = false
                }
                .buttonStyle(.bordered)
                .scaledFont(size: 12)
            }
        }
    }

    // MARK: - Status check

    private func checkStatus() async {
        // Only check status if this card's plugin type matches the
        // discovered plugin type. The /status endpoint is plugin-specific
        // (Telegram plugin returns Telegram chats, WhatsApp returns
        // WhatsApp chats). Without this guard, both cards would call
        // the same endpoint and both show "Connected" even if only
        // one is actually connected.
        guard config.isPluginReady else { return }
        
        // Check if the discovery file's plugin_type matches this card
        // If the plugin is Telegram, only the Telegram card checks status
        // If no discovery (manual config), only Telegram checks (the
        // currently implemented plugin)
        if let discovery = PluginDiscovery.read() {
            let discoveredType = discovery.pluginType.lowercased()
            let cardType: String
            switch plugin {
            case .telegram: cardType = "telegram"
            case .whatsapp: cardType = "whatsapp"
            }
            guard discoveredType == cardType else {
                // This card's plugin type doesn't match the running plugin
                return
            }
        } else {
            // No discovery file — only Telegram checks status
            guard plugin == .telegram else { return }
        }
        
        checkingStatus = true
        defer { checkingStatus = false }
        do {
            let status = try await AICloneClient.shared.status(
                baseURL: config.pluginURL,
                bearerToken: config.bearerToken
            )
            if (status.connectedChats ?? 0) > 0 {
                await MainActor.run {
                    connectionState = .connected(since: Date())
                    autoReplyEnabled = status.autoReplyEnabled ?? false
                    connectedChatId = status.firstChatId
                    connectedBotName = status.botUsername
                }
            } else {
                await MainActor.run {
                    connectionState = .notConnected
                    connectedChatId = nil
                    connectedBotName = nil
                }
            }
        } catch {
            // Status check failed — don't change the state, might be a
            // transient network issue
        }
    }

    // MARK: - Helpers

    private var statusColor: Color {
        switch connectionState {
        case .notConnected: return OmiColors.textTertiary
        case .connected: return OmiColors.success
        case .error: return OmiColors.error
        }
    }

    private func flipAutoReply(enabled: Bool) async {
        toggleInFlight = true
        defer { toggleInFlight = false }
        guard let chatId = connectedChatId else {
            log("PluginCard: no connected chat_id for toggle")
            await MainActor.run { autoReplyEnabled = !enabled }
            return
        }
        do {
            let body = plugin.toggleRequestBody(
                chatId: "all",
                enabled: enabled
            )
            _ = try await AICloneClient.shared.toggle(
                baseURL: config.pluginURL,
                bearerToken: config.bearerToken,
                plugin: plugin,
                body: body
            )
            log("PluginCard: toggle auto-reply \(enabled ? "ON" : "OFF") for \(plugin.displayName) (chat_id=\(chatId))")
        } catch {
            log("PluginCard: toggle failed: \(error)")
            await MainActor.run { autoReplyEnabled = !enabled }
        }
    }
}

/// Shared card chrome.
@ViewBuilder
func pluginCardChrome<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
    VStack(alignment: .leading, spacing: 0) {
        content()
    }
    .padding(20)
    .background(OmiColors.backgroundSecondary)
    .cornerRadius(12)
}

extension AIPlugin {
    var accentColor: Color {
        switch self {
        case .telegram: return OmiColors.info
        case .whatsapp: return OmiColors.success
        }
    }
}