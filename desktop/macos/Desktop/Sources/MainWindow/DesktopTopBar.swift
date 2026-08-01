import Foundation
import OmiTheme
import SwiftUI

/// The constant floating top bar that replaces the left nav rail: primary
/// navigation (Home / Memory / Tasks / Apps), a "new since you were last here"
/// counter (conversations · memories · tasks created while Omi wasn't in front),
/// and the Capture/Listening controls on the right.
struct DesktopTopBar: View {
  @Binding var selectedIndex: Int
  @Binding var memoryDestinationRawValue: Int
  @ObservedObject var appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  @ObservedObject var tasksStore: TasksStore
  /// Items created after this instant count as "new" — updated whenever Omi
  /// last resigned front (see DesktopHomeView).
  let sinceDate: Date
  let onRewind: () -> Void
  @State private var memoryDropdownState = MemoryDropdownInteractionState()
  @State private var memoryDropdownTask: Task<Void, Never>?
  @State private var isMemoryButtonHovered = false

  private var navItems: [TopNavigationItem] { TopNavigationRoutes.primaryItems }

  private var newConversations: Int {
    appState.conversations.filter { $0.createdAt > sinceDate && $0.deleted != true }.count
  }
  private var newMemories: Int {
    memoriesViewModel.memories.filter { $0.createdAt > sinceDate }.count
  }
  private var newTasks: Int {
    tasksStore.tasks.filter { $0.createdAt > sinceDate && $0.deleted != true }.count
  }

  var body: some View {
    TopNavigationBarLayout(
      expandedNavigation: { navPills },
      compactNavigation: { compactNavigationMenu },
      persistentControls: { CaptureListeningControls(appState: appState, onRewind: onRewind) },
      settings: { settingsButton }
    )
    .frame(maxWidth: .infinity)
    .frame(height: 44)
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .onDisappear {
      memoryDropdownTask?.cancel()
    }
  }

  /// The complete primary navigation remains available when the full set of
  /// fixed-width pills will not fit beside the persistent status controls.
  private var compactNavigationMenu: some View {
    Menu {
      ForEach(navItems) { item in
        compactNavigationItem(item)
      }
    } label: {
      Label("Navigate", systemImage: "sidebar.left")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .frame(height: 32)
    }
    .help("Navigate")
    .accessibilityLabel("Navigate")
    .accessibilityIdentifier("compact-navigation-menu")
  }

  @ViewBuilder
  private func compactNavigationItem(_ item: TopNavigationItem) -> some View {
    if item.index == SidebarNavItem.conversations.rawValue {
      Menu {
        ForEach(TopNavigationRoutes.memoryDestinations) { destination in
          Button {
            selectMemoryDestination(destination)
          } label: {
            Label(destination.title, systemImage: destination.icon)
          }
        }
      } label: {
        Label(item.title, systemImage: item.icon)
      }
    } else {
      Button {
        dismissMemoryDropdown()
        OmiMotion.withGated(.easeOut(duration: 0.08)) {
          selectedIndex = item.index
        }
      } label: {
        Label(item.title, systemImage: item.icon)
      }
    }
  }

  /// Gear that opens Settings. The old left rail held the settings/profile entry;
  /// with the rail gone this is the only visible way in (⌘, still works too).
  private var settingsButton: some View {
    let isActive = selectedIndex == SidebarNavItem.settings.rawValue
    return Button {
      dismissMemoryDropdown()
      OmiMotion.withGated(.easeOut(duration: 0.08)) {
        selectedIndex = SidebarNavItem.settings.rawValue
      }
    } label: {
      Image(systemName: "gearshape")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(isActive ? OmiColors.textPrimary : OmiColors.textTertiary)
        .frame(width: 32, height: 32)
        .background(Circle().fill(isActive ? OmiColors.textPrimary.opacity(0.08) : Color.clear))
        .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .help("Settings")
  }

  private var navPills: some View {
    // Flat, containerless nav so the bar blends with the chat page: unselected
    // items are muted text; the selected item gets a subtle highlight only.
    HStack(spacing: TopNavigationPillMetrics.itemSpacing) {
      ForEach(navItems) { item in
        if item.index == SidebarNavItem.conversations.rawValue {
          memoryNavigationItem(item)
        } else {
          let badgeCount = newCount(for: item)
          Button {
            dismissMemoryDropdown()
            OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = item.index }
          } label: {
            TopNavigationPill(
              icon: item.icon,
              title: item.title,
              badgeCount: badgeCount,
              isSelected: selectedIndex == item.index,
              width: TopNavigationPillMetrics.width(for: item.index, badgeCount: badgeCount)
            )
          }
          .buttonStyle(.plain)
          .help(item.title)
        }
      }
    }
  }

  private var memoryDestination: MemoryHubDestination {
    MemoryHubDestination(rawValue: memoryDestinationRawValue) ?? .memories
  }

  private func selectMemoryDestination(_ destination: MemoryHubDestination) {
    dismissMemoryDropdown()
    memoryDestinationRawValue = destination.rawValue
    OmiMotion.withGated(.easeOut(duration: 0.08)) {
      selectedIndex = SidebarNavItem.conversations.rawValue
    }
  }

  private func memoryNavigationItem(_ item: TopNavigationItem) -> some View {
    let isSelected =
      selectedIndex == item.index && memoryDestination == .memories
    let badgeCount = newCount(for: item)
    let pillWidth = TopNavigationPillMetrics.width(for: item.index, badgeCount: badgeCount)
    return Button {
      selectMemoryDestination(.memories)
    } label: {
      HStack(spacing: 6) {
        Image(systemName: item.icon)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .frame(width: TopNavigationPillMetrics.iconWidth)
        Text(item.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        memoryBadge(count: badgeCount)
      }
      .foregroundStyle(
        isSelected || isMemoryButtonHovered
          ? OmiColors.textPrimary : OmiColors.textSecondary
      )
      .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
      .frame(width: pillWidth, height: TopNavigationPillMetrics.height)
      .background(
        Capsule(style: .continuous)
          .fill(
            isSelected
              ? OmiColors.textPrimary.opacity(0.10)
              : isMemoryButtonHovered ? OmiColors.textPrimary.opacity(0.06) : Color.clear
          )
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help("Open Memories — hover for more Memory views")
    .accessibilityIdentifier("memory-navigation-button")
    .onHover { isMemoryButtonHovered = $0 }
    .fixedSize()
    .onHover { isHovering in
      memoryDropdownHoverChanged(isHovering, in: .anchor)
    }
    .overlay(alignment: .topLeading) {
      if memoryDropdownState.isPresented {
        memoryDropdown(width: pillWidth)
          .offset(y: TopNavigationPillMetrics.height + 5)
          .transition(.opacity.combined(with: .move(edge: .top)))
          .zIndex(20)
      }
    }
    .zIndex(memoryDropdownState.isPresented ? 20 : 0)
  }

  private func memoryDropdown(width: CGFloat) -> some View {
    VStack(alignment: .leading, spacing: 5) {
      ForEach(MemoryHubDestination.dropdownDestinations) { destination in
        MemoryDropdownRow(
          destination: destination,
          isSelected: memoryDestination == destination,
          width: width,
          onSelect: { selectMemoryDestination(destination) }
        )
      }
    }
    .frame(width: width)
    .onHover { isHovering in
      memoryDropdownHoverChanged(isHovering, in: .dropdown)
    }
  }

  private func memoryDropdownHoverChanged(
    _ isHovering: Bool,
    in region: MemoryDropdownInteractionState.HoverRegion
  ) {
    memoryDropdownTask?.cancel()
    guard let pendingPresentation = memoryDropdownState.hoverChanged(isHovering, in: region) else {
      memoryDropdownTask = nil
      return
    }

    let delay: Duration = pendingPresentation.isPresented ? .milliseconds(140) : .milliseconds(180)
    memoryDropdownTask = Task { @MainActor in
      try? await Task.sleep(for: delay)
      guard !Task.isCancelled else { return }
      _ = memoryDropdownState.apply(pendingPresentation)
    }
  }

  private func dismissMemoryDropdown() {
    memoryDropdownTask?.cancel()
    memoryDropdownState.dismiss()
  }

  @ViewBuilder
  private func memoryBadge(count: Int) -> some View {
    if count > 0 {
      Text("+\(count)")
        .scaledFont(size: OmiType.micro, weight: .bold)
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, 5)
        .padding(.vertical, 1)
        .background(Capsule(style: .continuous).fill(OmiColors.textPrimary.opacity(0.16)))
    }
  }

  /// New-item count to badge on a nav button (since Omi was last in front).
  /// The Memory hub holds both memories and conversations, so its badge sums
  /// them; Tasks badges new tasks. Home/Apps have no counter.
  private func newCount(for item: TopNavigationItem) -> Int {
    switch item.index {
    case SidebarNavItem.conversations.rawValue: return newMemories + newConversations
    case SidebarNavItem.tasks.rawValue: return newTasks
    default: return 0
    }
  }
}

/// Keeps the persistent capture and settings controls visible while replacing
/// only primary navigation with its compact menu when a whole top-bar row no
/// longer fits. Keeping the alternatives at this level means SwiftUI measures
/// the complete row instead of an unconstrained child of an `HStack`.
struct TopNavigationBarLayout<
  ExpandedNavigation: View,
  CompactNavigation: View,
  PersistentControls: View,
  Settings: View
>: View {
  let expandedNavigation: ExpandedNavigation
  let compactNavigation: CompactNavigation
  let persistentControls: PersistentControls
  let settings: Settings

  init(
    @ViewBuilder expandedNavigation: () -> ExpandedNavigation,
    @ViewBuilder compactNavigation: () -> CompactNavigation,
    @ViewBuilder persistentControls: () -> PersistentControls,
    @ViewBuilder settings: () -> Settings
  ) {
    self.expandedNavigation = expandedNavigation()
    self.compactNavigation = compactNavigation()
    self.persistentControls = persistentControls()
    self.settings = settings()
  }

  var body: some View {
    ViewThatFits(in: .horizontal) {
      TopNavigationBarRowLayout {
        expandedNavigation
        persistentControls
        settings
      }
      TopNavigationBarRowLayout {
        compactNavigation
        persistentControls
        settings
      }
    }
    .frame(maxWidth: .infinity)
  }
}

/// Measures a top-bar row at its no-overflow width, then pins its persistent
/// controls to the trailing edge once `ViewThatFits` has selected it.
private struct TopNavigationBarRowLayout: Layout {
  private static let navigationToControlsSpacing = OmiSpacing.md * 3
  private static let controlsToSettingsSpacing = OmiSpacing.md

  func sizeThatFits(
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) -> CGSize {
    let sizes = sizes(for: subviews)
    return CGSize(
      width: sizes.navigation.width + Self.navigationToControlsSpacing + sizes.controls.width
        + Self.controlsToSettingsSpacing + sizes.settings.width,
      height: max(sizes.navigation.height, sizes.controls.height, sizes.settings.height)
    )
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    let sizes = sizes(for: subviews)
    guard subviews.count == 3 else { return }

    let settingsX = bounds.maxX
    let controlsX = settingsX - sizes.settings.width - Self.controlsToSettingsSpacing

    // Cap navigation to the space available before the persistent controls so
    // that an enlarged font scale (where even the compact fallback overflows)
    // constrains navigation instead of overlapping capture/settings controls.
    let availableNavigationWidth = max(
      0,
      controlsX - Self.navigationToControlsSpacing - bounds.minX
    )
    let navigationProposal = CGSize(
      width: min(sizes.navigation.width, availableNavigationWidth),
      height: sizes.navigation.height
    )

    subviews[0].place(
      at: CGPoint(x: bounds.minX, y: bounds.midY),
      anchor: .leading,
      proposal: ProposedViewSize(navigationProposal)
    )
    subviews[1].place(
      at: CGPoint(x: controlsX, y: bounds.midY),
      anchor: .trailing,
      proposal: ProposedViewSize(sizes.controls)
    )
    subviews[2].place(
      at: CGPoint(x: settingsX, y: bounds.midY),
      anchor: .trailing,
      proposal: ProposedViewSize(sizes.settings)
    )
  }

  private func sizes(for subviews: Subviews) -> (navigation: CGSize, controls: CGSize, settings: CGSize) {
    guard subviews.count == 3 else { return (.zero, .zero, .zero) }
    return (
      subviews[0].sizeThatFits(.unspecified),
      subviews[1].sizeThatFits(.unspecified),
      subviews[2].sizeThatFits(.unspecified)
    )
  }
}

struct TopNavigationItem: Identifiable, Equatable {
  let index: Int
  let title: String
  let icon: String

  var id: Int { index }
}

enum TopNavigationRoutes {
  static var primaryItems: [TopNavigationItem] {
    primaryItems(
      bundleIdentifier: Bundle.main.bundleIdentifier,
      productionOmensRolloutEnabled: false)
  }

  static func primaryItems(
    bundleIdentifier: String?,
    productionOmensRolloutEnabled: Bool
  ) -> [TopNavigationItem] {
    let visibleSidebarItems = Set(
      SidebarNavItem.mainItems(
        bundleIdentifier: bundleIdentifier,
        productionOmensRolloutEnabled: productionOmensRolloutEnabled))
    return [
      TopNavigationItem(index: SidebarNavItem.dashboard.rawValue, title: "Home", icon: "house.fill"),
      TopNavigationItem(index: SidebarNavItem.conversations.rawValue, title: "Memory", icon: "brain"),
      TopNavigationItem(index: SidebarNavItem.tasks.rawValue, title: "Tasks", icon: "checklist"),
      TopNavigationItem(
        index: SidebarNavItem.projections.rawValue, title: "Omens",
        icon: "sparkles.rectangle.stack.fill"),
      TopNavigationItem(index: SidebarNavItem.apps.rawValue, title: "Apps", icon: "puzzlepiece.fill"),
    ].filter { item in
      guard let sidebarItem = SidebarNavItem(rawValue: item.index) else { return false }
      return visibleSidebarItems.contains(sidebarItem)
    }
  }

  static let memoryDestinations = MemoryHubDestination.allCases
}

enum TopNavigationPillMetrics {
  static let itemSpacing: CGFloat = 4
  static let horizontalPadding: CGFloat = 12
  static let height: CGFloat = 30
  static let iconWidth: CGFloat = 18
  static let badgeWidth: CGFloat = 38

  static func width(for itemIndex: Int, badgeCount: Int = 0) -> CGFloat {
    let baseWidth: CGFloat
    switch itemIndex {
    case SidebarNavItem.dashboard.rawValue:
      baseWidth = 88
    case SidebarNavItem.conversations.rawValue:
      baseWidth = 128
    case SidebarNavItem.tasks.rawValue:
      baseWidth = 84
    case SidebarNavItem.projections.rawValue:
      baseWidth = 96
    case SidebarNavItem.apps.rawValue:
      baseWidth = 80
    default:
      baseWidth = 88
    }
    return baseWidth + (badgeCount > 0 ? badgeWidth : 0)
  }
}

private struct TopNavigationPill: View {
  let icon: String
  let title: String
  let badgeCount: Int
  let isSelected: Bool
  let width: CGFloat
  @State private var isHovering = false

  var body: some View {
    HStack(spacing: 6) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .frame(width: TopNavigationPillMetrics.iconWidth)
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .semibold)
      if badgeCount > 0 {
        Text("+\(badgeCount)")
          .scaledFont(size: OmiType.micro, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
          .padding(.horizontal, 5)
          .padding(.vertical, 1)
          .background(Capsule(style: .continuous).fill(OmiColors.textPrimary.opacity(0.16)))
      }
    }
    .foregroundStyle(isSelected || isHovering ? OmiColors.textPrimary : OmiColors.textTertiary)
    .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
    .frame(width: width, height: TopNavigationPillMetrics.height)
    .background(
      Capsule(style: .continuous)
        .fill(
          isSelected
            ? OmiColors.textPrimary.opacity(0.10)
            : isHovering ? OmiColors.textPrimary.opacity(0.06) : Color.clear
        )
    )
    .contentShape(Capsule())
    .onHover { isHovering = $0 }
  }
}

private struct MemoryDropdownRow: View {
  let destination: MemoryHubDestination
  let isSelected: Bool
  let width: CGFloat
  let onSelect: () -> Void
  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      HStack(spacing: 6) {
        Image(systemName: destination.icon)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .frame(width: TopNavigationPillMetrics.iconWidth)
        Text(destination.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundStyle(
        isSelected || isHovering ? OmiColors.textPrimary : OmiColors.textSecondary
      )
      .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
      .frame(width: width, height: TopNavigationPillMetrics.height)
      .background(
        Capsule(style: .continuous)
          .fill(
            isSelected
              ? OmiColors.backgroundTertiary
              : isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary
          )
      )
      .overlay(
        Capsule(style: .continuous)
          .stroke(OmiColors.border.opacity(0.55), lineWidth: 1)
      )
      .shadow(color: Color.black.opacity(0.24), radius: 8, y: 3)
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .accessibilityIdentifier("memory-destination-\(destination.rawValue)")
  }
}
