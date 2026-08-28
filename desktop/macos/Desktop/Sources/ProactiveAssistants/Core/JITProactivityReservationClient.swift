import CryptoKit
import Foundation

enum JITProactivityOperation: String, Codable, Sendable {
  case plannedNotification = "planned_notification"
  case ambientNotification = "ambient_notification"
  case nanoTriage = "nano_triage"
  case fullTurn = "full_turn"
}

struct JITProactivityReservation: Equatable, Sendable {
  let eventID: String
  let candidateID: String
  let operation: JITProactivityOperation
  let accountGeneration: Int
  let triggerMemoryID: String?
  let triggerRevision: Int?
  let parentEventID: String?

  var acceptsExistingReceipt: Bool {
    operation == .plannedNotification || operation == .ambientNotification
  }

  init(
    eventID: String, candidateID: String, operation: JITProactivityOperation,
    accountGeneration: Int, triggerMemoryID: String?, triggerRevision: Int?,
    parentEventID: String? = nil
  ) {
    self.eventID = eventID
    self.candidateID = candidateID
    self.operation = operation
    self.accountGeneration = accountGeneration
    self.triggerMemoryID = triggerMemoryID
    self.triggerRevision = triggerRevision
    self.parentEventID = parentEventID
  }

  /// Derive a deterministic local join key without exposing a dictionary
  /// oracle. The persisted installation identity is random and private to the
  /// install; callers may use this overload in hermetic tests with a known
  /// key, but retained payloads only contain the resulting HMAC digest.
  static func opaqueIdentifier(_ components: [String], installationIdentity: String) -> String {
    let payload = Data(components.joined(separator: "\u{1f}").utf8)
    let key = SymmetricKey(data: Data(installationIdentity.utf8))
    return HMAC<SHA256>.authenticationCode(for: payload, using: key)
      .map { String(format: "%02x", $0) }.joined()
  }

  static func identifier(_ components: String...) -> String {
    opaqueIdentifier(
      components,
      installationIdentity: ClientDeviceService.shared.installationIdentity)
  }

  static func isIdentifier(_ value: String) -> Bool {
    let lowercaseHex = Set("0123456789abcdef")
    return value.count == 64 && value.allSatisfy(lowercaseHex.contains)
  }
}

private struct JITProactivityReservationRequest: Encodable {
  let eventID: String
  let candidateID: String
  let operation: JITProactivityOperation
  let accountGeneration: Int
  let deviceID: String
  let triggerMemoryID: String?
  let triggerRevision: Int?
  let parentEventID: String?

  enum CodingKeys: String, CodingKey {
    case eventID = "event_id"
    case candidateID = "candidate_id"
    case operation
    case accountGeneration = "account_generation"
    case deviceID = "device_id"
    case triggerMemoryID = "trigger_memory_id"
    case triggerRevision = "trigger_revision"
    case parentEventID = "parent_event_id"
  }
}

struct JITProactivityReservationReceipt: Decodable {
  let eventID: String
  let candidateID: String
  let operation: JITProactivityOperation
  let accountGeneration: Int
  let deviceID: String
  let triggerMemoryID: String?
  let triggerRevision: Int?
  let parentEventID: String?

  enum CodingKeys: String, CodingKey {
    case eventID = "event_id"
    case candidateID = "candidate_id"
    case operation
    case accountGeneration = "account_generation"
    case deviceID = "device_id"
    case triggerMemoryID = "trigger_memory_id"
    case triggerRevision = "trigger_revision"
    case parentEventID = "parent_event_id"
  }
}

struct JITProactivityReservationEnvelope: Decodable {
  let reserved: Bool
  let receipt: JITProactivityReservationReceipt
}

actor JITProactivityReservationClient {
  static let shared = JITProactivityReservationClient()

  private let session: URLSession
  private let baseURL: @Sendable () -> String

  init(
    session: URLSession = .shared,
    baseURL: @escaping @Sendable () -> String = { ProactiveLaneClient.backendBaseURL }
  ) {
    self.session = session
    self.baseURL = baseURL
  }

  static func validates(
    _ envelope: JITProactivityReservationEnvelope,
    reservation: JITProactivityReservation,
    deviceID: String
  ) -> Bool {
    let receipt = envelope.receipt
    return receipt.eventID == reservation.eventID
      && receipt.candidateID == reservation.candidateID
      && receipt.operation == reservation.operation
      && receipt.accountGeneration == reservation.accountGeneration
      && receipt.deviceID == deviceID
      && receipt.triggerMemoryID == reservation.triggerMemoryID
      && receipt.triggerRevision == reservation.triggerRevision
      && receipt.parentEventID == reservation.parentEventID
      && (envelope.reserved || reservation.acceptsExistingReceipt)
  }

  func reserve(
    _ reservation: JITProactivityReservation,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> Bool {
    guard reservation.accountGeneration >= 0,
      JITProactivityReservation.isIdentifier(reservation.eventID),
      JITProactivityReservation.isIdentifier(reservation.candidateID),
      reservation.parentEventID.map(JITProactivityReservation.isIdentifier) ?? true,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      (reservation.triggerMemoryID == nil) == (reservation.triggerRevision == nil),
      reservation.operation != .plannedNotification || reservation.triggerMemoryID != nil,
      (reservation.operation == .fullTurn) == (reservation.parentEventID != nil)
    else { return false }
    let root = baseURL().hasSuffix("/") ? baseURL() : baseURL() + "/"
    guard let url = URL(string: root + "v1/jit/proactivity/reservations") else { return false }
    do {
      let authService = await MainActor.run { AuthService.shared }
      let header = try await authService.getAuthHeader(expectedUserId: authorizationSnapshot.ownerID)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
      var request = URLRequest(url: url)
      request.httpMethod = "POST"
      request.setValue(header, forHTTPHeaderField: "Authorization")
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.timeoutInterval = 15
      let deviceID = JITProactivityReservation.identifier(
        "device", ClientDeviceService.shared.installationIdentity)
      request.httpBody = try JSONEncoder().encode(
        JITProactivityReservationRequest(
          eventID: reservation.eventID,
          candidateID: reservation.candidateID,
          operation: reservation.operation,
          accountGeneration: reservation.accountGeneration,
          deviceID: deviceID,
          triggerMemoryID: reservation.triggerMemoryID,
          triggerRevision: reservation.triggerRevision,
          parentEventID: reservation.parentEventID))
      let (data, response) = try await session.data(for: request)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        let http = response as? HTTPURLResponse,
        (200..<300).contains(http.statusCode)
      else { return false }
      guard let envelope = try? JSONDecoder().decode(JITProactivityReservationEnvelope.self, from: data) else {
        return false
      }
      return Self.validates(envelope, reservation: reservation, deviceID: deviceID)
    } catch {
      return false
    }
  }
}
