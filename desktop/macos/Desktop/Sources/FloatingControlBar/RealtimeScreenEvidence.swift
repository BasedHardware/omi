import AppKit
import CoreGraphics
import CryptoKit
import Foundation
import VoiceTurnDomain

/// The in-memory, single-turn source of truth for a PTT current-screen answer.
///
/// Pixels are captured before Omi expands its overlay, keyed to the current voice turn,
/// and never persisted into Rewind, the kernel context, or app logs. The provider only
/// receives the JPEG through the kernel-authorized `screenshot` tool result.
enum RealtimeScreenEvidenceTarget: String, Equatable, Sendable {
  case frontmostDisplay = "frontmost_display"
  case unavailable
}

/// A physical capture failure that the realtime tool and local spoken fallback can explain
/// without treating a missing image as visual evidence (for example, a black screen).
enum RealtimeScreenEvidenceCaptureFailure: String, Equatable, Sendable {
  case screenRecordingPermissionRequired = "screen_recording_permission_required"
  case captureUnavailable = "capture_unavailable"
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
  /// Present only when the PTT-bound physical capture could not produce pixels.
  /// This is bounded capability state, never a description of the user's screen.
  let captureFailure: RealtimeScreenEvidenceCaptureFailure?

  init(
    evidenceID: String,
    turnID: VoiceTurnID,
    capturedAt: Date,
    target: RealtimeScreenEvidenceTarget,
    frontmostApp: String?,
    frontmostBundleID: String?,
    windowID: UInt32?,
    displayID: UInt32?,
    imageByteCount: Int,
    imageDigest: String?,
    captureFailure: RealtimeScreenEvidenceCaptureFailure? = nil
  ) {
    self.evidenceID = evidenceID
    self.turnID = turnID
    self.capturedAt = capturedAt
    self.target = target
    self.frontmostApp = frontmostApp
    self.frontmostBundleID = frontmostBundleID
    self.windowID = windowID
    self.displayID = displayID
    self.imageByteCount = imageByteCount
    self.imageDigest = imageDigest
    self.captureFailure = captureFailure
  }

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

/// A PTT-down image is current-screen authority only for a short, bounded interval. Freshness
/// is checked at the physical-capture → provider-transport boundary: after the exact immutable
/// JPEG is locally enqueued while fresh, provider reasoning latency cannot retroactively turn
/// that already-authorized image into a different screen observation.
enum RealtimeScreenEvidenceFreshnessPolicy {
  static let maximumAge: TimeInterval = 5

  static func isFresh(_ descriptor: RealtimeScreenEvidenceDescriptor, now: Date) -> Bool {
    let age = now.timeIntervalSince(descriptor.capturedAt)
    return age >= 0 && age < maximumAge
  }

  static func remainingLifetime(_ descriptor: RealtimeScreenEvidenceDescriptor, now: Date) -> TimeInterval {
    max(0, descriptor.capturedAt.addingTimeInterval(maximumAge).timeIntervalSince(now))
  }
}

/// The report half of an already-admitted screen protocol has its own bounded deadline. This is
/// intentionally separate from capture freshness: the provider must be given time to inspect the
/// JPEG that was dispatched while fresh, but a missing report still cannot hold a PTT turn open.
enum RealtimeScreenEvidenceProtocolPolicy {
  static let maximumReportWait: TimeInterval = 8
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
  /// A screenshot was admitted for the current provider turn, but its frozen JPEG has not yet
  /// been handed to the provider. Suppress speculative provider output only from this point.
  case awaitingScreenshot(RealtimeScreenScreenshotRequest)
  /// The exact JPEG tool result was locally dispatched to the active provider session. A model
  /// report can now be presented only through this immutable local receipt.
  case awaitingReport(RealtimeScreenObservationReceipt)
  case accepted(RealtimeScreenObservationReceipt)
  /// Retain the token only long enough to let a physical screenshot tool result
  /// finish its already-authorized wire send after native lifecycle completion.
  case rejected(RealtimeScreenEvidenceDescriptor?, VoiceScreenEvidenceProtocolToken)

  var suppressesProviderOutput: Bool {
    switch self {
    // Before the provider proves it used the one current screenshot, any output can
    // be speculative or stale. Once the report is accepted, however, the next model
    // message is precisely the grounded answer we must surface; keeping the gate
    // closed there turns a successful verification into a silent PTT turn.
    case .awaitingScreenshot, .awaitingReport, .rejected:
      return true
    case .inactive, .accepted:
      return false
    }
  }

  var protocolToken: VoiceScreenEvidenceProtocolToken? {
    switch self {
    case .awaitingScreenshot(let request):
      return request.protocolToken
    case .awaitingReport(let receipt), .accepted(let receipt):
      return receipt.protocolToken
    case .inactive:
      return nil
    case .rejected(_, let token):
      return token
    }
  }

  /// Safe, bounded state for the automation bridge. It deliberately excludes raw evidence IDs,
  /// app names, captured pixels, and model text so a failed PTT turn can be diagnosed remotely.
  var diagnosticsLabel: String {
    switch self {
    case .inactive: return "inactive"
    case .awaitingScreenshot: return "awaiting_screenshot"
    case .awaitingReport: return "awaiting_report"
    case .accepted: return "accepted"
    case .rejected: return "rejected"
    }
  }
}

/// Screen-evidence completion must never silently leave the reducer-owned screenshot tool
/// pending. Keep each fail-closed reason typed so the live PTT probe can distinguish a provider
/// stall from an ownership or reducer transition failure without exposing user content.
enum RealtimeScreenEvidenceProtocolCompletion: String, Equatable, Sendable {
  case notRun = "not_run"
  case completed
  case turnNotActive = "turn_not_active"
  case protocolNotActive = "protocol_not_active"
  case ownerNotCurrent = "owner_not_current"
  case emptyAnswer = "empty_answer"
  case reducerDidNotResolve = "reducer_did_not_resolve"
}

/// A screenshot request belongs to one provider response and one tool epoch. The model never
/// supplies this authority: it is minted after reducer admission and checked again after every
/// asynchronous boundary.
struct RealtimeScreenScreenshotRequest: Equatable {
  let descriptor: RealtimeScreenEvidenceDescriptor?
  let turnID: VoiceTurnID
  let responseID: VoiceResponseID
  let sessionObjectID: ObjectIdentifier
  let screenshotCallID: String
  let protocolToken: VoiceScreenEvidenceProtocolToken
  let turnEpoch: Int

  func acceptsTransportDispatch(
    attachment: RealtimeScreenEvidenceAttachment,
    sourceObjectID: ObjectIdentifier,
    activeTurnID: VoiceTurnID?,
    activeResponseID: VoiceResponseID?,
    currentTurnEpoch: Int,
    callID: String
  ) -> Bool {
    descriptor?.evidenceID == attachment.descriptor.evidenceID
      && descriptor?.turnID == attachment.descriptor.turnID
      && turnID == activeTurnID
      && responseID == activeResponseID
      && sessionObjectID == sourceObjectID
      && screenshotCallID == callID
      && turnEpoch == currentTurnEpoch
  }
}

/// This is a local transport-enqueue receipt, not a provider delivery acknowledgement. It proves
/// that the session accepted the matching JPEG function-result wire for this exact active turn; a
/// report cannot use model-supplied ids or application labels to recreate that authority.
struct RealtimeScreenObservationReceipt: Equatable {
  let descriptor: RealtimeScreenEvidenceDescriptor
  let turnID: VoiceTurnID
  let responseID: VoiceResponseID
  let sessionObjectID: ObjectIdentifier
  let screenshotCallID: String
  let protocolToken: VoiceScreenEvidenceProtocolToken
  let turnEpoch: Int

  init(request: RealtimeScreenScreenshotRequest, descriptor: RealtimeScreenEvidenceDescriptor) {
    self.descriptor = descriptor
    turnID = request.turnID
    responseID = request.responseID
    sessionObjectID = request.sessionObjectID
    screenshotCallID = request.screenshotCallID
    protocolToken = request.protocolToken
    turnEpoch = request.turnEpoch
  }

  func isCurrent(
    sourceObjectID: ObjectIdentifier,
    activeTurnID: VoiceTurnID?,
    activeResponseID: VoiceResponseID?,
    currentTurnEpoch: Int
  ) -> Bool {
    descriptor.canVerifyCurrentScreen
      && turnID == activeTurnID
      && responseID == activeResponseID
      && sessionObjectID == sourceObjectID
      && !screenshotCallID.isEmpty
      && turnEpoch == currentTurnEpoch
  }
}

enum RealtimeScreenReportDecision: Equatable {
  case accepted
  case evidenceUnavailable
  case transportNotDispatched
  case staleReceipt
  case contradictoryApplication
  case emptyAnswer
}

/// Transport enqueue is the first of two freshness boundaries. Keep expiry distinct from an
/// ownership mismatch so the current turn fails closed immediately, while a stale callback from
/// an old turn stays a no-op.
enum RealtimeScreenTransportEnqueueDecision: Equatable {
  case accepted(RealtimeScreenObservationReceipt)
  case notAdmitted
  case evidenceExpired(RealtimeScreenEvidenceDescriptor)
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
enum RealtimeScreenEvidenceFailureDisposition: Equatable {
  /// The provider received a recoverable tool error and should answer in its
  /// normal native voice lane (for example, by offering Screen Recording or
  /// explaining that the current screen was temporarily unavailable).
  case providerContinuation
  /// No provider continuation can safely explain the failure, so the local
  /// deterministic result remains the terminal answer.
  case authoritativeLocalResult
}

enum RealtimeScreenGroundingPolicy {
  static func failureDisposition(
    for evidence: RealtimeScreenEvidenceDescriptor?
  ) -> RealtimeScreenEvidenceFailureDisposition {
    switch evidence?.captureFailure {
    case .screenRecordingPermissionRequired, .captureUnavailable:
      // Screen Recording can be granted while the compositor is still
      // initializing. That must degrade the visual tool result, never consume
      // the user's PTT turn or replace native voice with a local terminal path.
      return .providerContinuation
    case nil:
      return .authoritativeLocalResult
    }
  }

  static func failureText(for evidence: RealtimeScreenEvidenceDescriptor?) -> String {
    guard evidence?.captureFailure == .screenRecordingPermissionRequired else {
      return "I couldn't verify the current screen."
    }
    return
      "I need Screen Recording permission before I can view your screen. Say ‘grant it’ and I’ll open the permission request."
  }

  /// Mints the local presentation receipt only after the session reports that it accepted the
  /// exact image/function-response wire. The caller owns waiting for that asynchronous transport
  /// event; this pure transition protects against stale callbacks after barge-in or replacement.
  static func receiptAfterTransportEnqueued(
    state: RealtimeScreenGroundingState,
    attachment: RealtimeScreenEvidenceAttachment,
    sourceObjectID: ObjectIdentifier,
    activeTurnID: VoiceTurnID?,
    activeResponseID: VoiceResponseID?,
    currentTurnEpoch: Int,
    enqueuedTurnEpoch: Int,
    callID: String,
    now: Date = Date()
  ) -> RealtimeScreenTransportEnqueueDecision {
    guard enqueuedTurnEpoch == currentTurnEpoch,
      case .awaitingScreenshot(let request) = state,
      request.acceptsTransportDispatch(
        attachment: attachment,
        sourceObjectID: sourceObjectID,
        activeTurnID: activeTurnID,
        activeResponseID: activeResponseID,
        currentTurnEpoch: currentTurnEpoch,
        callID: callID)
    else { return .notAdmitted }
    guard RealtimeScreenEvidenceFreshnessPolicy.isFresh(attachment.descriptor, now: now) else {
      return .evidenceExpired(attachment.descriptor)
    }
    return .accepted(RealtimeScreenObservationReceipt(request: request, descriptor: attachment.descriptor))
  }

  static func reportDecision(
    state: RealtimeScreenGroundingState,
    observation: String,
    sourceObjectID: ObjectIdentifier,
    activeTurnID: VoiceTurnID?,
    activeResponseID: VoiceResponseID?,
    currentTurnEpoch: Int,
    now _: Date = Date()
  ) -> RealtimeScreenReportDecision {
    guard case .awaitingReport(let receipt) = state else {
      return .evidenceUnavailable
    }
    let evidence = receipt.descriptor
    guard evidence.canVerifyCurrentScreen else { return .transportNotDispatched }
    guard
      receipt.isCurrent(
        sourceObjectID: sourceObjectID,
        activeTurnID: activeTurnID,
        activeResponseID: activeResponseID,
        currentTurnEpoch: currentTurnEpoch)
    else { return .staleReceipt }
    guard !observation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return .emptyAnswer }
    guard
      !observationClaimsDifferentApplication(
        observation,
        frontmostApp: evidence.frontmostApp ?? "")
    else { return .contradictoryApplication }
    return .accepted
  }

  /// The native descriptor—not model prose—owns application identity. The model can supply
  /// a visual grounding observation, but one that directly claims a different active app fails
  /// closed before the provider continues to its conversational answer.
  private static func observationClaimsDifferentApplication(
    _ observation: String,
    frontmostApp: String
  ) -> Bool {
    let normalizedObservation = RealtimeScreenEvidenceDescriptor.normalizedAppName(observation)
    let normalizedFrontmost = RealtimeScreenEvidenceDescriptor.normalizedAppName(frontmostApp)
    let commonDesktopApps = [
      "cursor", "codex", "xcode", "finder", "terminal", "safari", "google chrome",
      "visual studio code", "vs code", "slack", "notion", "figma",
    ]
    // The frozen descriptor is the only app identity that belongs to this receipt.
    // Sampling the current process list here made a valid capture depend on a later
    // focus change, which is the same ambient-state leak this protocol exists to avoid.
    let candidates = Set(
      commonDesktopApps
        .map(RealtimeScreenEvidenceDescriptor.normalizedAppName)
        .filter { !$0.isEmpty && $0 != normalizedFrontmost })
    // Only reject a direct statement about which app is foreground. A screenshot description
    // naturally says things such as "application windows" or can mention an app visible inside
    // content; neither statement contradicts the native frontmost-app fact. This guard protects
    // the report's grounding role without constraining the provider's later conversational answer.
    let foregroundClaimPrefixes = [
      "you are in ", "you're in ", "currently in ",
      "frontmost app is ", "frontmost application is ",
      "active app is ", "active application is ",
    ]
    return candidates.contains { candidate in
      foregroundClaimPrefixes.contains { prefix in
        normalizedObservation.contains(prefix + candidate)
      }
    }
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
    let captureFailure: RealtimeScreenEvidenceCaptureFailure?
    let image: CGImage?
    if !CGPreflightScreenCaptureAccess() {
      log("RealtimeScreenEvidenceCapture: Screen Recording permission not granted at PTT capture")
      image = nil
      captureFailure = .screenRecordingPermissionRequired
    } else {
      image = displayID.flatMap { ScreenCaptureManager.captureScreenImage(displayID: $0) }
      captureFailure = image == nil ? .captureUnavailable : nil
    }
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
      imageDigest: nil,
      captureFailure: captureFailure
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
      imageDigest: sha256(jpeg),
      captureFailure: evidence.descriptor.captureFailure
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
    guard
      let windows = CGWindowListCopyWindowInfo(
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
