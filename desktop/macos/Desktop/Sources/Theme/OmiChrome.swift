import SwiftUI

package enum OmiChrome {
  package static let windowRadius: CGFloat = 26
  package static let cardRadius: CGFloat = 24
  package static let sectionRadius: CGFloat = 20
  package static let controlRadius: CGFloat = 16
  package static let chipRadius: CGFloat = 14
  /// Small controls: compact buttons, inputs, thumbnails.
  package static let smallControlRadius: CGFloat = 12
  /// Small elements: badges, list chips, inline pills.
  package static let elementRadius: CGFloat = 8
  /// Tags and micro badges.
  package static let badgeRadius: CGFloat = 6
  /// Progress bars, underline indicators, hairline strips.
  package static let stripRadius: CGFloat = 3
}

// `omiPanel` and `omiControlSurface` used to live here, and they are deliberately gone rather than
// recoloured.
//
// Both drew an opaque fill from the hardcoded-dark palette plus a `black.opacity(0.14)` drop
// shadow. That shadow was correct on a near-black page — it read as depth — and on the light glass
// panel it reads as dirt: a grey halo smeared around a card that is already sitting inside the one
// ambient shadow this system owns (`InkGlassShadow.ambient`). A second shadow inside that is a card
// floating above a card.
//
// Recolouring them would have left a second, competing card recipe next to `glassCard` for the next
// screen to pick by accident, so the retired shape is removed instead of aliased. The live
// vocabulary is `glassCard` / `glassRow` / `glassChip` / `glassField` in `GlassContentChrome.swift`
// for content hosted on the panel, and `inkGlassPanel` for a surface that is itself glass. Neither
// draws a drop shadow.
//
// The radii above stay — they are the shared geometry, not the retired recipe.
