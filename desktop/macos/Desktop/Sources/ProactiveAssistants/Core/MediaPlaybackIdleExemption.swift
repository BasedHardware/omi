import Foundation
import IOKit.pwr_mgt

/// Watching a movie is not being away from the machine.
///
/// The capture loop's idle gate reads HID idle time, and a person watching video
/// produces no HID input — so after 60 quiet seconds every capture tick was skipped
/// and the proactive assistants went blind exactly when the user asked "why no nudges
/// while I watch TikTok for an hour?" (measured live: 14 idle-skip cycles in one
/// movie hour, near-zero analyses at Maximum frequency).
///
/// The system already knows the difference: video players and browsers hold a
/// power-management assertion that prevents display sleep while media plays
/// (`PreventUserIdleDisplaySleep`, or the legacy `NoDisplaySleepAssertion`). While any
/// other process holds one, the display would stay lit for a human who is presumed to
/// be watching — the same presumption the idle gate should make.
enum MediaPlaybackIdlePolicy {
  /// The idle value the capture gate should act on. Media playback pins it to zero —
  /// the viewer is present — and otherwise the HID value passes through untouched.
  static func effectiveIdleSeconds(
    hidIdleSeconds: TimeInterval,
    isDisplaySleepPrevented: Bool
  ) -> TimeInterval {
    isDisplaySleepPrevented ? 0 : hidIdleSeconds
  }
}

/// Polls the power-management assertion table, cached so the capture loop's fast tick
/// does not shell into IOKit every second.
final class MediaPlaybackDetector {
  private let probe: () -> Bool
  private let cacheTTL: TimeInterval
  private var cachedValue = false
  private var cachedAt: Date = .distantPast

  init(
    cacheTTL: TimeInterval = 10,
    probe: @escaping () -> Bool = MediaPlaybackDetector.displaySleepPreventedByAnotherProcess
  ) {
    self.cacheTTL = cacheTTL
    self.probe = probe
  }

  func isDisplaySleepPrevented(now: Date = Date()) -> Bool {
    if now.timeIntervalSince(cachedAt) < cacheTTL {
      return cachedValue
    }
    cachedValue = probe()
    cachedAt = now
    return cachedValue
  }

  private var didLogExemption = false

  /// The idle value the capture gate should act on, with the once-per-episode
  /// observability log folded in so the gate call site stays a single line.
  func effectiveIdleSeconds(
    hidIdleSeconds: TimeInterval,
    threshold: TimeInterval,
    now: Date = Date()
  ) -> TimeInterval {
    let effective = MediaPlaybackIdlePolicy.effectiveIdleSeconds(
      hidIdleSeconds: hidIdleSeconds,
      isDisplaySleepPrevented: isDisplaySleepPrevented(now: now))
    if hidIdleSeconds >= threshold, effective < threshold, !didLogExemption {
      didLogExemption = true
      log("CaptureGate: HID-idle but media playback active — capture continues")
    } else if hidIdleSeconds < threshold {
      didLogExemption = false
    }
    return effective
  }

  /// Whether any process other than this one holds a display-sleep-prevention
  /// assertion. Our own capture/recording stack can hold assertions of its own, and
  /// those must not count as "the user is watching something".
  static func displaySleepPreventedByAnotherProcess() -> Bool {
    var assertionsRef: Unmanaged<CFDictionary>?
    guard IOPMCopyAssertionsByProcess(&assertionsRef) == kIOReturnSuccess,
      let byProcess = assertionsRef?.takeRetainedValue() as? [Int: [[String: Any]]]
    else { return false }

    let ownPID = Int(ProcessInfo.processInfo.processIdentifier)
    for (pid, assertions) in byProcess where pid != ownPID {
      for assertion in assertions {
        guard
          let type = assertion["AssertionTrueType"] as? String
            ?? assertion[kIOPMAssertionTypeKey as String] as? String
        else { continue }
        if type == "PreventUserIdleDisplaySleep" || type == "NoDisplaySleepAssertion" {
          return true
        }
      }
    }
    return false
  }
}
