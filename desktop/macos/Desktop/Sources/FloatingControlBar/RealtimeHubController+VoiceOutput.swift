import AppKit
import CoreGraphics
import Foundation
import OmiSupport

extension RealtimeHubController {
  func makePCMPlayer() -> StreamingPCMPlayer {
    let player = StreamingPCMPlayer(sampleRate: 24000)
    player.onPlaybackScheduled = { [weak self] playbackEpoch in
      Task { @MainActor in
        guard let self else { return }
        self.realtimePlaybackEpoch = playbackEpoch
      }
    }
    player.onPlaybackIdle = { [weak self] playbackEpoch in
      Task { @MainActor in
        guard let self, self.realtimePlaybackEpoch == playbackEpoch else { return }
        if let lease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease,
          lease.lane == .nativeRealtime
        {
          if VoiceTurnCoordinator.shared.releaseOutput(lease) {
            if VoiceTurnCoordinator.shared.model.turn?.phase.isTerminal == true {
              self.exitVoiceUI()
              self.applyPendingSessionRefreshIfIdle()
            }
          }
        }
        self.clearResponseGlowIfRealtimeAudioIdle()
      }
    }
    return player
  }

  /// Replaces the provider's post-tool narration with the kernel's durable
  /// admission fact. A spawn receipt is not a child completion receipt, so this
  /// is the only spoken acknowledgement for a PTT spawn turn.
  func playCanonicalSpawnAcknowledgement(_ text: String) {
    let acknowledgement = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !acknowledgement.isEmpty else { return }

    // A provider can begin a speculative response before its tool call returns.
    // Once the kernel accepts the spawn, that narration can no longer make
    // lifecycle claims. Stop it before taking the deterministic acknowledgement
    // lease so no stale audio competes with the canonical fact.
    takeOverVoiceOutputForAuthoritativeLocalResult()
    guard let lease = acquireVoiceOutput(.deterministicAgentAck, reason: "canonical_spawn_receipt")
    else { return }
    responseGlowGate.markPlaybackActive(lease: lease)
    FloatingBarVoicePlaybackService.shared.speakOneShot(acknowledgement, lease: lease)
  }

  /// Local results such as accepted agent receipts and verified/fail-closed
  /// screen evidence supersede any speculative provider narration for this
  /// turn. Keep the physical preemption and reducer lease release together so
  /// every authoritative answer can acquire its own deterministic lease.
  func takeOverVoiceOutputForAuthoritativeLocalResult() {
    if let activeLease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease {
      FloatingBarVoicePlaybackService.shared.interruptCurrentResponse(leaseID: activeLease.id)
      _ = VoiceTurnCoordinator.shared.releaseOutput(activeLease)
    }
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
  }

  func acquireVoiceOutput(_ lane: VoiceOutputLane, reason: String) -> VoiceOutputLease? {
    guard let turnID = VoiceTurnCoordinator.shared.activeTurnID else {
      log(
        "RealtimeHub[\(providerTag)]: dropping \(lane.rawValue) output with no active PTT turn reason=\(reason)"
      )
      return nil
    }
    _ = FloatingBarVoicePlaybackService.shared.preemptFillerIfNeeded(
      for: lane,
      turnID: turnID)
    switch VoiceTurnCoordinator.shared.acquireOutput(lane, turnID: turnID) {
    case .acquired(let lease):
      return lease
    case .denied(let active):
      log(
        "RealtimeHub[\(providerTag)]: dropping \(lane.rawValue) output reason=\(reason) "
          + "active_lane=\(active.lane.rawValue)"
      )
      return nil
    case .staleTurn:
      log("RealtimeHub[\(providerTag)]: dropping stale \(lane.rawValue) output reason=\(reason)")
      return nil
    }
  }

  func releaseVoiceOutputIfActive(_ lane: VoiceOutputLane) {
    guard let lease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease, lease.lane == lane else {
      return
    }
    _ = VoiceTurnCoordinator.shared.releaseOutput(lease)
  }

  /// Executes the reducer's exact native-audio stop effect. Terminal reduction
  /// clears the logical lease before effects run, so the terminal record is the
  /// authoritative fallback fence for this synchronous physical cleanup.
  @discardableResult
  func stopNativePlayback(lease: VoiceOutputLease) -> Bool {
    guard lease.lane == .nativeRealtime else { return false }
    let ownsActiveLease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease == lease
    let ownsTerminalTurn = VoiceTurnCoordinator.shared.activeTurnID == nil
      && VoiceTurnCoordinator.shared.model.lastTerminal?.turnID == lease.turnID
    guard ownsActiveLease || ownsTerminalTurn else {
      log("RealtimeHub: ignored stale native playback stop lease=\(lease.id)")
      return false
    }
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
    return true
  }
}
