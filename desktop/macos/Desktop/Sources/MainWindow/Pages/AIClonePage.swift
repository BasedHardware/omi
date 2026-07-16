import SwiftUI
import OmiTheme

/// AI Clone settings page.
///
/// Shows the plugin service configuration at the top (with auto-discovery
/// banner when detected), then per-plugin connection cards.
struct AIClonePage: View {
    @StateObject private var config = AICloneConfig.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            VStack(alignment: .leading, spacing: 0) {
                Text("Omi replies to messages on your behalf using your persona. Connect a messaging app to get started.")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 32)
            .padding(.top, 32)
            .padding(.bottom, 20)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    PluginURLCard(config: config)

                    ForEach(AIPlugin.allCases) { plugin in
                        PluginCard(plugin: plugin, config: config)
                    }

                    infoFooter
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 32)
            }
        }
    }

    private var infoFooter: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "info.circle")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                Text("How it works")
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundColor(OmiColors.textTertiary)
            }

            VStack(alignment: .leading, spacing: 4) {
                infoStep(number: "1", text: "Start the plugin service on your machine")
                infoStep(number: "2", text: "Connect a messaging app — you'll get a link to open on your phone")
                infoStep(number: "3", text: "Send a message and Omi replies using your persona")
            }
            .padding(.leading, 4)

            Text("Credentials are stored in the macOS Keychain. The plugin URL and bearer token are auto-filled when the plugin is running locally; your developer API key is still entered manually unless the plugin runs in dev mode.")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)
        }
        .padding(16)
        .background(OmiColors.backgroundTertiary)
        .cornerRadius(10)
    }

    private func infoStep(number: String, text: String) -> some View {
        HStack(spacing: 8) {
            Text(number)
                .scaledFont(size: 11, weight: .bold)
                .foregroundColor(.white)
                .frame(width: 18, height: 18)
                .background(OmiColors.textTertiary.opacity(0.6))
                .clipShape(Circle())
            Text(text)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}