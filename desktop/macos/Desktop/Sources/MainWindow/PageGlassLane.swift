//
//  PageGlassLane.swift — the panel every other destination floats on.
//
//  The main window has no ground. `OmiApp` wears the glass (`WindowGlass.wear`) and installs nothing
//  behind it, so the window is genuinely transparent and what is behind a surface is the user's
//  wallpaper. That is the whole point — panels sit *on* the desktop rather than on a full-bleed slab
//  of glass the window painted for them.
//
//  QueryShell Home and Rewind were already built that way: each is a set of glass objects with real air
//  between them (`QueryShellHome`, `RewindSearchLayout`). The two older Home surfaces are the exception:
//  `DashboardPage` is laned when it mounts either one, so without this file they render straight onto
//  the wallpaper. **Every other destination was drawn assuming the window's ground was underneath it**,
//  so this file is where they get a surface, and it is one surface for all of them: a page that invents
//  its own panel is the drift `InkGlass` exists to stop.
//
//  ## One tall panel, not a header plus a body
//
//  Home is two objects because it genuinely is two: a place you type and a place you look. A list page
//  has no second object — its header is a title, not an input — so splitting it into a header panel and
//  a body panel would draw a seam where there is no join, which is the "one slab with a rule through
//  it" failure read backwards. So a destination is **one panel, as tall as the page, scrolling inside
//  itself**, and every long page (Conversations, Memories, Tasks, Apps, Settings) is the same shape.
//  Consistency between them is worth more than either answer on its own.
//
//  ## Geometry is delegated, never restated
//
//  The lane is `TopNavigationLayoutMetrics.contentLaneWidth` — the top bar's own lane, which is also
//  the lane Home's two panels take. The corner and the shadow are `InkGlass`'s. Nothing here picks a
//  number that already exists somewhere else, for the reason `QueryShellLayout.panelGap` delegates to
//  `RewindSearchLayout.panelGap`: one product may only have one opinion about how its glass sits, and
//  a second copy of a number is how that opinion quietly becomes two.
//
//  Brand: nothing here picks a colour at all — the surface is `InkGlass`'s (INV-UI-1).
//

import OmiTheme
import SwiftUI

// MARK: - The decision

/// Which destinations already carry their own glass, and therefore must not be wrapped in more.
///
/// A pure function of the route rather than a condition inside the router, so "Home and Rewind own
/// their panels and everything else is given one" is a claim a hermetic test can hold. Nesting a
/// second `.behindWindow` surface inside a panel does not stack two materials, it takes a second copy
/// of the desktop and doubles the scrim — see `InkGlassBackdrop` — so a page wrapped twice reads
/// visibly muddier than the pages around it.
enum PageGlassLanePolicy {

  /// Whether the destination at `selectedIndex` builds its own panels.
  ///
  /// It takes the raw index rather than a `SidebarNavItem` because the router's `switch` sends every
  /// unrecognised index to Home through its `default:` branch. Resolving an unknown index to anything
  /// else here would wrap Home in a second panel on exactly the routes nobody tests. The router passes
  /// the already-resolved Home surface decision instead of making this lane read a settings key.
  static func ownsItsPanels(
    selectedIndex: Int,
    memoryDestinationRawValue: Int? = nil,
    homeOwnsItsPanels: Bool
  ) -> Bool {
    switch SidebarNavItem(rawValue: selectedIndex) ?? .dashboard {
    case .dashboard:
      return homeOwnsItsPanels
    case .rewind:
      return true
    case .conversations:
      // **Only this index is the Memory hub.** It is one rail slot wearing four different pages, and
      // only one of them builds its own glass: Activity is Home's column — a search bar and a
      // results panel, each already an `inkGlassPanel` — so wrapping the hub wholesale nested those
      // two inside a third and double-scrimmed both, the muddier-than-its-neighbours failure this
      // policy exists to prevent. The hub's list pages paint no ground and still need the lane.
      //
      // `SidebarNavItem.memories` is deliberately NOT here. In this shell that index is the
      // *standalone* `MemoriesPage`, not the hub, and it paints no ground of its own — answering
      // for it off a persisted hub destination stripped its panel and drew its rows onto the
      // wallpaper. The chat-first shell reaches the hub through `ChatFirstPageGlassLanePolicy`,
      // which never constructs this view for Activity at all.
      return MemoryHubDestination(rawValue: memoryDestinationRawValue ?? -1) == .activity
    default:
      return false
    }
  }
}

// MARK: - The metrics

/// Where a destination's panel sits and how big it is. Every value is delegated.
enum PageGlassLaneLayout {

  /// The readable lane the panel occupies — **the top bar's own lane, not a second one.**
  ///
  /// The same call Home makes (`QueryShellLayout.laneWidth`), so a page and the navigation above it
  /// share a leading edge and nothing shifts sideways as the user moves between destinations.
  static func laneWidth(for availableWidth: CGFloat) -> CGFloat {
    TopNavigationLayoutMetrics.contentLaneWidth(for: availableWidth)
  }

  /// The corner is the shared one — never a second opinion about 22.
  static var cornerRadius: CGFloat { QueryShellLayout.panelCornerRadius }

  /// The air between the top bar and the panel under it. Home's own top gap, taken from Home rather
  /// than matched by eye: a page that opens a few points lower than Home reads as the whole surface
  /// having jumped on navigation.
  static let topGap: CGFloat = OmiSpacing.sm

  /// Flush with the window's bottom edge so the resize handle sits on the visible panel, not on
  /// an invisible gutter under it.
  static let bottomGap: CGFloat = 0
}

// MARK: - The panel

/// A destination, on its own piece of glass.
///
/// It wraps the router's whole page switch rather than each page in turn, so there is exactly one
/// place that decides what a destination's surface is. A page inside it paints no background of its
/// own (`glassContent()`); the panel is the ground. Home and Rewind are handed their own-glass answer
/// by the router, while the older `DashboardPage` surfaces are handed `false` and use this panel.
struct PageGlassLane<Content: View>: View {
  /// The route being rendered, used only to ask `PageGlassLanePolicy` whether it already has glass.
  let selectedIndex: Int
  /// The hub page being rendered when `selectedIndex` is the Memory hub's rail index. Nil for every
  /// other destination, whose glass does not depend on a sub-page.
  var memoryDestinationRawValue: Int? = nil
  /// Whether the Home surface selected by the router owns its own glass.
  let homeOwnsItsPanels: Bool
  @ViewBuilder var content: () -> Content

  var body: some View {
    if PageGlassLanePolicy.ownsItsPanels(
      selectedIndex: selectedIndex,
      memoryDestinationRawValue: memoryDestinationRawValue,
      homeOwnsItsPanels: homeOwnsItsPanels)
    {
      // Handed the whole content area, so a modal dim mounted inside it has to take the lane rather
      // than the surface it was given — see `ShellModalScrim`. Published here rather than chosen at
      // each modal, because this is the one place that knows which of the two shapes it just built.
      content()
        .shellModalScrimBounds(.contentArea)
    } else {
      panel
    }
  }

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: PageGlassLaneLayout.cornerRadius, style: .continuous)
  }

  private var panel: some View {
    GeometryReader { proxy in
      content()
        // The page *is* the panel, so its modals fill it edge to edge and stop at its corner.
        .shellModalScrimBounds(.ownSurface)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        // The page scrolls *inside* the panel, so its rows have to stop at the corner. Without this a
        // list paints straight over the squircle and out onto the wallpaper, which is the clipped-view
        // reading a rounded panel is drawn to avoid.
        .clipShape(shape)
        .inkGlassPanel(cornerRadius: PageGlassLaneLayout.cornerRadius, shadow: .ambient)
        .frame(width: PageGlassLaneLayout.laneWidth(for: proxy.size.width))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .padding(.top, PageGlassLaneLayout.topGap)
    .padding(.bottom, PageGlassLaneLayout.bottomGap)
  }
}
