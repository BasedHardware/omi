import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// **The query bar, as the thing a person types into.**
///
/// Two defects met here and they were the same defect twice: the bar drew one variable while the
/// rest of the app read another, and the variable it drew could only ever show one line.
///
/// 1. The composer bound a `@State` on `QueryShellHome` while `ChatProvider.draftText` — what
///    persistence restores, what a send clears and what the automation bridge's `set_chat_drafts`
///    writes — went somewhere nothing rendered. `chat_drafts_snapshot` reported a draft stored and
///    the bar went on showing `Ask a follow-up…`, so every harness assertion made through the bridge
///    was an assertion about a dead variable.
/// 2. It was an `NSTextField`. A pasted three-line block was stored in full and drawn as its last
///    line, a long question scrolled its own beginning out of view, and Shift-⏎ did nothing.
///
/// These mount the real `QueryHeroBar` over the real `ChatComposerDraft` and read the `NSTextView`
/// the composer actually puts on screen, because the whole class of bug here is a view that agrees
/// with a test and disagrees with the window.
@MainActor
final class QueryComposerTests: XCTestCase {

  // MARK: - One variable behind one control

  /// The bridge's exact probe. `set_chat_drafts main=…` writes `ChatProvider.draftText`; this asserts
  /// the composer on screen is showing that string and not a placeholder.
  func testTheDraftTheBridgeWritesIsTheTextTheComposerDraws() throws {
    let composer = try Composer()
    defer { composer.tearDown() }

    composer.provider.draftText = "DRAFT-PROBE-VISIBLE-XYZ"

    XCTAssertEqual(
      composer.visibleText, "DRAFT-PROBE-VISIBLE-XYZ",
      "the bridge wrote a draft the composer does not render — two variables, one apparent control")
  }

  /// The other direction, so the two cannot be two stores that merely happen to agree once: what the
  /// reader types is what the provider — and therefore persistence and the bridge — holds.
  func testTypingInTheComposerWritesTheProvidersDraft() throws {
    let composer = try Composer()
    defer { composer.tearDown() }

    composer.type("half-written thought")

    XCTAssertEqual(composer.provider.draftText, "half-written thought")
    XCTAssertEqual(
      composer.provider.composerDraft.text, "half-written thought",
      "the composer must write through the one draft, not a copy of it")
  }

  /// Emptied by the send, the composer shows its placeholder again — the behaviour the earlier fix
  /// bought, asserted here through the variable the bar now actually draws.
  func testClearingTheProvidersDraftEmptiesTheComposer() throws {
    let composer = try Composer()
    defer { composer.tearDown() }
    composer.provider.draftText = "asked and gone"

    composer.provider.draftText = ""

    XCTAssertEqual(composer.visibleText, "")
  }

  // MARK: - More than one line

  /// The tester's paste. Three lines went in, one line came out.
  func testAPastedBlockKeepsEveryLineOnScreen() throws {
    let composer = try Composer()
    defer { composer.tearDown() }

    composer.type("line one\nline two\nline three")

    XCTAssertEqual(composer.visibleText, "line one\nline two\nline three")
    XCTAssertEqual(
      composer.renderedLineCount, 3,
      "the composer laid the pasted block out as fewer lines than it holds")
    XCTAssertGreaterThan(
      composer.composerHeight, QueryShellLayout.composerMinHeight,
      "a three-line draft left the composer at its one-line height")
    composer.assertTheGlassContainsTheText()
  }

  /// **The bar has to grow with the text, not just draw more of it.**
  ///
  /// The first attempt at this composer grew the editor without growing the bar: an
  /// `NSViewRepresentable` with no `sizeThatFits` has no height of its own, so three lines were drawn
  /// straight through a one-line bar and spilled outside the glass — clipped at the top and the
  /// bottom, worse than the single-line field it replaced. A test that only measured the *editor*
  /// passed anyway, which is why this one measures the bar around it.
  func testTheBarGrowsWithTheDraftInsteadOfSpillingOutOfIt() throws {
    let composer = try Composer()
    defer { composer.tearDown() }
    let resting = composer.barHeight

    composer.type("line one\nline two\nline three")

    XCTAssertGreaterThan(
      composer.barHeight, resting,
      "the composer grew and the bar did not, so the text is drawn outside the glass")
    composer.assertTheGlassContainsTheText()
  }

  /// Growth has to stop somewhere: the bar and the results panel share one column in an 800×680
  /// window, so a composer that grew without a ceiling would walk the panel off the bottom of it.
  func testTheComposerStopsGrowingAtItsCeiling() throws {
    let composer = try Composer()
    defer { composer.tearDown() }

    composer.type((1...40).map { "line \($0)" }.joined(separator: "\n"))

    XCTAssertLessThanOrEqual(composer.composerHeight, QueryShellLayout.composerMaxHeight)
    XCTAssertLessThanOrEqual(
      composer.barHeight,
      QueryShellLayout.composerMaxHeight + QueryShellLayout.barPaddingVertical * 2 + 1,
      "the bar grew past its own composer, so something else in the row is unbounded")
    composer.assertTheGlassContainsTheText()
  }

  /// **An empty bar is exactly as tall as it was.** The whole surface is laid out under this bar, so
  /// growing it would have been a regression if it had also moved the resting geometry.
  func testAnEmptyComposerLeavesTheBarAtItsRestingHeight() throws {
    let composer = try Composer()
    defer { composer.tearDown() }

    XCTAssertEqual(composer.barHeight, QueryShellLayout.barMinHeight, accuracy: 0.5)
  }

  /// **A squeezed bar still contains its text.**
  ///
  /// The surface can have less room than the composer wants — a short window, or a results panel
  /// that has already claimed its share. The composer then has to take what it is given and scroll
  /// inside it. Keeping its own height instead is the same spill as before, arriving from the other
  /// direction: seen live at the ceiling, where the bar was squeezed to four lines of glass with five
  /// lines of text drawn through it.
  func testALongDraftInAShortSurfaceScrollsInsteadOfSpilling() throws {
    let composer = try Composer(height: 260)
    defer { composer.tearDown() }

    composer.type((1...40).map { "line \($0)" }.joined(separator: "\n"))

    composer.assertTheGlassContainsTheText()
    XCTAssertGreaterThanOrEqual(
      composer.composerHeight, QueryShellLayout.composerMinHeight - 1,
      "squeezed below one line, the composer stops being a field at all")
  }

  /// The line height the growth arithmetic is built on, checked against the platform's own metrics
  /// for each face the composer is set in rather than left as a number somebody once measured by eye.
  func testTheComposersLineHeightsAreTheOnesTheseFacesActuallyLayOut() {
    let layoutManager = NSLayoutManager()

    XCTAssertEqual(
      QueryShellLayout.composerLineHeight,
      layoutManager.defaultLineHeight(for: .systemFont(ofSize: QueryShellLayout.queryFontSize)),
      "composerLineHeight has drifted from the line NSLayoutManager actually lays out — the ceiling "
        + "is a whole number of these, so an approximation shows as a half-drawn line at the glass edge")
    XCTAssertEqual(
      QueryShellLayout.panelComposerLineHeight,
      layoutManager.defaultLineHeight(
        for: .systemFont(ofSize: QueryShellLayout.panelComposerFontSize)),
      "the in-panel composer's line height has drifted from its own face")
  }

  // MARK: - The composer inside the panel

  /// **The chat composer is the same composer.** One `OmiTextEditor` over one `ChatProvider` draft,
  /// mounted in the panel instead of above it — so the bridge's `set_chat_drafts` still lands in the
  /// field the reader is looking at, which is the whole defect this file was opened for. A second
  /// composer written for chat mode is how that comes back.
  func testTheInPanelComposerDrawsTheSameOneDraft() throws {
    let composer = try Composer(mode: .answer)
    defer { composer.tearDown() }

    composer.provider.draftText = "DRAFT-IN-PANEL-XYZ"
    XCTAssertEqual(composer.visibleText, "DRAFT-IN-PANEL-XYZ")

    composer.type("typed under the transcript")
    XCTAssertEqual(composer.provider.draftText, "typed under the transcript")
  }

  /// **Bare `⏎` sends once a conversation is open.** On the list it commits the filter; in the panel
  /// there is no list left under it to filter, so the only thing Return has ever meant in a chat
  /// composer is what it means here. Driven through the editor's real `doCommandBy` seam rather than
  /// asserted about a value, because the key press is what the reader actually performs.
  func testBareReturnInTheInPanelComposerSends() throws {
    let composer = try Composer(mode: .answer)
    defer { composer.tearDown() }

    composer.type("what did priya decide")
    composer.pressReturn()

    XCTAssertEqual(
      composer.surface.asks, 1, "Return under the transcript did not send the follow-up")
    XCTAssertEqual(composer.surface.searches, 0, "Return in a conversation must not go back to filtering")
  }

  /// It is a chat composer, so it rests at a chat composer's height — not at the 64 pt hero bar's.
  /// A hero-sized block pinned under the transcript is the search bar in a different place, which is
  /// the arrangement this change exists to remove.
  func testTheInPanelComposerRestsAtItsOwnHeightRatherThanTheHeroBars() throws {
    let composer = try Composer(mode: .answer)
    defer { composer.tearDown() }

    XCTAssertEqual(
      composer.barHeight, QueryShellLayout.panelComposerMinHeight, accuracy: 1,
      "the in-panel composer is not resting at the height the panel reserves for it")
    XCTAssertLessThan(
      composer.barHeight, QueryShellLayout.barMinHeight,
      "the composer inside the panel is still as tall as the hero bar it replaced")
  }

  /// The same growth contract in the new place: it grows with the draft, stops at five lines, and
  /// never draws outside its own shell.
  func testTheInPanelComposerGrowsWithTheDraftAndStopsAtItsCeiling() throws {
    let composer = try Composer(mode: .answer)
    defer { composer.tearDown() }
    let resting = composer.barHeight

    composer.type((1...40).map { "line \($0)" }.joined(separator: "\n"))

    XCTAssertGreaterThan(composer.barHeight, resting)
    XCTAssertLessThanOrEqual(
      composer.composerHeight, QueryShellLayout.panelComposerMaxEditorHeight)
  }

  // MARK: - The caret

  /// **The caret goes where the surface says, and keeps going back.**
  ///
  /// `esc Results`, `‹ Results`, a sent question and re-activating the app all hand the caret to this
  /// bar. That used to be `@FocusState`, which cannot reach into an `NSViewRepresentable` at all —
  /// and, being a flag, could not re-claim a caret it already believed it held, which is the exact
  /// case the app-activation claim exists for. So the claim is a counter, and this is the test that
  /// it still lands.
  func testEachCaretClaimPutsTheCaretBackInTheComposer() throws {
    let composer = try Composer()
    defer { composer.tearDown() }

    composer.claimCaret()
    XCTAssertTrue(composer.hasCaret, "the first claim never reached the field")

    composer.resignCaret()
    XCTAssertFalse(composer.hasCaret)

    composer.claimCaret()
    XCTAssertTrue(
      composer.hasCaret,
      "a second claim was swallowed — the surface believes the bar is focused and it is not")
  }

  // MARK: - What ⏎ means

  /// Return sends, Shift-Return writes a newline, and neither happens while an input method still
  /// has uncommitted text. The coordinator reads the modifier from `NSApp.currentEvent`, which no
  /// hermetic test can stage — so the decision is a value and this is where it is held.
  func testShiftReturnWritesANewlineAndBareReturnSubmits() {
    XCTAssertEqual(
      OmiComposerReturnKey.resolve(hasMarkedText: false, shiftHeld: false), .submit)
    XCTAssertEqual(
      OmiComposerReturnKey.resolve(hasMarkedText: false, shiftHeld: true), .newline)
    XCTAssertEqual(
      OmiComposerReturnKey.resolve(hasMarkedText: true, shiftHeld: false), .newline,
      "Return mid-composition commits the IME candidate; it is never the composer's key")
  }

  /// `⏎` on the bar does what the bar's own hint says it does, in both modes, so the key and the
  /// label cannot drift apart.
  func testTheReturnKeyMeansWhateverTheBarsHintSays() {
    XCTAssertEqual(QueryShellSubmit.resolve(text: "priya", commandHeld: false), .search)
    XCTAssertEqual(QueryShellSubmit.resolve(text: "priya", commandHeld: true), .ask)
    XCTAssertEqual(QueryShellSubmit.resolve(text: "  ", commandHeld: true), .none)
  }

  // MARK: - Harness

  /// The real `QueryHeroBar` over the real `ChatComposerDraft`, in a window, with the `NSTextView`
  /// it puts on screen located rather than assumed.
  @MainActor
  private final class Composer {
    let provider: ChatProvider
    private let window: NSWindow
    private let host: NSHostingView<Host>
    private let textView: NSTextView

    let surface = Surface()

    init(width: CGFloat = 768, height: CGFloat = 400, mode: QueryShellMode = .results) throws {
      provider = ChatProvider()
      host = NSHostingView(rootView: Host(provider: provider, surface: surface, mode: mode))
      host.frame = NSRect(x: 0, y: 0, width: width, height: height)
      window = NSWindow(
        contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
      window.contentView = host
      host.layoutSubtreeIfNeeded()
      guard let found = Self.firstTextView(in: host) else {
        throw XCTSkip("SwiftUI built no NSTextView for the composer in this environment")
      }
      textView = found
      // A `ChatProvider` restores the persisted draft on init, so without this each test would start
      // holding whatever the last one typed — and would be asserting on the store rather than on the
      // composer.
      provider.draftText = ""
      host.layoutSubtreeIfNeeded()
    }

    func tearDown() {
      provider.draftText = ""
      ChatDraftStore.shared.clear(Self.mainDraftKey)
      ChatDraftStore.shared.flush()
      window.contentView = nil
    }

    private static let mainDraftKey = ChatDraftKey.mainChat(contextID: "omi:default")

    /// What a reader would see in the bar.
    var visibleText: String {
      settle()
      return textView.string
    }

    /// How many lines the composer actually laid out — the count the single-line field always got
    /// wrong, whatever it was storing.
    var renderedLineCount: Int {
      settle()
      guard let layoutManager = textView.layoutManager, let container = textView.textContainer else {
        return 0
      }
      layoutManager.ensureLayout(for: container)
      var lines = 0
      var index = 0
      let glyphs = layoutManager.numberOfGlyphs
      while index < glyphs {
        var lineRange = NSRange()
        layoutManager.lineFragmentRect(forGlyphAt: index, effectiveRange: &lineRange)
        index = NSMaxRange(lineRange)
        lines += 1
      }
      return lines
    }

    var composerHeight: CGFloat {
      settle()
      return textView.enclosingScrollView?.frame.height ?? 0
    }

    /// The bar's own laid-out height in a surface-shaped host, not its `fittingSize` — the failure
    /// this whole harness exists for was a bar that fitted in isolation and clipped in the window.
    var barHeight: CGFloat {
      settle()
      return host.rootView.probe.barHeight
    }

    /// **The reader's words are inside the panel.** The composer's scroll view must sit within the
    /// bar's own bounds, less the padding the bar reserves — anything else is text drawn over the
    /// glass edge.
    func assertTheGlassContainsTheText(
      file: StaticString = #filePath, line: UInt = #line
    ) {
      settle()
      let lane = barHeight - QueryShellLayout.barPaddingVertical * 2
      XCTAssertLessThanOrEqual(
        composerHeight, lane + 1,
        "the composer is \(composerHeight)pt inside a \(lane)pt lane — the text spills outside the bar",
        file: file, line: line)
    }

    /// What `QueryShellHome.claimCaret()` does on every mode change and app activation.
    func claimCaret() {
      surface.caretClaims += 1
      settle()
    }

    /// Whatever takes the keyboard away in between: another window, a menu, a sheet.
    func resignCaret() {
      window.makeFirstResponder(nil)
      settle()
    }

    var hasCaret: Bool {
      window.firstResponder === textView || textView.isDescendant(of: window.firstResponder as? NSView ?? NSView())
    }

    /// Put text in the way a paste does — through the text view, so the coordinator's
    /// `textDidChange` is what writes the draft, exactly as it is when a person types.
    func type(_ text: String) {
      let whole = NSRange(location: 0, length: (textView.string as NSString).length)
      textView.insertText(text, replacementRange: whole)
      settle()
    }

    /// Bare `⏎`, through the editor's own command seam — the exact call AppKit makes on the
    /// delegate, so the production `OmiComposerReturnKey` decision and the bar's `onSubmit` closure
    /// are both really exercised. With no shift held and no marked text this resolves to `.submit`.
    func pressReturn() {
      _ = textView.delegate?.textView?(
        textView, doCommandBy: #selector(NSResponder.insertNewline(_:)))
      settle()
    }

    /// SwiftUI applies a state change on the next layout pass, so ask for one rather than wait.
    private func settle() {
      host.layoutSubtreeIfNeeded()
      host.needsLayout = true
      host.layoutSubtreeIfNeeded()
    }

    private static func firstTextView(in view: NSView) -> NSTextView? {
      if let textView = view as? NSTextView { return textView }
      for subview in view.subviews {
        if let found = firstTextView(in: subview) { return found }
      }
      return nil
    }
  }

  /// The composer exactly as `QueryShellHome` mounts it: bound to the provider's one draft through
  /// `ChatDraftScope`, never to a `@State` of its own, and in the surface's own shape — a column
  /// with the composer in it and a body-sized block for company. The shape matters: a composer
  /// hosted on its own is asked for its ideal height and always looks right.
  ///
  /// `mode` picks the placement, because `QueryComposerPlacement.of` is the one thing that decides
  /// it — searching mounts the hero bar above the block, chatting mounts the chat composer under it,
  /// which is the arrangement each is laid out in on screen.
  private struct Host: View {
    @ObservedObject var provider: ChatProvider
    @ObservedObject var surface: Surface
    let mode: QueryShellMode
    let probe = HeightProbe()

    var body: some View {
      VStack(spacing: QueryShellLayout.panelGap) {
        if QueryComposerPlacement.of(mode) == .hero { composer }
        Color.clear.frame(height: QueryShellLayout.minimumBodyHeight)
        if QueryComposerPlacement.of(mode) == .panelFooter { composer }
        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private var composer: some View {
      ChatDraftScope(draft: provider.composerDraft) { draft in
        QueryHeroBar(
          text: draft,
          caretClaim: surface.caretClaims,
          isWorking: false,
          mode: mode,
          onSearch: { surface.searches += 1 },
          onAsk: { surface.asks += 1 }
        )
        .background {
          GeometryReader { bar in
            Color.clear.onChange(of: bar.size.height, initial: true) { _, height in
              probe.barHeight = height
            }
          }
        }
      }
    }
  }

  /// A reference box, so the harness can read a layout value out of a `View` value type.
  @MainActor
  private final class HeightProbe {
    var barHeight: CGFloat = 0
  }

  /// `QueryShellHome`'s half of the arrangement: the caret claim it owns and hands down, and the two
  /// submits it resolves — counted, so "what does `⏎` mean here" is answered by what was called.
  @MainActor
  private final class Surface: ObservableObject {
    @Published var caretClaims = 0
    var asks = 0
    var searches = 0
  }
}
