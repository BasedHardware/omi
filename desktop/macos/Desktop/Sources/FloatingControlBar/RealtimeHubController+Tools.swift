import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

/// Per-session arming record for synthetic HID input. Owner identity says who is
/// driving the session; this says whether the user agreed to let the model move
/// the pointer at all. It is keyed to one physical session so it cannot survive
/// the session that granted it.
struct SyntheticInputArmingState: Equatable {
  private(set) var armedSessionKey: ObjectIdentifier?

  func isArmed(forSessionKey key: ObjectIdentifier?) -> Bool {
    guard let key, let armedSessionKey else { return false }
    return key == armedSessionKey
  }

  /// Arms only when the supplied user confirmation returns true. No tool argument
  /// reaches this call, so the model cannot arm itself.
  mutating func armIfUserConfirms(
    sessionKey: ObjectIdentifier?,
    confirm: () -> Bool
  ) -> Bool {
    if isArmed(forSessionKey: sessionKey) { return true }
    guard let sessionKey, confirm() else { return false }
    armedSessionKey = sessionKey
    return true
  }

  mutating func disarm() {
    armedSessionKey = nil
  }
}

extension RealtimeHubController {
  // MARK: - Tools

  var syntheticInputSessionKey: ObjectIdentifier? {
    session.map(ObjectIdentifier.init)
  }

  /// Asks the user once per physical session before any synthetic click is posted.
  func ensureSyntheticInputArmed() -> Bool {
    syntheticInputArming.armIfUserConfirms(
      sessionKey: syntheticInputSessionKey,
      confirm: {
        AgentToolConsentGate.confirm(AgentToolConsentPolicy.syntheticInputArmingRequest())
      })
  }

  /// ask_higher_model — reuse the EXISTING prompt-cached /v2/chat/completions
  /// (no new backend route). Returns the assistant text for the model to speak.
  func escalateToHigherModel(
    _ query: String,
    kernelSemanticGuidance: String,
    kernelContext: String,
    stableCacheIdentity: String,
    dynamicContextIdentity: String,
    contextPlanID: String,
    toolContext: String,
    ownerID: String
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    let body = RealtimeHubTools.escalationBody(
      query: query,
      kernelSemanticGuidance: kernelSemanticGuidance,
      kernelContext: kernelContext,
      stableCacheIdentity: stableCacheIdentity,
      dynamicContextIdentity: dynamicContextIdentity,
      contextPlanID: contextPlanID,
      toolContext: toolContext)
    let t0 = Date()
    do {
      let answer = try await APIClient.shared.askHigherModel(
        body: body,
        expectedOwnerID: ownerID)
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      log(
        "RealtimeHub: ask_higher_model ← \(ModelQoS.Claude.defaultSelection) OK in \(ms)ms (\(answer.count) chars)"
      )
      return .succeeded(answer)
    } catch AuthError.userChangedDuringRequest {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    } catch {
      log("RealtimeHub: ask_higher_model failed — \(error.localizedDescription)")
      return .succeeded("I ran into an error reaching the model.")
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
