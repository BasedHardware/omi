import CoreAudio
import Foundation

/// Mutes the system's default audio-output device while push-to-talk is active,
/// mirroring Wispr Flow's "mute audio while dictating" behavior.
///
/// Unlike pausing media (which stops the track), this leaves playback running but
/// silent, so it resumes seamlessly the instant the user releases the key. To match
/// Wispr Flow exactly we only mute when audio is *already playing* on the device, we
/// never touch a device the user has muted themselves, and we always restore the
/// prior state when listening ends.
@MainActor
final class SystemAudioMuteController {
  static let shared = SystemAudioMuteController()

  /// The device we muted, or nil if we currently hold no mute.
  private var mutedDevice: AudioDeviceID?
  /// Per-channel volumes to restore when the fallback path was used.
  private var restoreVolumes: [(channel: UInt32, value: Float32)] = []
  private var usedVolumeFallback = false

  private init() {}

  // MARK: - Public API

  /// Mute the default output device if audio is currently playing through it.
  /// Idempotent — safe to call repeatedly while already muted.
  func muteForListening() {
    guard mutedDevice == nil else { return }  // we already hold a mute
    guard let device = Self.defaultOutputDevice() else { return }
    guard Self.isDeviceRunningSomewhere(device) else { return }  // nothing is playing
    if Self.deviceIsMuted(device) == true { return }  // user already muted it — leave it

    // Preferred path: toggle the device's master mute.
    if Self.setMute(device, muted: true) {
      mutedDevice = device
      usedVolumeFallback = false
      log("SystemAudioMuteController: muted output device \(device)")
      return
    }

    // Fallback: device has no settable mute → drop volume to zero, remembering prior.
    let saved = Self.zeroVolume(device)
    if !saved.isEmpty {
      restoreVolumes = saved
      mutedDevice = device
      usedVolumeFallback = true
      log("SystemAudioMuteController: muted via volume fallback on device \(device)")
    }
  }

  /// Restore whatever `muteForListening()` changed. No-op if we hold no mute.
  func restore() {
    guard let device = mutedDevice else { return }
    if usedVolumeFallback {
      for v in restoreVolumes { _ = Self.setVolume(device, channel: v.channel, value: v.value) }
    } else {
      _ = Self.setMute(device, muted: false)
    }
    log("SystemAudioMuteController: restored output device \(device)")
    mutedDevice = nil
    restoreVolumes = []
    usedVolumeFallback = false
  }

  // MARK: - CoreAudio helpers

  private static func defaultOutputDevice() -> AudioDeviceID? {
    var addr = AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyDefaultOutputDevice,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var device = AudioDeviceID(0)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    let status = AudioObjectGetPropertyData(
      AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &device)
    guard status == noErr, device != 0 else { return nil }
    return device
  }

  /// True if any process is actively running I/O on the device (i.e. audio is playing).
  private static func isDeviceRunningSomewhere(_ device: AudioDeviceID) -> Bool {
    var addr = AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyDeviceIsRunningSomewhere,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var running = UInt32(0)
    var size = UInt32(MemoryLayout<UInt32>.size)
    let status = AudioObjectGetPropertyData(device, &addr, 0, nil, &size, &running)
    return status == noErr && running != 0
  }

  private static func muteAddress() -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyMute,
      mScope: kAudioObjectPropertyScopeOutput,
      mElement: kAudioObjectPropertyElementMain)
  }

  /// Current mute state, or nil if the device exposes no mute property.
  private static func deviceIsMuted(_ device: AudioDeviceID) -> Bool? {
    var addr = muteAddress()
    guard AudioObjectHasProperty(device, &addr) else { return nil }
    var muted = UInt32(0)
    var size = UInt32(MemoryLayout<UInt32>.size)
    guard AudioObjectGetPropertyData(device, &addr, 0, nil, &size, &muted) == noErr else { return nil }
    return muted != 0
  }

  @discardableResult
  private static func setMute(_ device: AudioDeviceID, muted: Bool) -> Bool {
    var addr = muteAddress()
    var settable = DarwinBoolean(false)
    guard AudioObjectHasProperty(device, &addr),
      AudioObjectIsPropertySettable(device, &addr, &settable) == noErr,
      settable.boolValue
    else { return false }
    var value: UInt32 = muted ? 1 : 0
    let size = UInt32(MemoryLayout<UInt32>.size)
    return AudioObjectSetPropertyData(device, &addr, 0, nil, size, &value) == noErr
  }

  private static func volumeAddress(_ channel: UInt32) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyVolumeScalar,
      mScope: kAudioObjectPropertyScopeOutput,
      mElement: channel)
  }

  private static func getVolume(_ device: AudioDeviceID, channel: UInt32) -> Float32? {
    var addr = volumeAddress(channel)
    guard AudioObjectHasProperty(device, &addr) else { return nil }
    var value = Float32(0)
    var size = UInt32(MemoryLayout<Float32>.size)
    guard AudioObjectGetPropertyData(device, &addr, 0, nil, &size, &value) == noErr else { return nil }
    return value
  }

  @discardableResult
  private static func setVolume(_ device: AudioDeviceID, channel: UInt32, value: Float32) -> Bool {
    var addr = volumeAddress(channel)
    var settable = DarwinBoolean(false)
    guard AudioObjectHasProperty(device, &addr),
      AudioObjectIsPropertySettable(device, &addr, &settable) == noErr,
      settable.boolValue
    else { return false }
    var v = value
    let size = UInt32(MemoryLayout<Float32>.size)
    return AudioObjectSetPropertyData(device, &addr, 0, nil, size, &v) == noErr
  }

  /// Zero out the device volume, returning the prior values so they can be restored.
  /// Tries the master element first, then falls back to per-channel (stereo).
  private static func zeroVolume(_ device: AudioDeviceID) -> [(channel: UInt32, value: Float32)] {
    let main = kAudioObjectPropertyElementMain
    if let prior = getVolume(device, channel: main), setVolume(device, channel: main, value: 0) {
      return [(channel: main, value: prior)]
    }
    var saved: [(channel: UInt32, value: Float32)] = []
    for ch: UInt32 in [1, 2] {
      if let prior = getVolume(device, channel: ch), setVolume(device, channel: ch, value: 0) {
        saved.append((channel: ch, value: prior))
      }
    }
    return saved
  }
}
