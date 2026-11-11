import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Guards for the floating bar and the overlay surfaces after they moved off the dark `OmiColors`
/// palette and onto the glass design system.
///
/// The claims worth holding here are the ones with **no runtime signal when they break**. A view that
/// names a colour resolving to the same value as its ground still renders — it renders nothing, and
/// nothing logs. That is exactly what happened when the app was pinned light while `OmiColors` stayed
/// hardcoded dark, and it is what every case below is aimed at.
///
/// The floating bar is the one surface that is **not** light, and half this file exists to keep it
/// that way: it is welded to the physical notch, and the design has said since the handoff that the
/// pill is black glass in both themes (`SBTheme.pillBackground`). "Finish the conversion" applied
/// literally here would turn the notch into a white rectangle around a black bezel.
@MainActor
final class FloatingGlassChromeTests: XCTestCase {

  // MARK: - The pill stays black

  /// The regression this file exists for.
  ///
  /// Black in **both** themes, asserted for both rather than for the one the app currently asks for —
  /// "it happens to be black on the mode we ship" is not the claim, and a future light mode is
  /// precisely when someone would reach in here.
  func testTheNotchPillIsBlackGlassInBothThemes() throws {
    for mode in SBThemeMode.allCases {
      let ground = try resolve(NotchGlass.ground(mode), in: InkGlass.appearance)
      XCTAssertLessThan(
        ground.brightnessComponent, 0.12,
        "the \(mode.rawValue) pill ground is not black; a light pill draws a white rectangle around the notch")
      XCTAssertLessThan(
        ground.saturationComponent, 0.2,
        "the pill ground picked up a hue; it is neutral black glass (INV-UI-1)")
    }
    XCTAssertEqual(
      try resolve(NotchGlass.ground, in: InkGlass.appearance),
      try resolve(SBTheme(.light).pillBackground, in: InkGlass.appearance),
      "the pill's ground must stay the one `SBTheme` defines, not a second copy of it")
  }

  /// The pill's material is pinned **dark**, and that is the one value it overrides.
  ///
  /// `.hudWindow` in `.aqua` is a near-white sheet (`InkGlass.measuredMaterialTint`, 232/255). Under a
  /// black scrim that is a grey slab, and hiding it costs so much scrim that the panel stops passing
  /// any desktop at all. Everything else — the material itself, the corner, the edge alpha, the
  /// Reduce Transparency behaviour — is `InkGlass`'s and is asserted to be identical.
  func testThePillOverridesTheAppearanceAndNothingElse() {
    XCTAssertEqual(NotchGlass.appearanceName, .darkAqua)
    XCTAssertNotEqual(
      NotchGlass.appearanceName, InkGlass.appearanceName,
      "if the pill stops overriding the appearance it is no longer black glass")
    XCTAssertEqual(
      NotchGlass.material, InkGlass.material,
      "there is one material in this app; the pill renders it in a different appearance, not a different material")
    XCTAssertEqual(NotchGlass.appearance.name, .darkAqua)
  }

  /// Reduce Transparency really produces an opaque pill, and takes the blur with it.
  ///
  /// A machine setting a hermetic test cannot flip, which is why both decisions are functions of the
  /// `Bool` rather than statements inside the view — see `InkGlassView.apply(reduceTransparency:)`.
  ///
  /// This case caught the real thing on its first run: the opaque branch was `ground.opacity(1)`, and
  /// SwiftUI's `opacity` *multiplies* into an alpha the colour already carries, so a 0.85 scrim asked
  /// for opacity 1 came back 0.85. The pill stayed see-through with the setting on, and nothing at
  /// the call site looked wrong. See `NotchGlass.solidGround`.
  func testReduceTransparencyProducesAnOpaquePillAndDropsTheBlur() throws {
    let reduced = try resolve(NotchGlass.opaqueGround(reduceTransparency: true), in: NotchGlass.appearance)
    let normal = try resolve(NotchGlass.opaqueGround(reduceTransparency: false), in: NotchGlass.appearance)

    XCTAssertEqual(
      reduced.alphaComponent, 1, accuracy: 0.0001, "glass that ignores the setting is the defect the setting exists for"
    )
    XCTAssertLessThan(normal.alphaComponent, 1, "the pill is translucent when the user has not asked otherwise")
    XCTAssertFalse(
      NotchGlass.showsMaterial(reduceTransparency: true),
      "an unhidden NSVisualEffectView under an opaque ground samples the desktop every frame for nothing")
    XCTAssertTrue(NotchGlass.showsMaterial(reduceTransparency: false))
  }

  /// The bar's user-facing "solid background" switch and the accessibility setting are the same
  /// request, and go through the same seam. A second background branch is how one of them ends up
  /// drawing a surface the other was tuned against.
  func testSolidBackgroundPreferenceReachesTheSameOpaqueGroundAsReduceTransparency() throws {
    XCTAssertEqual(
      try resolve(NotchGlass.opaqueGround(reduceTransparency: true), in: NotchGlass.appearance),
      try resolve(NotchGlass.solidGround, in: NotchGlass.appearance))
  }

  /// The opaque ground is the *same colour*, fully opaque — not a different black someone matched by
  /// eye. Only the alpha may differ.
  func testTheOpaquePillIsTheSameColourAsTheTranslucentOne() throws {
    let scrim = try resolve(NotchGlass.ground, in: NotchGlass.appearance)
    let solid = try resolve(NotchGlass.solidGround, in: NotchGlass.appearance)
    XCTAssertEqual(solid.redComponent, scrim.redComponent, accuracy: 0.001)
    XCTAssertEqual(solid.greenComponent, scrim.greenComponent, accuracy: 0.001)
    XCTAssertEqual(solid.blueComponent, scrim.blueComponent, accuracy: 0.001)
  }

  // MARK: - The pill's ink

  /// **Inside the pill the ladder is light**, and this is the assertion that catches the whole class
  /// of bug this conversion introduced elsewhere: `Ink.primary` is `labelColor`, which resolves *dark*
  /// in the appearance the app is pinned to, so a run of it inside the pill is near-black type on
  /// near-black glass.
  func testThePillsInkLadderIsLightAndIsNotTheAppsPinnedLadder() throws {
    let appPrimary = try resolve(Ink.primary, in: InkGlass.appearance)
    XCTAssertLessThan(
      appPrimary.brightnessComponent, 0.5, "the app's pinned ladder is dark ink — the premise of the next assertion")

    for (name, color) in pillLadder {
      let resolved = try resolve(color, in: InkGlass.appearance)
      XCTAssertGreaterThan(
        resolved.brightnessComponent, 0.9,
        "\(name) is not light ink; inside the pill it would be dark type on black glass")
    }
  }

  /// Monotonic, and asserted as an ordering rather than four separate values: reaching for the token
  /// whose *name* sounds right rather than checking its alpha is how a ladder inverts.
  func testThePillsInkLadderIsMonotonic() throws {
    let alphas = try pillLadder.map { try resolve($0.1, in: InkGlass.appearance).alphaComponent }
    for (index, pair) in zip(alphas, alphas.dropFirst()).enumerated() {
      XCTAssertGreaterThan(
        pair.0, pair.1,
        "\(pillLadder[index].0) is not heavier than \(pillLadder[index + 1].0)")
    }
    XCTAssertEqual(alphas.first ?? 0, 1, accuracy: 0.0001, "the pill's top rung is solid ink")
  }

  /// **Active outranks hover.** A control the pointer happens to be over must not dim back to the
  /// lighter wash, which is what the naive `isHovering ? hover : (isActive ? active : rest)` ordering
  /// does — and it looks deliberate enough to ship.
  func testPillControlFeedbackOrderingAndThatEveryFillIsAWash() throws {
    let active = try resolve(NotchGlass.controlFill(isActive: true, isHovering: false), in: InkGlass.appearance)
    let activeHovered = try resolve(NotchGlass.controlFill(isActive: true, isHovering: true), in: InkGlass.appearance)
    let hovered = try resolve(NotchGlass.controlFill(isActive: false, isHovering: true), in: InkGlass.appearance)
    let rest = try resolve(NotchGlass.controlFill(isActive: false, isHovering: false), in: InkGlass.appearance)

    XCTAssertEqual(activeHovered.alphaComponent, active.alphaComponent, accuracy: 0.0001)
    XCTAssertGreaterThan(active.alphaComponent, hovered.alphaComponent)
    XCTAssertGreaterThan(hovered.alphaComponent, rest.alphaComponent)
    for fill in [active, hovered, rest] {
      XCTAssertLessThan(
        fill.alphaComponent, 0.2,
        "a fill heavier than a wash is a second ground on a surface the design is about seeing through")
    }
  }

  /// A control's label is the ink when it is on and the quiet rung when it is off — never the same
  /// value twice, which is a toggle with no visible state.
  func testPillControlLabelDistinguishesOnFromOff() throws {
    let on = try resolve(NotchGlass.controlLabel(isActive: true), in: InkGlass.appearance)
    let off = try resolve(NotchGlass.controlLabel(isActive: false), in: InkGlass.appearance)
    XCTAssertGreaterThan(on.alphaComponent - off.alphaComponent, 0.3)
  }

  /// INV-UI-1. The pill is where an "accent" would slip back in, because it is the one surface with a
  /// dark ground for a hue to look good on. The banned band is 250°–330°, violet through magenta.
  func testNoPillColourIsPurple() throws {
    var palette = pillLadder
    palette.append(contentsOf: [
      ("ground", NotchGlass.ground), ("edge", NotchGlass.edge),
      ("fill", NotchGlass.fill), ("fillHover", NotchGlass.fillHover), ("fillActive", NotchGlass.fillActive),
    ])
    for (name, color) in palette {
      let resolved = try resolve(color, in: InkGlass.appearance)
      // A near-neutral has no meaningful hue; reading one off an almost-grey is noise.
      guard resolved.saturationComponent > 0.15 else { continue }
      let hue = resolved.hueComponent * 360
      XCTAssertFalse((250...330).contains(hue), "\(name) is in the banned purple band at \(hue)°")
    }
  }

  // MARK: - The surfaces that render on *both* grounds

  /// The push-to-talk mic button and its waveform draw in the main window's **light** composer and in
  /// the floating bar's **black** pill, from one definition.
  ///
  /// Their first version was the legacy dark palette — a fixed `#B0B0B0` glyph and a `#FFFFFF`
  /// listening ring — which compiled, drew, and was invisible in the composer. The property that fixes
  /// it is that the tokens are *dynamic*: the same token has to resolve dark on the pinned-light panel
  /// and light in the dark-pinned pill. A fixed colour passes any single-appearance check and fails
  /// this one.
  func testTheSharedMicButtonPaletteInvertsWithTheGroundItIsOn() throws {
    let shared: [(String, Color)] = [
      ("PushToTalkMicButton.idleTint", PushToTalkMicButton().idleTint),
      ("VoiceWaveformBars.tint", VoiceWaveformBars(isActive: false).tint),
    ]
    for (name, color) in shared {
      let onLightGlass = try resolve(color, in: InkGlass.appearance)
      let inThePill = try resolve(color, in: NotchGlass.appearance)
      XCTAssertLessThan(
        onLightGlass.brightnessComponent, 0.5,
        "\(name) renders light on the light-pinned composer — invisible, and nothing logs")
      XCTAssertGreaterThan(
        inThePill.brightnessComponent, 0.5,
        "\(name) renders dark inside the black pill — invisible, and nothing logs")
    }
  }

  /// The listening indicator is the one place the shared button says something with colour, and it has
  /// to say it on both grounds. `Ink.listeningGreen` is a *named system colour* for that reason.
  func testTheListeningIndicatorReadsOnBothGrounds() throws {
    for appearance in [InkGlass.appearance, NotchGlass.appearance] {
      let green = try resolve(Ink.listeningGreen, in: appearance)
      XCTAssertGreaterThan(green.saturationComponent, 0.3, "the live indicator went neutral and now says nothing")
      let hue = green.hueComponent * 360
      XCTAssertTrue((80...170).contains(hue), "the live indicator is no longer green (\(hue)°)")
    }
  }

  // MARK: - The window the pill lives in

  /// Exactly one shadow per floating surface — never zero, never two.
  ///
  /// The bar's panel is borderless, so AppKit's rectangular window shadow would not match the pill.
  /// `hasShadow = false` is the correct half of that pairing, and the panel therefore must not ask
  /// for a second one from the content either.
  func testTheFloatingPanelAndItsContentAgreeOnWhoDrawsTheShadow() {
    XCTAssertFalse(
      WindowGlass.drawsSystemShadow(.floating),
      "a borderless panel's frame shadow traces a transparent rectangle, not the pill")
    XCTAssertFalse(
      WindowGlass.hasTitlebar(.floating),
      "there is no title bar to get out of the pill's way")
  }

  /// `WindowGlass.wear` really produces a transparent window, which is the property the overlay panels
  /// were converted to rely on. An opaque window cannot composite the material at all, and one that
  /// paints its own ground slips a sheet between the desktop and the `.behindWindow` blur.
  func testWearingTheFloatingGlassLeavesNoGroundBetweenTheDesktopAndTheBlur() {
    let panel = NSPanel(
      contentRect: NSRect(x: 0, y: 0, width: 320, height: 120),
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: true)
    panel.isOpaque = true
    panel.backgroundColor = .windowBackgroundColor
    panel.hasShadow = true

    WindowGlass.wear(panel, as: .floating)

    XCTAssertFalse(panel.isOpaque)
    XCTAssertEqual(panel.backgroundColor, .clear)
    XCTAssertFalse(panel.hasShadow)
    XCTAssertEqual(panel.appearance?.name, .aqua)
  }

  // MARK: - Static checkers
  //
  // Tripwires, not behavioural coverage, and labelled as such: "which colour token a call site names"
  // is not observable from a running view without a window server and a screenshot diff, and every
  // decision that *is* a value is covered above. They earn their place because each guards a class of
  // mistake with no runtime signal — the surface renders either way, it just renders nothing.

  /// The floating bar and every overlay surface converted with it.
  private static let convertedSources = [
    "FloatingControlBar/NotchGlassChrome.swift",
    "FloatingControlBar/FloatingBackgroundModifier.swift",
    "FloatingControlBar/FloatingControlBarView.swift",
    "FloatingControlBar/FloatingControlBarWindow.swift",
    "FloatingControlBar/AgentPill.swift",
    "FloatingControlBar/AIResponseView.swift",
    "FloatingControlBar/NotchSystemControlsView.swift",
    "FloatingControlBar/NotchVoiceMorphMark.swift",
    "FloatingControlBar/FloatingControlBarReceiptCard.swift",
    "FloatingControlBar/PushToTalkMicButton.swift",
    "FloatingControlBar/VoiceWaveformBars.swift",
    "CloudConnectorGuidanceOverlay.swift",
    "WhatsNewToast.swift",
    "UsageLimitPopupView.swift",
    "PostOnboardingPromptViews.swift",
    "FeedbackView.swift",
    "ViewExporter.swift",
  ]

  /// The subset that renders on the app's **light** glass. The floating bar is deliberately absent —
  /// its ladder is the white-on-black one, where a third rung is affordable (see `NotchGlass.quiet`).
  private static let lightGlassSources = [
    "CloudConnectorGuidanceOverlay.swift",
    "WhatsNewToast.swift",
    "UsageLimitPopupView.swift",
    "PostOnboardingPromptViews.swift",
    "FeedbackView.swift",
  ]

  /// The legacy dark palette is hardcoded hex tuned for a near-black page. A single surviving
  /// reference renders white-on-white — or an opaque slab — on a light-pinned panel, and nothing logs.
  func testStaticCheckerConvertedSurfacesNoLongerReadTheDarkPalette() throws {
    for path in Self.convertedSources {
      XCTAssertFalse(
        try code(path).contains("OmiColors."),
        "\(path) still reads the dark OmiColors palette, which does not resolve on glass.")
    }
  }

  /// SwiftUI's `Material` is *within-window* vibrancy: it blurs the app's own content rather than the
  /// desktop. On a borderless transparent overlay there is no app content to blur, so a card built on
  /// it comes out empty. There is one material in this app and `InkGlass` owns it.
  func testStaticCheckerConvertedSurfacesStackNoSecondMaterial() throws {
    for path in Self.convertedSources {
      let body = try code(path)
      for material in ["ultraThinMaterial", "thinMaterial", "regularMaterial", "thickMaterial"] {
        XCTAssertFalse(
          body.contains(material),
          "\(path) uses .\(material). InkGlass's .hudWindow is the only material in this app.")
      }
    }
  }

  /// **Two rungs on glass.** `Ink.tertiary` measures under WCAG AA on the ground the light panels are
  /// tuned to — see `Ink.tertiary` for the measurements. The pill is excluded on purpose: that rule is
  /// arithmetic about dark type on a light ground, and the pill's ground is the opposite.
  func testStaticCheckerLightGlassSurfacesNeverSetTheThirdTypeRungOnGlass() throws {
    for path in Self.lightGlassSources {
      XCTAssertFalse(
        try code(path).contains("Ink.tertiary"),
        "\(path) sets Ink.tertiary, which measures under WCAG AA on the panel. Promote to Ink.secondary.")
    }
  }

  /// INV-UI-1. macOS offers the banned hue as a system accent, so `Color.accentColor` renders
  /// off-brand on such a machine and no rendered-pixel check catches it — every machine this is
  /// developed on reports blue.
  func testStaticCheckerConvertedSurfacesNeverReadTheMachinesAccentColour() throws {
    for path in Self.convertedSources {
      XCTAssertFalse(
        try code(path).contains("Color.accentColor"),
        "\(path) reads Color.accentColor, which is purple on a machine set to purple. Use Ink.accent.")
    }
  }

  // MARK: - Helpers

  private var pillLadder: [(String, Color)] {
    [
      ("NotchGlass.primary", NotchGlass.primary),
      ("NotchGlass.secondary", NotchGlass.secondary),
      ("NotchGlass.quiet", NotchGlass.quiet),
      ("NotchGlass.disabled", NotchGlass.disabled),
    ]
  }

  /// Source with comments stripped.
  ///
  /// Scanning raw text would fail on the files this guards: the rules above are *documented* at the
  /// call sites that used to break them ("deliberately not `.ultraThinMaterial`"), and a checker that
  /// cannot tell a prohibition from its violation punishes writing the reason down.
  private func code(_ relativePath: String) throws -> String {
    // omi-test-quality: source-inspection -- static contract; the value decisions are covered
    // behaviorally above, and which token a call site *names* has no runtime signal.
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

  /// Resolved inside a named appearance, because that is the whole subject here: these tokens are
  /// dynamic, and reading one on whatever appearance the test machine happens to be in reports the
  /// wrong value and passes for the wrong reason.
  private func resolve(_ color: Color, in appearance: NSAppearance) throws -> NSColor {
    var resolved: NSColor?
    appearance.performAsCurrentDrawingAppearance {
      resolved = NSColor(color).usingColorSpace(.sRGB)
    }
    return try XCTUnwrap(resolved)
  }
}
