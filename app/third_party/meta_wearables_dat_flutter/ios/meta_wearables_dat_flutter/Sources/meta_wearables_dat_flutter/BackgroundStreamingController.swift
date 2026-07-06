// Background-streaming support on iOS.
//
// Owns the AVAudioSession configuration that keeps the BLE link + camera
// pipeline alive while the app is backgrounded / the screen is locked.
// Without this controller, iOS suspends the host app a few seconds after
// it enters the background, which kills both the device session (the
// SDK drops its `URLSession`) and the VideoToolbox decoder (the OS
// reclaims hardware decoders when an app is no longer foreground).
//
// Mechanics:
//   1. `enable()` activates an AVAudioSession with `.playAndRecord` /
//      `.videoRecording`, plus `.allowBluetoothHFP` so the BLE link to
//      the glasses survives, and `.mixWithOthers` so the host app
//      doesn't fight Apple Music / Spotify.
//   2. Registers observers for `AVAudioSession.interruptionNotification`,
//      `routeChangeNotification`, and `mediaServicesWereResetNotification`
//      so the session is automatically re-activated when iOS recovers.
//   3. Exposes `useSoftwareDecoder` so `MetaSessionManager` can flip its
//      `VTDecompressionPipeline` into software-only mode while background
//      streaming is active (hardware HEVC decoders are killed at
//      backgrounding time).
//
// Host apps must declare the corresponding `UIBackgroundModes` keys in
// `Info.plist`: `audio`, `bluetooth-central`, `bluetooth-peripheral`,
// `external-accessory`. Missing modes are reported by `dumpDiagnostics`.

import AVFAudio
import Foundation

@MainActor
final class BackgroundStreamingController {
  static let shared = BackgroundStreamingController()

  private(set) var isEnabled: Bool = false

  /// True while background streaming is active. While true, callers
  /// that build a `VTDecompressionSession` should disable hardware
  /// acceleration so the decoder survives backgrounding.
  var useSoftwareDecoder: Bool { isEnabled }

  private init() {}

  /// Called by `MetaSessionManager` when background streaming is
  /// toggled so the existing pipeline can swap decoders on the next
  /// stream.
  var onSoftwareModeChange: ((Bool) -> Void)?

  func enable() throws {
    if isEnabled { return }
    try activateSession()
    registerObservers()
    isEnabled = true
    onSoftwareModeChange?(true)
    print("[meta_wearables_dat_flutter] BackgroundStreaming enabled")
  }

  func disable() {
    if !isEnabled { return }
    deregisterObservers()
    let session = AVAudioSession.sharedInstance()
    do {
      try session.setActive(false, options: [.notifyOthersOnDeactivation])
    } catch {
      print("[meta_wearables_dat_flutter] AVAudioSession.setActive(false) " +
        "failed: \(error)")
    }
    isEnabled = false
    onSoftwareModeChange?(false)
    print("[meta_wearables_dat_flutter] BackgroundStreaming disabled")
  }

  // MARK: - AVAudioSession

  private func activateSession() throws {
    let session = AVAudioSession.sharedInstance()
    // `.playAndRecord` is required to keep the mic open and to qualify
    // for `audio` background mode. `.videoRecording` matches what
    // Meta's iOS sample uses. `.allowBluetoothHFP` keeps the BLE-HFP
    // route alive while the screen is locked. `.mixWithOthers`
    // prevents the host app from muting other audio.
    var options: AVAudioSession.CategoryOptions = [.mixWithOthers]
    // Bluetooth HFP options are unavailable on the simulator (no BT hardware).
    #if !targetEnvironment(simulator)
    if #available(iOS 14.5, *) {
      options.insert(.allowBluetoothHFP)
    } else {
      options.insert(.allowBluetooth)
    }
    #endif
    try session.setCategory(
      .playAndRecord,
      mode: .videoRecording,
      options: options,
    )
    try session.setActive(true)
  }

  private func registerObservers() {
    let center = NotificationCenter.default
    center.addObserver(
      self,
      selector: #selector(handleInterruption(_:)),
      name: AVAudioSession.interruptionNotification,
      object: nil,
    )
    center.addObserver(
      self,
      selector: #selector(handleRouteChange(_:)),
      name: AVAudioSession.routeChangeNotification,
      object: nil,
    )
    center.addObserver(
      self,
      selector: #selector(handleMediaServicesReset(_:)),
      name: AVAudioSession.mediaServicesWereResetNotification,
      object: nil,
    )
  }

  private func deregisterObservers() {
    let center = NotificationCenter.default
    center.removeObserver(
      self,
      name: AVAudioSession.interruptionNotification,
      object: nil,
    )
    center.removeObserver(
      self,
      name: AVAudioSession.routeChangeNotification,
      object: nil,
    )
    center.removeObserver(
      self,
      name: AVAudioSession.mediaServicesWereResetNotification,
      object: nil,
    )
  }

  // MARK: - Notification handlers

  @objc nonisolated private func handleInterruption(_ note: Notification) {
    guard
      let info = note.userInfo,
      let rawType = info[AVAudioSessionInterruptionTypeKey] as? UInt,
      let type = AVAudioSession.InterruptionType(rawValue: rawType)
    else { return }
    if type == .ended {
      Task { @MainActor in
        // Best-effort re-activation. Failure is logged but non-fatal —
        // user can re-enable manually.
        do {
          try self.activateSession()
          print("[meta_wearables_dat_flutter] AVAudioSession re-activated " +
            "after interruption")
        } catch {
          print("[meta_wearables_dat_flutter] AVAudioSession re-activation " +
            "failed: \(error)")
        }
      }
    }
  }

  @objc nonisolated private func handleRouteChange(_ note: Notification) {
    guard
      let info = note.userInfo,
      let rawReason = info[AVAudioSessionRouteChangeReasonKey] as? UInt,
      let reason = AVAudioSession.RouteChangeReason(rawValue: rawReason)
    else { return }
    // The glasses' BLE-HFP route can disappear when battery dies or
    // they are folded; if iOS yanked it, log so the host app can show
    // an error UI.
    if reason == .oldDeviceUnavailable {
      print("[meta_wearables_dat_flutter] AVAudioSession route lost " +
        "(.oldDeviceUnavailable)")
    }
  }

  @objc nonisolated private func handleMediaServicesReset(_ note: Notification) {
    print("[meta_wearables_dat_flutter] AVAudioSession mediaServicesWereReset")
    Task { @MainActor in
      do {
        try self.activateSession()
      } catch {
        print("[meta_wearables_dat_flutter] AVAudioSession re-activate " +
          "after mediaServicesWereReset failed: \(error)")
      }
    }
  }
}
