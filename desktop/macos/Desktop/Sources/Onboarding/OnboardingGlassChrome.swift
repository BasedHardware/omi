//
//  OnboardingGlassChrome.swift — the chrome every first-run card wears.
//
//  Onboarding and sign-in are the first screens a new user ever sees, and they are hosted on the
//  shell's one piece of glass (`glassShellGround`). That makes them the surfaces where the two rules
//  the glass is built on bite hardest, so they are encoded here rather than restated per step:
//
//  1. **The card paints no ground.** `DesktopHomeView` applies `glassShellGround()` once and says so
//     ("The one ground in this window. Nothing above it paints a background."). A first-run screen
//     that fills itself — with a colour, an image, or a `Material` — is an opaque slab pasted over
//     the panel, and the panel is the product. What replaced the dark art here is not "no design",
//     it is the design: the desktop, blurred, is the backdrop.
//  2. **Two type rungs, never three.** `Ink.tertiary` measures under WCAG AA on glass (see its
//     doc comment), so a first-run screen may only spend `Ink.primary` and `Ink.secondary`. The
//     faint-grey aside that reads as restraint on a dark sheet is illegible on this one.
//
//  The rest of this file is the two pieces of card furniture the steps share, and both exist because
//  the source app shipped the naive version and had to fix it:
//
//  - **The progress band is a reserved strip, not an overlay.** Dots positioned as an
//    `.overlay(alignment: .bottom)` are a *position*, not a reservation: upstream they landed inside
//    a permission row and, being `Ink.primary` on a near-black pill, invisibly on top of a button.
//    A `VStack` sibling subtracts the band from the height the column is offered, so there is
//    nothing left to collide with — and the band keeps its height on steps that draw no dots, so the
//    copy does not jump 40 pt between one card and the next.
//  - **The step transition is fraction-of-height, not a fixed offset.** A card that slides a fixed
//    number of points reads as a different distance in a tall window than in a short one.
//
//  Brand: `Ink` only — system semantics and neutrals, INV-UI-1's banned hue nowhere.
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - The decisions

/// First-run chrome's numbers and state colours, as values rather than as statements inside a view.
///
/// Pure functions of state for the same reason `GlassShell`'s are: it puts "an inactive dot really is
/// fainter than the current one" and "Reduce Motion really flattens the step transition" inside reach
/// of a hermetic test, and leaves each step view with no chrome judgement of its own.
enum OnboardingGlass {
  /// The corner of a first-run card — `InkGlass.cornerRadius` by construction, never a second
  /// opinion about 22.
  static let panelRadius: CGFloat = InkGlass.cornerRadius

  /// A progress dot. 5 pt is small enough to read as punctuation rather than as a control: these are
  /// an orientation cue, not a navigation bar.
  static let dotDiameter: CGFloat = 5

  /// Between two dots. Close enough that the row reads as one object.
  static let dotSpacing: CGFloat = 6

  /// How far a step drifts as it arrives, as a fraction of the card's height.
  static let stepOffsetFraction: CGFloat = 0.015

  /// The alpha an inactive dot is set at.
  ///
  /// Deliberately an opacity on `Ink.primary` rather than `Ink.secondary`: this is a *fill*, not
  /// type, so the two-rung rule does not apply and nobody has to read it. A dot set at the reading
  /// rung is very nearly as dark as the current one, which is a row of identical dots.
  static let inactiveDotOpacity: Double = 0.22

  /// The current dot against the rest.
  static func dotFill(isCurrent: Bool) -> Color {
    isCurrent ? Ink.primary : Ink.primary.opacity(inactiveDotOpacity)
  }

  /// The vertical drift a step arrives with, in points — zero under Reduce Motion.
  static func stepOffset(inHeight height: CGFloat) -> CGFloat {
    InkReduceMotion.isEnabled ? 0 : height * stepOffsetFraction
  }

  /// The one animation a step change is allowed.
  static var stepAnimation: Animation? {
    InkReduceMotion.animation(.easeOut(duration: InkMotion.stepTransition))
  }
}

// MARK: - The step transition

extension AnyTransition {
  /// How one first-run card becomes the next: a fade combined with a drift of
  /// `OnboardingGlass.stepOffsetFraction` of the card's height.
  ///
  /// Apply with `.id(step)` beside it — the `id` is what makes SwiftUI treat a step change as a
  /// removal and an insertion rather than as a mutation of one view, and without it the transition
  /// never runs.
  ///
  /// Plain `.opacity` under Reduce Motion: the setting is about movement, and a cross-fade is not
  /// movement. Removing the fade too would leave the cards snapping, which is not what was asked for.
  static func onboardingStep(in size: CGSize) -> AnyTransition {
    guard !InkReduceMotion.isEnabled else { return .opacity }
    return .opacity.combined(with: .offset(y: OnboardingGlass.stepOffset(inHeight: size.height)))
  }
}

// MARK: - The progress band

/// The strip at the foot of a first-run card that progress dots occupy.
///
/// **A `VStack` sibling of the column, never an overlay on it** — see the file header. It keeps
/// `InkLayout.progressBandHeight` whether or not this step draws dots, so every step's column is
/// offered the same room and the copy does not shift between cards.
///
/// `total` of zero draws an empty band rather than nothing, which is the case that keeps the
/// reservation honest on a step with no dots.
struct OnboardingProgressBand: View {
  /// How many cards of actual work this run has.
  let total: Int
  /// Which one is current, or `nil` on a step that sits outside the count (a finale, an error).
  var current: Int?

  var body: some View {
    dots
      .frame(height: InkLayout.progressBandHeight)
      .frame(maxWidth: .infinity)
      // The dots report progress; they do not offer navigation. A 5 pt circle is not a target.
      .allowsHitTesting(false)
      .accessibilityHidden(true)
  }

  @ViewBuilder
  private var dots: some View {
    if let current, total > 0 {
      HStack(spacing: OnboardingGlass.dotSpacing) {
        ForEach(0..<total, id: \.self) { dot in
          Circle()
            .fill(OnboardingGlass.dotFill(isCurrent: dot == current))
            .frame(width: OnboardingGlass.dotDiameter, height: OnboardingGlass.dotDiameter)
        }
      }
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: current)
    }
  }
}

// MARK: - The card

extension View {
  /// A first-run card: a wash, a hairline, the 22 pt corner, and the panel's light appearance.
  ///
  /// It delegates to `glassCard` so a card here and a card on a content page cannot disagree, and
  /// carries `glassContent()` because a first-run screen is reached before any navigation stack has
  /// pinned the appearance for it. Without that pin, a machine in Dark Mode resolves `Ink.primary`
  /// near-*white* onto the light panel and the whole card disappears — which is exactly the failure
  /// this conversion exists to end.
  func onboardingCard() -> some View {
    glassContent()
      .glassCard(cornerRadius: OnboardingGlass.panelRadius)
  }

  /// The copy column of a first-run step: the reading measure, centred, with the page padding.
  ///
  /// `InkLayout.contentMaxWidth` is the measure `prose` was sized against — wider is not more
  /// generous, it is a longer distance for the eye to travel back along.
  func onboardingColumn(maxWidth: CGFloat = InkLayout.contentMaxWidth) -> some View {
    frame(maxWidth: maxWidth)
      .padding(.horizontal, InkLayout.pagePaddingHorizontal)
      .padding(.vertical, InkLayout.pagePaddingVertical)
  }
}
