import Combine
import CryptoKit
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
  enum NudgeKind: String {
    case twentyFourHours = "24h"
    case oneHour = "1h"
    case expired
  }

  typealias NotificationPresenter =
    @MainActor (
      _ ownerID: String,
      _ title: String,
      _ message: String
    ) -> OwnerBoundNotificationPresentationResult

  private var activeOwnerID: String?

  init() {}

  /// Start observing trial metadata changes from AppState.
  func start(
    appState: AppState,
    presenter: @escaping NotificationPresenter = { ownerID, title, message in
      FloatingControlBarManager.shared.showNotification(
        ownerID: ownerID,
        title: title,
        message: message,
        assistantId: "trial",
        sound: .default
      )
    }
  ) {
    cancellable?.cancel()
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else {
      activeOwnerID = nil
      cancellable = nil
      return
    }
    activeOwnerID = ownerID
    cancellable = appState.$trialMetadata
      .compactMap { $0 }
      .sink { [weak self, ownerID] metadata in
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
        self?.evaluate(metadata, ownerID: ownerID, presenter: presenter)
      }
  }

  func stop() {
    cancellable?.cancel()
    cancellable = nil
    activeOwnerID = nil
  }

  /// Reset nudge flags (e.g. on sign-out so a new trial gets fresh nudges).
  func reset() {
    guard let ownerID = activeOwnerID ?? RuntimeOwnerIdentity.currentOwnerId() else { return }
    for kind in [NudgeKind.twentyFourHours, .oneHour, .expired] {
      UserDefaults.standard.removeObject(forKey: Self.nudgeKey(kind, ownerID: ownerID))
    }
  }

  private func evaluate(
    _ metadata: TrialMetadataResponse,
    ownerID: String,
    presenter: NotificationPresenter
  ) {
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
    guard metadata.trialStartedAt != nil else { return }

    if metadata.trialExpired {
      showOnce(
        kind: .expired,
        ownerID: ownerID,
        title: "Trial Ended",
        message: "Your 3-day premium trial has ended. Upgrade to keep unlimited access or bring your own API keys.",
        presenter: presenter)
      return
    }

    let remaining = metadata.trialRemainingSeconds
    if remaining <= 3600 {
      showOnce(
        kind: .oneHour,
        ownerID: ownerID,
        title: "Less than 1 hour left",
        message: "Your premium trial expires soon. Upgrade now to keep unlimited listening & transcription.",
        presenter: presenter)
    } else if remaining <= 24 * 3600 {
      showOnce(
        kind: .twentyFourHours,
        ownerID: ownerID,
        title: "Trial ending tomorrow",
        message: "Your premium trial ends in less than 24 hours. Check out plans in Settings.",
        presenter: presenter)
    }
  }

  private func showOnce(
    kind: NudgeKind,
    ownerID: String,
    title: String,
    message: String,
    presenter: NotificationPresenter
  ) {
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
    let key = Self.nudgeKey(kind, ownerID: ownerID)
    guard !UserDefaults.standard.bool(forKey: key) else { return }

    let result = presenter(ownerID, title, message)
    if result == .presented || result == .queued {
      Self.recordNudge(kind, ownerID: ownerID)
    }
  }

  static func hasRecordedNudge(_ kind: NudgeKind, ownerID: String) -> Bool {
    UserDefaults.standard.bool(forKey: nudgeKey(kind, ownerID: ownerID))
  }

  static func clearRecordedNudges(ownerID: String) {
    for kind in [NudgeKind.twentyFourHours, .oneHour, .expired] {
      UserDefaults.standard.removeObject(forKey: nudgeKey(kind, ownerID: ownerID))
    }
  }

  static func recordNudge(_ kind: NudgeKind, ownerID: String) {
    UserDefaults.standard.set(true, forKey: nudgeKey(kind, ownerID: ownerID))
  }

  private static func nudgeKey(_ kind: NudgeKind, ownerID: String) -> ScopedDefaultsKey {
    let digest = SHA256.hash(data: Data(ownerID.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
    return .trialNudge(kind.rawValue, ownerHash: String(digest.prefix(24)))
  }
}
