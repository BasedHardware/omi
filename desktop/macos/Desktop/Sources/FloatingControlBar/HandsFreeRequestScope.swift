import Foundation

/// One hands-free (wake word) command on its way through the floating bar's chat route: the
/// account that spoke it, and an identity for the presentation state it arms.
struct HandsFreeRequest: Equatable, Sendable {
  let origin: RuntimeOwnerAuthorizationSnapshot
  let id: UUID

  init(origin: RuntimeOwnerAuthorizationSnapshot, id: UUID = UUID()) {
    self.origin = origin
    self.id = id
  }

  /// False once the account has changed, including a sign-out and sign-in as the same user.
  var isCurrent: Bool { RuntimeOwnerIdentity.isAuthorizationCurrent(origin) }
}

/// Quiets the visible surface for exactly the request that armed it.
///
/// A global "next query is quiet" flag outlived any request that was rejected before
/// presenting, and then hid the answer to the user's next typed question. Scoping the arm to
/// one request means a rejected request releases only its own arm, and an older request can
/// never consume or clear a newer one's.
struct QuietSurfaceLatch {
  private(set) var armedFor: UUID?

  mutating func arm(_ id: UUID) { armedFor = id }

  /// Whether this query presents the surface. Only the armed request is quiet, and it
  /// consumes its arm.
  mutating func presentsSurface(for id: UUID?) -> Bool {
    guard let id, armedFor == id else { return true }
    armedFor = nil
    return false
  }

  /// A request that ends without presenting releases its own arm, never another's.
  mutating func release(_ id: UUID?) {
    if let id, armedFor == id { armedFor = nil }
  }
}

/// One queued query. A query that belongs to a hands-free request is handed out at most once,
/// and only while that request's account is still current.
struct RequestBoundSlot<Payload> {
  private var held: (payload: Payload, request: HandsFreeRequest?)?

  mutating func put(_ payload: Payload, request: HandsFreeRequest?) { held = (payload, request) }

  mutating func clear() { held = nil }

  /// The queued query and its request, or nil when nothing is queued or its account changed.
  mutating func take() -> (payload: Payload, request: HandsFreeRequest?)? {
    guard let held else { return nil }
    self.held = nil
    if let request = held.request, !request.isCurrent { return nil }
    return held
  }
}
