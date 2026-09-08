import AppKit
import SwiftUI

/// A contiguous stretch of one app on the timeline.
///
/// The unit the track draws, and deliberately not "one screenshot". A day of capture is thousands of
/// rows and a few dozen stretches; drawing a rectangle per row is what made the old strip a barcode
/// with no legible app identity in it, and it is also what made every redraw a thousand-fill loop.
struct RewindActivityBlock: Equatable {
  let app: String
  let startedAt: Double
  let endedAt: Double

  var duration: Double { max(0, endedAt - startedAt) }
}

/// Pure navigation policy shared by the AppKit track and the SwiftUI page.
enum RewindTimelineNavigation {
  static func clampedIndex(_ index: Int, screenshots: [Screenshot]) -> Int? {
    guard !screenshots.isEmpty else { return nil }
    return max(0, min(index, screenshots.count - 1))
  }

  /// Player index when the loaded array changes but the viewed frame still exists at `found`.
  /// Parked on the newest frame while new captures append (frame kept its position and the array
  /// only grew) follows to the new newest; any other change (scrubbed-back position,
  /// sampled-window replacement) preserves the user's position. A result different from `found`
  /// means the player moved and the caller must load that frame.
  static func sameFrameIndex(old: Int, new: Int, current: Int, found: Int) -> Int {
    if current == old - 1, found == current, new > old { return new - 1 }
    return found
  }

  /// The capture nearest an absolute moment in an ascending viewport sample.
  static func nearestIndex(to instant: Double, screenshots: [Screenshot]) -> Int? {
    guard !screenshots.isEmpty else { return nil }
    var lower = 0
    var upper = screenshots.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if screenshots[middle].timestamp.timeIntervalSince1970 <= instant {
        lower = middle + 1
      } else {
        upper = middle
      }
    }
    if lower == 0 { return 0 }
    if lower == screenshots.count { return screenshots.count - 1 }
    let earlier = screenshots[lower - 1].timestamp.timeIntervalSince1970
    let later = screenshots[lower].timestamp.timeIntervalSince1970
    return instant - earlier <= later - instant ? lower - 1 : lower
  }
}

/// The time window the track is showing, and how it is derived from the loaded capture history.
///
/// Split out of the view because it is the whole of the track's arithmetic and none of its drawing:
/// a pure function of timestamps that a hermetic test can drive without a window server.
enum RewindTrackWindow {

  /// The narrowest window a zoom may reach — a minute across the bar is already finer than the
  /// capture interval, so anything below it zooms into empty space.
  static let minimumSpan: Double = 60

  /// Exact retained-history bounds, padded enough that the end captures are not flush against the
  /// track. This range stays global while viewport samples come and go beneath it.
  static func historyRange(oldest: Date?, newest: Date?) -> ClosedRange<Double>? {
    guard let oldest, let newest else { return nil }
    let lower = oldest.timeIntervalSince1970 - 30
    let upper = max(newest.timeIntervalSince1970 + 30, lower + minimumSpan)
    return lower...upper
  }

  /// Contiguous same-app stretches, in capture order.
  ///
  /// Blocks tile: each one ends where the next begins, so the bar has no seams the data did not put
  /// there. The last block is given the run's median sampling interval so a day still in progress
  /// does not end in a zero-width segment.
  static func blocks(from instants: [Double], apps: [String]) -> [RewindActivityBlock] {
    guard instants.count == apps.count, !instants.isEmpty else { return [] }
    let tail = medianInterval(of: instants)
    var result: [RewindActivityBlock] = []
    var startIndex = 0
    for index in 1...instants.count {
      let ended = index == instants.count
      if ended || apps[index] != apps[startIndex] {
        let endedAt = ended ? instants[instants.count - 1] + tail : instants[index]
        result.append(
          RewindActivityBlock(
            app: apps[startIndex], startedAt: instants[startIndex], endedAt: endedAt))
        startIndex = index
      }
    }
    return result
  }

  /// The full extent of the loaded capture history, padded by one sampling interval at each end so the first and
  /// last segments are not flush against the bar's rounded corners.
  static func fullRange(of instants: [Double]) -> ClosedRange<Double> {
    guard let first = instants.first, let last = instants.last else {
      let now = Date().timeIntervalSince1970
      return now...(now + 3600)
    }
    let pad = max(medianInterval(of: instants), 30)
    let lower = first - pad
    let upper = max(last + pad, lower + minimumSpan)
    return lower...upper
  }

  /// Clamps a proposed window so it can neither be narrower than a minute nor leave retained history.
  ///
  /// One clamp for the buttons and the pinch both, so a gesture cannot leave the track in a state a
  /// button could not reach.
  static func clamp(start: Double, span: Double, within range: ClosedRange<Double>) -> (start: Double, span: Double) {
    let full = max(range.upperBound - range.lowerBound, minimumSpan)
    let clampedSpan = min(max(span, minimumSpan), full)
    let maximumStart = range.upperBound - clampedSpan
    let clampedStart = min(max(start, range.lowerBound), max(maximumStart, range.lowerBound))
    return (clampedStart, clampedSpan)
  }

  /// The median gap between consecutive captures — the run's own sampling interval, measured rather
  /// than assumed, because Rewind's capture rate is a user setting.
  static func medianInterval(of instants: [Double]) -> Double {
    guard instants.count > 1 else { return 60 }
    var gaps: [Double] = []
    gaps.reserveCapacity(instants.count - 1)
    for index in 1..<instants.count {
      let gap = instants[index] - instants[index - 1]
      if gap > 0 { gaps.append(gap) }
    }
    guard !gaps.isEmpty else { return 60 }
    gaps.sort()
    return gaps[gaps.count / 2]
  }

  static func extending(_ range: ClosedRange<Double>?, toInclude date: Date) -> ClosedRange<Double> {
    let instant = date.timeIntervalSince1970
    guard let range else { return instant...(instant + 30) }
    return range.lowerBound...max(range.upperBound, instant + 30)
  }

  static func shouldRefreshLiveFrames(
    visibleRange: ClosedRange<Double>?, newestLoadedTimestamp: Double?, now: Date,
    isPlayerParkedOnNewestFrame: Bool = false
  ) -> Bool {
    // The player sitting on the newest loaded frame is the live edge regardless of where the
    // track viewport is panned — the viewer wants the next capture, so keep refreshing.
    if isPlayerParkedOnNewestFrame { return true }
    guard let visibleRange else { return false }
    if visibleRange.contains(now.timeIntervalSince1970) { return true }
    // A viewport parked at the live edge always trails the clock (its end is the newest loaded
    // frame). Keep refreshing there; only a viewport panned back into older history stops.
    guard let newestLoadedTimestamp else { return false }
    return visibleRange.upperBound >= newestLoadedTimestamp
  }
}

enum RewindTimelinePresentation {
  static func showsTimeline(screenshotCount: Int, historyRange: ClosedRange<Double>?) -> Bool {
    screenshotCount > 0 || historyRange != nil
  }
}
