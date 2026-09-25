import Foundation

/// The notch card shown once a detected meeting has actually started
/// recording: a statement, not a prompt.
///
/// It is posted from the meeting boundary *after* the session rotated into the
/// meeting role, so "taking notes" is true when the card says it rather than a
/// prediction that a rotation might succeed. It carries no action — nothing is
/// being asked of the owner — and it is not persistent, so it behaves like the
/// other ambient proactive cards and clears itself.
@MainActor
enum MeetingNoteTakingNotice {
  static let title = "Meeting detected"
  static let message = "Omi is taking notes"

  /// Overridable so a test can observe the decision without a notification
  /// centre or a signed-in owner.
  static var present: () -> Void = {
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
    NotificationService.shared.sendNotification(
      ownerID: snapshot.ownerID,
      title: title,
      message: message,
      assistantId: MeetingActionItemBannerPolicy.assistantID,
      authorizationSnapshot: snapshot
    )
  }
}
