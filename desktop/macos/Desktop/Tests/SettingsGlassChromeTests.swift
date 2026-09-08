import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Guards for the Settings / Apps / Permissions surfaces after they were moved off the dark
/// `OmiColors` palette and onto the glass design system.
///
/// Two kinds of check live here and they are labelled as such, because they are not worth the same:
/// the colour and metric cases exercise the real values production draws with, and the source scans
/// at the bottom are **static checkers** — tripwires for a class of mistake that has no runtime
/// signal, not behavioural coverage.
final class SettingsGlassChromeTests: XCTestCase {

  // MARK: - The one colour added to the palette

  /// `SettingsInk.notice` exists because `Ink` has three states and Settings needs a fourth:
  /// attention without failure. This asserts it is genuinely a fourth and not a second spelling of
  /// one that already exists — a token that measures the same as `Ink.errorRed` is not a state, it is
  /// the error colour with a second name, and every "not granted" chip would then be crying wolf.
  func testNoticeIsDistinctFromTheErrorAndAccentColours() throws {
    let notice = try XCTUnwrap(NSColor(SettingsInk.notice).usingColorSpace(.sRGB))
    let error = try XCTUnwrap(NSColor(Ink.errorRed).usingColorSpace(.sRGB))
    let accent = try XCTUnwrap(NSColor(Ink.accent).usingColorSpace(.sRGB))

    // Hue separation rather than "not equal": two oranges a hundredth apart would pass equality and
    // still be indistinguishable to the person the state is for.
    XCTAssertGreaterThan(
      hueDistanceDegrees(notice, error), 15,
      "notice and error read as the same colour — a caution state must not look like a failure")
    XCTAssertGreaterThan(
      hueDistanceDegrees(notice, accent), 15,
      "notice and accent read as the same colour — caution must not look like selection")
  }

  /// INV-UI-1: purple is off-brand, and a colour added to the palette is exactly where it would slip
  /// back in. Every colour these surfaces are allowed to reach for is checked, not just the new one —
  /// the invariant is about the palette, not about the token that happened to be added last.
  ///
  /// The banned band is 250°–330°, which covers violet through magenta.
  func testNoPaletteColourOnTheseSurfacesIsPurple() throws {
    let palette: [(String, Color)] = [
      ("SettingsInk.notice", SettingsInk.notice),
      ("Ink.accent", Ink.accent),
      ("Ink.errorRed", Ink.errorRed),
      ("Ink.listeningGreen", Ink.listeningGreen),
      ("Ink.primary", Ink.primary),
      ("Ink.secondary", Ink.secondary),
      ("Ink.surface", Ink.surface),
    ]

    for (name, color) in palette {
      let resolved = try XCTUnwrap(NSColor(color).usingColorSpace(.sRGB), name)
      // A near-neutral has no meaningful hue to judge; `labelColor` and `controlBackgroundColor`
      // land here, and a hue reading off an almost-grey is noise rather than a colour decision.
      guard resolved.saturationComponent > 0.15 else { continue }
      let hue = resolved.hueComponent * 360
      XCTAssertFalse(
        (250...330).contains(hue),
        "\(name) resolves to hue \(hue)° — INV-UI-1 bans purple in UI")
    }
  }

  // MARK: - Metrics

  /// The row divider starts where the copy does, and it is *derived* from the row's own geometry
  /// rather than typed as a literal. A hand-typed 49 is a number that silently stops matching the
  /// row the first time the icon tile changes size.
  func testRowDividerInsetTracksTheRowsIconColumn() {
    XCTAssertEqual(
      SettingsGlassMetrics.rowDividerInset,
      SettingsGlassMetrics.rowHorizontalPadding + SettingsGlassMetrics.iconTile
        + SettingsGlassMetrics.rowContentSpacing)
    // The compact settings kit uses 10 + 26 + 11, keeping the divider aligned while reclaiming 2 pt.
    XCTAssertEqual(SettingsGlassMetrics.rowDividerInset, 47)
  }

  /// A card drawn inside the glass must round *tighter* than the glass does.
  ///
  /// At the panel's own 22 the card stops reading as content on a pane and starts reading as a second
  /// pane — which is the specific way a nested-card layout stops looking like one surface.
  func testCardCornerIsStrictlyInsideThePanelCorner() {
    XCTAssertLessThan(SettingsGlassMetrics.cardRadius, InkGlass.cornerRadius)
    XCTAssertLessThan(SettingsGlassMetrics.controlRadius, SettingsGlassMetrics.cardRadius)
    XCTAssertLessThan(SettingsGlassMetrics.pillRadius, SettingsGlassMetrics.controlRadius)
  }

  // MARK: - Static checkers
  //
  // Source scans, not behavioural coverage. They exist because both failures below are invisible at
  // runtime on the machine anyone develops on: the dark palette still compiles and still renders
  // (white on white), and the banned type rung is legible over a light desktop and only fails over a
  // dark one.

  /// **Static checker.** No restyled surface still reaches for the dark palette.
  ///
  /// `OmiColors` is a fixed dark ladder — `textPrimary` is `#FFFFFF`. On glass, which is pinned to a
  /// light appearance, one of those left behind is white type on a white ground: it compiles, it
  /// draws, and it is invisible. Nothing at runtime reports it.
  func testRestyledSurfacesDoNotUseTheDarkPalette() throws {
    for (path, source) in try restyledSources() {
      XCTAssertFalse(
        strippingComments(source).contains("OmiColors."),
        "\(path) still references the dark OmiColors palette; on light glass those values are "
          + "invisible. Use the Ink tokens.")
    }
  }

  /// **Static checker.** No restyled surface sets type in `Ink.tertiary`.
  ///
  /// The rule is arithmetic rather than taste, and it is stated on `Ink.tertiary` itself: the ground
  /// under dark type can only fall as far as the faintest rung set on it survives, so a third rung
  /// costs roughly half the panel's transparency (17% passthrough versus 34.8%) to buy a step of
  /// hierarchy. These surfaces carry two rungs; a `tertiary` promotes to `secondary`.
  func testRestyledSurfacesCarryOnlyTwoTypeRungs() throws {
    for (path, source) in try restyledSources() {
      XCTAssertFalse(
        strippingComments(source).contains("Ink.tertiary"),
        "\(path) uses Ink.tertiary, which may not go on glass — promote it to Ink.secondary. "
          + "See the doc comment on Ink.tertiary for why this is not a style preference.")
    }
  }

  // MARK: - Helpers

  /// Every source file this restyle covers, read off disk.
  ///
  /// Listed rather than globbed: a glob would quietly stop covering a file that moved, and would
  /// quietly start covering surfaces that are *not* on glass and are entitled to the third rung.
  private func restyledSources() throws -> [(String, String)] {
    let sourcesDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Desktop/Tests
      .deletingLastPathComponent()  // Desktop
      .appendingPathComponent("Sources")

    let relativePaths = [
      "MainWindow/Pages/SettingsPage.swift",
      "MainWindow/SettingsSidebar.swift",
      "MainWindow/Pages/ShortcutsSettingsSection.swift",
      "MainWindow/Pages/PermissionsPage.swift",
      "MainWindow/Pages/AppsPage.swift",
      "MainWindow/Pages/AppsPageHeaderControls.swift",
      "MainWindow/Pages/AgentConnectPickerSheet.swift",
      "MainWindow/Pages/ManualInstallationDisclosure.swift",
      "ConnectorBrandIcon.swift",
      "BrowserExtensionSetup.swift",
      "FileIndexing/FileIndexingView.swift",
      "WAL/StorageSyncView.swift",
      "MainWindow/Pages/Settings/Components/SettingsGlassKit.swift",
      "MainWindow/Pages/Settings/Components/SettingsContentView+Controls.swift",
      "MainWindow/Pages/Settings/Components/SettingsContentView+BillingHelpers.swift",
      "MainWindow/Pages/Settings/Components/SettingsContentView+SettingsUpdates.swift",
      "MainWindow/Pages/Settings/Components/AppRuleEditorView.swift",
      "MainWindow/Pages/Settings/Components/SearchableDropdown.swift",
      "MainWindow/Pages/Settings/Components/BillingWebFlow.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+General.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+Rewind.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+Transcription.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+Advanced.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+Assistants.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+AccountBilling.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+Integrations.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+DeveloperKeys.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+FloatingBarAndChat.swift",
      "MainWindow/Pages/Settings/Sections/SettingsContentView+NotificationsPrivacy.swift",
      "MainWindow/Pages/Settings/Sections/MicrophonePickerCard.swift",
    ]

    return try relativePaths.map { relative in
      let url = sourcesDir.appendingPathComponent(relative)
      // A missing file must fail loudly rather than pass vacuously: a scan over zero files is the
      // shape these checks fail in, and it looks exactly like success.
      // omi-test-quality: source-inspection -- static contract: which token a call site names is a source fact; a rendered view cannot report it.
      let source = try String(contentsOf: url, encoding: .utf8)
      return (relative, source)
    }
  }

  /// The source with its comments removed, so the scans above read code rather than prose.
  ///
  /// Without this, documenting the rule breaks the check that enforces it — `SettingsGlassKit`'s
  /// header states "`Ink.tertiary` may never go on glass" and would fail the very test it explains.
  /// A guard that punishes naming the thing it bans teaches people to stop writing the explanation,
  /// which costs more than the guard is worth.
  ///
  /// Deliberately not a Swift lexer: it drops `//` runs and `/* … */` blocks, which is every comment
  /// in these files. The failure mode is a string literal containing `//` losing its tail, and that
  /// can only ever make a scan *miss* a hit — a false pass on a token nobody writes inside a URL.
  private func strippingComments(_ source: String) -> String {
    var withoutBlocks = ""
    var rest = Substring(source)
    while let open = rest.range(of: "/*") {
      withoutBlocks += rest[..<open.lowerBound]
      guard let close = rest.range(of: "*/", range: open.upperBound..<rest.endIndex) else {
        rest = rest[rest.endIndex...]
        break
      }
      rest = rest[close.upperBound...]
    }
    withoutBlocks += rest

    return
      withoutBlocks
      .split(separator: "\n", omittingEmptySubsequences: false)
      .map { line -> Substring in
        guard let comment = line.range(of: "//") else { return line }
        return line[..<comment.lowerBound]
      }
      .joined(separator: "\n")
  }

  /// The shorter way round the hue circle, in degrees.
  private func hueDistanceDegrees(_ lhs: NSColor, _ rhs: NSColor) -> CGFloat {
    let raw = abs(lhs.hueComponent - rhs.hueComponent) * 360
    return min(raw, 360 - raw)
  }
}
