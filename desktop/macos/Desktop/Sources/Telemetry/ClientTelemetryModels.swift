import CryptoKit
import Foundation

enum ClientTelemetryJSON: Equatable, Sendable {
  case string(String)
  case int(Int)
  case bool(Bool)

  var jsonObject: Any {
    switch self {
    case .string(let value): return value
    case .int(let value): return value
    case .bool(let value): return value
    }
  }

  static func fromPersisted(_ value: Any) -> ClientTelemetryJSON? {
    if let text = value as? String { return .string(text) }
    // sol blocker: JSONSerialization materializes JSON `false`/`true` as
    // CFBoolean-backed NSNumber and JSON `0`/`1` as plain NSNumber, but plain
    // Ints ALSO bridge to Bool transparently in some paths. Check the CF type
    // identity on the NSNumber BEFORE the `as? Bool` bridge, or integer
    // counters (0/1) reload as booleans and fail collector validation.
    if let number = value as? NSNumber {
      if CFGetTypeID(number) == CFBooleanGetTypeID() { return .bool(number.boolValue) }
      return .int(number.intValue)
    }
    if let boolean = value as? Bool { return .bool(boolean) }
    return nil
  }
}

struct ClientTelemetryLimits: Equatable, Sendable {
  var maxObservationsPerBatch = 100
  var maxRequestBytes = 128 * 1024
  var maxObservationBytes = 4 * 1024
  var maxOutboxObservations = 1_000
  var maxOutboxBytes = 1_024 * 1_024
  var maxAge: TimeInterval = 24 * 60 * 60
  var maxFutureSkew: TimeInterval = 5 * 60
  var flushInterval: TimeInterval = 30
  var maxAttempts = 5
  var requestTimeout: TimeInterval = 10
  var retryDelayCaps: [TimeInterval] = [2, 4, 8, 16]
  var maxHonoredRetryAfter: TimeInterval = 300

  static let production = ClientTelemetryLimits()
}

struct ClientTelemetryObservation: Equatable, Sendable {
  var eventID: UUID
  var occurredAt: Date
  var platform: String
  var channel: String
  var family: String
  var attributes: [String: ClientTelemetryJSON]
  var ownerID: String
  var enqueuedAt: Date
  var attemptCount: Int

  func wireObject() -> [String: Any] {
    [
      "attributes": attributes.mapValues { $0.jsonObject },
      "channel": channel,
      "event_id": eventID.uuidString.lowercased(),
      "family": family,
      "occurred_at": ClientTelemetryCodec.iso8601(occurredAt),
      "platform": platform,
    ]
  }

  func encodedObservationBytes() -> Int {
    ClientTelemetryCodec.data(json: wireObject())?.count ?? Int.max
  }
}

struct ClientTelemetryRequest: Sendable {
  var url: URL
  var token: String
  var body: Data
  var timeout: TimeInterval
  var batchID: UUID
  var ownerID: String
}

enum ClientTelemetryHTTPResult: Sendable, Equatable {
  case response(status: Int, retryAfter: TimeInterval?, body: Data)
  case timeout
  case network
}

struct ClientTelemetryDropCounts: Equatable, Sendable {
  var overflowCount = 0
  var overflowBytes = 0
  var ttl = 0
  var oversize = 0
  var invalid = 0
  var permanent = 0
  var exhausted = 0
  var unauthorized = 0
  var conflict = 0
  var unreconciled = 0
  var missingOwner = 0

  mutating func add(_ reason: ClientTelemetryDropReason, bytes: Int = 0) {
    switch reason {
    case .overflowCount: overflowCount += 1
    case .overflowBytes: overflowBytes += max(bytes, 1)
    case .ttl: ttl += 1
    case .oversize: oversize += 1
    case .invalid: invalid += 1
    case .permanent: permanent += 1
    case .exhausted: exhausted += 1
    case .unauthorized: unauthorized += 1
    case .conflict: conflict += 1
    case .unreconciled: unreconciled += 1
    case .missingOwner: missingOwner += 1
    }
  }
}

enum ClientTelemetryDropReason: String, Sendable {
  case overflowCount = "overflow_count"
  case overflowBytes = "overflow_bytes"
  case ttl
  case oversize
  case invalid
  case permanent
  case exhausted
  case unauthorized
  case conflict
  case unreconciled
  case missingOwner = "missing_owner"
}

enum ClientTelemetryCodec {
  static func iso8601(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
  }

  static func date(from text: String) -> Date? {
    let formatter = ISO8601DateFormatter()
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: text) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.date(from: text)
  }

  static func data(json: Any) -> Data? {
    guard JSONSerialization.isValidJSONObject(json) else { return nil }
    return try? JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
  }

  static func object(from data: Data) -> [String: Any]? {
    (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
  }

  static func batchData(batchID: UUID, observations: [ClientTelemetryObservation]) -> Data? {
    let payload: [String: Any] = [
      "batch_id": batchID.uuidString.lowercased(),
      "observations": observations.map { $0.wireObject() },
      "schema_version": 1,
    ]
    return data(json: payload)
  }

  static func ownerFileName(_ ownerID: String) -> String {
    let digest = SHA256.hash(data: Data(ownerID.utf8))
    let hex = digest.map { String(format: "%02x", $0) }.joined()
    return "owner-\(hex).json"
  }

  static func stableUUID(_ raw: String) -> UUID {
    if let parsed = UUID(uuidString: raw) { return parsed }
    let digest = Array(SHA256.hash(data: Data("omi.client.telemetry|\(raw)".utf8)))
    let bytes = (
      digest[0], digest[1], digest[2], digest[3],
      digest[4], digest[5], (digest[6] & 0x0F) | 0x50, digest[7],
      (digest[8] & 0x3F) | 0x80, digest[9], digest[10], digest[11],
      digest[12], digest[13], digest[14], digest[15]
    )
    return UUID(uuid: bytes)
  }
}

enum ClientTelemetryRetryDelay {
  /// Full jitter within the attempt cap. A Retry-After above 300 seconds parks
  /// until a later flush instead of blocking the client.
  static func delay(
    failureIndex: Int,
    retryAfter: TimeInterval?,
    jitterUnit: Double,
    limits: ClientTelemetryLimits
  ) -> TimeInterval? {
    if let retryAfter {
      if retryAfter > limits.maxHonoredRetryAfter { return nil }
      return max(0, retryAfter)
    }
    let caps = limits.retryDelayCaps
    guard !caps.isEmpty else { return 0 }
    let index = min(max(0, failureIndex), caps.count - 1)
    let unit = min(max(jitterUnit, 0), 1)
    return unit * caps[index]
  }
}
