import Foundation
import OmiSupport
import SwiftUI

// MARK: - AI Clone service
//
// Owns the Beeper connection and the reply loop: live message events come in
// over the local WebSocket, the reply engine grounds a verdict in the user's
// persona + memories, and the per-chat trust ladder decides whether that
// verdict becomes a Beeper draft, an approval request, or an automatic send.
// Message content stays in Beeper — only bounded previews enter the activity
// log (never a second transcript store).

struct AIClonePendingApproval: Identifiable, Equatable {
  let id: UUID
  let chatID: String
  let chatTitle: String
  let network: String
  let inboundPreview: String
  var replyText: String
  let confidence: Double
  let receivedAt: Date
}

enum AICloneConnectionState: Equatable {
  case disconnected
  case connecting
  case connected(accounts: [BeeperAccount])
  case failed(message: String)

  var isConnected: Bool {
    if case .connected = self { return true }
    return false
  }
}

@MainActor
final class AICloneService: ObservableObject {
  static let shared = AICloneService()

  @Published private(set) var connectionState: AICloneConnectionState = .disconnected
  @Published private(set) var configuration: AICloneConfiguration
  @Published private(set) var chats: [BeeperChat] = []
  @Published private(set) var pendingApprovals: [AIClonePendingApproval] = []
  @Published private(set) var isListening = false
  @Published private(set) var benchmarkRunningChatIDs: Set<String> = []

  private let store: AICloneConfigurationStore
  private var replyEngine: AICloneReplyEngine
  private var clientFactory: (String) -> BeeperDesktopClient
  private var socketTask: URLSessionWebSocketTask?
  private var listenLoopTask: Task<Void, Never>?
  private var reconnectAttempts = 0
  private var listeningSince = Date()
  /// Chats currently being processed — coalesces bursts of message.upserted
  /// events so one inbound burst produces one reply decision.
  private var inFlightChatIDs: Set<String> = []
  /// Bounded auto-send budget (resets hourly) so a runaway loop can never
  /// spam a network into suspending the account.
  private var autoSendWindowStart = Date()
  private var autoSendsInWindow = 0
  static let autoSendsPerHourLimit = 20

  private var cachedPersona: Persona?
  private var cachedMemoryFacts: [String] = []
  private var memoryFactsFetchedAt: Date?

  static let tokenService = DesktopKeychainStore.scopedService("com.omi.desktop.beeper-access-token")
  static let tokenAccount = "beeper"

  init(
    store: AICloneConfigurationStore = AICloneConfigurationStore(
      directory: DesktopLocalProfile.applicationSupportURL().appendingPathComponent("AIClone", isDirectory: true)),
    replyEngine: AICloneReplyEngine = AICloneReplyEngine(),
    clientFactory: @escaping (String) -> BeeperDesktopClient = { BeeperDesktopClient(accessToken: $0) }
  ) {
    self.store = store
    self.replyEngine = replyEngine
    self.clientFactory = clientFactory
    self.configuration = store.load()
  }

  // MARK: Token

  var hasAccessToken: Bool {
    !(storedAccessToken() ?? "").isEmpty
  }

  func storedAccessToken() -> String? {
    DesktopKeychainStore.string(service: Self.tokenService, account: Self.tokenAccount)
  }

  func saveAccessToken(_ token: String) {
    let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    _ = DesktopKeychainStore.setString(trimmed, service: Self.tokenService, account: Self.tokenAccount)
  }

  func disconnectAndForgetToken() {
    stopListening()
    DesktopKeychainStore.delete(service: Self.tokenService, account: Self.tokenAccount)
    connectionState = .disconnected
    chats = []
  }

  private func client() throws -> BeeperDesktopClient {
    guard let token = storedAccessToken(), !token.isEmpty else {
      throw BeeperClientError.notConfigured
    }
    return clientFactory(token)
  }

  // MARK: Connect (functional probe, INV-INT-1)

  /// "Connected" is earned by a live probe every time — reach the API, pass
  /// auth, and enumerate accounts — never latched from a past success.
  func connect() async {
    connectionState = .connecting
    do {
      let client = try client()
      _ = try await client.probeInfo()
      let accounts = try await client.listAccounts()
      let chatPage = try await client.searchChats(limit: 80)
      connectionState = .connected(accounts: accounts)
      chats = chatPage.items.filter { $0.isReadOnly != true }
      if configuration.enabled {
        startListening()
      }
    } catch {
      connectionState = .failed(message: Self.userFacingConnectError(error))
      log("AIClone: connect failed: \(error)")
    }
  }

  static func userFacingConnectError(_ error: Error) -> String {
    switch error {
    case BeeperClientError.notConfigured:
      return "Paste your Beeper access token first."
    case BeeperClientError.httpError(let status, _) where status == 401 || status == 403:
      return "Beeper rejected the token. In Beeper Desktop open Settings, then Developer, and create a new access token."
    case let urlError as URLError where urlError.code == .cannotConnectToHost || urlError.code == .timedOut:
      return "Beeper Desktop isn't reachable. Open Beeper Desktop and enable the Desktop API, then retry."
    default:
      return "Couldn't connect to Beeper Desktop. Check that it is running with the Desktop API enabled."
    }
  }

  func setEnabled(_ enabled: Bool) {
    configuration.enabled = enabled
    store.save(configuration)
    if enabled, connectionState.isConnected {
      startListening()
    } else if !enabled {
      stopListening()
    }
  }

  func setMode(_ mode: AICloneChatMode, for chat: BeeperChat) {
    var next = mode
    if mode == .auto, !configuration.canEnableAuto(for: chat.id) {
      // Auto requires benchmark evidence; land on Ask instead of failing silently.
      next = .ask
    }
    configuration.chatModes[chat.id] = next
    store.save(configuration)
    objectWillChange.send()
  }

  // MARK: Live listening

  func startListening() {
    guard listenLoopTask == nil else { return }
    guard configuration.enabled, connectionState.isConnected else { return }
    isListening = true
    listeningSince = Date()
    listenLoopTask = Task { [weak self] in
      await self?.runListenLoop()
    }
  }

  func stopListening() {
    listenLoopTask?.cancel()
    listenLoopTask = nil
    socketTask?.cancel(with: .goingAway, reason: nil)
    socketTask = nil
    isListening = false
  }

  private func runListenLoop() async {
    while !Task.isCancelled, configuration.enabled {
      do {
        let client = try client()
        let task = try client.makeWebSocketTask()
        socketTask = task
        task.resume()
        let subscribe = try BeeperDesktopClient.subscriptionsSetPayload(
          chatIDs: ["*"], requestID: UUID().uuidString)
        try await task.send(.string(subscribe))
        reconnectAttempts = 0
        log("AIClone: live event stream connected")
        while !Task.isCancelled {
          let message = try await task.receive()
          guard case .string(let text) = message else { continue }
          if let event = BeeperDesktopClient.decodeLiveEvent(text) {
            await handleLiveEvent(event)
          }
        }
      } catch is CancellationError {
        break
      } catch {
        guard !Task.isCancelled, configuration.enabled else { break }
        reconnectAttempts += 1
        let delay = min(60.0, pow(2.0, Double(min(reconnectAttempts, 6))))
        log("AIClone: event stream dropped (\(error)); reconnecting in \(Int(delay))s")
        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
      }
    }
    isListening = false
  }

  func handleLiveEvent(_ event: BeeperLiveEvent) async {
    guard event.type == "message.upserted", let chatID = event.chatID else { return }
    let mode = configuration.mode(for: chatID)
    guard mode != .off else { return }
    guard let inbound = Self.latestActionableInbound(
      entries: event.entries ?? [],
      since: listeningSince)
    else { return }
    guard !inFlightChatIDs.contains(chatID) else { return }
    inFlightChatIDs.insert(chatID)
    defer { inFlightChatIDs.remove(chatID) }
    await processInbound(inbound, chatID: chatID, mode: mode)
  }

  /// The newest event entry worth replying to: text-like, sent by someone
  /// else, and not older than the listening session (history backfill and
  /// edits of old messages must never trigger the clone).
  nonisolated static func latestActionableInbound(entries: [BeeperMessage], since: Date) -> BeeperMessage? {
    let iso = ISO8601DateFormatter()
    let isoFractional = ISO8601DateFormatter()
    isoFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return entries.last { message in
      guard message.isSender != true, message.isDeleted != true, message.isTextLike,
        let text = message.text, !text.isEmpty
      else { return false }
      guard let stamp = message.timestamp else { return false }
      guard let date = isoFractional.date(from: stamp) ?? iso.date(from: stamp) else { return false }
      return date >= since.addingTimeInterval(-5)
    }
  }

  // MARK: Reply pipeline

  private func processInbound(_ inbound: BeeperMessage, chatID: String, mode: AICloneChatMode) async {
    let chat = chats.first { $0.id == chatID }
    let chatTitle = chat?.title ?? "Chat"
    let network = chat?.network ?? "Beeper"
    do {
      let client = try client()
      let thread = try await client.listMessages(chatID: chatID)
      let context = try await buildContext(
        inbound: inbound,
        chat: chat,
        chatTitle: chatTitle,
        network: network,
        thread: thread.items)
      let decision = try await replyEngine.decide(context: context)
      let outcome = decision.plannedOutcome(
        mode: mode,
        autoConfidenceThreshold: configuration.autoSendConfidenceThreshold)
      try await perform(
        outcome: outcome,
        decision: decision,
        inbound: inbound,
        chatID: chatID,
        chatTitle: chatTitle,
        network: network,
        client: client)
    } catch {
      log("AIClone: reply pipeline failed for chat: \(error)")
      recordActivity(
        chatID: chatID, chatTitle: chatTitle, network: network,
        inbound: inbound, replyText: nil, outcome: .failed, confidence: nil)
    }
  }

  private func buildContext(
    inbound: BeeperMessage,
    chat: BeeperChat?,
    chatTitle: String,
    network: String,
    thread: [BeeperMessage]
  ) async throws -> AICloneReplyContext {
    let persona = try await loadPersona()
    let facts = await loadMemoryFacts()
    let name = persona?.name ?? "the user"
    return AICloneReplyContext(
      personaName: name,
      personaPrompt: persona?.personaPrompt ?? "",
      memoryFacts: facts,
      chatTitle: chatTitle,
      network: network,
      isGroupChat: chat?.isSingle == false,
      threadLines: AICloneReplyEngine.threadLines(from: thread, selfName: name),
      inboundText: AICloneReplyEngine.strippedText(inbound.text ?? ""),
      inboundSenderName: inbound.senderName ?? "Them")
  }

  private func perform(
    outcome: AICloneActionOutcome,
    decision: AICloneReplyDecision,
    inbound: BeeperMessage,
    chatID: String,
    chatTitle: String,
    network: String,
    client: BeeperDesktopClient
  ) async throws {
    var effectiveOutcome = outcome
    if outcome == .sentAutomatically, !consumeAutoSendBudget() {
      // Provider/mode downgrade on a fail-open guard — visible to ops.
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "ai_clone",
        from: "auto_send",
        to: "draft",
        reason: "quota",
        outcome: .degraded)
      effectiveOutcome = .drafted
    }
    switch effectiveOutcome {
    case .drafted:
      if let reply = decision.reply {
        try await client.setDraft(chatID: chatID, text: reply)
      }
    case .askedApproval:
      if let reply = decision.reply {
        pendingApprovals.append(
          AIClonePendingApproval(
            id: UUID(),
            chatID: chatID,
            chatTitle: chatTitle,
            network: network,
            inboundPreview: Self.preview(inbound.text),
            replyText: reply,
            confidence: decision.confidence,
            receivedAt: Date()))
      }
    case .sentAutomatically:
      if let reply = decision.reply {
        _ = try await client.sendMessage(chatID: chatID, text: reply, replyToMessageID: inbound.id)
      }
    case .stayedSilent, .declinedInjection, .failed, .sentAfterApproval:
      break
    }
    recordActivity(
      chatID: chatID, chatTitle: chatTitle, network: network,
      inbound: inbound, replyText: decision.reply,
      outcome: effectiveOutcome, confidence: decision.confidence)
  }

  private func consumeAutoSendBudget() -> Bool {
    if Date().timeIntervalSince(autoSendWindowStart) > 3600 {
      autoSendWindowStart = Date()
      autoSendsInWindow = 0
    }
    guard autoSendsInWindow < Self.autoSendsPerHourLimit else { return false }
    autoSendsInWindow += 1
    return true
  }

  // MARK: Approvals

  func approve(_ approval: AIClonePendingApproval, editedText: String? = nil) async {
    pendingApprovals.removeAll { $0.id == approval.id }
    let text = (editedText ?? approval.replyText).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    do {
      let client = try client()
      _ = try await client.sendMessage(chatID: approval.chatID, text: text)
      recordActivity(
        chatID: approval.chatID, chatTitle: approval.chatTitle, network: approval.network,
        inboundPreview: approval.inboundPreview, replyText: text,
        outcome: .sentAfterApproval, confidence: approval.confidence)
    } catch {
      log("AIClone: approved send failed: \(error)")
      recordActivity(
        chatID: approval.chatID, chatTitle: approval.chatTitle, network: approval.network,
        inboundPreview: approval.inboundPreview, replyText: text,
        outcome: .failed, confidence: approval.confidence)
    }
  }

  func skip(_ approval: AIClonePendingApproval) {
    pendingApprovals.removeAll { $0.id == approval.id }
    recordActivity(
      chatID: approval.chatID, chatTitle: approval.chatTitle, network: approval.network,
      inboundPreview: approval.inboundPreview, replyText: approval.replyText,
      outcome: .stayedSilent, confidence: approval.confidence)
  }

  // MARK: Benchmark

  func runBenchmark(for chat: BeeperChat) async {
    guard !benchmarkRunningChatIDs.contains(chat.id) else { return }
    benchmarkRunningChatIDs.insert(chat.id)
    defer { benchmarkRunningChatIDs.remove(chat.id) }
    do {
      let client = try client()
      let history = try await client.listMessages(chatID: chat.id)
      let persona = try await loadPersona()
      let facts = await loadMemoryFacts()
      let benchmark = AICloneBenchmark(engine: replyEngine)
      let result = try await benchmark.run(
        chat: chat,
        history: history.items,
        personaName: persona?.name ?? "the user",
        personaPrompt: persona?.personaPrompt ?? "",
        memoryFacts: facts,
        judge: AICloneBackendCompletionTransport())
      configuration.benchmarkResults[chat.id] = result
      store.save(configuration)
      objectWillChange.send()
    } catch {
      log("AIClone: benchmark failed: \(error)")
    }
  }

  // MARK: Grounding caches

  private func loadPersona() async throws -> Persona? {
    if let cachedPersona { return cachedPersona }
    let persona = try? await APIClient.shared.getPersona()
    cachedPersona = persona
    return persona
  }

  private func loadMemoryFacts() async -> [String] {
    if let fetchedAt = memoryFactsFetchedAt, Date().timeIntervalSince(fetchedAt) < 600 {
      return cachedMemoryFacts
    }
    let memories = (try? await APIClient.shared.getMemories(limit: 60)) ?? []
    cachedMemoryFacts = memories.map(\.content)
    memoryFactsFetchedAt = Date()
    return cachedMemoryFacts
  }

  /// Test seam: refresh the persona/memory grounding without waiting on TTLs.
  func invalidateGroundingCaches() {
    cachedPersona = nil
    cachedMemoryFacts = []
    memoryFactsFetchedAt = nil
  }

  // MARK: Activity

  private func recordActivity(
    chatID: String, chatTitle: String, network: String,
    inbound: BeeperMessage, replyText: String?,
    outcome: AICloneActionOutcome, confidence: Double?
  ) {
    recordActivity(
      chatID: chatID, chatTitle: chatTitle, network: network,
      inboundPreview: Self.preview(inbound.text), replyText: replyText,
      outcome: outcome, confidence: confidence)
  }

  private func recordActivity(
    chatID: String, chatTitle: String, network: String,
    inboundPreview: String, replyText: String?,
    outcome: AICloneActionOutcome, confidence: Double?
  ) {
    configuration.appendActivity(
      AICloneActivityEntry(
        chatID: chatID,
        chatTitle: chatTitle,
        network: network,
        inboundPreview: inboundPreview,
        replyText: replyText.map { String($0.prefix(280)) },
        outcome: outcome,
        confidence: confidence))
    store.save(configuration)
    objectWillChange.send()
  }

  static func preview(_ text: String?) -> String {
    String(AICloneReplyEngine.strippedText(text ?? "").prefix(140))
  }
}
