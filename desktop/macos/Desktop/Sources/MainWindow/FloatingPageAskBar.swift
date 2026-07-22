import OmiTheme
import SwiftUI

/// Floating "Ask omi anything" bar pinned over the Memory and Tasks pages so
/// chat is reachable from anywhere. Reuses the exact HomeAskBar element from
/// the Home page. Sending routes to the Home chat through
/// MainChatNavigationRequestStore — the same flow the floating bar's
/// "Continue in Omi" uses — so the answer lands in the one main timeline.
/// A bottom black fade keeps page content readable as it scrolls beneath.
/// Currently shelved: PageContentView's overlay wiring is commented out.
struct FloatingPageAskBar: View {
  @ObservedObject var chatProvider: ChatProvider
  @Binding var selectedTabIndex: Int
  @FocusState private var askFieldFocused: Bool

  var body: some View {
    HomeAskBar(
      text: $chatProvider.draftText,
      isSending: chatProvider.isSending,
      isStopping: chatProvider.isStopping,
      isConnectActive: false,
      focus: $askFieldFocused,
      attachments: $chatProvider.pendingAttachments,
      onAttachmentsAdded: { urls in
        chatProvider.addAttachments(urls.compactMap { ChatAttachment.from(url: $0) })
      },
      onAttachmentRemoved: { id in
        chatProvider.removePendingAttachment(id: id)
      },
      onSend: sendFromPageBar,
      onStop: { chatProvider.stopAgent(owner: .mainChat) },
      onConnect: openConnectOnHome,
      onActivate: { askFieldFocused = true }
    )
    .frame(maxWidth: 720)
    .padding(.horizontal, OmiSpacing.section)
    .padding(.bottom, OmiSpacing.xl)
    .padding(.top, 64)
    .frame(maxWidth: .infinity)
    .background(
      LinearGradient(
        stops: [
          .init(color: Color.black.opacity(0), location: 0),
          .init(color: Color.black.opacity(0.85), location: 0.4),
          .init(color: Color.black, location: 0.62),
          .init(color: Color.black, location: 1),
        ],
        startPoint: .top,
        endPoint: .bottom
      )
      .allowsHitTesting(false)
    )
  }

  private func sendFromPageBar() {
    let draft = chatProvider.draftText
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    AnalyticsManager.shared.chatMessageSent(
      messageLength: text.count,
      hasSelectedAppContext: false,
      source: "page_ask_bar"
    )
    MainChatNavigationRequestStore.shared.request()
    guard !chatProvider.isSending else { return }
    Task { await chatProvider.sendMainDraft(draft) }
  }

  /// The Connect tray is a Home surface — jump there and open it, the same
  /// path the automation bridge's home_connect_toggle uses.
  private func openConnectOnHome() {
    selectedTabIndex = SidebarNavItem.dashboard.rawValue
    DispatchQueue.main.async {
      NotificationCenter.default.post(name: .homeStageToggleConnect, object: nil)
    }
  }
}
