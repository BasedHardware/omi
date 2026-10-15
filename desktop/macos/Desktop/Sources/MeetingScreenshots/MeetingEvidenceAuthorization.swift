//
//  MeetingEvidenceAuthorization.swift — the owner a background evidence upload is bound to.
//
//  Screen evidence is read from the signed-in owner's local stores (Rewind frames, OCR rows) and
//  uploaded after several awaits. An account switch in between must never send owner A's screen
//  under owner B's credentials (`product/invariants/auth-session.md`, owner-bound background sync).
//  So a pass captures one owner snapshot before it reads anything, revalidates it after every
//  read and before every upload, and binds each upload's transport auth to that owner.
//

import Foundation

struct MeetingEvidenceAuthorization: Sendable {
  /// The owner bound into transport auth; nil only for the test binding.
  let snapshot: RuntimeOwnerAuthorizationSnapshot?
  private let current: @Sendable () -> Bool

  /// Whether the captured owner is still the signed-in owner, with the same session.
  var isCurrent: Bool { current() }

  /// The signed-in owner now, or nil when there is none (signed out, or mid account switch).
  static func captureCurrentOwner() -> MeetingEvidenceAuthorization? {
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return nil }
    return MeetingEvidenceAuthorization(
      snapshot: snapshot, current: { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) })
  }

  /// A binding whose validity a test controls. Carries no snapshot, so it binds no transport.
  static func forTesting(isCurrent: @escaping @Sendable () -> Bool = { true }) -> MeetingEvidenceAuthorization {
    MeetingEvidenceAuthorization(snapshot: nil, current: isCurrent)
  }
}

enum MeetingEvidenceAuthorizationError: Error, LocalizedError, Equatable {
  /// No signed-in owner to bind to, or the owner changed after the evidence was read.
  case ownerChanged

  var errorDescription: String? { "The signed-in account changed during the screen evidence pass." }
}
