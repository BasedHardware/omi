import Foundation

@testable import Omi_Computer

/// Independent session authority, explicitly injected into hermetic cloud clients.
final class EmbeddingTestAuthorization: @unchecked Sendable {
  let authority = RuntimeOwnerAuthorizationAuthority()
  let ownerID: String
  init(ownerID: String = RewindCaptureOwnerSnapshot.resolvedOwnerID()) { self.ownerID = ownerID }
  var snapshot: RuntimeOwnerAuthorizationSnapshot {
    guard let snapshot = authority.capture(ownerID: ownerID, expectedOwnerID: ownerID) else {
      preconditionFailure("test fixture has no active session")
    }
    return snapshot
  }
  var source: EmbeddingOwnerAuthority {
    EmbeddingOwnerAuthority(
      capture: { [self] in authority.capture(ownerID: ownerID, expectedOwnerID: ownerID) },
      isCurrent: { [self] in authority.isCurrent($0, ownerID: ownerID) })
  }
}
