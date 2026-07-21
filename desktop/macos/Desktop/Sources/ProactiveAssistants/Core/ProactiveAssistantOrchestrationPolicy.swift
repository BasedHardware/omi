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
/// interval elapses. For heartbeat ticks it captures a tiny preview and computes
/// a similarity index against recent previews, so static or cycling screens are
/// skipped without a full screenshot.
struct ProactiveCaptureTrigger {
  enum Decision: Equatable {
    /// Do not capture this tick.
    case skip
    /// Capture a small preview and only proceed if its similarity index is low.
    case preview
    /// Perform a full capture immediately.
    case capture
  }

  let idleThreshold: TimeInterval
  private var heartbeatInterval: TimeInterval
  private let appSwitchDebounce: TimeInterval
  private let previewHistoryCapacity: Int
  private let maxHeartbeatMultiplier: Double
  private let heartbeatGrowthPerSimilarPreview: Double

  private var lastApp: String?
  private var lastWindowTitle: String?
  private var lastCaptureTime: Date = .distantPast
  private var previewHashHistory: [UInt64] = []
  private var consecutiveSimilarPreviews: Int = 0
  private var appSwitchRequest: (app: String, title: String?, time: Date)?

  init(
    idleThreshold: TimeInterval,
    heartbeatInterval: TimeInterval,
    appSwitchDebounce: TimeInterval = 0.5,
    previewHistoryCapacity: Int = 3,
    maxHeartbeatMultiplier: Double = 2.0,
    heartbeatGrowthPerSimilarPreview: Double = 0.5
  ) {
    self.idleThreshold = idleThreshold
    self.heartbeatInterval = heartbeatInterval
    self.appSwitchDebounce = appSwitchDebounce
    self.previewHistoryCapacity = previewHistoryCapacity
    self.maxHeartbeatMultiplier = maxHeartbeatMultiplier
    self.heartbeatGrowthPerSimilarPreview = heartbeatGrowthPerSimilarPreview
  }

  mutating func reset() {
    lastApp = nil
    lastWindowTitle = nil
    lastCaptureTime = .distantPast
    previewHashHistory.removeAll()
    consecutiveSimilarPreviews = 0
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
      consecutiveSimilarPreviews = 0
      return .capture
    }

    // Same context: only sample on heartbeat. The heartbeat interval grows when
    // recent previews are all similar, so static screens are probed less often.
    if now.timeIntervalSince(lastCaptureTime) >= effectiveHeartbeatInterval {
      return .preview
    }

    return .skip
  }

  private var effectiveHeartbeatInterval: TimeInterval {
    let multiplier = min(
      maxHeartbeatMultiplier,
      1.0 + Double(consecutiveSimilarPreviews) * heartbeatGrowthPerSimilarPreview)
    return heartbeatInterval * multiplier
  }

  mutating func updateHeartbeatInterval(_ interval: TimeInterval) {
    heartbeatInterval = interval
    consecutiveSimilarPreviews = 0
  }

  mutating func markCaptured(
    app: String,
    windowTitle: String?,
    at time: Date,
    frameHash: UInt64? = nil
  ) {
    lastApp = app
    lastWindowTitle = windowTitle
    lastCaptureTime = time
    consecutiveSimilarPreviews = 0
    if let frameHash = frameHash {
      recordPreviewHash(frameHash, at: time)
    }
  }

  mutating func recordPreviewHash(_ hash: UInt64, at time: Date) {
    previewHashHistory.append(hash)
    if previewHashHistory.count > previewHistoryCapacity {
      previewHashHistory.removeFirst(previewHashHistory.count - previewHistoryCapacity)
    }
    lastCaptureTime = time
    consecutiveSimilarPreviews = 0
  }

  mutating func markPreviewSkipped(at time: Date, similarity: Double, threshold: Double) {
    lastCaptureTime = time
    if similarity >= threshold {
      consecutiveSimilarPreviews += 1
    } else {
      consecutiveSimilarPreviews = 0
    }
  }

  /// Similarity index between a preview hash and the recent preview history.
  /// Returns 1.0 for an exact match and 0.0 for a completely different 64-bit
  /// hash. The index uses Hamming distance over the dHash output.
  func previewSimilarity(to hash: UInt64) -> Double {
    guard !previewHashHistory.isEmpty else { return 0.0 }
    let maxDistance = Double(UInt64.bitWidth)  // 64
    var best = 0.0
    for previous in previewHashHistory {
      let distance = (hash ^ previous).nonzeroBitCount
      let similarity = 1.0 - Double(distance) / maxDistance
      if similarity > best {
        best = similarity
      }
    }
    return best
  }

  /// Returns true when the preview is similar enough to a recent preview that
  /// the full capture can be skipped.
  func shouldSkipPreview(_ hash: UInt64, similarityThreshold: Double) -> Bool {
    previewSimilarity(to: hash) >= similarityThreshold
  }
}

/// Per-app preview-similarity thresholds for heartbeat dedupe.
/// Similarity ≥ threshold → skip full capture.
/// Higher = only near-identical frames skip (catch small edits).
/// Lower = tolerate noisy pixel churn (games/media/social).
///
/// Tiers (chosen for 80px dHash noise):
/// - 0.98 notes/docs:  ~1 bit of 64 may flip from cursor/scroll chrome; keep edits
/// - 0.96 code/IDE:    text dense but gutter/minimap/status tick often
/// - 0.95 default:     generic desktop apps
/// - 0.92 chat:        avatars/typing/unread badges pulse
/// - 0.90 browser:     tab strip/favicon/network chrome noise; site title can raise/lower
/// - 0.88 media player: artwork/progress bar animates
/// - 0.85 social web:  feeds/autoplay thumbs thrash
/// - 0.82 games:       near-constant pixel motion; keep sparse keyframes only
enum PreviewSimilarityThresholdPolicy {
  // Similarity ≥ threshold → skip full capture.
  // Higher = only near-identical frames skip (catch small edits).
  // Lower = tolerate noisy pixel churn (games/media/social).
  //
  // Tiers for ~80px dHash noise:
  // 0.98 notes/docs   ~1/64 bit may flip from cursor chrome; keep text edits
  // 0.96 code/IDE     dense text; gutter/minimap/status tick often
  // 0.95 default      generic desktop apps
  // 0.92 chat         avatars/typing/unread badges pulse
  // 0.90 browser      tab strip/favicon noise; window title can raise/lower
  // 0.88 media        artwork/progress bar animates
  // 0.85 social web   feeds/autoplay thumbs thrash
  // 0.82 games        near-constant motion; sparse keyframes only
  static let notes: Double = 0.98
  static let code: Double = 0.96
  static let `default`: Double = 0.95
  static let chat: Double = 0.92
  static let browser: Double = 0.90
  static let media: Double = 0.88
  static let social: Double = 0.85
  static let game: Double = 0.82

  private static let noteBundleIDs: Set<String> = [
    "com.apple.notes",
    "com.apple.iwork.pages",
    "com.apple.textedit",
    "com.microsoft.word",
    "com.microsoft.onenote.mac",
    "md.obsidian",
    "notion.id",
    "com.lukilabs.lukiapp",
    "com.culturedcode.thingsmac",
    "com.apple.ibooksx",
    "com.apple.preview",
    "com.bear-writer.bear",
    "com.ugmanny.ia-writer-mac",
    "com.ulyssesapp.mac",
  ]
  private static let noteAppNames: Set<String> = [
    "Notes", "Pages", "TextEdit", "Microsoft Word", "OneNote",
    "Obsidian", "Notion", "Craft", "Things", "Books", "Preview",
    "Bear", "iA Writer", "Ulysses",
  ]

  private static let codeBundleIDs: Set<String> = [
    "com.microsoft.vscode",
    "com.microsoft.vscodeinsiders",
    "com.apple.dt.xcode",
    "com.googlecode.iterm2",
    "com.apple.terminal",
    "net.kovidgoyal.kitty",
    "com.github.wez.wezterm",
    "dev.warp.warp-stable",
    "com.sublimetext.4",
    "com.panic.nova",
    "com.jetbrains.intellij",
    "com.jetbrains.pycharm",
    "com.jetbrains.webstorm",
    "com.jetbrains.goland",
    "com.jetbrains.clion",
    "com.jetbrains.datagrip",
  ]
  private static let codeAppNames: Set<String> = [
    "Code", "Visual Studio Code", "Xcode", "iTerm2", "Terminal",
    "kitty", "WezTerm", "Warp", "Sublime Text", "Nova",
    "IntelliJ IDEA", "PyCharm", "WebStorm", "GoLand", "CLion", "DataGrip",
  ]

  private static let chatBundleIDs: Set<String> = [
    "com.tinyspeck.slackmacgap",
    "com.hnc.discord",
    "ru.keepcoder.telegram",
    "net.whatsapp.whatsapp",
    "com.apple.mobilesms",
    "com.microsoft.teams2",
    "com.microsoft.teams",
    "com.apple.facetime",
  ]
  private static let chatAppNames: Set<String> = [
    "Slack", "Discord", "Telegram", "WhatsApp", "Messages",
    "Microsoft Teams", "FaceTime",
  ]

  private static let mediaBundleIDs: Set<String> = [
    "com.apple.music", "com.apple.podcasts", "com.apple.tv",
    "com.apple.photos", "com.spotify.client", "com.apple.ibooks",
    "com.apple.quicktimeplayerx", "com.colliderli.iina", "org.videolan.vlc",
  ]
  private static let mediaAppNames: Set<String> = [
    "Music", "Podcasts", "TV", "Photos", "Spotify", "Books",
    "QuickTime Player", "IINA", "VLC",
  ]

  private static let gameBundleIDPrefixes: [String] = [
    "com.valvesoftware", "com.epicgames", "com.blizzard", "com.ea.",
    "com.riotgames", "com.unity.", "com.apple.chess",
  ]
  private static let gameAppNames: Set<String> = [
    "Steam", "Chess", "Minecraft", "League of Legends", "Fortnite",
  ]

  /// Resolve skip threshold for the frontmost app.
  /// Browser titles can raise (docs) or lower (video/social/game sites).
  static func threshold(
    bundleID: String?,
    appName: String?,
    windowTitle: String? = nil
  ) -> Double {
    let bid = (bundleID ?? "").lowercased()
    let name = appName ?? ""

    if isGame(bundleID: bid, appName: name) { return game }
    if isMedia(bundleID: bid, appName: name) { return media }
    if isChat(bundleID: bid, appName: name) { return chat }
    if isCode(bundleID: bid, appName: name) { return code }
    if isNote(bundleID: bid, appName: name) { return notes }

    if isBrowser(bundleID: bid, appName: name) {
      return browserThreshold(windowTitle: windowTitle)
    }
    return `default`
  }

  private static func isBrowser(bundleID: String, appName: String) -> Bool {
    if !bundleID.isEmpty, ConferencingApps.isBrowserBundleID(bundleID) { return true }
    return ConferencingApps.browserApps.contains(appName)
      || TaskAssistantSettings.isBrowser(appName)
  }

  private static func isNote(bundleID: String, appName: String) -> Bool {
    if noteBundleIDs.contains(bundleID) { return true }
    return noteAppNames.contains(appName)
  }

  private static func isCode(bundleID: String, appName: String) -> Bool {
    if codeBundleIDs.contains(bundleID) { return true }
    return codeAppNames.contains(appName)
  }

  private static func isChat(bundleID: String, appName: String) -> Bool {
    if chatBundleIDs.contains(bundleID) { return true }
    return chatAppNames.contains(appName)
  }

  private static func isMedia(bundleID: String, appName: String) -> Bool {
    if mediaBundleIDs.contains(bundleID) { return true }
    return mediaAppNames.contains(appName)
  }

  private static func isGame(bundleID: String, appName: String) -> Bool {
    if gameBundleIDPrefixes.contains(where: { bundleID.hasPrefix($0) }) { return true }
    return gameAppNames.contains(appName)
  }

  private static func browserThreshold(windowTitle: String?) -> Double {
    guard let title = windowTitle?.lowercased(), !title.isEmpty else { return browser }

    let noteSignals = [
      "docs.google.com", "sheets.google.com", "slides.google.com",
      "notion.so", "notion.site", "obsidian.md", "roamresearch.com",
      "coda.io", "paper.dropbox.com", "evernote.com",
      "google docs", "google sheets", "google slides",
      "confluence", "hackmd.io", "dropbox paper",
      "overleaf.com", "quip.com",
    ]
    if noteSignals.contains(where: { title.contains($0) }) { return notes }

    let codeSignals = [
      "github.com", "gitlab.com", "bitbucket.org", "sourceforge.net",
      "linear.app", "figma.com", "miro.com", "whimsical.com",
      "codesandbox.io", "replit.com", "stackblitz.com",
      "jira", "atlassian.net",
    ]
    if codeSignals.contains(where: { title.contains($0) }) { return code }

    let chatSignals = [
      "mail.google.com", "outlook.live.com", "outlook.office",
      "app.slack.com", "discord.com", "web.whatsapp.com",
      "web.telegram.org", "teams.microsoft.com", "chat.google.com",
      "messages.google.com",
    ]
    if chatSignals.contains(where: { title.contains($0) }) { return chat }

    let socialSignals = [
      "twitter.com", "x.com", "instagram.com", "tiktok.com",
      "reddit.com", "facebook.com", "linkedin.com", "news.ycombinator.com",
    ]
    if socialSignals.contains(where: { title.contains($0) }) { return social }

    let thrashSignals = [
      "youtube.com", "youtu.be", "netflix.com", "twitch.tv",
      "disneyplus.com", "hulu.com", "spotify.com", "music.apple.com",
      "steamcommunity.com", "store.steampowered.com",
      "epicgames.com", "roblox.com", "chess.com", "lichess.org",
    ]
    if thrashSignals.contains(where: { title.contains($0) }) { return game }

    return browser
  }
}
