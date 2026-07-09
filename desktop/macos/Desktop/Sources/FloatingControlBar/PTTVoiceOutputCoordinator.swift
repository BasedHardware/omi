import Foundation

enum PTTVoiceOutputLane: String, Equatable, Sendable {
  case nativeRealtime = "native_realtime"
  case selectedVoiceFallback = "selected_voice_fallback"
  case deterministicAgentAck = "deterministic_agent_ack"
}

struct PTTVoiceLease: Equatable, Sendable {
  let id: UUID
  let turnID: UUID
  let lane: PTTVoiceOutputLane
  let epoch: UInt64
}

enum PTTVoiceOutputDecision: Equatable, Sendable {
  case acquired(PTTVoiceLease)
  case denied(active: PTTVoiceLease)
  case staleTurn
}

struct PTTVoiceOutputSnapshot: Equatable, Sendable {
  let turnID: UUID?
  let activeLease: PTTVoiceLease?
  let providerOutputSuppressed: Bool
}

/// Small turn-scoped voice-output arbiter for PTT.
///
/// Realtime native PCM, selected voice fallback, and deterministic agent acks
/// must not independently start audible output. This coordinator gives the
/// current PTT turn exactly one audible lane at a time and makes late provider
/// callbacks easy to reject by turn id.
struct PTTVoiceOutputCoordinator {
  private(set) var turnID: UUID?
  private(set) var activeLease: PTTVoiceLease?
  private(set) var providerOutputSuppressed = false
  private var epoch: UInt64 = 0

  mutating func beginTurn(id: UUID = UUID()) -> UUID {
    turnID = id
    activeLease = nil
    providerOutputSuppressed = false
    epoch &+= 1
    return id
  }

  mutating func endTurn() {
    turnID = nil
    activeLease = nil
    providerOutputSuppressed = false
    epoch &+= 1
  }

  mutating func interruptCurrentOutput() {
    activeLease = nil
    providerOutputSuppressed = false
    epoch &+= 1
  }

  mutating func acquire(_ lane: PTTVoiceOutputLane, turnID requestedTurnID: UUID) -> PTTVoiceOutputDecision {
    guard requestedTurnID == turnID else { return .staleTurn }
    if let activeLease {
      if activeLease.turnID == requestedTurnID, activeLease.lane == lane {
        return .acquired(activeLease)
      }
      return .denied(active: activeLease)
    }
    let lease = PTTVoiceLease(id: UUID(), turnID: requestedTurnID, lane: lane, epoch: epoch)
    activeLease = lease
    if lane == .deterministicAgentAck {
      providerOutputSuppressed = true
    }
    return .acquired(lease)
  }

  mutating func release(_ lease: PTTVoiceLease) {
    guard activeLease == lease else { return }
    activeLease = nil
    providerOutputSuppressed = false
  }

  func snapshot() -> PTTVoiceOutputSnapshot {
    PTTVoiceOutputSnapshot(
      turnID: turnID,
      activeLease: activeLease,
      providerOutputSuppressed: providerOutputSuppressed)
  }
}
