import Foundation

/// One-shot navigation handoff from an inline citation to the Rewind page. The request survives
/// the sidebar transition, then the destination resolves the canonical screenshot locally.
@MainActor
final class RewindCitationFocusState {
  static let shared = RewindCitationFocusState()

  private(set) var pendingScreenshotID: Int64?

  private init() {}

  func request(_ screenshotID: Int64) {
    pendingScreenshotID = screenshotID
    NotificationCenter.default.post(name: .rewindCitationFocusRequested, object: nil)
  }

  func consume() -> Int64? {
    defer { pendingScreenshotID = nil }
    return pendingScreenshotID
  }
}

extension Notification.Name {
  static let rewindCitationFocusRequested = Notification.Name("rewindCitationFocusRequested")
}
