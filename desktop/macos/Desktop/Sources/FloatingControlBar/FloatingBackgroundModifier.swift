import OmiTheme
import SwiftUI

/// The floating bar's ground.
///
/// It used to build its own translucent surface here — its own material, its own alpha, its own scrim
/// and its own border — which is the "two grounds" failure `InkGlass` exists to stop: four numbers
/// that have to agree, kept in a file that says nothing about the three other surfaces they have to
/// agree *with*. It draws the same pill it always did, but every value now comes from
/// `NotchGlassChrome`, which defers to `InkGlass` for all of them except the two that make this
/// surface black (see that file's header).
///
/// The border in particular was `Color.black.opacity(0.5)` — a *dark* line around a dark panel, which
/// reads as a gap rather than as an edge. `NotchGlass.edge` is the same faint light line every other
/// panel in the app is outlined with.
struct FloatingBackgroundModifier: ViewModifier {
  let cornerRadius: CGFloat
  @ObservedObject private var settings = ShortcutSettings.shared
  @ObservedObject private var reduceTransparency = InkReduceTransparencyObserver.shared

  func body(content: Content) -> some View {
    // The user's own opt-out, honoured through the same seam Reduce Transparency uses rather than as
    // a second background branch: "solid" and "the accessibility setting is on" are the same request.
    content.notchGlassPanel(
      cornerRadius: cornerRadius,
      reduceTransparency: settings.solidBackground || reduceTransparency.isEnabled)
  }
}

extension View {
  /// Wears the pill's glass.
  ///
  /// **Apply it to the surface, never to the card that happens to be on it**, and that is not style
  /// advice — it is the difference between a legible card and an invisible one. The floating bar has
  /// two presentations, and only one of them brings its own ground: docked to the notch, every card
  /// sits on `unifiedFloatingSurface`'s black dock shape, so a card needs nothing. Undocked, a
  /// notification is a bare sibling of the pill in a `VStack` with no shared ground at all — whatever
  /// it does not paint itself, the desktop paints.
  ///
  /// A card that grounds *itself* therefore only looks right until someone adds a second kind of
  /// card. That is exactly what happened: of the five branches `barNotification` dispatches to, one
  /// carried this modifier and four did not, so the receipt, the reach error, the end card and the
  /// suggestion each rendered white-on-white over the desktop in pill mode — measured at 205 on 192,
  /// a contrast ratio of about 1.1:1. The ground now goes on at the one call site that knows which
  /// presentation is on screen, so a sixth card cannot be born without one.
  func floatingBackground(cornerRadius: CGFloat = OmiChrome.sectionRadius) -> some View {
    modifier(FloatingBackgroundModifier(cornerRadius: cornerRadius))
  }
}

/// Simple spinning loader for the floating bar.
struct FloatingLoadingSpinner: View {
  @State private var isSpinning = false

  var body: some View {
    Circle()
      .trim(from: 0.1, to: 0.9)
      .stroke(NotchGlass.primary, lineWidth: 2)
      .rotationEffect(.degrees(isSpinning ? 360 : 0))
      .onAppear { isSpinning = true }
      .omiAnimation(
        .linear(duration: 1).repeatForever(autoreverses: false),
        value: isSpinning
      )
  }
}
