import Foundation

/// One atomic journal couples the once-only render receipt to its retryable outcome.
/// No feed text or credentials are persisted. Instances are owned by one auth session.
@MainActor
final class ProactivityReceiptStore {
  struct Entry: Codable {
    let itemID: String
    let request: OmiAPI.ProactivityOutcomeRequest
  }
  private struct State: Codable {
    var ownerID: String
    var shown: Set<String> = []
    var outbox: [Entry] = []
  }
  private let url: URL
  private var state: State
  var pending: [Entry] { state.outbox }

  init(url: URL, ownerID: String) throws {
    self.url = url
    if FileManager.default.fileExists(atPath: url.path) {
      let decoded = try JSONDecoder().decode(State.self, from: Data(contentsOf: url))
      state = decoded.ownerID == ownerID ? decoded : State(ownerID: ownerID)
    } else {
      state = State(ownerID: ownerID)
    }
    try save(state)
  }

  func hasShown(_ id: String) -> Bool { state.shown.contains(id) }

  func record(itemID: String, request: OmiAPI.ProactivityOutcomeRequest) throws {
    guard request.action != "timeout" else { return }
    if request.action == "shown", hasShown(itemID) { return }
    guard !state.outbox.contains(where: { $0.request.eventId == request.eventId }) else { return }
    var next = state
    if request.action == "shown" { next.shown.insert(itemID) }
    next.outbox.append(Entry(itemID: itemID, request: request))
    try save(next)
    state = next
  }

  func acknowledge(_ eventID: String) throws {
    var next = state
    next.outbox.removeAll { $0.request.eventId == eventID }
    try save(next)
    state = next
  }

  func drain(isCurrent: () -> Bool, send: (Entry) async throws -> Void) async throws {
    for entry in pending {
      guard isCurrent() else { return }
      try await send(entry)
      guard isCurrent() else { return }
      try acknowledge(entry.request.eventId)
    }
  }

  func purge() throws {
    state = State(ownerID: state.ownerID)
    try Self.purge(at: url)
  }

  static func purge(at url: URL) throws {
    if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
  }

  private func save(_ value: State) throws {
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try JSONEncoder().encode(value).write(to: url, options: .atomic)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
  }
}

/// Match the backend's undelivered-item notification window, not its 90-day ledger TTL.
enum ProactivityFreshness {
  static func date(_ value: String) -> Date? {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.date(from: value) ?? ISO8601DateFormatter().date(from: value)
  }
  static func deadline(createdAt: String, serverTime: String, now: Date = Date()) -> Date? {
    guard let created = date(createdAt), let server = date(serverTime), created <= server else { return nil }
    return now.addingTimeInterval(created.addingTimeInterval(86_400).timeIntervalSince(server))
  }
}
