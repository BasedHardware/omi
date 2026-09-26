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
/// and only bundles that had a call-like session that day.
enum CallAppAudioSummaryRanking {
  static let dailyBundleCap = 20

  static func select(
    counters: [String: CallAudioBundleCounters],
    localDay: String
  ) -> [CallAppAudioSummary] {
    let ranked = counters.filter { $0.value.callLikeSessions >= 1 }.sorted { lhs, rhs in
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
