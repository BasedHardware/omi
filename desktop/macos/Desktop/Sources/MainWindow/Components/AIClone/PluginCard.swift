import SwiftUI

/// Per-plugin connection card for the AI Clone page.
///
/// One parameterized card drives both the Telegram and WhatsApp tiles.
/// Shows connection status, auto-reply toggle, and disconnect button.
struct PluginCard: View {
    let plugin: AIPlugin
    @ObservedObject var config: AICloneConfig
    @State private var showingConnect = false
    @State private var connectionState: ConnectionState = .notConnected
    @State private var autoReplyEnabled = false

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
            .sheet(isPresented: $showingConnect) {
                ConnectSheet(plugin: plugin, config: config, isPresented: $showingConnect)
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
                    Circle()
                        .fill(connectionState.isConnected ? OmiColors.success : OmiColors.textTertiary)
                        .frame(width: 6, height: 6)
                    Text(connectionState.displayStatus)
                        .scaledFont(size: 12)
                        .foregroundColor(statusColor)
                }
            }

            Spacer()

            if case .connected(let since) = connectionState {
                Text(connectedSinceText(since))
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
            }
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
            .disabled(!config.isFullyConfigured)
            .help(config.isFullyConfigured ? "" : "Configure the plugin service first")
        }
    }

    private var connectedControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Auto-reply toggle row \u2014 disabled for v0.1.
            //
            // The desktop doesn't know the user's chat_id/phone (those
            // are bound on the plugin side after the user sends /start
            // from their phone). Toggling requires a real chatId, not
            // the placeholder "global" sentinel we used to send \u2014
            // both /toggle endpoints (Telegram + WhatsApp) return 403
            // for unknown chat_id. P1 (cubic).
            //
            // Per-chat toggles ship in a follow-up once the plugin
            // exposes a chat list API the desktop can enumerate.
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Auto-reply")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                    Text("Manage from your phone — send /start in Telegram or the connected WhatsApp chat")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }
                Spacer()
                Toggle("", isOn: $autoReplyEnabled)
                    .labelsHidden()
                    .disabled(true)
            }

            Divider()

            // Disconnect
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

    // MARK: - Helpers

    private var statusColor: Color {
        switch connectionState {
        case .notConnected: return OmiColors.textTertiary
        case .connected: return OmiColors.success
        case .error: return OmiColors.error
        }
    }

    private func connectedSinceText(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
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