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

    // MARK: - INV-UI-1, decided on the pixel
    //
    // ## Why the assertions this replaces passed a violet disc
    //
    // They were `hue < RewindPalette.hueCeiling` (250) and `!(250...330).contains(hue)`. The second
    // was written to be a second opinion — "stated independently of the ceiling constant" — but it
    // took the *same* boundary as its lower bound, so it was the same opinion twice, and 249.9°
    // satisfied both. That is the colour that shipped: sRGB (101, 86, 179), a lavender site disc in
    // the search panel, measured on screen at (134, 121, 191) after compositing. A hue in degrees is
    // a number; "looks violet" is a property of the pixel, and no inequality between two constants
    // can stand in for it — a wrong constant is invisible to a test whose only vocabulary is that
    // constant. So the guard below renders the colour and asks the pixel.
    //
    // ## What "looks violet" is, structurally
    //
    // Stated once, in `BrandColourGuard.swift`, and shared with the accent guard in `SettingsTests`
    // — which had the same defect with different constants. Short version: violet is the hue family
    // the eye reads as a mixture of the spectrum's two ends, `min(R, B) > G`, and `BrandColour`
    // measures how far a rendered pixel sits clear of it.

    /// The guard, over the palette's **entire** output domain rather than a sample of it.
    ///
    /// Both rendering paths are checked because both ship: `nsColor` draws the timeline segments and
    /// their badges, `color` draws the search panel's site discs — which is the surface the violet
    /// was seen on — and the frame border. They are separate constructors in separate colour spaces,
    /// so agreeing about one of them is not evidence about the other.
    func testEveryColourThePaletteCanEmitReadsAsBlueNotViolet() {
        // `BrandColour` skips near-greys, which have no hue to be wrong about. A palette that went
        // grey would therefore be *skipped* rather than checked, so the rule below would stop being
        // a rule silently. It cannot: this palette's saturation is fixed and well above the line.
        XCTAssertGreaterThan(
            RewindPalette.saturation, BrandColour.neutralSaturation,
            "a palette this desaturated would be waved through as neutral, not checked")

        var maxHue = 0.0
        for bucket in 0..<RewindPalette.hueBuckets {
            let hue = RewindPalette.hue(bucket: bucket)
            maxHue = max(maxHue, hue)
            assertReadsOnBrand(RewindPalette.nsColor(hue: hue), "bucket \(bucket) (hue \(hue)), AppKit")
            assertReadsOnBrand(NSColor(RewindPalette.color(hue: hue)), "bucket \(bucket) (hue \(hue)), SwiftUI")
        }
        // Reported rather than asserted as a bound: the property above is the rule, this is what the
        // arc actually reached while satisfying it.
        XCTAssertLessThan(maxHue, RewindPalette.hueCeiling)
        XCTAssertGreaterThan(maxHue, RewindPalette.hueCeiling - 1, "the arc must actually be used")
    }

    /// The guard's own regression test: it must reject the colour that shipped.
    ///
    /// Without this, "the palette is clean" and "the guard cannot see violet" are indistinguishable —
    /// which is precisely how the old assertion looked healthy for as long as it did.
    func testTheGuardRejectsTheVioletThatShipped() {
        // 249.9° is what the 250° ceiling could emit, and did — on both rendering paths.
        assertReadsOffBrand(RewindPalette.nsColor(hue: 249.9), "the shipped violet, AppKit")
        assertReadsOffBrand(NSColor(RewindPalette.color(hue: 249.9)), "the shipped violet, SwiftUI")

        // The pixel as measured on screen: the same colour after compositing, which is what a
        // screenshot of the search panel gives you.
        assertReadsOffBrand(
            NSColor(srgbRed: 134 / 255, green: 121 / 255, blue: 191 / 255, alpha: 1),
            "the measured on-screen pixel")

        // Blend invariance, stated as a test rather than as a claim: the same colour at 45% over a
        // white ground is a much paler lavender and is still caught.
        assertReadsOffBrand(
            NSColor(
                srgbRed: 0.45 * 101 / 255 + 0.55, green: 0.45 * 86 / 255 + 0.55,
                blue: 0.45 * 179 / 255 + 0.55, alpha: 1),
            "a washed-out lavender")

        // The margin's boundary, pinned from both sides. 226° is *outside* the wedge — the old
        // test's vocabulary could not object to it — and is rejected anyway, because it reads indigo.
        let indigo = BrandColour.read(RewindPalette.nsColor(hue: 226))
        XCTAssertGreaterThan(indigo?.clearance ?? -1, 0, "226° is outside the wedge")
        assertReadsOffBrand(RewindPalette.nsColor(hue: 226), "226°, outside the wedge but hugging it")
        XCTAssertGreaterThanOrEqual(
            BrandColour.read(RewindPalette.nsColor(hue: 219))?.clearance ?? 0, BrandColour.blueMargin,
            "the top of the arc must clear the margin, not sit on it")
    }

    /// The names side: every real app name and every host the search panel can be asked for lands
    /// inside that domain. The colours are already proven safe above; what this pins is that the
    /// mapping from a name cannot escape the arc.
    ///
    /// Hosts are here because `SearchFavicon` feeds this palette a domain, not an app name, and the
    /// violet disc was a domain's.
    func testEveryNameAndHostMapsIntoTheSafeArc() {
        let realAppNames = [
            "Arc", "Cursor", "Warp", "QuickTime Player", "Preview", "Google Chrome", "Telegram",
            "ChatGPT Atlas", "Claude", "Messages", "Finder", "omi-people-intel", "Notes",
            "System Settings", "Terminal", "Xcode", "Slack", "Safari", "Mail", "Music",
            "Activity Monitor", "Unknown", "Figma", "iTerm2",
        ]
        // Hosts that landed in the wedge under the 250° arc: gitlab.com was 244.7°, reddit.com
        // 242.9°, bsky.app 240.8°. They are named here so the case is a fixture, not a memory.
        let realHosts = [
            "github.com", "gitlab.com", "reddit.com", "bsky.app", "anthropic.com", "claude.ai",
            "news.ycombinator.com", "figma.com", "linear.app", "medium.com", "x.com", "google.com",
        ]
        var names = realAppNames + realHosts
        for index in 0..<20_000 { names.append("generated-app-\(index)") }

        for name in names {
            let hue = RewindPalette.hue(forApp: name)
            XCTAssertGreaterThanOrEqual(hue, 0, "hue below the wheel for \(name)")
            XCTAssertLessThan(hue, RewindPalette.hueCeiling, "\(name) escaped the arc at \(hue)")
        }
        // Spot-check the whole pipeline on the real names rather than trusting the arc alone.
        for name in realAppNames + realHosts {
            assertReadsOnBrand(RewindPalette.nsColor(forApp: name), name)
            assertReadsOnBrand(NSColor(RewindPalette.color(forApp: name)), "\(name), SwiftUI")
        }
    }

    /// The colour is a real colour rather than a semantic that would collapse to the same value for
    /// every app — and two different apps must actually differ.
    ///
    /// The second half is what keeps narrowing the arc honest: a ceiling low enough to satisfy the
    /// brand rule by squeezing every app into one blue would satisfy the guard above and destroy the
    /// only thing the palette is for.
    func testDifferentAppsGetDifferentHues() {
        let hues = ["Arc", "Cursor", "Warp", "Messages", "Finder"].map(RewindPalette.hue(forApp:))
        XCTAssertEqual(Set(hues).count, hues.count, "distinct apps must be distinguishable")

        let spread = ["Arc", "Cursor", "Warp", "QuickTime Player", "Google Chrome", "Claude",
            "Messages", "Finder", "Notes", "Terminal", "Xcode", "Slack", "Safari", "Music"]
            .map(RewindPalette.hue(forApp:))
        XCTAssertGreaterThan(
            (spread.max() ?? 0) - (spread.min() ?? 0), 150,
            "a real day's apps must still span the arc, not cluster into one colour")
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
