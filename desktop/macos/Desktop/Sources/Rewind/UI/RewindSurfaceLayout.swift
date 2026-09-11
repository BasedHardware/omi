//
//  RewindSurfaceLayout.swift — the glass Rewind's timeline stands on, and where its edges are.
//
//  The main window has no ground: `OmiApp` wears the glass and installs nothing behind it, so what is
//  under a surface is the user's wallpaper. `PageGlassLane` gives every other destination one
//  lane-width panel and passes Rewind through untouched, on the belief that Rewind already owned its
//  panels. It owns them in **search** — the results are their own sheet of glass
//  (`SearchResultsFilmstrip`) — and in **timeline** mode it owned none at all: the title, the query
//  field, the gear, the toggle, the date pill and the whole scrubber were drawn straight onto the
//  desktop, with only the screenshot carrying anything you could call a surface.
//
//  ## Two objects, and neither of them is "the page"
//
//  A **header** — what this page is, the field you type into, and the two switches — is a readable bar,
//  and it takes the same lane every other route's panel takes
//  (`TopNavigationLayoutMetrics.contentLaneWidth`). If it did not, the leading edge under the
//  navigation would move the moment you arrived here, which is the one thing a shared top bar cannot
//  survive.
//
//  Everything under it is a **player**: a photograph of one moment, and the ruler that chooses which
//  moment. Those are not two objects with air between them — the picture *is* the ruler's current
//  value — so they are welded onto one surface. A `panelGap` between a picture and its own scrubber
//  would say the scrubber belongs to something else.
//
//  ## One lane, all the way down
//
//  The player used to drop the reading clamp on wide windows to give the scrubber more pixels. That
//  made Rewind the only destination whose lower glass moved past the shared top-bar edge, and the
//  result looked like a second, unrelated window. The timeline is still fully usable at the shared
//  lane width, so every Rewind panel now uses the same readable lane as the navigation and query bar.
//
//  Brand: nothing here picks a colour at all — the surface is `InkGlass`'s (INV-UI-1).
//

import OmiTheme
import SwiftUI

// MARK: - The metrics

/// Where Rewind's two objects sit and how wide they are. Every value is delegated.
enum RewindSurfaceLayout {

  /// The air between the two objects, and between the query bar and the results in search mode.
  ///
  /// Taken from `RewindSearchLayout`, which introduced this surface's vocabulary, rather than restated
  /// as a second 12 — the same delegation `QueryShellLayout.panelGap` makes, for the same reason: one
  /// product may only hold one opinion about how far apart its glass sits.
  static var panelGap: CGFloat { RewindSearchLayout.panelGap }

  /// The corner is the shared one — never a second opinion about 22.
  static var panelCornerRadius: CGFloat { RewindSearchLayout.panelCornerRadius }

  /// The air above the first panel, and the margin under the last. `PageGlassLane`'s, so Rewind opens
  /// at the same distance below the top bar as every destination beside it and closes the same
  /// distance above the window's bottom edge.
  static var topGap: CGFloat { PageGlassLaneLayout.topGap }
  static var bottomGap: CGFloat { PageGlassLaneLayout.bottomGap }

  /// The header's lane — **the top bar's own**, reached through the same call `PageGlassLane` and
  /// Home make so the three cannot drift apart.
  static func headerWidth(for availableWidth: CGFloat) -> CGFloat {
    TopNavigationLayoutMetrics.contentLaneWidth(for: availableWidth)
  }

  /// The player's width: the same lane as the header and every other destination.
  static func playerWidth(for availableWidth: CGFloat) -> CGFloat {
    headerWidth(for: availableWidth)
  }

  /// Whether the two panels share a leading edge at this window width.
  static func edgesCoincide(availableWidth: CGFloat) -> Bool {
    abs(playerWidth(for: availableWidth) - headerWidth(for: availableWidth)) < 0.5
  }
}

// MARK: - Where the photograph actually lands

/// The stage inside the player panel, and where a picture of a given shape lands on it.
///
/// **The fit is a value rather than arithmetic inside a `body`** so the behaviour is a test rather
/// than a screenshot: at any aspect ratio the picture keeps its shape, stays inside the stage, sits
/// centred, and touches the edge that binds it. `RewindPage` asks it for the picture's display size;
/// the controls that belong to the picture are not overlaid on it any more — they sit in
/// `RewindStageControlBar` on the glass beneath it — so nothing else needs the picture's rect.
enum RewindStageFit {

  /// The air between the player panel's edge and the photograph's stage. The picture is a picture,
  /// not a full-bleed background, so it keeps a margin on the glass it sits on.
  static let horizontalInset: CGFloat = 18
  static let verticalInset: CGFloat = 12

  /// Where a picture of `image` lands inside `container` — aspect-fit and centred.
  ///
  /// Empty on any degenerate input, positioned at the container's centre rather than its origin, so
  /// a caller that reads the rect before the first image decodes gets "nothing, in the middle"
  /// rather than "nothing, in the top-left corner".
  static func pictureRect(image: CGSize, in container: CGSize) -> CGRect {
    guard image.width > 0, image.height > 0, container.width > 0, container.height > 0 else {
      return CGRect(x: container.width / 2, y: container.height / 2, width: 0, height: 0)
    }

    let imageAspect = image.width / image.height
    let containerAspect = container.width / container.height

    // Relatively wider than its container binds on width; anything else binds on height. `min`
    // against the container absorbs the float error that would otherwise put a picture a hundredth
    // of a point outside the glass it is meant to sit on.
    let fitted: CGSize =
      imageAspect > containerAspect
      ? CGSize(width: container.width, height: container.width / imageAspect)
      : CGSize(width: container.height * imageAspect, height: container.height)
    let width = min(fitted.width, container.width)
    let height = min(fitted.height, container.height)

    return CGRect(
      x: (container.width - width) / 2,
      y: (container.height - height) / 2,
      width: width,
      height: height)
  }
}

// MARK: - The panels

extension View {
  /// Rewind's header, on the app's one glass and on the shared lane.
  ///
  /// Clipped to the corner before the glass goes on: the recovery banner is a full-bleed warning
  /// wash, and an unclipped background paints straight over the squircle and out onto the wallpaper.
  func rewindHeaderPanel(width: CGFloat) -> some View {
    rewindGlassPanel(width: width, fillsHeight: false)
  }

  /// Rewind's player — the stage and the track as one object — with the gap that keeps it and the
  /// header reading as two.
  ///
  /// It fills the height it is offered because the picture does: a stage sized to its content would
  /// leave the track floating in the middle of the window on a tall display.
  func rewindPlayerPanel(width: CGFloat) -> some View {
    rewindGlassPanel(width: width, fillsHeight: true)
      .padding(.top, RewindSurfaceLayout.panelGap)
  }

  private func rewindGlassPanel(width: CGFloat, fillsHeight: Bool) -> some View {
    let shape = RoundedRectangle(
      cornerRadius: RewindSurfaceLayout.panelCornerRadius, style: .continuous)
    return
      self
      .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : nil)
      .frame(width: width)
      .clipShape(shape)
      .inkGlassPanel(cornerRadius: RewindSurfaceLayout.panelCornerRadius, shadow: .ambient)
      // Centred in whatever room is left, so a header narrower than the player still sits on the same
      // axis as the navigation above it.
      .frame(maxWidth: .infinity)
  }
}
