import SwiftUI

/// Telegram "reply on my behalf" inbox: connect via the on-device MTProto helper,
/// browse recent chats, review pre-drafts, send, and opt individual chats into
/// automatic replies. Telegram has no local DB, so all data flows through
/// TelegramInboxStore -> TelegramClientService (MTProto).
///
/// Shared row/header/bubble/compose UI lives in `MessagingInboxKit` so this tab,
/// iMessage, and WhatsApp look and behave identically.
struct TelegramInboxPage: View {
  static let telegramBlue = Color(red: 0.15, green: 0.63, blue: 0.92)
  @ObservedObject private var store = TelegramInboxStore.shared
  @State private var composeText: String = ""
  @State private var passcode: String = ""
  @State private var phone: String = ""
  @State private var code: String = ""
  @State private var password: String = ""

  var body: some View {
    Group {
      switch store.connection {
      case .connected:
        inbox
      default:
        connectPane
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
    .onAppear { store.start() }
  }

  // MARK: - Connect

  private var connectPane: some View {
    VStack(spacing: 16) {
      Image(systemName: "paperplane.circle.fill")
        .font(.system(size: 48))
        .foregroundStyle(.secondary)
      Text("Telegram Replies")
        .font(.title2).bold()

      switch store.connection {
      case .codeSent:
        Text("Enter the login code Telegram just sent to your app.")
          .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 380)
        TextField("Login code", text: $code)
          .textFieldStyle(.roundedBorder).frame(maxWidth: 200)
          .onSubmit { store.submitCode(code) }
        Button("Verify") { store.submitCode(code) }
          .buttonStyle(.borderedProminent)
          .disabled(code.trimmingCharacters(in: .whitespaces).isEmpty)
      case .passwordRequired:
        Text("Your account has two-factor auth. Enter your Telegram password (used once, to sign in).")
          .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 380)
        SecureField("2FA password", text: $password)
          .textFieldStyle(.roundedBorder).frame(maxWidth: 260)
          .onSubmit { store.submitPassword(password) }
        Button("Sign in") { store.submitPassword(password) }
          .buttonStyle(.borderedProminent)
          .disabled(password.isEmpty)
      case .needsPasscode:
        Text("Enter your Telegram Desktop Local Passcode to unlock your session. It stays on this Mac.")
          .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 380)
        SecureField("Local Passcode", text: $passcode)
          .textFieldStyle(.roundedBorder).frame(maxWidth: 260)
        Button("Unlock") { store.connectViaDesktop(passcode: passcode) }
          .buttonStyle(.borderedProminent)
      case .connecting:
        ProgressView("Connecting…")
      case .error(let msg):
        Text(msg).foregroundStyle(.red).frame(maxWidth: 380).multilineTextAlignment(.center)
        Button("Try Again") { store.sendCode(phone: phone) }
          .buttonStyle(.bordered)
          .disabled(phone.trimmingCharacters(in: .whitespaces).isEmpty)
      default:  // .disconnected
        Text("Sign in to reply on your behalf. Your session stays on this Mac.")
          .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 380)
        TextField("Phone (e.g. +14155551234)", text: $phone)
          .textFieldStyle(.roundedBorder).frame(maxWidth: 260)
          .onSubmit { store.sendCode(phone: phone) }
        Button("Send code") { store.sendCode(phone: phone) }
          .buttonStyle(.borderedProminent)
          .disabled(phone.trimmingCharacters(in: .whitespaces).isEmpty)
        if store.telegramDesktopAvailable {
          Button("Use Telegram Desktop session instead") { store.connectViaDesktop() }
            .buttonStyle(.link).font(.caption)
        }
      }
    }
    .padding(40)
  }

  // MARK: - Inbox

  private var inbox: some View {
    HStack(spacing: 0) {
      conversationList
        .frame(width: 300)
      Divider()
      if let chat = store.selectedChat {
        chatDetail(chat)
      } else {
        emptyDetail
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
  }

  private var conversationList: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: 10) {
        Text("Telegram")
          .scaledFont(size: 20, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        if store.connection == .connecting {
          ProgressView()
            .controlSize(.small)
            .help("Refreshing Telegram…")
        } else {
          Button(action: { store.refresh() }) {
            Image(systemName: "arrow.clockwise")
              .font(.system(size: 14, weight: .semibold))
              .foregroundColor(OmiColors.textSecondary)
          }
          .buttonStyle(.plain)
          .help("Refresh Telegram")
        }
      }
      .padding(.horizontal, 16)
      .padding(.vertical, 14)

      if store.chats.isEmpty {
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
                avatarData: chat.avatarImageData, isSelected: chat.chatID == store.selectedChatID,
                draftReady: store.preDrafts[chat.chatID] != nil,
                needsInput: store.needsInputReasons[chat.chatID] != nil,
                accent: Self.telegramBlue
              )
              .onTapGesture { store.selectedChatID = chat.chatID }
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

  private func chatDetail(_ chat: TelegramChat) -> some View {
    let accent = Self.telegramBlue
    let canSend = !composeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    return VStack(spacing: 0) {
      InboxChatHeader(name: chat.displayName, avatarData: chat.avatarImageData) {
        autoReplyToggle(for: chat, accent: accent)
      }
      Divider()

      ScrollViewReader { proxy in
        ScrollView {
          LazyVStack(spacing: 2) {
            ForEach(chat.bubbles) { bubble in
              InboxBubble(
                text: bubble.text, isFromMe: bubble.isFromMe, accent: accent,
                senderName: bubble.senderName,
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
        .onChange(of: chat.chatID) { _, _ in
          proxy.scrollTo("bottom", anchor: .bottom)
        }
        .onChange(of: chat.bubbles.count) { _, _ in
          withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
        }
      }

      if let reason = store.needsInputReasons[chat.chatID] {
        InboxNeedsInputBanner(reason: reason)
      }
      if let hold = store.pendingHolds[chat.chatID] {
        InboxHoldBanner(
          hold: hold, accent: accent,
          onConfirm: { store.resolveHold(chatID: chat.chatID, discard: false) },
          onDiscard: { store.resolveHold(chatID: chat.chatID, discard: true) }
        )
      }
      InboxComposeBar(
        text: $composeText, placeholder: "Message", accent: accent, canSend: canSend,
        onSend: sendComposed
      )
      .onChange(of: store.selectedChatID) { _, _ in composeText = "" }
      .onChange(of: store.preDrafts[chat.chatID]) { _, newValue in
        // Surface a fresh pre-draft in the compose bar for review + edit.
        if composeText.isEmpty, let draft = newValue { composeText = draft }
      }
      .onAppear {
        if composeText.isEmpty, let draft = store.preDrafts[chat.chatID] { composeText = draft }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
  }

  private func autoReplyToggle(for chat: TelegramChat, accent: Color) -> some View {
    Toggle(
      isOn: Binding(
        get: { store.isAutoReplyEnabled(chat.chatID) },
        set: { store.setAutoReply($0, for: chat.chatID) })
    ) {
      Text("Auto-reply")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
    }
    .toggleStyle(.switch)
    .controlSize(.mini)
    .tint(accent)
    .fixedSize()
    .help("When on, Omi drafts and sends replies in this chat automatically, without review.")
  }

  private func sendComposed() {
    store.sendManual(composeText)
    composeText = ""
  }
}
