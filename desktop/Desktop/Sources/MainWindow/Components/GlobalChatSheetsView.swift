import SwiftUI

/// A global invisible view that coordinates sheets and alerts triggered by the `ChatProvider`.
/// Placing this at the root window level ensures that authentication sheets (like Claude OAuth)
/// and limits are presented immediately, regardless of which page the user is currently viewing.
struct GlobalChatSheetsView: View {
  @ObservedObject var chatProvider: ChatProvider

  var body: some View {
    Color.clear
      .frame(width: 0, height: 0)
      .sheet(isPresented: $chatProvider.needsBrowserExtensionSetup) {
        BrowserExtensionSetup(
          onComplete: {
            chatProvider.needsBrowserExtensionSetup = false
          },
          onDismiss: {
            chatProvider.needsBrowserExtensionSetup = false
          },
          chatProvider: chatProvider
        )
        .fixedSize()
      }
      .sheet(isPresented: $chatProvider.isClaudeAuthRequired) {
        ClaudeAuthSheet(
          mode: .claudeLogin,
          onConnect: {
            chatProvider.startClaudeAuth()
          },
          onCancel: {
            chatProvider.isClaudeAuthRequired = false
            // Switch back to Omi AI (pi-mono) if auth cancelled
            Task {
              await chatProvider.switchBridgeMode(to: ChatProvider.BridgeMode.piMono)
            }
          }
        )
      }
      .alert("Upgrade Required", isPresented: $chatProvider.showOmiThresholdAlert) {
        Button("Upgrade to Omi Pro") {
          chatProvider.showOmiThresholdAlert = false
          if let url = URL(string: "https://omi.me/pricing") {
            NSWorkspace.shared.open(url)
          }
        }
        Button("Later", role: .cancel) {
          chatProvider.showOmiThresholdAlert = false
        }
      } message: {
        Text("Upgrade to Omi Pro for $199/month to continue chatting.")
      }
  }
}
