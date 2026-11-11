import Foundation

/// How the Brain Map grows over time.
///
/// Calendar time is a poor playback axis: years of silence between clusters
/// make replay pause on an almost-empty map. Missing `created_at` values also
/// decode as the Unix epoch, which used to pin the left of the scrubber at
/// 1969. Playback therefore compresses long quiet stretches, ignores epoch
/// placeholders, and still spends extra time inside dense imports so they do
/// not appear as one burst.
enum MemoryAtlasPlayback {
  /// Accounts with more than this many entities get a four-second replay.
  /// Smaller maps finish sooner so a handful of memories is not stretched.
  static let fewEntityCeiling = 12
  static let manyReplaySeconds: TimeInterval = 4
  static let fewReplaySeconds: TimeInterval = 2
  /// A calendar gap longer than this is treated as one short beat instead of
  /// occupying a proportional slice of the four-second replay.
  static let maxUncompressedGap: TimeInterval = 12 * 60 * 60
  /// Unix-epoch sentinels from missing timestamps. Anything earlier is not a
  /// real memory date and must not own the chronological axis.
  static let earliestCredibleDate = Date(timeIntervalSince1970: 1_000_000_000)
  /// Chronology after gap-compression. Density still gets the majority so a
  /// same-day import can bloom one entity at a time.
  static let chronologicalWeight = 0.18

  static func duration(entityCount: Int) -> TimeInterval {
    entityCount > fewEntityCeiling ? manyReplaySeconds : fewReplaySeconds
  }

  static func isCredible(_ date: Date) -> Bool {
    date >= earliestCredibleDate
  }

  /// Dates that may stretch the axis. Epoch placeholders collapse onto the
  /// first real timestamp so they still appear, just not in 1969. A graph with
  /// no credible dates keeps the placeholders instead of inventing today.
  static func effectiveDates(from dates: [Date]) -> [Date] {
    guard let first = dates.first else { return [] }
    let floor = dates.lazy.filter(isCredible).min() ?? first
    return dates.map { isCredible($0) ? $0 : floor }
  }

  /// Running compressed time for a sorted date list. Each inter-event gap is
  /// capped so a silent year cannot steal a third of the replay.
  static func compressedOffsets(for dates: [Date]) -> [TimeInterval] {
    guard let first = dates.first else { return [] }
    var offsets: [TimeInterval] = [0]
    offsets.reserveCapacity(dates.count)
    var elapsed: TimeInterval = 0
    var previous = first
    for date in dates.dropFirst() {
      elapsed += min(max(date.timeIntervalSince(previous), 0), maxUncompressedGap)
      offsets.append(elapsed)
      previous = date
    }
    return offsets
  }
}

/// The time axis behind the atlas. Built from entity `createdAt` timestamps so
/// the user can scrub — or watch — their memory come into being. Playback is
/// density-aware: a tight imported/backfilled cluster is expanded into a short,
/// deterministic sequence instead of appearing as one unreadable burst. Dates
/// shown to the user always remain the original dates from memory data.
struct MemoryAtlasTimeline: Equatable {
  struct Entry: Equatable {
    let nodeID: String
    let createdAt: Date
    let playbackFraction: Double
  }

  let start: Date
  let end: Date
  /// Entity-birth counts across the density-expanded playback axis, for the
  /// histogram. This describes animation pacing, not rewritten history.
  let buckets: [Int]
  let entries: [Entry]
  let playbackFractionByNodeID: [String: Double]

  var hasChronologicalRange: Bool { end > start }
  var span: TimeInterval { max(end.timeIntervalSince(start), 1) }

  func date(atFraction fraction: Double) -> Date {
    let clamped = min(max(fraction, 0), 1)
    guard let first = entries.first else {
      return start.addingTimeInterval(span * clamped)
    }
    guard clamped > first.playbackFraction else { return first.createdAt }
    // This deliberately steps to the last real creation date rather than
    // interpolating an invented timestamp between two memories.
    return entries[max(firstPlaybackIndex(after: clamped) - 1, 0)].createdAt
  }

  func fraction(for date: Date) -> Double {
    guard let first = entries.first, let last = entries.last else { return 1 }
    guard date > first.createdAt else { return first.playbackFraction }
    guard date < last.createdAt else { return last.playbackFraction }
    return entries[max(firstDateIndex(after: date) - 1, 0)].playbackFraction
  }

  func isVisible(nodeID: String, at fraction: Double) -> Bool {
    (playbackFractionByNodeID[nodeID] ?? 1) <= min(max(fraction, 0), 1)
  }

  func visibleNodeCount(at fraction: Double) -> Int {
    let clamped = min(max(fraction, 0), 1)
    return firstPlaybackIndex(after: clamped)
  }

  func spawnProgress(nodeID: String, at fraction: Double) -> Double {
    guard let bornAt = playbackFractionByNodeID[nodeID] else { return 0 }
    let age = fraction - bornAt
    let window = max(0.012, min(0.05, 5 / Double(max(entries.count, 1))))
    guard age >= 0, age < window else { return 0 }
    return 1 - age / window
  }

  /// Retained for the legacy Date-based preview path. Live replay uses
  /// `spawnProgress(nodeID:at:)` so dense imports bloom one-at-a-time.
  var spawnWindow: TimeInterval { span / 26 }

  private func firstPlaybackIndex(after fraction: Double) -> Int {
    var lower = 0
    var upper = entries.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if entries[middle].playbackFraction > fraction {
        upper = middle
      } else {
        lower = middle + 1
      }
    }
    return lower
  }

  private func firstDateIndex(after date: Date) -> Int {
    var lower = 0
    var upper = entries.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if entries[middle].createdAt > date {
        upper = middle
      } else {
        lower = middle + 1
      }
    }
    return lower
  }

  static func make(from nodes: [KnowledgeGraphNode], bucketCount: Int = 40) -> MemoryAtlasTimeline? {
    let orderedNodes = nodes.sorted {
      if $0.createdAt == $1.createdAt { return $0.id < $1.id }
      return $0.createdAt < $1.createdAt
    }
    guard orderedNodes.count > 1, let start = orderedNodes.first?.createdAt, let end = orderedNodes.last?.createdAt
    else {
      return nil
    }

    let effectiveDates = MemoryAtlasPlayback.effectiveDates(from: orderedNodes.map(\.createdAt))
    let axisStart = effectiveDates.min() ?? start
    let axisEnd = effectiveDates.max() ?? end
    let hasChronologicalRange = axisEnd > axisStart
    let compressedOffsets = MemoryAtlasPlayback.compressedOffsets(for: effectiveDates)
    let compressedSpan = max(compressedOffsets.last ?? 0, 1)
    // Chronology remains a minority signal for naturally distributed
    // memories, while rank gives dense imports enough playback room to be
    // comprehensible. Both inputs are monotonic, so this cannot reorder data
    // or fabricate a date.
    let chronologicalWeight = hasChronologicalRange ? MemoryAtlasPlayback.chronologicalWeight : 0
    let densityWeight = 1 - chronologicalWeight
    let denominator = Double(max(orderedNodes.count - 1, 1))
    let entries = orderedNodes.enumerated().map { index, node in
      let chronologicalFraction =
        hasChronologicalRange
        ? compressedOffsets[index] / compressedSpan
        : 0
      let densityFraction = Double(index) / denominator
      return Entry(
        nodeID: node.id,
        createdAt: effectiveDates[index],
        playbackFraction: chronologicalWeight * chronologicalFraction + densityWeight * densityFraction
      )
    }

    var buckets = Array(repeating: 0, count: max(bucketCount, 1))
    for entry in entries {
      let index = min(
        buckets.count - 1,
        max(0, Int(entry.playbackFraction * Double(buckets.count)))
      )
      buckets[index] += 1
    }
    return MemoryAtlasTimeline(
      start: axisStart,
      end: axisEnd,
      buckets: buckets,
      entries: entries,
      playbackFractionByNodeID: Dictionary(lastWriteWins: entries.map { ($0.nodeID, $0.playbackFraction) })
    )
  }
}
