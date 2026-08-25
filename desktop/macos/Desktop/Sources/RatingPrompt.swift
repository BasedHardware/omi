import OmiTheme
import SwiftUI

// MARK: - Policy

/// Decides when the one-time "rate Omi Desktop" ask is due. Pure so the
/// trigger contract stays unit-testable: the prompt appears once the user has
/// asked their 3rd question, and never again after a submit or a dismiss.
enum RatingPromptPolicy {
  static let questionThreshold = 3
  /// Remote kill switch (PostHog feature flag, preloaded at analytics init).
  /// Kill-switch polarity: enabling the flag DISABLES the prompt, so an unset
  /// or unreachable flag (dev builds never initialize PostHog) changes nothing.
  static let killSwitchFlag = "desktop-rating-prompt-disabled"

  static func shouldShow(
    questionCount: Int, submittedRating: Int, dismissed: Bool, remotelyDisabled: Bool = false
  ) -> Bool {
    !remotelyDisabled && questionCount >= questionThreshold && submittedRating == 0 && !dismissed
  }
}

// MARK: - Manager

/// Owns the rating-prompt lifecycle: counts asked questions (fed by the
/// single `AnalyticsManager.chatMessageSent` funnel every chat surface goes
/// through), decides visibility, and reports the submitted rating to PostHog
/// so admin.omi.me can chart it daily.
@MainActor
final class RatingPromptManager: ObservableObject {
  static let shared = RatingPromptManager()

  @Published private(set) var isVisible = false

  private let defaults = UserDefaults.standard
  private var flagObserver: NSObjectProtocol?
  private var flagPollTask: Task<Void, Never>?

  /// Injectable for tests; production reads the preloaded PostHog flag.
  var remoteDisableCheck: () -> Bool = {
    PostHogManager.shared.isFeatureEnabled(RatingPromptPolicy.killSwitchFlag)
  }

  private init() {
    refresh()
    // The kill switch must not wait for the next question: recompute whenever
    // PostHog delivers a flag payload (initial preload can finish AFTER this
    // singleton initializes, and reloads deliver mid-session flips).
    flagObserver = NotificationCenter.default.addObserver(
      forName: PostHogManager.featureFlagsDidLoad,
      object: nil, queue: nil
    ) { _ in
      Task { @MainActor in RatingPromptManager.shared.flagsDidUpdate() }
    }
  }

  func flagsDidUpdate() {
    refresh()
  }

  var questionCount: Int {
    defaults.integer(forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
  }

  var submittedRating: Int {
    defaults.integer(forKey: DefaultsKey.ratingPromptSubmittedRating.rawValue)
  }

  var isDismissed: Bool {
    defaults.bool(forKey: DefaultsKey.ratingPromptDismissed.rawValue)
  }

  func recordQuestionAsked() {
    defaults.set(questionCount + 1, forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
    refresh()
  }

  /// Rating just submitted this session — drives the thank-you state. 4-5
  /// star raters get a refer-a-friend proposal; lower ratings auto-hide.
  @Published private(set) var thankYouRating: Int?

  func submit(rating: Int) {
    let clamped = min(max(rating, 1), 5)
    defaults.set(clamped, forKey: DefaultsKey.ratingPromptSubmittedRating.rawValue)
    AnalyticsManager.shared.desktopRatingSubmitted(rating: clamped)
    thankYouRating = clamped
    refresh()
    if clamped < 4 {
      Task { @MainActor in
        try? await Task.sleep(nanoseconds: 6_000_000_000)
        if self.thankYouRating == clamped { self.closeThankYou() }
      }
    }
  }

  func closeThankYou() {
    thankYouRating = nil
  }

  func referFriend() {
    thankYouRating = nil
    NotificationCenter.default.post(name: .openReferralSheet, object: nil)
  }

  func dismiss() {
    defaults.set(true, forKey: DefaultsKey.ratingPromptDismissed.rawValue)
    refresh()
  }

  /// Automation/testing hook: rewind the persisted state so the real trigger
  /// path can be exercised repeatedly on a dev bundle.
  func resetForTesting() {
    thankYouRating = nil
    defaults.removeObject(forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
    defaults.removeObject(forKey: DefaultsKey.ratingPromptSubmittedRating.rawValue)
    defaults.removeObject(forKey: DefaultsKey.ratingPromptDismissed.rawValue)
    refresh()
  }

  var isRemotelyDisabled: Bool {
    remoteDisableCheck()
  }

  private func refresh() {
    isVisible = RatingPromptPolicy.shouldShow(
      questionCount: questionCount,
      submittedRating: submittedRating,
      dismissed: isDismissed,
      remotelyDisabled: isRemotelyDisabled)
    // While the prompt is on screen, poll for a remote disable so an active
    // kill switch takes effect within minutes, not at the next app launch.
    if isVisible, flagPollTask == nil {
      flagPollTask = Task { @MainActor [weak self] in
        while let self, self.isVisible, !Task.isCancelled {
          try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000)
          PostHogManager.shared.reloadFeatureFlags()
        }
        self?.flagPollTask = nil
      }
    } else if !isVisible {
      flagPollTask?.cancel()
      flagPollTask = nil
    }
  }
}

// MARK: - View

/// Closable sticky bar pinned to the bottom of the main window asking
/// "How would you rate Omi Desktop?" with 1–5 stars.
struct RatingPromptBar: View {
  @ObservedObject private var manager = RatingPromptManager.shared
  @State private var hoveredStar = 0

  var body: some View {
    if let rating = manager.thankYouRating {
      thankYouContent(rating: rating)
    } else if manager.isVisible {
      starsContent
    }
  }

  private var starsContent: some View {
    barChrome {
      Text("How would you rate Omi Desktop?")
        .font(.system(size: 13, weight: .medium))
        .foregroundColor(.primary)

      HStack(spacing: OmiSpacing.xs) {
        ForEach(1...5, id: \.self) { star in
          Button {
            manager.submit(rating: star)
          } label: {
            Image(systemName: star <= hoveredStar ? "star.fill" : "star")
              .font(.system(size: 15))
              .foregroundColor(star <= hoveredStar ? .yellow : .secondary)
          }
          .buttonStyle(.plain)
          .onHover { inside in
            if inside {
              hoveredStar = star
            } else if hoveredStar == star {
              hoveredStar = star - 1
            }
          }
          .accessibilityLabel("Rate \(star) star\(star == 1 ? "" : "s")")
        }
      }

      closeButton { manager.dismiss() }
    }
  }

  private func thankYouContent(rating: Int) -> some View {
    barChrome {
      Text("Thank you!")
        .font(.system(size: 13, weight: .semibold))
        .foregroundColor(.primary)

      if rating >= 4 {
        Text("Enjoying Omi? Give a friend a free month.")
          .font(.system(size: 13))
          .foregroundColor(.secondary)
        Button("Refer a friend") {
          manager.referFriend()
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.small)
        .tint(.primary)
      }

      closeButton { manager.closeThankYou() }
    }
  }

  private func closeButton(_ action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Image(systemName: "xmark")
        .font(.system(size: 11, weight: .semibold))
        .foregroundColor(.secondary)
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Dismiss rating prompt")
  }

  private func barChrome<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
    HStack(spacing: OmiSpacing.lg) {
      content()
    }
    .padding(.horizontal, OmiSpacing.xl)
    .padding(.vertical, OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: 10)
        .fill(.regularMaterial)
        .overlay(
          RoundedRectangle(cornerRadius: 10)
            .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
    )
    // Clears the chat composer row pinned to the window's bottom edge —
    // the prompt must never sit on top of the field the user types in.
    .padding(.bottom, 76)
    .transition(.move(edge: .bottom).combined(with: .opacity))
  }
}
