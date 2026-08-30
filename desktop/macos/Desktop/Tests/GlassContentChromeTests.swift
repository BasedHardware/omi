import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The content pages (conversations, memories, tasks, rewind) were restyled onto the glass panel. Two
/// of that restyle's rules are not visible in a screenshot and are exactly the ones a later edit
/// reintroduces by accident:
///
/// - **Glass carries two type rungs, never three.** `Ink.tertiary` measures under WCAG AA on the
///   panel (see `Ink.tertiary`), so a run that was tertiary on the dark chrome is `Ink.secondary`
///   here — promoted, never thinned.
/// - **There is one material in this app**, `InkGlass`. A SwiftUI `Material` inside the panel is a
///   second blur compositing over the first, which is what the pages looked like before.
///
/// The colour decisions live in `PageGlass` as pure functions precisely so the first half of this
/// file can assert them without a window server.
final class GlassContentChromeTests: XCTestCase {

  // MARK: - Behavioral coverage of the chrome's colour and geometry decisions

  func testCardCornerIsTheGlassPanelsOwnCorner() {
    // A card on the glass and the glass it sits on must be cut to the same curve; a page that picks
    // its own radius is a second opinion about what this product's corner is.
    XCTAssertEqual(PageGlass.cardRadius, InkGlass.cornerRadius)
    XCTAssertEqual(PageGlass.cardRadius, 22)
  }

  func testRowAtRestDrawsNothingAndSelectionOutranksHover() {
    // A list of forty filled slabs is a wall, so only the states the pointer or the selection put a
    // row into draw anything at all.
    XCTAssertEqual(PageGlass.rowFill(.rest), Color.clear)
    XCTAssertEqual(PageGlass.rowFill(.hover), Ink.rowFill)
    XCTAssertEqual(PageGlass.rowFill(.selected), Ink.rowFillHover)

    // Selection is the heavier wash: a selected row under the pointer must not dim back.
    XCTAssertNotEqual(PageGlass.rowFill(.selected), PageGlass.rowFill(.hover))
  }

  func testOnlyASelectedRowIsOutlined() {
    // A border that appears under the pointer reads as the row having moved; the hover wash is the
    // whole affordance.
    XCTAssertEqual(PageGlass.rowStroke(.rest), Color.clear)
    XCTAssertEqual(PageGlass.rowStroke(.hover), Color.clear)
    XCTAssertEqual(PageGlass.rowStroke(.selected), Ink.separator)
  }

  func testActiveChipCarriesTheHeavierWashAndEdge() {
    // The filter rows on Conversations, Memories and Tasks all lost their active state in the
    // migration when two different dark tokens collapsed onto one glass wash. The chip's state has
    // to be a visible difference, not just a different call site.
    XCTAssertNotEqual(PageGlass.chipFill(isActive: true), PageGlass.chipFill(isActive: false))
    XCTAssertNotEqual(PageGlass.chipStroke(isActive: true), PageGlass.chipStroke(isActive: false))

    // Assert the ordering, not the identity of the token that produces it. Pinning the active
    // fill to a named token is what let the defect through the first time: two tokens collapsed
    // onto one wash and the assertion still passed. What has to be true is that "on" is visibly
    // heavier than "off" — so measure it.
    func alpha(_ color: Color) -> CGFloat {
      NSColor(color).usingColorSpace(.sRGB)?.alphaComponent ?? 0
    }
    let rest = alpha(PageGlass.chipFill(isActive: false))
    let active = alpha(PageGlass.chipFill(isActive: true))
    XCTAssertGreaterThan(
      active, rest + 0.02,
      "The active chip must be visibly heavier than the resting one, not merely a different token.")
  }

  func testStateColoursAreNamedSystemColoursAndNotTheErrorRed() {
    // "Overdue" and "starred" are a step below an error and must not borrow the one colour this app
    // raises its voice with.
    XCTAssertNotEqual(PageGlass.warning, Ink.errorRed)
    XCTAssertEqual(PageGlass.warning, Color(nsColor: .systemOrange))
    XCTAssertEqual(PageGlass.starred, PageGlass.warning)
  }

  func testPrimaryFilledActionsUseTheInverseSurfaceInk() {
    XCTAssertEqual(PageGlass.primaryActionLabel, Ink.surface)
    XCTAssertNotEqual(PageGlass.primaryActionLabel, Ink.primary)
  }

  func testSpeakerTintsAreWashesRatherThanTheOldOpaqueNearBlacks() {
    // The dark chrome's six speaker colours were hand-mixed near-blacks that were only ever
    // distinguishable because the page behind them was `0x0F0F0F`. On glass a bubble has to stay a
    // tinted piece of the panel with `Ink.primary` legible on top, so every tint is a low-alpha
    // wash — and there are still six, because the index is `speakerId % count`.
    XCTAssertEqual(PageGlass.speakerTints.count, 6)
    for tint in PageGlass.speakerTints {
      let resolved = NSColor(tint).usingColorSpace(.sRGB)
      XCTAssertNotNil(resolved)
      XCTAssertLessThanOrEqual(resolved?.alphaComponent ?? 1, 0.2)
    }
  }

  // MARK: - Static checker (not behavioral coverage)
  //
  // These read the restyled sources. They are tripwires on a rule the compiler cannot express, not
  // evidence that anything renders correctly — the assertions above are the behavioral half.

  /// Every content-page source this restyle owns, relative to `Sources/`.
  ///
  /// `GlassContentChrome.swift` is deliberately absent: it is where the rules below are *written
  /// down*, so its prose names the very tokens the pages may not use, and a substring checker cannot
  /// tell a prohibition from a violation.
  private static let restyledSources: [String] = [
    "MainWindow/Pages/ConversationsPage.swift",
    "MainWindow/Pages/ConversationDetailView.swift",
    "MainWindow/Pages/MemoriesPage.swift",
    "MainWindow/Pages/PersonaPage.swift",
    "MainWindow/Pages/TasksPage.swift",
    "MainWindow/Pages/GoalsHistoryPage.swift",
    "MainWindow/Pages/MemoryExportDestinationSheet.swift",
    "MainWindow/Pages/MemoryGraph/CanonicalMemoryAtlasView.swift",
    "MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift",
    "MainWindow/Pages/MemoryGraph/MemoryAtlasTerritoryLabels.swift",
    "MainWindow/Components/ConversationListView.swift",
    "MainWindow/Components/LiveTranscriptView.swift",
    "MainWindow/Components/SpeakerBubbleView.swift",
    "MainWindow/Components/TranscriptDetailView.swift",
    "Rewind/UI/RewindPage.swift",
    "Rewind/UI/RewindSurfaceLayout.swift",
    "Rewind/UI/RewindTimelineView.swift",
    "Rewind/UI/SearchResultsFilmstrip.swift",
    "Rewind/UI/ScreenshotThumbnailView.swift",
  ]

  private func sourceURL(_ relativePath: String) -> URL {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    return
      testsDirectory
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
  }

  /// **A deleted page must fail this suite with an instruction, not an `NSCocoaErrorDomain` throw.**
  ///
  /// This has now bitten twice on the same branch: removing `FocusPage.swift` and then
  /// `InsightPage.swift` each left this list naming a file that no longer existed. `String(contentsOf:)`
  /// *throws* on a missing file, which aborts the test case at its first entry with "no such file"
  /// and no hint that the fix is one line in an array two hundred lines away — and, worse, aborts
  /// before checking any of the pages that do still exist, so the guard silently stops guarding.
  ///
  /// Checking first turns that into a named failure that says what to do.
  private func source(_ relativePath: String) throws -> String {
    let url = sourceURL(relativePath)
    guard FileManager.default.fileExists(atPath: url.path) else {
      XCTFail(
        """
        restyledSources names \(relativePath), which no longer exists. If the page was deleted, \
        delete its line here too — a guard that names a missing file stops checking the pages that \
        remain rather than reporting the deletion.
        """)
      throw CocoaError(.fileNoSuchFile)
    }
    // omi-test-quality: source-inspection -- static contract: "which colour token a call site names"
    // is not observable from a running view without a window server and a screenshot diff, and the
    // decisions that *are* values are covered behaviorally above.
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// The same claim once, up front, so a deletion is reported as one clear failure rather than as
  /// whichever of the checkers below happened to run first.
  func testEveryPageThisGuardNamesStillExists() {
    for path in Self.restyledSources {
      XCTAssertTrue(
        FileManager.default.fileExists(atPath: sourceURL(path).path),
        "restyledSources names \(path), which is not on disk — remove the line or restore the page")
    }
  }

  func testStaticCheckerContentPagesNeverSetTheThirdTypeRungOnGlass() throws {
    for path in Self.restyledSources {
      let body = try source(path)
      XCTAssertFalse(
        body.contains("Ink.tertiary"),
        """
        \(path) sets Ink.tertiary. Glass carries two rungs: that colour measures under WCAG AA on \
        the panel, so promote the run to Ink.secondary (see Ink.tertiary's documentation).
        """
      )
    }
  }

  func testStaticCheckerContentPagesNeverStackASecondMaterialInsideTheGlass() throws {
    for path in Self.restyledSources {
      let body = try source(path)
      for material in ["ultraThinMaterial", "thinMaterial", "regularMaterial", "thickMaterial"] {
        XCTAssertFalse(
          body.contains(material),
          "\(path) uses .\(material). InkGlass is the only material in this app."
        )
      }
    }
  }

  func testStaticCheckerContentPagesNeverReadTheMachinesAccentColour() throws {
    // INV-UI-1. macOS offers the banned hue as a system accent, so `Color.accentColor` renders
    // off-brand on such a machine and no rendered-pixel check catches it — every machine this is
    // developed on reports blue. `Ink.accent` is a *named* system colour for exactly this reason.
    for path in Self.restyledSources {
      let body = try source(path)
      XCTAssertFalse(
        body.contains("Color.accentColor"),
        "\(path) reads Color.accentColor, which is purple on a machine set to purple. Use Ink.accent."
      )
    }
  }

  func testStaticCheckerFolderColourPickerOffersNoPurpleSwatch() throws {
    // INV-UI-1 again, and the case the ratchet was blindest to: a hue the *product* ships in a
    // swatch grid is the UI choosing it, not the user.
    let body = try source("MainWindow/Components/FolderManagementViews.swift")
    XCTAssertFalse(body.contains("\"Purple\""))
    XCTAssertFalse(body.contains("#A855F7"))
    XCTAssertFalse(body.contains("#6366F1"))
  }
}
