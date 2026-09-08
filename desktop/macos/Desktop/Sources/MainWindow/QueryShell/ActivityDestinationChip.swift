//
//  ActivityDestinationChip.swift — the Activity spine's chip row, and the door it now is.
//
//  Activity used to carry two stacked rows of chips: the Memory hub's switcher
//  (`Activity | Conversations | Memories | Brain Map`) and, directly beneath it, a filter row
//  (`All | Conversations | Memories | Tasks | Rewind`) that narrowed the spine in place. Two rows
//  that look alike, one word apart, doing different things is the ambiguity — you cannot tell from
//  the row which `Conversations` you are about to press.
//
//  So there is one row, and every chip in it navigates. That is the rule the row teaches and the
//  rule it keeps: no chip here narrows the list while its neighbour leaves the page. `Brain Map`
//  joins it because it is now a peer destination rather than a control hidden in the panel header.
//
//  **This value is the reachability claim, not decoration.** `ShellDestination.Reach.activityChipRow`
//  names this row as the mechanism that reaches Conversations, Memories and Brain Map now that the
//  switcher is gone, and `ShellDestination.unreachable()` checks membership here. The row's `ForEach`
//  and the invariant model therefore read the same list — a destination dropped from this enum is a
//  test failure rather than a page someone discovers is stranded.
//

import OmiTheme
import SwiftUI

/// One chip in Activity's row. Every case is a destination; none is a filter.
enum ActivityDestinationChip: String, CaseIterable, Identifiable {
  case activity
  case conversations
  case memories
  case rewind
  case brainMap

  var id: String { rawValue }

  var title: String {
    switch self {
    case .activity: return "Activity"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .rewind: return "Rewind"
    case .brainMap: return "Brain Map"
    }
  }

  /// The Brain page this chip opens. Tasks stays global because it has its own primary pill. Rewind
  /// belongs here because it is another way to inspect captured history.
  ///
  /// **Not optional, and that is the reachability claim's teeth.** A chip that opens no hub page
  /// would be a chip that reaches nothing while `reachableHubDestinations` quietly dropped it; the
  /// type forbids adding one rather than leaving a test to notice.
  var hubDestination: MemoryHubDestination {
    switch self {
    case .activity: return .activity
    case .conversations: return .conversations
    case .memories: return .memories
    case .rewind: return .rewind
    case .brainMap: return .brainMap
    }
  }

  /// Every hub page this row can reach. `ShellDestination.unreachable()` reads exactly this.
  static var reachableHubDestinations: [MemoryHubDestination] {
    allCases.map(\.hubDestination)
  }
}

/// Stable peer navigation for every Brain surface. A section selection is not a drill-in, so this
/// row stays visible instead of making each page manufacture a way back to Activity.
struct BrainSectionNavigation: View {
  let selected: MemoryHubDestination
  let onSelect: (MemoryHubDestination) -> Void

  var body: some View {
    ViewThatFits(in: .horizontal) {
      navigationRow
      ScrollView(.horizontal, showsIndicators: false) {
        navigationRow
          .padding(.trailing, QueryShellLayout.chipSpacing)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("brain-section-navigation")
  }

  @ViewBuilder
  private var navigationRow: some View {
    HStack(spacing: QueryShellLayout.chipSpacing) {
      ForEach(ActivityDestinationChip.allCases) { chip in
        BrainSectionButton(
          title: chip.title,
          isActive: chip.hubDestination == selected,
          action: { onSelect(chip.hubDestination) }
        )
        .accessibilityIdentifier("brain-section-\(chip.rawValue)")
      }
    }
  }
}

private struct BrainSectionButton: View {
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
    .contentShape(Capsule(style: .continuous))
    .onHover { isHovering = $0 }
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isActive)
    .accessibilityAddTraits(isActive ? .isSelected : [])
  }
}

/// The shared Brain page shape: the product-wide search surface above a content panel whose first
/// row is Brain navigation. Search stays visually and behaviorally identical to Chat, Tasks, and
/// Apps; section switching belongs to the thing it changes rather than decorating the query field.
struct BrainSectionPageLayout<Search: View, Content: View>: View {
  let selected: MemoryHubDestination
  let onSelect: (MemoryHubDestination) -> Void
  let search: Search
  let content: Content

  init(
    selected: MemoryHubDestination,
    onSelect: @escaping (MemoryHubDestination) -> Void,
    @ViewBuilder search: () -> Search,
    @ViewBuilder content: () -> Content
  ) {
    self.selected = selected
    self.onSelect = onSelect
    self.search = search()
    self.content = content()
  }

  var body: some View {
    GeometryReader { proxy in
      let lane = QueryShellLayout.laneWidth(for: proxy.size.width)

      VStack(spacing: QueryShellLayout.panelGap) {
        search

        VStack(alignment: .leading, spacing: 0) {
          BrainSectionNavigation(selected: selected, onSelect: onSelect)
            .padding(.horizontal, QueryShellLayout.panelPaddingHorizontal)
            .padding(.top, BrainSectionPageMetrics.navigationTopPadding)
            .padding(.bottom, BrainSectionPageMetrics.navigationBottomPadding)

          content
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
      }
      .frame(width: lane)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      .padding(.top, QueryShellLayout.surfaceTopInset)
    }
  }
}

enum BrainSectionPageMetrics {
  static let navigationTopPadding = PagePanelFirstRowMetrics.topPadding
  static let navigationBottomPadding = PagePanelVerticalRhythm.rowGap
  static let navigationHeight: CGFloat =
    QueryShellLayout.chipHeight + navigationTopPadding + navigationBottomPadding
}
