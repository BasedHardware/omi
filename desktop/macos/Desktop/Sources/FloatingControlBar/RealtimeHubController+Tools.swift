import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

extension RealtimeHubController {
  // MARK: - Tools

  /// think_deeper — run the question through the same kernel session,
  /// model selection, and tool surface as typed Chat. Returns its final text
  /// for the realtime provider to speak faithfully.
  func escalateToHigherModel(
    _ query: String,
    toolContext: String,
    invocationID: String,
    ownerID: String
  ) async -> AuthorizedRealtimeToolExecutionResult {
    // The chat lane cannot see the screen; hand it what this turn's screenshot showed so
    // "what's the answer to this riddle?" resolves to the riddle on screen, not an earlier one.
    // When the realtime model escalated without grounding on the image, fall back to the OCR
    // text of the same PTT-down frame so the escalation is never blind to the current screen.
    var screenContext = screenContextByContinuityKey[turnIdempotencyKey]
    if screenContext == nil,
      let ocr = await PushToTalkManager.shared.visibleScreenText(timeout: 1.5)
    {
      screenContext = "OCR text of the screen at the moment they pressed the key:\n\(ocr)"
    }
    return await queryChatLaneForVoice(
      prompt: RealtimeHubTools.escalationUserPrompt(
        query: query, toolContext: toolContext, screenContext: screenContext),
      invocationID: invocationID,
      ownerID: ownerID,
      toolName: HubTool.thinkDeeper.rawValue,
      failureMessage: "I ran into an error reaching the model.")
  }

  /// web_search — execute a fresh public-only lookup and return its grounded
  /// answer for the realtime provider to speak faithfully.
  func searchPublicWeb(
    _ query: String,
    toolContext _: String,
    invocationID: String,
    ownerID: String
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    let t0 = Date()
    do {
      let answer = try await APIClient.shared.searchPublicWebForVoice(
        query: RealtimeHubTools.publicWebSearchPrompt(query: query),
        expectedOwnerID: ownerID)
      guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
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

  private func queryChatLaneForVoice(
    prompt: String,
    invocationID: String,
    ownerID: String,
    toolName: String,
    failureMessage: String
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    let t0 = Date()
    do {
      let answer = try await FloatingControlBarManager.shared.askChatLaneForSpokenAnswer(
        prompt: prompt,
        invocationID: invocationID,
        expectedOwnerID: ownerID)
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      log("RealtimeHub: \(toolName) chat lane OK in \(ms)ms (\(answer.count) chars)")
      return .succeeded(answer)
    } catch RealtimeChatLaneError.ownerChanged {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    } catch {
      log("RealtimeHub: \(toolName) failed — \(error.localizedDescription)")
      return .succeeded(failureMessage)
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
