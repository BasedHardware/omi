import SwiftUI

/// WhatsApp tab — a native WhatsApp-style view of your chats. Shows the full
/// conversation, with an Omi-drafted reply pre-filled in the compose bar that you
/// review, edit, and send. Per 1:1 chat, an opt-in "Auto-reply" switch lets Omi
/// draft and send replies to new inbound messages automatically (off by default).
///
/// Shared row/header/bubble/compose UI lives in `MessagingInboxKit` so this tab,
/// iMessage, and Telegram look and behave identically.
struct WhatsAppInboxPage: View {
  @ObservedObject private var store = WhatsAppInboxStore.shared

  // WhatsApp brand green (#25D366) — non-purple, on-brand accent.
  private static let whatsappGreen = Color(red: 0.145, green: 0.827, blue: 0.400)

  var body: some View {
    Group {
      if store.permissionNeeded {
        permissionCard
      } else {
        HStack(spacing: 0) {
          conversationList
            .frame(width: 300)
          Divider()
          if let chat = store.selectedChat {
            ChatDetailView(chat: chat, store: store, accent: Self.whatsappGreen)
          } else {
            emptyDetail
          }
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
    .task {
      await store.load()
      store.startWatching()
    }
    // NB: do NOT stopWatching() on disappear — the singleton store keeps its
    // watcher (and auto-reply) alive app-wide even when this tab isn't visible.
  }

  // MARK: conversation list

  private var conversationList: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: 10) {
        Text("WhatsApp")
          .scaledFont(size: 20, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        Button { Task { await store.load() } } label: {
          Image(systemName: "arrow.clockwise").foregroundColor(OmiColors.textSecondary)
        }
        .buttonStyle(.plain)
        .disabled(store.isLoading)
      }
      .padding(.horizontal, 16)
      .padding(.vertical, 14)

      if store.isLoading && store.chats.isEmpty {
        HStack(spacing: 8) {
          ProgressView().controlSize(.small)
          Text("Loading chats…").scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
        }
        .padding(16)
        Spacer()
      } else if store.chats.isEmpty {
        Text("No recent conversations.")
          .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
          .padding(16)
        Spacer()
      } else {
        ScrollView {
          LazyVStack(spacing: 0) {
            ForEach(Array(store.chats.enumerated()), id: \.element.id) { idx, chat in
              InboxConversationRow(
                name: chat.displayName, preview: chat.lastPreview, time: chat.lastDate,
                avatarData: chat.avatarImageData, isSelected: chat.id == store.selectedChatID,
                draftReady: store.preDrafts[chat.id] != nil,
                needsInput: store.needsInputReasons[chat.id] != nil,
                accent: Self.whatsappGreen
              )
              .onTapGesture { store.selectedChatID = chat.id }
              if idx < store.chats.count - 1 {
                Divider().overlay(OmiColors.textTertiary.opacity(0.18)).padding(.leading, 62)
              }
            }
          }
        }
      }
    }
    .background(MessagingInbox.sidebarBackground)
  }

  private var emptyDetail: some View {
    VStack(spacing: 8) {
      Image(systemName: "message").font(.system(size: 34)).foregroundColor(OmiColors.textTertiary)
      Text("Select a conversation").scaledFont(size: 14).foregroundColor(OmiColors.textSecondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var permissionCard: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Grant Full Disk Access")
        .scaledFont(size: 16, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
      Text(
        "Omi needs Full Disk Access to read WhatsApp. Turn it on in System Settings → Privacy & Security → Full Disk Access, then quit and reopen Omi."
      )
      .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
      .fixedSize(horizontal: false, vertical: true)
      Button("Open System Settings") { WhatsAppPermissionPolicy.openFullDiskAccessSettings() }
        .buttonStyle(.borderedProminent).tint(.white).foregroundColor(.black)
    }
    .padding(20)
    .frame(maxWidth: 460, alignment: .leading)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

// MARK: - Chat detail (bubbles + compose)

private struct ChatDetailView: View {
  let chat: WhatsAppChat
  @ObservedObject var store: WhatsAppInboxStore
  let accent: Color

  @State private var draft = ""
  @State private var isDrafting = false
  @State private var isSending = false
  @State private var errorText: String?
  @State private var infoText: String?

  var body: some View {
    VStack(spacing: 0) {
      InboxChatHeader(name: chat.displayName, avatarData: chat.avatarImageData) {
        if store.canAutoReply(chat.chatID) {
          autoReplyToggle
        }
      }
      Divider()

      // Bubbles
      ScrollViewReader { proxy in
        ScrollView {
          LazyVStack(spacing: 2) {
            ForEach(Array(chat.bubbles.enumerated()), id: \.element.id) { idx, bubble in
              InboxBubble(
                text: bubble.text, isFromMe: bubble.isFromMe, accent: accent,
                reserveGutter: chat.isGroup && !bubble.isFromMe,
                senderName: shouldShowSender(at: idx) ? bubble.senderName : nil,
                senderAvatarData: bubble.senderImage,
                imagePath: bubble.imagePath,
                caption: (bubble.imagePath != nil && !bubble.text.isEmpty) ? bubble.text : nil
              )
              .id(bubble.id)
            }
            Color.clear.frame(height: 1).id("bottom")
          }
          .padding(.horizontal, 14)
          .padding(.vertical, 10)
        }
        .onAppear { proxy.scrollTo("bottom", anchor: .bottom) }
        .onChange(of: chat.id) { _, _ in
          proxy.scrollTo("bottom", anchor: .bottom)
        }
        .onChange(of: chat.bubbles.count) { _, _ in
          withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
        }
      }

      if let reason = store.needsInputReasons[chat.id] {
        InboxNeedsInputBanner(reason: reason)
      }
      if let hold = store.pendingHolds[chat.id] {
        InboxHoldBanner(
          hold: hold, accent: accent,
          onConfirm: { store.resolveHold(chatID: chat.id, discard: false) },
          onDiscard: { store.resolveHold(chatID: chat.id, discard: true) }
        )
      }
      InboxComposeBar(
        text: $draft, placeholder: "Message", accent: accent, canSend: canSend,
        onSend: { Task { await send() } }, isDrafting: isDrafting,
        errorText: errorText, infoText: infoText
      )
    }
    .background(OmiColors.backgroundPrimary)
    // Reset the composer for the newly-opened chat, then draft. Keyed on chat.id so
    // switching chats re-runs without recreating the whole detail view (snappier).
    .task(id: chat.id) {
      draft = ""
      errorText = nil
      infoText = nil
      await generateDraft()
    }
  }

  /// Per-chat auto-reply switch. When on, Omi sends a drafted reply automatically
  /// (no review) for new inbound messages in this chat. Shown only for 1:1 chats
  /// where an automated send is possible.
  private var autoReplyToggle: some View {
    Toggle(
      isOn: Binding(
        get: { store.isAutoReplyEnabled(chat.chatID) },
        set: { store.setAutoReply($0, for: chat.chatID) }
      )
    ) {
      Text("Auto-reply")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
    }
    .toggleStyle(.switch)
    .controlSize(.mini)
    .tint(accent)
    .fixedSize()
    .help("When on, Omi automatically drafts and sends a reply to new messages in this chat.")
  }

  private var canSend: Bool {
    !isSending && !isDrafting && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  /// In group chats, show the sender name only at the start of each run of
  /// consecutive messages from the same person.
  private func shouldShowSender(at idx: Int) -> Bool {
    guard chat.isGroup else { return false }
    let bubble = chat.bubbles[idx]
    guard !bubble.isFromMe, bubble.senderName != nil else { return false }
    if idx == 0 { return true }
    let prev = chat.bubbles[idx - 1]
    return prev.isFromMe || prev.senderName != bubble.senderName
  }

  private func generateDraft() async {
    if !draft.isEmpty { return }
    // Don't auto-draft if you already replied (you sent the last message).
    if let last = chat.bubbles.last, last.isFromMe { return }
    // Use a reply the background watcher already pre-drafted, if any (instant).
    if let ready = store.preDrafts[chat.id], !ready.isEmpty {
      draft = ready
      return
    }
    isDrafting = true
    errorText = nil
    infoText = nil
    defer { isDrafting = false }
    do {
      let resp = try await APIClient.shared.whatsappDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
      if resp.abstain {
        // Group message that wasn't directed at the user — don't invent a reply.
        draft = ""
        errorText = "This didn't look like it was meant for you — no reply drafted."
      } else if resp.ambiguous {
        // The contact name matched more than one person — surface the ask and keep
        // the composer empty so it can't be sent as-is.
        draft = ""
        errorText = resp.draft
      } else {
        draft = resp.draft
      }
    } catch is CancellationError {
      return
    } catch let urlError as URLError where urlError.code == .cancelled {
      return
    } catch {
      errorText = "Couldn't draft a reply: \(error.localizedDescription)"
    }
  }

  private func send() async {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    isSending = true
    errorText = nil
    infoText = nil
    defer { isSending = false }
    do {
      try await WhatsAppSenderService.send(text: text, toChatID: chat.chatID, phone: chat.dialablePhone)
      // Only reflect a sent message once WhatsApp's own database confirms it landed in
      // THIS chat. Pin the append to `chat.id`: send is awaited, so the user may have
      // switched chats during it, and the no-arg appendSent writes to whatever is
      // selected now.
      store.appendSent(text, to: chat.id)
      draft = ""
    } catch let error as WhatsAppSenderError {
      switch error {
      case .invalidTarget, .permissionRequired, .sendUnconfirmed:
        // Not a hard failure — the reply is prefilled or unconfirmed; guide the user (open
        // the chat, grant the one-time permission, or check WhatsApp before resending) and
        // keep the draft so a possibly-unsent reply isn't lost. (Both the manual and
        // auto-reply paths keep the draft on .sendUnconfirmed.)
        infoText = error.errorDescription
      case .notConfirmed, .sendFailed:
        // Nothing was sent — keep the draft so the user can try again.
        errorText = error.errorDescription
      }
    } catch {
      errorText = error.localizedDescription
    }
  }
}
