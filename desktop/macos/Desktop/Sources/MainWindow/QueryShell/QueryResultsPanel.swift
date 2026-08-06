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

extension View {
  /// A panel body says how many rows it kept. The only thing the chrome ever learns about the body.
  func queryShellMatchCount(_ count: Int) -> some View {
    preference(key: QueryShellMatchCount.self, value: count)
  }
}

struct QueryResultsPanel<Content: View, Accessory: View>: View {
  @Binding var request: QueryShellRequest
  let mode: QueryShellMode
  /// The whole corpus, for the resting sentence. Nil while it is still being counted, which reads as
  /// "counting…" rather than as a confident zero.
  let total: Int?
  let onExitAnswer: () -> Void
  /// One slot in the header's leading cluster, next to `Filter ›` / `‹ Results`.
  ///
  /// **The chrome still learns nothing about the body.** It does not know that the thing beside the
  /// filter is a way into the transcript, or that the thing beside the back chip is a chat menu —
  /// it knows there is a control there and where controls on this panel sit. The alternative was to
  /// hand this file a `HomeChatMenu`, which would make a panel that draws counts and time windows
  /// start knowing what chat is.
  @ViewBuilder var headerAccessory: () -> Accessory
  @ViewBuilder var content: () -> Content

  @State private var matching: Int = 0

  var body: some View {
    VStack(alignment: .leading, spacing: QueryShellLayout.panelHeaderSpacing) {
      header
      if mode == .results {
        chips
      }
      content()
        .frame(maxWidth: .infinity, minHeight: QueryShellLayout.minimumBodyHeight, alignment: .top)
        .onPreferenceChange(QueryShellMatchCount.self) { matching = $0 }
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
        backToResultsButton
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
        Text(request.range == .all ? "Filter" : request.range.title)
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
  private var backToResultsButton: some View {
    Button(action: onExitAnswer) {
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
    .help("Back to what you captured")
    .accessibilityIdentifier("query-shell-exit-answer")
  }

  private var countSentence: String {
    guard let total else { return "Counting what you've captured…" }
    if mode == .answer {
      return "Answered from \(QueryShellCount.number(total)) captured moments"
    }
    return QueryShellCount.sentence(
      matching: matching, total: total, isFiltering: request.isFiltering)
  }

  // MARK: - Chips

  private var chips: some View {
    HStack(spacing: QueryShellLayout.chipSpacing) {
      ForEach(QueryShellKind.allCases) { kind in
        QueryTypeChip(
          title: kind.title,
          isActive: request.kind == kind,
          action: { request.kind = kind }
        )
        .accessibilityIdentifier("query-shell-chip-\(kind.rawValue)")
      }
      Spacer(minLength: 0)
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
