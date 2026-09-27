import Foundation

/// Per-bundle microphone counters for one local day. Counts and duration
/// buckets only — no pids, device names, or window titles.
struct CallAudioBundleCounters: Codable, Equatable, Sendable {
  var callLikeSessions = 0
  var releasesCallEnd = 0
  var releasesMuteLike = 0
  var releasesDeviceSwitch = 0
  var reacquireGapLt2s = 0
  var reacquireGap2to10s = 0
  var reacquireGap10to60s = 0
  var reacquireGap60to300s = 0
  var sessionLt1m = 0
  var session1to10m = 0
  var session10to60m = 0
  var sessionGe60m = 0
}

/// Classifies microphone releases and two-way sessions from timestamped snapshots.
///
/// A bundle is "running input" when any of its processes is. `deviceSwitch`
/// (default input device changed within ±2s of the stop) wins over `callEnd`
/// (output already stopped, or stops within 1s) and `muteLike` (output keeps
/// running for at least 2s). Classification waits out that 2s window so a late
/// device change is not counted as a call end. Reacquire gaps longer than 300s
/// are dropped. A call-like session is two-way audio lasting at least 60s.
struct CallAudioSessionTracker {
  private struct Runtime {
    var input = false
    var twoWayStartedAt: Date?
    var pending: PendingRelease?
    var lastReleaseAt: Date?
    var hadInputRelease = false
    var generation = 0
  }

  private struct PendingRelease {
    var at: Date
    var outputWasRunning: Bool
    var outputStoppedAt: Date?
    var latestOutputOnAt: Date?
    /// Set once input is back. Later samples belong to the new session, so
    /// they must not extend the evidence for this release.
    var inputReturnedAt: Date?
  }

  private var runtime: [String: Runtime] = [:]
  private(set) var counters: [String: CallAudioBundleCounters] = [:]
  private var lastDeviceID: UInt32?
  private var deviceChangeTimes: [Date] = []

  init(counters: [String: CallAudioBundleCounters] = [:]) {
    self.counters = counters
  }

  mutating func ingest(_ snapshot: CallAudioSnapshot, at now: Date) {
    noteDevice(snapshot.defaultInputDeviceID, at: now)
    var flags: [String: (input: Bool, output: Bool)] = [:]
    for process in snapshot.processes {
      let bundle = Self.appKey(process.bundleID)
      guard !bundle.isEmpty else { continue }
      var current = flags[bundle] ?? (false, false)
      current.input = current.input || process.isRunningInput
      current.output = current.output || process.isRunningOutput
      flags[bundle] = current
    }
    let bundles = Set(flags.keys).union(runtime.keys)
    for bundle in bundles {
      let audio = flags[bundle] ?? (false, false)
      ingest(bundle: bundle, input: audio.input, output: audio.output, at: now)
    }
  }

  /// The key a process is counted under. Electron and Chromium apps split audio across helper
  /// processes (a Discord call holds the mic in `com.hnc.discord.helper.renderer`), so helpers
  /// are folded into their app: a catalogued call app resolves through
  /// `ConferencingApps.nativeCallAppID`, and any other `<app>.helper[.<kind>]` drops the helper
  /// suffix. Call identities, the release catalog, and the daily summary all use this key.
  static func appKey(_ bundleID: String) -> String {
    if let appID = ConferencingApps.nativeCallAppID(bundleID: bundleID) { return appID }
    let lower = bundleID.lowercased()
    if let range = lower.range(of: #"\.helper(\.[a-z0-9_-]+)*$"#, options: .regularExpression) {
      return String(lower[..<range.lowerBound])
    }
    return lower
  }

  /// `app:<bundle>#<n>` when the catalog says a mic release ends the call.
  /// `n` starts at 1 and increments each time that app re-acquires input after
  /// a release. Every other bundle keeps `app:<bundle>`.
  func nativeCallIdentity(bundleID: String) -> String {
    let bundle = bundleID.lowercased()
    guard CallAppReleasePolicy.releaseEndsCall(bundleID: bundle) else {
      return "app:\(bundle)"
    }
    let generation = runtime[bundle]?.generation ?? 0
    return "app:\(bundle)#\(max(generation, 1))"
  }

  /// Count a two-way session that is still open, using `now` as its end.
  /// Called when the local day rolls so the in-progress call is not dropped.
  mutating func closeOpenSessions(at now: Date) {
    for bundle in Array(runtime.keys) {
      guard var state = runtime[bundle], let started = state.twoWayStartedAt else { continue }
      recordSession(bundle: bundle, duration: now.timeIntervalSince(started))
      state.twoWayStartedAt = nil
      runtime[bundle] = state
    }
  }

  private mutating func noteDevice(_ deviceID: UInt32, at now: Date) {
    if let lastDeviceID, lastDeviceID != deviceID {
      deviceChangeTimes.append(now)
    }
    lastDeviceID = deviceID
    deviceChangeTimes.removeAll { now.timeIntervalSince($0) > 30 }
  }

  private mutating func ingest(bundle: String, input: Bool, output: Bool, at now: Date) {
    var state = runtime[bundle] ?? Runtime()
    let wasInput = state.input

    let twoWay = input && output
    if twoWay {
      if state.twoWayStartedAt == nil { state.twoWayStartedAt = now }
    } else if let started = state.twoWayStartedAt {
      recordSession(bundle: bundle, duration: now.timeIntervalSince(started))
      state.twoWayStartedAt = nil
    }

    let justReleased = wasInput && !input
    if justReleased {
      state.lastReleaseAt = now
      state.hadInputRelease = true
      state.pending = PendingRelease(
        at: now,
        outputWasRunning: output,
        outputStoppedAt: nil,
        latestOutputOnAt: output ? now : nil,
        inputReturnedAt: nil)
    }

    if !wasInput && input {
      if state.pending != nil {
        state.pending?.inputReturnedAt = now
      }
      if let releaseAt = state.lastReleaseAt {
        recordGap(bundle: bundle, gap: now.timeIntervalSince(releaseAt))
        state.lastReleaseAt = nil
      }
      if CallAppReleasePolicy.releaseEndsCall(bundleID: bundle) {
        if state.hadInputRelease {
          state.generation = max(state.generation, 1) + 1
        } else if state.generation == 0 {
          state.generation = 1
        }
      }
      state.hadInputRelease = false
    }

    if var pending = state.pending {
      // Output after the mic is back is the next session, not this release.
      if !input && !justReleased && pending.inputReturnedAt == nil {
        if output {
          pending.latestOutputOnAt = now
        } else if pending.outputWasRunning, pending.outputStoppedAt == nil {
          pending.outputStoppedAt = now
        }
      }
      state.pending = pending
      if finalize(bundle: bundle, pending: pending, at: now) {
        state.pending = nil
      }
    }

    state.input = input
    runtime[bundle] = state
  }

  /// True once the release is decided (counted or discarded). A device change
  /// already inside the ±2s window decides immediately and wins over call-end
  /// and mute. Anything else waits until 2s after the stop.
  private mutating func finalize(bundle: String, pending: PendingRelease, at now: Date) -> Bool {
    let stop = pending.at
    let windowEnd = stop.addingTimeInterval(2)
    let deviceSwitched = deviceChangeTimes.contains { change in
      change >= stop.addingTimeInterval(-2) && change <= windowEnd && change <= now
    }
    if deviceSwitched {
      update(bundle) { $0.releasesDeviceSwitch += 1 }
      return true
    }
    guard now >= windowEnd else { return false }

    if !pending.outputWasRunning
      || pending.outputStoppedAt.map({ $0.timeIntervalSince(stop) <= 1 }) == true
    {
      update(bundle) { $0.releasesCallEnd += 1 }
      return true
    }
    // Mute requires output still running at least 2s after the stop, observed
    // while the mic was still released. Input coming back earlier is not enough.
    let returnedAt = pending.inputReturnedAt
    let heldPastWindow: Bool
    if let onAt = pending.latestOutputOnAt {
      if let returnedAt {
        heldPastWindow = onAt >= windowEnd && onAt < returnedAt
      } else {
        heldPastWindow = onAt >= windowEnd
      }
    } else {
      heldPastWindow = false
    }
    let outputStillReleased = pending.outputStoppedAt == nil && returnedAt == nil
    if outputStillReleased || heldPastWindow {
      update(bundle) { $0.releasesMuteLike += 1 }
    }
    return true
  }

  private mutating func recordGap(bundle: String, gap: TimeInterval) {
    guard gap >= 0 else { return }
    if gap < 2 {
      update(bundle) { $0.reacquireGapLt2s += 1 }
    } else if gap < 10 {
      update(bundle) { $0.reacquireGap2to10s += 1 }
    } else if gap < 60 {
      update(bundle) { $0.reacquireGap10to60s += 1 }
    } else if gap <= 300 {
      update(bundle) { $0.reacquireGap60to300s += 1 }
    }
  }

  private mutating func recordSession(bundle: String, duration: TimeInterval) {
    guard duration >= 0 else { return }
    update(bundle) { row in
      if duration < 60 {
        row.sessionLt1m += 1
      } else if duration < 600 {
        row.session1to10m += 1
        row.callLikeSessions += 1
      } else if duration < 3600 {
        row.session10to60m += 1
        row.callLikeSessions += 1
      } else {
        row.sessionGe60m += 1
        row.callLikeSessions += 1
      }
    }
  }

  private mutating func update(_ bundle: String, _ body: (inout CallAudioBundleCounters) -> Void) {
    var row = counters[bundle] ?? CallAudioBundleCounters()
    body(&row)
    counters[bundle] = row
  }
}
