import Foundation

/// Per-owner outbox. Owner ids stay in this local file and never enter the request body.
/// The transport actor is the only caller; the class is not independently synchronized.
final class ClientTelemetryStore: @unchecked Sendable {
  let directory: URL
  let limits: ClientTelemetryLimits
  private(set) var dropCounts = ClientTelemetryDropCounts()

  init(directory: URL, limits: ClientTelemetryLimits) {
    self.directory = directory
    self.limits = limits
    dropCounts = Self.loadDrops(directory: directory)
  }

  func observations(ownerID: String) -> [ClientTelemetryObservation] {
    load(ownerID: ownerID)?.observations ?? []
  }

  func knownOwnerIDs() -> [String] {
    guard let data = try? Data(contentsOf: indexURL),
      let object = ClientTelemetryCodec.object(from: data),
      let owners = object["owners"] as? [String]
    else { return [] }
    return owners
  }

  @discardableResult
  func enqueue(_ observation: ClientTelemetryObservation, now: Date) -> Bool {
    if observation.occurredAt.timeIntervalSince(now) > limits.maxFutureSkew {
      note(.invalid)
      return false
    }
    if now.timeIntervalSince(observation.occurredAt) > limits.maxAge {
      note(.ttl)
      return false
    }
    if observation.encodedObservationBytes() > limits.maxObservationBytes {
      note(.oversize)
      return false
    }
    var record =
      load(ownerID: observation.ownerID) ?? OwnerRecord(ownerID: observation.ownerID, observations: [], notBefore: nil)
    if record.observations.contains(where: { $0.eventID == observation.eventID }) {
      return false
    }
    record.observations.append(observation)
    trim(&record, now: now)
    save(record)
    remember(observation.ownerID)
    return true
  }

  func expire(ownerID: String, now: Date) {
    guard var record = load(ownerID: ownerID) else { return }
    let before = record.observations.count
    record.observations.removeAll { now.timeIntervalSince($0.occurredAt) > limits.maxAge }
    let removed = before - record.observations.count
    if removed > 0 {
      for _ in 0..<removed { note(.ttl) }
      save(record)
    }
  }

  func incrementAttempts(ownerID: String, eventIDs: Set<UUID>) {
    guard var record = load(ownerID: ownerID) else { return }
    for index in record.observations.indices where eventIDs.contains(record.observations[index].eventID) {
      record.observations[index].attemptCount += 1
    }
    save(record)
  }

  /// sol blocker: durable parking window (429 Retry-After over the honored
  /// cap). Persisted inside the owner record so a restart respects it.
  func setNotBefore(ownerID: String, until: Date) {
    guard var record = load(ownerID: ownerID) else { return }
    if let existing = record.notBefore, existing >= until { return }
    record.notBefore = until
    save(record)
  }

  func notBefore(ownerID: String) -> Date? {
    return load(ownerID: ownerID)?.notBefore
  }

  func remove(ownerID: String, eventIDs: Set<UUID>) {
    guard var record = load(ownerID: ownerID) else { return }
    record.observations.removeAll { eventIDs.contains($0.eventID) }
    save(record)
  }

  func purgeOwner(_ ownerID: String) {
    try? FileManager.default.removeItem(at: fileURL(ownerID))
    var owners = knownOwnerIDs()
    owners.removeAll { $0 == ownerID }
    writeIndex(owners)
  }

  func purgeOwners(except ownerID: String?) {
    for owner in knownOwnerIDs() where owner != ownerID {
      purgeOwner(owner)
    }
  }

  func note(_ reason: ClientTelemetryDropReason, bytes: Int = 0) {
    dropCounts.add(reason, bytes: bytes)
    persistDrops()
  }

  private struct OwnerRecord {
    var ownerID: String
    var observations: [ClientTelemetryObservation]
    var notBefore: Date?
  }

  private func trim(_ record: inout OwnerRecord, now: Date) {
    record.observations.removeAll { observation in
      let stale = now.timeIntervalSince(observation.occurredAt) > limits.maxAge
      if stale { note(.ttl) }
      return stale
    }
    record.observations.sort { lhs, rhs in
      if lhs.enqueuedAt != rhs.enqueuedAt { return lhs.enqueuedAt < rhs.enqueuedAt }
      return lhs.eventID.uuidString < rhs.eventID.uuidString
    }
    while record.observations.count > limits.maxOutboxObservations {
      record.observations.removeFirst()
      note(.overflowCount)
    }
    while encodedBytes(record.observations) > limits.maxOutboxBytes, !record.observations.isEmpty {
      let dropped = record.observations.removeFirst()
      note(.overflowBytes, bytes: dropped.encodedObservationBytes())
    }
  }

  private func encodedBytes(_ observations: [ClientTelemetryObservation]) -> Int {
    observations.reduce(0) { $0 + $1.encodedObservationBytes() }
  }

  private func fileURL(_ ownerID: String) -> URL {
    directory.appendingPathComponent(ClientTelemetryCodec.ownerFileName(ownerID))
  }

  private var indexURL: URL { directory.appendingPathComponent("owners.json") }
  private var dropsURL: URL { directory.appendingPathComponent("drops.json") }

  private func load(ownerID: String) -> OwnerRecord? {
    guard let data = try? Data(contentsOf: fileURL(ownerID)),
      let object = ClientTelemetryCodec.object(from: data),
      let storedOwner = object["owner_id"] as? String,
      storedOwner == ownerID,
      let rows = object["observations"] as? [[String: Any]]
    else { return nil }
    let observations = rows.compactMap { Self.observation(ownerID: ownerID, row: $0) }
    let notBefore = (object["not_before"] as? String).flatMap { ClientTelemetryCodec.date(from: $0) }
    return OwnerRecord(ownerID: ownerID, observations: observations, notBefore: notBefore)
  }

  private func save(_ record: OwnerRecord) {
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let rows = record.observations.map { observation -> [String: Any] in
      [
        "attempt_count": observation.attemptCount,
        "attributes": observation.attributes.mapValues { $0.jsonObject },
        "channel": observation.channel,
        "enqueued_at": ClientTelemetryCodec.iso8601(observation.enqueuedAt),
        "event_id": observation.eventID.uuidString.lowercased(),
        "family": observation.family,
        "occurred_at": ClientTelemetryCodec.iso8601(observation.occurredAt),
        "platform": observation.platform,
      ]
    }
    var payload: [String: Any] = [
      "observations": rows,
      "owner_id": record.ownerID,
      "schema_version": 1,
    ]
    if let notBefore = record.notBefore {
      payload["not_before"] = ClientTelemetryCodec.iso8601(notBefore)
    }
    if let data = ClientTelemetryCodec.data(json: payload) {
      try? data.write(to: fileURL(record.ownerID), options: .atomic)
    }
  }

  private func remember(_ ownerID: String) {
    var owners = knownOwnerIDs()
    if !owners.contains(ownerID) {
      owners.append(ownerID)
      writeIndex(owners)
    }
  }

  private func writeIndex(_ owners: [String]) {
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let payload: [String: Any] = ["owners": owners, "schema_version": 1]
    if let data = ClientTelemetryCodec.data(json: payload) {
      try? data.write(to: indexURL, options: .atomic)
    }
  }

  private func persistDrops() {
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let payload: [String: Any] = [
      "counts": [
        "conflict": dropCounts.conflict,
        "exhausted": dropCounts.exhausted,
        "invalid": dropCounts.invalid,
        "missing_owner": dropCounts.missingOwner,
        "overflow_bytes": dropCounts.overflowBytes,
        "overflow_count": dropCounts.overflowCount,
        "oversize": dropCounts.oversize,
        "permanent": dropCounts.permanent,
        "ttl": dropCounts.ttl,
        "unauthorized": dropCounts.unauthorized,
        "unreconciled": dropCounts.unreconciled,
      ],
      "schema_version": 1,
    ]
    if let data = ClientTelemetryCodec.data(json: payload) {
      try? data.write(to: dropsURL, options: .atomic)
    }
  }

  private static func loadDrops(directory: URL) -> ClientTelemetryDropCounts {
    let url = directory.appendingPathComponent("drops.json")
    guard let data = try? Data(contentsOf: url),
      let object = ClientTelemetryCodec.object(from: data),
      let counts = object["counts"] as? [String: Any]
    else { return ClientTelemetryDropCounts() }
    func integer(_ key: String) -> Int { (counts[key] as? NSNumber)?.intValue ?? 0 }
    var drops = ClientTelemetryDropCounts()
    drops.conflict = integer("conflict")
    drops.exhausted = integer("exhausted")
    drops.invalid = integer("invalid")
    drops.missingOwner = integer("missing_owner")
    drops.overflowBytes = integer("overflow_bytes")
    drops.overflowCount = integer("overflow_count")
    drops.oversize = integer("oversize")
    drops.permanent = integer("permanent")
    drops.ttl = integer("ttl")
    drops.unauthorized = integer("unauthorized")
    drops.unreconciled = integer("unreconciled")
    return drops
  }

  private static func observation(ownerID: String, row: [String: Any]) -> ClientTelemetryObservation? {
    guard let eventText = row["event_id"] as? String, let eventID = UUID(uuidString: eventText),
      let occurredText = row["occurred_at"] as? String, let occurredAt = ClientTelemetryCodec.date(from: occurredText),
      let enqueuedText = row["enqueued_at"] as? String, let enqueuedAt = ClientTelemetryCodec.date(from: enqueuedText),
      let platform = row["platform"] as? String,
      let channel = row["channel"] as? String,
      let family = row["family"] as? String,
      let rawAttributes = row["attributes"] as? [String: Any]
    else { return nil }
    var attributes: [String: ClientTelemetryJSON] = [:]
    for (key, value) in rawAttributes {
      guard let parsed = ClientTelemetryJSON.fromPersisted(value) else { continue }
      attributes[key] = parsed
    }
    let attempts = (row["attempt_count"] as? NSNumber)?.intValue ?? 0
    return ClientTelemetryObservation(
      eventID: eventID,
      occurredAt: occurredAt,
      platform: platform,
      channel: channel,
      family: family,
      attributes: attributes,
      ownerID: ownerID,
      enqueuedAt: enqueuedAt,
      attemptCount: attempts
    )
  }
}
