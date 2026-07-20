import Foundation

enum ScreenCaptureHealth: String, Equatable {
  case active
  case temporarilyUnavailable
  case recovering
  case stopped

  var statusText: String {
    switch self {
    case .active:
      return "Capturing screen content"
    case .temporarilyUnavailable:
      return "Capture paused: current window can’t be captured"
    case .recovering:
      return "Capture paused: recovering screen capture"
    case .stopped:
      return "Screen capture is paused"
    }
  }

  var rewindBadgeText: String? {
    switch self {
    case .active, .stopped:
      return nil
    case .temporarilyUnavailable:
      return "Capture paused"
    case .recovering:
      return "Recovering"
    }
  }

  var rewindToggleHelp: String {
    switch self {
    case .active:
      return "Rewind is capturing - click to stop"
    case .temporarilyUnavailable:
      return "Rewind is on, but the current window cannot be captured"
    case .recovering:
      return "Rewind is recovering screen capture"
    case .stopped:
      return "Rewind is off - click to start capturing"
    }
  }
}

struct ScreenCaptureFailureTracker {
  private(set) var consecutiveEngineFailures = 0

  mutating func recordCaptureSuccess() -> Int {
    let previousFailures = consecutiveEngineFailures
    consecutiveEngineFailures = 0
    return previousFailures
  }

  mutating func recordTargetUnavailable() {
    consecutiveEngineFailures = 0
  }

  mutating func recordEngineFailure() -> Int {
    consecutiveEngineFailures += 1
    return consecutiveEngineFailures
  }

  mutating func reset() {
    consecutiveEngineFailures = 0
  }
}

enum ProactiveAssistantOrchestrationPolicy {
  enum ScreenshotAppDecision: Equatable {
    case pause(backoffUntil: Date)
    case resumeIntoBackoff
    case resumeAndCapture
    case continueBackoff
    case capture
  }

  enum VideoCallThrottleDecision: Equatable {
    case capture(nextCounter: Int, didLeaveCall: Bool)
    case skip(nextCounter: Int, didEnterCall: Bool)
  }

  enum DistributionDecision: Equatable {
    case flushNow
    case debounce
    case skip
  }

  static func shouldRecheckPermission(
    now: Date,
    lastCheckTime: Date,
    interval: TimeInterval
  ) -> Bool {
    now.timeIntervalSince(lastCheckTime) >= interval
  }

  static func screenshotAppDecision(
    isScreenshotAppFrontmost: Bool,
    wasScreenshotAppFrontmost: Bool,
    backoffUntil: Date,
    now: Date,
    backoffDuration: TimeInterval
  ) -> ScreenshotAppDecision {
    if isScreenshotAppFrontmost {
      return .pause(backoffUntil: now.addingTimeInterval(backoffDuration))
    }

    if wasScreenshotAppFrontmost {
      return now < backoffUntil ? .resumeIntoBackoff : .resumeAndCapture
    }

    if now < backoffUntil {
      return .continueBackoff
    }

    return .capture
  }

  static func videoCallThrottleDecision(
    isVideoCall: Bool,
    currentCounter: Int,
    throttleFactor: Int
  ) -> VideoCallThrottleDecision {
    guard throttleFactor > 1 else {
      return .capture(nextCounter: 0, didLeaveCall: !isVideoCall && currentCounter > 0)
    }

    if isVideoCall {
      let nextCounter = currentCounter + 1
      if nextCounter < throttleFactor {
        return .skip(nextCounter: nextCounter, didEnterCall: nextCounter == 1)
      }
      return .capture(nextCounter: 0, didLeaveCall: false)
    }

    return .capture(nextCounter: 0, didLeaveCall: currentCounter > 0)
  }

  static func distributionDecision(
    lastDistributedApp: String?,
    lastDistributedWindowTitle: String?,
    frameApp: String,
    frameWindowTitle: String?,
    lastDistributionTime: Date,
    now: Date,
    defaultFallbackInterval: TimeInterval,
    messagingFallbackInterval: TimeInterval,
    messagingFastPathApps: Set<String>
  ) -> DistributionDecision {
    guard lastDistributedApp != nil else {
      return .flushNow
    }

    if ContextDetection.didContextChange(
      fromApp: lastDistributedApp,
      fromWindowTitle: lastDistributedWindowTitle,
      toApp: frameApp,
      toWindowTitle: frameWindowTitle
    ) {
      return .debounce
    }

    let fallbackInterval =
      messagingFastPathApps.contains(frameApp)
      ? messagingFallbackInterval
      : defaultFallbackInterval
    return now.timeIntervalSince(lastDistributionTime) >= fallbackInterval ? .flushNow : .skip
  }
}

struct ProactiveScreenshotCaptureGate {
  private(set) var wasScreenshotAppFrontmost = false
  private(set) var backoffUntil: Date = .distantPast

  mutating func nextDecision(
    isScreenshotAppFrontmost: Bool,
    now: Date,
    backoffDuration: TimeInterval
  ) -> ProactiveAssistantOrchestrationPolicy.ScreenshotAppDecision {
    let decision = ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
      isScreenshotAppFrontmost: isScreenshotAppFrontmost,
      wasScreenshotAppFrontmost: wasScreenshotAppFrontmost,
      backoffUntil: backoffUntil,
      now: now,
      backoffDuration: backoffDuration
    )

    switch decision {
    case .pause(let nextBackoffUntil):
      wasScreenshotAppFrontmost = true
      backoffUntil = nextBackoffUntil
    case .resumeIntoBackoff, .resumeAndCapture:
      wasScreenshotAppFrontmost = false
    case .continueBackoff, .capture:
      break
    }

    return decision
  }

  mutating func reset() {
    wasScreenshotAppFrontmost = false
    backoffUntil = .distantPast
  }
}

struct ProactiveVideoCallThrottleGate {
  private(set) var counter = 0

  mutating func nextDecision(
    isVideoCall: Bool,
    throttleFactor: Int
  ) -> ProactiveAssistantOrchestrationPolicy.VideoCallThrottleDecision {
    let decision = ProactiveAssistantOrchestrationPolicy.videoCallThrottleDecision(
      isVideoCall: isVideoCall,
      currentCounter: counter,
      throttleFactor: throttleFactor
    )

    switch decision {
    case .capture(let nextCounter, _), .skip(let nextCounter, _):
      counter = nextCounter
    }

    return decision
  }

  mutating func reset() {
    counter = 0
  }
}

struct ProactiveFrameDistributionGate {
  enum Action: Equatable {
    case flushNow
    case scheduleDebounce
    case skip
  }

  private(set) var lastDistributedApp: String?
  private(set) var lastDistributedWindowTitle: String?
  private(set) var lastDistributionTime: Date = .distantPast

  mutating func reset() {
    lastDistributedApp = nil
    lastDistributedWindowTitle = nil
    lastDistributionTime = .distantPast
  }

  mutating func nextAction(
    frameApp: String,
    frameWindowTitle: String?,
    now: Date,
    defaultFallbackInterval: TimeInterval,
    messagingFallbackInterval: TimeInterval,
    messagingFastPathApps: Set<String>
  ) -> Action {
    let decision = ProactiveAssistantOrchestrationPolicy.distributionDecision(
      lastDistributedApp: lastDistributedApp,
      lastDistributedWindowTitle: lastDistributedWindowTitle,
      frameApp: frameApp,
      frameWindowTitle: frameWindowTitle,
      lastDistributionTime: lastDistributionTime,
      now: now,
      defaultFallbackInterval: defaultFallbackInterval,
      messagingFallbackInterval: messagingFallbackInterval,
      messagingFastPathApps: messagingFastPathApps
    )

    switch decision {
    case .flushNow:
      return .flushNow
    case .debounce:
      // Track the pending context immediately so repeated captures in that same
      // context do not starve the debounce timer by rescheduling forever.
      lastDistributedApp = frameApp
      lastDistributedWindowTitle = frameWindowTitle
      return .scheduleDebounce
    case .skip:
      return .skip
    }
  }

  mutating func markFlushed(
    frameApp: String,
    frameWindowTitle: String?,
    at time: Date
  ) {
    lastDistributedApp = frameApp
    lastDistributedWindowTitle = frameWindowTitle
    lastDistributionTime = time
  }
}

/// Gating policy for the screen-capture loop. The goal is to avoid taking a
/// full screenshot on a fixed cadence when nothing has changed. Instead, the
/// loop polls cheap signals (idle time, active app/window) at a fast rate and
/// only proceeds to a full capture when the user context changes or a heartbeat
/// interval elapses. For heartbeat ticks it can request a cheap preview capture
/// whose hash is compared to the last preview, so static screens are skipped.
struct ProactiveCaptureTrigger {
  enum Decision: Equatable {
    /// Do not capture this tick.
    case skip
    /// Capture a small preview and only proceed if its hash differs.
    case preview
    /// Perform a full capture immediately.
    case capture
  }

  private let idleThreshold: TimeInterval
  private var heartbeatInterval: TimeInterval
  private let appSwitchDebounce: TimeInterval

  private var lastApp: String?
  private var lastWindowTitle: String?
  private var lastCaptureTime: Date = .distantPast
  private var lastPreviewHash: UInt64?
  private var appSwitchRequest: (app: String, title: String?, time: Date)?

  init(
    idleThreshold: TimeInterval,
    heartbeatInterval: TimeInterval,
    appSwitchDebounce: TimeInterval = 0.5
  ) {
    self.idleThreshold = idleThreshold
    self.heartbeatInterval = heartbeatInterval
    self.appSwitchDebounce = appSwitchDebounce
  }

  mutating func reset() {
    lastApp = nil
    lastWindowTitle = nil
    lastCaptureTime = .distantPast
    lastPreviewHash = nil
    appSwitchRequest = nil
  }

  /// Record that an app-switch notification fired. The trigger debounces rapid
  /// switches and evaluates the next poll as a capture candidate.
  mutating func requestAppSwitchCapture(app: String, at time: Date) {
    appSwitchRequest = (app, nil, time)
  }

  /// Decide whether the next poll should skip, preview, or capture.
  mutating func nextDecision(
    app: String,
    windowTitle: String?,
    idleSeconds: TimeInterval,
    now: Date
  ) -> Decision {
    if idleSeconds >= idleThreshold {
      // User is idle: keep last context but do not capture.
      return .skip
    }

    // A pending app-switch request suppresses capture until its debounce passes,
    // then the normal context-change/heartbeat logic takes over.
    if let request = appSwitchRequest {
      if now.timeIntervalSince(request.time) < appSwitchDebounce {
        return .skip
      }
      appSwitchRequest = nil
    }

    // If the active context changed, capture immediately.
    if ContextDetection.didContextChange(
      fromApp: lastApp, fromWindowTitle: lastWindowTitle, toApp: app, toWindowTitle: windowTitle
    ) {
      lastApp = app
      lastWindowTitle = windowTitle
      lastCaptureTime = now
      return .capture
    }

    // Same context: only sample on heartbeat.
    if now.timeIntervalSince(lastCaptureTime) >= heartbeatInterval {
      return .preview
    }

    return .skip
  }

  mutating func updateHeartbeatInterval(_ interval: TimeInterval) {
    heartbeatInterval = interval
  }

  mutating func markCaptured(
    app: String,
    windowTitle: String?,
    at time: Date,
    previewHash: UInt64? = nil
  ) {
    lastApp = app
    lastWindowTitle = windowTitle
    lastCaptureTime = time
    if let previewHash = previewHash {
      lastPreviewHash = previewHash
    }
  }

  mutating func markPreviewHash(_ hash: UInt64) {
    lastPreviewHash = hash
  }

  func isPreviewUnchanged(_ hash: UInt64, threshold: Int) -> Bool {
    guard let last = lastPreviewHash else { return false }
    return (hash ^ last).nonzeroBitCount <= threshold
  }
}
