import Foundation
import TDLibKit

// MARK: - Auth state

/// The public-facing authorization state the login UI drives against. Mirrors the
/// subset of TDLib's `AuthorizationState` machine we actually respond to, collapsing
/// the rest into `.connecting` / `.error`.
enum TelegramAuthState: Equatable, Sendable {
  /// No client yet, or a client that is still negotiating parameters / connecting.
  case connecting
  /// TDLib wants the phone number (international format, e.g. +14155550123).
  case waitPhone
  /// A login code was sent (SMS / Telegram app) and TDLib wants it back.
  case waitCode
  /// The account has 2-step verification; TDLib wants the cloud password.
  case waitPassword
  /// Fully authorized — safe to send and receive messages.
  case ready
  /// The client was closed (logout or teardown).
  case closed
  /// A terminal-ish error surfaced by TDLib (login failure, unhandled state, …).
  case error(String)
}

enum TelegramSendError: LocalizedError {
  case missingCredentials
  case notReady
  case clientUnavailable

  var errorDescription: String? {
    switch self {
    case .missingCredentials:
      return "Telegram API credentials are missing from the Keychain."
    case .notReady:
      return "Telegram is not logged in yet."
    case .clientUnavailable:
      return "The Telegram client is not available."
    }
  }
}

// MARK: - Observable model for SwiftUI

/// Bridges the actor's auth state onto the main actor so SwiftUI can observe it.
/// The actor owns the truth; this is a thin, published mirror.
@MainActor
final class TelegramLoginModel: ObservableObject {
  static let shared = TelegramLoginModel()
  @Published private(set) var state: TelegramAuthState = .connecting
  /// Set while a request the user just submitted is in flight (disables the button).
  @Published var isSubmitting = false

  fileprivate func apply(_ newState: TelegramAuthState) {
    state = newState
    if case .waitPhone = newState { isSubmitting = false }
    if case .waitCode = newState { isSubmitting = false }
    if case .waitPassword = newState { isSubmitting = false }
    if case .error = newState { isSubmitting = false }
    if case .ready = newState { isSubmitting = false }
  }
}

// MARK: - Service

/// Native Telegram client wrapping TDLibKit's prebuilt TDLib (1.8.65). Owns the
/// client lifecycle, the authorization state machine, message sending, and the
/// realtime update subscription.
///
/// Ported from a validated Rust `td_json` POC. Notable version-driven differences
/// from that POC's older TDLib:
///   * There is NO `authorizationStateWaitEncryptionKey` state and no
///     `checkDatabaseEncryptionKey` in TDLib 1.8.65 — the database encryption key
///     is passed inline via `setTdlibParameters(databaseEncryptionKey:)`.
///   * `setTdlibParameters` fields are flat (TDLibKit's typed API already reflects this).
///
/// Security: TDLib's internal logger writes `api_hash` and the phone number in
/// plaintext at its default verbosity. We drop verbosity to 0 (fatal-only) before
/// any secret-bearing request is ever sent — see `silenceLoggingOnce`.
actor TelegramSendService {
  static let shared = TelegramSendService()

  private var manager: TDLibClientManager?
  private var client: TDLibClient?
  private var didSilenceLogging = false
  private var currentState: TelegramAuthState = .connecting

  /// Live message subscription installed by `startListening`. TDLib delivers *all*
  /// updates through the single client update handler, so we fan out here.
  private var onNewMessage: (@Sendable (Int64, Bool, String, Foundation.Date) -> Void)?

  // MARK: Session persistence
  //
  // TDLib persists its own encrypted session (auth keys, DC, message cache) under
  // `database_directory`. Pointing this at a stable Application Support path means a
  // relaunch resumes straight to `authorizationStateReady` with no phone/code re-entry.

  private static var sessionRoot: URL {
    let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support", isDirectory: true)
    return base.appendingPathComponent("Omi/tdlib", isDirectory: true)
  }
  private static var databaseDirectory: URL { sessionRoot.appendingPathComponent("db", isDirectory: true) }
  private static var filesDirectory: URL { sessionRoot.appendingPathComponent("files", isDirectory: true) }

  // MARK: Lifecycle

  /// Create the client (if needed) and begin (or resume) the authorization flow.
  /// Safe to call repeatedly — a no-op once a client exists.
  func start() {
    guard client == nil else { return }

    // Ensure the persistent session directories exist up front.
    try? FileManager.default.createDirectory(
      at: Self.databaseDirectory, withIntermediateDirectories: true)
    try? FileManager.default.createDirectory(
      at: Self.filesDirectory, withIntermediateDirectories: true)

    let manager = TDLibClientManager()
    // The update handler runs on TDLib's serial per-client queue. It must NOT block,
    // so it silences logging once (synchronously, before we ever answer
    // WaitTdlibParameters), decodes the update, then hops onto the actor to react.
    let client = manager.createClient { [weak self] data, client in
      guard let self else { return }
      self.silenceLoggingOnce(client)
      guard let update = try? client.decoder.decode(Update.self, from: data) else { return }
      Task { await self.handle(update) }
    }
    self.manager = manager
    self.client = client
    // Belt-and-suspenders: also lower verbosity synchronously here. `createClient`
    // only sends a secret-free getOption("version") before this, so nothing sensitive
    // can have been logged yet.
    silence(client)
  }

  /// Tear the client down (used on logout). TDLib flushes the session on `close`.
  func logout() async {
    guard let client else { return }
    onNewMessage = nil
    try? await client.logOut()
    self.client = nil
    self.manager?.closeClients()
    self.manager = nil
    didSilenceLogging = false
    await setState(.closed)
  }

  // MARK: Auth flow — inputs from the login UI

  func submitPhone(_ phone: String) async {
    guard let client else { await setState(.error("no client")); return }
    do {
      _ = try await client.setAuthenticationPhoneNumber(
        phoneNumber: phone.trimmingCharacters(in: .whitespaces), settings: nil)
    } catch {
      await setState(.error(Self.describe(error)))
    }
  }

  func submitCode(_ code: String) async {
    guard let client else { await setState(.error("no client")); return }
    do {
      _ = try await client.checkAuthenticationCode(code: code.trimmingCharacters(in: .whitespaces))
    } catch {
      await setState(.error(Self.describe(error)))
    }
  }

  func submitPassword(_ password: String) async {
    guard let client else { await setState(.error("no client")); return }
    do {
      _ = try await client.checkAuthenticationPassword(password: password)
    } catch {
      await setState(.error(Self.describe(error)))
    }
  }

  func state() -> TelegramAuthState { currentState }

  /// The logged-in user. A real authenticated round-trip to Telegram's servers —
  /// useful to prove a resumed session is actually usable (not just "ready" locally).
  func me() async throws -> User {
    guard let client else { throw TelegramSendError.clientUnavailable }
    return try await client.getMe()
  }

  // MARK: Sending

  /// Send a plain-text message to a chat. `chatId` is TDLib's chat id (for a 1:1 chat
  /// this equals the peer's user id and is positive).
  func sendMessage(chatId: Int64, text: String) async throws {
    guard case .ready = currentState else { throw TelegramSendError.notReady }
    guard let client else { throw TelegramSendError.clientUnavailable }
    // Ensure TDLib has the chat loaded. On a cold session resume the chat list isn't
    // in memory yet, so sendMessage against a raw chat id fails until it's known. For
    // a 1:1 chat the id equals the peer's user id, so createPrivateChat loads and
    // registers it; otherwise getChat pulls it into the chat list.
    if chatId > 0 {
      _ = try? await client.createPrivateChat(force: false, userId: chatId)
    } else {
      _ = try? await client.getChat(chatId: chatId)
    }
    let content = InputMessageContent.inputMessageText(
      InputMessageText(
        clearDraft: true,
        linkPreviewOptions: nil,
        text: FormattedText(entities: [], text: text)))
    _ = try await client.sendMessage(
      chatId: chatId,
      inputMessageContent: content,
      options: nil,
      replyMarkup: nil,
      replyTo: nil,
      topicId: nil)
  }

  // MARK: Listening

  /// Subscribe to incoming/outgoing messages on 1:1 (private) chats. Mirrors the
  /// shape of `IMessageSendService.startListening` for consistency across platforms.
  /// The callback fires for both directions; `fromMe` distinguishes them.
  func startListening(
    onNewMessage: @escaping @Sendable (
      _ chatId: Int64, _ fromMe: Bool, _ text: String, _ date: Foundation.Date)
      -> Void
  ) {
    self.onNewMessage = onNewMessage
  }

  func stopListening() {
    onNewMessage = nil
  }

  // MARK: - Update handling

  private func handle(_ update: Update) async {
    switch update {
    case .updateAuthorizationState(let wrapper):
      await handleAuthState(wrapper.authorizationState)
    case .updateNewMessage(let wrapper):
      deliver(wrapper.message)
    default:
      break
    }
  }

  private func handleAuthState(_ state: AuthorizationState) async {
    switch state {
    case .authorizationStateWaitTdlibParameters:
      await sendTdlibParameters()
    case .authorizationStateWaitPhoneNumber:
      await setState(.waitPhone)
    case .authorizationStateWaitCode:
      await setState(.waitCode)
    case .authorizationStateWaitPassword:
      await setState(.waitPassword)
    case .authorizationStateReady:
      await setState(.ready)
    case .authorizationStateLoggingOut, .authorizationStateClosing:
      await setState(.connecting)
    case .authorizationStateClosed:
      await setState(.closed)
    default:
      // States we don't drive (email, premium purchase, other-device confirmation,
      // registration). Surface them so the UI isn't stuck silently.
      await setState(.error("Unsupported Telegram auth step: \(String(describing: state))"))
    }
  }

  private func sendTdlibParameters() async {
    guard let client else { return }
    guard let creds = Self.readCredentials() else {
      await setState(.error(TelegramSendError.missingCredentials.localizedDescription))
      return
    }
    do {
      _ = try await client.setTdlibParameters(
        apiHash: creds.apiHash,
        apiId: creds.apiId,
        applicationVersion: "omi-desktop",
        databaseDirectory: Self.databaseDirectory.path,
        databaseEncryptionKey: Data(),  // empty key — matches the POC
        deviceModel: "Desktop",
        filesDirectory: Self.filesDirectory.path,
        systemLanguageCode: "en",
        systemVersion: "macOS",
        useChatInfoDatabase: true,
        useFileDatabase: true,
        useMessageDatabase: true,
        useSecretChats: false,
        useTestDc: false)
    } catch {
      await setState(.error(Self.describe(error)))
    }
  }

  /// Fan a new message out to the registered listener, restricted to 1:1 chats.
  /// In TDLib, private (1:1) chats have a positive `chatId` (it equals the peer's
  /// user id); groups/supergroups/channels are negative. Text-only for now.
  private func deliver(_ message: Message) {
    guard let onNewMessage else { return }
    guard message.chatId > 0 else { return }
    guard case .messageText(let messageText) = message.content else { return }
    let text = messageText.text.text
    guard !text.isEmpty else { return }
    let date = Foundation.Date(timeIntervalSince1970: TimeInterval(message.date))
    onNewMessage(message.chatId, message.isOutgoing, text, date)
  }

  // MARK: - State plumbing

  private func setState(_ newState: TelegramAuthState) async {
    currentState = newState
    await MainActor.run { TelegramLoginModel.shared.apply(newState) }
  }

  // MARK: - Logging safety

  /// TDLib's internal logger dumps request/response JSON — including `api_hash` and
  /// the phone number — at its default verbosity. Lower to 0 (fatal-only) before any
  /// secret-bearing request is sent. Runs at most once, synchronously.
  private nonisolated func silenceLoggingOnce(_ client: TDLibClient) {
    // `didSilenceLogging` is actor-isolated; the handler runs off-actor, so we can't
    // read it here without hopping. Executing setLogVerbosityLevel is idempotent and
    // cheap, so just do it unconditionally on the synchronous path — the actor's
    // `silence(client)` in `start()` already covers the guaranteed-first case.
    silence(client)
  }

  private nonisolated func silence(_ client: TDLibClient) {
    _ = try? client.execute(query: DTO(SetLogVerbosityLevel(newVerbosityLevel: 0)))
  }

  // MARK: - Credentials

  private struct Credentials { let apiId: Int; let apiHash: String }

  /// Read `api_id` / `api_hash` from the macOS Keychain (generic-password items,
  /// scoped to the current user). Never hardcoded, never logged.
  private static func readCredentials() -> Credentials? {
    guard let idString = keychainValue(service: "me.omi.telegram.tdlib.api_id"),
      let apiId = Int(idString),
      let apiHash = keychainValue(service: "me.omi.telegram.tdlib.api_hash"),
      !apiHash.isEmpty
    else { return nil }
    return Credentials(apiId: apiId, apiHash: apiHash)
  }

  private static func keychainValue(service: String) -> String? {
    let user = NSUserName()
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
    process.arguments = ["find-generic-password", "-a", user, "-s", service, "-w"]
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = Pipe()
    do {
      try process.run()
      process.waitUntilExit()
      guard process.terminationStatus == 0 else { return nil }
      let value = String(
        data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      return (value?.isEmpty == false) ? value : nil
    } catch {
      return nil
    }
  }

  /// Redact a TDLib error to a short, secret-free string for state/UI. TDLib errors
  /// carry only a code + message (no credentials), but keep it terse regardless.
  private static func describe(_ error: Swift.Error) -> String {
    if let tdError = error as? TDLibKit.Error {
      return "\(tdError.message) (\(tdError.code))"
    }
    return error.localizedDescription
  }
}
