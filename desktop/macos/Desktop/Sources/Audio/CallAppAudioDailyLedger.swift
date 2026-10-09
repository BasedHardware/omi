import Foundation

/// Persists the current local day's call-audio aggregates and flushes the
/// previous day. Sparkle relaunches the app about hourly, so the counters live
/// in UserDefaults rather than only in the detector.
struct CallAppAudioDailyLedger {
  private struct Stored: Codable {
    var localDay: String
    var bundles: [StoredBundle]
  }

  private struct StoredBundle: Codable {
    var bundleID: String
    var counters: CallAudioBundleCounters
  }

  private var tracker = CallAudioSessionTracker()
  private var localDay: String?
  private var didBegin = false
  private let defaults: UserDefaults
  private let calendar: Calendar

  init(defaults: UserDefaults = .standard, calendar: Calendar = .current) {
    self.defaults = defaults
    self.calendar = calendar
  }

  func nativeCallIdentity(bundleID: String) -> String {
    tracker.nativeCallIdentity(bundleID: bundleID)
  }

  /// Load today's counters, or return the previous day's summaries and start
  /// a fresh day. Saving happens before the caller emits, so a crash cannot
  /// flush the same day twice.
  mutating func begin(at date: Date) -> [CallAppAudioSummary] {
    let today = CallAppAudioLocalDay.string(for: date, calendar: calendar)
    if didBegin { return roll(to: today, at: date) }
    didBegin = true
    guard let stored = load() else {
      localDay = today
      return []
    }
    if stored.localDay == today {
      localDay = today
      tracker = CallAudioSessionTracker(counters: stored.counters)
      return []
    }
    let flushed = CallAppAudioSummaryRanking.select(counters: stored.counters, localDay: stored.localDay)
    localDay = today
    tracker = CallAudioSessionTracker()
    save()
    return flushed
  }

  mutating func ingest(_ snapshot: CallAudioSnapshot, at date: Date) -> [CallAppAudioSummary] {
    let flushed = begin(at: date)
    tracker.ingest(snapshot, at: date)
    save()
    return flushed
  }

  private mutating func roll(to today: String, at date: Date) -> [CallAppAudioSummary] {
    guard let localDay, localDay != today else { return [] }
    tracker.closeOpenSessions(at: date)
    let flushed = CallAppAudioSummaryRanking.select(counters: tracker.counters, localDay: localDay)
    self.localDay = today
    tracker = CallAudioSessionTracker()
    save()
    return flushed
  }

  private func load() -> (localDay: String, counters: [String: CallAudioBundleCounters])? {
    guard let data = defaults.data(forKey: .callAppAudioDailyLedger) else { return nil }
    guard let stored = try? JSONDecoder().decode(Stored.self, from: data) else {
      log("CallAppAudioDailyLedger: ignoring unreadable aggregate store")
      return nil
    }
    var counters: [String: CallAudioBundleCounters] = [:]
    for bundle in stored.bundles {
      let id = bundle.bundleID.lowercased()
      guard !id.isEmpty else { continue }
      counters[id] = bundle.counters
    }
    return (stored.localDay, counters)
  }

  private func save() {
    guard let localDay else { return }
    let bundles = tracker.counters.map { bundle, counters in
      StoredBundle(bundleID: bundle, counters: counters)
    }
    guard let data = try? JSONEncoder().encode(Stored(localDay: localDay, bundles: bundles)) else { return }
    defaults.set(data, forKey: .callAppAudioDailyLedger)
  }
}
