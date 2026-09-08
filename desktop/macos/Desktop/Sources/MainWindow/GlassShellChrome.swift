//
//  GlassShellChrome.swift — the *shell's* half of the glass chrome.
//
//  Two files own the app's glass vocabulary and the split between them is deliberate:
//
//  - `Components/GlassContentChrome.swift` owns what a **page hosted inside the panel** may draw on
//    it: the card, the row, the chip, the field, the scroll fade. Every one of those is a wash on the
//    ground rather than a surface of its own.
//  - **This file owns the shell's own terms** — window-specific clearance, plus the
//    nav pill / icon button the top bar and the sidebar are built out of. The window itself has no
//    ground at all: `ShellWindowChrome` makes it transparent and every surface grounds itself, so what
//    is behind a panel is the user's wallpaper. See that file.
//
//  Nothing here restates a number from `InkGlass` — the material, the scrim, the 22 pt corner and the
//  ambient shadow live there and are reached through `inkGlassPanel`. What is here is the handful of
//  facts about *this window* a design system cannot know.
//
//  The decisions are pure functions of state rather than statements inside a view, for the same
//  reason `InkGlass` reduced the surface itself to functions of one `Bool`: it puts "the shell really
//  has one ground and one shadow" and "a selected pill really outranks a hovered one" inside reach of
//  a hermetic test, and leaves each view with no chrome judgement of its own.
//
//  Brand: system semantics and neutrals only, straight off `Ink` (INV-UI-1).
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - The decisions

/// The shell's own numbers and state colours.
enum GlassShell {
  /// Vertical clearance the content keeps under a hidden title bar.
  ///
  /// Zero: the top bar is drawn in that band (`fullSizeContentView` + a transparent
  /// title bar), so the window's top edge is the nav bar's top edge. Drag lives on
  /// the visible top bar (`ShellWindowDragHandle`).
  static let titlebarClearance: CGFloat = 0

  /// A pill of shell chrome: nothing at rest, a wash under the pointer, the heavier wash when
  /// selected.
  ///
  /// **Selected outranks hover.** A selected pill the pointer happens to be over must not dim back to
  /// the lighter wash, which is what the naive `isHovering ? hover : (isSelected ? selected : rest)`
  /// ordering does and is the single most common way a nav bar loses its current item.
  ///
  /// Every branch is a wash — an alpha on `labelColor` — and never a rung of the type ladder. On
  /// glass the ladder has two rungs and both of them are *type*; a fill borrowed from it is an opaque
  /// slab on a surface the whole design is about seeing through.
  static func pillFill(isSelected: Bool, isHovering: Bool) -> Color {
    if isSelected { return Ink.rowFillHover }
    return isHovering ? Ink.rowFill : .clear
  }

  /// An icon button's fill. Pressed outranks active outranks hover, for the same reason.
  ///
  /// The washes are picked so the ladder is **monotonic**: rest 0 → hover `rowFill` (0.045) →
  /// active `wash` (0.06) → pressed `rowFillHover` (0.085). Reaching for the token whose *name*
  /// sounds right rather than checking its alpha is how the first version of this made a merely
  /// hovered button heavier than the current one.
  static func iconButtonFill(isPressed: Bool, isActive: Bool, isHovering: Bool) -> Color {
    if isPressed { return Ink.rowFillHover }
    if isActive { return Ink.wash }
    return isHovering ? Ink.rowFill : .clear
  }

  /// A control's label: the ink when it is current or under the pointer, the reading rung otherwise.
  /// Two rungs, because this is glass — see `Ink.tertiary`.
  static func controlLabel(isProminent: Bool) -> Color {
    isProminent ? Ink.primary : Ink.secondary
  }
}

// MARK: - Shell controls

/// The background of a pill of shell chrome — a nav item, a segment, a toolbar toggle.
///
/// A full continuous capsule, and feedback is colour only: the shape never scales. A row of pills
/// that bounce under the pointer reads as a toy, and on a translucent panel a scaling capsule also
/// drags its own wash across the desktop behind it.
struct GlassPillBackground: View {
  var isSelected: Bool
  var isHovering: Bool

  var body: some View {
    Capsule(style: .continuous)
      .fill(GlassShell.pillFill(isSelected: isSelected, isHovering: isHovering))
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isSelected)
  }
}

/// The shell's icon button: a circular target, no fill at rest, colour-only feedback.
struct GlassIconButtonStyle: ButtonStyle {
  var isActive: Bool = false
  var diameter: CGFloat = 32

  func makeBody(configuration: Configuration) -> some View {
    Chrome(configuration: configuration, isActive: isActive, diameter: diameter)
  }

  /// A nested view rather than an inline body: `@State` is only tracked inside a `View`, so a hover
  /// flag written in `makeBody` would never redraw anything.
  private struct Chrome: View {
    let configuration: Configuration
    let isActive: Bool
    let diameter: CGFloat
    @State private var isHovering = false

    var body: some View {
      configuration.label
        .foregroundStyle(GlassShell.controlLabel(isProminent: isActive || isHovering))
        .frame(width: diameter, height: diameter)
        .background(
          Circle().fill(
            GlassShell.iconButtonFill(
              isPressed: configuration.isPressed, isActive: isActive, isHovering: isHovering))
        )
        .contentShape(Circle())
        .onHover { isHovering = $0 }
        .animation(
          InkReduceMotion.animation(.easeOut(duration: InkMotion.press)),
          value: isHovering
        )
        .animation(
          InkReduceMotion.animation(.easeOut(duration: InkMotion.press)),
          value: configuration.isPressed)
    }
  }
}
