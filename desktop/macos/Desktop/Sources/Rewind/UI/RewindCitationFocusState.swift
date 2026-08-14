import Foundation

/// One-shot navigation handoff from an inline citation to the Rewind page. The request survives
/// the sidebar transition, then the destination resolves the canonical screenshot locally.
@MainActor
final class RewindCitationFocusState {
  static let shared = RewindCitationFocusState()

  private(set) var pendingScreenshotID: Int64?
  private var pendingOwnerScope: OwnerScope?

  private struct OwnerScope: Equatable {
    let ownerID: String
    let generation: UInt64
  }

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
    pendingScreenshotID = screenshotID
    pendingOwnerScope = OwnerScope(ownerID: ownerSnapshot.ownerID, generation: ownerSnapshot.generation)
    NotificationCenter.default.post(name: .rewindCitationFocusRequested, object: nil)
  }

  func consume() -> Int64? {
    defer { clear() }
    guard let pendingScreenshotID, let pendingOwnerScope,
      let currentOwner = RewindCaptureOwnerSnapshot.capture(),
      pendingOwnerScope == OwnerScope(ownerID: currentOwner.ownerID, generation: currentOwner.generation),
      currentOwner.isCurrent()
    else {
      // A request that outlives its owner is never allowed to resolve by numeric id. Rowids are
      // local to each owner's database, so treating this as a miss is the fail-closed behavior.
      return nil
    }
    return pendingScreenshotID
  }

  private func clear() {
    pendingScreenshotID = nil
    pendingOwnerScope = nil
  }
}

extension Notification.Name {
  static let rewindCitationFocusRequested = Notification.Name("rewindCitationFocusRequested")
}
