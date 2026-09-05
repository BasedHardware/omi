import AppKit

/// A bounded, session-wide memo for chat prose text and its measured height.
///
/// Chat is torn down and mounted again on every route change
/// (`ChatFirstShell` keys the destination by route), and every mount rebuilds
/// the transcript window: one Foundation Markdown parse plus one
/// `NSAttributedString` build per prose block in
/// `ChatSelectableProse.attributedString`, and one throwaway TextKit stack per
/// `sizeThatFits` query — twelve per block across the mount layout passes,
/// every one at the width the first measured.
///
/// Measured by instrumenting both calls on the mounted transcript
/// (`ChatTranscriptGestureHarnessTests.Harness`, 120-message journal, compact
/// 50-row window, debug build): before the cache, every mount — including
/// every return to Chat — paid 50 parses and 600 height measures, 58–70 ms of
/// TextKit layout and parsing combined. With the cache, the cold mount pays
/// it once (50 and 50) and every remount pays none of it.
///
/// The cache is keyed on the exact render inputs, so a hit is identical to a
/// recompute. Entries are immutable `NSAttributedString`s shared read-only
/// with `NSTextStorage`, which copies on edit — these text views are
/// non-editable. Bounded LRU: a streaming row mints a new key per flush, so
/// the cache turns over during an answer and the cap keeps the worst case
/// small.
@MainActor
enum ChatProseRenderCache {
  struct Key: Hashable {
    let markdown: String
    let style: OmiMarkdown.Style
    let fontSize: Int
    /// Thousandths, so a fractional `fontScale` keys exactly.
    let fontScaleMilli: Int
    /// Sorted ordinals named by the block, or empty.
    let citationOrdinals: [Int]
  }

  final class Entry {
    let attributed: NSAttributedString
    var heightsByWidth: [CGFloat: CGFloat] = [:]

    init(attributed: NSAttributedString) {
      self.attributed = attributed
    }
  }

  private static var entries: [Key: Entry] = [:]
  private static var lruOrder: [Key] = []
  /// A full transcript window plus headroom for the streaming row's turnover.
  private static let maximumEntries = 192
  /// A window resize proposes a new width per block per frame of the drag.
  /// Old widths are dead once the window settles at its new size, so the map
  /// is dropped wholesale at the bound rather than curated.
  private static let maximumMeasuredWidthsPerEntry = 8

  /// The entry for `key`, running `produce` on a miss. Nil when the block
  /// cannot be represented as AppKit prose (a table, a fenced block) — those
  /// keep their SwiftUI renderers and are never cached.
  static func entry(for key: Key, produce: () -> NSAttributedString?) -> Entry? {
    if let hit = entries[key] {
      touch(key)
      return hit
    }
    guard let attributed = produce() else { return nil }
    let entry = Entry(attributed: attributed)
    entries[key] = entry
    lruOrder.append(key)
    evictIfNeeded()
    return entry
  }

  /// Memoized TextKit height for the width the transcript proposed. The width
  /// keys exactly: a sub-point change is a different wrap.
  static func height(for entry: Entry, width: CGFloat, measure: () -> CGFloat) -> CGFloat {
    if let cached = entry.heightsByWidth[width] { return cached }
    if entry.heightsByWidth.count >= maximumMeasuredWidthsPerEntry {
      entry.heightsByWidth.removeAll()
    }
    let measured = measure()
    entry.heightsByWidth[width] = measured
    return measured
  }

  /// The cache is session-wide by design, which is exactly why a suite that
  /// asserts on its population needs a way to start from empty.
  static func removeAll() {
    entries.removeAll()
    lruOrder.removeAll()
  }

  /// Population, for tests that pin the eviction bound.
  static var entryCount: Int { entries.count }

  private static func touch(_ key: Key) {
    lruOrder.removeAll { $0 == key }
    lruOrder.append(key)
  }

  private static func evictIfNeeded() {
    while lruOrder.count > maximumEntries {
      entries[lruOrder.removeFirst()] = nil
    }
  }
}
