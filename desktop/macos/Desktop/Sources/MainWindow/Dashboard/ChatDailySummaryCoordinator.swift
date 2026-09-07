import AppKit
import Foundation

/// The one daily-summary read shared by both shells' Chat surfaces.
///
/// Chat is the resting surface on desktop, so the summary belongs at the top of the thread rather
/// than on a page nobody opens. Both shells render the same `ChatMessagesView`, so both mount the
/// same card — and a second store would mean two fetches, two throttles, and two chances to show a
/// previous owner's day. `HomeDailySummaryStore` already owns the fetch, the 15-minute throttle,
/// and the owner-change reset; this coordinator adds only what Chat needs on top of it: the day
/// boundary, the wake, and the one-notch-card-per-new-summary announcement.
///
/// **It is not a transcript.** The card is chrome above the messages (INV-CHAT-1): nothing here
/// writes a turn, a journal entry, or a synthetic message.
@MainActor
final class ChatDailySummaryCoordinator: ObservableObject {
  static let shared = ChatDailySummaryCoordinator()

  /// Posts the notch card. Injected so a test can observe the announcement without a notification
  /// centre or a signed-in owner.
  typealias CardSink = @MainActor (_ ownerID: String, _ title: String, _ body: String) -> Void

  let store: HomeDailySummaryStore

  /// True while the summary on hand is the one the owner cleared out of Chat.
  ///
  /// Clearing the transcript is a statement about the whole surface, not about
  /// the rows the journal happens to own. The card is chrome above the thread
  /// (INV-CHAT-1 keeps transcript authorship in the kernel, so nothing here
  /// writes a turn) and a journal clear cannot reach it — which left the day's
  /// summary sitting alone in a chat the reader had just emptied. Clearing
  /// records the summary it was showing instead, and the card stays away until
  /// a newer day's summary arrives.
  @Published private(set) var isClearedFromTranscript = false

  private let defaults: UserDefaults
  private let cardSink: CardSink
  private let ownerID: () -> String?
  /// `nonisolated(unsafe)` so the nonisolated `deinit` can unregister; only ever written on
  /// the main actor, and only once.
  nonisolated(unsafe) private var observers: [NSObjectProtocol] = []
  private var didStartObserving = false

  init(
    store: HomeDailySummaryStore? = nil,
    defaults: UserDefaults = .standard,
    ownerID: @escaping () -> String? = { RuntimeOwnerIdentity.captureAuthorizationSnapshot()?.ownerID },
    cardSink: CardSink? = nil
  ) {
    // No `settingsHour` override: the store's own default reads the same setting and falls back
    // to `HomeDailySummaryStore.defaultSummaryHour`. Passing a second closure here duplicated the
    // literal 22, so a change to the backend default would have moved one of them and not the other.
    self.store = store ?? HomeDailySummaryStore()
    self.defaults = defaults
    self.ownerID = ownerID
    self.cardSink = cardSink ?? Self.defaultCardSink
  }

  deinit {
    let captured = observers
    let workspace = NSWorkspace.shared.notificationCenter
    for observer in captured {
      NotificationCenter.default.removeObserver(observer)
      workspace.removeObserver(observer)
    }
  }

  /// Called by the card when it mounts. Registers the cadence observers once and takes the first
  /// read. Refreshing on mount is the launch trigger: Chat is what both shells open on.
  func activate() async {
    startObservingIfNeeded()
    await refreshIfNeeded()
  }

  /// Owner-gated. A signed-out or mid-transition process must never fetch, because the record it
  /// would get back belongs to whoever the runtime settles on next.
  func refreshIfNeeded() async {
    guard ownerID() != nil else { return }
    await store.refreshIfNeeded()
    refreshClearedState()
    announceIfNew()
  }

  /// Bypasses the throttle: the day changed, or the Mac woke into a new day, and the summary the
  /// card is showing is now about a day that is over.
  func refresh() async {
    guard ownerID() != nil else { return }
    await store.refresh()
    refreshClearedState()
    announceIfNew()
  }

  // MARK: - Clearing

  /// Chat was cleared. Take the card with it.
  ///
  /// Recording the id rather than a flag is what lets tomorrow's summary come
  /// back on its own: the card is withdrawn only while the summary on hand is
  /// the one that was on screen when the reader cleared.
  func noteChatCleared() {
    guard let owner = ownerID(), let record = store.latest else { return }
    defaults.set(record.id, forKey: ScopedDefaultsKey.dailySummaryClearedID(ownerID: owner))
    isClearedFromTranscript = true
    AnalyticsManager.shared.trackDailySummary(.cardDismissed)
  }

  private func refreshClearedState() {
    guard let owner = ownerID(), let record = store.latest else {
      isClearedFromTranscript = false
      return
    }
    isClearedFromTranscript =
      defaults.string(forKey: ScopedDefaultsKey.dailySummaryClearedID(ownerID: owner)) == record.id
  }

  // MARK: - New-summary announcement

  /// Desktop has no FCM registration and no remote-notification delegate, so the `daily_summary`
  /// push the backend sends to `macos_` tokens never arrives here. The observable equivalent is a
  /// refresh that returns a summary the owner has not been shown yet; announcing on that keeps the
  /// card at-most-once per summary without inventing a push path.
  private func announceIfNew() {
    guard let record = store.latest, let owner = ownerID() else { return }
    let key = ScopedDefaultsKey.dailySummaryLastSeenID(ownerID: owner)
    guard defaults.string(forKey: key) != record.id else { return }
    // A record whose overview has not filled in yet is not consumed: the id is
    // marked seen only once a card was actually handed to the sink.
    guard let body = ChatDailySummaryPresentation.cardBody(for: record.overview) else { return }
    cardSink(owner, ChatDailySummaryPresentation.cardTitle(for: record), body)
    defaults.set(record.id, forKey: key)
    AnalyticsManager.shared.trackDailySummary(.cardShown)
  }

  /// The assistant identity the recap announcement presents under, so the floating bar's kind
  /// derivation (`ProactiveNotificationKind.from(assistantId:)`) lands on `.dailyRecap` —
  /// presentation-only. The announcement must not journal a transcript turn: the recap is already
  /// in the thread as the dedicated `ChatDailyRecapRow` day boundary, and a journaled bell card
  /// rendered a truncated, stat-less copy of it (INV-CHAT-1 — the recap is chrome, not a turn).
  static let assistantID = "daily_recap"

  private static let defaultCardSink: CardSink = { ownerID, title, body in
    // Fenced to the owner the summary was fetched for, not whoever is current now.
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID) else {
      return
    }
    NotificationService.shared.sendNotification(
      ownerID: snapshot.ownerID,
      title: title,
      message: body,
      assistantId: ChatDailySummaryCoordinator.assistantID,
      // The summary is a statement about a day that already happened; the frequency budget exists
      // to throttle interruptions the user did not ask for, and this one is at most one per day.
      respectFrequency: false,
      isPersistent: false,
      authorizationSnapshot: snapshot
    )
  }

  // MARK: - Cadence

  private func startObservingIfNeeded() {
    guard !didStartObserving else { return }
    didStartObserving = true

    observers.append(
      NotificationCenter.default.addObserver(
        forName: .NSCalendarDayChanged, object: nil, queue: .main
      ) { [weak self] _ in
        Task { @MainActor [weak self] in await self?.refresh() }
      })

    observers.append(
      NSWorkspace.shared.notificationCenter.addObserver(
        forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
      ) { [weak self] _ in
        Task { @MainActor [weak self] in await self?.refresh() }
      })

    observers.append(
      NotificationCenter.default.addObserver(
        forName: .runtimeOwnerDidChange, object: nil, queue: .main
      ) { [weak self] _ in
        Task { @MainActor [weak self] in await self?.refreshIfNeeded() }
      })
  }
}
