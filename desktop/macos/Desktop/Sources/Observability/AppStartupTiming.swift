import Darwin
import Foundation

/// Wall-clock start of this process, read from the kernel process table.
///
/// `App Startup Timing` reported `time_to_interactive_ms` values of 11–131ms,
/// which is not a cold start of a SwiftUI app — it was the duration of
/// `ViewModelContainer.loadAllData()`, which begins long after `main()`. The
/// only honest source for "when did this process actually start" is
/// `kinfo_proc.kp_proc.p_starttime`, which the kernel stamps at exec, before
/// dyld, before `main`, and before any code of ours could take a timestamp.
enum AppStartupTiming {
  /// Wall-clock start of `pid` as recorded by the kernel, or nil when the
  /// sysctl is unavailable.
  static func processStartDate(pid: pid_t = getpid()) -> Date? {
    var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, pid]
    var info = kinfo_proc()
    var size = MemoryLayout<kinfo_proc>.stride
    let result = sysctl(&mib, UInt32(mib.count), &info, &size, nil, 0)
    guard result == 0, size > 0 else { return nil }
    let started = info.kp_proc.p_starttime
    guard started.tv_sec > 0 else { return nil }
    return Date(
      timeIntervalSince1970: Double(started.tv_sec) + Double(started.tv_usec) / 1_000_000)
  }

  /// Milliseconds between two instants, floored at zero.
  ///
  /// The process-start stamp and `Date()` both come from the wall clock, so a
  /// clock adjustment between them can produce a negative or absurd interval.
  /// A startup metric must never report a negative duration.
  static func elapsedMilliseconds(from start: Date, to end: Date) -> Double {
    max(0, end.timeIntervalSince(start) * 1_000)
  }

  /// Milliseconds from process start to `now`, or nil when the process start is
  /// unavailable. Callers omit the property rather than substituting a
  /// plausible-looking number.
  static func millisecondsSinceProcessStart(
    now: Date = Date(),
    processStart: Date? = AppStartupTiming.processStartDate()
  ) -> Double? {
    guard let processStart else { return nil }
    return elapsedMilliseconds(from: processStart, to: now)
  }
}
