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

struct AICloneInboundQueue {
  private var inFlightChatIDs: Set<String> = []
  private var pendingByChatID: [String: BeeperMessage] = [:]

  mutating func submit(_ inbound: BeeperMessage, chatID: String) -> BeeperMessage? {
    guard !inFlightChatIDs.contains(chatID) else {
      pendingByChatID[chatID] = inbound
      return nil
    }
    inFlightChatIDs.insert(chatID)
    return inbound
  }

  mutating func complete(chatID: String) -> BeeperMessage? {
    if let pending = pendingByChatID.removeValue(forKey: chatID) {
      return pending
    }
    inFlightChatIDs.remove(chatID)
    return nil
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
  private var clientFactory: (String, URL) -> BeeperDesktopClient
  /// Base URL discovered from Beeper's public /v1/info (self-corrects the port
  /// across Beeper versions). Defaults to the current known port until probed.
  private var resolvedBaseURL = BeeperDesktopClient.defaultBaseURL
  private var socketTask: URLSessionWebSocketTask?
  private var listenLoopTask: Task<Void, Never>?
  private var reconnectAttempts = 0
  private var listeningSince = Date()
  /// Chats currently being processed — coalesces bursts of message.upserted
  /// events so one inbound burst produces one reply decision.
  private var inboundQueue = AICloneInboundQueue()
  /// Inbound message ids the clone has already acted on. Beeper emits the same
  /// message as several `message.upserted` events (bridge numeric id, then the
  /// Matrix event id, plus edits), so one message must reply at most once.
  private var processedInboundMessageIDs: Set<String> = []
  private var processedInboundOrder: [String] = []
  private static let processedInboundLimit = 500
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
    clientFactory: @escaping (String, URL) -> BeeperDesktopClient = {
      BeeperDesktopClient(accessToken: $0, baseURL: $1)
    }
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

  /// UserDefaults key used for the Beeper token on non-production bundles.
  /// The login Keychain's item ACL is bound to the code signature, so ad-hoc
  /// `omi-*` test builds (re-signed every rebuild) cannot silently read a token
  /// written by a prior build and would otherwise prompt for the Keychain
  /// password. The token is a local, revocable Beeper access token, so on
  /// non-production builds it lives in UserDefaults (stable across rebuilds, no
  /// prompt); production (stable Developer ID signature) keeps it in the
  /// Keychain.
  static let tokenDefaultsKey = "aiCloneBeeperAccessToken"
  private static var usesKeychainForToken: Bool { AppBuild.isProductionBundle }

  func storedAccessToken() -> String? {
    if Self.usesKeychainForToken {
      return DesktopKeychainStore.string(service: Self.tokenService, account: Self.tokenAccount)
    }
    let value = UserDefaults.standard.string(forKey: Self.tokenDefaultsKey)
    return (value?.isEmpty ?? true) ? nil : value
  }

  func saveAccessToken(_ token: String) {
    let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    if Self.usesKeychainForToken {
      _ = DesktopKeychainStore.setString(trimmed, service: Self.tokenService, account: Self.tokenAccount)
    } else {
      UserDefaults.standard.set(trimmed, forKey: Self.tokenDefaultsKey)
    }
  }

  func disconnectAndForgetToken() {
    stopListening()
    UserDefaults.standard.removeObject(forKey: Self.tokenDefaultsKey)
    DesktopKeychainStore.delete(service: Self.tokenService, account: Self.tokenAccount)
    connectionState = .disconnected
    chats = []
  }

  private func client() throws -> BeeperDesktopClient {
    guard let token = storedAccessToken(), !token.isEmpty else {
      throw BeeperClientError.notConfigured
    }
    return clientFactory(token, resolvedBaseURL)
  }

  // MARK: Connect (functional probe, INV-INT-1)

  /// "Connected" is earned by a live probe every time — reach the API, pass
  /// auth, and enumerate accounts — never latched from a past success.
  func connect() async {
    connectionState = .connecting
    do {
      // Locate the running Beeper Desktop API first (public, no token needed),
      // then run the authed probe against the port it actually reports.
      if let discovered = await BeeperDesktopClient.discoverBaseURL() {
        resolvedBaseURL = discovered
      }
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
      return
        "Beeper rejected the token. In Beeper Desktop open Settings, then Developer, and create a new access token."
    case let urlError as URLError where urlError.code == .cannotConnectToHost || urlError.code == .timedOut:
      return "Beeper Desktop isn't reachable. Open Beeper Desktop and enable the Desktop API, then retry."
    default:
      return "Couldn't connect to Beeper Desktop. Check that it is running with the Desktop API enabled."
    }
  }

  /// App-launch entry point: reconnect and start listening when the user left
  /// the clone enabled. Silent no-op otherwise, so a disabled or unconfigured
  /// clone makes no network calls at launch.
  func resumeIfEnabled() {
    guard configuration.enabled, hasAccessToken, !connectionState.isConnected else { return }
    Task { await connect() }
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
    log("AIClone: message.upserted in enabled chat (mode=\(mode.rawValue))")
    guard
      let inbound = Self.latestActionableInbound(
        entries: event.entries ?? [],
        since: listeningSince)
    else {
      log("AIClone: event had no fresh inbound message to act on")
      return
    }
    // One reply per message: Beeper re-emits the same message under multiple
    // event/envelope ids, so dedupe on the message id, not the event.
    guard claimInbound(inbound.id) else {
      log("AIClone: duplicate event for an already-handled message; ignoring")
      return
    }
    guard var next = inboundQueue.submit(inbound, chatID: chatID) else { return }
    while true {
      if configuration.mode(for: chatID) != .off {
        await processInbound(next, chatID: chatID)
      }
      guard let pending = inboundQueue.complete(chatID: chatID) else { return }
      next = pending
    }
  }

  /// Claims an inbound message id for processing. Returns true the first time a
  /// message id is seen and false for every duplicate event afterward, so one
  /// message produces at most one reply. Bounded so it can't grow unbounded.
  func claimInbound(_ id: String) -> Bool {
    guard !processedInboundMessageIDs.contains(id) else { return false }
    processedInboundMessageIDs.insert(id)
    processedInboundOrder.append(id)
    if processedInboundOrder.count > Self.processedInboundLimit {
      let evicted = processedInboundOrder.removeFirst()
      processedInboundMessageIDs.remove(evicted)
    }
    return true
  }

  /// Undoes `claimInbound` when the message never reached a terminal action, so
  /// a later redelivery of the same message can be retried.
  func releaseInbound(_ id: String) {
    guard processedInboundMessageIDs.remove(id) != nil else { return }
    processedInboundOrder.removeAll { $0 == id }
  }

  /// Beeper's message page order is documented only as "sorted by timestamp" —
  /// the direction is not guaranteed across versions, and both the reply prompt
  /// (`threadLines`) and the benchmark require oldest-first input. Sort
  /// explicitly when every message carries a parseable timestamp; otherwise
  /// leave the page untouched rather than inventing an order.
  nonisolated static func oldestFirst(_ messages: [BeeperMessage]) -> [BeeperMessage] {
    var dated: [(offset: Int, date: Date, message: BeeperMessage)] = []
    dated.reserveCapacity(messages.count)
    for (offset, message) in messages.enumerated() {
      guard let stamp = message.timestamp, let date = parseTimestamp(stamp) else { return messages }
      dated.append((offset, date, message))
    }
    return
      dated
      .sorted { lhs, rhs in
        lhs.date == rhs.date ? lhs.offset < rhs.offset : lhs.date < rhs.date
      }
      .map(\.message)
  }

  nonisolated static func parseTimestamp(_ value: String) -> Date? {
    let isoFractional = ISO8601DateFormatter()
    isoFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return isoFractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
  }

  /// The newest event entry worth replying to: text-like, sent by someone
  /// else, and not older than the listening session (history backfill and
  /// edits of old messages must never trigger the clone).
  nonisolated static func latestActionableInbound(entries: [BeeperMessage], since: Date) -> BeeperMessage? {
    return entries.last { message in
      guard message.isSender != true, message.isDeleted != true, message.isTextLike,
        let text = message.text, !text.isEmpty
      else { return false }
      guard let stamp = message.timestamp, let date = parseTimestamp(stamp) else { return false }
      return date >= since.addingTimeInterval(-5)
    }
  }

  // MARK: Reply pipeline

  private func processInbound(_ inbound: BeeperMessage, chatID: String) async {
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
        thread: Self.oldestFirst(thread.items))
      let decision = try await replyEngine.decide(context: context)
      // Grounding and the model take several round-trips; the user may have
      // turned the clone off or moved this chat to Off while they ran. Re-read
      // the policy so a verdict is never acted on under stale authority.
      let currentMode = configuration.mode(for: chatID)
      guard !Task.isCancelled, configuration.enabled, currentMode != .off else {
        log("AIClone: policy changed while replying; discarding the verdict")
        releaseInbound(inbound.id)
        return
      }
      let outcome = decision.plannedOutcome(
        mode: currentMode,
        autoConfidenceThreshold: configuration.autoSendConfidenceThreshold,
        inboundText: inbound.text ?? "")
      log(
        "AIClone: reply decision shouldReply=\(decision.shouldReply) confidence=\(decision.confidence) injection=\(decision.suspectedInjection) outcome=\(outcome.rawValue)"
      )
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
      // The claim is only durable once the message reached a terminal action.
      // A transient failure (Beeper closed, backend hiccup) must not retire the
      // id, or the redelivered `message.upserted` would be dropped as a
      // duplicate and the message skipped forever.
      releaseInbound(inbound.id)
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
    let text = (editedText ?? approval.replyText).trimmingCharacters(in: .whitespacesAndNewlines)
    // An empty edit is not "discard this reply" — keep it waiting instead of
    // silently dropping the user's pending approval.
    guard !text.isEmpty else { return }
    pendingApprovals.removeAll { $0.id == approval.id }
    do {
      let client = try client()
      _ = try await client.sendMessage(chatID: approval.chatID, text: text)
      recordActivity(
        chatID: approval.chatID, chatTitle: approval.chatTitle, network: approval.network,
        inboundPreview: approval.inboundPreview, replyText: text,
        outcome: .sentAfterApproval, confidence: approval.confidence)
    } catch {
      log("AIClone: approved send failed: \(error)")
      // Beeper was closed or rejected the send — put the (edited) reply back in
      // the queue so the user can retry instead of losing what they wrote.
      var restored = approval
      restored.replyText = text
      pendingApprovals.append(restored)
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

  /// Clears the activity log only. Pending approvals are unsent work the user
  /// still has to decide on, so a log-clearing button must never discard them;
  /// chat modes and the Beeper connection are untouched too.
  func clearActivity() {
    configuration.activityLog.removeAll()
    store.save(configuration)
    objectWillChange.send()
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
        history: Self.oldestFirst(history.items),
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

  /// Test seam: stage an approval exactly as the reply pipeline would, so the
  /// approve/skip lifecycle is exercisable without a live Beeper event.
  func enqueueApprovalForTesting(_ approval: AIClonePendingApproval) {
    pendingApprovals.append(approval)
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
