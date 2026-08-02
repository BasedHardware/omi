import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// The Rewind window's pure decisions, tested where they are decidable without a screen: the brand
/// rule on segment colour, the Vision coordinate flip, and the honest-resolution rule behind the
/// "open externally" button.
final class RewindTests: XCTestCase {

    // MARK: - Segment colour

    /// The reason the palette computes FNV-1a itself instead of using `String.hashValue`.
    ///
    /// Swift seeds `hashValue` per process, so the implementation this was ported from redraws every
    /// app in a different colour on every launch — which destroys the only thing a per-app colour is
    /// for. This asserts the hash is a fixed function of its input by pinning known values; if
    /// somebody swaps it back to `hashValue`, these constants stop matching.
    func testStableHashIsPinnedAndNotProcessSeeded() {
        // FNV-1a 64-bit offset basis, i.e. the empty string.
        XCTAssertEqual(RewindPalette.stableHash(""), 0xcbf2_9ce4_8422_2325)
        // Standard FNV-1a test vectors.
        XCTAssertEqual(RewindPalette.stableHash("a"), 0xaf63_dc4c_8601_ec8c)
        XCTAssertEqual(RewindPalette.stableHash("foobar"), 0x85944_171_f73967e8 & 0xffff_ffff_ffff_ffff)
    }

    func testHueIsStableAcrossCallsAndCaseInsensitive() {
        let first = RewindPalette.hue(forApp: "Google Chrome")
        XCTAssertEqual(first, RewindPalette.hue(forApp: "Google Chrome"))
        // One app, one colour: a stretch of a day must not split in two because a title was cased
        // differently.
        XCTAssertEqual(first, RewindPalette.hue(forApp: "google chrome "))
    }

    /// INV-UI-1: never purple, anywhere.
    ///
    /// Asserted over the app names actually present in the real database on this machine plus a large
    /// generated sweep, because the failure mode being guarded is statistical — a hash over a full
    /// 360° wheel emits purple for roughly one name in six, so a handful of hand-picked names would
    /// pass a broken implementation.
    func testNoAppNameEverProducesPurple() {
        let realAppNames = [
            "Arc", "Cursor", "Warp", "QuickTime Player", "Preview", "Google Chrome", "Telegram",
            "ChatGPT Atlas", "Claude", "Messages", "Finder", "omi-people-intel", "Notes",
            "System Settings", "Terminal", "Xcode", "Slack", "Safari", "Mail", "Music",
            "Activity Monitor", "Unknown",
        ]
        var names = realAppNames
        for index in 0..<20_000 { names.append("generated-app-\(index)") }

        for name in names {
            let hue = RewindPalette.hue(forApp: name)
            XCTAssertGreaterThanOrEqual(hue, 0, "hue below the wheel for \(name)")
            XCTAssertLessThan(
                hue, RewindPalette.hueCeiling,
                "\(name) produced hue \(hue), which is in the violet/purple band")
            // The band this exists to exclude, stated independently of the ceiling constant so
            // raising that constant cannot silently re-admit purple.
            XCTAssertFalse(
                (250.0...330.0).contains(hue), "\(name) produced a purple/magenta hue: \(hue)")
        }
    }

    /// The colour is a real colour rather than a semantic that would collapse to the same value for
    /// every app — and two different apps must actually differ.
    func testDifferentAppsGetDifferentHues() {
        let hues = ["Arc", "Cursor", "Warp", "Messages", "Finder"].map(RewindPalette.hue(forApp:))
        XCTAssertEqual(Set(hues).count, hues.count, "distinct apps must be distinguishable")
    }

    // MARK: - Live Text geometry

    /// Vision measures from the bottom-left; every drawing system here measures from the top-left.
    /// The flip is `1 - y - height`, and the classic bug is writing `1 - y`, which puts every
    /// highlight exactly one box-height too high.
    func testScreenRectFlipsVisionsBottomLeftOrigin() {
        // A box occupying the bottom-left tenth of the image.
        let block = LiveTextBlock(
            id: 0, text: "hi", boundingBox: CGRect(x: 0, y: 0, width: 0.1, height: 0.1))
        let rect = block.screenRect(for: CGSize(width: 1000, height: 1000))

        XCTAssertEqual(rect.minX, 0, accuracy: 0.001)
        // Bottom in Vision space becomes bottom in top-left space: y = 1 - 0 - 0.1 = 0.9.
        XCTAssertEqual(rect.minY, 900, accuracy: 0.001)
        XCTAssertEqual(rect.width, 100, accuracy: 0.001)
        XCTAssertEqual(rect.height, 100, accuracy: 0.001)
    }

    func testScreenRectPlacesATopBoxAtTheTop() {
        let block = LiveTextBlock(
            id: 0, text: "title", boundingBox: CGRect(x: 0, y: 0.9, width: 1, height: 0.1))
        let rect = block.screenRect(for: CGSize(width: 800, height: 600))

        // y = 1 - 0.9 - 0.1 = 0, i.e. flush with the top edge.
        XCTAssertEqual(rect.minY, 0, accuracy: 0.001)
        XCTAssertEqual(rect.height, 60, accuracy: 0.001)
    }

    /// The wrong flip and the right one disagree for any box that is not vertically centred, which is
    /// what makes this worth pinning rather than eyeballing.
    func testFlipIsNotTheNaiveOneMinusY() {
        let block = LiveTextBlock(
            id: 0, text: "x", boundingBox: CGRect(x: 0, y: 0.2, width: 0.5, height: 0.3))
        let correct = block.screenRect(for: CGSize(width: 100, height: 100)).minY
        let naive = (1.0 - 0.2) * 100

        XCTAssertEqual(correct, 50, accuracy: 0.001)
        XCTAssertNotEqual(correct, naive, accuracy: 0.001)
    }

    // MARK: - Open externally

    private func frame(title: String?, app: String = "Warp") -> RewindFrame {
        RewindFrame(
            id: 1, capturedAt: 0, appName: app, windowTitle: title,
            imagePath: "/tmp/frame.heic")
    }

    /// The button must be **absent**, not disabled, for a frame that resolves to nothing — which on
    /// the real database is 99.9% of them.
    func testOrdinaryWindowTitleResolvesToNothing() {
        XCTAssertNil(OpenExternally.target(for: frame(title: "zsh")))
        XCTAssertNil(OpenExternally.target(for: frame(title: nil)))
        XCTAssertNil(OpenExternally.target(for: frame(title: "✳ Claude Code")))
        XCTAssertNil(OpenExternally.target(for: frame(title: "/nonexistent/path/for/tests")))
    }

    /// The regression this file exists for. Arc's window title is the *page* title, and on this
    /// machine 73 frames carry a `t.co` link quoted inside a tweet's text. Resolving that URL and
    /// opening it navigates somewhere the user never went — a confidently wrong answer, which is
    /// worse than a hidden button. No URL in a title may ever produce a target.
    func testAUrlQuotedInsideAPageTitleIsNeverOpened() {
        let realTitle = """
            Aidan Guo on X: "A billion people produce the most valuable dataset in the world every \
            day – and delete it every night. We're recording it. Introducing @AttentionInc \
            https://t.co/wT0pLYHt01" / X
            """
        XCTAssertNil(
            OpenExternally.target(for: frame(title: realTitle, app: "Arc")),
            "a link drawn inside a page is not that page's address")
        XCTAssertNil(OpenExternally.target(for: frame(title: "https://example.com", app: "Arc")))
    }

    /// What genuinely does resolve: a terminal whose title is its working directory. This is the app
    /// declaring the window's subject rather than text that happened to be on screen.
    func testATitleThatIsAnExistingDirectoryResolvesToThatFolder() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-open-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let target = OpenExternally.target(for: frame(title: directory.path))

        XCTAssertEqual(target, .folder(directory))
        XCTAssertEqual(target?.symbolName, "folder")
    }

    func testATitleThatIsAnExistingFileResolvesToThatFile() throws {
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-open-\(UUID().uuidString).txt")
        try Data("x".utf8).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }

        let target = OpenExternally.target(for: frame(title: file.path))

        XCTAssertEqual(target, .file(file))
        XCTAssertEqual(target?.symbolName, "doc")
    }

    /// `~` and `~/…` are how shells write a home-relative directory, and Warp's real titles use them.
    func testHomeRelativeTitleIsExpanded() {
        let target = OpenExternally.target(for: frame(title: "~"))
        XCTAssertEqual(target, .folder(URL(fileURLWithPath: NSHomeDirectory())))
    }

    /// A path mentioned inside a sentence is not a window showing that path. Only whole
    /// separator-delimited segments count, which is exactly what keeps the URL-in-a-title case out.
    func testAPathEmbeddedInProseIsNotResolved() {
        XCTAssertNil(
            OpenExternally.target(
                for: frame(title: "I was reading \(NSHomeDirectory()) earlier today")))
    }

    /// Editors title windows "file — project"; both sides are tried, so the real path is found
    /// wherever the app put it.
    func testEitherSideOfASeparatorIsTried() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-open-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        XCTAssertEqual(
            OpenExternally.target(for: frame(title: "main.swift — \(directory.path)")),
            .folder(directory))
        XCTAssertEqual(
            OpenExternally.target(for: frame(title: "\(directory.path) — main.swift")),
            .folder(directory))
    }

    // MARK: - Brand: no hardcoded light-only colours
    //
    // A static tripwire, not behavioural coverage — labelled as such. It guards a property that is
    // invisible in the appearance a developer happens to be running: the implementation this was
    // ported from is hardcoded dark, with dozens of `Color.white.opacity(…)` and `NSColor(white:…)`
    // values that vanish on a light window. Catching a reintroduced one needs a source scan, because
    // rendering in one appearance cannot see it.

    func testRewindSourcesUseNoLightOnlyColourLiterals() throws {
        let directory = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Sources/ContextApp/Rewind", isDirectory: true)

        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "swift" }
        XCTAssertFalse(files.isEmpty, "the Rewind sources moved; update this scan")

        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            for (number, line) in source.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
                // Comments explain *why* the two intentional cases are correct, so they are not code.
                let code = line.trimmingCharacters(in: .whitespaces)
                guard !code.hasPrefix("//"), !code.hasPrefix("///") else { continue }

                XCTAssertFalse(
                    code.contains("NSColor(white:"),
                    "\(file.lastPathComponent):\(number + 1) uses NSColor(white:), which is light-only")
                XCTAssertFalse(
                    code.contains("Color.white.opacity") || code.contains(".white.opacity"),
                    "\(file.lastPathComponent):\(number + 1) uses a white opacity wash, which is light-only")
                XCTAssertFalse(
                    code.lowercased().contains("purple"),
                    "\(file.lastPathComponent):\(number + 1) mentions purple (INV-UI-1)")
                XCTAssertFalse(
                    code.contains("preferredColorScheme(.dark)"),
                    "\(file.lastPathComponent):\(number + 1) forces dark; the window must follow the system")
            }
        }
    }
}
