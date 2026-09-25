//
//  ShellModalScrim.swift — the modal dim, painted on a surface instead of on the window.
//
//  A modal dim was the last piece of chrome in this shell still drawn at *window* scale, and the
//  window stopped being a thing you can see. `ShellWindowChrome` took the ground away: the shell is a
//  transparent rectangle noticeably larger than the panels floating inside it, so a full-bleed
//  `Color.black.opacity(…).ignoresSafeArea()` no longer dims "the app" — it stamps a hard-edged dark
//  rectangle, in the shape of an invisible window, straight onto the user's wallpaper. It is the same
//  failure as the window shadow `ShellWindowChrome.glassKind` fixed and as the full-bleed ground
//  `PageGlassLane` replaced: **a window-scale paint on a window that has no visible extent.**
//
//  ## A dim still has to do its job
//
//  Deleting it trades a visual bug for a usability one — a modal with nothing behind it does not read
//  as modal, and clicking outside a sheet has to keep dismissing it. So this splits the two things the
//  old scrim did and gives each the scale it actually wants:
//
//  - **Modality is host scale.** An invisible, full-host barrier still swallows every click, still
//    carries the caller's dismiss gesture, and still keeps what is underneath out of reach. That part
//    never had a visible extent to get wrong.
//  - **The paint is surface scale.** What darkens is the shell's own silhouette — the lane the top bar
//    and the page panel share, cut to the one corner every panel in this product is cut to. Its edges
//    are a surface's edges, so it can never read as a rectangle laid over the desktop.
//
//  ## Why the surface tells the dim, and the caller does not
//
//  The same dim is mounted in three different coordinate spaces: over the whole shell
//  (`DesktopHomeView`'s overlays), inside the content area under the top bar (Home and Rewind own
//  their panels, so `PageGlassLanePolicy` hands them that whole surface), and inside a page that is
//  *already* a panel on the lane. Filling the host is right in exactly one of those and catastrophic
//  in the other two; clamping to the lane is right in two and leaves an undimmed 24 pt border of glass
//  in the third.
//
//  The first version of this file made that a parameter at every call site. That is the shape this
//  defect keeps coming back in — one more thing for a caller to get wrong, on the routes nobody looks
//  at, silently. So the **surface publishes what it is** and the dim reads it: `PageGlassLane` already
//  knows whether it wrapped a destination in a panel or handed it the whole area, because that is the
//  one decision it exists to make. A modal mounted anywhere gets the right bounds without being told,
//  a new page inherits it by being a page, and the wiring is one hermetic assertion rather than an
//  audit of every `dismissableSheet` in the app.
//
//  Every number here is delegated: the lane is the top bar's (`TopNavigationLayoutMetrics`), the corner
//  and the gaps are `InkGlass`'s and `PageGlassLaneLayout`'s. Nothing restates a value that already
//  exists, for the reason `PageGlassLane` does not either.
//
//  Brand: `Ink.primary` — `labelColor`, one neutral, never a hue (INV-UI-1).
//

import OmiTheme
import SwiftUI

// MARK: - Which surface the dim belongs to

/// The surface a modal dim darkens.
///
/// Three cases because there are exactly three places a modal is mounted in this shell. It is written
/// into the environment by whoever owns the surface — never chosen at the call site — so the value is
/// a fact about where the modal is, not a judgement someone had to make.
enum ShellModalScrimBounds: Equatable, Sendable, CaseIterable {
  /// Mounted over the whole shell window (`DesktopHomeView`'s overlays), or over any surface that is
  /// not one of the two below. The lane fills the window, so the dim does too — ending at the page
  /// panel's bottom margin so it does not paint the air under the stack.
  ///
  /// The default, and deliberately the *conservative* one: an unknown surface is treated as one whose
  /// edges cannot be trusted, which fails towards a dim that is too small rather than one that paints
  /// on the desktop.
  case wholeShell

  /// Mounted inside the shell's content area, below the top bar: a destination that owns its panels
  /// and is therefore handed the whole surface (Home, Rewind — see `PageGlassLanePolicy`). Same lane,
  /// but the drag band is already above this host.
  case contentArea

  /// Mounted inside a surface that already has its own extent and corner — a page riding on
  /// `PageGlassLane`'s panel. The dim fills that surface exactly, so its edges are the surface's
  /// edges.
  case ownSurface
}

// MARK: - How a surface says what it is

private struct ShellModalScrimBoundsKey: EnvironmentKey {
  static let defaultValue: ShellModalScrimBounds = .wholeShell
}

extension EnvironmentValues {
  /// What the nearest enclosing surface is, for any modal dim mounted inside it.
  ///
  /// Written by `PageGlassLane` and read by `ShellModalScrim`. A view that is not inside one gets
  /// `.wholeShell`, which is correct for the shell's own overlays and safe everywhere else.
  var shellModalScrimBounds: ShellModalScrimBounds {
    get { self[ShellModalScrimBoundsKey.self] }
    set { self[ShellModalScrimBoundsKey.self] = newValue }
  }
}

extension View {
  /// Declares this subtree to be a surface of the given kind, for any modal dim inside it.
  func shellModalScrimBounds(_ bounds: ShellModalScrimBounds) -> some View {
    environment(\.shellModalScrimBounds, bounds)
  }
}

// MARK: - The metrics

/// Where the dim is painted and how dark it is. Every value is delegated or stated once.
enum ShellModalScrimLayout {

  /// The lane the dim takes — the top bar's own, reached the same way `PageGlassLaneLayout` reaches
  /// it, so a dim and the panel under it share a leading edge.
  static func laneWidth(for availableWidth: CGFloat) -> CGFloat {
    TopNavigationLayoutMetrics.contentLaneWidth(for: availableWidth)
  }

  /// The corner is the shared one — never a second opinion about 22.
  static var cornerRadius: CGFloat { InkGlass.cornerRadius }

  /// How wide the dim is painted inside a host of `availableWidth`.
  static func paintedWidth(_ bounds: ShellModalScrimBounds, in availableWidth: CGFloat) -> CGFloat {
    switch bounds {
    case .wholeShell, .contentArea:
      return laneWidth(for: availableWidth)
    case .ownSurface:
      return max(0, availableWidth)
    }
  }

  /// The air the dim leaves above itself inside its host.
  static func topInset(_ bounds: ShellModalScrimBounds) -> CGFloat {
    switch bounds {
    case .wholeShell:
      // The window is flush with the glass; the top bar is the top edge. Zero here lets the dim
      // cover the bar. A leftover title-bar band would leave an undimmed strip above it.
      return GlassShell.titlebarClearance
    case .contentArea:
      return PageGlassLaneLayout.topGap
    case .ownSurface:
      return 0
    }
  }

  /// …and below it.
  static func bottomInset(_ bounds: ShellModalScrimBounds) -> CGFloat {
    switch bounds {
    case .wholeShell, .contentArea:
      return PageGlassLaneLayout.bottomGap
    case .ownSurface:
      return 0
    }
  }

  /// How tall the dim is painted inside a host of `availableHeight`.
  static func paintedHeight(_ bounds: ShellModalScrimBounds, in availableHeight: CGFloat) -> CGFloat {
    max(0, availableHeight - topInset(bounds) - bottomInset(bounds))
  }

  /// **The** modal dim.
  ///
  /// One value where there were six (0.16, 0.18, 0.22, 0.24, 0.28, 0.3, on two different base
  /// colours), which is the drift a shared primitive exists to end: two modals opened from the same
  /// window darkening it by different amounts reads as two products. On `Ink.primary` — `labelColor`,
  /// black at 0.85 in the pinned light appearance — so it composites to roughly a quarter of black,
  /// which is where the old set clustered.
  static let dim: Double = 0.28

  /// A modal the user cannot dismiss — today, only the required-update prompt. Heavier on purpose:
  /// there is no click-outside to discover, so the dim is the whole of the signal that the app behind
  /// it is unavailable.
  static let blocking: Double = 0.72
}

// MARK: - The dim

/// A modal dim: an invisible barrier at the host's full size, and a painted surface that follows
/// the glass rather than the leftover air between panels.
///
/// Use it for every modal dim in the shell. A caller that reaches for a bare
/// `Color.black.opacity(…).ignoresSafeArea()` is drawing a rectangle on the wallpaper.
///
/// It takes no bounds: the enclosing surface publishes that (`\.shellModalScrimBounds`). See this
/// file's header for why that is not a parameter.
struct ShellModalScrim: View {
  /// How dark. `ShellModalScrimLayout.dim` unless the modal has no way out.
  var opacity: Double = ShellModalScrimLayout.dim

  /// Whether the dim swallows clicks. True for a modal; false for a dim that is pure decoration and
  /// must not steal the pointer from the app underneath (the goal celebration).
  var blocksInteraction: Bool = true

  /// What a click on the barrier does, if anything. A modal with no dismiss gesture still blocks.
  var onTap: (() -> Void)?

  @Environment(\.shellModalScrimBounds) private var bounds

  var body: some View {
    GeometryReader { proxy in
      ZStack {
        if blocksInteraction {
          // Modality, at the host's full size — the part that was never wrong to draw host-wide,
          // because it draws nothing. The reporter keeps the transparent barrier inside the
          // window's pointer ownership: without it, the shell's click-through sync would pass
          // clicks on the barrier straight to whatever is behind the window (see
          // `ShellClickThrough.swift`), and the modal would stop being modal.
          Color.clear
            .contentShape(Rectangle())
            .onTapGesture { onTap?() }
            .background(InkGlassHitRegionReporter())
            // Modality for the keyboard too: a stray key over the modal must not start a search in
            // the bar behind it (`StrayTypingRouter`).
            .straysTypingBlocked()
        }

        RoundedRectangle(cornerRadius: ShellModalScrimLayout.cornerRadius, style: .continuous)
          .fill(Ink.primary.opacity(opacity))
          .frame(
            width: ShellModalScrimLayout.paintedWidth(bounds, in: proxy.size.width),
            height: ShellModalScrimLayout.paintedHeight(bounds, in: proxy.size.height)
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
          .padding(.top, ShellModalScrimLayout.topInset(bounds))
          .padding(.bottom, ShellModalScrimLayout.bottomInset(bounds))
          // The barrier above owns the clicks; a second hit-testing layer would eat the caller's
          // dismiss gesture on exactly the region the dim covers.
          .allowsHitTesting(false)
      }
    }
  }
}
