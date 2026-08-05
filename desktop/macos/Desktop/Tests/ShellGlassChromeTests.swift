import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Guards for the main window's shell after it moved off the dark `OmiColors` palette and onto the
/// glass design system.
///
/// The claims worth holding here are the ones with **no runtime signal when they break**: a window
/// that quietly paints its own opaque background still renders — it just renders a flat slab instead
/// of glass, and nothing logs. Every case below exercises the real value production uses.
@MainActor
final class ShellGlassChromeTests: XCTestCase {

  // MARK: - The window

  /// The regression this file exists for.
  ///
  /// The shell used to set `window.appearance = NSAppearance(named: .darkAqua)` on launch and again
  /// on every summon. On a glass window that is three failures at once: the panel's light-pinned
  /// material renders its *dark* variant, `labelColor` resolves near-white onto it, and the window
  /// keeps painting an opaque background so the `.behindWindow` blur has an opaque sheet in front of
  /// the desktop. Nothing about the drawing code looks wrong — it just is not glass.
  ///
  /// Behavioural: a real `NSWindow`, the real `WindowGlass.wear`, and the properties AppKit
  /// composites from. No window server is involved in reading them back.
  func testTitledWindowWearsTheGlassAndIsNotPinnedDark() throws {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 900, height: 600),
      styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
      backing: .buffered,
      defer: true)
    window.isOpaque = true
    window.backgroundColor = .windowBackgroundColor
    window.appearance = NSAppearance(named: .darkAqua)

    WindowGlass.wear(window, as: .titled)

    XCTAssertEqual(
      window.appearance?.name, .aqua,
      "the glass is pinned light; a dark-pinned window renders the dark material and white type on it")
    XCTAssertFalse(
      window.isOpaque,
      "an opaque window cannot composite the material at all")
    XCTAssertEqual(
      window.backgroundColor, .clear,
      "a window that paints its own ground slips an opaque sheet between the desktop and the blur")
    XCTAssertTrue(window.titlebarAppearsTransparent)
    XCTAssertEqual(window.titleVisibility, .hidden)
    XCTAssertEqual(window.titlebarSeparatorStyle, .none)
  }

  /// Exactly one shadow per window — never zero, never two.
  ///
  /// A titled window's frame draws the shadow, so the ground inside it must not draw a second one;
  /// a floating panel is the inverse. Asserting the *pairing* rather than each half is the point:
  /// either one alone is a coherent-looking mistake.
  func testTheShellGroundAndTheWindowFrameAgreeOnWhoDrawsTheShadow() {
    XCTAssertTrue(
      WindowGlass.drawsSystemShadow(.titled),
      "the main window is titled; AppKit's frame shadow is the only correct one")
    XCTAssertNil(
      GlassShell.groundStyle.shadow,
      "the ground must not cast a second shadow inside a window that already has one")

    // The inverse, so the pairing is a rule rather than a coincidence of one case.
    XCTAssertFalse(WindowGlass.drawsSystemShadow(.floating))
    XCTAssertNotNil(InkGlassStyle.floating.shadow)
  }

  /// The ground fills the window rather than floating in it: square, and inset by nothing.
  func testTheShellGroundIsFullBleed() {
    XCTAssertEqual(GlassShell.groundStyle, .fullBleed)
    XCTAssertEqual(GlassShell.groundStyle.cornerRadius, 0)
    XCTAssertEqual(GlassShell.groundStyle.inset, 0)
  }

  /// `.hiddenTitleBar` puts the traffic lights over the content view, so the shell reserves a band
  /// for them. The number is AppKit's own, not a guess — a hand-tuned constant is exactly what drifts
  /// when a future macOS changes the title bar height.
  func testTitlebarClearanceCoversTheTrafficLights() {
    let content = NSRect(x: 0, y: 0, width: 640, height: 480)
    let frame = NSWindow.frameRect(
      forContentRect: content, styleMask: [.titled, .closable, .resizable])
    let titlebarHeight = frame.height - content.height

    XCTAssertGreaterThan(titlebarHeight, 0, "a titled window has a title bar to clear")
    XCTAssertGreaterThanOrEqual(
      GlassShell.titlebarClearance, titlebarHeight,
      "content starting above the traffic lights renders under three coloured circles")
  }

  // MARK: - Shell controls

  /// Selected outranks hover.
  ///
  /// The naive ordering — hover checked first — makes a nav bar lose its current item the moment the
  /// pointer touches it, and it looks deliberate enough that it ships. This is the whole reason the
  /// decision is a function rather than a ternary inside a view.
  func testSelectedPillOutranksHover() throws {
    let selectedAndHovered = try resolve(GlassShell.pillFill(isSelected: true, isHovering: true))
    let selectedOnly = try resolve(GlassShell.pillFill(isSelected: true, isHovering: false))
    let hoveredOnly = try resolve(GlassShell.pillFill(isSelected: false, isHovering: true))
    let rest = try resolve(GlassShell.pillFill(isSelected: false, isHovering: false))

    XCTAssertEqual(
      selectedAndHovered.alphaComponent, selectedOnly.alphaComponent, accuracy: 0.0001,
      "a selected pill under the pointer dimmed back to the hover wash")
    XCTAssertGreaterThan(
      selectedOnly.alphaComponent, hoveredOnly.alphaComponent,
      "selection must read heavier than hover")
    XCTAssertGreaterThan(
      hoveredOnly.alphaComponent, rest.alphaComponent,
      "hover must read heavier than rest")
    XCTAssertEqual(
      rest.alphaComponent, 0, accuracy: 0.0001,
      "a pill that is filled at rest turns a nav bar into a row of grey slabs")
  }

  /// Pressed outranks active outranks hover, and an icon button is likewise empty at rest.
  func testIconButtonFeedbackOrdering() throws {
    let pressed = try resolve(
      GlassShell.iconButtonFill(isPressed: true, isActive: false, isHovering: false))
    let active = try resolve(
      GlassShell.iconButtonFill(isPressed: false, isActive: true, isHovering: false))
    let hovered = try resolve(
      GlassShell.iconButtonFill(isPressed: false, isActive: false, isHovering: true))
    let rest = try resolve(
      GlassShell.iconButtonFill(isPressed: false, isActive: false, isHovering: false))

    XCTAssertGreaterThan(pressed.alphaComponent, active.alphaComponent)
    XCTAssertGreaterThan(active.alphaComponent, hovered.alphaComponent)
    XCTAssertGreaterThan(hovered.alphaComponent, rest.alphaComponent)
    XCTAssertEqual(rest.alphaComponent, 0, accuracy: 0.0001)

    // A pressed *active* button must still read as pressed, not fall back to the active wash.
    XCTAssertEqual(
      try resolve(GlassShell.iconButtonFill(isPressed: true, isActive: true, isHovering: true))
        .alphaComponent,
      pressed.alphaComponent, accuracy: 0.0001)
  }

  /// **Two rungs on glass, never three.** `Ink.tertiary` measures under WCAG AA on the ground this
  /// panel is tuned to (see `Ink.tertiary`), so the shell's own label decision may never resolve to
  /// it. This is the rule the whole surface's transparency was bought with.
  func testShellLabelsNeverUseTheThirdRung() throws {
    let tertiary = try resolve(Ink.tertiary)
    for prominent in [true, false] {
      let label = try resolve(GlassShell.controlLabel(isProminent: prominent))
      XCTAssertGreaterThan(
        abs(label.alphaComponent - tertiary.alphaComponent), 0.01,
        "the shell reached for Ink.tertiary, which is illegal on glass")
    }
  }

  /// Every fill the shell draws is a *wash* — an alpha on the label colour — and not a rung of the
  /// type ladder. A fill borrowed from the ladder is an opaque slab on a surface the design is about
  /// seeing through.
  func testShellFillsAreWashesAndNeverOpaque() throws {
    let fills = [
      GlassShell.pillFill(isSelected: true, isHovering: false),
      GlassShell.pillFill(isSelected: false, isHovering: true),
      GlassShell.iconButtonFill(isPressed: true, isActive: false, isHovering: false),
      GlassShell.iconButtonFill(isPressed: false, isActive: true, isHovering: false),
      GlassShell.iconButtonFill(isPressed: false, isActive: false, isHovering: true),
    ]
    for fill in fills {
      let resolved = try resolve(fill)
      XCTAssertLessThan(
        resolved.alphaComponent, 0.2,
        "a shell fill heavier than a wash is a second ground on a translucent panel")
      XCTAssertGreaterThan(resolved.alphaComponent, 0)
    }
  }

  /// INV-UI-1: purple is off-brand, and shell chrome is where an "accent" would slip back in. The
  /// banned band is 250°–330°, violet through magenta.
  func testNoShellColourIsPurple() throws {
    let palette: [(String, Color)] = [
      ("pill.selected", GlassShell.pillFill(isSelected: true, isHovering: false)),
      ("pill.hover", GlassShell.pillFill(isSelected: false, isHovering: true)),
      ("icon.pressed", GlassShell.iconButtonFill(isPressed: true, isActive: false, isHovering: false)),
      ("label.prominent", GlassShell.controlLabel(isProminent: true)),
      ("label.quiet", GlassShell.controlLabel(isProminent: false)),
      ("Ink.accent", Ink.accent),
      ("Ink.surface", Ink.surface),
    ]
    for (name, color) in palette {
      let resolved = try resolve(color)
      // A near-neutral has no meaningful hue; reading one off an almost-grey is noise.
      guard resolved.saturationComponent > 0.15 else { continue }
      let hue = resolved.hueComponent * 360
      XCTAssertFalse(
        (250...330).contains(hue),
        "\(name) is in the banned purple band at \(hue)°")
    }
  }

  // MARK: - Static checkers
  //
  // Tripwires, not behavioural coverage, and labelled as such: "which colour token a call site
  // names" is not observable from a running view without a window server and a screenshot diff, and
  // every decision that *is* a value is covered above. They earn their place because each guards a
  // class of mistake with no runtime signal — the app renders either way, it just stops being glass.

  /// The shell surfaces this file guards.
  private static let shellSources = [
    "MainWindow/GlassShellChrome.swift",
    "MainWindow/DesktopHomeView.swift",
    "MainWindow/SidebarView.swift",
    "MainWindow/DesktopTopBar.swift",
    "MainWindow/ChatFirst/ChatFirstShell.swift",
    "MainWindow/ChatFirst/Blocks/ChatFirstContentBlockViews.swift",
    "MainWindow/Pages/ChatPage.swift",
    "MainWindow/Pages/ChatErrorCard.swift",
    "MainWindow/Components/ChatBubble.swift",
    "MainWindow/Components/ChatMessagesView.swift",
    "MainWindow/Components/ChatSessionsSidebar.swift",
    "MainWindow/Components/ChatPromptTimeline.swift",
    "MainWindow/Components/ConversationRowView.swift",
    "MainWindow/Components/CitationCardView.swift",
    "MainWindow/Components/OmiSearchField.swift",
    "MainWindow/SecondBrain/SBComponents.swift",
    "MainWindow/SecondBrain/SBWallpaper.swift",
    "Chat/TypingIndicator.swift",
    "Chat/ChatOmiMark.swift",
  ]

  /// **Two rungs on glass.** The shell and the chat surfaces may not name `Ink.tertiary` — see the
  /// behavioural case above for why, and `Ink.tertiary`'s own documentation for the measurements.
  func testStaticCheckerShellSurfacesNeverSetTheThirdTypeRungOnGlass() throws {
    for path in Self.shellSources {
      XCTAssertFalse(
        try code(path).contains("Ink.tertiary"),
        "\(path) sets Ink.tertiary, which measures under WCAG AA on the panel. Promote to Ink.secondary.")
    }
  }

  /// SwiftUI's `Material` is *within-window* vibrancy: it blurs the app's own content rather than the
  /// desktop, so a surface built on it is not glass at all — it is a frosted hole in the page. There
  /// is one material in this app and `InkGlass` owns it.
  func testStaticCheckerShellSurfacesStackNoSecondMaterial() throws {
    for path in Self.shellSources {
      let body = try code(path)
      for material in ["ultraThinMaterial", "thinMaterial", "regularMaterial", "thickMaterial"] {
        XCTAssertFalse(
          body.contains(material),
          "\(path) uses .\(material). InkGlass's .hudWindow is the only material in this app.")
      }
    }
  }

  /// The legacy dark palette is hardcoded hex on a near-black page. A single surviving reference
  /// renders white-on-white — or an opaque slab — on a light-pinned panel, and nothing logs.
  func testStaticCheckerShellSurfacesNoLongerReadTheDarkPalette() throws {
    for path in Self.shellSources {
      XCTAssertFalse(
        try code(path).contains("OmiColors."),
        "\(path) still reads the dark OmiColors palette, which does not resolve on glass.")
    }
  }

  /// INV-UI-1. macOS offers the banned hue as a system accent, so `Color.accentColor` renders
  /// off-brand on such a machine and no rendered-pixel check catches it — every machine this is
  /// developed on reports blue. `Ink.accent` is a *named* system colour for exactly that reason.
  func testStaticCheckerShellSurfacesNeverReadTheMachinesAccentColour() throws {
    for path in Self.shellSources {
      XCTAssertFalse(
        try code(path).contains("Color.accentColor"),
        "\(path) reads Color.accentColor, which is purple on a machine set to purple. Use Ink.accent.")
    }
  }

  /// Source with comments stripped.
  ///
  /// Scanning raw text would fail on this very file's neighbours: the rules above are *documented*
  /// at the call sites that used to break them ("deliberately not `.ultraThinMaterial`"), and a
  /// checker that cannot tell a prohibition from its violation punishes writing the reason down.
  private func code(_ relativePath: String) throws -> String {
    // omi-test-quality: source-inspection -- static contract; the value decisions are covered
    // behaviorally above, and which token a call site *names* has no runtime signal.
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
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

  private func resolve(_ color: Color) throws -> NSColor {
    // Resolved inside the appearance the glass is pinned to, because that is the appearance the
    // shell actually draws in — reading these on a Dark machine would report the wrong values.
    var resolved: NSColor?
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      resolved = NSColor(color).usingColorSpace(.sRGB)
    }
    return try XCTUnwrap(resolved)
  }
}
