import Foundation

/// One `Desktop Call App Audio Summary` row: a bundle's counts for one local day.
struct CallAppAudioSummary: Equatable, Sendable {
  var bundleID: String
  var localDay: String
  var counters: CallAudioBundleCounters
  var catalogReleaseEndsCall: Bool

  init(bundleID: String, localDay: String, counters: CallAudioBundleCounters) {
    self.bundleID = bundleID
    self.localDay = localDay
    self.counters = counters
    self.catalogReleaseEndsCall = CallAppReleasePolicy.releaseEndsCall(bundleID: bundleID)
  }
}

enum CallAppAudioLocalDay {
  static func string(for date: Date, calendar: Calendar) -> String {
    let parts = calendar.dateComponents([.year, .month, .day], from: date)
    return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
  }
}

/// Largest call-like session count first, then bundle id. At most 20 bundles,
/// and only bundles that had a call-like session that day. Omi's own processes are excluded.
enum CallAppAudioSummaryRanking {
  static let dailyBundleCap = 20

  static func isOwnApp(_ bundleID: String) -> Bool {
    bundleID.lowercased().hasPrefix("com.omi.")
  }

  static func select(
    counters: [String: CallAudioBundleCounters],
    localDay: String
  ) -> [CallAppAudioSummary] {
    // Omi's own capture holds the mic and speaker for hours; it is not a call app.
    let ranked = counters.filter { $0.value.callLikeSessions >= 1 && !isOwnApp($0.key) }.sorted { lhs, rhs in
      if lhs.value.callLikeSessions != rhs.value.callLikeSessions {
        return lhs.value.callLikeSessions > rhs.value.callLikeSessions
      }
      return lhs.key < rhs.key
    }
    return ranked.prefix(dailyBundleCap).map { bundle, row in
      CallAppAudioSummary(bundleID: bundle, localDay: localDay, counters: row)
    }
  }
}

/// Bounded payload for `Desktop Call App Audio Summary`. Keys are counts,
/// buckets, the bundle id, and the local day — nothing user-authored.
enum CallAppAudioSummaryTelemetry {
  static let eventName = "Desktop Call App Audio Summary"

  static func properties(_ summary: CallAppAudioSummary) -> [String: Any] {
    let counters = summary.counters
    return [
      "platform": "macos",
      "bundle_id": summary.bundleID,
      "call_like_sessions": counters.callLikeSessions,
      "releases_call_end": counters.releasesCallEnd,
      "releases_mute_like": counters.releasesMuteLike,
      "releases_device_switch": counters.releasesDeviceSwitch,
      "reacquire_gap_lt2s": counters.reacquireGapLt2s,
      "reacquire_gap_2_10s": counters.reacquireGap2to10s,
      "reacquire_gap_10_60s": counters.reacquireGap10to60s,
      "reacquire_gap_60_300s": counters.reacquireGap60to300s,
      "session_lt1m": counters.sessionLt1m,
      "session_1_10m": counters.session1to10m,
      "session_10_60m": counters.session10to60m,
      "session_ge60m": counters.sessionGe60m,
      "catalog_release_ends_call": summary.catalogReleaseEndsCall,
      "local_day": summary.localDay,
    ]
  }
}

/// Bounded on-edge evidence using the same bundle dimension as daily audio summaries.
/// Never includes window titles, Meet codes, pids, or device identifiers.
struct MeetingDetectionEvidence: Sendable {
  static let eventName = "Desktop Meeting Confirmed"
  let bundleIDs: [String]
  let titleMatched: Bool
  let titlesReadable: Bool
  let processInputAPIAvailable: Bool
  let mode: String

  init(snapshot: CallAudioSnapshot, mode: AssistantSettings.AudioRecordingMode, processInputAPIAvailable: Bool) {
    var bundles = MeetingCallObservation.nativeApps(snapshot: snapshot)
    let windows = MeetingCallObservation.liveBrowserWindows(
      snapshot: snapshot, processInputAPIAvailable: processInputAPIAvailable)
    for window in windows { bundles.insert(window.bundleID.lowercased()) }
    if !snapshot.browserTitlesReadable {
      for process in snapshot.processes where process.isRunningInput {
        if let browser = MeetingCallObservation.browserFamily(process.bundleID) { bundles.insert(browser) }
      }
    }
    bundleIDs = Array(bundles.sorted().prefix(CallAppAudioSummaryRanking.dailyBundleCap))
    titleMatched = !windows.isEmpty
    titlesReadable = snapshot.browserTitlesReadable
    self.processInputAPIAvailable = processInputAPIAvailable
    self.mode = mode.rawValue
  }

  var properties: [String: Any] {
    [
      "platform": "macos", "bundle_ids": bundleIDs, "browser_title_matched": titleMatched,
      "browser_titles_readable": titlesReadable, "process_input_api_available": processInputAPIAvailable,
      "recording_mode": mode, "confirmation_seconds": MeetingDetectionTiming.confirmationPeriod,
    ]
  }
}
