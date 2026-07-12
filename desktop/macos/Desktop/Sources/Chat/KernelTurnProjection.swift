import Foundation

/// Projects kernel `turn_recorded` events into main-chat UI state and records
/// surface turns / voice seed fetches for the realtime hub.
@MainActor
final class KernelTurnProjection {
  private weak var host: ChatProvider?
  private var client: AgentClient.Session?
  /// Continuity keys already committed from kernel `turn_recorded` (or promoted
  /// optimistic stages). Prevents double-append of the same logical turn.
  private var appliedKernelTurnKeys = Set<String>()
  /// Insertion order of `appliedKernelTurnKeys`, so eviction drops the OLDEST
  /// keys rather than an arbitrary hash-ordered subset (see
  /// rememberAppliedKernelTurnKey).
  private var appliedKernelTurnKeyOrder: [String] = []
  private let appliedKernelTurnKeysCap = 64
  private let appliedKernelTurnKeysTrimTo = 32

  init(host: ChatProvider) {
    self.host = host
  }

  /// Registers this projection as the sole turn_recorded UI apply gate (INV-6).
  /// Runtime keeps one replaceable handler slot — re-attach after warm/restart
  /// must not accumulate duplicate applies into chat.
  func attachClient(_ client: AgentClient.Session) async {
    self.client = client
    await client.setTurnRecordedHandler { [weak self] turn in
      Task { @MainActor [weak self] in
        self?.apply(turn)
      }
    }
  }

  func apply(_ turn: AgentRuntimeProcess.KernelTurnRecorded) {
    guard let host else { return }
    let expectedSurface = host.mainChatSurfaceReference()
    guard turn.surfaceKind == expectedSurface.surfaceKind,
          turn.externalRefKind == expectedSurface.externalRefKind,
          turn.externalRefId == expectedSurface.externalRefId
    else {
      return
    }

    let key = turn.idempotencyKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !key.isEmpty {
      guard !appliedKernelTurnKeys.contains(key) else { return }
      if host.hasOptimisticTurn(continuityKey: key) {
        host.promoteOptimisticTurn(continuityKey: key, from: turn)
        rememberAppliedKernelTurnKey(key)
        return
      }
      rememberAppliedKernelTurnKey(key)
    }

    let contentBlocks = Self.contentBlocksForKernelApply(turn)
    _ = host.recordCompletedTurn(
      userText: turn.userText,
      assistantText: turn.assistantText,
      logLabel: turn.origin == "realtime_voice" ? "voice" : "kernel_turn",
      messageSource: turn.origin,
      continuityKey: key.isEmpty ? nil : key,
      contentBlocks: contentBlocks
    )
  }

  /// For kernel-only pill completions (no optimistic stage), materialize a
  /// structured agentCompletion block from legacy bracket summary text.
  static func contentBlocksForKernelApply(
    _ turn: AgentRuntimeProcess.KernelTurnRecorded
  ) -> [ChatContentBlock] {
    guard turn.origin == "pill_completion" else { return [] }
    guard let summary = BackgroundAgentSummary.parse(turn.assistantText) else { return [] }
    let runId = Self.runIdFromPillCompletionKey(turn.idempotencyKey)
    let trimmedKey = turn.idempotencyKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let stableSeed =
      (!trimmedKey.isEmpty ? trimmedKey : nil)
      ?? runId
      ?? summary.agentID?.uuidString
      ?? summary.prompt
    let blockId = "agent_completion:\(stableSeed)"
    return [
      .agentCompletion(
        id: blockId,
        pillId: summary.agentID,
        sessionId: nil,
        runId: runId,
        title: "Background agent",
        promptSnippet: summary.prompt,
        output: summary.output,
        status: "completed"
      )
    ]
  }

  private static func runIdFromPillCompletionKey(_ key: String?) -> String? {
    guard let key else { return nil }
    let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
    let prefix = "pill_completion:"
    guard trimmed.hasPrefix(prefix) else { return nil }
    let value = String(trimmed.dropFirst(prefix.count))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    // Keys may be pill UUID when runId was absent — only treat non-UUID as runId.
    if UUID(uuidString: value) != nil { return nil }
    return value.isEmpty ? nil : value
  }

  private func rememberAppliedKernelTurnKey(_ key: String) {
    // Track first-seen order so eviction can drop the OLDEST keys. The previous
    // `Set(Array(set).suffix(32))` operated on a hash-ordered array, so it kept an
    // ARBITRARY 32 keys — a just-applied key could be evicted while a stale one
    // survived, letting a re-delivered turn_recorded (durable-outbox replay or
    // bridge reattach) slip past the dedup guard and double-append the same
    // logical turn (INV-6 rule 4).
    guard appliedKernelTurnKeys.insert(key).inserted else { return }
    appliedKernelTurnKeyOrder.append(key)
    if appliedKernelTurnKeyOrder.count > appliedKernelTurnKeysCap {
      let evictCount = appliedKernelTurnKeyOrder.count - appliedKernelTurnKeysTrimTo
      for evicted in appliedKernelTurnKeyOrder.prefix(evictCount) {
        appliedKernelTurnKeys.remove(evicted)
      }
      appliedKernelTurnKeyOrder.removeFirst(evictCount)
    }
  }

  func recordSurfaceTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    userText: String,
    assistantText: String,
    origin: String = "realtime_voice",
    interrupted: Bool = false,
    idempotencyKey: String? = nil
  ) async -> Bool {
    guard let host, await host.ensureBridgeStartedForKernel() else { return false }
    guard let client else { return false }
    do {
      return try await client.recordSurfaceTurn(
        surface: surface,
        ownerID: ownerID,
        userText: userText,
        assistantText: assistantText,
        origin: origin,
        interrupted: interrupted,
        idempotencyKey: idempotencyKey
      )
    } catch {
      log("KernelTurnProjection: surface turn persistence failed: \(error.localizedDescription)")
      return false
    }
  }

  func fetchVoiceSeedContext(surface: AgentSurfaceReference) async -> String {
    await fetchVoiceSeedSnapshot(surface: surface).context
  }

  func fetchVoiceSeedSnapshot(
    surface: AgentSurfaceReference
  ) async -> AgentRuntimeProcess.VoiceSeedContextResult {
    let empty = AgentRuntimeProcess.VoiceSeedContextResult(
      conversationId: "", context: "", idempotencyKeys: [])
    guard let host, await host.ensureBridgeStartedForKernel() else { return empty }
    guard let client else { return empty }
    do {
      return try await client.getVoiceSeedContext(surface: surface)
    } catch {
      log("KernelTurnProjection: voice seed fetch failed: \(error.localizedDescription)")
      return empty
    }
  }

  func fetchKernelTurnTail(limit: Int = 8) async -> AgentRuntimeProcess.KernelTurnTailResult? {
    guard let host, await host.ensureBridgeStartedForKernel() else { return nil }
    guard let client else { return nil }
    do {
      return try await client.getKernelTurnTail(limit: limit)
    } catch {
      log("KernelTurnProjection: kernel turn tail fetch failed: \(error.localizedDescription)")
      return nil
    }
  }

  func clearOwnerSurfaceState(chatId: String = "default") async {
    guard let host, await host.ensureBridgeStartedForKernel() else { return }
    guard let client else { return }
    await client.clearOwnerSurfaceState(chatId: chatId)
  }

  func projectCrossSurfaceTurn(
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String,
    idempotencyKey: String? = nil
  ) async {
    guard let host, await host.ensureBridgeStartedForKernel() else { return }
    guard let client else { return }
    await client.projectCrossSurfaceTurn(
      surface: surface,
      userText: userText,
      assistantText: assistantText,
      origin: origin,
      idempotencyKey: idempotencyKey
    )
  }
}
