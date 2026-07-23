@preconcurrency import CoreAudio

/// Resolves the PTT microphone policy without coupling the selection policy to
/// CoreAudio enumeration. An explicit user choice always wins; Automatic keeps
/// Bluetooth output on A2DP by preferring the built-in microphone.
enum PTTInputDeviceRouting {
  static func overrideDeviceID(
    selectedDeviceID: AudioDeviceID?,
    outputIsBluetooth: Bool,
    builtInDeviceID: AudioDeviceID?
  ) -> AudioDeviceID? {
    selectedDeviceID ?? (outputIsBluetooth ? builtInDeviceID : nil)
  }
}

@MainActor
extension PushToTalkManager {
  func preferredPTTInputOverrideDeviceID() -> AudioDeviceID? {
    let selectedUID = ShortcutSettings.shared.pttInputDeviceUID
    let selectedDeviceID =
      selectedUID.isEmpty
      ? nil
      : AudioCaptureService.inputDeviceID(forUID: selectedUID)
    if !selectedUID.isEmpty, selectedDeviceID == nil {
      log("PushToTalkManager: selected PTT microphone is unavailable — using Automatic")
    }
    let outputIsBluetooth = AudioCaptureService.isDefaultOutputBluetooth()
    return PTTInputDeviceRouting.overrideDeviceID(
      selectedDeviceID: selectedDeviceID,
      outputIsBluetooth: outputIsBluetooth,
      builtInDeviceID: outputIsBluetooth ? AudioCaptureService.findBuiltInMicDeviceID() : nil
    )
  }
}
