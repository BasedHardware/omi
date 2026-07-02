import SwiftUI

/// WhatsApp tab — a native WhatsApp-style view of your chats. Shows the full
/// conversation, with an Omi-drafted reply pre-filled in the compose bar that you
/// review, edit, and send. Per 1:1 chat, an opt-in "Auto-reply" switch lets Omi
/// draft and send replies to new inbound messages automatically (off by default).
struct WhatsAppInboxPage: View {
  @StateObject private var store = WhatsAppInboxStore()

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
              .id(chat.id)
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
    .onDisappear { store.stopWatching() }
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
            ForEach(store.chats) { chat in
              ConversationRow(
                chat: chat, isSelected: chat.id == store.selectedChatID,
                accent: Self.whatsappGreen,
                draftReady: store.preDrafts[chat.id] != nil
              )
              .contentShape(Rectangle())
              .onTapGesture { store.selectedChatID = chat.id }
            }
          }
        }
      }
    }
    .background(OmiColors.backgroundPrimary)
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

// MARK: - Conversation row

private struct ConversationRow: View {
  let chat: WhatsAppChat
  let isSelected: Bool
  let accent: Color
  var draftReady: Bool = false

  var body: some View {
    HStack(spacing: 10) {
      Avatar(name: chat.displayName, size: 40, imageData: chat.avatarImageData)
      VStack(alignment: .leading, spacing: 2) {
        HStack {
          Text(chat.displayName)
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)
          Spacer()
          Text(shortTime(chat.lastDate))
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }
        HStack(spacing: 6) {
          Text(chat.lastPreview)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textSecondary)
            .lineLimit(2)
          if chat.awaitingReply {
            Text(draftReady ? "Draft ready" : "Draft")
              .scaledFont(size: 9, weight: .semibold)
              .foregroundColor(draftReady ? .white : accent)
              .padding(.horizontal, 5)
              .padding(.vertical, 1)
              .background(draftReady ? accent : accent.opacity(0.15))
              .clipShape(Capsule())
          }
        }
      }
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 10)
    .background(isSelected ? OmiColors.backgroundSecondary : Color.clear)
  }

  private func shortTime(_ date: Date) -> String {
    let cal = Calendar.current
    let f = DateFormatter()
    if cal.isDateInToday(date) {
      f.dateFormat = "h:mm a"
    } else if cal.isDateInYesterday(date) {
      return "Yesterday"
    } else {
      f.dateFormat = "MMM d"
    }
    return f.string(from: date)
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
      // Header — contact centered, per-chat auto-reply toggle trailing (1:1 only).
      ZStack {
        VStack(spacing: 2) {
          Avatar(name: chat.displayName, size: 30, imageData: chat.avatarImageData)
          Text(chat.displayName)
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
        }
        .frame(maxWidth: .infinity)
        if store.canAutoReply(chat.chatID) {
          HStack {
            Spacer()
            autoReplyToggle
          }
        }
      }
      .padding(.vertical, 8)
      .background(OmiColors.backgroundPrimary.opacity(0.98))
      Divider()

      // Bubbles
      ScrollViewReader { proxy in
        ScrollView {
          LazyVStack(spacing: 2) {
            ForEach(Array(chat.bubbles.enumerated()), id: \.element.id) { idx, bubble in
              ChatBubbleView(
                bubble: bubble, isGroup: chat.isGroup,
                showSender: shouldShowSender(at: idx), accent: accent
              )
              .id(bubble.id)
            }
            Color.clear.frame(height: 1).id("bottom")
          }
          .padding(.horizontal, 14)
          .padding(.vertical, 10)
        }
        .onAppear { proxy.scrollTo("bottom", anchor: .bottom) }
        .onChange(of: chat.bubbles.count) { _, _ in
          withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
        }
      }

      composeBar
    }
    .background(OmiColors.backgroundPrimary)
    .task(id: chat.id) { await generateDraft() }
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
    .padding(.trailing, 12)
    .help("When on, Omi automatically drafts and sends a reply to new messages in this chat.")
  }

  private var composeBar: some View {
    VStack(spacing: 6) {
      if let errorText {
        Text(errorText).scaledFont(size: 11).foregroundColor(.orange)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      if let infoText {
        Text(infoText).scaledFont(size: 11).foregroundColor(accent)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      HStack(alignment: .bottom, spacing: 8) {
        Button { Task { await generateDraft(force: true) } } label: {
          Image(systemName: "sparkles")
            .foregroundColor(isDrafting ? OmiColors.textTertiary : accent)
        }
        .buttonStyle(.plain)
        .help("Draft a reply with Omi")
        .disabled(isDrafting)

        ZStack(alignment: .leading) {
          if draft.isEmpty && !isDrafting {
            Text("Message").scaledFont(size: 13).foregroundColor(OmiColors.textTertiary)
              .padding(.leading, 12)
          }
          if isDrafting {
            HStack(spacing: 6) {
              ProgressView().controlSize(.small)
              Text("Omi is drafting…").scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
            }.padding(.leading, 12)
          }
          TextEditor(text: $draft)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textPrimary)
            .scrollContentBackground(.hidden)
            .frame(minHeight: 20, maxHeight: 90)
            .padding(.horizontal, 8)
            .opacity(isDrafting ? 0 : 1)
        }
        .padding(.vertical, 6)
        .background(
          RoundedRectangle(cornerRadius: 18, style: .continuous)
            .stroke(OmiColors.textTertiary.opacity(0.4), lineWidth: 1)
        )

        Button { Task { await send() } } label: {
          Image(systemName: "arrow.up.circle.fill")
            .font(.system(size: 26))
            .foregroundColor(canSend ? accent : OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
      }
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 10)
    .background(OmiColors.backgroundPrimary)
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

  private func generateDraft(force: Bool = false) async {
    if !force && !draft.isEmpty { return }
    // Don't auto-draft if you already replied (you sent the last message).
    if !force, let last = chat.bubbles.last, last.isFromMe { return }
    // Use a reply the background watcher already pre-drafted, if any (instant).
    if !force, let ready = store.preDrafts[chat.id], !ready.isEmpty {
      draft = ready
      return
    }
    isDrafting = true
    errorText = nil
    infoText = nil
    defer { isDrafting = false }
    do {
      let resp = try await APIClient.shared.whatsappDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil)
      if resp.ambiguous {
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
      try WhatsAppSenderService.send(text: text, toChatID: chat.chatID)
      // Auto-send scheduled (1:1 + Accessibility). Optimistically reflect it.
      store.appendSent(text)
      draft = ""
    } catch let error as WhatsAppSenderError {
      switch error {
      case .manualSendRequired, .invalidTarget:
        // Not a failure — the reply is prefilled in WhatsApp (or the user must open
        // the chat). Keep the draft and guide them to finish the send.
        infoText = error.errorDescription
      case .sendFailed:
        errorText = error.errorDescription
      }
    } catch {
      errorText = error.localizedDescription
    }
  }
}

// MARK: - Bubble

private struct ChatBubbleView: View {
  let bubble: WhatsAppChatBubble
  let isGroup: Bool
  let showSender: Bool
  let accent: Color

  var body: some View {
    HStack {
      if bubble.isFromMe { Spacer(minLength: 60) }
      VStack(alignment: bubble.isFromMe ? .trailing : .leading, spacing: 2) {
        if showSender, let sender = bubble.senderName {
          Text(sender).scaledFont(size: 10).foregroundColor(OmiColors.textTertiary)
            .padding(.leading, 12)
        }
        messageBubble(bubble.text)
      }
      if !bubble.isFromMe { Spacer(minLength: 60) }
    }
  }

  @ViewBuilder
  private func messageBubble(_ text: String) -> some View {
    Text(text)
      .scaledFont(size: 13)
      .foregroundColor(bubble.isFromMe ? .white : OmiColors.textPrimary)
      .padding(.horizontal, 12)
      .padding(.vertical, 8)
      .background(bubble.isFromMe ? accent : Color(red: 0.17, green: 0.17, blue: 0.19))
      .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
  }
}

// MARK: - Avatar

private struct Avatar: View {
  let name: String
  let size: CGFloat
  var imageData: Data? = nil

  var body: some View {
    Group {
      if let data = imageData, let nsImage = NSImage(data: data) {
        Image(nsImage: nsImage)
          .resizable()
          .aspectRatio(contentMode: .fill)
      } else {
        Circle()
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            Text(initials)
              .scaledFont(size: size * 0.38, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)
          )
      }
    }
    .frame(width: size, height: size)
    .clipShape(Circle())
  }

  private var initials: String {
    let parts = name.split(separator: " ").prefix(2)
    let letters = parts.compactMap { $0.first }.map(String.init).joined()
    return letters.isEmpty ? "?" : letters.uppercased()
  }
}
