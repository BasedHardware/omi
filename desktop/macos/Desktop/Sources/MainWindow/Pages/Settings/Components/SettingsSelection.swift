//
//  SettingsSelection.swift — how Settings says "this one is chosen" and "this is on".
//
//  Settings used to spend solid `systemBlue` on selection: the sidebar's current row, every switch's
//  on-track, the option tiles, the stepped sliders, the shortcut chips. The rest of the app states
//  the same fact in neutral ink — the top bar's current pill is a heavier `labelColor` wash
//  (`GlassShell.pillFill`), a page's active chip is `PageGlass.chipFill(isActive: true)` — so Settings
//  read as a different app, and the blue it spent on state left nothing for the one actionable link a
//  surface is allowed to colour (`Ink.accent`).
//
//  So selection is neutral here too, and the decisions are values rather than statements inside a
//  view so a hermetic test can hold "selected is not the accent" and "selected is still legible".
//
//  Brand: system semantics and neutrals only (INV-UI-1).
//

import OmiTheme
import SwiftUI

enum SettingsSelection {
  /// A navigation row (the sidebar and its subsections): the shell's pill ladder, so Settings' table
  /// of contents marks its current page exactly the way the top bar marks its current tab.
  static func rowFill(isSelected: Bool, isHovering: Bool) -> Color {
    GlassShell.pillFill(isSelected: isSelected, isHovering: isHovering)
  }

  /// A navigation row's glyph. The selected row's icon steps up to full ink; the text beside it
  /// is always `Ink.primary` and carries selection in its weight.
  static func rowIcon(isSelected: Bool) -> Color {
    isSelected ? Ink.primary : Ink.secondary
  }

  /// A navigation row's label weight. The fill is a wash, so the weight is the second cue that
  /// keeps the selected row distinct from a merely hovered one.
  static func rowWeight(isSelected: Bool) -> Font.Weight {
    isSelected ? .medium : .regular
  }

  /// An option tile, radio row or chip (transcription mode, tier, shortcut choice): the page chip's
  /// active wash.
  static func optionFill(isSelected: Bool) -> Color {
    PageGlass.chipFill(isActive: isSelected)
  }

  /// An option's outline. The chosen option takes the ink itself, because two washes a few percent
  /// apart are not enough on their own to tell "chosen" from "available" on a light panel.
  static func optionStroke(isSelected: Bool) -> Color {
    isSelected ? Ink.primary : Ink.hairline
  }

  /// A radio mark or check glyph beside an option.
  static func optionMark(isSelected: Bool) -> Color {
    isSelected ? Ink.primary : Ink.secondary
  }

  /// The filled part of a slider, and a stepped slider's reached dots: the same ink the switch's
  /// on-track is (`OmiToggleStyle.trackFill(isOn: true)`), so every "how much / is it on" control in
  /// the app draws its value in one colour.
  static let valueFill = Ink.primary

  /// The ground of a value readout chip beside a slider.
  static let readoutFill = PageGlass.chipFill(isActive: true)
}
