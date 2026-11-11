import Foundation

/// Calculates the smallest sort-order write set for a desired category order.
///
/// Sort orders are sparse integers inside a category band. Unchanged rows act as
/// anchors; moved rows are allocated into the gaps between those anchors. A
/// caller can fall back to the existing category reindexing scheme when the
/// persisted ranks are not usable or the requested gap is exhausted. Local-only
/// action-item rows participate in the same SQLite ordering; staged rows do not
/// have an action_items sort-order column and remain outside this planner.
enum TaskSortOrderPlanner {
  enum Result: Equatable {
    case incremental([String: Int])
    case needsRebalance
  }

  static func plan(
    orderedIDs: [String],
    existingRanks: [String: Int],
    affectedIDs: Set<String>,
    categoryIndex: Int,
    bandWidth: Int
  ) -> Result {
    let ids = orderedIDs.filter { !$0.hasPrefix("staged_") }
    guard !ids.isEmpty else { return .incremental([:]) }
    guard Set(ids).count == ids.count else { return .needsRebalance }

    let base = categoryIndex * bandWidth
    let upperBound = base + bandWidth
    guard ids.allSatisfy({ existingRanks[$0] != nil }) else { return .needsRebalance }

    let ranks = ids.compactMap { existingRanks[$0] }
    guard ranks.allSatisfy({ $0 > base && $0 < upperBound }), Set(ranks).count == ranks.count else {
      return .needsRebalance
    }

    let affected = affectedIDs.intersection(ids)
    guard !affected.isEmpty else { return .incremental([:]) }

    // Unchanged rows must remain valid anchors in the desired order. This also
    // detects a multi-drag that would otherwise invert two untouched rows.
    let anchors = ids.filter { !affected.contains($0) }
    let anchorRanks = anchors.compactMap { existingRanks[$0] }
    guard anchorRanks == anchorRanks.sorted(), Set(anchorRanks).count == anchorRanks.count else {
      return .needsRebalance
    }

    var updates: [String: Int] = [:]
    var runStart = 0
    while runStart < ids.count {
      guard affected.contains(ids[runStart]) else {
        runStart += 1
        continue
      }

      var runEnd = runStart
      while runEnd + 1 < ids.count, affected.contains(ids[runEnd + 1]) {
        runEnd += 1
      }

      let lower: Int
      if runStart > 0 {
        guard let previousRank = existingRanks[ids[runStart - 1]] else { return .needsRebalance }
        lower = previousRank
      } else {
        lower = base
      }
      let upper: Int
      if runEnd + 1 < ids.count {
        guard let nextRank = existingRanks[ids[runEnd + 1]] else { return .needsRebalance }
        upper = nextRank
      } else {
        upper = upperBound
      }
      let runIDs = Array(ids[runStart...runEnd])
      let currentRunRanks = runIDs.compactMap { existingRanks[$0] }

      // A no-op reorder should not churn a rank just because the evenly spaced
      // midpoint differs from the row's already-valid rank.
      if currentRunRanks.allSatisfy({ $0 > lower && $0 < upper }),
        currentRunRanks == currentRunRanks.sorted(),
        Set(currentRunRanks).count == currentRunRanks.count
      {
        runStart = runEnd + 1
        continue
      }

      let available = upper - lower
      guard available > runIDs.count else { return .needsRebalance }
      for (offset, id) in runIDs.enumerated() {
        let rank = lower + (available * (offset + 1)) / (runIDs.count + 1)
        guard rank > lower, rank < upper else { return .needsRebalance }
        updates[id] = rank
      }

      runStart = runEnd + 1
    }

    return .incremental(updates)
  }
}
