import OmiTheme
import SwiftUI

/// The constant floating top bar.
///
/// **It carries the destinations flat, and nothing opens.** On the left, one pill per destination:
/// `Home`, `Activity`, `Tasks`, `Rewind`, `Apps`. On the right, the referral action sits immediately
/// before the microphone, followed by screen capture and settings.
///
/// The bar used to spell out `Home · Memory · Tasks · Apps` beside `Listening` and `Capture`, and both
/// halves were wrong once Home became a search surface. A **`Memory` destination sitting next to a
/// field that already returns memories is a contradiction** — the user reads it as two different
/// memories — so the destinations that search absorbs are reached through `Activity`, which is where
/// the whole corpus lives when you want to browse it rather than ask for it. The right-hand pills,
/// meanwhile, were two labels permanently occupying the corner of a window whose point is the field in
/// the middle of it; `ShellStatusIcons` carries the same state in a dot and the same sentence in a
/// tooltip, at a third of the width.
///
/// That pill — then labelled `Library` — briefly opened a **hover menu** of seven destinations, and
/// that was the worse mistake: a control that opens because the pointer crossed it and closes because
/// the pointer left on the way to the row you wanted. It is gone. Three of its seven entries were the
/// Memory hub's own views and now live as chips on the page this pill opens
/// (`ActivityDestinationChip`); the rest are the flat pills above. See
/// `TopNavigationDestinations.swift` for the full argument and `ShellDestination` for the
/// reachability contract that keeps it honest.
///
/// **Nothing became unreachable.** INV-NAV-1 is about the destination a shell routes to, not about how
/// many pills the bar has: every established destination — Home, Conversations, Memories, Brain Map,
/// Tasks, Rewind — still lands on its own feature-complete page. `Insights` is not in that list
/// because its page was deleted rather than rehoused: the invariant forbids *stranding* a destination
/// behind a reduced copy, not retiring one. What the assistant produces still arrives, as memories and
/// notifications, and Home's knows-list still reads its history (`InsightStorage`).
///
/// **It is a panel, and it is the same panel as the two below it.** The window has no ground
/// (`ShellWindowChrome`), so a bar drawn with nothing behind it is type hanging on the user's wallpaper
/// — legible, and reading as a fault rather than as a design. One full-lane bar rather than a pill
/// hugging its own content, for two reasons: the row already pins its trailing controls to the lane's
/// trailing edge, so a content-hugging shape would have to become *two* pills and lose that edge; and
/// three objects stacked on one lane with one corner and one shadow read as one surface, where a narrow
/// pill floating over two wide panels reads as a stray. Everything it wears is `InkGlass`'s.
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
  @State private var showingReferral = false

  private var newConversations: Int {
    appState.conversations.filter { $0.createdAt > sinceDate && $0.deleted != true }.count
  }
  private var newMemories: Int {
    memoriesViewModel.memories.filter { $0.createdAt > sinceDate }.count
  }
  private var newTasks: Int {
    tasksStore.tasks.filter { $0.createdAt > sinceDate && !$0.isRetired }.count
  }

  private var badges: TopNavigationDestinationBadges {
    TopNavigationDestinationBadges(library: newConversations + newMemories, tasks: newTasks)
  }

  var body: some View {
    GeometryReader { proxy in
      let laneWidth = TopNavigationLayoutMetrics.contentLaneWidth(for: proxy.size.width)

      HStack(spacing: 0) {
        Spacer(minLength: 0)
        TopNavigationBarLayout(
          expandedNavigation: {
            TopNavigationDestinationRow(
              selectedIndex: selectedIndex, badges: badges, onSelect: navigate)
          },
          compactNavigation: { compactNavigationMenu },
          persistentControls: {
            TopNavigationTrailingControlsLayout(
              updateStatus: { DesktopUpdateStatusChip() },
              referral: { ReferralTopBarButton { showingReferral = true } },
              statusControls: { ShellStatusIcons(appState: appState) }
            )
          },
          settings: { settingsButton }
        )
        // The inset first, then the lane: the *glass* is exactly `laneWidth`, so the bar shares a
        // leading edge with the panels under it, and the controls sit inside that edge rather than
        // touching the corner.
        .padding(.horizontal, TopNavigationLayoutMetrics.barContentInset)
        .frame(width: laneWidth, height: TopNavigationLayoutMetrics.barHeight)
        .inkGlassPanel(
          cornerRadius: TopNavigationLayoutMetrics.barCornerRadius,
          shadow: TopNavigationLayoutMetrics.barShadow
        )
        .shellWindowDragHandle()
        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .frame(height: TopNavigationLayoutMetrics.barHeight)
    // Gap below the bar only: padding above it would put the top resize handle on empty air.
    .padding(.bottom, OmiSpacing.sm)
    // The compact fallback's menu is the one surface here that draws outside the bar. Elevation
    // belongs to the shared top-bar component so every shell and exported preview paints it above the
    // destination sibling rather than relying on each call site to remember (INV-NAV-1).
    .zIndex(1)
    .sheet(isPresented: $showingReferral) {
      ReferralSheetView()
    }
    .onReceive(NotificationCenter.default.publisher(for: .openReferralSheet)) { _ in
      // The rating prompt's refer-a-friend proposal opens the same sheet as
      // the top bar's own Refer control.
      showingReferral = true
    }
  }

  /// The complete primary navigation remains available when the full row of pills will not fit beside
  /// the persistent status controls — a window narrower than the shell's own minimum, or a large
  /// accessibility text size. It is flat too: the same destinations, one press each.
  private var compactNavigationMenu: some View {
    Menu {
      ForEach(TopNavigationRoutes.primaryItems) { item in
        Button {
          navigate(to: item.index)
        } label: {
          Label(item.title, systemImage: item.icon)
        }
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

  /// Gear that opens Settings, wordless like the two capture controls beside it. The tooltip carries
  /// the sentence the label used to — and now it is true: `Permissions` is a row in the list this
  /// opens, where before the gear promised a surface Settings did not have.
  ///
  /// Built from `TopNavigationRoutes.persistentItems` rather than from literals here, so the gear
  /// the user presses and the gear `ShellDestination.unreachable()` checks are the same one.
  @ViewBuilder
  private var settingsButton: some View {
    ForEach(TopNavigationRoutes.persistentItems) { item in
      ShellStatusIconButton(
        systemImage: item.icon,
        tooltip: item.tooltip,
        // No live capability behind it, so it wears neither the dot nor the off-slash: a permanently
        // hollow badge or a struck-through gear would both report a state Settings does not have.
        state: nil,
        isSelected: selectedIndex == item.index,
        action: { navigate(to: item.index) }
      )
      .accessibilityIdentifier("shell-status-settings")
    }
  }

  /// Every nav press on this bar: the brand, the pills and the settings gear. Keeping the transition
  /// in one place prevents those entry points from drifting apart.
  ///
  /// `Rewind` is the one destination the shell does not reach by index — each shell hands the bar its
  /// own way in (an overlay here, a `More` route in chat-first), so the pill calls that.
  private func navigate(to index: Int) {
    guard index != SidebarNavItem.rewind.rawValue else {
      onRewind()
      return
    }
    OmiMotion.withGated(.easeOut(duration: 0.08)) {
      // The pill says `Activity`, so it opens Activity rather than whichever hub page was persisted
      // last. `memoryDestinationRawValue` was declared here and never written — which is why this
      // shell used to land on Memories with no chip row and no switcher: a dead end reachable from
      // a cold launch, since the stored default is `.memories`.
      if index == SidebarNavItem.conversations.rawValue {
        memoryDestinationRawValue = MemoryHubDestination.activity.rawValue
      }
      selectedIndex = index
    }
  }
}

/// The right-side controls in their visual order. Keeping Refer in this cluster makes its placement
/// independent of navigation width and keeps it directly beside the microphone at every window size.
struct TopNavigationTrailingControlsLayout<UpdateStatus: View, Referral: View, StatusControls: View>: View {
  let updateStatus: UpdateStatus
  let referral: Referral
  let statusControls: StatusControls

  init(
    @ViewBuilder updateStatus: () -> UpdateStatus,
    @ViewBuilder referral: () -> Referral,
    @ViewBuilder statusControls: () -> StatusControls
  ) {
    self.updateStatus = updateStatus()
    self.referral = referral()
    self.statusControls = statusControls()
  }

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      updateStatus
      referral
      statusControls
    }
  }
}

enum TopNavigationLayoutMetrics {
  /// The top bar follows the same readable lane as the query bar and results panel below it,
  /// retaining the composer's horizontal inset at narrow sizes.
  ///
  /// It is the **source** of that lane rather than a copy of it: `QueryShellLayout.laneWidth` and
  /// `PageGlassLaneLayout.laneWidth` both delegate here, so the bar and whatever is under it cannot
  /// drift apart.
  ///
  /// The lane fills the window. The 900 pt readable cap belongs to content inside the lane, not to
  /// the window itself: capping here inside a larger window is what drew the invisible click border
  /// around the glass.
  static func contentLaneWidth(for availableWidth: CGFloat) -> CGFloat {
    max(0, availableWidth - (DesktopWindowLayoutPolicy.windowInset * 2))
  }

  /// The bar's own height.
  ///
  /// The row inside it is 32 pt (the icon buttons; the pills are 30), so this is that plus a band of
  /// air top and bottom. Comfortably more than twice `barCornerRadius`, which matters: at exactly
  /// twice, the 22 pt corner degenerates into a capsule and the bar stops being the same *shape* as
  /// the panels under it — it becomes a giant pill sitting on two rounded rectangles.
  static let barHeight: CGFloat = 52

  /// The air between the bar's glass edge and the first pill inside it.
  ///
  /// One spacing token, not a tuned number. It exists so a *selected* pill — which is a filled capsule
  /// — never touches the panel's rounded edge, which is the one state where a flush row looks broken
  /// rather than tight.
  static let barContentInset: CGFloat = OmiSpacing.sm

  /// The corner the bar is cut to — the shared one, never a second opinion about 22. See
  /// `InkGlass.cornerRadius`: a bar and a timeline rounded differently read as two products.
  static var barCornerRadius: CGFloat { InkGlass.cornerRadius }

  /// The bar's shadow: the one broad ambient shadow every floating object in this app casts, so the
  /// three objects on the lane are lit by the same light.
  static var barShadow: InkGlassShadow { .ambient }

  /// What the trailing cluster costs the row: the two capture icons.
  ///
  /// Stated here so the layout test can ask "does the flat row of destinations fit beside the controls
  /// at the narrowest window" without hosting the capture stack and its permissions.
  static let persistentControlsWidth: CGFloat = 32 * 2 + OmiSpacing.sm
  static let settingsControlWidth: CGFloat = 32
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
