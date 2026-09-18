import Foundation

/// Debug-only work counters for the streaming transcript's render path.
///
/// A streamed answer re-renders its row on every buffer flush, and the cost
/// of one flush is not visible from any assertion a test can make on the
/// rendered result: the text is right whether the row parsed its Markdown
/// once or three times, and whether TextKit laid out the whole answer or only
/// the tail. These counters make that work observable, so
/// `ChatStreamingRenderBudgetTests` can pin *how much* one flush is allowed to
/// do rather than only what it must show.
///
/// Compiled out of release builds: every call site is `#if DEBUG`, so a
/// shipped bundle allocates nothing and does no extra work per flush.
#if DEBUG
  enum ChatStreamingRenderProbe {
    enum Counter: CaseIterable, Sendable {
      /// `ChatSelectableProse.attributedString` — the AppKit prose parse.
      case appKitProseBuild
      /// `OmiMarkdownContent.styledAttributedString` — the SwiftUI prose parse.
      case swiftUIProseBuild
      /// `OmiMarkdownDocument.init` — the block-level split.
      case documentParse
      /// `ChatSelectableProseText.height(of:fittingWidth:)` — a throwaway
      /// TextKit stack laying out the whole block.
      case throwawayHeightMeasure
      /// A height answered from the live text view's own layout.
      case liveHeightRead
      /// `NSTextStorage.setAttributedString` — the whole block replaced.
      case storageReplacement
      /// The block's storage edited from the first differing character on.
      case storageIncrementalEdit
      /// `ChatMessagesView.body` evaluated.
      case transcriptBodyEvaluation
      /// `ChatBubble.body` evaluated (any row).
      case bubbleBodyEvaluation
      /// `ChatSelectableProseText.sizeThatFits` asked (any row) — a layout
      /// pass over the transcript queries every mounted prose block.
      case proseSizeQuery
      /// One frame of the working mark's animation drawn.
      case markFrame
    }

    private static let lock = NSLock()
    // Guarded by `lock`; `nonisolated(unsafe)` records that contract for the
    // concurrency checker, which cannot see a lock's exclusion.
    private nonisolated(unsafe) static var counts: [Counter: Int] = [:]

    nonisolated static func hit(_ counter: Counter) {
      lock.lock()
      counts[counter, default: 0] += 1
      lock.unlock()
    }

    nonisolated static func snapshot() -> [Counter: Int] {
      lock.lock()
      defer { lock.unlock() }
      return counts
    }

    nonisolated static func reset() {
      lock.lock()
      counts.removeAll()
      lock.unlock()
    }
  }
#endif
