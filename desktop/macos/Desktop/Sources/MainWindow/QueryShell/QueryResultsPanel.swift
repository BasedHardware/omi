//
//  QueryResultsPanel.swift — the second glass object: the panel the query bar points at.
//
//  **This file owns the panel's chrome and none of its content.** The `Filter ›` control, the live
//  count, the type chips and the frame are here; what is inside is handed in as a body and this file
//  never looks at it. The seam is one value in each direction:
//
//  - down: a `QueryShellRequest` — the term, the type, the time window. A body that wants to know what
//    the user typed reads that and nothing else.
//  - up: a `QueryShellMatchCount` preference — how many rows survived. The count line in the corner is
//    then the body's own answer rather than a second, quietly divergent count computed from the same
//    data by different code, which is the standard way a search surface starts lying about itself.
//
//  Two rungs of type, because this is glass (`Ink.tertiary` is not available here). 22 pt corner, one
//  ambient shadow, 12 pt of real air above it — see `QueryShellLayout.panelGap`.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// How many rows the panel body kept. Reported by the body, rendered by the chrome.
struct QueryShellMatchCount: PreferenceKey {
  static let defaultValue: Int = 0
  static func reduce(value: inout Int, nextValue: () -> Int) {
    value = nextValue()
  }
}

/// Whether the body has composed the whole account yet, or is still paging it in.
///
/// The corner sentence is a claim about how much Omi is holding, and while hydration is still
/// walking the account that claim is provisional and visibly climbing — the tester watched it go
/// 5,562 → 7,310 in under a minute. A number that moves under the reader has to say why.
struct QueryShellCorpusSettled: PreferenceKey {
  /// `false`, because "we have not finished looking" is the honest state before a body reports.
  static let defaultValue: Bool = false
  static func reduce(value: inout Bool, nextValue: () -> Bool) {
    value = nextValue()
  }
}

extension View {
  /// A panel body says how many rows it kept. The only thing the chrome ever learns about the body.
  func queryShellMatchCount(_ count: Int) -> some View {
    preference(key: QueryShellMatchCount.self, value: count)
  }

  /// A panel body says whether what it is showing is the whole account yet.
  func queryShellCorpusSettled(_ isSettled: Bool) -> some View {
    preference(key: QueryShellCorpusSettled.self, value: isSettled)
  }
}

struct QueryResultsPanel<Content: View, Accessory: View, Footer: View>: View {
  @Binding var request: QueryShellRequest
  let mode: QueryShellMode
  /// The whole corpus, for the resting sentence. Nil while it is still being counted, which reads as
  /// "counting…" rather than as a confident zero.
  let total: Int?
  /// Nil when the host has no results surface to go back to — Home is a chat only, so it mounts the
  /// panel without the `‹ Results` chip. The Activity hub tab never enters answer mode at all.
  let onExitAnswer: (() -> Void)?
  /// **How tall the body is allowed to be — the panel's decision, not the body's.**
  ///
  /// Each body used to pin its own height against a window it could not see, which is how the panel
  /// ended up taller than the page and clipped mid-row. The chrome is the only thing here that knows
  /// what it costs, so it is the only thing that can say what is left; the host measures the window
  /// and `QueryShellLayout.panelBodyHeight` does the arithmetic.
  let bodyHeight: CGFloat
  /// What the chip row does on this surface. Home narrows its search results in place; Activity's
  /// row is navigation — see `ActivityDestinationChip`.
  var chipBehavior: QueryPanelChipBehavior = .filterKinds

  /// One slot in the header's leading cluster, next to `Filter ›` / `‹ Results`.
  ///
  /// **The chrome still learns nothing about the body.** It does not know that the thing beside the
  /// filter is a way into the transcript, or that the thing beside the back chip is a chat menu —
  /// it knows there is a control there and where controls on this panel sit. The alternative was to
  /// hand this file a `HomeChatMenu`, which would make a panel that draws counts and time windows
  /// start knowing what chat is.
  @ViewBuilder var headerAccessory: () -> Accessory
  /// **The slot under the body, for the composer once a conversation is open.**
  ///
  /// The chrome still learns nothing about the body or about chat: it knows there is something the
  /// host wants pinned under the content and that the content's height was already reserved for it
  /// (`QueryShellLayout.panelChromeHeight`). Empty on the list, where the field belongs above the
  /// rows it filters. See `QueryComposerPlacement`.
  @ViewBuilder var footer: () -> Footer
  @ViewBuilder var content: () -> Content
  @State private var matching: Int = 0
  /// Whether `total` is a finished count or a running one. See `QueryShellCorpusSettled`.
  @State private var corpusSettled = false

  var body: some View {
    VStack(alignment: .leading, spacing: QueryShellLayout.panelHeaderSpacing) {
      header
      if mode == .results {
        chips
      }
      content()
        .frame(
          maxWidth: .infinity, minHeight: bodyHeight, maxHeight: bodyHeight, alignment: .top
        )
        .onPreferenceChange(QueryShellMatchCount.self) { matching = $0 }
        .onPreferenceChange(QueryShellCorpusSettled.self) { corpusSettled = $0 }
      footer()
    }
    .padding(.horizontal, QueryShellLayout.panelPaddingHorizontal)
    .padding(.top, QueryShellLayout.panelPaddingTop)
    .padding(.bottom, QueryShellLayout.panelPaddingBottom)
    .frame(maxWidth: .infinity)
    .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
  }

  // MARK: - Header

  private var header: some View {
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      if mode == .answer {
        if let onExitAnswer {
          backToResultsButton(onExitAnswer)
        }
      } else {
        filterControl
      }
      headerAccessory()
      Spacer(minLength: OmiSpacing.sm)
      Text(countSentence)
        .scaledFont(size: OmiType.caption, weight: .regular)
        .foregroundStyle(Ink.secondary)
        .monospacedDigit()
        .lineLimit(1)
        .accessibilityIdentifier("query-shell-count")
    }
  }

  /// `Filter ›` — a menu of time windows, and the only control that narrows the panel by *when*.
  private var filterControl: some View {
    Menu {
      Picker("Time", selection: $request.range) {
        ForEach(QueryShellRange.allCases) { range in
          Text(range.title).tag(range)
        }
      }
      .pickerStyle(.inline)
      .labelsHidden()
    } label: {
      HStack(spacing: 6) {
        Image(systemName: "line.3.horizontal.decrease")
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Text(request.range == .all ? chipBehavior.disclosureLabel : request.range.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Image(systemName: "chevron.right")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }
      .foregroundStyle(Ink.primary)
      .padding(.horizontal, 12)
      .frame(height: QueryShellLayout.chipHeight + 2)
      .glassChip(isActive: request.range != .all)
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
    // **The one tint override on this surface.** `DesktopHomeView` sets `.tint(Ink.accent)` for the
    // whole shell, and a `Menu` label inherits the tint rather than the `foregroundStyle` set on its
    // own content — so without this the `Filter` control renders in the accent, which on a surface
    // that spends its single accent on `⌘⏎ Ask` reads as two primary actions.
    .tint(Ink.primary)
    .help("Narrow the panel to a time window")
    .accessibilityIdentifier("query-shell-filter")
  }

  /// In answer mode the same corner carries the way back, because asking is a mode of this query and
  /// not a page you navigated to — there is no back button anywhere else to reach for.
  private func backToResultsButton(_ action: @escaping () -> Void) -> some View {
    Button(action: action) {
      HStack(spacing: 6) {
        Image(systemName: "chevron.left")
          .scaledFont(size: OmiType.micro, weight: .semibold)
        Text("Results")
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundStyle(Ink.primary)
      .padding(.horizontal, 12)
      .frame(height: QueryShellLayout.chipHeight + 2)
      .glassChip(isActive: false)
    }
    .buttonStyle(.plain)
    // The key is named here because the composer under the transcript no longer advertises it: a
    // chat composer with an `esc Results` hint in it is a search control on a conversation.
    .help("Back to what you captured — esc")
    .accessibilityIdentifier("query-shell-exit-answer")
  }

  private var countSentence: String {
    guard let total else { return "Counting what you've captured…" }
    if mode == .answer {
      return "Answered from \(QueryShellCount.number(total)) captured moments"
    }
    return QueryShellCount.sentence(
      matching: matching, total: total, isFiltering: request.isFiltering, isSettled: corpusSettled)
  }

  // MARK: - Chips

  @ViewBuilder
  private var chips: some View {
    HStack(spacing: QueryShellLayout.chipSpacing) {
      switch chipBehavior {
      case .filterKinds:
        ForEach(QueryShellKind.allCases) { kind in
          QueryTypeChip(
            title: kind.title,
            isActive: request.kind == kind,
            action: { request.kind = kind }
          )
          .accessibilityIdentifier("query-shell-chip-\(kind.rawValue)")
        }
      case .openDestinations(let selected, let open):
        ForEach(ActivityDestinationChip.allCases) { chip in
          QueryTypeChip(
            title: chip.title,
            isActive: chip == selected,
            action: { open(chip) }
          )
          .accessibilityIdentifier("activity-chip-\(chip.rawValue)")
        }
      }
      Spacer(minLength: 0)
    }
  }
}

/// The two things a chip row can mean. Standalone rather than nested in the generic panel so the
/// contract is assertable without naming three view types, and modelled as a value so one surface
/// cannot quietly become the other: a row where some chips filter and some navigate teaches a rule
/// and then breaks it.
enum QueryPanelChipBehavior {
  case filterKinds
  case openDestinations(selected: ActivityDestinationChip, open: (ActivityDestinationChip) -> Void)

  /// What the row's own header calls it. The word has to follow the behaviour: on Home the chips
  /// narrow the results in place and `Filter` is the truth; on Activity they open pages, and a row
  /// of destinations under the word `Filter` describes something the row does not do.
  var disclosureLabel: String {
    switch self {
    case .filterKinds: return "Filter"
    case .openDestinations: return "View"
    }
  }
}

/// The label a header control wears, so a control added beside `Filter ›` matches it instead of
/// re-deriving 12 pt of padding and `chipHeight + 2` at a second call site.
struct QueryPanelChipLabel: View {
  let systemImage: String
  var title: String? = nil
  var trailingSystemImage: String? = nil
  var isActive: Bool = false

  var body: some View {
    HStack(spacing: 6) {
      Image(systemName: systemImage)
        .scaledFont(size: OmiType.caption, weight: .semibold)
      if let title {
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      if let trailingSystemImage {
        Image(systemName: trailingSystemImage)
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }
    }
    .foregroundStyle(Ink.primary)
    .padding(.horizontal, 12)
    .frame(height: QueryShellLayout.chipHeight + 2)
    .glassChip(isActive: isActive)
  }
}

private struct QueryTypeChip: View {
  let title: String
  let isActive: Bool
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: isActive ? .semibold : .regular)
        .foregroundStyle(GlassShell.controlLabel(isProminent: isActive || isHovering))
        .padding(.horizontal, 12)
        .frame(height: QueryShellLayout.chipHeight)
        .glassChip(isActive: isActive)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isActive)
    .accessibilityAddTraits(isActive ? .isSelected : [])
  }
}
