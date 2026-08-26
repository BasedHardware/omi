import SwiftUI

/// The app's single button primitive, in the glass system's vocabulary.
///
/// It renders what `InkButtonStyle` renders — the same stadium, the same inverted label ladder, the
/// same press feedback — and shares its metrics rather than restating them. It exists beside that
/// primitive only because the app's call sites need a `Kind × Size` matrix the onboarding button has
/// no vocabulary for: a `.compact` size for settings rows, and a `.destructive` kind.
///
/// **Primary is deliberately not accent-filled**, for the reason spelled out on `InkButtonStyle`: the
/// accent is already spent on the one link that needs it, and a filled accent button owes a label
/// colour legible on it in both appearances — one more contrast pair to keep true. Inverting the
/// label ladder (`Ink.primary` fill, `Ink.surface` label) is high-contrast by construction.
///
/// Every colour below is an `Ink` token, which is the whole point of the file: it is the one place
/// that decides how ~80 buttons across the app look, so a palette that is legible here is legible
/// everywhere, and one that is not is invisible everywhere.
package struct OmiButtonStyle: ButtonStyle {
  package enum Kind: Equatable, CaseIterable, Sendable {
    /// `Ink.primary` fill, `Ink.surface` label — the label ladder inverted.
    case primary
    /// Clear fill, `Ink.primary` label, 1 pt `Ink.hairline`.
    case secondary
    /// `Ink.errorRed` fill, `Ink.surface` label — the one place this app raises its voice.
    case destructive
  }

  package enum Size: Equatable, CaseIterable, Sendable {
    case regular
    case compact
  }

  let kind: Kind
  let size: Size

  package init(_ kind: Kind = .primary, size: Size = .regular) {
    self.kind = kind
    self.size = size
  }

  // MARK: - The decisions, as pure functions
  //
  // `nonisolated` for the same reason `InkButtonStyle.minHeight` is: `ButtonStyle` is `@MainActor`,
  // and these are values a caller may want to read while measuring or asserting rather than draw
  // with. Stating them here rather than inside the body is what lets "the primary button's label is
  // the surface, not the primary" be a claim a test can hold without a window server.

  /// Disabled is its own small palette, and it did not used to be.
  ///
  /// It was one `opacity(0.45)` over the whole control, on the argument that a greyed fill and a
  /// greyed label are two more contrast pairs to keep true and neither says anything the dimming
  /// does not. On the dark palette that held. On the light-pinned glass it does not, and the reason
  /// is arithmetic rather than taste: **dimming composites the fill and the label toward the same
  /// panel, so the pair converges.** A disabled `.primary` — black capsule, white label — lands its
  /// label at 3.4:1 on its own fill, under the 4.5:1 a 13 pt label needs; a disabled `.destructive`
  /// lands at 1.9:1; and `.secondary` has no fill of its own, so it dims to grey type behind a
  /// 0.10-alpha outline. Seen live on Settings → About → "Check Now": a grey pill with grey words
  /// on it, which is not a button that is off, it is a smudge.
  ///
  /// So the two pairs are named here and measured in `GlassButtonPrimitiveTests` rather than left
  /// implicit in an alpha:
  ///
  /// - a **fill** faint enough to read as inert but distinct from the card under it,
  /// - an **outline**, so the control keeps its shape — that is the part that still says "button",
  /// - a **label** on the rung that carries sentences, so the words are still words.
  ///
  /// One neutral for every kind, deliberately: a dimmed red still reads as a warning and a dimmed
  /// black still reads as the live primary, and a disabled control should say neither.
  nonisolated package static let disabledFill = Ink.primary.opacity(0.10)
  nonisolated package static let disabledLabel = Ink.secondary
  nonisolated package static let disabledBorder = Ink.hairline

  /// Pressed drops opacity rather than darkening: letting the surface through is the only direction
  /// that reads as give in both appearances.
  nonisolated package static let pressedFillOpacity: Double = 0.82

  nonisolated package static func fill(_ kind: Kind, pressed: Bool) -> Color {
    switch kind {
    case .primary:
      return pressed ? Ink.primary.opacity(pressedFillOpacity) : Ink.primary
    // The button with no fill of its own takes the shared pressed wash instead of thinning to
    // nothing — there is nothing to thin.
    case .secondary:
      return pressed ? Ink.wash : Color.clear
    case .destructive:
      return pressed ? Ink.errorRed.opacity(pressedFillOpacity) : Ink.errorRed
    }
  }

  /// The label, which is the ladder *inverted* on anything filled and upright on anything not.
  nonisolated package static func label(_ kind: Kind) -> Color {
    switch kind {
    case .primary, .destructive: return Ink.surface
    case .secondary: return Ink.primary
    }
  }

  /// Only the button with no fill of its own is outlined; on a filled one the border is a second
  /// edge drawn over the first. `Ink.hairline` and not `Ink.separator` — this is the outline of a
  /// control, which is a different job from a rule between blocks.
  nonisolated package static func border(_ kind: Kind) -> Color {
    switch kind {
    case .secondary: return Ink.hairline
    case .primary, .destructive: return Color.clear
    }
  }

  /// The regular size is `InkButtonStyle`'s, referenced rather than repeated so the two primitives
  /// cannot disagree about how tall a button in this app is.
  nonisolated package static func minHeight(_ size: Size) -> CGFloat {
    switch size {
    case .regular: return InkButtonStyle.minHeight
    case .compact: return 30
    }
  }

  nonisolated package static func horizontalPadding(_ size: Size) -> CGFloat {
    switch size {
    case .regular: return InkButtonStyle.horizontalPadding
    // A stadium needs more side room than the rounded rectangle this replaced, or the label runs
    // into the curve.
    case .compact: return OmiSpacing.lg
    }
  }

  private var fontSize: CGFloat {
    size == .regular ? OmiType.subheading : OmiType.body
  }

  package func makeBody(configuration: Configuration) -> some View {
    OmiButtonContent(
      configuration: configuration,
      kind: kind,
      size: size,
      fontSize: fontSize
    )
  }
}

/// Extracted body so it can read `@Environment(\.isEnabled)` — `ButtonStyle`
/// configurations do not expose enabled state directly.
private struct OmiButtonContent: View {
  let configuration: ButtonStyle.Configuration
  let kind: OmiButtonStyle.Kind
  let size: OmiButtonStyle.Size
  let fontSize: CGFloat

  @Environment(\.isEnabled) private var isEnabled

  private var pressed: Bool { configuration.isPressed }

  private var shape: Capsule { Capsule(style: .continuous) }

  var body: some View {
    configuration.label
      .scaledFont(size: fontSize, weight: .semibold)
      .foregroundStyle(isEnabled ? OmiButtonStyle.label(kind) : OmiButtonStyle.disabledLabel)
      .padding(.horizontal, OmiButtonStyle.horizontalPadding(size))
      // Vertical padding *and* a minimum height: the height is what a one-line label gets, the
      // padding is what keeps a wrapping one off the stadium's edge.
      .padding(.vertical, OmiSpacing.xs)
      .frame(minHeight: OmiButtonStyle.minHeight(size))
      .background(
        shape.fill(
          isEnabled ? OmiButtonStyle.fill(kind, pressed: pressed) : OmiButtonStyle.disabledFill)
      )
      .overlay(
        shape.strokeBorder(
          isEnabled ? OmiButtonStyle.border(kind) : OmiButtonStyle.disabledBorder, lineWidth: 1)
      )
      .contentShape(shape)
      // Colour only, no scale: a pill this size bouncing reads as a toy.
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: pressed)
  }
}
