import AppKit
import CoreText
import SwiftUI
import XCTest
@testable import ContextApp

final class MenuBarPresentationTests: XCTestCase {
    // MARK: - The mark

    /// The menu bar mark must stay a template image.
    ///
    /// A non-template mark carries its own colour, which means it does not invert for a light or
    /// dark menu bar and does not dim with the status item when the app is inactive — it shipped
    /// that way once, hardcoded to a brand clay, and looked wrong on half the machines it ran on.
    /// `isTemplate` is the whole of the fix, so it is the thing asserted.
    @MainActor
    func testMenuBarMarkIsATemplateSoTheSystemOwnsItsColour() {
        XCTAssertTrue(ContextMark.menuBar.isTemplate)
        XCTAssertTrue(ContextMark.menuBarPaused.isTemplate)
        // Drawn at the size it is displayed: macOS scales template images down cleanly, not up.
        XCTAssertEqual(ContextMark.menuBar.size, ContextMark.menuBarSize)
        XCTAssertEqual(ContextMark.menuBarPaused.size, ContextMark.menuBarSize)
    }

    // MARK: - Type

    /// Registers the bundled faces the way the app shell does, so the type assertions below exercise
    /// the real resolution path rather than a stand-in.
    ///
    /// The test bundle is not the app bundle, so `Bundle.main.resourceURL` cannot be used here; the
    /// files are found relative to this source file instead. `CTFontManagerRegisterFontsForURL`
    /// returns false when a face is already registered in the process, so the return value is
    /// deliberately ignored and resolution is what gets checked.
    private static let bundledFacesRegistered: Bool = {
        let fonts = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Resources/Fonts", isDirectory: true)
        let contents = (try? FileManager.default.contentsOfDirectory(at: fonts, includingPropertiesForKeys: nil)) ?? []
        for url in contents where ["otf", "ttf"].contains(url.pathExtension.lowercased()) {
            var error: Unmanaged<CFError>?
            _ = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error)
            error?.release()
        }
        InkFonts.invalidate()
        return !contents.isEmpty
    }()

    /// Every bundled face has to resolve by its **PostScript** name.
    ///
    /// That name is the only reliable handle — the family/weight route does not dependably reach
    /// these faces — and a name that does not resolve fails silently, degrading the whole display
    /// ladder to SF Pro with nothing on screen to say so. Renaming a file or shipping a differently
    /// named cut has to fail here instead.
    func testEveryBundledDisplayFaceResolvesByItsPostScriptName() {
        XCTAssertTrue(Self.bundledFacesRegistered, "no font files found next to the package")
        for weight: RundeWeight in [.regular, .medium, .semiBold, .bold] {
            XCTAssertNotNil(NSFont(name: weight.fontName, size: 12), weight.fontName)
        }
        XCTAssertTrue(InkFonts.bundledFacesAvailable)
    }

    /// The display/reading split: Open Runde above the threshold, SF Pro below it, decided by the
    /// role's own size and never by a flag at a call site.
    func testDisplayRolesUseOpenRundeAndReadingRolesStayOnSFPro() {
        XCTAssertTrue(Self.bundledFacesRegistered)

        for role in [InkType.introHero, InkType.stepHeadline, InkType.firstTitle] {
            XCTAssertGreaterThanOrEqual(role.size, Font.inkDisplayThreshold)
            XCTAssertTrue(role.usesBundledFace, "display role at \(role.size) pt is not on Open Runde")
        }

        for role in [InkType.prose, InkType.rowCopy, InkType.statusLabel, InkType.buttonLabel] {
            XCTAssertLessThan(role.size, Font.inkDisplayThreshold)
            XCTAssertFalse(role.usesBundledFace, "reading role at \(role.size) pt should be SF Pro")
        }
    }

    /// A missing or unregistered face degrades to SF Pro at the same size and weight rather than
    /// crashing or resolving to something arbitrary. The app is still usable in San Francisco.
    func testAnUnregisteredFaceFallsBackToTheSystemFontAtTheSameMetrics() {
        let resolved = InkFonts.resolve(
            "NoSuchFace-Regular", size: 32, weight: .semibold, appKitWeight: .semibold)

        XCTAssertFalse(resolved.isCustom)
        XCTAssertEqual(resolved.metrics.pointSize, 32)
        XCTAssertEqual(
            InkFonts.naturalLineHeight(resolved.metrics),
            InkFonts.naturalLineHeight(NSFont.systemFont(ofSize: 32, weight: .semibold)))
    }

    // MARK: - Connector copy

    func testConnectorSetupCopyCallsOutLocalConfigurationWithoutClaimingAClaudeAccount() {
        let copy = OnboardingConnectorCopy(surfaces: [])

        XCTAssertEqual(copy.title, "Bring Claude in")
        XCTAssertEqual(copy.action, "Set up Claude")
        XCTAssertTrue(copy.detail.contains("local connector"))
        XCTAssertFalse(copy.detail.localizedCaseInsensitiveContains("account"))
        XCTAssertFalse(copy.detail.localizedCaseInsensitiveContains("connected"))
    }

    func testConnectorSetupCopyNamesOnlyLocallyConfiguredSurfaces() {
        let copy = OnboardingConnectorCopy(surfaces: [.claudeCode])

        XCTAssertEqual(copy.title, "Claude Code is ready")
        XCTAssertEqual(copy.action, "Continue")
        XCTAssertEqual(copy.detail, "The local connector is configured for Claude Code.")
    }

}