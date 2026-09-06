//
//  TopNavigationDestinations.swift — where the shell can go, and the flat row that shows it.
//
//  **There is no menu here, and that is the point.** The bar used to carry one `Library` pill that
//  opened a hover menu of seven destinations. A menu that opens because the pointer crossed it — and
//  closes because the pointer left on the way to the row you wanted — is a control that fires when you
//  did not ask and cancels when you did. Replacing hover with a click only changes *when* the wrong
//  thing happens; the destinations were still hidden behind a disclosure the rest of the time.
//
//  So the disclosure is gone and the destinations were re-sorted by what they actually are:
//
//  - **Five of them are one section.** Activity, Conversations, Memories, Rewind and Brain Map are
//    peer views in Brain (`MemoryHubDestination`). The bar keeps one `Brain` pill; a persistent row
//    inside the section keeps every peer visible, instead of pretending peer navigation is Back.
//  - **The rest are genuinely separate views**, so they are flat pills: `Tasks` and `Apps`.
//    Always visible, one click, no disclosure, no hover.
//
//  `Home` is a peer of those, with a magnifying glass for a glyph. It used to be the eight-dot Omi
//  mark, and the mark also leads the query bar on Home — the same glyph twice on one screen, once
//  static in chrome and once **animating while Omi is answering**. Only the second one earns it: the
//  mark means "this is Omi answering", and a nav button that spends it on "you are on Home" dilutes
//  that to decoration. The bar's row is uniform now — every item is a glyph and a word.
//
//  What is left is a row of four words. That fits the lane at the narrowest window
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
    /// A chip in Activity's row, on the page the `Activity` pill opens.
    ///
    /// This replaced `memoryHubView` when the hub's switcher was deleted. The old case named a
    /// mechanism `unreachable()` never actually checked — it only verified the pill existed — so
    /// removing the switcher would have stranded three pages with every test still green. This one
    /// is checked against `ActivityDestinationChip`, the same value the row renders from.
    case activityChipRow
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
    case .activity: return "Memories"
    }
  }

  /// The established page this routes to. Never a shell-local copy of it (INV-NAV-1).
  var navItem: SidebarNavItem {
    switch self {
    case .home: return .dashboard
    case .conversations, .memories, .brainMap, .rewind, .activity: return .conversations
    case .tasks: return .tasks
    case .apps: return .apps
    case .permissions: return .permissions
    }
  }

  /// The Brain sub-destination this selects.
  var memoryDestination: MemoryHubDestination? {
    switch self {
    case .conversations: return .conversations
    case .memories: return .memories
    case .brainMap: return .brainMap
    case .activity: return .activity
    case .rewind: return .rewind
    case .home, .tasks, .apps, .permissions: return nil
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
    /// `Activity` is what the hub's pill opens, so its door is the bar itself — the other four
    /// hub views are reached from Activity's chip row once you are there.
    case .conversations, .memories, .brainMap, .rewind: return .activityChipRow
    case .permissions: return .settingsSidebar
    case .home, .tasks, .apps, .activity: return .topBar
    }
  }

  /// Every destination whose `reach` is not actually wired up — empty, or INV-NAV-1 is broken.
  ///
  /// A `topBar` destination must have a pill; an `activityChipRow` destination must be a hub view
  /// Activity's row actually offers *and* the page that carries the row must itself have a pill; a
  /// `settingsSidebar` destination must be a row the
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
      case .activityChipRow:
        // Two claims, both checkable: the row actually offers this page, and the bar still carries
        // the pill that opens the page the row lives on.
        guard let hubView = destination.memoryDestination,
          ActivityDestinationChip.reachableHubDestinations.contains(hubView)
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

  /// Whether the page currently on screen is one of the hub's, so the `Activity` pill can read as
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
  /// **The whole primary navigation, flat.** `Brain` owns five peer views and exposes them from a
  /// persistent section row. Chat, Tasks and Apps are single pages, so they are single pills.
  static let primaryItems = [
    TopNavigationItem(
      index: SidebarNavItem.dashboard.rawValue, title: "Chat", icon: "bubble.left.and.text.bubble.right",
      tooltip: "Chat — talk to Omi about everything you've seen and heard"),
    // The hub's pill names the view it opens. It used to say `Memories` while opening whichever hub
    // view was last persisted, so the word on the bar and the page you landed on were only
    // sometimes the same thing. It opens `Brain` — the chronological spine over everything
    // captured — and says so; Conversations, Memories, Rewind and Brain Map stay one click away in that
    // page's own chip row, which is the mechanism `ShellDestination.reach` records for them.
    // The glyph is deliberately not `clock.arrow.circlepath`: that belongs to Rewind inside Brain.
    TopNavigationItem(
      index: SidebarNavItem.conversations.rawValue, title: "Memories", icon: "brain",
      tooltip: "Memories — everything Omi captured, newest first"),
    TopNavigationItem(
      index: SidebarNavItem.tasks.rawValue, title: "Tasks", icon: "checklist",
      tooltip: "Tasks — everything Omi heard you commit to"),
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
/// Split rather than summed onto one pill: while `Tasks` lived inside the retired `Library` menu, a
/// single badge on that pill was the only honest place to put a task count. Now that `Tasks` is its
/// own pill, a task counted on the hub's pill would send you to the wrong page.
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

/// The bar's left half: the tab bar, one segment per destination.
///
/// On macOS 26 it is the Liquid Glass segmented control the way iOS draws it: the segments on the bar's
/// own glass, and a glass lens under the selected word that **lifts and follows the pointer while you
/// press and drag**,
/// then settles on the nearest segment when you let go (`TopNavigationGlassSegments`). The system's own
/// `NSSegmentedControl` on the Mac gets the material but not that interaction — it flips between
/// segments — so the lens is drawn here with `glassEffect` inside one `GlassEffectContainer`, the way
/// Apple's "Build a SwiftUI app with the new design" session builds custom glass controls. Below 26 it
/// is the system segmented `Picker`, which is exactly what a macOS `TabView` draws for its tabs.
///
/// Neither renderer is a hand-drawn pill: hover, shine, Reduce Transparency, Increase Contrast and
/// accessibility text size all come from the material or the control, not from this file.
///
/// **Glyph and word on macOS 26, word only below.** The glass segments keep the SF Symbol beside each
/// title the way the pills did; the system segmented control cannot show both (it does not honour
/// `titleAndIcon`), so the fallback carries the word, which is the half that names the destination.
///
/// It takes plain values rather than the app's view models, which is what lets the layout test host
/// the *real* row — real labels, real counts — and prove it fits the narrowest window.
struct TopNavigationDestinationRow: View {
  let selectedIndex: Int
  let badges: TopNavigationDestinationBadges
  let onSelect: (Int) -> Void

  var body: some View {
    if #available(macOS 26.0, *) {
      TopNavigationGlassSegments(selectedIndex: selectedIndex, badges: badges, onSelect: onSelect)
    } else {
      segmentedFallback
    }
  }

  /// The pre-Liquid-Glass tab bar: the system segmented control.
  private var segmentedFallback: some View {
    Picker("Navigate", selection: selection) {
      ForEach(TopNavigationRoutes.primaryItems) { item in
        Text(TopNavigationSegmentSelection.title(for: item, badges: badges))
          .tag(Optional(item.index))
          .help(item.tooltip)
          .accessibilityLabel(item.tooltip)
          .accessibilityIdentifier("top-navigation-\(item.index)")
      }
    }
    .pickerStyle(.segmented)
    .labelsHidden()
    .controlSize(.large)
    // Neutral, not the accent: untinted, the control fills the selected segment with whatever
    // accent colour the machine is set to. `controlColor` keeps the knob plain in both appearances,
    // which is INV-UI-1's neutral accent and the way the system's own tab bars read.
    .tint(TopNavigationSegmentMetrics.selectionTint)
    .fixedSize()
    .accessibilityIdentifier("top-navigation-row")
  }

  /// The segmented control reads the selected tag and writes the pressed one; the shell keeps owning
  /// the index. Reading through `TopNavigationSegmentSelection` keeps the Brain rule (any hub page
  /// lights the `Memories` tab) and the "no tab" rule (Settings selects nothing) in one testable place.
  private var selection: Binding<Int?> {
    Binding(
      get: { TopNavigationSegmentSelection.selectedTag(forSelectedIndex: selectedIndex) },
      set: { tag in
        TopNavigationSegmentSelection.press(tag: tag, selectedIndex: selectedIndex, onSelect: onSelect)
      }
    )
  }
}

/// The Liquid Glass segmented control with the iOS interaction.
///
/// Every segment is the same width (`EqualWidthSegments`), as on iOS, so the lens is one shape that
/// only ever moves. The lens is the only glass here: the bar under it is already `inkGlassPanel`, and a
/// track with its own material on top of that read as a white pill on the bar rather than as part of
/// it. The lens is untinted too: no accent fill (INV-UI-1), the selected word simply goes to full ink.
///
/// Pointer down anywhere on the track lifts the lens and puts it under the pointer; dragging carries
/// it; release snaps it to the nearest segment and navigates there. A plain click is the same gesture
/// with no travel. The shell still owns the selection — the lens follows `selectedIndex` when it is not
/// being dragged, so a navigation from anywhere else (⌘1, a deep link) slides it too.
@available(macOS 26.0, *)
private struct TopNavigationGlassSegments: View {
  let selectedIndex: Int
  let badges: TopNavigationDestinationBadges
  let onSelect: (Int) -> Void

  @State private var segmentWidth: CGFloat = 0
  /// The pointer's x in track space while a press is in flight, nil otherwise.
  @State private var dragX: CGFloat?

  private var items: [TopNavigationItem] { TopNavigationRoutes.primaryItems }

  private var selectedPosition: Int? {
    guard let tag = TopNavigationSegmentSelection.selectedTag(forSelectedIndex: selectedIndex) else {
      return nil
    }
    return items.firstIndex { $0.index == tag }
  }

  /// Where the lens sits: under the pointer while dragging, else on the selected segment.
  private var lensCenterX: CGFloat? {
    let geometry = TopNavigationGlassSegmentGeometry(
      segmentWidth: segmentWidth, count: items.count, inset: TopNavigationGlassSegmentMetrics.trackInset)
    if let dragX { return geometry.lensCenterX(forPointerX: dragX) }
    guard let selectedPosition else { return nil }
    return geometry.lensCenterX(forPosition: selectedPosition)
  }

  var body: some View {
    // One glass shape, so no `GlassEffectContainer`: the container composites its glass above every
    // non-glass sibling, which put the lens *over* the words and washed the selected one out.
    // As a plain background layer the lens stays under the labels.
    EqualWidthSegments {
      ForEach(Array(items.enumerated()), id: \.element.id) { position, item in
        segment(item, isSelected: position == selectedPosition)
      }
    }
    .padding(TopNavigationGlassSegmentMetrics.trackInset)
    .background(alignment: .topLeading) {
      if let lensCenterX {
        Capsule()
          .fill(.clear)
          // `.clear`, not `.regular`: regular glass on the light bar read as a white pill. Clear glass
          // keeps the lens's refraction and shine but lets the bar's own colour through.
          .glassEffect(.clear.interactive(), in: .capsule)
          .frame(width: max(0, segmentWidth), height: TopNavigationGlassSegmentMetrics.height)
          // Lifted while held, the way the iOS lens rises off the track under a finger.
          .scaleEffect(dragX == nil ? 1 : TopNavigationGlassSegmentMetrics.liftScale)
          .position(
            x: lensCenterX,
            y: TopNavigationGlassSegmentMetrics.trackInset + TopNavigationGlassSegmentMetrics.height / 2)
      }
    }
    // No glass of the track's own: the bar it sits on is already the glass (`inkGlassPanel`), and a
    // second capsule of material on top of it read as a white pill. Only the lens is glass.
    .contentShape(Capsule())
    // The press is owned by AppKit, not by a SwiftUI `DragGesture`: the bar around this control is a
    // `WindowDragGesture` handle that recognises *simultaneously*, so a SwiftUI drag here moved the
    // lens and the whole window together. An `NSView` that claims the mouse-down keeps the window
    // still, exactly the way the Rewind scrubber keeps its own drags.
    .overlay {
      TopNavigationPointerCapture(
        onWidthChange: { width in
          segmentWidth = TopNavigationGlassSegmentGeometry.segmentWidth(
            forTrackWidth: width, count: items.count, inset: TopNavigationGlassSegmentMetrics.trackInset)
        },
        onChanged: { dragX = $0 },
        onEnded: { x, width in
          // Geometry from the overlay's own width, not from state: the release must land on the right
          // segment even before any SwiftUI update has published the measured width.
          let geometry = TopNavigationGlassSegmentGeometry(
            segmentWidth: TopNavigationGlassSegmentGeometry.segmentWidth(
              forTrackWidth: width, count: items.count, inset: TopNavigationGlassSegmentMetrics.trackInset),
            count: items.count, inset: TopNavigationGlassSegmentMetrics.trackInset)
          let position = geometry.position(forPointerX: x)
          dragX = nil
          guard items.indices.contains(position) else { return }
          TopNavigationSegmentSelection.press(
            tag: items[position].index, selectedIndex: selectedIndex, onSelect: onSelect)
        }
      )
    }
    // The lens slides under the motion gate: with Reduce Motion on it simply appears under the new
    // segment, exactly as the system's own controls behave.
    .animation(OmiMotion.gated(.snappy(duration: 0.26)), value: selectedPosition)
    .animation(OmiMotion.gated(.snappy(duration: 0.18)), value: dragX == nil)
    .fixedSize()
  }

  private func segment(_ item: TopNavigationItem, isSelected: Bool) -> some View {
    Label(TopNavigationSegmentSelection.title(for: item, badges: badges), systemImage: item.icon)
      .labelStyle(.titleAndIcon)
      .scaledFont(size: OmiType.caption, weight: .semibold)
      .lineLimit(1)
      .fixedSize()
      .foregroundStyle(isSelected ? Ink.primary : Ink.secondary)
      .padding(.horizontal, TopNavigationGlassSegmentMetrics.horizontalPadding)
      .frame(height: TopNavigationGlassSegmentMetrics.height)
      .frame(maxWidth: .infinity)
      .help(item.tooltip)
      .accessibilityElement(children: .ignore)
      .accessibilityLabel(item.tooltip)
      .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
      .accessibilityAction {
        TopNavigationSegmentSelection.press(
          tag: item.index, selectedIndex: selectedIndex, onSelect: onSelect)
      }
      .accessibilityIdentifier("top-navigation-\(item.index)")
  }
}

/// A transparent AppKit view that owns the pointer while it is down over the control.
///
/// Reports the pointer's x in the control's own coordinates, which is the track space the lens is
/// positioned in because the overlay covers the control exactly. Hover is untouched — the glass
/// lens's shine comes from SwiftUI tracking areas, which this view does not intercept.
@available(macOS 26.0, *)
private struct TopNavigationPointerCapture: NSViewRepresentable {
  /// The overlay covers the control exactly, so its width *is* the track width. Reported from
  /// `layout()`, which is the one place that is always right, rather than measured a second time
  /// through a `GeometryReader` that publishes a frame later.
  let onWidthChange: (CGFloat) -> Void
  let onChanged: (CGFloat) -> Void
  /// The release: pointer x and the track width at that instant.
  let onEnded: (CGFloat, CGFloat) -> Void

  func makeNSView(context: Context) -> PointerCaptureView {
    let view = PointerCaptureView()
    apply(to: view)
    return view
  }

  func updateNSView(_ view: PointerCaptureView, context: Context) {
    apply(to: view)
  }

  private func apply(to view: PointerCaptureView) {
    view.onWidthChange = onWidthChange
    view.onChanged = onChanged
    view.onEnded = onEnded
  }

  @MainActor
  final class PointerCaptureView: NSView {
    var onWidthChange: ((CGFloat) -> Void)?
    var onChanged: ((CGFloat) -> Void)?
    var onEnded: ((CGFloat, CGFloat) -> Void)?
    private var reportedWidth: CGFloat = -1

    /// The control keeps its own drags; the bar around it is the window handle.
    override var mouseDownCanMoveWindow: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func layout() {
      super.layout()
      guard bounds.width != reportedWidth else { return }
      reportedWidth = bounds.width
      onWidthChange?(bounds.width)
    }

    override func mouseDown(with event: NSEvent) {
      onChanged?(convert(event.locationInWindow, from: nil).x)
    }

    override func mouseDragged(with event: NSEvent) {
      onChanged?(convert(event.locationInWindow, from: nil).x)
    }

    override func mouseUp(with event: NSEvent) {
      onEnded?(convert(event.locationInWindow, from: nil).x, bounds.width)
    }
  }
}

/// Where the lens is allowed to be, in track coordinates. Pure so the drag can be tested without a
/// pointer: the lens centre is clamped to the first and last segment centres, and a release picks the
/// segment whose span contains the pointer.
struct TopNavigationGlassSegmentGeometry: Equatable {
  let segmentWidth: CGFloat
  let count: Int
  let inset: CGFloat

  /// Equal segments: the track minus its inset on both sides, shared evenly.
  static func segmentWidth(forTrackWidth width: CGFloat, count: Int, inset: CGFloat) -> CGFloat {
    guard count > 0 else { return 0 }
    return max(0, width - inset * 2) / CGFloat(count)
  }

  func lensCenterX(forPosition position: Int) -> CGFloat {
    inset + segmentWidth * (CGFloat(position) + 0.5)
  }

  func lensCenterX(forPointerX x: CGFloat) -> CGFloat {
    guard count > 0, segmentWidth > 0 else { return inset }
    return min(max(x, lensCenterX(forPosition: 0)), lensCenterX(forPosition: count - 1))
  }

  func position(forPointerX x: CGFloat) -> Int {
    guard count > 0, segmentWidth > 0 else { return 0 }
    let raw = Int(((x - inset) / segmentWidth).rounded(.down))
    return min(max(raw, 0), count - 1)
  }
}

/// Every segment as wide as the widest, in a row. Intrinsic width is `count × widest`, which is what
/// keeps the row `fixedSize` and lets the narrowest-window test measure it.
private struct EqualWidthSegments: Layout {
  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
    let widest = sizes.map(\.width).max() ?? 0
    let tallest = sizes.map(\.height).max() ?? 0
    return CGSize(width: widest * CGFloat(subviews.count), height: tallest)
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
    guard !subviews.isEmpty else { return }
    let width = bounds.width / CGFloat(subviews.count)
    for (position, subview) in subviews.enumerated() {
      subview.place(
        at: CGPoint(x: bounds.minX + width * CGFloat(position), y: bounds.minY),
        anchor: .topLeading,
        proposal: ProposedViewSize(width: width, height: bounds.height))
    }
  }
}

enum TopNavigationGlassSegmentMetrics {
  /// The air between the track's glass edge and the lens.
  static let trackInset: CGFloat = 3
  static let horizontalPadding: CGFloat = 14
  static let height: CGFloat = 28
  /// How much the lens grows while held.
  static let liftScale: CGFloat = 1.08
}

/// The two rules that turn the shell's index into what the native tab bar shows.
enum TopNavigationSegmentSelection {
  /// The tab the control should show as selected for a shell index, or `nil` for a page that has no
  /// tab (Settings, Permissions) — a tab bar with no selection is the honest state there, where a
  /// fabricated selection would claim you are on a page you are not.
  static func selectedTag(
    forSelectedIndex selectedIndex: Int,
    items: [TopNavigationItem] = TopNavigationRoutes.primaryItems
  ) -> Int? {
    if ShellDestination.isHubPage(selectedIndex: selectedIndex) {
      return SidebarNavItem.conversations.rawValue
    }
    return items.contains { $0.index == selectedIndex } ? selectedIndex : nil
  }

  /// What a press on the control does: navigate to the pressed tab, unless it is already the one
  /// showing. The control re-writes its selection on a re-press, and forwarding that would restart
  /// the page you are on. A `nil` write never navigates — the control has nowhere to go.
  static func press(tag: Int?, selectedIndex: Int, onSelect: (Int) -> Void) {
    guard let tag, tag != selectedTag(forSelectedIndex: selectedIndex) else { return }
    onSelect(tag)
  }

  /// The new-item count the pills used to wear as a badge is part of the title: `Tasks +7`. A native
  /// segment carries text and nothing else. A zero count adds nothing.
  static func title(for item: TopNavigationItem, badges: TopNavigationDestinationBadges) -> String {
    let count = badges.count(forNavItemIndex: item.index)
    return count > 0 ? "\(item.title) +\(count)" : item.title
  }
}

enum TopNavigationSegmentMetrics {
  /// The least a native segment can be and still be a target: the HIG's minimum control width. The
  /// real segments are wider — each carries a word — so this is a strict lower bound the layout test
  /// uses to notice a segment that stopped being rendered.
  static let minimumSegmentWidth: CGFloat = 44

  /// The selected segment's fill: the system control colour, so the knob is neutral glass in light
  /// and dark rather than the user's accent.
  static let selectionTint = Color(nsColor: .controlColor)
}

/// Metrics the referral pill still shares with the bar. The bar's own destinations are native
/// segments now (`TopNavigationDestinationRow`) and no longer read these.
enum TopNavigationPillMetrics {
  static let itemSpacing: CGFloat = 4
  static let horizontalPadding: CGFloat = 12
  static let height: CGFloat = 30
  static let iconWidth: CGFloat = 18
}
