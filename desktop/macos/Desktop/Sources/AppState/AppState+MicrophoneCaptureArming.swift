@preconcurrency import AVFoundation
import Foundation

@MainActor
extension AppState {
  /// Arm microphone + system audio capture for the session. Actual capture is managed by
  /// `reconcileCapture()` according to the System Audio mode + meeting state:
  ///  - Always / Never: the microphone runs for the whole session (system audio per mode).
  ///  - Only during meetings: nothing is captured until a call is detected, then mic + system
  ///    start, and both pause when the call ends — so the mic (and its indicator) stays off
  ///    outside meetings.
  /// Captured audio is mixed into one mono stream (cloud) or fed to separate Parakeet instances
  /// (local) so calls/videos/music end up in the transcript alongside the user's voice.
  /// Silent-mic watchdog: CoreAudio can report a healthy IOProc while a Bluetooth, USB, or
  /// built-in input returns only zeros. Listen/manual/Quick Note all flow through here, so
  /// they must opt into all-transport detection just as PTT does. Shared by the session-arm
  /// path and the preferred-microphone swap in startMicCaptureIfNeeded().
  func configureSharedCaptureWatchdog(_ service: AudioCaptureService) {
    SharedCaptureSilentMicRecoveryPolicy.configure(service)
    service.onSilentMicDetected = { [weak self, weak service] detection in
      Task { @MainActor in
        // A swapped-out capture service (preferred-mic reapply, silent-mic
        // fallback) can still deliver a queued detection — it must not rebuild
        // the replacement service's stack.
        guard let self, self.audioCaptureService === service else { return }
        switch detection.suggestedAction {
        case .fallbackToBuiltIn:
          await self.handleSilentMicFallback(detection: detection)
        case .rebuildCoreAudioStack:
          await self.handleSharedCaptureSilentMicDetection(detection: detection)
        }
      }
    }
  }

  func startMicrophoneAudioCapture(userInitiated: Bool = false) async {
    guard let audioCaptureService = audioCaptureService else { return }

    // Authorization first, capture second. CoreAudio HAL capture never triggers the
    // system microphone prompt on its own: with a notDetermined or revoked TCC entry it
    // "succeeds" and delivers zero samples forever. The silent-mic watchdog then reads
    // those zeros as a dead device and loops the user through rebuilds into a
    // "Microphone Isn't Capturing Audio" alert every ~90s — a permission problem wearing
    // a hardware costume. startTranscription() has its own guard, but resume, the meeting
    // gate, and the watchdog's own rebuild all arm capture through here without passing it.
    var gateAction = MicrophoneCaptureAuthorizationPolicy.action(
      for: AudioCaptureService.authorizationStatus(), userInitiated: userInitiated)
    if gateAction == .requestPermission {
      log("Transcription: microphone permission undetermined — requesting before capture")
      gateAction = MicrophoneCaptureAuthorizationPolicy.action(
        afterRequestGranted: await AudioCaptureService.requestPermission())
    }
    guard gateAction == .proceed else {
      if gateAction == .surfacePermissionAlert {
        surfaceMicrophonePermissionAlert()
      } else {
        log("Transcription: automatic capture abandoned after microphone authorization changed")
      }
      captureAttempt?.noteErrorTerminal()
      if armedMicrophoneRecovery.isProbing {
        recordSilentMicDiagnostic(detection: nil, phase: "armed_retry", result: "permission_abandoned")
        armedMicrophoneRecovery.cancel()
      }
      stopTranscription(finalizationReason: .microphoneUnavailable)
      return
    }

    configureSharedCaptureWatchdog(audioCaptureService)

    // Cloud mode: the mixer sums mic + system into one mono stream for the WebSocket.
    // Local mode: bypass the mixer — mic and system are transcribed by SEPARATE Parakeet
    // instances so transcripts are diarized by source (mic = you, system = another speaker).
    if !sttSession.useLocalSTT {
      let probeAudioGate = armedMicrophoneRecovery.outboundAudioGate
      audioMixer?.start { [weak self] monoMixed in
        // A dead HAL route produces PCM zeros. Do not bill a cloud provider for it.
        guard probeAudioGate.isOpen, AudioCaptureService.containsLivePCM(monoMixed) else { return }
        self?.transcriptionService?.sendAudio(monoMixed)
      }
    }

    // Start (or gate) microphone + system capture according to the System Audio mode + meeting state.
    await reconcileCapture()

    log("Transcription: Audio capture armed (mic + system managed by meeting gate)")
  }
}
