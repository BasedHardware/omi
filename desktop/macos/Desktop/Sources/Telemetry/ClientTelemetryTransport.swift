import Foundation

/// Owner-scoped outbox for `POST /v1/telemetry/client/batches`.
///
/// One batch is in flight. Event ids are frozen at creation and reused across
/// retries. Logout and account swap purge the previous owner's pending rows
/// instead of sending them with the new token. Transport failure never throws
/// to capture, recording, or delivery callers.
actor ClientTelemetryTransport {
  static let shared = ClientTelemetryTransport(
    directory: productionDirectory(),
    limits: .production,
    dependencies: .production
  )

  private let limits: ClientTelemetryLimits
  private let dependencies: ClientTelemetryDependencies
  private let store: ClientTelemetryStore
  private var flushing = false
  private var flushAgain = false
  private var flushLoop: Task<Void, Never>?

  init(directory: URL, limits: ClientTelemetryLimits, dependencies: ClientTelemetryDependencies) {
    self.limits = limits
    self.dependencies = dependencies
    store = ClientTelemetryStore(directory: directory, limits: limits)
  }

  nonisolated static func scheduleBestEffortFlush() {
    Task { await shared.flush() }
  }

  func enqueue(_ observation: ClientTelemetryObservation) async {
    let now = dependencies.now()
    _ = store.enqueue(observation, now: now)
    let pending = store.observations(ownerID: observation.ownerID).count
    if pending >= limits.maxObservationsPerBatch {
      await flush()
    } else {
      armFlushLoop()
    }
  }

  func recordDrop(_ reason: ClientTelemetryDropReason) async {
    store.note(reason)
  }

  func purgeOwner(_ ownerID: String) async {
    store.purgeOwner(ownerID)
  }

  func purgeOwnersExceptCurrent() async {
    store.purgeOwners(except: dependencies.currentOwnerID())
  }

  func dropCounts() async -> ClientTelemetryDropCounts { store.dropCounts }

  func pending(ownerID: String) async -> [ClientTelemetryObservation] {
    store.observations(ownerID: ownerID)
  }

  func flush() async {
    if flushing {
      flushAgain = true
      return
    }
    flushing = true
    defer {
      flushing = false
      if flushAgain {
        flushAgain = false
        Task { await self.flush() }
      }
    }
    guard let ownerID = dependencies.currentOwnerID() else { return }
    var guardrail = max(1, limits.maxOutboxObservations)
    while guardrail > 0 {
      guardrail -= 1
      let before = store.observations(ownerID: ownerID).count
      let sent = await sendNextBatch(ownerID: ownerID)
      if !sent { break }
      if store.observations(ownerID: ownerID).count >= before { break }
    }
  }

  private func sendNextBatch(ownerID: String) async -> Bool {
    let now = dependencies.now()
    // sol blocker: a parked owner (429 + Retry-After over the honored cap)
    // must not send again until the persisted `not_before` elapses.
    if let notBefore = store.notBefore(ownerID: ownerID), now < notBefore { return false }
    store.expire(ownerID: ownerID, now: now)
    let pending = store.observations(ownerID: ownerID).filter { $0.attemptCount < limits.maxAttempts }
    guard !pending.isEmpty else { return false }
    guard dependencies.currentOwnerID() == ownerID else { return false }
    let batch = pack(pending)
    if batch.isEmpty {
      if let first = pending.first {
        store.remove(ownerID: ownerID, eventIDs: [first.eventID])
        store.note(.oversize)
      }
      return false
    }
    let eventIDs = Set(batch.map(\.eventID))
    let batchID = UUID()
    var refreshed = false
    var failureIndex = 0
    while true {
      guard dependencies.currentOwnerID() == ownerID else { return false }
      let attempts = store.observations(ownerID: ownerID).filter { eventIDs.contains($0.eventID) }
      guard attempts.count == batch.count else { return false }
      if attempts.contains(where: { $0.attemptCount >= limits.maxAttempts }) {
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        store.note(.exhausted)
        return false
      }
      guard let token = await dependencies.token(ownerID, false) else {
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        store.note(.unauthorized)
        return false
      }
      guard dependencies.currentOwnerID() == ownerID else { return false }
      guard let body = ClientTelemetryCodec.batchData(batchID: batchID, observations: batch),
        body.count <= limits.maxRequestBytes
      else {
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        store.note(.oversize)
        return false
      }
      let baseURL = await dependencies.endpointBaseURL()
      guard let url = ClientTelemetryHTTP.endpoint(baseURL: baseURL) else {
        store.note(.invalid)
        return false
      }
      store.incrementAttempts(ownerID: ownerID, eventIDs: eventIDs)
      let request = ClientTelemetryRequest(
        url: url, token: token, body: body, timeout: limits.requestTimeout, batchID: batchID, ownerID: ownerID)
      let result = await dependencies.send(request)
      switch classify(result, batchID: batchID, count: batch.count) {
      case .accepted:
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        return true
      case .unauthorized:
        if !refreshed, case .response(let status, _, _) = result, status == 401 {
          refreshed = true
          guard dependencies.currentOwnerID() == ownerID else { return false }
          let renewed = await dependencies.token(ownerID, true)
          guard dependencies.currentOwnerID() == ownerID, renewed != nil else {
            store.remove(ownerID: ownerID, eventIDs: eventIDs)
            store.note(.unauthorized)
            return false
          }
          continue
        }
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        store.note(.unauthorized)
        return false
      case .conflict:
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        store.note(.conflict)
        return false
      case .permanent:
        store.remove(ownerID: ownerID, eventIDs: eventIDs)
        store.note(.permanent)
        return false
      case .park(let retryAfter):
        // sol blocker: persist the parking window so a restart or a second
        // flush cannot retry the parked batch before `not_before` elapses.
        let until = dependencies.now().addingTimeInterval(min(retryAfter, limits.maxHonoredRetryAfter))
        store.setNotBefore(ownerID: ownerID, until: until)
        return false
      case .retry(let retryAfter):
        let latest = store.observations(ownerID: ownerID).filter { eventIDs.contains($0.eventID) }
        if latest.contains(where: { $0.attemptCount >= limits.maxAttempts }) {
          store.remove(ownerID: ownerID, eventIDs: eventIDs)
          store.note(.exhausted)
          return false
        }
        guard
          let delay = ClientTelemetryRetryDelay.delay(
            failureIndex: failureIndex,
            retryAfter: retryAfter,
            jitterUnit: dependencies.jitterUnit(),
            limits: limits
          )
        else {
          return false
        }
        failureIndex += 1
        await dependencies.sleep(delay)
      }
    }
  }

  private enum Disposition {
    case accepted
    case unauthorized
    case conflict
    case permanent
    case retry(TimeInterval?)
    case park(TimeInterval)
  }

  private func classify(_ result: ClientTelemetryHTTPResult, batchID: UUID, count: Int) -> Disposition {
    switch result {
    case .timeout, .network:
      return .retry(nil)
    case .response(let status, let retryAfter, let body):
      if status == 200 {
        guard let object = ClientTelemetryCodec.object(from: body),
          (object["schema_version"] as? NSNumber)?.intValue == 1,
          let echoed = object["batch_id"] as? String,
          UUID(uuidString: echoed) == batchID,
          let accepted = (object["accepted_count"] as? NSNumber)?.intValue,
          let duplicate = (object["duplicate_count"] as? NSNumber)?.intValue,
          accepted >= 0, duplicate >= 0, accepted + duplicate == count
        else { return .retry(nil) }
        return .accepted
      }
      if status == 401 || status == 403 { return .unauthorized }
      if status == 409 { return .conflict }
      if status == 408 || status == 429 || (500...599).contains(status) {
        if let retryAfter, retryAfter > limits.maxHonoredRetryAfter { return .park(retryAfter) }
        return .retry(retryAfter)
      }
      if (400...499).contains(status) { return .permanent }
      return .retry(retryAfter)
    }
  }

  private func pack(_ observations: [ClientTelemetryObservation]) -> [ClientTelemetryObservation] {
    var selected: [ClientTelemetryObservation] = []
    for observation in observations {
      if selected.count >= limits.maxObservationsPerBatch { break }
      var candidate = selected
      candidate.append(observation)
      guard let body = ClientTelemetryCodec.batchData(batchID: UUID(), observations: candidate),
        body.count <= limits.maxRequestBytes
      else { break }
      selected = candidate
    }
    return selected
  }

  private func armFlushLoop() {
    guard dependencies.automaticFlush, flushLoop == nil else { return }
    flushLoop = Task { [limits] in
      await self.dependencies.sleep(limits.flushInterval)
      await self.flush()
      self.finishFlushLoop()
    }
  }

  private func finishFlushLoop() {
    flushLoop = nil
    if dependencies.currentOwnerID().flatMap({ store.observations(ownerID: $0).isEmpty ? nil : $0 }) != nil {
      armFlushLoop()
    }
  }

  private static func productionDirectory() -> URL {
    let base =
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
    return base.appendingPathComponent("OmiDesktopClientTelemetry", isDirectory: true)
  }
}
