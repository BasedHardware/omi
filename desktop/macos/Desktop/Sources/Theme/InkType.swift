//
//  InkType.swift — the glass design system's type: faces, roles, tracking, leading.
//
//  Split out of `Ink.swift` so neither file approaches the repository's 1,500-line source ratchet;
//  `Ink` still owns the colour, layout and motion vocabulary these roles are used with.
//
//  **Open Runde above the display threshold, SF Pro below it.** One threshold —
//  `Font.inkDisplayThreshold` (22 pt) — decides which, because the split is a fact about the role and
//  every role already encodes its role in its size. A headline is never 15 pt here and body copy is
//  never 24. Nothing takes a flag at a call site.
//
//  Open Runde is a geometric sans with rounded terminals: distinctive, and ours rather than borrowed.
//  Reading type stays SF Pro, which is what a native macOS app should be setting body copy in anyway,
//  and which is also where a bundled face buys least.
//
//  The faces ship at `Sources/Resources/Fonts/OpenRunde-{Regular,Medium,Semibold,Bold}.otf` in the
//  executable target's resource bundle and are registered at launch by `OmiFontRegistration`. They are
//  **OpenType/CFF**, not TrueType: a registrar that sweeps only `.ttf` silently drops every face.
//
//  Faces resolve by **PostScript name** — `OpenRunde-Regular`, `OpenRunde-Medium`,
//  `OpenRunde-Semibold` (lowercase `b`), `OpenRunde-Bold` — because the family + weight route does not
//  dependably reach them. A name that does not resolve fails silently, so `InkFonts.resolve` returns
//  the SF Pro font **and** SF Pro's metrics together: the drawn face and the measured face can never
//  disagree.
//

import AppKit
import SwiftUI

// MARK: - Font resolution

/// The four bundled Open Runde faces. One family carries display, body and label.
package enum RundeWeight: Sendable {
  case regular, medium, semiBold, bold

  /// PostScript names of the bundled faces. Note the lowercase `b` in `Semibold`: it is the name
  /// inside the `.otf`, and the family/weight route would not find it — the PostScript name is the
  /// only reliable handle.
  package var fontName: String {
    switch self {
    case .regular: return "OpenRunde-Regular"
    case .medium: return "OpenRunde-Medium"
    case .semiBold: return "OpenRunde-Semibold"
    case .bold: return "OpenRunde-Bold"
    }
  }

  package var swiftUIWeight: Font.Weight {
    switch self {
    case .regular: return .regular
    case .medium: return .medium
    case .semiBold: return .semibold
    case .bold: return .bold
    }
  }

  package var appKitWeight: NSFont.Weight {
    switch self {
    case .regular: return .regular
    case .medium: return .medium
    case .semiBold: return .semibold
    case .bold: return .bold
    }
  }
}

/// Looks up a bundled face, falls back to the matching system font, and caches both the SwiftUI font
/// and its AppKit metrics (needed to turn a line-height multiple into `.lineSpacing`).
package enum InkFonts {
  /// The drawn face and the measured face, produced together and from the same decision. `NSFont` is
  /// not `Sendable`, so this value deliberately is not either — it never crosses an isolation domain.
  package struct Resolved {
    package let font: Font
    package let metrics: NSFont
    /// False when the bundled face was missing and a system font stood in. A missing font file must
    /// degrade, never crash — the app is still usable in San Francisco.
    package let isCustom: Bool

    fileprivate init(font: Font, metrics: NSFont, isCustom: Bool) {
      self.font = font
      self.metrics = metrics
      self.isCustom = isCustom
    }
  }

  private struct Key: Hashable {
    let name: String
    let size: CGFloat
  }

  private static let lock = NSLock()
  // Guarded by `lock`, which is why the compiler's check is opted out of rather than satisfied: the
  // value type carries an `NSFont` and cannot be `Sendable`.
  nonisolated(unsafe) private static var cache: [Key: Resolved] = [:]

  /// The app shell registers the bundled faces before any view renders, so this is normally
  /// unnecessary. If a font ever resolves ahead of registration, calling this afterwards drops the
  /// system-font stand-ins that got cached.
  package static func invalidate() {
    lock.lock()
    cache.removeAll()
    lock.unlock()
  }

  /// True when every bundled face resolved. Useful in a diagnostic line; never gate UI on it.
  package static var bundledFacesAvailable: Bool {
    let names = [RundeWeight.regular, .medium, .semiBold, .bold].map(\.fontName)
    return names.allSatisfy { NSFont(name: $0, size: 12) != nil }
  }

  package static func resolve(
    _ name: String,
    size: CGFloat,
    weight: Font.Weight,
    appKitWeight: NSFont.Weight
  ) -> Resolved {
    let key = Key(name: name, size: size)
    lock.lock()
    let cached = cache[key]
    lock.unlock()
    if let cached { return cached }

    let resolved: Resolved
    if let custom = NSFont(name: name, size: size) {
      // `fixedSize:` and not `size:` — these are fixed-metric design roles, not body text that should
      // ride Dynamic Type.
      resolved = Resolved(font: .custom(name, fixedSize: size), metrics: custom, isCustom: true)
    } else {
      resolved = Resolved(
        font: .system(size: size, weight: weight),
        metrics: NSFont.systemFont(ofSize: size, weight: appKitWeight),
        isCustom: false
      )
    }

    lock.lock()
    cache[key] = resolved
    lock.unlock()
    return resolved
  }

  /// The line box a font draws by default, which is what `.lineSpacing` adds to.
  package static func naturalLineHeight(_ font: NSFont) -> CGFloat {
    font.ascender - font.descender + font.leading
  }

  /// The pairing every role resolves through: Open Runde for display, SF Pro for reading.
  ///
  /// Drawn face and measured face are produced together and from the same decision, because the two
  /// must never disagree — a headline whose line spacing was computed from a different face is the kind
  /// of bug that looks like bad taste rather than like a defect. `resolve` guarantees that: when the
  /// bundled face is missing it returns the SF Pro font *and* SF Pro's metrics.
  package static func role(size: CGFloat, weight: RundeWeight) -> Resolved {
    guard size >= Font.inkDisplayThreshold else {
      return Resolved(
        font: .system(size: size, weight: weight.swiftUIWeight),
        metrics: NSFont.systemFont(ofSize: size, weight: weight.appKitWeight),
        isCustom: false)
    }
    return resolve(
      weight.fontName,
      size: size,
      weight: weight.swiftUIWeight,
      appKitWeight: weight.appKitWeight)
  }
}

extension Font {
  /// The size at or above which a run of text is display type rather than reading type.
  ///
  /// One threshold rather than a flag on every call site: the split is a fact about the role, and every
  /// role in this system already encodes its role in its size.
  package static let inkDisplayThreshold: CGFloat = 22

  /// The glass system's pairing: bundled Open Runde at display size, SF Pro for reading.
  ///
  /// Goes through `InkFonts` rather than naming `.custom` directly, so an unregistered face falls back
  /// to SF Pro at the same size and weight instead of resolving to whatever SwiftUI picks for a font
  /// name it cannot find.
  package static func openRunde(_ size: CGFloat, _ weight: RundeWeight = .regular) -> Font {
    InkFonts.role(size: size, weight: weight).font
  }
}

// MARK: - Type roles

/// A complete type role: face, size, tracking and leading travelling together so none of them can be
/// dropped at a call site.
package struct InkTextStyle: Sendable {
  /// Point size, before tracking or leading.
  package let size: CGFloat
  package let font: Font
  /// `.tracking` in points; 0 when the role has none. The scale states tracking in `em`, so each role
  /// below carries the em value it was converted from.
  package let tracking: CGFloat
  /// Target line box as a multiple of `size`; nil when the role uses the face's natural leading.
  package let lineHeightMultiple: CGFloat?
  /// Extra leading that lands the line box on `lineHeightMultiple`.
  ///
  /// Clamped at zero: `NSParagraphStyle.lineSpacing` is defined as non-negative, so a multiple
  /// *tighter* than the face's own leading (the 1.10 hero, the 1.18 step headline) cannot be expressed
  /// with `.lineSpacing` and renders at the face's natural leading instead.
  package let lineSpacing: CGFloat
  /// False when the bundled face was missing for this role.
  package let usesBundledFace: Bool
  /// The line box the face draws by default.
  package let naturalLineHeight: CGFloat

  /// The exact line box the scale asks for, or the face's own when the role has no multiple.
  package var lineHeight: CGFloat {
    guard let lineHeightMultiple else { return naturalLineHeight }
    return size * lineHeightMultiple
  }

  /// `lineHeight - naturalLineHeight`, and negative for the two headline roles.
  ///
  /// The escape hatch for exact leading: `.lineSpacing` cannot go below the face's own leading, so a
  /// caller that lays lines out itself (`VStack(spacing: style.leadingDelta)` over one `Text` per line
  /// — `VStack` does accept negative spacing) gets the scale's value where the modifier path clamps to
  /// the face's.
  package var leadingDelta: CGFloat { lineHeight - naturalLineHeight }

  fileprivate init(
    size: CGFloat,
    resolved: InkFonts.Resolved,
    tracking: CGFloat = 0,
    lineHeightMultiple: CGFloat? = nil
  ) {
    self.size = size
    self.font = resolved.font
    self.tracking = tracking
    self.lineHeightMultiple = lineHeightMultiple
    self.usesBundledFace = resolved.isCustom
    let natural = InkFonts.naturalLineHeight(resolved.metrics)
    self.naturalLineHeight = natural
    if let lineHeightMultiple {
      self.lineSpacing = max(0, size * lineHeightMultiple - natural)
    } else {
      self.lineSpacing = 0
    }
  }
}

/// The scale, and the two rules that generate it.
///
/// **Sizes.** Every reading role stays under `Font.inkDisplayThreshold` (22 pt) so it is still SF Pro
/// and not Open Runde, and `prose` stays under 18 pt so it is still *normal* text under WCAG and the
/// label ladder's AA bar stays the 4.5:1 one rather than the 3:1 large-text allowance. **The bar must
/// not get easier because the type got bigger.**
///
/// **Tracking.** Every value below is `em × size`, and this is the rule a size change breaks silently:
/// tracking is stored in points, so a role that grows and keeps its old point value has quietly
/// loosened — bigger letterforms with the same gap between them. Recompute from the `em`, which is the
/// fixed part: −0.035 at display, −0.03 at headline, −0.01 at reading size, and **nothing at 12 pt or
/// under**, where tightening closes the counters faster than it locks the words up.
package enum InkType {
  /// Open Runde 34 / semibold / −1.19 (−0.035 em) / 1.10. The largest thing on screen, and the only
  /// reason the tracking is this tight: at display size a geometric sans falls apart if the words do
  /// not lock up.
  package static var introHero: InkTextStyle {
    runde(34, .semiBold, tracking: -1.19, lineHeight: 1.10)
  }

  /// Open Runde 27 / semibold / −0.81 (−0.03 em) / 1.18.
  package static var stepHeadline: InkTextStyle {
    runde(27, .semiBold, tracking: -0.81, lineHeight: 1.18)
  }

  /// The "First…" line. Same face, size and tracking as `stepHeadline` — one headline size — and no
  /// leading multiple, because it is always a single line over a list.
  package static var firstTitle: InkTextStyle {
    runde(27, .semiBold, tracking: -0.81)
  }

  /// SF Pro 17 / regular / −0.17 (−0.01 em) / 1.55. The one role that carries paragraphs. Pair with
  /// `Ink.secondary`.
  ///
  /// 17 and not 18: at 18 pt WCAG reclassifies it as large text, which would drop the label ladder's
  /// contrast bar from 4.5:1 to 3:1 for the step that does the most reading.
  package static var prose: InkTextStyle {
    runde(17, .regular, tracking: -0.17, lineHeight: 1.55)
  }

  /// SF Pro 15 / medium / −0.15 (−0.01 em) / 1.40. Row copy. Medium, not regular: on a card, a row's
  /// sentence sits beside a heavier headline and regular goes weedy next to it. Pair with
  /// `Ink.primary`.
  package static var rowCopy: InkTextStyle {
    runde(15, .medium, tracking: -0.15, lineHeight: 1.40)
  }

  /// SF Pro 12 / regular. Every small line and the status word in a row. Pair with `Ink.secondary` —
  /// and on an opaque surface, and only there, `Ink.tertiary` for a single glanceable word. Small type
  /// on glass is exactly where the bottom rung disappears.
  ///
  /// No tracking, and for a boundary rather than a margin: 12 pt is the floor the ladder tightens
  /// *above*. This role sits exactly on the floor, where the −0.01 em the reading roles take would come
  /// to −0.12 pt: not a letterform decision, a rounding error with a legibility cost.
  package static var statusLabel: InkTextStyle {
    runde(12, .regular)
  }

  /// SF Pro 15 / semibold / −0.15 (−0.01 em).
  package static var buttonLabel: InkTextStyle {
    runde(15, .semiBold, tracking: -0.15)
  }

  /// The smallest size any role is allowed to resolve at.
  ///
  /// Not a style value — a floor, and the one the scale is guarded against sliding back under. It is
  /// also the size the tracking ladder stops at, so a role that ever lands below this has both gone
  /// under the legible minimum and left the part of the ladder where tracking is defined.
  package static let minimumSize: CGFloat = 12

  /// The roles, in the order they appear in the design doc. Used by previews and by the completeness
  /// check that every role resolves to a real face.
  package static let allRoles: [InkTextStyle] = [
    introHero, stepHeadline, firstTitle, prose, rowCopy, statusLabel, buttonLabel,
  ]

  private static func runde(
    _ size: CGFloat,
    _ weight: RundeWeight,
    tracking: CGFloat = 0,
    lineHeight: CGFloat? = nil
  ) -> InkTextStyle {
    InkTextStyle(
      size: size,
      resolved: InkFonts.role(size: size, weight: weight),
      tracking: tracking,
      lineHeightMultiple: lineHeight
    )
  }
}

/// The roles again, on the type they produce, so every call site can infer the base:
/// `.inkStyle(.introHero)` rather than `.inkStyle(InkType.introHero)`. `InkType` stays the place the
/// values are defined; this is only how they are spelled at the point of use.
extension InkTextStyle {
  package static var introHero: InkTextStyle { InkType.introHero }
  package static var stepHeadline: InkTextStyle { InkType.stepHeadline }
  package static var firstTitle: InkTextStyle { InkType.firstTitle }
  package static var prose: InkTextStyle { InkType.prose }
  package static var rowCopy: InkTextStyle { InkType.rowCopy }
  package static var statusLabel: InkTextStyle { InkType.statusLabel }
  package static var buttonLabel: InkTextStyle { InkType.buttonLabel }
}

extension View {
  /// The role applied to a view whose text it cannot reach directly — a `Button` label, a `Label`, a
  /// stack of runs. Carries the face and the tracking, which propagate to descendant text; the leading
  /// is `Text`-level and stays with the `Text` overload below.
  @ViewBuilder
  package func inkStyle(_ style: InkTextStyle, color: Color? = nil) -> some View {
    let styled = font(style.font).tracking(style.tracking)
    if let color {
      styled.foregroundStyle(color)
    } else {
      styled
    }
  }
}

extension Text {
  /// The whole role: face, size, tracking, leading, and optionally the colour.
  /// `Text("…").inkStyle(.introHero)` — there is no supported way to get the face without the tracking,
  /// which is the point.
  ///
  /// `color` is applied innermost so a caller's own `.foregroundStyle` further out cannot fight it;
  /// omit it to inherit from the environment.
  @ViewBuilder
  package func inkStyle(_ style: InkTextStyle, color: Color? = nil) -> some View {
    Group {
      if let color {
        inkFont(style).foregroundStyle(color)
      } else {
        inkFont(style)
      }
    }
    .lineSpacing(style.lineSpacing)
  }

  /// Face + size + tracking only, still a `Text`, for the rare case that needs to concatenate or feed a
  /// `Label`. Loses the leading — prefer `inkStyle(_:)`.
  package func inkFont(_ style: InkTextStyle) -> Text {
    font(style.font).tracking(style.tracking)
  }
}
