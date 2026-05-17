import Combine
import Foundation

/// Watches trial metadata and posts floating-bar notifications at key thresholds:
/// - 24 hours remaining (once)
/// - 1 hour remaining (once)
/// - Trial expired (once)
///
/// Thresholds are tracked via UserDefaults so they fire at most once per trial period.
@MainActor
final class TrialBannerService {
  static let shared = TrialBannerService()

  private var cancellable: AnyCancellable?
  private static let nudge24hKey = "trial_nudge_24h_shown"
  private static let nudge1hKey = "trial_nudge_1h_shown"
  private static let expiredKey = "trial_expired_banner_shown"

  private init() {}

  /// Start observing trial metadata changes from AppState.
  func start(appState: AppState) {
    cancellable = appState.$trialMetadata
      .compactMap { $0 }
      .sink { [weak self] metadata in
        self?.evaluate(metadata)
      }
  }

  func stop() {
    cancellable?.cancel()
    cancellable = nil
  }

  /// Reset nudge flags (e.g. on sign-out so a new trial gets fresh nudges).
  func reset() {
    UserDefaults.standard.removeObject(forKey: Self.nudge24hKey)
    UserDefaults.standard.removeObject(forKey: Self.nudge1hKey)
    UserDefaults.standard.removeObject(forKey: Self.expiredKey)
  }

  private func evaluate(_ metadata: TrialMetadataResponse) {
    guard metadata.trialStartedAt != nil else { return }

    if metadata.trialExpired {
      showOnce(key: Self.expiredKey, title: "Trial Ended", message: "Your 3-day premium trial has ended. Upgrade to keep unlimited access or bring your own API keys.")
      return
    }

    let remaining = metadata.trialRemainingSeconds
    if remaining <= 3600 {
      showOnce(key: Self.nudge1hKey, title: "Less than 1 hour left", message: "Your premium trial expires soon. Upgrade now to keep unlimited listening & transcription.")
    } else if remaining <= 24 * 3600 {
      showOnce(key: Self.nudge24hKey, title: "Trial ending tomorrow", message: "Your premium trial ends in less than 24 hours. Check out plans in Settings.")
    }
  }

  private func showOnce(key: String, title: String, message: String) {
    guard !UserDefaults.standard.bool(forKey: key) else { return }
    UserDefaults.standard.set(true, forKey: key)

    FloatingControlBarManager.shared.showNotification(
      title: title,
      message: message,
      assistantId: "trial",
      sound: .default
    )
  }
}
