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

  init(host: ChatProvider) {
    self.host = host
  }

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

    _ = host.recordCompletedTurn(
      userText: turn.userText,
      assistantText: turn.assistantText,
      logLabel: turn.origin == "realtime_voice" ? "voice" : "kernel_turn",
      messageSource: turn.origin,
      continuityKey: key.isEmpty ? nil : key
    )
  }

  private func rememberAppliedKernelTurnKey(_ key: String) {
    appliedKernelTurnKeys.insert(key)
    if appliedKernelTurnKeys.count > 64 {
      appliedKernelTurnKeys = Set(Array(appliedKernelTurnKeys).suffix(32))
    }
  }

  func recordSurfaceTurn(
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String = "realtime_voice",
    interrupted: Bool = false,
    idempotencyKey: String? = nil
  ) async {
    guard let host, await host.ensureBridgeStartedForKernel() else { return }
    guard let client else { return }
    await client.recordSurfaceTurn(
      surface: surface,
      userText: userText,
      assistantText: assistantText,
      origin: origin,
      interrupted: interrupted,
      idempotencyKey: idempotencyKey
    )
  }

  func fetchVoiceSeedContext(surface: AgentSurfaceReference) async -> String {
    guard let host, await host.ensureBridgeStartedForKernel() else { return "" }
    guard let client else { return "" }
    do {
      return try await client.getVoiceSeedContext(surface: surface).context
    } catch {
      log("KernelTurnProjection: voice seed fetch failed: \(error.localizedDescription)")
      return ""
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
