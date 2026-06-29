import SwiftUI

/// Per-plugin connection card for the AI Clone page.
///
/// One parameterized card drives both the Telegram and WhatsApp tiles —
/// everything that differs between the two lives on the `AIPlugin` enum
/// (display name, icon color, credential fields). Previously this was
/// duplicated as TelegramCard.swift + WhatsAppCard.swift (~330 LOC);
/// this file is the single source of truth.
struct PluginCard: View {
    let plugin: AIPlugin
    @ObservedObject var config: AICloneConfig
    @State private var showingConnect = false
    @State private var connectionState: ConnectionState = .notConnected
    @State private var autoReplyEnabled = false
    @State private var toggleInFlight = false

    enum ConnectionState: Equatable {
        case notConnected
        case connected(since: Date)
        case error(String)

        var isConnected: Bool {
            if case .connected = self { return true }
            return false
        }

        var displayStatus: String {
            switch self {
            case .notConnected: return "Not connected"
            case .connected: return "Connected"
            case .error(let msg): return "Error: \(msg)"
            }
        }
    }

    var body: some View {
        pluginCardChrome {
            content
        }
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
        HStack(spacing: 8) {
            Image(systemName: plugin.systemImage)
                .scaledFont(size: 22)
                .foregroundColor(plugin.accentColor)
                .frame(width: 36, height: 36)
                .background(plugin.accentColor.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(plugin.displayName)
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text(connectionState.displayStatus)
                    .scaledFont(size: 12)
                    .foregroundColor(statusColor)
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
                Text("Connect \(plugin.displayName)")
                    .scaledFont(size: 13, weight: .medium)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!config.isFullyConfigured)
            .help(config.isFullyConfigured ? "" : "Configure the plugin service URL, bearer token, and dev API key first")
        }
    }

    private var connectedControls: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Auto-reply")
                    .scaledFont(size: 13, weight: .medium)
                Spacer()
                Toggle("", isOn: $autoReplyEnabled)
                    .labelsHidden()
                    // C2: per-chat toggle requires a chat_id/phone from a completed
                    // handshake, which we don't track yet. v0.1 ships disabled;
                    // the toggle becomes functional once /global-toggle lands on
                    // the plugin backend (separate PR).
                    .disabled(true)
                    .onChange(of: autoReplyEnabled) { _, newValue in
                        Task { await flipAutoReply(enabled: newValue) }
                    }
            }

            Text("Auto-reply activates once you send a message in \(plugin.displayName) and the handshake completes.")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .fixedSize(horizontal: false, vertical: true)

            Button("Disconnect", role: .destructive) {
                connectionState = .notConnected
                autoReplyEnabled = false
            }
            .buttonStyle(.bordered)
            // I1: Disconnect is local-only — clears the in-app connection view
            // but does not tell the plugin service to forget the stored
            // credentials. To fully disconnect, the user must also remove the
            // webhook/bot from the platform's admin (Telegram @BotFather /
            // Meta Business dashboard). This is intentional for v0.1; a future
            // DELETE /setup endpoint on the plugin can make it remote too.
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
        return "since " + formatter.localizedString(for: date, relativeTo: Date())
    }

    /// Stub for the (future) per-chat / global toggle. The toggle is currently
    /// disabled in the UI; this exists so the wiring is in place when the
    /// plugin backend adds `POST /global-toggle`.
    private func flipAutoReply(enabled: Bool) async {
        toggleInFlight = true
        defer { toggleInFlight = false }
        try? await Task.sleep(nanoseconds: 200_000_000)
        _ = enabled
    }
}

/// Shared card chrome — wraps the per-plugin content in the standard
/// section background + corner radius.
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
    /// Accent color for the plugin card icon. Mapped from the plugin enum
    /// rather than hardcoded in the view, so adding a third plugin (e.g.
    /// iMessage) is a one-line change.
    var accentColor: Color {
        switch self {
        case .telegram: return OmiColors.info
        case .whatsapp: return OmiColors.success
        }
    }
}