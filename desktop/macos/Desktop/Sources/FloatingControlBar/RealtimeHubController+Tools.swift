import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

extension RealtimeHubController {
  // MARK: - Tools

  /// think_deeper — single-shot Luna escalation with explicit reasoning effort.
  /// Forwards the kernel context snapshot, the untrusted tool context, and the
  /// exact screenshots the PTT agent viewed this turn, then returns the final
  /// text for the realtime provider to speak faithfully.
  func escalateToHigherModel(
    _ query: String,
    toolContext: String,
    thinkingLevel: RealtimeHubTools.EscalationThinkingLevel,
    invocationTurnID: VoiceTurnID?,
    invocationID _: String,
    ownerID: String
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    // The same kernel snapshot material the realtime session was instructed
    // with, scoped to the current owner.
    let context = voiceSessionContext(for: currentOwnerScope)
    // Screen pixels are forwarded only for an explicitly visual request. This
    // preserves the exact same-turn evidence while keeping unrelated research
    // escalations from inheriting an ambient settings page.
    let needsTurnImage = RealtimeHubTools.escalationNeedsTurnImage(query: query)
    let screenJPEGs =
      needsTurnImage
      ? RealtimeHubTools.escalationScreenJPEGs(
        expectedTurnID: invocationTurnID,
        evidence: screenEvidence,
        authorizedScreenshots: authorizedRealtimeScreenshotImages)
      : []
    var screenContext = needsTurnImage ? screenContextByContinuityKey[turnIdempotencyKey] : nil
    if needsTurnImage, screenJPEGs.isEmpty, screenContext == nil,
      let ocr = await PushToTalkManager.shared.visibleScreenText(timeout: 1.5)
    {
      screenContext = "OCR text of the screen at the moment they pressed the key:\n\(ocr)"
    }
    let publicWebEvidence = invocationTurnID.flatMap { turnPublicWebEvidence?.evidence(for: $0) }
    let body = RealtimeHubTools.escalationBody(
      query: query,
      kernelSemanticGuidance: context.semanticGuidance,
      kernelContext: context.rendered,
      stableCacheIdentity: context.stableCacheIdentity,
      dynamicContextIdentity: context.dynamicContextIdentity,
      contextPlanID: context.planID,
      toolContext: toolContext,
      screenContext: screenContext,
      publicWebEvidence: publicWebEvidence,
      thinkingLevel: thinkingLevel,
      screenJPEGs: screenJPEGs)
    let t0 = Date()
    do {
      let answer = try await APIClient.shared.thinkDeeperForVoice(
        body: body,
        thinkingLevel: thinkingLevel,
        expectedOwnerID: ownerID)
      guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      log(
        "RealtimeHub: think_deeper ← \(RealtimeHubTools.escalationModel) "
          + "effort=\(thinkingLevel.lunaReasoningEffort) images=\(screenJPEGs.count) "
          + "OK in \(ms)ms (\(answer.count) chars)")
      return .succeeded(answer)
    } catch AuthError.userChangedDuringRequest {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    } catch {
      guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      log("RealtimeHub: think_deeper failed — \(error.localizedDescription)")
      return .succeeded("I ran into an error reaching the model.")
    }
  }

  /// web_search — execute a fresh public-only lookup and return its grounded
  /// answer for the realtime provider to speak faithfully.
  func searchPublicWeb(
    _ query: String,
    scope: RealtimePublicWebSearchScope,
    toolContext _: String,
    invocationID: String,
    ownerID: String,
    turnID: VoiceTurnID
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    let t0 = Date()
    do {
      let prompts = RealtimeHubTools.publicWebSearchPrompts(query: query, scope: scope)
      let answer: String
      if prompts.count == 1 {
        answer = try await APIClient.shared.searchPublicWebForVoice(
          query: prompts[0], expectedOwnerID: ownerID)
      } else {
        async let primary = try? await APIClient.shared.searchPublicWebForVoice(
          query: prompts[0], expectedOwnerID: ownerID, includeSourceEvidence: true)
        async let corroborating = try? await APIClient.shared.searchPublicWebForVoice(
          query: prompts[1], expectedOwnerID: ownerID, includeSourceEvidence: true)
        async let exactMatch = try? await APIClient.shared.searchPublicWebForVoice(
          query: prompts[2], expectedOwnerID: ownerID, includeSourceEvidence: true)
        let (primaryAnswer, corroboratingAnswer, exactMatchAnswer) = await (
          primary, corroborating, exactMatch
        )
        guard
          let combined = RealtimeHubTools.combinedHistoricalWebEvidence(
            primary: primaryAnswer,
            corroborating: corroboratingAnswer,
            exactMatch: exactMatchAnswer)
        else {
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "realtime_hub", from: "primary_search", to: "corroborating_search",
            reason: "other", outcome: .exhausted)
          throw RealtimePublicWebSearchError.noEvidence
        }
        if primaryAnswer == nil || corroboratingAnswer == nil || exactMatchAnswer == nil {
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "realtime_hub", from: "historical_dual_search", to: "single_search_evidence",
            reason: "other", outcome: .degraded)
        }
        answer = combined
      }
      guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      guard VoiceTurnCoordinator.shared.activeTurnID == turnID else {
        return .failed(Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
      }
      turnPublicWebEvidence = RealtimePublicWebEvidenceReceipt(turnID: turnID, evidence: answer)
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      log("RealtimeHub: web_search public lane OK in \(ms)ms (\(answer.count) chars)")
      return .succeeded(answer)
    } catch {
      guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      log("RealtimeHub: web_search failed — \(error.localizedDescription)")
      return .succeeded("The web lookup failed. Please try again.")
    }
  }

  /// Executes a synchronous physical effect only while the immutable command
  /// owner is still current. Because this check and closure run on MainActor
  /// without suspension, an account-switch callback cannot interleave between
  /// the fence and the physical operation.
  @MainActor
  static func performOwnerBoundPhysicalEffect<T>(
    expectedOwnerID: String,
    ownerIsCurrent: (String) -> Bool = { AuthorizedToolExecution.isOwnerCurrent($0) },
    effect: () -> T
  ) -> T? {
    guard ownerIsCurrent(expectedOwnerID) else { return nil }
    return effect()
  }

  /// Local synthetic mouse click (point_click tool).
  @discardableResult
  static func click(
    at point: CGPoint,
    expectedOwnerID: String,
    ownerIsCurrent: (String) -> Bool = { AuthorizedToolExecution.isOwnerCurrent($0) },
    postEvents: (CGPoint) -> Bool = { point in
      guard
        let down = CGEvent(
          mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point,
          mouseButton: .left),
        let up = CGEvent(
          mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point,
          mouseButton: .left)
      else { return false }
      down.post(tap: .cghidEventTap)
      up.post(tap: .cghidEventTap)
      return true
    }
  ) -> Bool {
    performOwnerBoundPhysicalEffect(
      expectedOwnerID: expectedOwnerID,
      ownerIsCurrent: ownerIsCurrent,
      effect: { postEvents(point) }) ?? false
  }

  nonisolated static func finiteCoordinate(_ value: Any?) -> Double? {
    let coordinate: Double?
    switch value {
    case is Bool:
      coordinate = nil
    case let number as NSNumber:
      coordinate = number.doubleValue
    case let double as Double:
      coordinate = double
    case let int as Int:
      coordinate = Double(int)
    default:
      coordinate = nil
    }
    guard let coordinate, coordinate.isFinite else { return nil }
    return coordinate
  }
}

private enum RealtimePublicWebSearchError: Error {
  case noEvidence
}
