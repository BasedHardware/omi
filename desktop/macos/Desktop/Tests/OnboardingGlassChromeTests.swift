import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The first-run surfaces' half of the glass contract.
///
/// These screens are where the light conversion was most dangerous and least visible. Sign-in, the
/// session-recovery card and the conversational onboarding all painted a **full-bleed dark
/// background** — a dune photograph under a black gradient — and set every label in `Color.white` or
/// the dark-only `SBTheme` ink on top of it. On the light-pinned panel each of those is white on
/// white: it compiles, it draws, it lays out, and it is invisible. Nothing logs, no test failed, and
/// the surfaces affected are the only ones a *new* user ever sees, so the first person to find it
/// would have been someone who had never seen the app work.
///
/// Two kinds of check live here, and the split is deliberate:
///
/// - **Behavioural** — `OnboardingGlass`'s decisions are pure functions, so the claims that matter
///   ("an inactive dot really is fainter", "Reduce Motion really flattens the drift") are asserted by
///   calling them, not by reading the source.
/// - **Static checkers**, labelled as such. Which colour token a call site *names* has no runtime
///   signal without a window server and a screenshot diff, so the palette rules are source scrapes.
///   They are tripwires, not behavioural coverage.
///
/// Source is scanned **with comments stripped**, for the reason `ShellGlassChromeTests` gives: these
/// rules are documented at the call sites that used to break them ("was `.ultraThinMaterial`"), and a
/// checker that cannot tell a prohibition from its violation punishes writing the reason down.
@MainActor
final class OnboardingGlassChromeTests: XCTestCase {

  // MARK: - The surfaces under contract

  /// Every screen a signed-out or un-onboarded user can reach, plus the shared chrome they wear.
  ///
  /// Adding a first-run surface to this list is how it joins the contract. A screen that renders
  /// before the user is onboarded and is *not* here is a screen that can go white-on-white again.
  private static let firstRunSources: [String] = [
    "SignInView.swift",
    "Auth/SessionRecoveryView.swift",
    "Onboarding/SecondBrain/SBOnboardingView.swift",
    "Onboarding/OnboardingGlassChrome.swift",
  ]

  /// The signed-in onboarding flow mounted by `DesktopHomeView`. `OnboardingView` is retained for
  /// export previews and already owns the legacy `OnboardingProgressBar`; this is the production
  /// current-step container that must consume the shared glass transition and reserved band.
  private static let liveOnboardingSource = "Onboarding/SecondBrain/SBOnboardingView.swift"

  // MARK: - Behaviour: the progress band

  /// The current dot outranks the rest, and the rest are a *fill* rather than a rung of the ladder.
  func testProgressDotsDistinguishTheCurrentStep() {
    XCTAssertEqual(OnboardingGlass.dotFill(isCurrent: true), Ink.primary)
    XCTAssertNotEqual(
      OnboardingGlass.dotFill(isCurrent: false), OnboardingGlass.dotFill(isCurrent: true),
      "an inactive dot that matches the current one is a row of identical dots")
    XCTAssertEqual(
      OnboardingGlass.dotFill(isCurrent: false),
      Ink.primary.opacity(OnboardingGlass.inactiveDotOpacity))
  }

  /// The band is a **reservation**, not a position.
  ///
  /// This is the regression the source app paid for: dots hung as an `.overlay(alignment: .bottom)`
  /// are placed at a fixed distance from the foot, so a column taller than that distance draws
  /// straight through them — upstream they landed inside a permission row and, being `Ink.primary` on
  /// a near-black pill, invisibly on top of a button. A height subtracted from the column by a
  /// `VStack` sibling cannot collide with anything, and it has to be non-zero for that to mean
  /// anything.
  func testProgressBandReservesAFixedStripRatherThanOverlayingTheColumn() {
    XCTAssertGreaterThan(
      InkLayout.progressBandHeight, 0,
      "a zero-height band is an overlay wearing a VStack's clothes")
    let band = OnboardingProgressBand(total: 5, current: 2)
    let hosted = NSHostingView(rootView: band)
    XCTAssertEqual(
      hosted.fittingSize.height, InkLayout.progressBandHeight, accuracy: 0.5,
      "the band must claim its full height so the column above is offered the same room")
  }

  /// …and it claims that height on a step with no dots, so copy does not jump between cards.
  func testProgressBandKeepsItsHeightWithNoDotsToDraw() {
    let empty = NSHostingView(rootView: OnboardingProgressBand(total: 0, current: nil))
    XCTAssertEqual(
      empty.fittingSize.height, InkLayout.progressBandHeight, accuracy: 0.5,
      "a step without dots must reserve the same strip or the copy shifts by 40 pt between cards")
  }

  func testScrollContentKeepsAFullBandOfClearanceAboveTheProgressBand() {
    XCTAssertGreaterThan(
      OnboardingGlass.scrollContentBottomPadding,
      InkLayout.progressBandHeight,
      "the scroll sentinel needs more room than the band itself to avoid covering the last control")
  }

  // MARK: - Behaviour: the step transition

  /// The drift is a fraction of the card, not a fixed number of points: the same modifier has to read
  /// as the same distance in a tall window and a short one.
  func testStepDriftScalesWithTheCard() throws {
    guard !InkReduceMotion.isEnabled else {
      throw XCTSkip("Reduce Motion is on for this machine; the drift is asserted as zero below")
    }
    let short = OnboardingGlass.stepOffset(inHeight: 400)
    let tall = OnboardingGlass.stepOffset(inHeight: 800)
    XCTAssertEqual(tall, short * 2, accuracy: 0.001)
    XCTAssertEqual(short, 400 * OnboardingGlass.stepOffsetFraction, accuracy: 0.001)
  }

  /// Reduce Motion flattens the drift to nothing. Asserted through the same seam the view uses, so
  /// the setting is honoured by a call rather than by a discipline nobody keeps.
  func testReduceMotionRemovesTheStepDrift() {
    if InkReduceMotion.isEnabled {
      XCTAssertEqual(OnboardingGlass.stepOffset(inHeight: 900), 0)
      XCTAssertNil(OnboardingGlass.stepAnimation)
    } else {
      XCTAssertNotEqual(OnboardingGlass.stepOffset(inHeight: 900), 0)
      XCTAssertNotNil(OnboardingGlass.stepAnimation)
    }
  }

  /// The shared helpers must be consumed by the live Second Brain panel. Keeping the band as a
  /// sibling of its scroll view reserves the tested strip without adding a second progress control to
  /// the legacy export-only wizard.
  func testLiveOnboardingConsumesTheSharedStepChrome() throws {
    let body = try code(Self.liveOnboardingSource)
    XCTAssertTrue(
      body.contains("panel(in: panelSize)"),
      "the live onboarding view must pass its actual fixed panel height to the step container")
    XCTAssertTrue(
      body.contains(".transition(.onboardingStep(in: panelSize))"),
      "the current step must consume the height-relative transition")
    XCTAssertTrue(
      body.contains("OnboardingProgressBand("),
      "the live current-step container must consume the fixed progress reservation")
    XCTAssertTrue(
      body.contains("OnboardingGlass.scrollContentBottomPadding"),
      "the live scroll content must leave structural clearance above the progress band")
    XCTAssertFalse(
      body.contains("Color.clear.frame(height: 14)"),
      "the old ad hoc footer is not the tested fixed progress band")
  }

  /// One corner for every panel in this system — a first-run card and the window it floats in must
  /// not be cut to two different curves.
  func testFirstRunCardsShareTheOnePanelCorner() {
    XCTAssertEqual(OnboardingGlass.panelRadius, InkGlass.cornerRadius)
    XCTAssertEqual(OnboardingGlass.panelRadius, 22)
  }

  // MARK: - Static checkers

  /// The legacy palette is hardcoded hex for a near-black page: `textPrimary` is `#FFFFFF`. One
  /// surviving reference on a first-run screen is white type on a white panel.
  func testStaticCheckerFirstRunSurfacesNoLongerReadTheDarkPalette() throws {
    for path in Self.firstRunSources {
      let body = try code(path)
      XCTAssertFalse(
        body.contains("OmiColors."),
        "\(path) reads the legacy dark palette. On the light-pinned panel that renders invisibly.")
    }
  }

  /// `SBTheme` is **dark-only** — `SBThemeManager.mode` is a `let`-in-practice `.dark`, so `sb.ink`
  /// is `#FFFFFF` and `sb.inkInverted` is near-black. Both are exactly inverted on light glass, which
  /// is the same white-on-white failure wearing a design system's name.
  func testStaticCheckerFirstRunSurfacesNoLongerReadTheDarkOnlySecondBrainInk() throws {
    for path in Self.firstRunSources {
      let body = try code(path)
      for token in ["sbTheme", "sb.ink", "sb.inkInverted"] {
        XCTAssertFalse(
          body.contains(token),
          "\(path) reads \(token). SBTheme is dark-only; use Ink, which resolves in the pinned light appearance."
        )
      }
    }
  }

  /// SwiftUI's `Material` is *within-window* vibrancy: it blurs the app's own content rather than the
  /// desktop, so it is not the panel's material and stacks a second scrim on a ground already tuned
  /// to the contrast floor.
  func testStaticCheckerFirstRunSurfacesStackNoSecondMaterial() throws {
    for path in Self.firstRunSources {
      let body = try code(path)
      for material in ["ultraThinMaterial", "thinMaterial", "regularMaterial", "thickMaterial"] {
        XCTAssertFalse(
          body.contains(material),
          "\(path) uses .\(material). InkGlass's .hudWindow is the only material in this app.")
      }
    }
  }

  /// Glass carries two rungs. `Ink.tertiary` measures under WCAG AA on the panel (see its
  /// documentation), and small type on glass is exactly where the bottom rung disappears.
  func testStaticCheckerFirstRunSurfacesNeverSetTheThirdTypeRungOnGlass() throws {
    for path in Self.firstRunSources {
      let body = try code(path)
      XCTAssertFalse(
        body.contains("Ink.tertiary"),
        "\(path) sets Ink.tertiary. Promote the run to Ink.secondary — glass carries two rungs.")
    }
  }

  /// **The one that would have caught the original defect.** The glass is the product; a first-run
  /// screen that fills itself with an image or a colour hides it and forces every label on top to be
  /// white — which is how every label on these three screens came to be `Color.white`.
  func testStaticCheckerFirstRunSurfacesPaintNoOpaqueGroundOfTheirOwn() throws {
    for path in Self.firstRunSources {
      let body = try code(path)
      for ground in ["signin_bg", "SBWallpaper()", "ignoresSafeArea()"] {
        XCTAssertFalse(
          body.contains(ground),
          """
          \(path) fills itself edge to edge (\(ground)). A first-run screen carries one ground and \
          it is the shared glass (`onboardingCard`); an opaque one hides it.
          """)
      }
    }
  }

  /// **The second defect, and the mirror image of the first.** Every screen above has to *have* a
  /// ground, because since `ShellWindowChrome` retired the window's full-bleed glass there is nothing
  /// under these screens but the user's wallpaper. Onboarding kept a bare `glassCard` — a 4.5%
  /// darkening wash — and shipped its copy straight onto a photograph of a city.
  ///
  /// A source scrape because "does this view tree end up with a material under it" has no runtime
  /// signal a hermetic test can read: `InkGlassBackdrop` blends `.behindWindow` and a test process has
  /// no desktop behind its windows. What the ground is *worth* once it exists is measured for real in
  /// `OnboardingGlassGroundRenderTests`; this only asserts each screen asks for it.
  func testStaticCheckerEveryFirstRunScreenWearsTheSharedCard() throws {
    // The chrome file defines the modifiers rather than wearing one.
    for path in Self.firstRunSources where path != "Onboarding/OnboardingGlassChrome.swift" {
      let body = try code(path)
      XCTAssertTrue(
        body.contains("onboardingCard()") || body.contains("onboardingScreen()"),
        """
        \(path) never applies `onboardingCard()` / `onboardingScreen()`, so it has no ground. The \
        window is transparent (`ShellWindowChrome`) — a first-run screen that draws only a wash is \
        drawing on the wallpaper.
        """)
    }
  }

  /// Every pressable pill in this system is a **full stadium**, and press feedback is colour only. A
  /// first-run screen that rolls its own `RoundedRectangle` fill is a web form's button.
  func testStaticCheckerFirstRunActionsNeverScaleOnPress() throws {
    for path in Self.firstRunSources {
      let body = try code(path)
      XCTAssertFalse(
        body.contains("scaleEffect(configuration.isPressed"),
        "\(path) scales a control on press. A pill this size bouncing reads as a toy.")
    }
  }

  // MARK: - Helpers

  /// Source with `//` comments stripped.
  ///
  /// Scanning raw text would fail on the very rules being enforced: each is documented at the call
  /// site that used to break it, and a checker that cannot tell a prohibition from its violation
  /// punishes writing the reason down.
  private func code(_ relativePath: String) throws -> String {
    // omi-test-quality: source-inspection -- static contract; which token a call site names has no
    // runtime signal without a window server, and the value decisions are covered behaviorally above.
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: which token a call site names is a source fact; a rendered view cannot report it.
    let source = try String(contentsOf: url, encoding: .utf8)
    return
      source
      .split(separator: "\n", omittingEmptySubsequences: false)
      .map { line -> Substring in
        guard let comment = line.range(of: "//") else { return line }
        return line[line.startIndex..<comment.lowerBound]
      }
      .joined(separator: "\n")
  }
}
