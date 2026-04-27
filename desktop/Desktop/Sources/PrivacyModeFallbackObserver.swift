import Foundation
import SwiftUI

/// Observable that surfaces "this request left the EU" events to the UI when
/// the user has EU Privacy Mode enabled but a specific request had to fall
/// back (vision unsupported, regolo outage, 429s exhausted, no regolo key).
///
/// Backend contract: when the user sent ``X-Privacy-Mode: on`` but the
/// request could not actually be served by regolo.ai, the response carries
/// ``X-Privacy-Mode-Fallback: <reason>``. APIClient extracts it and calls
/// ``record(reason:)`` here; the banner view observes the published state.
@MainActor
final class PrivacyModeFallbackObserver: ObservableObject {
  static let shared = PrivacyModeFallbackObserver()

  /// How long a fallback banner stays visible after the last event.
  private static let autoDismissAfter: TimeInterval = 6

  struct Event: Equatable {
    let reason: Reason
    let seenAt: Date
  }

  /// Backend-defined reason tokens — kept in sync with the PRIVACY_FALLBACK_*
  /// constants in backend/utils/byok.py. Unknown reasons surface as ``.other``
  /// so the banner can still show a generic message instead of dropping the
  /// event silently.
  enum Reason: String, CaseIterable {
    case visionUnsupported = "vision_unsupported"
    case regoloOutage = "regolo_outage"
    case regoloRateLimited = "regolo_rate_limited"
    case noRegoloKey = "no_regolo_key"
    case other = ""

    init(rawValueOrOther raw: String) {
      self = Reason(rawValue: raw) ?? .other
    }

    /// One-line banner copy. Deliberately terse — the banner is transient.
    var displayMessage: String {
      switch self {
      case .visionUnsupported:
        return "Vision isn't available on regolo.ai — this screenshot was processed by Gemini."
      case .regoloOutage:
        return "Regolo.ai is unreachable — falling back to your regular LLM provider."
      case .regoloRateLimited:
        return "Regolo.ai rate limit hit — falling back to your regular LLM provider."
      case .noRegoloKey:
        return "EU Privacy Mode is on but no Regolo key is configured. Add one in Settings."
      case .other:
        return "This request left the EU."
      }
    }
  }

  @Published private(set) var currentEvent: Event?

  /// Rolling 7-day count of fallback events, surfaced in Settings as
  /// "N requests fell back this week". Persisted across app restarts via
  /// UserDefaults; auto-resets when the 7-day window rolls over.
  @Published private(set) var weeklyFallbackCount: Int = 0

  private static let weeklyCountKey = "eu_privacy_fallback_count_week"
  private static let weeklyCountResetAtKey = "eu_privacy_fallback_count_week_reset_at"
  private static let weekSeconds: TimeInterval = 7 * 24 * 60 * 60

  private var dismissTask: Task<Void, Never>?

  private init() {
    weeklyFallbackCount = Self.loadCounterRollingOverIfStale()
  }

  /// Call from APIClient when the backend sends X-Privacy-Mode-Fallback.
  /// Nothing happens if the user has Privacy Mode disabled — nothing to warn
  /// about in that case.
  func record(rawReason: String) {
    guard APIKeyService.isEUPrivacyModeEnabled else { return }
    let reason = Reason(rawValueOrOther: rawReason)
    currentEvent = Event(reason: reason, seenAt: Date())
    weeklyFallbackCount = Self.bumpCounter()
    scheduleAutoDismiss()
  }

  // MARK: - Weekly counter persistence

  /// Read the persisted weekly counter, resetting if the 7-day window expired.
  private static func loadCounterRollingOverIfStale() -> Int {
    let defaults = UserDefaults.standard
    let resetAt = defaults.double(forKey: weeklyCountResetAtKey)
    let now = Date().timeIntervalSince1970
    if resetAt == 0 || now - resetAt >= weekSeconds {
      defaults.set(0, forKey: weeklyCountKey)
      defaults.set(now, forKey: weeklyCountResetAtKey)
      return 0
    }
    return defaults.integer(forKey: weeklyCountKey)
  }

  /// Increment the weekly counter, rolling over the window first if stale.
  private static func bumpCounter() -> Int {
    let defaults = UserDefaults.standard
    let next = loadCounterRollingOverIfStale() + 1
    defaults.set(next, forKey: weeklyCountKey)
    return next
  }

  /// User-initiated dismissal (tap the banner).
  func dismiss() {
    dismissTask?.cancel()
    currentEvent = nil
  }

  private func scheduleAutoDismiss() {
    dismissTask?.cancel()
    dismissTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(Self.autoDismissAfter * 1_000_000_000))
      guard !Task.isCancelled else { return }
      await MainActor.run { self?.currentEvent = nil }
    }
  }
}

/// Small red banner shown at the top of the main window when a fallback
/// event is active. Host views embed it with ``.safeAreaInset(edge: .top)``
/// or overlay at the top.
struct PrivacyModeFallbackBanner: View {
  @ObservedObject private var observer = PrivacyModeFallbackObserver.shared

  var body: some View {
    if let event = observer.currentEvent {
      HStack(spacing: 10) {
        Image(systemName: "exclamationmark.triangle.fill")
          .foregroundColor(.white)

        Text(event.reason.displayMessage)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(.white)
          .fixedSize(horizontal: false, vertical: true)

        Spacer(minLength: 8)

        Button(action: { observer.dismiss() }) {
          Image(systemName: "xmark")
            .foregroundColor(.white.opacity(0.85))
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, 14)
      .padding(.vertical, 8)
      .background(Color.red.opacity(0.85))
      .transition(.move(edge: .top).combined(with: .opacity))
    }
  }
}
