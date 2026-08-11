//
//  NotchGlassChrome.swift — the floating bar's half of the glass chrome.
//
//  The rest of the app went light. **This surface deliberately did not**, and that is the single fact
//  this file exists to hold in one place.
//
//  `InkGlass` pins every panel to `.aqua` because a light material with dark type on it is what a
//  window floating over a desktop should be. The floating bar is not that object. It hangs off the
//  physical notch — a black cut-out in the hardware — and the design's answer to "what colour is a
//  panel welded to a black bezel" has been settled since the handoff: the pill is **black glass in
//  both themes** (`SBTheme.pillBackground`, and the comment above it). A light pill draws a white
//  rectangle around the notch and turns the hardware into a visible seam.
//
//  So this is not a second design system, it is `InkGlass` with two values overridden and everything
//  else deferred to. The material, the corner, the edge alpha, the Reduce Transparency behaviour and
//  the ambient shadow all come from there, unrestated; what is overridden is the **appearance the
//  material renders in** and the **scrim painted over it**, because those two are what decide whether
//  the panel is light or dark, and only those two.
//
//  The consequence for type: inside the pill the ink scale is always the white-on-black one
//  (`SBTheme.pillInk`), never `Ink.primary` / `Ink.secondary`. Those are dynamic — they resolve dark
//  on a light-pinned panel — and a run of `Ink.primary` inside the pill is near-black type on near-
//  black glass. `NotchGlass.primary` and friends below are the pill's ladder and the only one that is
//  correct here.
//
//  Brand: neutrals only, no hue anywhere (INV-UI-1).
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - The values

/// The pill's glass, as values rather than as statements inside a view.
///
/// Every decision is a pure function of at most one `Bool`, for the same reason `InkGlass` reduced
/// the surface itself that way: it puts "the pill really is black in both themes" and "Reduce
/// Transparency really produces an opaque pill" inside reach of a hermetic test, and leaves the views
/// with no chrome judgement of their own.
enum NotchGlass {
  // MARK: Ground

  /// The scrim painted over the material — **black glass, in both themes.**
  ///
  /// Read off `SBTheme` rather than restated, so there is exactly one definition of the pill's ground
  /// in the app and it is the one the design handoff owns. Both modes resolve to the same near-black
  /// and differ only in alpha, which is the whole content of "black in both themes"; `.light` is
  /// named here because that is the appearance the app is pinned to.
  static let ground: Color = SBTheme(.light).pillBackground

  /// The same value for either theme, so a test can assert both are black rather than trusting the
  /// one the app happens to ask for.
  static func ground(_ mode: SBThemeMode) -> Color { SBTheme(mode).pillBackground }

  /// The appearance the material renders in, and the **one deliberate divergence from `InkGlass`.**
  ///
  /// `NSVisualEffectView` renders a different material per appearance, and `.hudWindow` in `.aqua` is
  /// a near-white sheet (232/255 — see `InkGlass.measuredMaterialTint`). Under a black scrim that is
  /// a grey slab, not black glass: the scrim would have to go almost opaque to hide it, at which
  /// point the panel stops passing any desktop at all and the blur is decorative. Pinning the
  /// material dark is what lets the scrim stay thin enough to see through.
  static let appearanceName: NSAppearance.Name = .darkAqua

  /// Resolved, for the layers that need the object. `.darkAqua` is system-guaranteed, so the lookup
  /// cannot fail; computed rather than stored because `NSAppearance` is a reference type.
  static var appearance: NSAppearance {
    guard let appearance = NSAppearance(named: appearanceName) else {
      preconditionFailure("NSAppearance(named: .darkAqua) is guaranteed by AppKit")
    }
    return appearance
  }

  /// `InkGlass`'s material, unchanged. There is one material in this app.
  static let material: NSVisualEffectView.Material = InkGlass.material

  /// Whether the blurred material is drawn at all. False under Reduce Transparency, where an opaque
  /// ground sits over it and an unhidden `NSVisualEffectView` would sample the desktop every frame
  /// for nothing.
  static func showsMaterial(reduceTransparency: Bool) -> Bool {
    InkGlass.showsMaterial(reduceTransparency: reduceTransparency)
  }

  /// The pill's ground with no alpha at all.
  ///
  /// **Not `ground.opacity(1)`, and that is the whole reason this exists.** SwiftUI's `opacity`
  /// *multiplies* into the alpha a colour already carries, so asking a 0.85 scrim for opacity 1
  /// returns the same 0.85 scrim — the pill stays see-through with Reduce Transparency switched on,
  /// which is the defect the setting exists for, and nothing at the call site looks wrong. The alpha
  /// is replaced instead of scaled, off the same value, so there is still one definition of the
  /// pill's colour.
  static var solidGround: Color {
    Color(nsColor: NSColor(ground).withAlphaComponent(1))
  }

  /// The ground actually painted, given the setting: the design's translucent scrim normally, and the
  /// same colour fully opaque when the user has asked for no transparency.
  ///
  /// A colour rather than an alpha because the pill's scrim is already an alpha on a named black —
  /// multiplying a second one in is how a surface ends up with two opinions about its own opacity.
  static func opaqueGround(reduceTransparency: Bool) -> Color {
    reduceTransparency ? solidGround : ground
  }

  // MARK: Ink
  //
  // The white-on-black scale, always. See the file header: `Ink.primary` is dynamic and resolves
  // *dark* on this app's pinned-light panels, so it is near-black type on near-black glass here.

  /// A token from the design's white-alpha scale, inside the pill.
  static func ink(_ token: SBInk) -> Color { SBTheme(.light).pillInk(token) }

  /// The pill's headline rung: a title, an active control, the thing being read.
  static let primary: Color = SBTheme(.light).pillInkSolid

  /// A sentence or a secondary control — everything on the pill that is not `primary`.
  static let secondary: Color = SBTheme(.light).pillInk(.w6)

  /// A glance word, and the floor. **The pill is black glass, not the light panel**, so the
  /// two-rungs-on-glass rule (`Ink.tertiary`) does not transfer: that rule is arithmetic about *dark
  /// type on a light ground the desktop shows through*, and this ground is the opposite. Light type
  /// on a near-opaque black scrim keeps its contrast, which is why a third rung is affordable here
  /// and is not on `InkGlass`.
  static let quiet: Color = SBTheme(.light).pillInk(.w45)

  /// The label of something switched off.
  static let disabled: Color = SBTheme(.light).pillInk(.w3)

  // MARK: Edges and fills

  /// The panel's edge. `InkGlass.edgeAlpha`, on white rather than on `labelColor`: the edge of a dark
  /// panel is a *light* line, and the semantic colour would need the environment to be dark to say so
  /// — which makes the edge depend on who hosted the view rather than on what it is.
  static let edge: Color = .white.opacity(InkGlass.edgeAlpha)

  /// A control's fill at rest, under the pointer, and pressed. Monotonic by construction, so the
  /// ladder cannot invert the way it does when each call site picks the token whose name sounds
  /// right.
  static let fill: Color = SBTheme(.light).pillInk(.w08)
  static let fillHover: Color = SBTheme(.light).pillInk(.w12)
  static let fillActive: Color = SBTheme(.light).pillInk(.w18)

  /// A control's fill given its state, so the ordering is a function rather than a nested ternary.
  /// **Active outranks hover**: a control the pointer happens to be over must not dim back to the
  /// lighter wash.
  static func controlFill(isActive: Bool, isHovering: Bool) -> Color {
    if isActive { return fillActive }
    return isHovering ? fillHover : fill
  }

  /// A control's label given the same state, two-valued for the same reason.
  static func controlLabel(isActive: Bool) -> Color {
    isActive ? primary : quiet
  }
}

// MARK: - The material

/// The pill's blurred backdrop: `InkGlass`'s material, pinned dark.
///
/// The ported `NSVisualEffectView` path and never SwiftUI's `Material`, which is *within-window*
/// vibrancy — it would blur the app's own content instead of the desktop, and over a borderless
/// transparent panel there is no app content to blur, so the surface would come out empty.
struct NotchGlassBackdrop: NSViewRepresentable {
  func makeNSView(context: Context) -> NSVisualEffectView {
    let view = NSVisualEffectView()
    view.material = NotchGlass.material
    // `.behindWindow`, so the blur is of the desktop rather than of this panel's own content.
    view.blendingMode = .behindWindow
    // `.active` and not `.followsWindowActiveState`: this panel is a non-activating overlay and is
    // almost never in a key window, and a pill that goes flat grey whenever the user clicks anything
    // else reads as broken.
    view.state = .active
    view.appearance = NotchGlass.appearance
    return view
  }

  func updateNSView(_ view: NSVisualEffectView, context: Context) {}
}

// MARK: - The panel

extension View {
  /// Wears the pill's glass: material, black scrim, corner and faint edge.
  ///
  /// **Apply once**, at the root of a floating-bar surface. A second one stacks a second scrim and
  /// halves the passthrough the first was tuned for, which is what makes a translucent panel read as
  /// muddy over one desktop and opaque over another.
  ///
  /// - Parameters:
  ///   - cornerRadius: the floating bar's surfaces are cut by their own geometry (a docked pill is
  ///     square where it meets the bezel), so unlike `inkGlassPanel` this has no single right answer
  ///     and the caller states it.
  ///   - shadow: `nil` by default, and that is not an oversight. The panel hugs the current surface,
  ///     so there is no spare margin inside its bounds for an ambient shadow to fall into, and the
  ///     surface it would fall onto is the screen bezel. The window's own `hasShadow` stays `false`
  ///     because an AppKit shadow would trace the rectangular panel rather than the pill.
  ///   - reduceTransparency: passed rather than read, for the same reason
  ///     `InkGlassView.apply(reduceTransparency:)` takes it: the setting is a machine setting a
  ///     hermetic test cannot flip, so a view that reads it directly has an accessibility path
  ///     nothing can ever assert.
  func notchGlassPanel(
    cornerRadius: CGFloat,
    shadow: InkGlassShadow? = nil,
    reduceTransparency: Bool = InkReduceTransparency.isEnabled
  ) -> some View {
    let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
    return
      self
      // Forced rather than inherited: the ink inside the pill is the white-on-black scale, and any
      // descendant that reaches for a semantic colour (an `NSTextField`, a `ProgressView`, a system
      // symbol's default tint) has to resolve against a dark ground or it disappears.
      .environment(\.colorScheme, .dark)
      .background {
        ZStack {
          if NotchGlass.showsMaterial(reduceTransparency: reduceTransparency) {
            NotchGlassBackdrop()
          }
          NotchGlass.opaqueGround(reduceTransparency: reduceTransparency)
        }
      }
      // **The clip is on the content, not only on the ground**, and that is load-bearing here in a
      // way it is not for `inkGlassPanel`: the bar's surfaces are a text editor, a scrolling response
      // and a row of controls laid out to the window's full width. Without it a long line runs out
      // through the rounded corner and the pill stops having a shape.
      .clipShape(shape)
      .overlay(shape.strokeBorder(NotchGlass.edge, lineWidth: 1))
      .shadow(
        color: .black.opacity(shadow.map { Double($0.opacity) } ?? 0),
        // SwiftUI's blur radius is half Core Animation's for the same visual spread.
        radius: (shadow?.radius ?? 0) / 2,
        y: -(shadow?.offsetY ?? 0))
  }
}
