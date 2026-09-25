import Foundation

/// Opt-in, in-app telemetry for the route switch into Chat.
///
/// A reader's "navigating to Chat feels slow" complaint cannot be answered from
/// the automation bridge's `navigate` round trip — that number includes the
/// bridge's own poll loop. This logger stamps the real in-app spans instead:
/// route-select entry, destination teardown, QueryShellHome construction,
/// transcript appearance, first laid-out document, the settled initial restore,
/// and the composer's caret claim. Every mark is printed as one
/// `SWITCH_PERF` line to stdout (the dev bundle redirects it to the app log),
/// each carrying milliseconds elapsed since that switch's `switchBegin`.
///
/// A switch also runs a main-thread stall watchdog: a background queue pings
/// the main queue every 5 ms until the switch ends and reports every gap over
/// 40 ms, so the span where the window cannot process input is measured
/// directly rather than inferred.
///
/// Disabled unless `OMI_SWITCH_PERF` is set in the environment, in which case
/// every call returns after one nil-check. It changes no behaviour; it only
/// prints.
enum ChatSwitchPerfLog {
  static let linePrefix = "SWITCH_PERF"

  private static let isEnabled: Bool = ProcessInfo.processInfo.environment["OMI_SWITCH_PERF"] != nil

  private static let lock = NSLock()
  // Guarded by `lock` above; `nonisolated(unsafe)` records that contract for
  // the concurrency checker, which cannot see a lock's exclusion.
  private nonisolated(unsafe) static var switchID = 0
  private nonisolated(unsafe) static var beganAt: DispatchTime = DispatchTime.now()
  private nonisolated(unsafe) static var firedEvents: Set<String> = []
  private nonisolated(unsafe) static var watchdog: StallWatchdog?

  /// Marks the moment a route change was requested and starts the watchdog.
  static func beginSwitch(destination: String) {
    guard isEnabled else { return }
    lock.lock()
    switchID += 1
    beganAt = DispatchTime.now()
    firedEvents = []
    let id = switchID
    let dog = StallWatchdog(switchID: id, origin: beganAt)
    watchdog = dog
    lock.unlock()
    dog.start()
    emit(switchID: id, event: "switchBegin", at: beganAt, beganAt: beganAt, detail: destination)
  }

  /// One timestamped span event. Fires every time; use `markOnce` for events
  /// SwiftUI may re-evaluate several times during one switch.
  static func mark(_ event: String, detail: String? = nil) {
    guard isEnabled else { return }
    lock.lock()
    let id = switchID
    let began = beganAt
    lock.unlock()
    guard id > 0 else { return }
    emit(switchID: id, event: event, at: DispatchTime.now(), beganAt: began, detail: detail)
  }

  /// Like `mark`, but only the first call per switch is recorded — for events
  /// raised from body evaluations or view updates that run repeatedly.
  static func markOnce(_ event: String, detail: String? = nil) {
    guard isEnabled else { return }
    lock.lock()
    guard !firedEvents.contains(event) else {
      lock.unlock()
      return
    }
    firedEvents.insert(event)
    let id = switchID
    let began = beganAt
    lock.unlock()
    guard id > 0 else { return }
    emit(switchID: id, event: event, at: DispatchTime.now(), beganAt: began, detail: detail)
  }

  /// Duration of an awaited span the caller bracketed with `DispatchTime.now()`.
  static func span(_ name: String, startedAt: DispatchTime) {
    guard isEnabled else { return }
    lock.lock()
    let id = switchID
    let began = beganAt
    lock.unlock()
    guard id > 0 else { return }
    let end = DispatchTime.now()
    let durationMs = Self.milliseconds(from: startedAt, to: end)
    let offsetMs = Self.milliseconds(from: began, to: end)
    print(
      "\(linePrefix) switch=\(id) event=\(name) t_ms=\(String(format: "%.1f", offsetMs)) duration_ms=\(String(format: "%.1f", durationMs))\(detailSuffix(nil))"
    )
  }

  /// Ends the current switch (watchdog included) and prints its worst stall.
  static func endSwitch(_ reason: String) {
    guard isEnabled else { return }
    lock.lock()
    let id = switchID
    let began = beganAt
    let dog = watchdog
    watchdog = nil
    lock.unlock()
    guard id > 0 else { return }
    let worst = dog?.stopAndReportWorstStall() ?? 0
    emit(
      switchID: id, event: "switchEnd", at: DispatchTime.now(), beganAt: began,
      detail: "\(reason) worst_stall_ms=\(String(format: "%.1f", worst))")
  }

  private static func emit(
    switchID: Int, event: String, at: DispatchTime, beganAt: DispatchTime, detail: String?
  ) {
    let offsetMs = milliseconds(from: beganAt, to: at)
    print(
      "\(linePrefix) switch=\(switchID) event=\(event) t_ms=\(String(format: "%.1f", offsetMs))\(detailSuffix(detail))"
    )
  }

  private static func detailSuffix(_ detail: String?) -> String {
    guard let detail, !detail.isEmpty else { return "" }
    return " detail=\(detail)"
  }

  private static func milliseconds(from start: DispatchTime, to end: DispatchTime) -> Double {
    Double(end.uptimeNanoseconds &- start.uptimeNanoseconds) / 1_000_000
  }
}

/// Bounds main-thread unresponsiveness during one switch. A background queue
/// asks the main queue to timestamp a hop every 5 ms; any hop that lands more
/// than 40 ms late is a span during which the window could not process input,
/// and each one is printed with its offset from the switch's start.
///
/// `@unchecked Sendable`: the pinger hops between its serial queue and the main
/// queue, and every mutable field is reached only under `lock`.
private final class StallWatchdog: @unchecked Sendable {
  private static let pingIntervalNs: UInt64 = 5_000_000
  private static let stallThresholdNs: UInt64 = 40_000_000
  /// Bounded lifetime: a switch whose settled mark never fires cannot run the
  /// pinger forever.
  private static let lifetimeNs: UInt64 = 6_000_000_000

  private let switchID: Int
  private let origin: DispatchTime
  private let queue = DispatchQueue(label: "omi.chat-switch-perf", qos: .userInteractive)
  private var timer: DispatchSourceTimer?
  private let lock = NSLock()
  private var worstStallNs: UInt64 = 0

  init(switchID: Int, origin: DispatchTime) {
    self.switchID = switchID
    self.origin = origin
  }

  func start() {
    lock.lock()
    defer { lock.unlock() }
    guard timer == nil else { return }
    let source = DispatchSource.makeTimerSource(queue: queue)
    source.schedule(
      deadline: .now() + .nanoseconds(Int(StallWatchdog.pingIntervalNs)),
      repeating: .nanoseconds(Int(StallWatchdog.pingIntervalNs)),
      leeway: .nanoseconds(1_000_000))
    source.setEventHandler { [weak self] in
      guard let self else { return }
      self.ping()
      if DispatchTime.now().uptimeNanoseconds &- self.origin.uptimeNanoseconds
        > StallWatchdog.lifetimeNs
      {
        ChatSwitchPerfLog.endSwitch("watchdog-timeout")
      }
    }
    timer = source
    source.resume()
  }

  private func ping() {
    let dispatchedAt = DispatchTime.now()
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      let lagNs = DispatchTime.now().uptimeNanoseconds &- dispatchedAt.uptimeNanoseconds
      self.lock.lock()
      if lagNs > self.worstStallNs {
        self.worstStallNs = lagNs
      }
      self.lock.unlock()
      guard lagNs > StallWatchdog.stallThresholdNs else { return }
      let offsetMs =
        Double(dispatchedAt.uptimeNanoseconds &- self.origin.uptimeNanoseconds) / 1_000_000
      print(
        "SWITCH_PERF switch=\(self.switchID) event=mainStall t_ms=\(String(format: "%.1f", offsetMs)) lag_ms=\(String(format: "%.1f", Double(lagNs) / 1_000_000))"
      )
    }
  }

  /// Cancels the pinger and returns the worst observed main-queue hop lag.
  func stopAndReportWorstStall() -> Double {
    lock.lock()
    defer { lock.unlock() }
    timer?.cancel()
    timer = nil
    return Double(worstStallNs) / 1_000_000
  }
}
