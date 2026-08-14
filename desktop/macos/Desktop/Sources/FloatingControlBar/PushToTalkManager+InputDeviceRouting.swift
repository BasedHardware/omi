@preconcurrency import CoreAudio
import Foundation

/// The CoreAudio reads PTT routing needs, behind a seam so a fault test can stall
/// the HAL without a genuinely wedged driver.
struct PTTAudioDeviceProbe: Sendable {
  var inputDeviceID: @Sendable (String) -> AudioDeviceID?
  var outputIsBluetooth: @Sendable () -> Bool
  var builtInMicDeviceID: @Sendable () -> AudioDeviceID?
  // Explicit, never defaulted: a defaulted real-HAL closure inside an injected
  // fake would silently defeat the hermetic probe seam these tests rely on.
  var defaultInputDeviceID: @Sendable () -> AudioDeviceID?
  var isBluetoothInput: @Sendable (AudioDeviceID) -> Bool

  static let coreAudio = PTTAudioDeviceProbe(
    inputDeviceID: { AudioCaptureService.inputDeviceID(forUID: $0) },
    outputIsBluetooth: { AudioCaptureService.isDefaultOutputBluetooth() },
    builtInMicDeviceID: { AudioCaptureService.findBuiltInMicDeviceID() },
    defaultInputDeviceID: { AudioCaptureService.currentDefaultInputDeviceID() },
    isBluetoothInput: { AudioCaptureService.isBluetoothTransport(deviceID: $0) }
  )
}

/// Resolves the PTT microphone policy without coupling the selection policy to
/// CoreAudio enumeration. An explicit user choice always wins; Automatic keeps
/// Bluetooth output on A2DP by preferring the built-in microphone.
///
/// CoreAudio property reads have no deadline and no cancellation: against a wedged
/// audio driver they block for as long as the driver stays wedged. PTT resolves its
/// input device on the main actor at turn start, so those reads must never happen
/// there — not even behind a bounded wait, which still freezes the run loop for the
/// whole budget. The HAL is therefore read only on `probeQueue`, and the main actor
/// reads the resulting snapshot under a lock.
enum PTTInputDeviceRouting {
  static func overrideDeviceID(
    selectedDeviceID: AudioDeviceID?,
    outputIsBluetooth: Bool,
    builtInDeviceID: AudioDeviceID?
  ) -> AudioDeviceID? {
    selectedDeviceID ?? (outputIsBluetooth ? builtInDeviceID : nil)
  }

  /// One completed HAL read. Carries the UID it was resolved for so a snapshot
  /// taken before the user changed their microphone is never applied afterwards.
  struct Snapshot: Sendable, Equatable {
    let selectedUID: String
    let selectedDeviceID: AudioDeviceID?
    let outputIsBluetooth: Bool
    let builtInDeviceID: AudioDeviceID?
    var defaultInputDeviceID: AudioDeviceID? = nil
    var defaultInputIsBluetooth: Bool = false
    /// True when this snapshot was probed while a capture was live, i.e. the
    /// contention fields above are meaningful rather than skipped-for-cost.
    var contentionResolved: Bool = false

    var overrideDeviceID: AudioDeviceID? {
      PTTInputDeviceRouting.overrideDeviceID(
        selectedDeviceID: selectedDeviceID,
        outputIsBluetooth: outputIsBluetooth,
        builtInDeviceID: builtInDeviceID)
    }
  }

  private static let store = SnapshotStore()

  private static let probeQueue = DispatchQueue(
    label: "com.omi.ptt.input-device-probe", qos: .userInitiated)

  /// The routing resolved for `selectedUID`, or `nil` when no snapshot has landed for
  /// it yet. Returning the whole snapshot rather than just the device ID lets a caller
  /// tell a real "no override needed" answer from "the HAL has not answered yet" from a
  /// single read, so the two cannot disagree across a concurrent refresh.
  ///
  /// Never touches CoreAudio, so it is safe on the main actor at PTT turn start.
  static func currentSnapshot(selectedUID: String) -> Snapshot? {
    store.snapshot(matching: selectedUID)
  }

  /// Reads the HAL off the main thread and publishes a new snapshot.
  ///
  /// Coalesced: while one read is outstanding, further calls are dropped. A wedged
  /// driver therefore parks exactly one queue thread no matter how many PTT turns the
  /// user starts, instead of leaking one per turn.
  static func refresh(
    selectedUID: String,
    probe: PTTAudioDeviceProbe = .coreAudio,
    completion: (@Sendable () -> Void)? = nil
  ) {
    guard store.beginRefresh() else {
      completion?()
      return
    }
    probeQueue.async {
      let selectedDeviceID = selectedUID.isEmpty ? nil : probe.inputDeviceID(selectedUID)
      let outputIsBluetooth = probe.outputIsBluetooth()
      // The contention fallback only matters while another capture in this
      // process is live, so the extra HAL reads it needs — the built-in mic
      // walk (the most expensive device-list enumeration) and the default
      // input — are gated on that registry state. With no live capture the
      // probe pattern is identical to the pre-contention behavior.
      let contentionPossible = AudioCaptureService.hasActiveCapture()
      let defaultInputDeviceID = contentionPossible ? probe.defaultInputDeviceID() : nil
      store.finishRefresh(
        Snapshot(
          selectedUID: selectedUID,
          selectedDeviceID: selectedDeviceID,
          outputIsBluetooth: outputIsBluetooth,
          builtInDeviceID: (outputIsBluetooth || contentionPossible) ? probe.builtInMicDeviceID() : nil,
          defaultInputDeviceID: defaultInputDeviceID,
          defaultInputIsBluetooth: defaultInputDeviceID.map(probe.isBluetoothInput) ?? false,
          contentionResolved: contentionPossible
        ))
      completion?()
    }
  }

  static func resetForTests() {
    store.reset()
  }
}

private final class SnapshotStore: @unchecked Sendable {
  private let lock = NSLock()
  private var stored: PTTInputDeviceRouting.Snapshot?
  private var refreshing = false

  func snapshot(matching selectedUID: String) -> PTTInputDeviceRouting.Snapshot? {
    lock.lock()
    defer { lock.unlock() }
    guard let stored, stored.selectedUID == selectedUID else { return nil }
    return stored
  }

  func beginRefresh() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    if refreshing { return false }
    refreshing = true
    return true
  }

  func finishRefresh(_ snapshot: PTTInputDeviceRouting.Snapshot) {
    lock.lock()
    defer { lock.unlock() }
    stored = snapshot
    refreshing = false
  }

  func reset() {
    lock.lock()
    defer { lock.unlock() }
    stored = nil
    refreshing = false
  }
}

@MainActor
extension PushToTalkManager {
  /// Non-blocking. Kicks the next HAL read and answers from the last one that landed.
  func preferredPTTInputOverrideDeviceID() -> AudioDeviceID? {
    let selectedUID = ShortcutSettings.unifiedMicrophoneUID
    let snapshot = PTTInputDeviceRouting.currentSnapshot(selectedUID: selectedUID)
    if let snapshot, !selectedUID.isEmpty, snapshot.selectedDeviceID == nil {
      log("PushToTalkManager: selected PTT microphone is unavailable — using Automatic")
    }
    if snapshot == nil {
      log("PushToTalkManager: PTT input routing not resolved yet — using the system default input")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "ptt_input_routing",
        from: "resolved_routing",
        to: "system_default_input",
        reason: "timeout",
        outcome: .degraded)
    }
    PTTInputDeviceRouting.refresh(selectedUID: selectedUID)
    return applyMicContentionPolicy(to: snapshot)
  }

  /// PTT must not open a second CoreAudio IOProc against a device another
  /// capture in this process already holds (e.g. transcription capturing from
  /// Ray-Ban Meta glasses), and must not join a Bluetooth mic's A2DP↔HFP
  /// profile flap while any capture runs — both race the two captures'
  /// stream-format reconfiguration. The active-capture registry is lock-guarded
  /// process state, not a HAL read, so consulting it here is main-actor safe.
  /// This manager's own parked warm capture is excluded: adopting it is reuse,
  /// not contention. An explicit user mic choice is always respected.
  private func applyMicContentionPolicy(
    to snapshot: PTTInputDeviceRouting.Snapshot?
  ) -> AudioDeviceID? {
    guard let snapshot else { return nil }
    let overrideID = snapshot.overrideDeviceID
    let parkedCapture = parkedMicCapture?.service
    if snapshot.selectedDeviceID == nil, overrideID == nil,
      !snapshot.contentionResolved,
      AudioCaptureService.hasActiveCapture(excluding: parkedCapture)
    {
      // The snapshot predates the live capture, so the contention fields were
      // skipped for cost and this turn cannot see the contended device. The
      // refresh this call already kicked will carry them for the next turn;
      // surface the blind turn instead of hiding it.
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "ptt_input_routing",
        from: "resolved_routing",
        to: "system_default_input",
        reason: "stale_contention_snapshot",
        outcome: .degraded)
      return overrideID
    }
    if snapshot.selectedDeviceID == nil, overrideID == nil,
      let defaultInput = snapshot.defaultInputDeviceID,
      let builtIn = snapshot.builtInDeviceID,
      defaultInput != builtIn
    {
      if AudioCaptureService.isDeviceActivelyCaptured(defaultInput, excluding: parkedCapture) {
        log("PushToTalkManager: default input is held by another capture — using built-in mic")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "ptt_input_routing",
          from: "default_input",
          to: "built_in_mic",
          reason: "device_contention",
          outcome: .degraded)
        return builtIn
      }
      if AudioCaptureService.hasActiveCapture(excluding: parkedCapture),
        snapshot.defaultInputIsBluetooth
      {
        log("PushToTalkManager: Bluetooth input while another capture is live — using built-in mic")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "ptt_input_routing",
          from: "bluetooth_default_input",
          to: "built_in_mic",
          reason: "bluetooth_contention",
          outcome: .degraded)
        return builtIn
      }
    }
    return overrideID
  }

  /// Warms the routing snapshot at the start of a turn, before the turn's own setup
  /// work, so the HAL read overlaps that work instead of gating capture on it.
  func warmPTTInputRouting() {
    PTTInputDeviceRouting.refresh(selectedUID: ShortcutSettings.unifiedMicrophoneUID)
  }
}
