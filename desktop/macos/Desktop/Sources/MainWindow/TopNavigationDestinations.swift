//
//  TopNavigationDestinations.swift — where the shell can go, and the flat row that shows it.
//
//  **There is no menu here, and that is the point.** The bar used to carry one `Library` pill that
//  opened a hover menu of seven destinations. A menu that opens because the pointer crossed it — and
//  closes because the pointer left on the way to the row you wanted — is a control that fires when you
//  did not ask and cancels when you did. Replacing hover with a click only changes *when* the wrong
//  thing happens; the destinations were still hidden behind a disclosure the rest of the time.
//
//  So the disclosure is gone and the seven destinations were re-sorted by what they actually are:
//
//  - **Three of them are one page.** Conversations, Memories and Brain Map are the Memory hub's own
//    three views (`MemoryHubDestination`). The bar was carrying a page's internal tabs, which is why
//    it needed a menu to hold them. They now live on that page, in its own switcher — see
//    `MemoryHubSwitcher`. The bar keeps one pill, `Library`, that opens the hub.
//  - **The rest are genuinely separate views**, so they are flat pills: `Tasks`, `Rewind`, `Apps`.
//    Always visible, one click, no disclosure, no hover.
//
//  `Home` is a peer of those, with a magnifying glass for a glyph. It used to be the eight-dot Omi
//  mark, and the mark also leads the query bar on Home — the same glyph twice on one screen, once
//  static in chrome and once **animating while Omi is answering**. Only the second one earns it: the
//  mark means "this is Omi answering", and a nav button that spends it on "you are on Home" dilutes
//  that to decoration. The bar's row is uniform now — every item is a glyph and a word.
//
//  What is left is a row of five words. That fits the lane at the narrowest window
//  the shell allows without falling back to the compact menu —
//  `TopNavigationBarLayoutTests.testTheFlatDestinationRowFitsTheNarrowestWindow…` measures the real
//  pills with both badges at their widest and asserts it.
//
//  **Nothing became unreachable** (INV-NAV-1). `ShellDestination` is that claim as a value: every
//  destination the shell owns, and the mechanism that reaches it. A destination with no mechanism is
//  a test failure rather than a discovery someone makes in the app.
//
//  Brand: `Ink` semantics only, two rungs on glass (INV-UI-1).
//

import OmiTheme
import SwiftUI

// MARK: - The contract

/// Every established destination the main window owns, and **how you get to it now**.
///
/// This exists so "the bar lost its menu and stranded nothing" is a value a test can hold rather than
/// a claim about a `body`. `reach` is the interesting half: it names the one mechanism responsible for
/// each destination, so a future edit that removes a pill has to move the destination somewhere else
/// explicitly instead of quietly deleting the only way in.
enum ShellDestination: Int, CaseIterable, Identifiable {
  case home
  case conversations
  case memories
  case brainMap
  case tasks
  case rewind
  /// The app catalog — connectors in, MCP destinations out.
  ///
  /// It is modelled here because it is now the **only** door to them. Home used to carry a second,
  /// smaller one: a `Connect` tray in the ask bar whose two `More` buttons opened this very page as a
  /// bounded card. When Home became the query surface that tray went with it. Nothing was stranded,
  /// because this pill was already on the bar — but nothing would have *said* so either, since `Apps`
  /// was the one destination the bar reaches that this enum did not know about. Closing that gap is
  /// the point of `reach`: the pill the user presses and the claim the test checks are now one thing.
  case apps
  case permissions
  /// The chronological activity spine — Home's former landing surface, now the Memory hub's first
  /// view. Appended last so the established cases keep their raw values.
  case activity

  /// The one mechanism that reaches a destination. Not a description of the UI — a claim about
  /// reachability that `ShellDestination.unreachable` checks.
  enum Reach: Equatable {
    /// A pill in the top bar: always visible, one click.
    case topBar
    /// One of the Memory hub's own three views, selected by the hub's switcher on the hub's page.
    /// The bar reaches the hub itself with the `Library` pill.
    case memoryHubView
    /// A row in the Settings section list, which the bar's gear opens.
    ///
    /// This case exists because `PermissionsPage` had `nil` for an answer. It renders correctly and
    /// always did; its only writer was the sidebar the glass shell stopped rendering, so it became a
    /// page with no door — and the gear's own tooltip has been promising "permissions" the whole
    /// time. The row mounts the same page the shell's route does, so this is a way in rather than a
    /// second, smaller version of it (INV-NAV-1).
    case settingsSidebar
  }

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .home: return "Chat"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .brainMap: return "Brain Map"
    case .tasks: return "Tasks"
    case .rewind: return "Rewind"
    case .apps: return "Apps"
    case .permissions: return "Permissions"
    case .activity: return "Activity"
    }
  }

  /// The established page this routes to. Never a shell-local copy of it (INV-NAV-1).
  var navItem: SidebarNavItem {
    switch self {
    case .home: return .dashboard
    case .conversations, .memories, .brainMap, .activity: return .conversations
    case .tasks: return .tasks
    case .rewind: return .rewind
    case .apps: return .apps
    case .permissions: return .permissions
    }
  }

  /// The Memory hub sub-destination this selects, for the three that share the hub's page.
  var memoryDestination: MemoryHubDestination? {
    switch self {
    case .conversations: return .conversations
    case .memories: return .memories
    case .brainMap: return .brainMap
    case .activity: return .activity
    case .home, .tasks, .rewind, .apps, .permissions: return nil
    }
  }

  /// The Settings row that opens this page, for the one the Settings list owns.
  var settingsSection: SettingsContentView.SettingsSection? {
    switch self {
    case .permissions: return .permissions
    case .home, .conversations, .memories, .brainMap, .activity, .tasks, .rewind, .apps: return nil
    }
  }

  var reach: Reach {
    switch self {
    case .conversations, .memories, .brainMap, .activity: return .memoryHubView
    case .permissions: return .settingsSidebar
    case .home, .tasks, .rewind, .apps: return .topBar
    }
  }

  /// Every destination whose `reach` is not actually wired up — empty, or INV-NAV-1 is broken.
  ///
  /// A `topBar` destination must have a pill; a `memoryHubView` must be one of the hub's own views
  /// *and* the hub itself must have a pill; a `settingsSidebar` destination must be a row the
  /// Settings list actually shows, that row must mount the whole page rather than a summary of it,
  /// *and* the bar must still carry the gear that opens Settings.
  static func unreachable(
    fromBarItems barItems: [TopNavigationItem] = TopNavigationRoutes.primaryItems,
    persistentItems: [TopNavigationItem] = TopNavigationRoutes.persistentItems,
    settingsSidebarSections: [SettingsContentView.SettingsSection] = SettingsSidebarRoutes
      .visibleSections
  ) -> [ShellDestination] {
    let barTargets = Set(barItems.map(\.index))
    let persistentTargets = Set(persistentItems.map(\.index))
    return allCases.filter { destination in
      switch destination.reach {
      case .topBar:
        return !barTargets.contains(destination.navItem.rawValue)
      case .memoryHubView:
        guard let hubView = destination.memoryDestination,
          MemoryHubDestination.allCases.contains(hubView)
        else { return true }
        return !barTargets.contains(SidebarNavItem.conversations.rawValue)
      case .settingsSidebar:
        guard let section = destination.settingsSection,
          settingsSidebarSections.contains(section),
          section.presentedPage == destination
        else { return true }
        return !persistentTargets.contains(SidebarNavItem.settings.rawValue)
      }
    }
  }

  /// Whether the page currently on screen is one of the hub's, so the `Library` pill can read as
  /// current while you are reading a conversation rather than claiming you are nowhere.
  static func isHubPage(selectedIndex: Int) -> Bool {
    selectedIndex == SidebarNavItem.conversations.rawValue
  }
}

// MARK: - The bar's own vocabulary

struct TopNavigationItem: Identifiable, Equatable {
  let index: Int
  let title: String
  let icon: String
  /// The sentence the one-word label is short for. Never an instruction about how to operate the
  /// control — the retired menu's tooltip read "hover for conversations, memories, tasks, Rewind",
  /// which is a UI explaining itself instead of being obvious.
  let tooltip: String

  init(index: Int, title: String, icon: String, tooltip: String? = nil) {
    self.index = index
    self.title = title
    self.icon = icon
    self.tooltip = tooltip ?? title
  }

  var id: Int { index }
}

enum TopNavigationRoutes {
  /// **The whole navigation, flat.** `Library` is the Memory hub — the one destination that owns
  /// more than one view, and it shows those views itself. The other four are single pages, so they
  /// are single pills. Nothing here opens a menu.
  static let primaryItems = [
    TopNavigationItem(
      index: SidebarNavItem.dashboard.rawValue, title: "Chat", icon: "bubble.left.and.text.bubble.right",
      tooltip: "Chat — talk to Omi about everything you've seen and heard"),
    TopNavigationItem(
      index: SidebarNavItem.conversations.rawValue, title: "Memories", icon: "books.vertical",
      tooltip: "Everything Omi has kept — activity, conversations, memories, brain map"),
    TopNavigationItem(
      index: SidebarNavItem.tasks.rawValue, title: "Tasks", icon: "checklist",
      tooltip: "Tasks — everything Omi heard you commit to"),
    TopNavigationItem(
      index: SidebarNavItem.rewind.rawValue, title: "Rewind", icon: "clock.arrow.circlepath",
      tooltip: "Rewind — replay what was on your screen"),
    TopNavigationItem(
      index: SidebarNavItem.apps.rawValue, title: "Apps", icon: "puzzlepiece.fill",
      tooltip: "Apps — connectors, imports and exports"),
  ]

  /// **The controls pinned to the lane's trailing edge that are navigation**, as opposed to the two
  /// capture toggles beside them. Today that is the settings gear.
  ///
  /// It is a value for the same reason `primaryItems` is: `Permissions` and `Help` are reached
  /// through Settings, so "the gear is still there" is part of whether those pages have a door at
  /// all, and `ShellDestination.unreachable()` has to be able to ask.
  static let persistentItems = [
    TopNavigationItem(
      index: SidebarNavItem.settings.rawValue, title: "Settings", icon: "gearshape",
      tooltip: "Settings — permissions, capture, account (⌘,)")
  ]

  static let memoryDestinations = MemoryHubDestination.allCases
}

/// The `+N` counts the row carries, one per pill that owns them.
///
/// Split rather than summed onto one pill: while `Tasks` lived inside the `Library` menu, a single
/// badge on `Library` was the only honest place to put a task count. Now that `Tasks` is its own pill,
/// a task counted on `Library` would send you to the wrong page.
struct TopNavigationDestinationBadges: Equatable {
  var library: Int = 0
  var tasks: Int = 0

  func count(forNavItemIndex index: Int) -> Int {
    switch index {
    case SidebarNavItem.conversations.rawValue: return library
    case SidebarNavItem.tasks.rawValue: return tasks
    default: return 0
    }
  }
}

// MARK: - The row

/// The bar's left half: the mark, then one pill per destination.
///
/// It takes plain values rather than the app's view models, which is what lets the layout test host
/// the *real* row — real labels, real icons, real badges — and prove it fits the narrowest window.
struct TopNavigationDestinationRow: View {
  let selectedIndex: Int
  let badges: TopNavigationDestinationBadges
  let onSelect: (Int) -> Void

  var body: some View {
    HStack(spacing: TopNavigationPillMetrics.itemSpacing) {
      ForEach(TopNavigationRoutes.primaryItems) { item in
        Button {
          onSelect(item.index)
        } label: {
          TopNavigationPill(
            icon: item.icon,
            title: item.title,
            badgeCount: badges.count(forNavItemIndex: item.index),
            isSelected: isSelected(item)
          )
        }
        .buttonStyle(.plain)
        .help(item.tooltip)
        .accessibilityLabel(item.tooltip)
        .accessibilityIdentifier("top-navigation-\(item.index)")
      }
    }
  }

  private func isSelected(_ item: TopNavigationItem) -> Bool {
    if item.index == SidebarNavItem.conversations.rawValue {
      return ShellDestination.isHubPage(selectedIndex: selectedIndex)
    }
    return selectedIndex == item.index
  }
}

enum TopNavigationPillMetrics {
  static let itemSpacing: CGFloat = 4
  static let horizontalPadding: CGFloat = 12
  static let height: CGFloat = 30
  static let iconWidth: CGFloat = 18
}

/// One destination. **It hugs its own label** rather than taking a width from a table keyed by rail
/// index: five pills whose widths were guessed one at a time is how a row that fitted in a mockup
/// stops fitting once a badge appears on two of them.
private struct TopNavigationPill: View {
  let icon: String
  let title: String
  let badgeCount: Int
  let isSelected: Bool
  @State private var isHovering = false

  var body: some View {
    HStack(spacing: 6) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .frame(width: TopNavigationPillMetrics.iconWidth)
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .lineLimit(1)
        .fixedSize()
      if badgeCount > 0 {
        TopNavigationBadge(count: badgeCount)
      }
    }
    .foregroundStyle(GlassShell.controlLabel(isProminent: isSelected || isHovering))
    .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
    .frame(height: TopNavigationPillMetrics.height)
    .background(GlassPillBackground(isSelected: isSelected, isHovering: isHovering))
    .contentShape(Capsule())
    .onHover { isHovering = $0 }
    .fixedSize()
  }
}

/// How many of this destination's rows arrived since Omi last lost the front.
private struct TopNavigationBadge: View {
  let count: Int

  var body: some View {
    Text("+\(count)")
      .scaledFont(size: OmiType.micro, weight: .bold)
      .foregroundColor(Ink.primary)
      .monospacedDigit()
      .lineLimit(1)
      .fixedSize()
      .padding(.horizontal, 5)
      .padding(.vertical, 1)
      .background(Capsule(style: .continuous).fill(Ink.rowFillHover))
  }
}
