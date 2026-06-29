import SwiftUI

/// AI Clone settings page.
///
/// Shows the plugin service configuration at the top, then a stack of
/// per-plugin connection cards (Telegram, WhatsApp, and future plugins).
/// Each card handles its own connect/disconnect/toggle state.
///
/// The list of plugin cards is driven by `AIPlugin.allCases` — adding a new
/// plugin is a one-line enum addition, not a UI edit.
struct AIClonePage: View {
    @StateObject private var config = AICloneConfig.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                Text("AI Clone")
                    .scaledFont(size: 28, weight: .bold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Connect Omi to your messaging apps. Omi will reply on your behalf using your persona. Auto-reply is per-plugin for v0.1; per-chat toggles are coming in a follow-up.")
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
        VStack(alignment: .leading, spacing: 6) {
            Text("About AI Clone")
                .scaledFont(size: 12, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
            // Footer is intentionally short on guarantees. Real constraints
            // (HTTPS, private host) are validated in AICloneConfig.isValid
            // and AICloneClient.endpointURL — the UI just describes what
            // the user is doing, not what we're promising.
            Text("AI Clone uses your self-hosted plugin service to talk to Telegram, WhatsApp, and (coming soon) iMessage. Your bot tokens and API keys are sent only to the plugin URL you configure (HTTPS recommended). Messages are answered using your Omi persona.")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 12)
    }
}