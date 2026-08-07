//
//  QueryShellModel.swift — every decision the query shell makes, as values rather than statements
//  inside a `body`.
//
//  The shell is **two glass objects with air between them**: a bar you type into and a panel you look
//  at. They are different in kind, so they are drawn as two panels of the same width with a real gap,
//  each wearing the app's one glass and its own ambient shadow. Welding them into one tall slab with a
//  rule across the middle is the single change that would make this read as a form rather than as a
//  search surface, so `panelGap` lives here where a test can hold it.
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
  case rewind

  var id: String { rawValue }

  var title: String {
    switch self {
    case .all: return "All"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
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

/// Which body the panel is hosting. **Asking is a mode of the same query, not a destination** — the
/// query bar keeps its text, the panel keeps its frame, and only what is inside it swaps.
enum QueryShellMode: Equatable, Sendable {
  case results
  case answer
}

/// What the two keyboard hints resolve to for a given key press. A pure function so "⌘⏎ asks and ⏎
/// searches" is a test rather than a guess about SwiftUI's modifier reporting.
enum QueryShellSubmit: Equatable, Sendable {
  /// Filter the panel body in place.
  case search
  /// Swap the panel body for the answer thread and send the query as a chat turn.
  case ask
  /// Nothing to do — an empty field.
  case none

  static func resolve(text: String, commandHeld: Bool) -> QueryShellSubmit {
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return .none }
    return commandHeld ? .ask : .search
  }
}

/// **One submit, resolved once — including what the field is left holding.**
///
/// The bar does two jobs with one string, and every way this surface felt broken
/// came from confusing them. In `.results` the text is a *filter* over the list
/// under it, so submitting keeps it. In `.answer` the text is a *message*, and a
/// composer that keeps the message it just sent is a composer you have to empty
/// by hand before you can write the next one: the `Ask a follow-up…` placeholder
/// was unreachable, a second `⏎` re-sent the question verbatim, and emptying the
/// field to type a follow-up used to throw the whole conversation away because
/// an empty field was read as "take me back to the list".
///
/// So the field is emptied by the *send*, and nothing else reads emptiness as an
/// instruction. The two labelled exits (`esc Results` on the bar, `‹ Results` in
/// the panel header) are the only ways out of a conversation.
struct QueryShellSubmission: Equatable, Sendable {
  let action: QueryShellSubmit
  /// The trimmed question to send. Non-nil only for `.ask`.
  let question: String?
  /// What the field holds afterwards.
  let text: String
  /// What the panel shows next, or nil to leave the panel exactly as it is — an
  /// inert key must never move the reader.
  let mode: QueryShellMode?

  static func resolve(text: String, commandHeld: Bool) -> Self {
    switch QueryShellSubmit.resolve(text: text, commandHeld: commandHeld) {
    case .none:
      return Self(action: .none, question: nil, text: text, mode: nil)
    case .search:
      return Self(action: .search, question: nil, text: text, mode: .results)
    case .ask:
      return Self(
        action: .ask,
        question: text.trimmingCharacters(in: .whitespacesAndNewlines),
        text: "",
        mode: .answer)
    }
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
    case .conversation, .memories, .brainMap: return .conversations
    case .rewind: return .rewind
    }
  }

  /// Which of the Memory hub's own three views to select on arrival, for the three that share its
  /// page. `nil` means the destination is a page of its own.
  var memoryDestination: MemoryHubDestination? {
    switch self {
    case .conversation: return .conversations
    case .memories: return .memories
    case .brainMap: return .brainMap
    case .rewind: return nil
    }
  }
}

// MARK: - Copy

/// The one sentence in the panel's top-right corner.
///
/// It has two jobs and they are not the same sentence: at rest it says how much Omi is holding, and
/// under a filter it says how much of that survived the filter. Collapsing them into one string is how
/// a search surface ends up claiming "0 moments captured" the moment you type a letter.
enum QueryShellCount {
  static func sentence(matching: Int, total: Int, isFiltering: Bool) -> String {
    guard isFiltering else {
      return "\(number(total)) moment\(total == 1 ? "" : "s") captured"
    }
    return "\(number(matching)) result\(matching == 1 ? "" : "s") · of \(number(total)) captured"
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

  /// Roomy: this is a place to type, not a control strip.
  static let barMinHeight: CGFloat = 64
  static let barPaddingHorizontal: CGFloat = 18
  static let barPaddingVertical: CGFloat = 12
  /// The animated mark at the leading edge.
  static let markDiameter: CGFloat = 26
  /// The push-to-talk disc. Larger than the composer's 32 because it is the bar's only round target.
  static let micDiameter: CGFloat = 38

  /// The query's point size. Visibly larger than every other run on the surface, and deliberately
  /// under `Font.inkDisplayThreshold` (22) so it resolves to the reading face rather than the display
  /// one — a search field is type you read, not a headline.
  static let queryFontSize: CGFloat = 21

  // The results panel.

  static let panelPaddingHorizontal: CGFloat = 16
  static let panelPaddingTop: CGFloat = 14
  static let panelPaddingBottom: CGFloat = 12
  /// Between the `Filter ›` row and the chips under it.
  static let panelHeaderSpacing: CGFloat = 10
  static let chipSpacing: CGFloat = 6
  static let chipHeight: CGFloat = 26

  /// The floor under the panel body, so an empty result set is still a panel and not a sliver.
  static let minimumBodyHeight: CGFloat = 120
}
