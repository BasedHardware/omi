import Foundation

// MARK: - Time (JS toISOString wire shape)

enum ScreenTime {
  /// UTC instant matching `Date.prototype.toISOString()` (always milliseconds + Z).
  static func wireTimestamp(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
    return formatter.string(from: date)
  }

  static func parse(_ text: String) -> Date? {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
    if let date = formatter.date(from: text) { return date }
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = iso.date(from: text) { return date }
    iso.formatOptions = [.withInternetDateTime]
    return iso.date(from: text)
  }
}

// MARK: - dHash / Hamming

enum ScreenDHash {
  static let size = 8

  /// 64-bit difference hash from a row-major 9×8 grayscale buffer (72 samples).
  /// Bit (row * 8 + col) is set when gray[row, col] > gray[row, col+1].
  static func hash64(gray9x8: [UInt8]) -> UInt64 {
    precondition(gray9x8.count == 72, "dHash buffer must be 9×8")
    var hash: UInt64 = 0
    for row in 0..<8 {
      for col in 0..<8 {
        let left = gray9x8[row * 9 + col]
        let right = gray9x8[row * 9 + col + 1]
        if left > right {
          hash |= 1 << UInt64(row * 8 + col)
        }
      }
    }
    return hash
  }

  static func hamming(_ a: UInt64, _ b: UInt64) -> Int {
    (a ^ b).nonzeroBitCount
  }

  static func hex(_ hash: UInt64) -> String {
    String(format: "%016llx", hash)
  }

  static func parseHex(_ text: String) -> UInt64? {
    UInt64(text, radix: 16)
  }
}

// MARK: - Retention

enum ScreenRetentionPolicy {
  static let allowed: Set<Int> = [0, 3, 7, 14, 30]
  static let defaultDays = 7
  static let sweepInterval: TimeInterval = 6 * 60 * 60

  /// Invalid values fail safe to unlimited (0), never to a deleting window.
  static func normalize(_ days: Int) -> Int {
    allowed.contains(days) ? days : 0
  }

  static func shouldSweep(lastSweepAt: Date?, now: Date) -> Bool {
    guard let lastSweepAt else { return true }
    return now.timeIntervalSince(lastSweepAt) >= sweepInterval
  }

  static func isExpired(capturedAt: Date, now: Date, days: Int) -> Bool {
    if days == 0 { return false }
    return now.timeIntervalSince(capturedAt) >= TimeInterval(days) * 86_400
  }
}

// MARK: - Permission mapping

enum ScreenPermissionPolicy {
  /// Badge/status reports `CGPreflightScreenCaptureAccess` only.
  /// An engine failure is never mapped to denied.
  static func map(preflightGranted: Bool, hasRequested: Bool) -> String {
    if preflightGranted { return "granted" }
    if hasRequested { return "denied" }
    return "undetermined"
  }

  static func engineFailureNeverDenied(permission: String, engineFailed: Bool) -> String {
    _ = engineFailed
    return permission
  }
}

// MARK: - Default exclusions

enum ScreenExclusionPolicy {
  static let defaultBundleIds: [String] = [
    "com.1password.1password",
    "com.1password.1password7",
    "com.1password.1password-macos",
    "com.agilebits.onepassword7",
    "com.agilebits.onepassword-macos",
    "com.lastpass.LastPass",
    "com.bitwarden.desktop",
    "com.dashlane.dashlanephonefinal",
    "com.dashlane.Dashlane",
    "com.apple.keychainaccess",
    "me.omi.shell.core-tasks.prototype",
  ]

  static let videoCallBundleIds: Set<String> = [
    "us.zoom.xos",
    "com.microsoft.teams",
    "com.microsoft.teams2",
    "com.apple.FaceTime",
    "com.cisco.webexmeetingsapp",
    "com.skype.skype",
    "com.hnc.Discord",
    "com.tinyspeck.slackmacgap",
  ]

  static let screenshotBundleIds: Set<String> = [
    "com.apple.screencaptureui",
    "com.apple.Screenshot",
    "com.apple.screencapture",
    "com.cleanshot.cleanshotx",
    "com.knollsoft.Hookshot",
  ]

  static let mediaPlaybackBundleIds: Set<String> = [
    "com.apple.Music",
    "com.apple.TV",
    "com.apple.podcasts",
    "com.apple.QuickTimePlayerX",
    "com.apple.iBooksX",
    "com.apple.Photos",
  ]

  static func perAppIntervalSeconds(bundleId: String) -> TimeInterval? {
    switch bundleId {
    case "com.apple.Music", "com.apple.podcasts", "com.apple.Photos":
      return 10
    case "com.apple.iBooksX", "com.apple.iBooks":
      return 20
    case "com.apple.TV":
      return 30
    default:
      return nil
    }
  }

  /// Re-merge defaults on launch unless the user removed an entry.
  static func mergeDefaults(
    stored: [String],
    userRemoved: Set<String>,
    omiBundleId: String
  ) -> [String] {
    var set = Set(stored)
    for id in defaultBundleIds where !userRemoved.contains(id) {
      set.insert(id)
    }
    if !userRemoved.contains(omiBundleId) {
      set.insert(omiBundleId)
    }
    return set.sorted()
  }

  static func removedDefaults(previous: [String], next: [String]) -> Set<String> {
    let dropped = Set(previous).subtracting(next)
    return dropped.intersection(Set(defaultBundleIds).union([
      "me.omi.shell.core-tasks.prototype",
    ]))
  }
}

// MARK: - Fence generation

struct ScreenFence {
  var generation: UInt64
  var inFlight: Int

  static let initial = ScreenFence(generation: 0, inFlight: 0)

  mutating func bump() -> UInt64 {
    generation += 1
    return generation
  }

  mutating func beginWork() -> UInt64 {
    inFlight += 1
    return generation
  }

  mutating func endWork() {
    if inFlight > 0 { inFlight -= 1 }
  }

  func canWrite(capturedGeneration: UInt64) -> Bool {
    capturedGeneration == generation
  }

  var isDrained: Bool { inFlight == 0 }
}

// MARK: - Cadence

struct ScreenCadenceInput: Equatable {
  var now: Date
  var lastCaptureAt: Date?
  var lastAnchorAt: Date?
  var lastAppBundleId: String?
  var lastWindowTitle: String?
  var appBundleId: String
  var windowTitle: String
  var onBattery: Bool
  var idleSeconds: TimeInterval
  var mediaPlaying: Bool
  var locked: Bool
  var screensaver: Bool
  var loginwindow: Bool
  var frontmostIsScreenshotApp: Bool
  var screenSharingActive: Bool
  var sharingBackoffUntil: Date?
  var excluded: Bool
  var dhashHammingFromLastStored: Int?
  var heartbeatSeconds: TimeInterval
  var videoCallTick: Int
}

enum ScreenCadenceDecision: Equatable {
  case skip(String)
  case capture(String)
}

enum ScreenCadencePolicy {
  static let pollSeconds: TimeInterval = 1
  static let defaultHeartbeat: TimeInterval = 3
  static let idleGateSeconds: TimeInterval = 60
  static let anchorSeconds: TimeInterval = 30
  static let sharingBackoffSeconds: TimeInterval = 10
  static let staticHamming = 5
  static let ocrHamming = 5
  static let ocrEveryNth = 3

  static func decide(_ input: ScreenCadenceInput) -> ScreenCadenceDecision {
    if input.locked { return .skip("lock") }
    if input.screensaver { return .skip("screensaver") }
    if input.loginwindow { return .skip("loginwindow") }
    if input.frontmostIsScreenshotApp { return .skip("screenshot-app") }
    if input.screenSharingActive { return .skip("screen-sharing") }
    if let until = input.sharingBackoffUntil, input.now < until {
      return .skip("screen-sharing-backoff")
    }
    if input.excluded { return .skip("excluded") }
    if input.idleSeconds >= idleGateSeconds && !input.mediaPlaying {
      return .skip("idle")
    }

    let appChanged = input.lastAppBundleId.map { $0 != input.appBundleId } ?? true
    let titleChanged = input.lastWindowTitle.map { $0 != input.windowTitle } ?? true
    if appChanged || titleChanged {
      return .capture("app-or-title-change")
    }

    let sinceLast =
      input.lastCaptureAt.map { input.now.timeIntervalSince($0) } ?? .greatestFiniteMagnitude
    let sinceAnchor =
      input.lastAnchorAt.map { input.now.timeIntervalSince($0) } ?? .greatestFiniteMagnitude
    let needsAnchor = sinceAnchor >= anchorSeconds

    var interval = input.heartbeatSeconds
    if let override = ScreenExclusionPolicy.perAppIntervalSeconds(bundleId: input.appBundleId) {
      interval = override
    }
    if input.onBattery { interval *= 3 }
    let visuallyStatic =
      (input.dhashHammingFromLastStored ?? Int.max) <= staticHamming
    if visuallyStatic { interval *= 2 }

    if needsAnchor { return .capture("anchor") }

    if ScreenExclusionPolicy.videoCallBundleIds.contains(input.appBundleId),
      input.videoCallTick % 5 != 0
    {
      return .skip("video-call-sample")
    }

    if sinceLast < interval { return .skip("heartbeat") }
    if visuallyStatic { return .skip("dhash-static") }
    return .capture("heartbeat")
  }

  static func nextSharingBackoff(now: Date) -> Date {
    now.addingTimeInterval(sharingBackoffSeconds)
  }

  /// OCR at most every 3rd captured frame; Hamming ≤5 vs last OCR'd dHash skips OCR.
  static func shouldOCR(
    capturedCount: Int,
    hammingFromLastOCR: Int?
  ) -> Bool {
    if let hamming = hammingFromLastOCR, hamming <= ocrHamming { return false }
    if capturedCount <= 0 { return true }
    return capturedCount % ocrEveryNth == 0
  }
}

// MARK: - Indexed meaning (one: OCR completed)

enum ScreenIndexMeaning {
  /// A frame is indexed only when on-device OCR completed and produced blocks.
  static func isIndexed(ocrCompleted: Bool, blockCount: Int) -> Bool {
    ocrCompleted && blockCount > 0
  }
}

// MARK: - Ingest batching / cursor / backoff

struct ScreenIngestCursor: Equatable {
  var lastAcceptedId: String?
  var pendingIds: [String]
  var failureCount: Int
  var backoffUntil: Date?

  static let empty = ScreenIngestCursor(
    lastAcceptedId: nil, pendingIds: [], failureCount: 0, backoffUntil: nil)

  static let maxBatch = 100

  func nextBatch(from pending: [String]) -> [String] {
    Array(pending.prefix(Self.maxBatch))
  }

  func canAttempt(now: Date) -> Bool {
    guard let backoffUntil else { return true }
    return now >= backoffUntil
  }

  func backoffDelay() -> TimeInterval {
    let exp = min(failureCount, 6)
    return min(60, pow(2.0, Double(max(exp, 0))))
  }

  func afterFailure(now: Date) -> ScreenIngestCursor {
    var next = self
    next.failureCount += 1
    next.backoffUntil = now.addingTimeInterval(next.backoffDelay())
    return next
  }

  func afterSuccess(acceptedIds: [String]) -> ScreenIngestCursor {
    var next = self
    if let last = acceptedIds.last { next.lastAcceptedId = last }
    let done = Set(acceptedIds)
    next.pendingIds = pendingIds.filter { !done.contains($0) }
    next.failureCount = 0
    next.backoffUntil = nil
    return next
  }
}

// MARK: - Retired GC

enum ScreenRetiredGC {
  static func chunkPathsToDelete(
    retiredRefs: [String],
    index: [String: String]
  ) -> [String] {
    var paths: [String] = []
    var seen = Set<String>()
    for ref in retiredRefs {
      guard let path = index[ref], !seen.contains(path) else { continue }
      seen.insert(path)
      paths.append(path)
    }
    return paths
  }
}
