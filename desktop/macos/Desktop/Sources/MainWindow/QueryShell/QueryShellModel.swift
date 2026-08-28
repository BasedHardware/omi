//
//  QueryShellModel.swift — every decision the query shell makes, as values rather than statements
//  inside a `body`.
//
//  While it is searching the shell is **two glass objects with air between them**: a bar you type into
//  and a panel you look at. They are different in kind, so they are drawn as two panels of the same
//  width with a real gap, each wearing the app's one glass and its own ambient shadow. Welding them
//  into one tall slab with a rule across the middle is the single change that would make this read as
//  a form rather than as a search surface, so `panelGap` lives here where a test can hold it.
//
//  With a conversation open it is **one** object: the composer comes down inside the panel and the gap
//  it was on the other side of stops existing. `QueryComposerPlacement` is that decision, and
//  `panelBodyHeight` is what spends the room it frees.
//
//  The gap, the lane, the count sentence and the type filter are all arithmetic or copy — none of them
//  need a window to be true. A view is then left with nothing of its own to get wrong.
//
//  Brand: nothing here picks a colour (INV-UI-1).
//

import Foundation
import OmiTheme
import SwiftUI

// MARK: - What the panel is showing

/// The type filter the chips select. `all` is not "no filter" — it is the merged view, which is the
/// point of the surface: one spine where a conversation, the memory it produced and the screen you
/// were on sit together.
enum QueryShellKind: String, CaseIterable, Identifiable, Sendable {
  case all
  case conversations
  case memories
  case tasks
  case rewind

  var id: String { rawValue }

  var title: String {
    switch self {
    case .all: return "All"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .tasks: return "Tasks"
    case .rewind: return "Rewind"
    }
  }
}

/// How far back the panel is looking. The `Filter ›` control's one job.
///
/// A time window rather than a second list of types: the chips already answer "what kind of thing",
/// and the question they cannot answer — the only one a capture log is routinely asked — is "when".
enum QueryShellRange: String, CaseIterable, Identifiable, Sendable {
  case today
  case week
  case month
  case all

  var id: String { rawValue }

  var title: String {
    switch self {
    case .today: return "Today"
    case .week: return "Last 7 days"
    case .month: return "Last 30 days"
    case .all: return "All time"
    }
  }

  /// The earliest instant this range admits, or `nil` for all of it.
  func earliest(now: Date = Date(), calendar: Calendar = .current) -> Date? {
    switch self {
    case .today: return calendar.startOfDay(for: now)
    case .week: return calendar.date(byAdding: .day, value: -7, to: now)
    case .month: return calendar.date(byAdding: .day, value: -30, to: now)
    case .all: return nil
    }
  }

  func admits(_ date: Date, now: Date = Date(), calendar: Calendar = .current) -> Bool {
    guard let earliest = earliest(now: now, calendar: calendar) else { return true }
    return date >= earliest
  }
}

/// What the query bar is asking for. **This is the seam.** The panel body is handed one of these and
/// nothing else: it never reads the text field, and the bar never reaches into the body's list.
struct QueryShellRequest: Equatable, Sendable {
  var text: String = ""
  var kind: QueryShellKind = .all
  var range: QueryShellRange = .all

  /// The trimmed, case-folded term a body should actually match on. Doing it here means every body
  /// matches the same way and no call site invents a second normalisation.
  var term: String {
    text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  }

  var isFiltering: Bool { !term.isEmpty || kind != .all || range != .all }

  /// Whether a candidate of `kind` created at `date` survives this request's non-textual filters.
  /// The text match belongs to the body, which knows what fields a row actually has.
  func admits(kind candidate: QueryShellKind, at date: Date, now: Date = Date()) -> Bool {
    (kind == .all || kind == candidate) && range.admits(date, now: now)
  }
}

/// **The half of a request the shell owns.**
///
/// The other half — the text — belongs to `ChatProvider.composerDraft`, which is what the composer
/// renders, what persistence restores and what the automation bridge writes. It is deliberately absent
/// here: this surface stored its own copy of the query text once, and the copy the bridge wrote and
/// the copy the bar drew were different variables behind one apparent control. A request is therefore
/// *assembled* from the draft plus these, never stored whole.
struct QueryShellFilters: Equatable, Sendable {
  var kind: QueryShellKind = .all
  var range: QueryShellRange = .all
}

extension QueryShellRequest {
  init(text: String, filters: QueryShellFilters) {
    self.init(text: text, kind: filters.kind, range: filters.range)
  }

  var filters: QueryShellFilters {
    QueryShellFilters(kind: kind, range: range)
  }
}

/// Which body the panel is hosting. **Asking is a mode of the same query, not a destination** — the
/// window does not navigate, the panel keeps its frame and its corner, and only what is inside it
/// swaps. What *does* move is the composer: see `QueryComposerPlacement`.
enum QueryShellMode: Equatable, Sendable {
  case results
  case answer

  /// What Home is when it first appears: the conversation. Opening the app is opening a chat with
  /// Omi; the spine/search surface stays one `esc` (or `‹ Results`) away rather than being the
  /// landing page.
  static let homeDefault: QueryShellMode = .answer
}

/// The `home_*` bridge actions, as the search-text transition each one promises.
///
/// Home's mode is derived from the search text, so a bridge action that promises the conversation
/// (`home_open_chat`, `home_ask`, `home_close_panel`) must clear the search — otherwise it reports
/// success while its effect stays hidden behind the results panel the user was filtering. One pure
/// function, so the handlers and the tests cannot disagree about which actions collapse the search.
enum HomeBridgeIntent: CaseIterable, Sendable {
  case openChat
  case ask
  case closePanel
  case attach

  /// The search text after this intent runs. Everything that lands the user in the conversation
  /// clears it; staging an attachment narrows nothing and keeps the search where it was.
  func searchTextAfter(_ current: String) -> String {
    switch self {
    case .openChat, .ask, .closePanel: return ""
    case .attach: return current
    }
  }
}

/// **Where the one composer is standing.**
///
/// While you are searching, a field above the panel is the right arrangement: you type at the top
/// and the rows underneath redraw, so the control sits above the thing it filters. Once you have
/// asked something that arrangement is wrong in an ordinary way — every chat anyone has ever used
/// puts its input *under* the transcript, because what you write next is a reply to what is already
/// there. A search bar floating over a conversation is a control for a job you already finished.
///
/// So the composer stands in two places rather than existing twice. There is still one
/// `OmiTextEditor`, one `ChatProvider` draft, one caret claim and one send (INV-6); this value is
/// the entire difference between the two, and it is here so the arithmetic below can reserve room
/// for the composer wherever it actually is.
enum QueryComposerPlacement: Equatable, Sendable {
  /// Above the panel, wearing the surface's second glass. The search bar.
  case hero
  /// Inside the panel, pinned under the transcript. Ordinary chat.
  case panelFooter

  /// Which placement a mode puts the composer in. One function, so the layout arithmetic and the
  /// view cannot end up disagreeing about where the composer is.
  static func of(_ mode: QueryShellMode) -> Self {
    switch mode {
    case .results: return .hero
    case .answer: return .panelFooter
    }
  }
}

/// What a key press resolves to. **There is only one thing a key does on this surface now.**
///
/// This used to be a choice between two, and the choice was the mistake. The surface offered `⏎
/// Search` and `⌘⏎ Ask` as two buttons and two keys, so the reader had to decide which of two modes
/// they were in before they could press anything — and one of the two was not a decision at all:
/// **typing already filters the list in place**, live, as each character lands. A key that commits
/// to a filter the panel has already applied is a button for a job that finished while you were
/// reaching for it.
///
/// So searching stopped being a control. `⏎` sends, in both placements, and nothing has to be
/// chosen. `⌘⏎` still sends — it is the `keyboardShortcut` on the same button, kept for the muscle
/// memory it built — but it is no longer advertised, because it is now the harder of two identical
/// routes.
enum QueryShellSubmit: Equatable, Sendable {
  /// Swap the panel body for the answer thread and send the words as a chat turn.
  case ask
  /// Nothing to do — an empty field.
  case none

  /// No `commandHeld`. Which key was pressed stopped being information the moment both keys meant
  /// the same thing; a parameter nothing branches on is the next thing to grow a branch back.
  static func resolve(text: String) -> QueryShellSubmit {
    text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? .none : .ask
  }
}

/// **One submit, resolved once — including what the field is left holding.**
///
/// The text is a *message*, and a composer that keeps the message it just sent is a composer you
/// have to empty by hand before you can write the next one: the `Ask a follow-up…` placeholder was
/// unreachable, a second `⏎` re-sent the question verbatim, and emptying the field to type a
/// follow-up used to throw the whole conversation away because an empty field was read as "take me
/// back to the list".
///
/// So the field is emptied by the *send*, and nothing else reads emptiness as an instruction. `esc`
/// and `‹ Results` in the panel header are the two ways out of a conversation.
///
/// **While you are on the list the same string is also a filter** — but it filters as you type, so
/// no key has to say so. The one thing `⏎` can mean is therefore the same thing in both placements,
/// which is why there is no longer a `commandHeld` to disambiguate.
struct QueryShellSubmission: Equatable, Sendable {
  let action: QueryShellSubmit
  /// The trimmed question to send. Non-nil only for `.ask`.
  let question: String?
  /// What the field holds afterwards.
  let text: String
  /// What the panel shows next, or nil to leave the panel exactly as it is — an
  /// inert key must never move the reader.
  let mode: QueryShellMode?

  static func resolve(text: String) -> Self {
    switch QueryShellSubmit.resolve(text: text) {
    case .none:
      return Self(action: .none, question: nil, text: text, mode: nil)
    case .ask:
      return Self(
        action: .ask,
        question: text.trimmingCharacters(in: .whitespacesAndNewlines),
        text: "",
        mode: .answer)
    }
  }
}

// MARK: - Send accounting

/// **The submit/retry ledger for the query shell's single send path.** The view
/// delegates every send decision here so the exactly-once question accounting
/// the rating prompt depends on is executable in tests, not view-private glue:
/// a resolved submit counts as one asked question and remembers itself for
/// `Try again`; a retry re-sends that SAME question and never counts again.
struct QueryShellSendLedger: Equatable, Sendable {
  struct Plan: Equatable, Sendable {
    let question: String
    /// Whether this emission advances the rating-prompt question counter.
    let countsAsQuestion: Bool
  }

  private(set) var lastAskedQuestion = ""

  /// A resolved submission — the one place a NEW question enters the send path.
  /// A busy provider yields no plan at all: Return during an active send would
  /// be rejected by ChatProvider anyway, so it must neither dispatch nor count
  /// (nor overwrite the question 'Try again' would re-send). Planning mutates
  /// nothing — only `recordAccepted` commits state, so a send ChatProvider
  /// rejects asynchronously leaves the ledger exactly as it was.
  func planSubmit(_ question: String?, providerBusy: Bool = false) -> Plan? {
    guard !providerBusy, let question, !question.isEmpty else { return nil }
    return Plan(question: question, countsAsQuestion: true)
  }

  /// Called from ChatProvider's `onAccepted` — the send is really in flight,
  /// so NOW the question becomes what 'Try again' re-sends.
  mutating func recordAccepted(_ plan: Plan) {
    if plan.countsAsQuestion {
      lastAskedQuestion = plan.question
    }
  }

  /// `Try again` on a failed turn: the same logical question, so it keeps the
  /// analytics event but never re-counts toward the rating prompt.
  func planRetry() -> Plan? {
    guard !lastAskedQuestion.isEmpty else { return nil }
    return Plan(question: lastAskedQuestion, countsAsQuestion: false)
  }
}

// MARK: - Where Home's controls send you

/// **Every way out of Home, as a value.** Home shows rows it does not own: a conversation, a memory,
/// a screen, and now the graph over all of them. Each of those has an established page that owns
/// editing, search, folders, starring and the rest, and INV-NAV-1 is the rule that Home routes to
/// that page instead of growing a smaller copy of it here.
///
/// It is a value because the rule is otherwise four separate two-line functions in a `body`, and
/// "does this control still land on the real page" is then a claim nothing checks. `Brain Map ›` in
/// the panel header is the fourth of these and the newest, so it is the one most likely to drift into
/// rendering an atlas inside Home's panel — which would be the reduced copy the invariant forbids.
enum QueryShellRoute: Equatable, CaseIterable, Sendable {
  /// A conversation row, and the `Conversations` chip's underlying list.
  case conversation
  /// The answer thread's citations into what Omi kept.
  case memories
  /// The panel header's `Brain Map ›` **and** the spine's end-of-day card. One destination, so one
  /// case: two controls that landed in different places would be two maps.
  case brainMap
  /// A screen row.
  case rewind

  /// The established page that owns this destination. Never a shell-local surface (INV-NAV-1).
  var navItem: SidebarNavItem {
    switch self {
    case .conversation, .memories, .brainMap, .rewind: return .conversations
    }
  }

  /// Which Brain view to select on arrival.
  var memoryDestination: MemoryHubDestination? {
    switch self {
    case .conversation: return .conversations
    case .memories: return .memories
    case .brainMap: return .brainMap
    case .rewind: return .rewind
    }
  }
}

// MARK: - Copy

/// The one sentence in the panel's top-right corner.
///
/// It has two jobs and they are not the same sentence: at rest it says how much Omi is holding, and
/// under a filter it says how much of that survived the filter. Collapsing them into one string is how
/// a search surface ends up claiming "0 moments captured" the moment you type a letter.
///
/// **Every one of them names its scope, because there is a second counter on this page.** Home shows
/// two numbers about 200 pt apart: the hour rail on the left counts *one day* of screen capture, and
/// this corner counts the *whole account*. The reader looked at a large `0` beside `798 so far ·
/// still counting` and asked what each one was supposed to be — as written, neither said.
///
/// This is the second attempt at that. The first gave the two counters different **nouns** (screen
/// moments vs moments), which shipped and did not work: a different noun does not tell you that one
/// covers a day and the other covers everything. The missing words were never nouns — they were
/// "today" and "everything", so the scope is now stated outright in every branch. The rail says its
/// own half.
enum QueryShellCount {
  /// **The scope this corner counts, in the app's own words.** Deliberately a phrase and not a
  /// system word like "all" or "total": "in all" is what the line used to end in, and it reads as a
  /// rhetorical flourish rather than as a claim about *which* moments were counted.
  ///
  /// It is one constant rather than three literals so the three branches cannot end up describing
  /// three different corpora — which is the drift that produced the contradiction in the first place.
  static let scope = "everything Omi has kept"

  /// - Parameter isSettled: whether `total` is a finished count. While the account is still paging
  ///   in, the number climbs under the reader — so it says that instead of presenting a moving
  ///   figure as a settled one.
  static func sentence(matching: Int, total: Int, isFiltering: Bool, isSettled: Bool) -> String {
    guard isFiltering else {
      guard isSettled else {
        return "\(number(total)) so far · still counting \(scope)"
      }
      return "\(number(total)) moment\(total == 1 ? "" : "s") in \(scope)"
    }
    return "\(number(matching)) result\(matching == 1 ? "" : "s") · of \(number(total)) in \(scope)"
  }

  /// Grouped digits, because the count is routinely five figures and an ungrouped one is unreadable
  /// at a glance — which is the only way this line is ever read.
  static func number(_ value: Int) -> String {
    value.formatted(.number.grouping(.automatic))
  }
}

// MARK: - Layout

/// Every number the surface is laid out from.
enum QueryShellLayout {
  /// **The gap.** Two panels 12 pt apart read as two objects; the same two at 0 read as one slab with
  /// a rule through it.
  ///
  /// Taken from `RewindSearchLayout`, which introduced this surface's vocabulary, rather than restated
  /// as a second 12. One product cannot have two opinions about how far apart its glass sits — that is
  /// exactly the drift that turns a design system back into a pile of literals.
  static var panelGap: CGFloat { RewindSearchLayout.panelGap }

  /// The corner is the shared one — never a second opinion about 22.
  static var panelCornerRadius: CGFloat { InkGlass.cornerRadius }

  /// The readable lane both panels occupy — **the top bar's own lane, not a second one.**
  ///
  /// The bar and the panel under it have to share a leading edge with the navigation above them or
  /// the surface reads as three objects that missed each other. Delegating rather than restating the
  /// number is what keeps that true after someone retunes the lane.
  static func laneWidth(for availableWidth: CGFloat) -> CGFloat {
    TopNavigationLayoutMetrics.contentLaneWidth(for: availableWidth)
  }

  // The hero bar.

  /// Search is a persistent utility, not a hero. Keep it large enough to scan
  /// and focus while returning the vertical space to the page it filters.
  static let barMinHeight: CGFloat = 48
  static let barPaddingHorizontal: CGFloat = 14
  static let barPaddingVertical: CGFloat = 6
  /// The animated mark at the leading edge.
  static let markDiameter: CGFloat = 22
  /// The push-to-talk disc. Larger than the compact in-panel controls because it is the bar's only round target.
  static let micDiameter: CGFloat = 32

  /// Between the hero row's controls. It is set at the query face, so it can afford more air than
  /// the chat row inside the panel, which uses `OmiSpacing.sm`.
  static let heroRowSpacing: CGFloat = 10

  /// The glyph the hero's two quiet controls share — the paperclip and the mic, which are the same
  /// kind of thing and must not be two sizes.
  static var heroGlyphSize: CGFloat { OmiType.subheading }

  /// The primary's glyph is heavier than the quiet ones in both rows, because it is the filled one:
  /// roughly half its disc, which is the proportion that reads as a button rather than as an icon
  /// with a circle behind it.
  static var heroPrimaryGlyphSize: CGFloat { OmiType.heading }

  /// The query's point size. Visibly larger than every other run on the surface, and deliberately
  /// under `Font.inkDisplayThreshold` (22) so it resolves to the reading face rather than the display
  /// one — a search field is type you read, not a headline.
  static let queryFontSize: CGFloat = 17

  // The composer inside the bar.
  //
  // **The bar is a composer, so it has to be able to show more than one line.** As a single-line
  // `TextField` it stored everything you pasted and showed you the last line of it, and a long
  // question scrolled the start of your own sentence out of view — you could not read back what you
  // were about to ask. Growing it is the fix, and the two numbers a growing field needs are how tall
  // one line is and where it stops.

  /// One laid-out line of the query face — `NSLayoutManager.defaultLineHeight` for
  /// `NSFont.systemFont(ofSize: 17)`, measured rather than estimated. `QueryComposerTests` checks it
  /// against the platform every run, because the ceiling below is a whole number of these and an
  /// approximate line height shows as a sixth line half-drawn at the bottom edge of the glass.
  static let composerLineHeight: CGFloat = 20

  /// The text container's breathing room, top and bottom.
  static let composerInsetVertical: CGFloat = 6

  /// **The resting height is the height it always was.** One line plus its insets is 37, which the
  /// 32 pt push-to-talk disc beside it already sets — so an empty bar is exactly as tall as before
  /// (`barMinHeight`) and nothing on the surface moves until there is a second line to show.
  static var composerMinHeight: CGFloat { composerLineHeight + composerInsetVertical * 2 }

  /// **Where growth stops.** Past this the composer scrolls instead of pushing the results panel
  /// down: the bar and the panel share one column in an 800×680 window (`DesktopWindowLayoutPolicy`),
  /// and a composer that grows without a ceiling walks the panel off the bottom of it.
  static let composerMaxLines: CGFloat = 5

  static var composerMaxHeight: CGFloat {
    composerLineHeight * composerMaxLines + composerInsetVertical * 2
  }

  // The composer once it moves inside the panel (`QueryComposerPlacement.panelFooter`).
  //
  // Same editor, same draft, same send — a different *face* and a different ground, because down
  // there it is no longer a hero.

  /// **The chat face, not the query face.** In the panel the composer sits a few points under the
  /// transcript it is replying to, and it is typed in the size that transcript is read in
  /// (`ChatInputView`'s 14) rather than in the 21 pt a hero search field is set at. A query face
  /// under a conversation reads as a second headline stacked on the end of it.
  static let panelComposerFontSize: CGFloat = 14

  /// One laid-out line of that face. Same contract as `composerLineHeight` and checked the same way
  /// by `QueryComposerTests`: the ceiling is a whole number of these, so an approximation shows as a
  /// half-drawn sixth line at the composer's own edge.
  static let panelComposerLineHeight: CGFloat = 17

  /// **One size for every control in the in-panel row.** The row shipped with three: a 28 pt
  /// paperclip frame, a 28 pt text pill and a 38 pt mic disc, each drawn in a different visual
  /// language. Three loud controls at three sizes is not a cluster, it is a queue — and the loudest
  /// of them was the least important. One diameter, and only one of them filled.
  static let panelComposerControlDiameter: CGFloat = 28

  /// The one glyph size the quiet controls share, so the paperclip and the mic read as the same
  /// kind of thing rather than as two unrelated icons that happened to land beside each other.
  static var panelComposerGlyphSize: CGFloat { OmiType.subheading }

  /// **The text's breathing room, chosen so one line is exactly a control tall.**
  ///
  /// `(28 − 17) / 2`. It is derived rather than picked because when one laid-out line of the chat
  /// face is the same height as the disc beside it, the row's baseline and the glyphs' centres
  /// coincide — at rest and at the ceiling, whichever way the row aligns. A round number here buys a
  /// permanent point or two of vertical drift between the reader's own words and the button that
  /// sends them.
  static var panelComposerInsetVertical: CGFloat {
    (panelComposerControlDiameter - panelComposerLineHeight) / 2
  }

  /// **The interior margin, equal on all four sides.** The composer's height comes from this rather
  /// than from a declared row height, which is what keeps the padding symmetric: the placeholder
  /// starts this far in from the fill's leading edge, the send disc ends this far from its trailing
  /// one, and there is the same air above and below.
  static let panelComposerShellInset: CGFloat = 7

  static var panelComposerMinEditorHeight: CGFloat {
    panelComposerLineHeight + panelComposerInsetVertical * 2
  }

  static var panelComposerMaxEditorHeight: CGFloat {
    panelComposerLineHeight * composerMaxLines + panelComposerInsetVertical * 2
  }

  /// **The pill's own resting height** — one control row plus its margin, and nothing declared.
  static var panelComposerShellHeight: CGFloat {
    max(panelComposerMinEditorHeight, panelComposerControlDiameter) + panelComposerShellInset * 2
  }

  /// **A true capsule at rest: the corner is half the pill's own height.**
  ///
  /// Not a shared card radius. `ChatComposerLayout.shellRadius` is 18 against a 52 pt pill, which is
  /// a rounded rectangle with visibly straight sides — a boxy input, which is exactly what the
  /// reader said it looked like. At half the height the two ends are semicircles, and the send disc
  /// (`panelComposerControlDiameter` inside `panelComposerShellInset`) ends up concentric with the
  /// cap it sits in, which is the whole reason the trailing cluster reads as settled.
  ///
  /// It stops tracking the height past one line on purpose: a pill that stayed a capsule as it grew
  /// would turn into an oval around a five-line draft. Every chat composer that grows keeps its
  /// resting corner instead.
  static var panelComposerCornerRadius: CGFloat { panelComposerShellHeight / 2 }

  /// **The air between the pill and the panel holding it**, so the composer reads as an object
  /// *inside* the panel rather than as the panel's own bottom edge. On top of the panel's padding
  /// this leaves 20 pt at the sides and 14 pt underneath.
  static let panelComposerEdgeInset: CGFloat = OmiSpacing.xs
  static let panelComposerBottomInset: CGFloat = OmiSpacing.xxs

  /// **The resting height of the whole in-panel composer container** — the pill plus the air under
  /// it. This is the number the panel reserves, so it has to cover everything the composer occupies;
  /// the pill's own height is `panelComposerShellHeight`.
  static var panelComposerMinHeight: CGFloat {
    panelComposerShellHeight + panelComposerBottomInset
  }

  /// The resting height of whichever container is holding the composer. The floor under the
  /// measured value, so a reserve computed before the first measurement lands is still honest.
  static func composerContainerMinHeight(placement: QueryComposerPlacement) -> CGFloat {
    switch placement {
    case .hero: return barMinHeight
    case .panelFooter: return panelComposerMinHeight
    }
  }

  // The results panel.

  static let panelPaddingHorizontal: CGFloat = 16
  static let panelPaddingTop: CGFloat = 10
  static let panelPaddingBottom: CGFloat = 10
  /// Between the `Filter ›` row and the chips under it.
  static let panelHeaderSpacing: CGFloat = 6
  static let chipSpacing: CGFloat = 6
  static let chipHeight: CGFloat = 28

  /// The floor under the panel body, so an empty result set is still a panel and not a sliver.
  static let minimumBodyHeight: CGFloat = 120

  /// The ceiling over it. Home is two objects with air between them, and a panel that keeps growing
  /// with the window stops being the second one and becomes the surface.
  static let maximumBodyHeight: CGFloat = 470

  /// The air above the hero bar, between it and the navigation.
  static let surfaceTopInset: CGFloat = OmiSpacing.sm

  /// **The panel's own chrome, above and below whatever it is showing.**
  ///
  /// The header row is a chip plus its 2 pt of lift (`QueryPanelChipLabel`); the type chips exist only
  /// on the list, because in answer mode there is nothing to narrow by type; and in answer mode the
  /// composer is *inside* the panel, under the transcript, which is the row the chips paid for.
  ///
  /// The composer's own height is passed in rather than assumed, for the same reason the hero bar's
  /// was: it grows with the draft and with a staged file, and a reserve that ignores that is a
  /// reserve that walks the panel off the bottom edge the first time somebody writes two lines.
  static func panelChromeHeight(mode: QueryShellMode, composerHeight: CGFloat) -> CGFloat {
    let headerRow = chipHeight + 2
    let typeChips = mode == .results ? chipHeight + panelHeaderSpacing : 0
    let composerRow =
      QueryComposerPlacement.of(mode) == .panelFooter
      ? panelHeaderSpacing + max(panelComposerMinHeight, composerHeight)
      : 0
    return panelPaddingTop + headerRow + panelHeaderSpacing + typeChips + composerRow
      + panelPaddingBottom
  }

  /// **How tall the panel body may be, so the panel ends inside the window instead of past it.**
  ///
  /// The body used to be pinned: the spine took a flat 470 and the answer thread a flat 460, numbers
  /// chosen against a window nobody re-measured. At the shell's own default size the page has 600 pt
  /// for a surface asking for 654, so the panel ran off the bottom edge and AppKit cut the last row
  /// through the middle of its text — no fade, no bottom padding, no way to scroll to it, because the
  /// part that was missing was outside the scroll view rather than below it.
  ///
  /// So the height is derived rather than declared: whatever the window has, less what is above the
  /// body and the panel's own chrome, held between the floor and the ceiling. The composer is
  /// measured rather than assumed — it grows when files are staged onto it and when the draft runs
  /// past one line, and reserving its minimum would put the overflow straight back the first time
  /// somebody attached something.
  ///
  /// **Which side of the panel that reserve falls on is the mode's decision.** In results mode the
  /// composer is the hero bar above, so it costs the body its height *and* the gap under it. In
  /// answer mode it is inside the panel, so it costs the body its height and nothing above the panel
  /// at all — which is why the transcript ends up with slightly more room than the list, not less.
  static func panelBodyHeight(
    availableHeight: CGFloat,
    composerHeight: CGFloat,
    mode: QueryShellMode
  ) -> CGFloat {
    let placement = QueryComposerPlacement.of(mode)
    let composer = max(composerContainerMinHeight(placement: placement), composerHeight)
    let above = surfaceTopInset + (placement == .hero ? composer + panelGap : 0)
    let room = availableHeight - above - panelChromeHeight(mode: mode, composerHeight: composer)
    return min(maximumBodyHeight, max(minimumBodyHeight, room))
  }
}
