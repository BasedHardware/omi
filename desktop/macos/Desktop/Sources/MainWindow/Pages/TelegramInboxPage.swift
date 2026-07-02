import SwiftUI

/// Telegram "reply on my behalf" inbox: connect via the on-device MTProto helper,
/// browse recent chats, review pre-drafts, send, and opt individual chats into
/// automatic replies. Mirrors the iMessage Replies tab; Telegram has no local DB,
/// so all data flows through TelegramInboxStore -> TelegramClientService (MTProto).
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
        HStack(spacing: 10) {
          TelegramAvatar(name: chat.displayName, size: 34, imageData: chat.avatarImageData)
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
        TelegramAvatar(name: chat.displayName, size: 28, imageData: chat.avatarImageData)
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
              TelegramBubbleView(bubble: bubble)
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
    let accent = Self.telegramBlue
    let canSend = !composeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    return HStack(alignment: .bottom, spacing: 10) {
      Button {
        Task { await store.generateDraft() }
      } label: {
        Image(systemName: "sparkles")
          .font(.system(size: 15))
          .foregroundStyle(accent)
          .frame(width: 32, height: 32)
          .background(Circle().fill(accent.opacity(0.12)))
      }
      .buttonStyle(.plain)
      .help("Draft a reply in your voice")

      TextField("Message", text: $composeText, axis: .vertical)
        .textFieldStyle(.plain)
        .lineLimit(1...4)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
          RoundedRectangle(cornerRadius: 20, style: .continuous).fill(.quaternary.opacity(0.5))
        )
        .overlay(
          RoundedRectangle(cornerRadius: 20, style: .continuous)
            .stroke(.secondary.opacity(0.15), lineWidth: 1)
        )
        .onSubmit(sendComposed)

      Button(action: sendComposed) {
        Image(systemName: "arrow.up.circle.fill")
          .font(.system(size: 28))
          .foregroundStyle(canSend ? accent : Color.secondary.opacity(0.5))
      }
      .buttonStyle(.plain)
      .disabled(!canSend)
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 10)
    .overlay(alignment: .top) { Divider().overlay(Color.secondary.opacity(0.15)) }
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

// MARK: - Avatar

private struct TelegramAvatar: View {
  let name: String
  let size: CGFloat
  var imageData: Data? = nil

  var body: some View {
    Group {
      if let data = imageData, let img = NSImage(data: data) {
        Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
      } else {
        ZStack {
          TelegramInboxPage.telegramBlue.opacity(0.2)
          Image(systemName: "person.fill")
            .font(.system(size: size * 0.5))
            .foregroundStyle(.secondary)
        }
      }
    }
    .frame(width: size, height: size)
    .clipShape(Circle())
  }
}

// MARK: - Bubble (text + inline photo)

private struct TelegramBubbleView: View {
  let bubble: TelegramChatBubble

  @State private var loadedImage: NSImage?

  var body: some View {
    VStack(alignment: bubble.isFromMe ? .trailing : .leading, spacing: 2) {
      if let path = bubble.imagePath {
        imageAttachment(path: path)
        if !bubble.text.isEmpty { textBubble }
      } else {
        textBubble
      }
    }
  }

  private var textBubble: some View {
    Text(bubble.text)
      .padding(8)
      .background(
        bubble.isFromMe ? Color.accentColor.opacity(0.2) : Color.gray.opacity(0.15),
        in: RoundedRectangle(cornerRadius: 10))
  }

  @ViewBuilder
  private func imageAttachment(path: String) -> some View {
    Group {
      if let img = loadedImage {
        Image(nsImage: img)
          .resizable()
          .aspectRatio(contentMode: .fit)
          .frame(maxWidth: 220, maxHeight: 260)
          .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
      } else {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(Color.gray.opacity(0.15))
          .frame(width: 160, height: 160)
          .overlay(Image(systemName: "photo").font(.system(size: 28)).foregroundStyle(.secondary))
      }
    }
    .task(id: path) {
      loadedImage = await TelegramAttachmentImageCache.shared.image(atPath: path)
    }
  }
}

/// Loads and caches Telegram attachment images off the SwiftUI render path.
private actor TelegramAttachmentImageCache {
  static let shared = TelegramAttachmentImageCache()

  private let cache: NSCache<NSString, NSImage> = {
    let cache = NSCache<NSString, NSImage>()
    cache.countLimit = 200
    cache.totalCostLimit = 100 * 1024 * 1024  // 100MB
    return cache
  }()

  func image(atPath path: String) -> NSImage? {
    let key = path as NSString
    if let cached = cache.object(forKey: key) { return cached }
    if Task.isCancelled { return nil }
    guard let image = NSImage(contentsOfFile: path) else { return nil }
    cache.setObject(image, forKey: key, cost: Self.decodedByteCost(of: image))
    return image
  }

  private static func decodedByteCost(of image: NSImage) -> Int {
    var pixels = 0
    for rep in image.representations {
      pixels = max(pixels, rep.pixelsWide * rep.pixelsHigh)
    }
    if pixels == 0 { pixels = Int(image.size.width * image.size.height) }
    return max(1, pixels * 4)
  }
}
