@preconcurrency import AVFoundation
import AppKit
import CoreAudio
import CoreGraphics
import Foundation
import IOKit

/// Launch provenance is set once from the consumed Sparkle marker. A later wake
/// supplies its own context at the capture start boundary.
@MainActor
enum CaptureLaunchContext {
  enum Kind: String {
    case updateRelaunch = "update_relaunch"
    case wake
    case other
  }
  static let launchedAt = Date()
  static var kind: Kind = .other
  static var updateAttemptID: String?
  static var defaultInputAtLaunch = AudioCaptureService.currentDefaultInputDeviceID()
  static var hasStartedCapture = false

  static func setPendingRelaunch(_ pending: PendingUpdateRelaunch?) {
    _ = launchedAt
    defaultInputAtLaunch = AudioCaptureService.currentDefaultInputDeviceID()
    guard let pending else { return }
    kind = .updateRelaunch
    updateAttemptID = pending.attempt?.id
  }

  static func kindForStart(override: Kind? = nil) -> Kind {
    if let override { return override }
    if kind == .updateRelaunch {
      return hasStartedCapture ? .other : .updateRelaunch
    }
    return kind
  }

  static func timeBucket(_ interval: TimeInterval?) -> String {
    guard let interval, interval >= 0 else { return "unknown" }
    switch interval {
    case ..<10: return "0_10s"
    case ..<30: return "10_30s"
    case ..<60: return "30_60s"
    case ..<300: return "1_5m"
    case ..<3600: return "5_60m"
    case ..<86400: return "1_24h"
    default: return "24h_plus"
    }
  }
}

/// Presence is sampled at the decision, not inferred from app activation. Nil
/// means macOS did not provide a trustworthy answer.
struct CapturePresence: Equatable {
  let screenLocked: Bool?
  let displaysAsleep: Bool?
  let consoleSessionActive: Bool?
  let lidClosed: Bool?
  let appActive: Bool

  @MainActor static func current() -> Self {
    let session = CGSessionCopyCurrentDictionary() as? [String: Any]
    let console = session?["kCGSSessionOnConsoleKey"] as? Bool
    let locked: Bool? = session.map { $0["CGSSessionScreenIsLocked"] as? Bool ?? false }
    var displays = [CGDirectDisplayID](repeating: 0, count: 16)
    var count: UInt32 = 0
    let status = CGGetOnlineDisplayList(UInt32(displays.count), &displays, &count)
    let asleep: Bool? =
      status == .success && count > 0
      ? displays.prefix(Int(count)).allSatisfy { CGDisplayIsAsleep($0) != 0 } : nil
    let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("IOPMrootDomain"))
    let lidClosed: Bool?
    if service != 0 {
      lidClosed =
        IORegistryEntryCreateCFProperty(
          service, "AppleClamshellState" as CFString, kCFAllocatorDefault, 0)?
        .takeRetainedValue() as? Bool
      IOObjectRelease(service)
    } else {
      lidClosed = nil
    }
    return Self(
      screenLocked: locked, displaysAsleep: asleep,
      consoleSessionActive: console, lidClosed: lidClosed, appActive: NSApp?.isActive ?? false)
  }
}

/// The exact, content-free PostHog contract for watchdog and armed lifecycle
/// events. Unknown HAL facts stay "unknown"; we never send device identifiers.
enum SilentMicDiagnosticTelemetry {
  static let eventName = "Desktop Silent Mic Diagnostic"
  static let armedEventName = "Desktop Microphone Armed"

  struct Snapshot {
    let attemptID: String
    let recoveryAttempt: Int
    let phase: String
    let result: String
    let launchContext: String
    let updateAttemptID: String?
    let secondsSinceLaunch: String
    let secondsSinceWake: String
    let secondsSinceUnlock: String
    let presence: CapturePresence
    let transport: String
    let isSystemDefault: Bool?
    let healedRouteOverride: Bool
    let deviceIsAlive: Bool?
    let deviceIsRunningSomewhere: Bool?
    let hogModePIDPresent: Bool?
    let nominalSampleRate: String
    let channelCount: String
    let inputDeviceCount: String
    let defaultInputChangedSinceLaunch: Bool?
    let framesReceived: String
    let signalClass: String
    let peak: String
    let timeToFirstFrame: String
    let micAuthorization: String
  }

  static func properties(_ s: Snapshot) -> [String: Any] {
    [
      "platform": "macos", "attempt_id": s.attemptID,
      "recovery_attempt": min(s.recoveryAttempt, 20), "phase": s.phase, "result": s.result,
      "launch_context": s.launchContext, "update_attempt_id": s.updateAttemptID ?? "none",
      "seconds_since_launch": s.secondsSinceLaunch, "seconds_since_wake": s.secondsSinceWake,
      "seconds_since_unlock": s.secondsSinceUnlock,
      "screen_locked": optional(s.presence.screenLocked),
      "displays_asleep": optional(s.presence.displaysAsleep),
      "console_session_active": optional(s.presence.consoleSessionActive),
      "lid_closed": optional(s.presence.lidClosed),
      "app_active": s.presence.appActive, "input_transport": s.transport,
      "input_is_system_default": optional(s.isSystemDefault),
      "healed_route_override": s.healedRouteOverride,
      "device_is_alive": optional(s.deviceIsAlive),
      "device_is_running_somewhere": optional(s.deviceIsRunningSomewhere),
      "hog_mode_pid_present": optional(s.hogModePIDPresent),
      "nominal_sample_rate": s.nominalSampleRate, "channel_count": s.channelCount,
      "input_device_count": s.inputDeviceCount,
      "default_input_changed_since_launch": optional(s.defaultInputChangedSinceLaunch),
      "frames_received": s.framesReceived, "signal_class": s.signalClass,
      "peak": s.peak, "time_to_first_frame": s.timeToFirstFrame,
      "mic_authorization": s.micAuthorization,
    ]
  }

  static func armedProperties(
    attemptID: String, phase: String, trigger: String, launchContext: String,
    updateAttemptID: String?, duration: String
  ) -> [String: Any] {
    [
      "platform": "macos", "attempt_id": attemptID, "phase": phase,
      "trigger": trigger, "launch_context": launchContext,
      "update_attempt_id": updateAttemptID ?? "none", "armed_duration": duration,
    ]
  }

  private static func optional(_ value: Bool?) -> String {
    value.map { $0 ? "true" : "false" } ?? "unknown"
  }

  static func countBucket(_ count: Int) -> String {
    switch count {
    case ..<1: return "0"
    case 1: return "1"
    case 2...9: return "2_9"
    case 10...99: return "10_99"
    default: return "100_plus"
    }
  }

  static func rateBucket(_ rate: Double?) -> String {
    guard let rate else { return "unknown" }
    if rate < 16000 { return "below_16k" }
    if rate < 32000 { return "16_32k" }
    if rate < 48000 { return "32_48k" }
    if rate < 96000 { return "48_96k" }
    return "96k_plus"
  }

  static func authorization(_ status: AVAuthorizationStatus) -> String {
    switch status {
    case .authorized: return "authorized"
    case .denied: return "denied"
    case .restricted: return "restricted"
    case .notDetermined: return "not_determined"
    @unknown default: return "unknown"
    }
  }
}

/// At most six diagnostics per attempt and 24 per hour in this process.
struct SilentMicDiagnosticRateLimit {
  private var hourStart: Date?
  private var hourlyCount = 0
  private var perAttempt: [String: Int] = [:]

  mutating func allow(attemptID: String, now: Date) -> Bool {
    if hourStart.map({ now.timeIntervalSince($0) >= 3600 }) ?? true {
      hourStart = now
      hourlyCount = 0
      perAttempt.removeAll()
    }
    guard hourlyCount < 24, perAttempt[attemptID, default: 0] < 6 else { return false }
    hourlyCount += 1
    perAttempt[attemptID, default: 0] += 1
    return true
  }
}

enum SilentMicHALSnapshot {
  struct Facts {
    let transport: String
    let alive: Bool?
    let running: Bool?
    let hog: Bool?
    let rate: Double?
    let channels: Int?
    let inputCount: Int
  }

  static func collect(deviceID: AudioDeviceID?) -> Facts {
    let count = AudioCaptureService.availableInputDevices().count
    guard let deviceID else {
      return Facts(
        transport: "unknown", alive: nil, running: nil, hog: nil, rate: nil, channels: nil, inputCount: count)
    }
    let transportCode = scalar(deviceID, kAudioDevicePropertyTransportType, scope: kAudioObjectPropertyScopeGlobal)
    let transport: String
    switch transportCode {
    case kAudioDeviceTransportTypeBuiltIn: transport = "built_in"
    case kAudioDeviceTransportTypeBluetooth, kAudioDeviceTransportTypeBluetoothLE: transport = "bluetooth"
    case kAudioDeviceTransportTypeUSB: transport = "usb"
    case kAudioDeviceTransportTypeVirtual: transport = "virtual"
    case kAudioDeviceTransportTypeAggregate: transport = "aggregate"
    default: transport = "other"
    }
    let alive = scalar(deviceID, kAudioDevicePropertyDeviceIsAlive, scope: kAudioObjectPropertyScopeGlobal).map {
      $0 != 0
    }
    let running = scalar(deviceID, kAudioDevicePropertyDeviceIsRunningSomewhere, scope: kAudioObjectPropertyScopeGlobal)
      .map { $0 != 0 }
    let hog = scalar(deviceID, kAudioDevicePropertyHogMode, scope: kAudioObjectPropertyScopeGlobal).map {
      Int32(bitPattern: $0) > 0
    }
    var rate: Double = 0
    var size = UInt32(MemoryLayout<Double>.size)
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyNominalSampleRate, mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    let rateKnown = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &rate) == noErr
    var format = AudioStreamBasicDescription()
    var formatSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
    var formatAddress = AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyStreamFormat, mScope: kAudioDevicePropertyScopeInput,
      mElement: kAudioObjectPropertyElementMain)
    let formatKnown =
      AudioObjectGetPropertyData(
        deviceID, &formatAddress, 0, nil, &formatSize, &format) == noErr
    return Facts(
      transport: transport, alive: alive, running: running, hog: hog,
      rate: rateKnown ? rate : nil,
      channels: formatKnown ? Int(format.mChannelsPerFrame) : nil, inputCount: count)
  }

  private static func scalar(
    _ id: AudioDeviceID, _ selector: AudioObjectPropertySelector, scope: AudioObjectPropertyScope
  ) -> UInt32? {
    var value: UInt32 = 0
    var size = UInt32(MemoryLayout<UInt32>.size)
    var address = AudioObjectPropertyAddress(
      mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
    return AudioObjectGetPropertyData(id, &address, 0, nil, &size, &value) == noErr ? value : nil
  }
}
