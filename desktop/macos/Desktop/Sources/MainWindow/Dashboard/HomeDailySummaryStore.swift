import Foundation
import OmiSupport

/// Loads recent daily summaries for Chat and the Activity timeline, and keeps them owner-scoped.
///
/// Mobile has rendered daily summaries for months; the desktop only ever exposed the on/off
/// setting. This store is the smallest read path that lets Home show the same record, including
/// the stats row the backend now fills from desktop usage. It never blocks anything: a failed
/// fetch leaves the last good summary in place and records a bounded error string.
@MainActor
final class HomeDailySummaryStore: ObservableObject {
  typealias Fetch = @Sendable (Int) async throws -> [DailySummaryRecord]
  typealias SettingsHour = @Sendable () async -> Int
  /// Owner fence for one refresh: `nil` when no owner is signed in (do not
  /// fetch), otherwise a check that the same owner is still current after the
  /// await, so a result never publishes for an account that has since switched.
  typealias OwnerFence = @MainActor () -> (@MainActor () -> Bool)?

  /// Newest-first window the timeline looks up by date. One row used to make a 10-day-old
  /// record look current.
  static let fetchLimit = 14
  /// Backend default when the settings read fails (`DEFAULT_DAILY_SUMMARY_HOUR_LOCAL`).
  /// `nonisolated` so the nonisolated `settingsHour` fallback and the stored-property
  /// initializer below can both name it.
  nonisolated static let defaultSummaryHour = 22

  @Published private(set) var latest: DailySummaryRecord?
  /// Keyed by the backend's `date` string (`YYYY-MM-DD`). Duplicate dates last-write-win;
  /// nil/malformed dates are omitted.
  @Published private(set) var byDate: [String: DailySummaryRecord] = [:]
  /// Local hour the user asked the recap to run. Empty-state "Generate" hides for today before this.
  @Published private(set) var summaryHour: Int = HomeDailySummaryStore.defaultSummaryHour
  @Published private(set) var isLoading = false
  @Published private(set) var lastError: String?

  /// Refetch no more often than this while the hub stays open; the record changes once a day.
  static let refreshInterval: TimeInterval = 15 * 60

  private let ownerFence: OwnerFence
  private let fetch: Fetch
  private let settingsHour: SettingsHour
  private let now: () -> Date
  private var lastRefresh: Date?
  private var inFlight: Task<Void, Never>?
  /// `nonisolated(unsafe)` so the nonisolated `deinit` can remove it; only ever written on the main actor.
  nonisolated(unsafe) private var ownerObserver: NSObjectProtocol?

  init(
    ownerFence: @escaping OwnerFence = {
      guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return nil }
      return { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) }
    },
    fetch: @escaping Fetch = { limit in try await APIClient.shared.getDailySummaries(limit: limit) },
    settingsHour: @escaping SettingsHour = {
      // The empty-state gate is only honest if it reads the hour the user actually chose.
      // A hardcoded default hid "Generate recap" until 22:00 for anyone on a different hour.
      (try? await APIClient.shared.getDailySummarySettings().hour) ?? HomeDailySummaryStore.defaultSummaryHour
    },
    now: @escaping () -> Date = Date.init
  ) {
    self.ownerFence = ownerFence
    self.fetch = fetch
    self.settingsHour = settingsHour
    self.now = now
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      Task { @MainActor [weak self] in self?.reset() }
    }
  }

  deinit {
    if let ownerObserver { NotificationCenter.default.removeObserver(ownerObserver) }
  }

  /// Refresh when the hub appears, but not on every re-render.
  func refreshIfNeeded() async {
    if let lastRefresh, now().timeIntervalSince(lastRefresh) < Self.refreshInterval, latest != nil {
      return
    }
    await refresh()
  }

  func refresh() async {
    if let inFlight {
      await inFlight.value
      return
    }
    let task = Task { @MainActor [weak self] in
      guard let self else { return }
      self.isLoading = true
      defer { self.isLoading = false }
      // INV-AUTH-1: the result publishes only for the owner it was fetched for.
      guard let isOwnerStillCurrent = self.ownerFence() else { return }
      do {
        let summaries = try await self.fetch(Self.fetchLimit)
        let resolvedHour = await self.settingsHour()
        guard isOwnerStillCurrent() else {
          log("HomeDailySummaryStore: dropped summary after account switch")
          return
        }
        self.latest = summaries.first
        // `summaries` is newest-first and `lastWriteWins` keeps the *last* pair seen, so the
        // sequence has to be reversed: iterated as served, a duplicated date (#4608) would
        // resolve to the older of the two records.
        self.byDate = Dictionary(
          lastWriteWins: summaries.reversed().compactMap { record -> (String, DailySummaryRecord)? in
            guard let date = record.date, ChatDailySummaryPresentation.day(from: date) != nil else {
              return nil
            }
            return (date, record)
          })
        self.summaryHour = resolvedHour
        self.lastError = nil
        self.lastRefresh = self.now()
      } catch {
        // Bounded: the message is for the local log and an inline hint, never for analytics.
        self.lastError = "Couldn't load your daily summary."
        log("HomeDailySummaryStore: refresh failed: \(error)")
      }
    }
    inFlight = task
    await task.value
    inFlight = nil
  }

  /// Publish a record the user just generated or regenerated so the timeline updates in place.
  func upsert(_ record: DailySummaryRecord) {
    if let date = record.date, ChatDailySummaryPresentation.day(from: date) != nil {
      byDate[date] = record
    }
    if latest == nil || latest?.date == record.date || latest?.id == record.id {
      latest = record
    }
  }

  private func reset() {
    inFlight?.cancel()
    inFlight = nil
    latest = nil
    byDate = [:]
    summaryHour = HomeDailySummaryStore.defaultSummaryHour
    lastError = nil
    lastRefresh = nil
  }
}
