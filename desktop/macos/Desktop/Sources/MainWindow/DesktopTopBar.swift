import OmiTheme
import SwiftUI

/// The constant floating top bar.
///
/// **It carries two things and no third.** On the left, the brand mark — which is also the way Home
/// is reached — and the two destinations a search field cannot absorb: `Library` and `Apps`. On the
/// right, three wordless controls: microphone, screen capture, settings.
///
/// The bar used to spell out `Home · Memory · Tasks · Apps` beside `Listening` and `Capture`, and both
/// halves were wrong once Home became a search surface. A **`Memory` destination sitting next to a
/// field that already returns memories is a contradiction** — the user reads it as two different
/// memories — so the destinations that search absorbs are gone from the bar and reachable through
/// `Library`, which is where the whole corpus lives when you want to browse it rather than ask for it.
/// The right-hand pills, meanwhile, were two labels permanently occupying the corner of a window whose
/// point is the field in the middle of it; `ShellStatusIcons` carries the same state in a dot and the
/// same sentence in a tooltip, at a third of the width.
///
/// **Nothing became unreachable.** INV-NAV-1 is about the destination a shell routes to, not about how
/// many pills the bar has: every established destination — Conversations, Memories, Brain Map, Tasks,
/// Rewind, Focus, Insights — is in the `Library` menu and still lands on its own feature-complete page.
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
  @State private var libraryDropdownState = MemoryDropdownInteractionState()
  @State private var libraryDropdownTask: Task<Void, Never>?
  @State private var isLibraryHovered = false
  @State private var isBrandHovered = false

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
    GeometryReader { proxy in
      let laneWidth = TopNavigationLayoutMetrics.contentLaneWidth(for: proxy.size.width)

      HStack(spacing: 0) {
        Spacer(minLength: 0)
        TopNavigationBarLayout(
          expandedNavigation: { navPills },
          compactNavigation: { compactNavigationMenu },
          persistentControls: { ShellStatusIcons(appState: appState) },
          settings: { settingsButton }
        )
        .frame(width: laneWidth)
        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .frame(height: 44)
    .padding(.vertical, OmiSpacing.sm)
    // The Library submenu is an inline overlay. Elevation belongs to the shared
    // top-bar component so every shell and exported preview paints it above the
    // destination sibling rather than relying on each call site to remember.
    .zIndex(1)
    .onDisappear {
      libraryDropdownTask?.cancel()
    }
  }

  /// The complete primary navigation remains available when the full set of
  /// fixed-width pills will not fit beside the persistent status controls.
  private var compactNavigationMenu: some View {
    Menu {
      Button {
        navigate(to: SidebarNavItem.dashboard.rawValue)
      } label: {
        Label("Home", systemImage: "magnifyingglass")
      }
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
        ForEach(LibraryDestination.allCases) { destination in
          Button {
            select(destination)
          } label: {
            Label(destination.title, systemImage: destination.icon)
          }
        }
      } label: {
        Label(item.title, systemImage: item.icon)
      }
    } else {
      Button {
        navigate(to: item.index)
      } label: {
        Label(item.title, systemImage: item.icon)
      }
    }
  }

  /// Gear that opens Settings, wordless like the two capture controls beside it. The tooltip carries
  /// the sentence the label used to.
  private var settingsButton: some View {
    ShellStatusIconButton(
      systemImage: "gearshape",
      tooltip: "Settings — permissions, capture, account (⌘,)",
      state: .inactive,
      showsDot: false,
      isSelected: selectedIndex == SidebarNavItem.settings.rawValue,
      action: { navigate(to: SidebarNavItem.settings.rawValue) }
    )
    .accessibilityIdentifier("shell-status-settings")
  }

  private var navPills: some View {
    // Flat, containerless nav so the bar blends with the page beneath it: unselected items are muted
    // text; the selected item gets a subtle highlight only.
    HStack(spacing: TopNavigationPillMetrics.itemSpacing) {
      brandHomeButton
      ForEach(navItems) { item in
        if item.index == SidebarNavItem.conversations.rawValue {
          libraryNavigationItem(item)
        } else {
          Button {
            navigate(to: item.index)
          } label: {
            TopNavigationPill(
              icon: item.icon,
              title: item.title,
              badgeCount: 0,
              isSelected: selectedIndex == item.index,
              width: TopNavigationPillMetrics.width(for: item.index)
            )
          }
          .buttonStyle(.plain)
          .help(item.title)
        }
      }
    }
  }

  /// The mark and the wordmark, and **the way back to the search surface.**
  ///
  /// Home lost its pill because Home is now the field the search results hang under, and a `Home`
  /// button next to a search field reads as somewhere else to go. The brand is the affordance every
  /// app on the machine already uses for "take me back to the start", so it is the one that is left —
  /// a real button, selected-looking while you are there, with the word in its tooltip for anyone who
  /// does not assume it.
  private var brandHomeButton: some View {
    let isSelected = selectedIndex == SidebarNavItem.dashboard.rawValue
    return Button {
      navigate(to: SidebarNavItem.dashboard.rawValue)
    } label: {
      HStack(spacing: 8) {
        OmiQueryDotMark(diameter: 18)
        Text("Omi")
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundStyle(GlassShell.controlLabel(isProminent: isSelected || isBrandHovered))
      .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
      .frame(height: TopNavigationPillMetrics.height)
      .background(GlassPillBackground(isSelected: isSelected, isHovering: isBrandHovered))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { isBrandHovered = $0 }
    .help("Search everything you've seen and heard")
    .accessibilityLabel("Omi — search everything you've seen and heard")
    .accessibilityIdentifier("shell-brand-home")
    .fixedSize()
  }

  private func select(_ destination: LibraryDestination) {
    if let memoryDestination = destination.memoryDestination {
      memoryDestinationRawValue = memoryDestination.rawValue
    }
    if destination == .rewind {
      dismissLibraryDropdown()
      OmiUISound.play(.navigate)
      onRewind()
      return
    }
    navigate(to: destination.navItem.rawValue)
  }

  /// Every nav press on this bar: the brand, the pills, the Library menu's destinations, and the
  /// settings gear. They were four copies of the same two lines; being one place is also what makes
  /// the cue fire once per press instead of once per call site that remembered to fire it.
  private func navigate(to index: Int) {
    dismissLibraryDropdown()
    OmiUISound.play(.navigate)
    OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = index }
  }

  /// `Library` — one pill standing for the whole corpus, with every destination behind it.
  ///
  /// It is selected whenever the page you are on is one of its destinations, so the bar never claims
  /// you are nowhere while you are reading a conversation.
  private func libraryNavigationItem(_ item: TopNavigationItem) -> some View {
    let isSelected = LibraryDestination.contains(selectedIndex: selectedIndex)
    let badgeCount = newMemories + newConversations + newTasks
    let pillWidth = TopNavigationPillMetrics.width(for: item.index, badgeCount: badgeCount)
    return Button {
      select(.conversations)
    } label: {
      HStack(spacing: 6) {
        Image(systemName: item.icon)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .frame(width: TopNavigationPillMetrics.iconWidth)
        Text(item.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        libraryBadge(count: badgeCount)
      }
      .foregroundStyle(GlassShell.controlLabel(isProminent: isSelected || isLibraryHovered))
      .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
      .frame(width: pillWidth, height: TopNavigationPillMetrics.height)
      .background(
        GlassPillBackground(isSelected: isSelected, isHovering: isLibraryHovered)
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help("Everything Omi has kept — hover for conversations, memories, tasks, Rewind")
    .accessibilityIdentifier("library-navigation-button")
    .onHover { isLibraryHovered = $0 }
    .fixedSize()
    .onHover { isHovering in
      libraryDropdownHoverChanged(isHovering, in: .anchor)
    }
    .overlay(alignment: .topLeading) {
      if libraryDropdownState.isPresented {
        libraryDropdown(width: max(pillWidth, TopNavigationPillMetrics.libraryMenuWidth))
          .offset(y: TopNavigationPillMetrics.height + 5)
          .transition(.opacity.combined(with: .move(edge: .top)))
          .zIndex(20)
      }
    }
    .zIndex(libraryDropdownState.isPresented ? 20 : 0)
  }

  private func libraryDropdown(width: CGFloat) -> some View {
    VStack(alignment: .leading, spacing: 5) {
      ForEach(LibraryDestination.allCases) { destination in
        LibraryDropdownRow(
          destination: destination,
          isSelected: destination.isCurrent(
            selectedIndex: selectedIndex, memoryDestinationRawValue: memoryDestinationRawValue),
          width: width,
          onSelect: { select(destination) }
        )
      }
    }
    .padding(5)
    .frame(width: width + 10)
    .glassFloatingBar(cornerRadius: PageGlass.cardRadius)
    .onHover { isHovering in
      libraryDropdownHoverChanged(isHovering, in: .dropdown)
    }
  }

  private func libraryDropdownHoverChanged(
    _ isHovering: Bool,
    in region: MemoryDropdownInteractionState.HoverRegion
  ) {
    libraryDropdownTask?.cancel()
    guard let pendingPresentation = libraryDropdownState.hoverChanged(isHovering, in: region) else {
      libraryDropdownTask = nil
      return
    }

    let delay: Duration = pendingPresentation.isPresented ? .milliseconds(140) : .milliseconds(180)
    libraryDropdownTask = Task { @MainActor in
      try? await Task.sleep(for: delay)
      guard !Task.isCancelled else { return }
      _ = libraryDropdownState.apply(pendingPresentation)
    }
  }

  private func dismissLibraryDropdown() {
    libraryDropdownTask?.cancel()
    libraryDropdownState.dismiss()
  }

  @ViewBuilder
  private func libraryBadge(count: Int) -> some View {
    if count > 0 {
      Text("+\(count)")
        .scaledFont(size: OmiType.micro, weight: .bold)
        .foregroundColor(Ink.primary)
        .padding(.horizontal, 5)
        .padding(.vertical, 1)
        .background(Capsule(style: .continuous).fill(Ink.rowFillHover))
    }
  }
}

/// Everything reachable from `Library`.
///
/// One list rather than a menu built inline, so "no destination was stranded when the bar lost its
/// pills" is a value a test can hold instead of a claim about a `body`.
enum LibraryDestination: Int, CaseIterable, Identifiable {
  case conversations
  case memories
  case brainMap
  case tasks
  case rewind
  case focus
  case insights

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .brainMap: return "Brain Map"
    case .tasks: return "Tasks"
    case .rewind: return "Rewind"
    case .focus: return "Focus"
    case .insights: return "Insights"
    }
  }

  var icon: String {
    switch self {
    case .conversations: return "text.bubble"
    case .memories: return "brain.head.profile"
    case .brainMap: return "point.3.connected.trianglepath.dotted"
    case .tasks: return "checklist"
    case .rewind: return "clock.arrow.circlepath"
    case .focus: return "eye"
    case .insights: return "lightbulb"
    }
  }

  /// The established page this routes to. Never a shell-local copy of it (INV-NAV-1).
  var navItem: SidebarNavItem {
    switch self {
    case .conversations, .memories, .brainMap: return .conversations
    case .tasks: return .tasks
    case .rewind: return .rewind
    case .focus: return .focus
    case .insights: return .insight
    }
  }

  /// The Memory hub sub-destination this selects, for the three that share the hub's page.
  var memoryDestination: MemoryHubDestination? {
    switch self {
    case .conversations: return .conversations
    case .memories: return .memories
    case .brainMap: return .brainMap
    case .tasks, .rewind, .focus, .insights: return nil
    }
  }

  func isCurrent(selectedIndex: Int, memoryDestinationRawValue: Int) -> Bool {
    guard selectedIndex == navItem.rawValue else { return false }
    guard let memoryDestination else { return true }
    return memoryDestination.rawValue == memoryDestinationRawValue
  }

  /// Whether the page currently on screen is one of `Library`'s, so the pill can show as current.
  static func contains(selectedIndex: Int) -> Bool {
    allCases.contains { $0.navItem.rawValue == selectedIndex }
  }
}

enum TopNavigationLayoutMetrics {
  /// The top bar follows the same readable lane as the query bar and results panel below it,
  /// retaining the composer's horizontal inset at narrow sizes.
  static func contentLaneWidth(for availableWidth: CGFloat) -> CGFloat {
    max(
      0,
      min(
        ChatComposerLayout.contentLaneMaxWidth,
        availableWidth - (ChatComposerLayout.pageMargin * 2)
      )
    )
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

/// Fills the proposed lane when the row fits, then pins its persistent controls
/// to the trailing edge. When it does not fit, reporting intrinsic width lets
/// `ViewThatFits` select the compact alternative.
private struct TopNavigationBarRowLayout: Layout {
  private static let navigationToControlsSpacing = OmiSpacing.md * 3
  private static let controlsToSettingsSpacing = OmiSpacing.md

  func sizeThatFits(
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) -> CGSize {
    let sizes = sizes(for: subviews)
    let intrinsicWidth =
      sizes.navigation.width + Self.navigationToControlsSpacing + sizes.controls.width
      + Self.controlsToSettingsSpacing + sizes.settings.width
    let width: CGFloat
    if let proposedWidth = proposal.width, proposedWidth.isFinite {
      width = max(proposedWidth, intrinsicWidth)
    } else {
      width = intrinsicWidth
    }
    return CGSize(
      width: width,
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
  /// Two pills, because search absorbed the rest. `Library` carries every destination the removed
  /// pills used to reach (see `LibraryDestination`); `Apps` is the one destination search cannot
  /// answer for, because an app you have not installed is not a moment you captured.
  static let primaryItems = [
    TopNavigationItem(
      index: SidebarNavItem.conversations.rawValue, title: "Library", icon: "books.vertical"),
    TopNavigationItem(index: SidebarNavItem.apps.rawValue, title: "Apps", icon: "puzzlepiece.fill"),
  ]

  static let memoryDestinations = MemoryHubDestination.allCases
}

enum TopNavigationPillMetrics {
  static let itemSpacing: CGFloat = 4
  static let horizontalPadding: CGFloat = 12
  static let height: CGFloat = 30
  static let iconWidth: CGFloat = 18
  static let badgeWidth: CGFloat = 38
  /// The Library menu has to hold `Brain Map` and `Conversations` without truncating, which is wider
  /// than the pill it hangs from.
  static let libraryMenuWidth: CGFloat = 176

  static func width(for itemIndex: Int, badgeCount: Int = 0) -> CGFloat {
    let baseWidth: CGFloat
    switch itemIndex {
    case SidebarNavItem.dashboard.rawValue:
      baseWidth = 88
    case SidebarNavItem.conversations.rawValue:
      baseWidth = 128
    case SidebarNavItem.tasks.rawValue:
      baseWidth = 84
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
          .foregroundColor(Ink.primary)
          .padding(.horizontal, 5)
          .padding(.vertical, 1)
          .background(Capsule(style: .continuous).fill(Ink.rowFillHover))
      }
    }
    .foregroundStyle(isSelected || isHovering ? Ink.primary : Ink.secondary)
    .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
    .frame(width: width, height: TopNavigationPillMetrics.height)
    .background(GlassPillBackground(isSelected: isSelected, isHovering: isHovering))
    .contentShape(Capsule())
    .onHover { isHovering = $0 }
  }
}

private struct LibraryDropdownRow: View {
  let destination: LibraryDestination
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
        Spacer(minLength: 0)
      }
      .foregroundStyle(
        isSelected || isHovering ? Ink.primary : Ink.secondary
      )
      .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
      .frame(width: width, height: TopNavigationPillMetrics.height)
      .background(GlassPillBackground(isSelected: isSelected, isHovering: isHovering))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .accessibilityIdentifier("library-destination-\(destination.rawValue)")
  }
}
