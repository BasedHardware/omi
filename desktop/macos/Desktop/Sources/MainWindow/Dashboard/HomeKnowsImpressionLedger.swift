import CryptoKit
import Foundation

// MARK: - What the knows-list already showed

/// One row's history in the Home knows-list.
///
/// The composer used to have no memory at all, so a thin source (four open
/// commitments, one stale insight) re-rendered the same four rows on every
/// visit — the owner's 14-day sample repeated "meet with <person>" nine times
/// and "improve meeting notes quality" eight. This is the memory.
struct HomeKnowsImpression: Codable, Equatable {
  var shows: Int = 0
  var firstShownAt: Date?
  var lastShownAt: Date?
  var lastOpenedAt: Date?
  var dismissedAt: Date?
  /// Hash of the underlying object the last time this entry was written.
  /// A dismissed or capped row returns only when this changes.
  var contentHash: String = ""
}

struct HomeKnowsImpressionLedger: Codable, Equatable {
  static let empty = HomeKnowsImpressionLedger()

  var entries: [String: HomeKnowsImpression] = [:]

  func entry(_ key: String) -> HomeKnowsImpression? { entries[key] }
}

/// The identity and freshness facts the rotation rules need, independent of
/// which source a candidate came from.
struct HomeKnowsCandidateFacts: Equatable {
  let key: String
  let contentHash: String
  /// When the underlying object last changed. `nil` sorts last on freshness.
  let updatedAt: Date?
  /// Due date for task rows; `nil` for everything else.
  let dueAt: Date?
  /// False once the underlying task is completed, retired, or deleted.
  let isActive: Bool

  init(
    key: String,
    contentHash: String,
    updatedAt: Date? = nil,
    dueAt: Date? = nil,
    isActive: Bool = true
  ) {
    self.key = key
    self.contentHash = contentHash
    self.updatedAt = updatedAt
    self.dueAt = dueAt
    self.isActive = isActive
  }
}

/// Why a candidate did not get its slot. Bounded set — it is a PostHog property.
enum HomeKnowsRotationReason: String, Equatable, Sendable, CaseIterable {
  /// The reader dismissed it and the underlying object has not changed since.
  case dismissed
  /// Shown the cap number of times without ever being opened.
  case showCap = "show_cap"
  /// Already shown today, and never opened, so it does not repeat.
  case sameDay = "same_day"
  /// Task due date is far enough past that surfacing it is noise.
  case staleDueDate = "stale_due_date"
  /// Underlying task was completed or deleted.
  case inactive
  /// The source had nothing to offer this slot at all.
  case noCandidate = "no_candidate"
}

// MARK: - Rules

/// Deterministic, clock-injected rotation rules. Pure by construction so the
/// behaviour is unit-testable without UserDefaults or a running app.
enum HomeKnowsRotationPolicy {
  /// Shows without an open before a row rotates out.
  static let showCapCount = 3
  /// How long a capped row stays out.
  static let showCapCooldown: TimeInterval = 7 * 24 * 60 * 60
  /// How far past due a task may be before it stops being surfaced.
  static let stalePastDueGrace: TimeInterval = 14 * 24 * 60 * 60

  /// A stable content hash for a row's underlying object. A dismissed row
  /// returns only when this changes, so it must move when the object does.
  static func contentHash(text: String, updatedAt: Date? = nil) -> String {
    let stamp = updatedAt.map { String(Int($0.timeIntervalSince1970)) } ?? "-"
    return digest("\(text)|\(stamp)")
  }

  /// Ledger key for a free-text row (a suggested question or composed tip).
  /// Hashed rather than raw so the persisted ledger is not a copy of the
  /// reader's suggestions.
  static func questionKey(_ text: String) -> String { "question:\(digest(text))" }
  static func taskKey(_ id: String) -> String { "task:\(id)" }
  static func insightKey(_ id: String) -> String { "insight:\(id)" }

  private static func digest(_ value: String) -> String {
    let hash = SHA256.hash(data: Data(value.utf8))
    return String(hash.compactMap { String(format: "%02x", $0) }.joined().prefix(16))
  }

  /// Why this candidate is not something to surface at all right now, or `nil`
  /// if it still is. Independent of how often it has been shown.
  ///
  /// Split out because two callers need exactly this much and no more: the
  /// composer, which then layers the rotation rules on top, and the greeting's
  /// open-task count, which must not shrink just because a row has already had
  /// its three impressions today. One predicate is what keeps "3 things need
  /// you" honest about the list underneath it.
  static func availability(
    facts: HomeKnowsCandidateFacts,
    entry: HomeKnowsImpression?,
    now: Date
  ) -> HomeKnowsRotationReason? {
    guard facts.isActive else { return .inactive }
    if let dueAt = facts.dueAt, now.timeIntervalSince(dueAt) > stalePastDueGrace {
      return .staleDueDate
    }
    // A changed underlying object is new information: it clears a dismissal and
    // resets the show cap. That is the only way a dismissed row ever returns.
    guard let entry, entry.contentHash == facts.contentHash else { return nil }
    return entry.dismissedAt != nil ? .dismissed : nil
  }

  /// Why this candidate must not take a slot right now, or `nil` if it may.
  ///
  /// - Parameter allowSameDayRepeat: set only when the slot has no other
  ///   qualifying candidate. Even then a same-day repeat needs a prior open.
  static func suppression(
    facts: HomeKnowsCandidateFacts,
    entry: HomeKnowsImpression?,
    now: Date,
    calendar: Calendar,
    allowSameDayRepeat: Bool
  ) -> HomeKnowsRotationReason? {
    if let unavailable = availability(facts: facts, entry: entry, now: now) { return unavailable }
    // Past this point the entry exists and still describes this exact content;
    // anything else was already admitted by `availability`.
    guard let entry, entry.contentHash == facts.contentHash else { return nil }

    if entry.lastOpenedAt == nil, entry.shows >= showCapCount {
      let lastShownAt = entry.lastShownAt ?? .distantPast
      if now.timeIntervalSince(lastShownAt) < showCapCooldown { return .showCap }
    }

    if let lastShownAt = entry.lastShownAt, calendar.isDate(lastShownAt, inSameDayAs: now) {
      guard allowSameDayRepeat, entry.lastOpenedAt != nil else { return .sameDay }
    }
    return nil
  }

  /// Freshness order inside one slot: never-shown first, then fewest shows,
  /// then most recently updated.
  ///
  /// Deliberately not tie-broken on the row key: candidates arrive in the
  /// caller's own priority order (the most pressing task, the best-ranked
  /// suggested question), and hashing that order away would silently reorder
  /// equally-fresh rows. Callers break remaining ties on the source index.
  static func freshnessRank(
    _ facts: HomeKnowsCandidateFacts,
    ledger: HomeKnowsImpressionLedger
  ) -> (Int, Int, Double) {
    let shows = ledger.entry(facts.key)?.shows ?? 0
    let updated = facts.updatedAt?.timeIntervalSince1970 ?? 0
    return (shows == 0 ? 0 : 1, shows, -updated)
  }

  /// The one reason worth reporting when a whole slot came up empty. Fixed
  /// priority so the telemetry is deterministic rather than dictionary-ordered.
  static func dominantReason(_ reasons: [HomeKnowsRotationReason]) -> HomeKnowsRotationReason {
    let priority: [HomeKnowsRotationReason] = [
      .dismissed, .showCap, .sameDay, .staleDueDate, .inactive, .noCandidate,
    ]
    return priority.first { reasons.contains($0) } ?? .noCandidate
  }
}

// MARK: - Persistence

@MainActor
protocol HomeKnowsImpressionPersisting: AnyObject {
  func load() -> HomeKnowsImpressionLedger
  func save(_ ledger: HomeKnowsImpressionLedger)
}

/// Owner-scoped so one account's dismissals never silence the knows-list for
/// another account on the same Mac (the #9821 account-switch-bleed class).
@MainActor
final class HomeKnowsImpressionDefaults: HomeKnowsImpressionPersisting {
  /// Entries with no activity inside this window are dropped on load, so the
  /// ledger cannot grow without bound across months of tasks.
  static let retention: TimeInterval = 90 * 24 * 60 * 60

  private let defaults: UserDefaults
  private let fixedOwnerID: String?
  private let now: () -> Date

  init(defaults: UserDefaults = .standard, ownerID: String? = nil, now: @escaping () -> Date = Date.init) {
    self.defaults = defaults
    fixedOwnerID = ownerID
    self.now = now
  }

  private var key: ScopedDefaultsKey {
    let dynamicOwner =
      defaults === UserDefaults.standard
      ? RuntimeOwnerIdentity.currentOwnerId()
      : defaults.string(forKey: .authUserId)
    return .homeKnowsImpressions(ownerID: fixedOwnerID ?? dynamicOwner ?? "signed-out")
  }

  func load() -> HomeKnowsImpressionLedger {
    guard let data = defaults.data(forKey: key),
      let decoded = try? JSONDecoder().decode(HomeKnowsImpressionLedger.self, from: data)
    else { return .empty }
    let cutoff = now().addingTimeInterval(-Self.retention)
    var pruned = decoded
    pruned.entries = decoded.entries.filter { _, impression in
      let touched = [impression.lastShownAt, impression.dismissedAt, impression.lastOpenedAt]
        .compactMap { $0 }
        .max()
      return (touched ?? .distantPast) >= cutoff
    }
    return pruned
  }

  func save(_ ledger: HomeKnowsImpressionLedger) {
    defaults.set(try? JSONEncoder().encode(ledger), forKey: key)
  }
}

// MARK: - Store (single mutation owner)

/// The only thing that writes the knows-list ledger.
///
/// Views read a snapshot taken when the list appeared and hand every show,
/// open, and dismiss back here; nothing else mutates impression state.
@MainActor
final class HomeKnowsImpressionStore {
  static let shared = HomeKnowsImpressionStore()

  private let persistence: any HomeKnowsImpressionPersisting
  private let now: () -> Date
  private let ownerID: () -> String?
  /// Row keys and slot names already reported during the current visit. One
  /// visit is one impression: the in-visit rotation timer re-renders the same
  /// row every few seconds and must not burn through the show cap.
  private var reportedThisVisit: Set<String> = []
  /// The owner the keys above belong to. The ledger itself is owner-scoped at
  /// every read and write, but this set is not — and a shared key (a suggested
  /// question is keyed by its text) would silence the new owner's first
  /// impression on a switch that leaves the dashboard mounted.
  private var visitOwnerID: String?

  /// `persistence` defaults to owner-scoped `UserDefaults`. It is built inside
  /// the initializer rather than as a default argument because default argument
  /// expressions are evaluated outside this type's actor.
  init(
    persistence: (any HomeKnowsImpressionPersisting)? = nil,
    now: @escaping () -> Date = Date.init,
    ownerID: (() -> String?)? = nil
  ) {
    self.persistence = persistence ?? HomeKnowsImpressionDefaults()
    self.now = now
    self.ownerID = ownerID ?? { RuntimeOwnerIdentity.currentOwnerId() }
  }

  /// Reads through to storage so an account switch cannot be served a cached
  /// ledger from the previous owner.
  func snapshot() -> HomeKnowsImpressionLedger {
    adoptCurrentOwner()
    return persistence.load()
  }

  /// Starts a new visit to the knows-list. Resets in-visit de-duplication.
  func beginVisit() {
    visitOwnerID = ownerID()
    reportedThisVisit.removeAll()
  }

  /// An owner change is the start of a new visit whether or not the view was
  /// rebuilt: the previous owner's keys describe another account's ledger.
  private func adoptCurrentOwner() {
    let current = ownerID()
    guard current != visitOwnerID else { return }
    visitOwnerID = current
    reportedThisVisit.removeAll()
  }

  /// Records a row as shown. Returns the updated impression, or `nil` when this
  /// row was already recorded during the current visit.
  @discardableResult
  func recordShown(key: String, contentHash: String) -> HomeKnowsImpression? {
    adoptCurrentOwner()
    guard reportedThisVisit.insert(key).inserted else { return nil }
    return mutate(key: key) { impression in
      let contentChanged = impression.contentHash != contentHash
      let cooledDown =
        impression.lastOpenedAt == nil
        && impression.shows >= HomeKnowsRotationPolicy.showCapCount
        && self.now().timeIntervalSince(impression.lastShownAt ?? .distantPast)
          >= HomeKnowsRotationPolicy.showCapCooldown
      if contentChanged || cooledDown {
        impression.shows = 0
        impression.firstShownAt = nil
        impression.dismissedAt = nil
      }
      // A prior open belonged to the old text. Carrying it across exempted the
      // new content from the show cap and the same-day rule for good — the one
      // row in the ledger that could repeat itself indefinitely.
      if contentChanged { impression.lastOpenedAt = nil }
      impression.shows += 1
      impression.firstShownAt = impression.firstShownAt ?? self.now()
      impression.lastShownAt = self.now()
      impression.contentHash = contentHash
    }
  }

  @discardableResult
  func recordOpened(key: String, contentHash: String) -> HomeKnowsImpression {
    mutate(key: key) { impression in
      impression.lastOpenedAt = self.now()
      impression.dismissedAt = nil
      impression.contentHash = contentHash
    }
  }

  @discardableResult
  func recordDismissed(key: String, contentHash: String) -> HomeKnowsImpression {
    mutate(key: key) { impression in
      impression.dismissedAt = self.now()
      impression.contentHash = contentHash
    }
  }

  /// True the first time this visit that an empty slot is worth reporting.
  func shouldReportEmptySlot(_ slot: String) -> Bool {
    adoptCurrentOwner()
    return reportedThisVisit.insert("slot:\(slot)").inserted
  }

  @discardableResult
  private func mutate(key: String, _ body: (inout HomeKnowsImpression) -> Void) -> HomeKnowsImpression {
    var ledger = persistence.load()
    var impression = ledger.entries[key] ?? HomeKnowsImpression()
    body(&impression)
    ledger.entries[key] = impression
    persistence.save(ledger)
    return impression
  }
}
