import CoreAudio
import Foundation

/// Pure policy for re-pinning ambient capture when a persisted preferred mic
/// reappears after fallback (#10921 item 1).
enum PreferredMicrophoneReconnectPolicy {
  /// Restart capture when the preferred UID resolves to a live device that is
  /// not the one currently open (typical: open fell back to system default
  /// while glasses were offline; glasses reconnect).
  ///
  /// Requires `isCaptureLive` so a device-list flap during HAL startup cannot
  /// restart while `activeDeviceID` is already assigned but `stopCapture()` is
  /// still a no-op (`isCapturing == false`).
  static func shouldReapplyPreferredMicrophone(
    preferredUID: String,
    resolvedPreferredDeviceID: AudioDeviceID?,
    activeCaptureDeviceID: AudioDeviceID?,
    isCaptureLive: Bool
  ) -> Bool {
    guard isCaptureLive else { return false }
    guard !preferredUID.isEmpty, let resolved = resolvedPreferredDeviceID else { return false }
    guard let active = activeCaptureDeviceID, active != kAudioObjectUnknown else {
      // Capture not open yet — startMicCaptureIfNeeded will resolve preferred.
      return false
    }
    return active != resolved
  }
}

/// Observes `kAudioHardwarePropertyDevices` while ambient transcription is live
/// so a preferred mic (e.g. Ray-Ban Meta) is reapplied after reconnect — Settings
/// does not need to be open (#10921).
@MainActor
final class PreferredMicrophoneReconnectMonitor {
  private weak var appState: AppState?
  private var isObserving = false
  // nonisolated(unsafe): written only on main in start/stop; deinit reads after last ref.
  nonisolated(unsafe) private var listenerBlock: AudioObjectPropertyListenerBlock?
  private var restartInFlight = false

  func start(observing appState: AppState) {
    self.appState = appState
    guard !isObserving else { return }

    var address = Self.devicesPropertyAddress
    let listener: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
      Task { @MainActor in
        await self?.evaluateAndRestartIfNeeded()
      }
    }

    let status = AudioObjectAddPropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject),
      &address,
      DispatchQueue.main,
      listener
    )
    guard status == noErr else { return }

    listenerBlock = listener
    isObserving = true
  }

  func stop() {
    guard isObserving, let listenerBlock else {
      appState = nil
      restartInFlight = false
      return
    }
    var address = Self.devicesPropertyAddress
    AudioObjectRemovePropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject),
      &address,
      DispatchQueue.main,
      listenerBlock
    )
    self.listenerBlock = nil
    isObserving = false
    restartInFlight = false
    appState = nil
  }

  deinit {
    guard isObserving, let listenerBlock else { return }
    var address = Self.devicesPropertyAddress
    AudioObjectRemovePropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject),
      &address,
      DispatchQueue.main,
      listenerBlock
    )
  }

  private func evaluateAndRestartIfNeeded() async {
    guard let appState, appState.isTranscribing, !restartInFlight else { return }

    let preferredUID =
      UserDefaults.standard.string(forKey: AudioCaptureService.preferredInputUIDDefaultsKey) ?? ""
    guard !preferredUID.isEmpty else { return }

    let resolved = await AudioCaptureService.resolvePreferredMicrophone()
    // Snapshot live capture only — `activeDeviceID` is assigned mid-HAL start
    // before `capturing` flips true; restarting then races the original start.
    let capture = appState.audioCaptureService
    guard
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: preferredUID,
        resolvedPreferredDeviceID: resolved?.id,
        activeCaptureDeviceID: capture?.activeDeviceID,
        isCaptureLive: capture?.capturing == true
      )
    else { return }

    restartInFlight = true
    defer { restartInFlight = false }

    log(
      "Transcription: preferred microphone reconnected — restarting capture onto \(resolved?.name ?? preferredUID)"
    )
    if await appState.prepareTranscriptionRestartAfterSettingsChange() {
      appState.startTranscription(userInitiated: false)
    }
  }

  nonisolated private static var devicesPropertyAddress: AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyDevices,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain
    )
  }
}
