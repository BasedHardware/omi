import Foundation

enum VoiceOutputDecision: Equatable, Sendable {
  case acquired(VoiceOutputLease)
  case denied(active: VoiceOutputLease)
  case staleTurn
}

struct VoiceOutputSnapshot: Equatable, Sendable {
  let turnID: VoiceTurnID?
  let activeLease: VoiceOutputLease?
  let providerOutputSuppressed: Bool
}

enum VoiceOutputHandoffPolicy {
  static func fillerCanYield(
    active: VoiceOutputLease,
    to incomingLane: VoiceOutputLane,
    turnID: VoiceTurnID
  ) -> Bool {
    active.turnID == turnID && active.lane == .filler && incomingLane != .filler
  }
}

/// Authoritative audible-output owner for a PTT turn.
///
/// Every PTT audio path must acquire a turn-scoped lease before it can play.
/// Releases and turn endings are identity checked so an old playback callback
/// cannot clear a newer turn's output or UI.
@MainActor
final class VoiceOutputCoordinator {
  static let shared = VoiceOutputCoordinator()

  private(set) var turnID: VoiceTurnID?
  private(set) var activeLease: VoiceOutputLease?
  private(set) var providerOutputSuppressed = false

  init() {}

  @discardableResult
  func beginTurn(id: VoiceTurnID = VoiceTurnID()) -> VoiceTurnID {
    turnID = id
    activeLease = nil
    providerOutputSuppressed = false
    return id
  }

  @discardableResult
  func endTurn(_ requestedTurnID: VoiceTurnID) -> Bool {
    guard requestedTurnID == turnID else { return false }
    turnID = nil
    activeLease = nil
    providerOutputSuppressed = false
    return true
  }

  @discardableResult
  func interrupt(turnID requestedTurnID: VoiceTurnID) -> Bool {
    guard requestedTurnID == turnID else { return false }
    activeLease = nil
    providerOutputSuppressed = false
    return true
  }

  func acquire(_ lane: VoiceOutputLane, turnID requestedTurnID: VoiceTurnID) -> VoiceOutputDecision
  {
    guard requestedTurnID == turnID else { return .staleTurn }
    if let activeLease {
      if activeLease.turnID == requestedTurnID, activeLease.lane == lane {
        return .acquired(activeLease)
      }
      return .denied(active: activeLease)
    }
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: requestedTurnID, lane: lane)
    activeLease = lease
    if lane == .deterministicAgentAck {
      providerOutputSuppressed = true
    }
    return .acquired(lease)
  }

  @discardableResult
  func release(_ lease: VoiceOutputLease) -> Bool {
    guard activeLease == lease, turnID == lease.turnID else { return false }
    activeLease = nil
    providerOutputSuppressed = false
    return true
  }

  func snapshot() -> VoiceOutputSnapshot {
    VoiceOutputSnapshot(
      turnID: turnID,
      activeLease: activeLease,
      providerOutputSuppressed: providerOutputSuppressed)
  }
}
