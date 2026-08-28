import Foundation

/// One-shot navigation handoff from an inline citation to the Rewind page. The request survives
/// the sidebar transition, then the destination resolves the canonical screenshot locally.
@MainActor
final class RewindCitationFocusState {
  static let shared = RewindCitationFocusState()

  /// The one-shot request carries the complete authorization snapshot rather than only a user id
  /// and generation. A same-uid sign-out/sign-in must not be able to reuse a row id while an async
  /// destination lookup is suspended.
  struct Request: Equatable, Sendable {
    let screenshotID: Int64
    let owner: RewindCaptureOwnerSnapshot
  }

  private(set) var pendingRequest: Request?

  /// Compatibility projection for callers/tests that only need to inspect the queued row id.
  var pendingScreenshotID: Int64? { pendingRequest?.screenshotID }

  private init() {
    // The singleton lives for the process lifetime, so the notification token does not need a
    // teardown path. Clearing on the owner transition is the important part of the contract.
    NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      Task { @MainActor [weak self] in
        self?.clear()
      }
    }
  }

  /// Accept only a real SQLite row id. Callers that start with an untrusted citation source id
  /// must use this parser before changing navigation state; zero, negative, empty, and overflowing
  /// values are not screenshot identities.
  static func parseScreenshotID(_ sourceID: String) -> Int64? {
    let normalized = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty, let id = Int64(normalized), id > 0 else { return nil }
    return id
  }

  func request(_ screenshotID: Int64) {
    guard screenshotID > 0, let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else {
      clear()
      return
    }
    pendingRequest = Request(screenshotID: screenshotID, owner: ownerSnapshot)
    NotificationCenter.default.post(name: .rewindCitationFocusRequested, object: nil)
  }

  /// Consume the request only when the complete owner lease is still current. The returned lease
  /// must be passed through every asynchronous read and into the timeline admission boundary.
  func consumeRequest() -> Request? {
    defer { clear() }
    guard let request = pendingRequest,
      Self.isCurrent(owner: request.owner)
    else {
      // A request that outlives its owner is never allowed to resolve by numeric id. Rowids are
      // local to each owner's database, so treating this as a miss is the fail-closed behavior.
      return nil
    }
    return request
  }

  func consume() -> Int64? {
    consumeRequest()?.screenshotID
  }

  static func isCurrent(owner: RewindCaptureOwnerSnapshot) -> Bool {
    guard let currentOwner = RewindCaptureOwnerSnapshot.capture() else { return false }
    return currentOwner == owner && owner.isCurrent()
  }

  private func clear() {
    pendingRequest = nil
  }
}

extension Notification.Name {
  static let rewindCitationFocusRequested = Notification.Name("rewindCitationFocusRequested")
}

enum RewindCitationUnavailablePresentationPolicy {
  static let title = "Rewind frame unavailable"
  static let hint = "No frame was opened because it is no longer available on this Mac."

  static func message(for screenshotID: Int64) -> String {
    "Frame \(screenshotID) is no longer available locally. It may have been pruned."
  }
}
