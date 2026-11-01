import Foundation

/// Evidence is additive: local rotation still runs through MeetingConversationBoundaryPolicy.
struct DesktopBoundarySignal: Encodable, Equatable, Sendable {
  let kind = "desktop_meeting"
  let startedAt: Date
  var endedAt: Date?
  let confidence = 1.0
  let sourceDevice = "macos"
  let externalID: String
  enum CodingKeys: String, CodingKey {
    case kind, confidence
    case startedAt = "started_at"
    case endedAt = "ended_at"
    case sourceDevice = "source_device"
    case externalID = "external_id"
  }
  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    let iso = ISO8601DateFormatter()
    try c.encode(kind, forKey: .kind)
    try c.encode(iso.string(from: startedAt), forKey: .startedAt)
    try c.encodeIfPresent(endedAt.map(iso.string), forKey: .endedAt)
    try c.encode(confidence, forKey: .confidence)
    try c.encode(sourceDevice, forKey: .sourceDevice)
    try c.encode(externalID, forKey: .externalID)
  }
}

struct MeetingBoundaryEvidence {
  private(set) var active: DesktopBoundarySignal?
  mutating func observe(
    active meetingActive: Bool, callChanged: Bool, now: Date,
    makeID: () -> String = { UUID().uuidString }
  ) -> [DesktopBoundarySignal] {
    var signals: [DesktopBoundarySignal] = []
    if var previous = active, !meetingActive || callChanged {
      previous.endedAt = max(now, previous.startedAt)
      signals.append(previous)
      active = nil
    }
    if meetingActive && active == nil {
      let signal = DesktopBoundarySignal(startedAt: now, externalID: makeID())
      active = signal
      signals.append(signal)
    }
    return signals
  }
}

extension APIClient {
  private struct BoundaryAck: Decodable {}
  func sendBoundaryEvidence(_ signals: [DesktopBoundarySignal], authorization: RuntimeOwnerAuthorizationSnapshot)
    async throws
  {
    let _: BoundaryAck = try await post(
      "v1/capture/boundary-evidence", body: signals, customBaseURL: nil, authorizationSnapshot: authorization)
  }
}

extension AppState {
  func reportMeetingBoundaryEvidence(active: Bool, callChanged: Bool) {
    guard ClientRefactorFlags.boundaryEvidence else { return }
    let signals = meetingBoundaryEvidence.observe(active: active, callChanged: callChanged, now: Date())
    guard !signals.isEmpty else { return }
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
    let generation = ownerScopeGeneration
    Task {
      guard self.ownerScopeGeneration == generation else { return }
      do { try await APIClient.shared.sendBoundaryEvidence(signals, authorization: authorization) } catch {
        log("event=refactor_shadow lane=L5 check=boundary_evidence outcome=error")
      }
    }
  }
}
