import CryptoKit
import Foundation

/// The 90% / 100% chat-quota warning shown above the chat composer.
///
/// A state, not an event: it is derived from the current quota snapshot every
/// time usage moves, so it needs no scheduling and cannot be missed. The user
/// can dismiss one, and it stays dismissed only for that threshold in that
/// billing cycle — crossing the next threshold speaks again.
struct ChatQuotaBanner: Equatable {
  static let thresholds = [90, 100]

  let threshold: Int
  let title: String
  let message: String
  /// The count in six words, for the banner's single compact line: the full
  /// `message` lives in the accessibility label and the plan page.
  let summary: String
  /// Usage as a whole percent of the allowance, clamped to 100 — the meter's
  /// fill. A banner is only ever raised at a threshold, so this is never
  /// below the smallest one.
  let percent: Int
  /// Past the allowance on an overage plan: billed, not blocked.
  let isBillingOverage: Bool
  /// The billing cycle and allowance this banner was computed against.
  let cycleID: String

  /// The banner for the current usage, or nil when there is nothing to warn
  /// about (unlimited or BYOK quota, or the highest crossed threshold was
  /// already dismissed this cycle).
  static func current(
    quota: APIClient.ChatUsageQuota?,
    optimisticDelta: Int,
    dismissed: Set<String>,
    now: Date = Date()
  ) -> ChatQuotaBanner? {
    guard let quota, let limit = quota.limit, limit > 0 else { return nil }
    // Only question quotas can be counted locally; a cost_usd plan has no
    // per-query estimate, so its usage moves on server syncs alone.
    let used = quota.unit == "questions" ? quota.used + Double(optimisticDelta) : quota.used
    let percent = 100.0 * used / limit
    guard let threshold = thresholds.last(where: { Double($0) <= percent }) else { return nil }
    let cycle = cycleID(for: quota)
    guard !dismissed.contains(dismissalKey(threshold: threshold, cycleID: cycle)) else { return nil }

    let overage = threshold >= 100 && quota.isOveragePlan == true
    return ChatQuotaBanner(
      threshold: threshold,
      title: title(threshold: threshold, isBillingOverage: overage),
      message: message(
        threshold: threshold, isBillingOverage: overage, quota: quota, used: used, limit: limit,
        now: now),
      summary: summary(quota: quota, used: used, limit: limit),
      // Floor, not round: the meter must never read full before the allowance
      // actually is (99.8% is not "at your limit").
      percent: min(100, Int(percent)),
      isBillingOverage: overage,
      cycleID: cycle)
  }

  /// Identifies the billing cycle AND the allowance in force during it, so an
  /// upgrade mid-cycle speaks again rather than staying dismissed against a
  /// limit that no longer applies.
  static func cycleID(for quota: APIClient.ChatUsageQuota) -> String {
    "\(quota.resetAt ?? 0)-\(Int(quota.limit ?? 0))"
  }

  static func dismissalKey(threshold: Int, cycleID: String) -> String {
    "\(threshold)@\(cycleID)"
  }

  private static func title(threshold: Int, isBillingOverage: Bool) -> String {
    guard threshold >= 100 else { return "Almost at your monthly limit" }
    return isBillingOverage ? "Now billing overage" : "Monthly limit reached"
  }

  private static func summary(quota: APIClient.ChatUsageQuota, used: Double, limit: Double)
    -> String
  {
    if quota.unit == "cost_usd" {
      return String(format: "$%.0f of $%.0f used", used, limit)
    }
    return "\(Int(used)) of \(Int(limit)) used"
  }

  private static func message(
    threshold: Int,
    isBillingOverage: Bool,
    quota: APIClient.ChatUsageQuota,
    used: Double,
    limit: Double,
    now: Date
  ) -> String {
    let allowance: String
    if quota.unit == "cost_usd" {
      allowance = String(
        format: "$%.2f of your $%.0f %@ monthly spend used.", used, limit, quota.plan)
    } else {
      allowance = "\(Int(used)) of \(Int(limit)) \(quota.plan) questions used."
    }
    let tail: String
    if threshold < 100 {
      tail = ""
    } else if isBillingOverage {
      tail = " Extra usage is billed at the end of your cycle."
    } else {
      tail = " Upgrade to keep chatting."
    }
    return "\(allowance)\(tail) \(resetText(quota.resetAt, now: now))."
  }

  /// Mirrors `SettingsContentView.chatUsageQuotaResetText` so the plan page and
  /// this banner never disagree about when the cycle turns over.
  static func resetText(_ resetAt: Int?, now: Date = Date()) -> String {
    guard let resetAt else { return "Resets next month" }
    let days = max(
      0, Int(Date(timeIntervalSince1970: TimeInterval(resetAt)).timeIntervalSince(now) / 86400))
    if days <= 0 { return "Resets today" }
    if days == 1 { return "Resets tomorrow" }
    return "Resets in \(days) days"
  }
}

/// Per-user record of which quota warnings have been dismissed. Persisted so a
/// dismissal survives relaunch, and scoped to the runtime owner so signing in
/// as someone else never inherits their dismissals.
@MainActor
final class ChatQuotaBannerDismissals: ObservableObject {
  static let shared = ChatQuotaBannerDismissals()

  @Published private(set) var dismissed: Set<String> = []

  private let defaults: UserDefaults
  /// The owner `dismissed` was loaded for. Startup reaches this before auth
  /// settles, so the first load can be for no owner at all; without tracking it
  /// the set would be read from one bucket and written to another.
  private var loadedOwner: String?

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    load()
    // The center owns the observation; this store lives for the process, so
    // there is no token to retain and nothing to tear down.
    NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      Task { @MainActor in self?.load() }
    }
  }

  /// Records a dismissal, dropping any from an earlier cycle: only the current
  /// one can still be consulted, so the stored set stays bounded by the number
  /// of thresholds rather than growing for the life of the account.
  func dismiss(threshold: Int, cycleID: String) {
    load()
    let suffix = "@\(cycleID)"
    dismissed =
      dismissed.filter { $0.hasSuffix(suffix) }
      .union([ChatQuotaBanner.dismissalKey(threshold: threshold, cycleID: cycleID)])
    defaults.set(Array(dismissed), forKey: Self.storageKey(owner: loadedOwner))
  }

  func reset() {
    dismissed = []
    defaults.removeObject(forKey: Self.storageKey(owner: loadedOwner))
  }

  /// Reloads when the runtime owner has changed since the last read.
  private func load() {
    let owner = RuntimeOwnerIdentity.currentOwnerId()
    guard owner != loadedOwner || dismissed.isEmpty else { return }
    loadedOwner = owner
    dismissed = Set(defaults.stringArray(forKey: Self.storageKey(owner: owner)) ?? [])
  }

  /// Hashed, never the raw uid: this is a `UserDefaults` key name, which is
  /// readable by anything that can read the domain.
  private static func storageKey(owner: String?) -> ScopedDefaultsKey {
    guard let owner, !owner.isEmpty else {
      return .chatQuotaBannerDismissals(ownerHash: "anonymous")
    }
    let digest = SHA256.hash(data: Data(owner.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
    return .chatQuotaBannerDismissals(ownerHash: String(digest.prefix(24)))
  }
}

/// What the banner view last rendered, for the automation bridge.
///
/// `ChatQuotaBanner.current` says what *should* show; this says what a mounted
/// `ChatQuotaBannerView.Slot` actually put on screen. An e2e flow asserting only
/// the former proves the arithmetic and nothing about the surface.
@MainActor
final class ChatQuotaBannerPresentation {
  static let shared = ChatQuotaBannerPresentation()

  private(set) var rendered: ChatQuotaBanner?

  func record(_ banner: ChatQuotaBanner?) {
    rendered = banner
  }
}
