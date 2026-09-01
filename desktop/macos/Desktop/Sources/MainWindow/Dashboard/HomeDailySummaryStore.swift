import Foundation

/// Loads the newest daily summary for the Home hub and keeps it owner-scoped.
///
/// Mobile has rendered daily summaries for months; the desktop only ever exposed the on/off
/// setting. This store is the smallest read path that lets Home show the same record, including
/// the stats row the backend now fills from desktop usage. It never blocks anything: a failed
/// fetch leaves the last good summary in place and records a bounded error string.
@MainActor
final class HomeDailySummaryStore: ObservableObject {
  typealias Fetch = @Sendable (Int) async throws -> [DailySummaryRecord]

  @Published private(set) var latest: DailySummaryRecord?
  @Published private(set) var isLoading = false
  @Published private(set) var lastError: String?

  /// Refetch no more often than this while the hub stays open; the record changes once a day.
  static let refreshInterval: TimeInterval = 15 * 60

  private let fetch: Fetch
  private let now: () -> Date
  private var lastRefresh: Date?
  private var inFlight: Task<Void, Never>?
  /// `nonisolated(unsafe)` so the nonisolated `deinit` can remove it; only ever written on the main actor.
  nonisolated(unsafe) private var ownerObserver: NSObjectProtocol?

  init(
    fetch: @escaping Fetch = { limit in try await APIClient.shared.getDailySummaries(limit: limit) },
    now: @escaping () -> Date = Date.init
  ) {
    self.fetch = fetch
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
      do {
        let summaries = try await self.fetch(1)
        self.latest = summaries.first
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

  private func reset() {
    inFlight?.cancel()
    inFlight = nil
    latest = nil
    lastError = nil
    lastRefresh = nil
  }
}
