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
//  ## The player is deliberately not on the lane
//
//  `contentLaneWidth` is `min(ChatComposerLayout.contentLaneMaxWidth, available − 2·pageMargin)`, and
//  the 900 in it is a **measure**: the width past which a column of reading type stops being readable.
//  The player holds no column of type. It holds a picture that wants the room, and a track that maps a
//  pointer's x to a capture timestamp by binary search (`RewindTrackNSView.instant(atX:)`), so every
//  point taken off its width is resolution taken off the scrub — on a wide window the reading clamp
//  would throw away more than half of it and damage the feature to serve the styling.
//
//  So the player keeps the page's own margin and drops the reading clamp. Below
//  `contentLaneMaxWidth + 2·pageMargin` the two widths are the same number and the two panels share a
//  leading edge exactly (`edgesCoincide`); above it the header stays a bar and the player takes the
//  glass the ruler needs.
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

  /// The player's width: the page's margin, without the reading clamp. See the file header.
  static func playerWidth(for availableWidth: CGFloat) -> CGFloat {
    max(0, availableWidth - ChatComposerLayout.pageMargin * 2)
  }

  /// Whether the two panels share a leading edge at this window width.
  ///
  /// True on any window narrow enough that the reading clamp is not what is binding, which is the
  /// common case and the one the composition is tuned for. A value rather than a remark, so "they
  /// line up until the lane runs out of room" is a claim a test can hold.
  static func edgesCoincide(availableWidth: CGFloat) -> Bool {
    abs(playerWidth(for: availableWidth) - headerWidth(for: availableWidth)) < 0.5
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
