import OmiTheme
import SwiftUI

/// The compact vertical rhythm shared by every destination panel.
///
/// Each gap has exactly one owner: the destination owns the navigation-to-
/// surface gap, the panel owns its top inset, the preceding control row owns
/// the row gap, and content owns the final eight points before its first item.
/// This prevents adjacent views from stacking otherwise reasonable padding.
enum PagePanelVerticalRhythm {
  static let horizontalPadding = QueryShellLayout.panelPaddingHorizontal
  static let panelTopPadding = QueryShellLayout.panelPaddingTop
  static let rowGap = QueryShellLayout.panelHeaderSpacing
  static let contentGap = OmiSpacing.sm
  static let sectionGap = OmiSpacing.lg
  static let contentBottomPadding = OmiSpacing.lg
}

enum PagePanelFirstRowMetrics {
  static let horizontalPadding = PagePanelVerticalRhythm.horizontalPadding
  static let topPadding = PagePanelVerticalRhythm.panelTopPadding
  static let bottomPadding: CGFloat = 0
}

extension View {
  func pagePanelFirstRowInsets() -> some View {
    padding(.horizontal, PagePanelFirstRowMetrics.horizontalPadding)
      .padding(.top, PagePanelFirstRowMetrics.topPadding)
      .padding(.bottom, PagePanelFirstRowMetrics.bottomPadding)
  }

  /// A refinement row below Brain navigation. Navigation already owns the six
  /// points between rows, so this row only owns horizontal alignment.
  func pagePanelSubsequentRowInsets() -> some View {
    padding(.horizontal, PagePanelVerticalRhythm.horizontalPadding)
  }

  @ViewBuilder
  func pagePanelToolbarInsets(isBelowNavigation: Bool) -> some View {
    if isBelowNavigation {
      pagePanelSubsequentRowInsets()
    } else {
      pagePanelFirstRowInsets()
    }
  }
}

/// Shared chrome for the controls that refine a page's search results.
///
/// Search remains in the product-wide search panel. This row belongs to the
/// content it changes and gives filters, sorting, modes, and actions distinct
/// positions instead of rendering all of them as an undifferentiated chip row.
struct PageQueryToolbar<Refinement: View, ActiveFilters: View, Actions: View>: View {
  let refinement: Refinement
  let activeFilters: ActiveFilters
  let actions: Actions

  init(
    @ViewBuilder refinement: () -> Refinement,
    @ViewBuilder activeFilters: () -> ActiveFilters,
    @ViewBuilder actions: () -> Actions = { EmptyView() }
  ) {
    self.refinement = refinement()
    self.activeFilters = activeFilters()
    self.actions = actions()
  }

  var body: some View {
    ViewThatFits(in: .horizontal) {
      toolbarRow(showsActiveFilters: true)
      toolbarRow(showsActiveFilters: false)
    }
    .frame(minHeight: QueryShellLayout.chipHeight)
    .accessibilityElement(children: .contain)
  }

  private func toolbarRow(showsActiveFilters: Bool) -> some View {
    HStack(alignment: .center, spacing: OmiSpacing.sm) {
      refinement
        .fixedSize(horizontal: true, vertical: false)

      if showsActiveFilters {
        activeFilters
          .layoutPriority(-1)
      }

      Spacer(minLength: OmiSpacing.xs)

      actions
        .fixedSize(horizontal: true, vertical: false)
    }
  }
}

extension PageQueryToolbar where ActiveFilters == EmptyView {
  init(
    @ViewBuilder refinement: () -> Refinement,
    @ViewBuilder actions: () -> Actions = { EmptyView() }
  ) {
    self.init(refinement: refinement, activeFilters: { EmptyView() }, actions: actions)
  }
}

/// A labelled value used as a Menu or Button label in `PageQueryToolbar`.
/// The dimension is always visible so values such as "All" and "Default" do
/// not force users to infer what they control.
struct PageQueryControlLabel: View {
  let icon: String
  let dimension: String?
  let value: String
  var isActive = false
  var showsDisclosure = true
  var dimensionSeparator = ":"

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.caption, weight: .medium)

      if let dimension, !dimension.isEmpty {
        Text("\(dimension)\(dimensionSeparator)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(Ink.secondary)
      }

      Text(value)
        .scaledFont(size: OmiType.caption, weight: isActive ? .semibold : .medium)
        .foregroundStyle(Ink.primary)
        .lineLimit(1)

      if showsDisclosure {
        Image(systemName: "chevron.down")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .frame(height: QueryShellLayout.chipHeight)
    .glassChip(isActive: isActive)
    .fixedSize(horizontal: true, vertical: false)
    .accessibilityElement(children: .combine)
    .accessibilityLabel(
      dimension.map { "\($0), \(value)" } ?? value
    )
  }
}

/// Textual action chrome for page-level operations. Primary actions invert the
/// shared ink; secondary actions retain the neutral chip treatment.
struct PageQueryActionLabel: View {
  let icon: String
  let title: String
  var isPrimary = false
  @State private var isHovering = false

  var body: some View {
    ViewThatFits(in: .horizontal) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .lineLimit(1)
      }

      Image(systemName: icon)
        .scaledFont(size: OmiType.caption, weight: .semibold)
    }
    .foregroundStyle(isPrimary ? Ink.surface : Ink.primary)
    .tint(isPrimary ? Ink.surface : Ink.primary)
    .padding(.horizontal, OmiSpacing.sm)
    .frame(minWidth: QueryShellLayout.chipHeight)
    .frame(height: QueryShellLayout.chipHeight)
    .background {
      if isPrimary {
        Capsule(style: .continuous)
          .fill(Ink.primary)
      } else {
        Capsule(style: .continuous)
          .fill(isHovering ? Ink.rowFillHover : Ink.rowFill)
          .overlay {
            Capsule(style: .continuous)
              .stroke(Ink.separator, lineWidth: 1)
          }
      }
    }
    .contentShape(Capsule(style: .continuous))
    .onHover { isHovering = $0 }
    .accessibilityElement(children: .combine)
    .accessibilityLabel(title)
  }
}

/// A filter value and the action that removes it. Keeping these as data lets
/// the strip progressively collapse values into one `+N` menu instead of
/// wrapping the page header or clipping the selected value.
struct PageActiveFilter: Identifiable {
  let id: String
  let title: String
  let onRemove: () -> Void

  init(id: String, title: String, onRemove: @escaping () -> Void) {
    self.id = id
    self.title = title
    self.onRemove = onRemove
  }
}

struct ActivePageFilterStrip: View {
  let filters: [PageActiveFilter]
  var onClearAll: (() -> Void)?

  var body: some View {
    if !filters.isEmpty {
      ViewThatFits(in: .horizontal) {
        filterRow(visibleCount: filters.count)
        filterRow(visibleCount: min(2, filters.count))
        filterRow(visibleCount: min(1, filters.count))
        filterRow(visibleCount: 0)
      }
      .accessibilityIdentifier("active-page-filters")
    }
  }

  private func filterRow(visibleCount: Int) -> some View {
    let visible = Array(filters.prefix(visibleCount))
    let hidden = Array(filters.dropFirst(visibleCount))

    return HStack(spacing: OmiSpacing.xs) {
      ForEach(visible) { filter in
        ActivePageFilterChip(label: filter.title, onRemove: filter.onRemove)
      }

      if !hidden.isEmpty {
        Menu {
          Section("Active filters") {
            ForEach(hidden) { filter in
              Button("Remove \(filter.title)", action: filter.onRemove)
            }
          }

          if filters.count > 1, let onClearAll {
            Divider()
            Button("Clear all filters", action: onClearAll)
          }
        } label: {
          Text("+\(hidden.count)")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, OmiSpacing.sm)
            .frame(height: QueryShellLayout.chipHeight)
            .glassChip(isActive: true)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Show \(hidden.count) more active filters")
        .accessibilityLabel("\(hidden.count) more active filters")
      }
    }
    .fixedSize(horizontal: true, vertical: false)
  }
}

/// One removable value in the single active-filter row shared by list pages.
struct ActivePageFilterChip: View {
  let label: String
  let onRemove: () -> Void

  var body: some View {
    Button(action: onRemove) {
      HStack(spacing: OmiSpacing.xs) {
        Text(label)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .lineLimit(1)
          .truncationMode(.tail)
        Image(systemName: "xmark")
          .scaledFont(size: 9, weight: .bold)
      }
      .foregroundStyle(Ink.primary)
      .padding(.horizontal, OmiSpacing.sm)
      .frame(maxWidth: 150)
      .frame(height: QueryShellLayout.chipHeight)
      .glassChip(isActive: true)
    }
    .buttonStyle(.plain)
    .help("Remove \(label) filter")
    .accessibilityLabel("Remove \(label) filter")
  }
}
