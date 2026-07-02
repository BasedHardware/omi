import SwiftUI

/// Telegram "reply on my behalf" inbox: connect via the on-device MTProto helper,
/// browse recent chats, review pre-drafts, send, and opt individual chats into
/// automatic replies. Mirrors the iMessage Replies tab; Telegram has no local DB,
/// so all data flows through TelegramInboxStore -> TelegramClientService (MTProto).
struct TelegramInboxPage: View {
  @StateObject private var store = TelegramInboxStore()
  @State private var composeText: String = ""
  @State private var passcode: String = ""

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
      case .needsTelegramDesktop:
        Text("Install and sign in to Telegram Desktop first — Omi reads your session locally to reply on your behalf.")
          .multilineTextAlignment(.center)
          .foregroundStyle(.secondary)
          .frame(maxWidth: 380)
      case .needsPasscode:
        Text("Enter your Telegram Desktop Local Passcode to unlock your session. It stays on this Mac.")
          .multilineTextAlignment(.center)
          .foregroundStyle(.secondary)
          .frame(maxWidth: 380)
        SecureField("Local Passcode", text: $passcode)
          .textFieldStyle(.roundedBorder)
          .frame(maxWidth: 260)
        Button("Unlock") { store.connect(passcode: passcode) }
          .buttonStyle(.borderedProminent)
      case .connecting:
        ProgressView("Connecting…")
      case .error(let msg):
        Text(msg).foregroundStyle(.red).frame(maxWidth: 380).multilineTextAlignment(.center)
        Button("Try Again") { store.connect() }.buttonStyle(.borderedProminent)
      default:
        Text("Omi will use your existing Telegram Desktop session — no login code needed. Your session never leaves this Mac.")
          .multilineTextAlignment(.center)
          .foregroundStyle(.secondary)
          .frame(maxWidth: 380)
        Button("Connect Telegram") { store.connect() }
          .buttonStyle(.borderedProminent)
      }
    }
    .padding(40)
  }

  // MARK: - Inbox

  private var inbox: some View {
    HSplitView {
      chatList
        .frame(minWidth: 240, idealWidth: 300, maxWidth: 360)
      if let chat = store.selectedChat {
        chatDetail(chat)
      } else {
        VStack { Text("Select a chat").foregroundStyle(.secondary) }
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
  }

  private var chatList: some View {
    List(selection: $store.selectedChatID) {
      ForEach(store.chats) { chat in
        HStack {
          VStack(alignment: .leading, spacing: 2) {
            Text(chat.displayName).font(.body).lineLimit(1)
            Text(chat.lastPreview).font(.caption).foregroundStyle(.secondary).lineLimit(1)
          }
          Spacer()
          if store.preDrafts[chat.chatID] != nil {
            Text("Draft").font(.caption2).padding(.horizontal, 6).padding(.vertical, 2)
              .background(.quaternary, in: Capsule())
          }
          if store.isAutoReplyEnabled(chat.chatID) {
            Image(systemName: "bolt.fill").font(.caption2).foregroundStyle(.secondary)
          }
        }
        .tag(chat.chatID)
      }
    }
  }

  private func chatDetail(_ chat: TelegramChat) -> some View {
    VStack(spacing: 0) {
      HStack {
        Text(chat.displayName).font(.headline)
        Spacer()
        Toggle(
          "Auto-reply",
          isOn: Binding(
            get: { store.isAutoReplyEnabled(chat.chatID) },
            set: { store.setAutoReply($0, for: chat.chatID) })
        )
        .toggleStyle(.switch)
        .help("When on, Omi drafts and sends replies in this chat automatically, without review.")
      }
      .padding(10)
      Divider()

      ScrollView {
        VStack(alignment: .leading, spacing: 6) {
          ForEach(chat.bubbles) { bubble in
            HStack {
              if bubble.isFromMe { Spacer() }
              Text(bubble.text)
                .padding(8)
                .background(bubble.isFromMe ? Color.accentColor.opacity(0.2) : Color.gray.opacity(0.15),
                  in: RoundedRectangle(cornerRadius: 10))
              if !bubble.isFromMe { Spacer() }
            }
          }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      Divider()
      composeBar(for: chat)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func composeBar(for chat: TelegramChat) -> some View {
    HStack(spacing: 8) {
      Button {
        Task { await store.generateDraft() }
      } label: {
        Image(systemName: "sparkles")
      }
      .help("Draft a reply in your voice")

      TextField("Message", text: $composeText, axis: .vertical)
        .textFieldStyle(.roundedBorder)
        .lineLimit(1...4)
        .onSubmit(sendComposed)

      Button("Send", action: sendComposed)
        .buttonStyle(.borderedProminent)
        .disabled(composeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }
    .padding(10)
    .onChange(of: store.selectedChatID) { composeText = "" }
    .onChange(of: store.preDrafts[chat.chatID]) { _, newValue in
      // Surface a fresh pre-draft in the compose bar for review + edit.
      if composeText.isEmpty, let draft = newValue { composeText = draft }
    }
    .onAppear {
      if composeText.isEmpty, let draft = store.preDrafts[chat.chatID] { composeText = draft }
    }
  }

  private func sendComposed() {
    store.sendManual(composeText)
    composeText = ""
  }
}
