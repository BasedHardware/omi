import AppKit
import Foundation
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// `OmiButtonStyle` is the app's one button primitive — roughly eighty call sites wear it, from
/// onboarding to billing to the settings pane — so whatever it decides about colour, every button in
/// the product decides at once. That leverage is why it is worth a test, and it is also exactly how
/// it broke:
///
/// The style used to fill `.primary` with `OmiColors.accent` (`#FFFFFF`) and set the label in
/// `OmiColors.backgroundPrimary` (`#0F0F0F`). Read on its own that is a perfectly good pair — black
/// on white, 19:1 — and **that is exactly why the bug was invisible to review**. The pair that
/// failed was the one nobody names: the button's *fill* against the *panel it sits on*. On the dark
/// page it was white on `#0F0F0F`; when the app was pinned to a light glass appearance the palette
/// did not move with it, and a white capsule on a near-white panel is a button-shaped hole. It
/// compiled, it laid out, it took clicks, and nobody could see it.
///
/// So the claims below are about **resolved pixels**, not token names, and they include the ground
/// as well as the label. Each is composited in the appearance the glass is actually pinned to
/// (`InkGlass.appearance`) and measured with the WCAG contrast formula, which is the only form of
/// the assertion a future palette change cannot satisfy vacuously.
@MainActor
final class GlassButtonPrimitiveTests: XCTestCase {

  // MARK: - The failure that shipped: a label the same colour as the fill under it

  func testEveryButtonKindKeepsItsLabelLegibleOnItsOwnFill() {
    for kind in OmiButtonStyle.Kind.allCases {
      let label = resolved(OmiButtonStyle.label(kind))
      // `.secondary` has no fill of its own, so the ground it is read against is the panel's.
      let ground = resolved(
        kind == .secondary ? Ink.surface : OmiButtonStyle.fill(kind, pressed: false))
      let ratio = contrast(label, ground)

      // 3:1 is WCAG's bar for large text and for UI component boundaries, which is what a 15 pt
      // semibold button label on a filled capsule is. The neutral kinds clear it several times over;
      // it is the red one that sets the floor.
      XCTAssertGreaterThanOrEqual(
        ratio, 3.0,
        """
        OmiButtonStyle(\(kind)) draws its label at \(String(format: "%.2f", ratio)):1 against the \
        ground under it. This is the white-on-white failure the light-glass migration shipped: the \
        style still compiles and still lays out, so nothing else in the suite notices.
        """
      )
    }
  }

  func testAFilledButtonIsDistinguishableFromThePanelUnderIt() {
    // **This is the assertion that would have caught the shipped defect**, and the one the obvious
    // label-vs-fill check above does not: a button is a shape before it is a label, so its fill has
    // to separate from the glass it is drawn on. 3:1 is WCAG's bar for the boundary of a UI
    // component against what is adjacent to it.
    for kind in OmiButtonStyle.Kind.allCases where kind != .secondary {
      let ratio = contrast(resolved(OmiButtonStyle.fill(kind, pressed: false)), resolved(Ink.surface))
      XCTAssertGreaterThanOrEqual(
        ratio, 3.0,
        """
        OmiButtonStyle(\(kind)) fills at \(String(format: "%.2f", ratio)):1 against the panel it \
        sits on — a button-shaped hole. Its label may still be perfectly legible on that fill, \
        which is how this shipped.
        """
      )
    }

    // The witness that keeps the bar above from being vacuous: the fill this style used to draw.
    // The retired dark palette's `accent` was `#FFFFFF` — on the light-pinned glass that is the
    // panel's own colour. Written as the literal because the palette itself is now deleted; if
    // this ever clears 3:1 the ground moved and the check above has stopped meaning anything.
    XCTAssertLessThan(
      contrast(resolved(Color(hex: 0xFFFF_FF)), resolved(Ink.surface)), 3.0,
      "The pre-glass primary fill is no longer invisible on the panel; re-derive this test.")
  }

  func testPressingAButtonStaysLegible() {
    // The press state is a different fill, so it is a different contrast pair — and it is the one
    // nobody screenshots.
    for kind in OmiButtonStyle.Kind.allCases where kind != .secondary {
      let label = resolved(OmiButtonStyle.label(kind))
      let pressedFill = resolved(OmiButtonStyle.fill(kind, pressed: true))
      XCTAssertGreaterThanOrEqual(contrast(label, pressedFill), 3.0, "\(kind) pressed")
    }
  }

  // MARK: - The shape of the decision

  func testPrimaryInvertsTheLabelLadderRatherThanFillingWithTheAccent() {
    // Deliberately *not* accent-filled: the accent is already spent on the one link that needs it,
    // and a filled accent button owes a label colour legible on it in both appearances — one more
    // contrast pair to keep true. See `InkButtonStyle`, which this mirrors.
    XCTAssertEqual(OmiButtonStyle.fill(.primary, pressed: false), Ink.primary)
    XCTAssertEqual(OmiButtonStyle.label(.primary), Ink.surface)
    XCTAssertNotEqual(OmiButtonStyle.fill(.primary, pressed: false), Ink.accent)
  }

  func testOnlyTheUnfilledKindIsOutlined() {
    // On a filled capsule a border is a second edge drawn over the first.
    XCTAssertEqual(OmiButtonStyle.border(.secondary), Ink.hairline)
    XCTAssertEqual(OmiButtonStyle.border(.primary), Color.clear)
    XCTAssertEqual(OmiButtonStyle.border(.destructive), Color.clear)

    // …and `hairline`, not `separator`: the outline of a control and a rule between blocks are
    // different jobs, and `Ink` keeps two values precisely so they cannot be confused here.
    XCTAssertNotEqual(OmiButtonStyle.border(.secondary), Ink.separator)
  }

  func testSecondaryDrawsNothingAtRestAndTakesTheSharedPressWash() {
    XCTAssertEqual(OmiButtonStyle.fill(.secondary, pressed: false), Color.clear)
    XCTAssertEqual(OmiButtonStyle.fill(.secondary, pressed: true), Ink.wash)
  }

  func testPressIsVisibleForEveryKind() {
    // Press feedback is colour only — no scale, because a pill this size bouncing reads as a toy —
    // so if the two fills were equal there would be no feedback at all.
    for kind in OmiButtonStyle.Kind.allCases {
      XCTAssertNotEqual(
        OmiButtonStyle.fill(kind, pressed: false),
        OmiButtonStyle.fill(kind, pressed: true),
        "\(kind) gives no press feedback")
    }
  }

  func testTheTwoButtonPrimitivesAgreeOnHowTallAButtonIs() {
    // `OmiButtonStyle(.regular)` and `InkButton` appear on the same screens. Two primitives with two
    // opinions about the metric is how a row of buttons ends up half a step out of line.
    XCTAssertEqual(OmiButtonStyle.minHeight(.regular), InkButtonStyle.minHeight)
    XCTAssertEqual(OmiButtonStyle.horizontalPadding(.regular), InkButtonStyle.horizontalPadding)
    XCTAssertLessThan(OmiButtonStyle.minHeight(.compact), OmiButtonStyle.minHeight(.regular))
  }

  func testDisabledIsOneOpacityRatherThanASecondPalette() {
    // A greyed-out fill and a greyed-out label are two more contrast pairs to keep true, and neither
    // says anything the dimming does not.
    XCTAssertEqual(OmiButtonStyle.disabledOpacity, 0.45)
    XCTAssertLessThan(OmiButtonStyle.pressedFillOpacity, 1.0)
  }

  // MARK: - The task agent's status readout

  func testTaskAgentFailureRaisesItsVoiceAndNothingUsesTheThirdRung() {
    // Both copies of this switch (the row indicator and the detail sheet) rendered `.failed` in the
    // faintest grey in the file, which is the opposite of what a failure has to do. They are one
    // function now, so there is one place for that to be right.
    XCTAssertEqual(TaskAgentStatusInk.color(for: .failed), Ink.errorRed)
    XCTAssertEqual(TaskAgentStatusInk.color(for: .completed), Ink.primary)

    for status in TaskAgentManager.AgentStatus.allCases {
      // Glass carries two rungs. `Ink.tertiary` measures under WCAG AA on the panel, so a status
      // word set in it is a status word nobody reads.
      XCTAssertNotEqual(
        TaskAgentStatusInk.color(for: status), Ink.tertiary,
        "\(status) uses the third type rung, which is illegal on glass")
    }
  }

  // MARK: - Measurement

  /// Composites a colour in the appearance the glass is pinned to.
  ///
  /// This is the whole point of the file. `Ink.primary` is `labelColor`, which is near-black in Light
  /// and near-white in Dark; asserting on the token alone would pass in either. The panel pins
  /// `.aqua`, so that is where the pixels have to be measured.
  private func resolved(_ color: Color) -> NSColor {
    var out = NSColor.black
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      // Flattened onto the panel's own ground first: `Ink.wash` and the pressed fills are alphas,
      // and an alpha's `redComponent` is not the colour anybody sees.
      let ground = NSColor(Ink.surface).usingColorSpace(.sRGB) ?? .white
      let raw = NSColor(color).usingColorSpace(.sRGB) ?? .black
      out = ground.blended(withFraction: raw.alphaComponent, of: raw.withAlphaComponent(1)) ?? raw
    }
    return out
  }

  private func luminance(_ color: NSColor) -> Double {
    func channel(_ raw: CGFloat) -> Double {
      let value = Double(raw)
      return value <= 0.03928 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * channel(color.redComponent)
      + 0.7152 * channel(color.greenComponent)
      + 0.0722 * channel(color.blueComponent)
  }

  private func contrast(_ lhs: NSColor, _ rhs: NSColor) -> Double {
    let a = luminance(lhs)
    let b = luminance(rhs)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)
  }
}
