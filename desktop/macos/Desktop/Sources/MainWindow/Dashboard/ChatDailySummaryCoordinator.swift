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
    announceIfNew()
  }

  /// Bypasses the throttle: the day changed, or the Mac woke into a new day, and the summary the
  /// card is showing is now about a day that is over.
  func refresh() async {
    guard ownerID() != nil else { return }
    await store.refresh()
    announceIfNew()
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

  // MARK: - EXP-002 postcard-first landing

  /// True when the latest summary has not been landed on yet, and marks it
  /// landed. The `memory_v1` arm opens the Chat surface on the postcard for
  /// exactly those summaries — the night object — instead of the live edge;
  /// every later open follows the bottom as usual. Uses its own latch so it
  /// can never consume the notch announcement (or vice versa), and only
  /// counts a summary whose overview has filled in, matching
  /// `announceIfNew`'s "not consumed until actually shown" rule.
  func consumeUnseenSummaryForPostcardLanding() -> Bool {
    guard let record = store.latest,
      ChatDailySummaryPresentation.cardBody(for: record.overview) != nil,
      let owner = ownerID()
    else { return false }
    let key = ScopedDefaultsKey.dailySummaryPostcardLandedID(ownerID: owner)
    guard defaults.string(forKey: key) != record.id else { return false }
    defaults.set(record.id, forKey: key)
    return true
  }

  private static let defaultCardSink: CardSink = { ownerID, title, body in
    // Fenced to the owner the summary was fetched for, not whoever is current now.
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID) else {
      return
    }
    NotificationService.shared.sendNotification(
      ownerID: snapshot.ownerID,
      title: title,
      message: body,
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
