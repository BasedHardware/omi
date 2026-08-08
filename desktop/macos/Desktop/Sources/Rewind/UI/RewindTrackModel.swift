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

/// The time window the track is showing, and how it is derived from a day of capture.
///
/// Split out of the view because it is the whole of the track's arithmetic and none of its drawing:
/// a pure function of timestamps that a hermetic test can drive without a window server.
enum RewindTrackWindow {

  /// The narrowest window a zoom may reach — a minute across the bar is already finer than the
  /// capture interval, so anything below it zooms into empty space.
  static let minimumSpan: Double = 60

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

  /// The full extent of a day's capture, padded by one sampling interval at each end so the first and
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

  /// Clamps a proposed window so it can neither be narrower than a minute nor wander off the day.
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
}
