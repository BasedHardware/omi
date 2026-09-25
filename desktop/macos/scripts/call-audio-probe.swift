// Call-boundary probe: records which processes hold the microphone and speaker, and which
// call-like windows are on screen, as JSON lines with wall-clock timestamps.
//
// It measures the inputs a call-session detector would use (mic acquire/release per process,
// two-way audio, window titles) so boundary rules can be fitted to real traces instead of
// guessed. It is read-only: no audio is captured, only CoreAudio process state and window
// metadata. Window titles need Screen Recording permission for the terminal running it;
// without it, titles are simply absent.
//
// Usage (macOS 14.4+):
//   xcrun swift desktop/macos/scripts/call-audio-probe.swift > /tmp/call-probe.jsonl
// Type a line and press Return to insert a {"event":"note"} marker (e.g. "left meet A").
// Ctrl-C to stop.

import AppKit
import CoreAudio
import Foundation

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

func emit(_ fields: [String: Any]) {
  var record = fields
  record["t"] = isoFormatter.string(from: Date())
  guard let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
    let line = String(data: data, encoding: .utf8)
  else { return }
  print(line)
  fflush(stdout)
}

func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
  AudioObjectPropertyAddress(
    mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
}

func processObjects() -> [AudioObjectID] {
  var addr = address(kAudioHardwarePropertyProcessObjectList)
  let system = AudioObjectID(kAudioObjectSystemObject)
  var size: UInt32 = 0
  guard AudioObjectGetPropertyDataSize(system, &addr, 0, nil, &size) == noErr, size > 0 else { return [] }
  var objects = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
  guard AudioObjectGetPropertyData(system, &addr, 0, nil, &size, &objects) == noErr else { return [] }
  return objects
}

func boolProperty(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> Bool {
  var addr = address(selector)
  var value: UInt32 = 0
  var size = UInt32(MemoryLayout<UInt32>.size)
  return AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &value) == noErr && value != 0
}

func pid(of object: AudioObjectID) -> pid_t {
  var addr = address(kAudioProcessPropertyPID)
  var value: pid_t = -1
  var size = UInt32(MemoryLayout<pid_t>.size)
  _ = AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &value)
  return value
}

func bundleID(of object: AudioObjectID) -> String {
  var addr = address(kAudioProcessPropertyBundleID)
  var unmanaged: Unmanaged<CFString>?
  var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
  let status = withUnsafeMutablePointer(to: &unmanaged) {
    AudioObjectGetPropertyData(object, &addr, 0, nil, &size, $0)
  }
  guard status == noErr, let value = unmanaged?.takeRetainedValue() as String? else { return "" }
  return value
}

struct ProcessState: Equatable {
  var input = false
  var output = false
}

final class Probe {
  private var states: [AudioObjectID: ProcessState] = [:]
  private var identities: [AudioObjectID: (pid: pid_t, bundle: String)] = [:]
  private var watched = Set<AudioObjectID>()
  private var listeners: [AudioObjectID: AudioObjectPropertyListenerBlock] = [:]
  private var titles: [String: String] = [:]
  private let queue = DispatchQueue.main

  func start() {
    var listAddr = address(kAudioHardwarePropertyProcessObjectList)
    AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &listAddr, queue) {
      [weak self] _, _ in self?.refreshProcessList()
    }
    refreshProcessList()
    Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in self?.sampleWindows() }
    sampleWindows()
    emit(["event": "probe_started", "os": ProcessInfo.processInfo.operatingSystemVersionString])
  }

  private func refreshProcessList() {
    let current = Set(processObjects())
    for gone in watched.subtracting(current) {
      if let state = states[gone], state.input || state.output, let id = identities[gone] {
        emit(["event": "process_gone", "pid": Int(id.pid), "bundle": id.bundle])
      }
      states[gone] = nil
      identities[gone] = nil
      // Unregister, or CoreAudio keeps every process object that ever touched audio alive.
      if let block = listeners.removeValue(forKey: gone) {
        for selector in [kAudioProcessPropertyIsRunningInput, kAudioProcessPropertyIsRunningOutput] {
          var addr = address(selector)
          AudioObjectRemovePropertyListenerBlock(gone, &addr, queue, block)
        }
      }
    }
    for object in current.subtracting(watched) {
      identities[object] = (pid(of: object), bundleID(of: object))
      let block: AudioObjectPropertyListenerBlock = { [weak self] _, _ in self?.sample(object) }
      listeners[object] = block
      for selector in [kAudioProcessPropertyIsRunningInput, kAudioProcessPropertyIsRunningOutput] {
        var addr = address(selector)
        AudioObjectAddPropertyListenerBlock(object, &addr, queue, block)
      }
      sample(object)
    }
    watched = current
  }

  private func sample(_ object: AudioObjectID) {
    let next = ProcessState(
      input: boolProperty(object, kAudioProcessPropertyIsRunningInput),
      output: boolProperty(object, kAudioProcessPropertyIsRunningOutput))
    let previous = states[object] ?? ProcessState()
    states[object] = next
    guard let id = identities[object] else { return }
    let base: [String: Any] = ["pid": Int(id.pid), "bundle": id.bundle]
    if next.input != previous.input {
      emit(base.merging(["event": next.input ? "input_start" : "input_stop", "two_way": next.input && next.output]) { $1 })
    }
    if next.output != previous.output {
      emit(base.merging(["event": next.output ? "output_start" : "output_stop", "two_way": next.input && next.output]) { $1 })
    }
  }

  /// Titles of on-screen windows owned by apps that currently hold audio, plus browsers.
  private func sampleWindows() {
    let audioPIDs = Set(states.filter { $0.value.input || $0.value.output }.compactMap { identities[$0.key]?.pid })
    let browsers: Set<String> = ["Google Chrome", "Arc", "Safari", "Firefox", "Microsoft Edge", "Brave Browser", "Helium"]
    guard let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
      as? [[String: Any]]
    else { return }
    var seen: [String: String] = [:]
    for window in windows {
      let owner = window[kCGWindowOwnerName as String] as? String ?? ""
      let ownerPID = window[kCGWindowOwnerPID as String] as? pid_t ?? -1
      guard let title = window[kCGWindowName as String] as? String, !title.isEmpty else { continue }
      guard browsers.contains(owner) || audioPIDs.contains(ownerPID) else { continue }
      let key = "\(owner)#\(window[kCGWindowNumber as String] as? Int ?? 0)"
      seen[key] = title
      if titles[key] != title {
        emit(["event": "window_title", "owner": owner, "pid": Int(ownerPID), "window": key, "title": title])
      }
    }
    for (key, _) in titles where seen[key] == nil {
      emit(["event": "window_gone", "window": key])
    }
    titles = seen
  }
}

let probe = Probe()
probe.start()
FileHandle.standardInput.readabilityHandler = { handle in
  let data = handle.availableData
  guard !data.isEmpty else {
    handle.readabilityHandler = nil  // EOF: stop polling a closed stdin
    return
  }
  guard let text = String(data: data, encoding: .utf8) else { return }
  for line in text.split(separator: "\n") where !line.trimmingCharacters(in: .whitespaces).isEmpty {
    DispatchQueue.main.async { emit(["event": "note", "text": String(line)]) }
  }
}
// Ctrl-C is delivered through a dispatch source on the main queue, so the stop marker is
// written from ordinary code rather than from an async-signal-unsafe handler.
signal(SIGINT, SIG_IGN)
let interrupt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
interrupt.setEventHandler {
  emit(["event": "probe_stopped"])
  exit(0)
}
interrupt.resume()
RunLoop.main.run()
