//
//  GlassShellChrome.swift — the *shell's* half of the glass chrome.
//
//  Two files own the app's glass vocabulary and the split between them is deliberate:
//
//  - `Components/GlassContentChrome.swift` owns what a **page hosted inside the panel** may draw on
//    it: the card, the row, the chip, the field, the scroll fade. Every one of those is a wash on the
//    ground rather than a surface of its own.
//  - **This file owns the ground itself**, plus the two controls only the shell has: the window's
//    glass, the clearance the hidden title bar demands, and the nav pill / icon button the top bar
//    and the sidebar are built out of.
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
  /// The style the window's ground wears.
  ///
  /// `fullBleed` and not `floating`: this is an ordinary titled window, whose frame already owns the
  /// corner and the shadow (`WindowGlass.drawsSystemShadow`). Naming the style rather than passing
  /// `0` and `nil` at the call site is what makes "exactly one shadow per window, never zero and
  /// never two" a claim a test can hold.
  static let groundStyle: InkGlassStyle = .fullBleed

  /// Vertical clearance the content keeps under a hidden title bar.
  ///
  /// `.hiddenTitleBar` gives the window `fullSizeContentView`, which puts the traffic lights *over*
  /// the content view. 32 pt is the height AppKit adds to a content rect to make a titled window's
  /// frame rect, which is exactly the band the lights sit in — a **measurement**, checked against
  /// `NSWindow.frameRect(forContentRect:styleMask:)` by `ShellGlassChromeTests`, so the guard fails
  /// rather than the layout if a future macOS changes it. Content that starts above this line is
  /// content with three coloured circles punched through it.
  ///
  /// It is a *reserved band* and not a leading inset: the top bar centres its lane, so a leading
  /// inset moves the whole bar off centre and still collides at the minimum window width.
  ///
  /// A stored constant rather than the live measurement because `NSWindow.frameRect` is main-actor
  /// isolated and this is read while laying out — the test does the asking.
  static let titlebarClearance: CGFloat = 32

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

// MARK: - The ground

extension View {
  /// The window's whole ground: material, scrim and the light pin, edge to edge.
  ///
  /// **Apply this once**, at the root of a window's content. A second one stacks a second scrim and
  /// halves the passthrough the first was tuned for, which is what makes a translucent surface read
  /// as muddy over one desktop and opaque over another.
  ///
  /// It is the AppKit `.hudWindow` material blending `.behindWindow`, never SwiftUI's `Material` —
  /// that is within-window vibrancy and would frost the app's own content instead of the desktop.
  func glassShellGround() -> some View {
    inkGlassPanel(
      cornerRadius: GlassShell.groundStyle.cornerRadius,
      shadow: GlassShell.groundStyle.shadow)
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
