import Foundation
import SwiftUI

/// Find-in-transcript: which segments contain the query, where, and which match is current.
///
/// A value type so the matching and the "N of M" stepping are testable without a view. Matching is
/// case- and diacritic-insensitive ("cafe" finds "Café"), non-overlapping, and in transcript order
/// across every speaker. A blank query matches nothing.
struct TranscriptSearchModel: Equatable {
  struct Match: Equatable {
    let segmentID: String
    let range: Range<String.Index>
  }

  static let compareOptions: String.CompareOptions = [.caseInsensitive, .diacriticInsensitive]

  private(set) var query = ""
  private(set) var matches: [Match] = []
  private(set) var currentIndex: Int?
  /// Bumped whenever the current match should be scrolled into view, including a step that wraps
  /// onto the same match (a single hit), which leaves `currentIndex` unchanged.
  private(set) var revealRequest = 0
  private var rangesBySegment: [String: [Range<String.Index>]] = [:]

  var isActive: Bool { !Self.normalized(query).isEmpty }

  var currentMatch: Match? { currentIndex.map { matches[$0] } }

  /// "3 of 12", "No matches", or empty while there is no query.
  var countLabel: String {
    guard isActive else { return "" }
    guard let currentIndex else { return "No matches" }
    return "\(currentIndex + 1) of \(matches.count)"
  }

  /// Re-runs the search. A changed query starts at the first match; the same query over refreshed
  /// segments keeps the current match when it still exists.
  mutating func update(query newQuery: String, segments: [(id: String, text: String)]) {
    let previous = newQuery == query ? currentMatch : nil
    query = newQuery
    matches = []
    rangesBySegment = [:]
    let needle = Self.normalized(newQuery)
    if !needle.isEmpty {
      for segment in segments {
        let ranges = Self.ranges(of: needle, in: segment.text)
        guard !ranges.isEmpty else { continue }
        rangesBySegment[segment.id, default: []].append(contentsOf: ranges)
        matches.append(contentsOf: ranges.map { Match(segmentID: segment.id, range: $0) })
      }
    }
    if matches.isEmpty {
      currentIndex = nil
    } else {
      currentIndex = previous.flatMap { matches.firstIndex(of: $0) } ?? 0
    }
    revealRequest += 1
  }

  /// Steps to the next match, wrapping from the last to the first.
  mutating func next() { step(by: 1) }

  /// Steps to the previous match, wrapping from the first to the last.
  mutating func previous() { step(by: -1) }

  private mutating func step(by delta: Int) {
    guard let currentIndex, !matches.isEmpty else { return }
    let count = matches.count
    self.currentIndex = ((currentIndex + delta) % count + count) % count
    revealRequest += 1
  }

  /// Every match inside one segment, in reading order. Empty (and free) while there is no query.
  func ranges(inSegment id: String) -> [Range<String.Index>] {
    rangesBySegment[id] ?? []
  }

  /// The current match, when it falls inside this segment.
  func currentRange(inSegment id: String) -> Range<String.Index>? {
    guard let currentMatch, currentMatch.segmentID == id else { return nil }
    return currentMatch.range
  }

  static func normalized(_ query: String) -> String {
    query.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Non-overlapping occurrences of `needle` in `text`, honoring `compareOptions`.
  static func ranges(of needle: String, in text: String) -> [Range<String.Index>] {
    guard !needle.isEmpty else { return [] }
    var found: [Range<String.Index>] = []
    var searchStart = text.startIndex
    while searchStart < text.endIndex,
      let range = text.range(of: needle, options: compareOptions, range: searchStart..<text.endIndex)
    {
      found.append(range)
      searchStart = range.upperBound > range.lowerBound ? range.upperBound : text.index(after: range.lowerBound)
    }
    return found
  }

  /// `text` with each match painted behind, the current one stronger. Built only for bubbles that
  /// contain a match, so an idle transcript renders plain `Text` with no attributed-string work.
  static func highlighted(
    _ text: String,
    ranges: [Range<String.Index>],
    current: Range<String.Index>?,
    matchColor: Color,
    currentColor: Color
  ) -> AttributedString {
    var attributed = AttributedString(text)
    for range in ranges {
      guard let attributedRange = Range(range, in: attributed) else { continue }
      attributed[attributedRange].backgroundColor = range == current ? currentColor : matchColor
    }
    return attributed
  }
}
