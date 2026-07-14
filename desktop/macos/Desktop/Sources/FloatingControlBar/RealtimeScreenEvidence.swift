import AppKit
import CoreGraphics
import CryptoKit
import Foundation

/// The in-memory, single-turn source of truth for a PTT current-screen answer.
///
/// Pixels are captured before Omi expands its overlay, keyed to the current voice turn,
/// and never persisted into Rewind, the kernel context, or app logs. The provider only
/// receives the JPEG through the kernel-authorized `screenshot` tool result.
enum RealtimeScreenEvidenceTarget: String, Equatable, Sendable {
  case frontmostDisplay = "frontmost_display"
  case unavailable
}

struct RealtimeScreenEvidenceDescriptor: Equatable, Sendable {
  let evidenceID: String
  let turnID: VoiceTurnID
  let capturedAt: Date
  let target: RealtimeScreenEvidenceTarget
  let frontmostApp: String?
  let frontmostBundleID: String?
  let windowID: UInt32?
  let displayID: UInt32?
  let imageByteCount: Int
  let imageDigest: String?

  var canVerifyCurrentScreen: Bool {
    target != .unavailable
      && !(frontmostApp?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
      && imageByteCount > 0
      && imageDigest != nil
  }

  var opaqueID: String {
    Self.hash(evidenceID)
  }

  var opaqueAppID: String? {
    frontmostBundleID.map(Self.hash)
  }

  static func normalizedAppName(_ value: String) -> String {
    value.lowercased()
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
  }

  private static func hash(_ value: String) -> String {
    let digest = SHA256.hash(data: Data(value.utf8))
    return digest.prefix(8).map { String(format: "%02x", $0) }.joined()
  }
}

struct RealtimeScreenEvidence {
  let descriptor: RealtimeScreenEvidenceDescriptor
  /// Used only by the existing immediate PTT OCR path. It is never retained past the turn.
  let preOverlayImage: CGImage?
  /// Sent only with the matching provider tool result.
  let jpeg: Data?
  /// Distinguishes an in-flight post-capture encode from a definite failure, so a quick
  /// transcript cannot fail closed merely because JPEG work has not yet completed.
  let encodingFinished: Bool

  var isReadyForProviderDelivery: Bool {
    jpeg != nil && descriptor.canVerifyCurrentScreen
  }
}

/// The provider-facing form retains only the opaque evidence descriptor and the exact JPEG
/// captured at PTT-down. It cannot trigger another physical capture.
struct RealtimeScreenEvidenceAttachment {
  let descriptor: RealtimeScreenEvidenceDescriptor
  let jpeg: Data
}

/// Bridges the post-capture JPEG worker to an authorized tool call without blocking the
/// main PTT path. CGImage is immutable/CoreGraphics-owned; access to the result itself is
/// serialized by the lock and semaphore.
final class RealtimeScreenEvidenceReadiness: @unchecked Sendable {
  private let lock = NSLock()
  private let resolved = DispatchGroup()
  private var result: RealtimeScreenEvidence?

  init() {
    resolved.enter()
  }

  func resolve(_ evidence: RealtimeScreenEvidence) {
    lock.lock()
    guard result == nil else {
      lock.unlock()
      return
    }
    result = evidence
    lock.unlock()
    resolved.leave()
  }

  func wait(timeout: TimeInterval) -> RealtimeScreenEvidence? {
    lock.lock()
    let immediate = result
    lock.unlock()
    if let immediate { return immediate }
    guard resolved.wait(timeout: .now() + timeout) == .success else { return nil }
    lock.lock()
    defer { lock.unlock() }
    return result
  }
}

enum RealtimeScreenGroundingState: Equatable {
  case inactive
  case awaitingTranscript(RealtimeScreenEvidenceDescriptor?)
  case passthrough
  case awaitingReport(RealtimeScreenEvidenceDescriptor?)
  case accepted(RealtimeScreenEvidenceDescriptor)
  case rejected(RealtimeScreenEvidenceDescriptor?)

  var suppressesProviderOutput: Bool {
    switch self {
    case .awaitingTranscript, .awaitingReport, .accepted, .rejected:
      return true
    case .inactive, .passthrough:
      return false
    }
  }
}

enum RealtimeScreenReportDecision: Equatable {
  case accepted
  case evidenceUnavailable
  case screenshotNotDelivered
  case wrongEvidence
  case wrongApplication
  case contradictoryApplication
  case emptyAnswer
}

/// A suspended screenshot tool execution may resume after a barge-in. A stale execution is
/// allowed to fail its provider request, but it must never mutate or speak into the replacement
/// turn. Keep the admission rule pure so this cancellation boundary has a direct regression.
enum RealtimeScreenEvidenceToolExecutionPolicy {
  static func failureEvidence(
    capturedEvidence: RealtimeScreenEvidenceDescriptor?,
    commandTurnID: VoiceTurnID,
    activeTurnID: VoiceTurnID?,
    invocationIsCurrent: Bool
  ) -> RealtimeScreenEvidenceDescriptor? {
    guard invocationIsCurrent,
      activeTurnID == commandTurnID,
      capturedEvidence?.turnID == commandTurnID
    else { return nil }
    return capturedEvidence
  }
}

/// Pure policy for locally enforcing current-screen provenance. The model may propose a
/// screen observation, but it cannot make one user-visible until this policy validates it.
enum RealtimeScreenGroundingPolicy {
  static let failureText = "I couldn't verify the current screen."

  static func stateAfterFinalTranscript(
    _ transcript: String,
    evidence: RealtimeScreenEvidenceDescriptor?
  ) -> RealtimeScreenGroundingState {
    guard ScreenContextInterestDetector.isScreenContextRequest(transcript) else {
      return .passthrough
    }
    guard evidence?.canVerifyCurrentScreen == true else {
      return .rejected(evidence)
    }
    return .awaitingReport(evidence)
  }

  static func reportDecision(
    state: RealtimeScreenGroundingState,
    evidenceID: String,
    frontmostApp: String,
    answer: String,
    deliveredEvidenceID: String?,
    knownApplicationNames: [String] = []
  ) -> RealtimeScreenReportDecision {
    guard case .awaitingReport(let evidence?) = state, evidence.canVerifyCurrentScreen else {
      return .evidenceUnavailable
    }
    guard evidence.evidenceID == evidenceID else { return .wrongEvidence }
    guard deliveredEvidenceID == evidenceID else { return .screenshotNotDelivered }
    guard !answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return .emptyAnswer }
    guard RealtimeScreenEvidenceDescriptor.normalizedAppName(frontmostApp)
      == RealtimeScreenEvidenceDescriptor.normalizedAppName(evidence.frontmostApp ?? "")
    else { return .wrongApplication }
    guard !answerClaimsDifferentApplication(
      answer,
      frontmostApp: evidence.frontmostApp ?? "",
      knownApplicationNames: knownApplicationNames)
    else { return .contradictoryApplication }
    return .accepted
  }

  /// The native descriptor—not model prose—owns application identity. The model can supply
  /// detail from the image, but an answer that names a different active app fails closed.
  static func presentedAnswer(
    evidence: RealtimeScreenEvidenceDescriptor,
    answer: String
  ) -> String {
    let app = evidence.frontmostApp?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let detail = answer.trimmingCharacters(in: .whitespacesAndNewlines)
    return detail.isEmpty ? "The frontmost app is \(app)." : "The frontmost app is \(app). \(detail)"
  }

  private static func answerClaimsDifferentApplication(
    _ answer: String,
    frontmostApp: String,
    knownApplicationNames: [String]
  ) -> Bool {
    let normalizedAnswer = RealtimeScreenEvidenceDescriptor.normalizedAppName(answer)
    let normalizedFrontmost = RealtimeScreenEvidenceDescriptor.normalizedAppName(frontmostApp)
    let identityMarkers = [
      "you are in ", "you're in ", "currently in ", "frontmost app", "application", "app is ",
    ]
    if identityMarkers.contains(where: normalizedAnswer.contains),
      !normalizedAnswer.contains(normalizedFrontmost)
    {
      return true
    }
    let commonDesktopApps = [
      "cursor", "codex", "xcode", "finder", "terminal", "safari", "google chrome",
      "visual studio code", "vs code", "slack", "notion", "figma",
    ]
    let candidates = Set((knownApplicationNames + commonDesktopApps)
      .map(RealtimeScreenEvidenceDescriptor.normalizedAppName)
      .filter { !$0.isEmpty && $0 != normalizedFrontmost })
    return candidates.contains { normalizedAnswer.contains($0) }
  }
}

/// Captures the display containing the frontmost window at PTT-down. We intentionally do not
/// select the display under the mouse: that is unrelated to the window the user is speaking
/// about on a multi-display desktop.
enum RealtimeScreenEvidenceCapture {
  /// Performs only the unavoidable pre-overlay compositor capture. JPEG encoding and hashing
  /// run after microphone capture begins so a first PTT is not blocked on image processing.
  static func capture(for turnID: VoiceTurnID) -> RealtimeScreenEvidence {
    let capturedAt = Date()
    let frontmostApplication = NSWorkspace.shared.frontmostApplication
    let frontmostWindowID = frontmostApplication.flatMap {
      frontmostOnScreenWindowID(ownedBy: $0.processIdentifier)
    }
    let appName = frontmostApplication?.localizedName
    let bundleID = frontmostApplication?.bundleIdentifier
    let displayID = displayContaining(windowID: frontmostWindowID) ?? onlyActiveDisplay()
    // A PTT evidence capture must never silently fall back to the mouse-selected display.
    // On an ambiguous multi-display desktop we fail closed instead of describing the wrong one.
    let image = displayID.flatMap { ScreenCaptureManager.captureScreenImage(displayID: $0) }
    let target: RealtimeScreenEvidenceTarget = image == nil ? .unavailable : .frontmostDisplay
    let descriptor = RealtimeScreenEvidenceDescriptor(
      evidenceID: UUID().uuidString.lowercased(),
      turnID: turnID,
      capturedAt: capturedAt,
      target: target,
      frontmostApp: appName,
      frontmostBundleID: bundleID,
      windowID: frontmostWindowID.map { UInt32($0) },
      displayID: displayID.map { UInt32($0) },
      imageByteCount: 0,
      imageDigest: nil
    )
    return RealtimeScreenEvidence(
      descriptor: descriptor,
      preOverlayImage: image,
      jpeg: nil,
      encodingFinished: image == nil)
  }

  static func encode(_ evidence: RealtimeScreenEvidence) -> RealtimeScreenEvidence {
    guard let image = evidence.preOverlayImage,
      let jpeg = ScreenCaptureManager.jpegData(from: image)
    else {
      return RealtimeScreenEvidence(
        descriptor: evidence.descriptor,
        preOverlayImage: evidence.preOverlayImage,
        jpeg: nil,
        encodingFinished: true)
    }
    let descriptor = RealtimeScreenEvidenceDescriptor(
      evidenceID: evidence.descriptor.evidenceID,
      turnID: evidence.descriptor.turnID,
      capturedAt: evidence.descriptor.capturedAt,
      target: evidence.descriptor.target,
      frontmostApp: evidence.descriptor.frontmostApp,
      frontmostBundleID: evidence.descriptor.frontmostBundleID,
      windowID: evidence.descriptor.windowID,
      displayID: evidence.descriptor.displayID,
      imageByteCount: jpeg.count,
      imageDigest: sha256(jpeg)
    )
    return RealtimeScreenEvidence(
      descriptor: descriptor,
      preOverlayImage: image,
      jpeg: jpeg,
      encodingFinished: true)
  }

  /// Avoid Accessibility calls here: PTT-down is latency-sensitive and an AX cold start can
  /// block the first turn. The compositor's front-to-back list is enough to identify the
  /// frontmost on-screen window for the already-known foreground process.
  private static func frontmostOnScreenWindowID(ownedBy pid: pid_t) -> CGWindowID? {
    guard let windows = CGWindowListCopyWindowInfo(
      [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    else { return nil }
    for window in windows {
      guard let ownerPID = window[kCGWindowOwnerPID as String] as? NSNumber,
        ownerPID.int32Value == pid,
        let number = window[kCGWindowNumber as String] as? NSNumber,
        let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
        let rect = CGRect(dictionaryRepresentation: bounds as CFDictionary),
        rect.width >= 32, rect.height >= 32
      else { continue }
      return CGWindowID(number.uint32Value)
    }
    return nil
  }

  private static func displayContaining(windowID: CGWindowID?) -> CGDirectDisplayID? {
    guard let windowID,
      let windows = CGWindowListCopyWindowInfo([.optionIncludingWindow], windowID)
        as? [[String: Any]],
      let bounds = windows.first?[kCGWindowBounds as String] as? [String: CGFloat],
      let rect = CGRect(dictionaryRepresentation: bounds as CFDictionary)
    else { return nil }

    var display = CGDirectDisplayID()
    var count: UInt32 = 0
    guard CGGetDisplaysWithRect(rect, 1, &display, &count) == .success, count == 1 else {
      return nil
    }
    return display
  }

  private static func onlyActiveDisplay() -> CGDirectDisplayID? {
    var display = CGDirectDisplayID()
    var count: UInt32 = 0
    guard CGGetActiveDisplayList(1, &display, &count) == .success, count == 1 else {
      return nil
    }
    return display
  }

  private static func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }
}
