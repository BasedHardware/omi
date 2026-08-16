import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

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

  /// A verified, fail-closed screen result supersedes provider narration for
  /// this turn. Keep physical preemption and reducer lease release together so
  /// that local error can acquire its own deterministic lease.
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
    let ownsTerminalTurn =
      VoiceTurnCoordinator.shared.activeTurnID == nil
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
