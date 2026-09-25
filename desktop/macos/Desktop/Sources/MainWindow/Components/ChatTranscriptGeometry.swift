import AppKit
import Combine
import CoreGraphics
import SwiftUI

/// The two coordinate spaces the transcript measures itself in.
///
/// They live outside the view because `ChatMessagesView` is generic over its
/// welcome content, and a generic type cannot hold a static — and because the
/// geometry closures that read them are `Sendable`, which rules out reaching
/// back into a main-actor view for a string.
enum ChatTranscriptSpace {
  /// Travels with the content, so a row's offset in it describes where the row
  /// sits in the document and does not change when the reader scrolls.
  static let content = "chatTranscriptContent"
  /// The scroll view itself, where the content's origin is the scroll offset.
  static let viewport = "chatTranscriptViewport"
}

/// One geometry read of the transcript's content: how tall it is, and how far
/// it has travelled up past the top of the scroll view. Taken together so a
/// scroll reports once rather than twice.
struct ChatTranscriptContentFrame: Equatable {
  let height: CGFloat
  let scrollTop: CGFloat
}

/// The transcript's measured geometry, held off the view's own state.
///
/// Scroll position changes tens of times a second. Kept in `@State` on
/// `ChatMessagesView` it would re-evaluate the whole transcript body on every
/// one of those frames, which is the cost that view's comments already go out of
/// their way to avoid. Here only the timeline overlay observes it, and only the
/// two derived values it actually draws — the marks and which one is active —
/// are published, each behind a did-it-really-change guard.
@MainActor
final class ChatTranscriptGeometry: ObservableObject {
  /// Row placement is measured during every SwiftUI layout pass. Ignore small
  /// jitter so an unrelated animated subview cannot republish the whole rail.
  private static let heightEpsilon: CGFloat = 4
  private static let rowOffsetEpsilon: CGFloat = 4
  private static let gutterEpsilon: CGFloat = 1

  @Published private(set) var marks: [ChatPromptMark] = []
  @Published private(set) var activeMarkID: String?
  /// Width available outside the readable column, on one side.
  @Published private(set) var gutter: CGFloat = 0

  /// The rail is an overlay on the trailing edge, not a reserved column. It
  /// appears once there are enough prompts to navigate; the native scroller
  /// stays `.never` so the two never sit side by side.
  var showsPromptTimeline: Bool {
    marks.count >= ChatPromptTimelineModel.minimumMarks
  }

  /// The NSScrollView the detector last resolved. Used to restore clip origin
  /// after older rows are prepended.
  weak var scrollView: NSScrollView?

  private var sources: [ChatPromptSource] = []
  private var offsets: [String: CGFloat] = [:]
  private var documentHeight: CGFloat = 0
  private var scrollTop: CGFloat = 0
  private var viewport: CGSize = .zero
  /// Starts true because an opened transcript immediately restores to its live
  /// edge. Only physical reader input hands active-mark authority back to the
  /// reading line.
  private var isFollowingLiveEdge = true
  /// A prompt the reader picked outright, which outranks what the reading line
  /// happens to be over.
  private var pinnedMarkID: String?

  /// The prompt/reply text. Rebuilt only when the transcript itself changes:
  /// it walks every message and normalises their text, which is far too much
  /// work to repeat while a document is merely growing a few points at a time.
  func setMessages(_ messages: [ChatMessage]) {
    let rebuilt = ChatPromptTimelineModel.sources(messages: messages)
    guard rebuilt != sources else { return }
    sources = rebuilt
    rebuildMarks()
  }

  func setRowOffset(_ offset: CGFloat, for id: String) {
    if let existing = offsets[id], abs(existing - offset) < Self.rowOffsetEpsilon { return }
    offsets[id] = offset
    rebuildMarks()
  }

  func setContent(height: CGFloat, scrollTop: CGFloat) {
    let heightChanged = abs(documentHeight - height) >= Self.heightEpsilon
    if heightChanged { documentHeight = height }
    self.scrollTop = scrollTop
    if heightChanged {
      rebuildMarks()
    } else {
      refreshActiveMark()
    }
  }

  func prependSnapshot() -> ChatTranscriptPrependPreservation.Snapshot? {
    guard documentHeight > 0 else { return nil }
    return .init(documentHeight: documentHeight, scrollTop: scrollTop)
  }

  func setViewport(_ size: CGSize, columnWidth: CGFloat?) {
    let column = min(columnWidth ?? size.width, size.width)
    let measured = max(0, (size.width - column) / 2)
    if abs(viewport.height - size.height) >= Self.heightEpsilon {
      viewport.height = size.height
      refreshActiveMark()
    }
    viewport.width = size.width
    if abs(gutter - measured) >= Self.gutterEpsilon { gutter = measured }
  }

  /// Follows the scroll controller's explicit intent rather than waiting for a
  /// layout pass to prove the bottom position. That prevents the final prompt
  /// from briefly lighting the penultimate mark after initial restore or a new
  /// message. Entering live-follow also drops a rail pin: Jump to latest is an
  /// outright choice of the newest turn, even if the follow flag was already true.
  func setFollowingLiveEdge(_ isFollowing: Bool) {
    let pinCleared = isFollowing && pinnedMarkID != nil
    if isFollowing {
      pinnedMarkID = nil
    }
    guard isFollowingLiveEdge != isFollowing || pinCleared else { return }
    isFollowingLiveEdge = isFollowing
    refreshActiveMark()
  }

  /// The reader picked a prompt, from the rail or from ⌘↑ / ⌘↓.
  ///
  /// Tracking alone gets this wrong, and correctly so: the jump puts the prompt
  /// at the top of the viewport, and if its answer is short the *next* prompt is
  /// already sitting on the reading line — so the mark that lights is the one
  /// below the one that was clicked. An outright choice is not a guess to be
  /// overruled by geometry, so it holds until the reader scrolls away from it.
  func selectMark(_ id: String) {
    isFollowingLiveEdge = false
    pinnedMarkID = id
    if activeMarkID != id { activeMarkID = id }
  }

  /// Physical scrolling hands authority back to the reading line. Called from
  /// the transcript's user-scroll detector, which is the only thing that can
  /// tell a reader's gesture from the jump the selection itself performed.
  func releaseSelection() {
    guard pinnedMarkID != nil else { return }
    pinnedMarkID = nil
    refreshActiveMark()
  }

  /// A conversation switch must not leave the previous transcript's rows on the
  /// rail: the ids are gone, so their marks would never be measured again.
  func reset() {
    offsets.removeAll()
    documentHeight = 0
    scrollTop = 0
    isFollowingLiveEdge = true
    sources = []
    pinnedMarkID = nil
    if !marks.isEmpty { marks = [] }
    if activeMarkID != nil { activeMarkID = nil }
  }

  private func rebuildMarks() {
    let rebuilt = ChatPromptTimelineModel.marks(
      sources: sources, offsets: offsets, documentHeight: documentHeight)
    if rebuilt != marks { marks = rebuilt }
    refreshActiveMark()
  }

  private func refreshActiveMark() {
    // A pin that outlived its prompt (history pruned, conversation switched) is
    // stale, not authoritative.
    if let pinnedMarkID {
      if marks.contains(where: { $0.id == pinnedMarkID }) {
        if activeMarkID != pinnedMarkID { activeMarkID = pinnedMarkID }
        return
      }
      self.pinnedMarkID = nil
    }
    guard documentHeight > 0, !marks.isEmpty else {
      if activeMarkID != nil { activeMarkID = nil }
      return
    }
    if isFollowingLiveEdge {
      let newest = marks.last?.id
      if activeMarkID != newest { activeMarkID = newest }
      return
    }
    let resolved = ChatPromptTimelineModel.activeMarkID(
      marks: marks,
      viewportTopFraction: scrollTop / documentHeight,
      viewportHeightFraction: viewport.height / documentHeight,
      isAtBottom: ChatScrollLiveEdge.isAtBottom(
        visibleMaxY: scrollTop + viewport.height,
        documentHeight: documentHeight)
    )
    if resolved != activeMarkID { activeMarkID = resolved }
  }
}
