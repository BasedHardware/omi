import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// **INV-UI-1 for the one colour the app cannot check by looking at it.**
///
/// `Ink.accent` used to be `NSColor.controlAccentColor` — the accent the *user* picked in System
/// Settings. macOS offers Purple there, so on that machine the accent rendered purple and every
/// token spending it went with it: the selection ring and the checkbox and the radio fill in
/// Settings, the sidebar's selected row, the popover's `Connect` link, the timeline's Live Text
/// highlight and its toggle, the tutorial's drag hint and its chosen-moment ring, and the switch in
/// the onboarding permission replica. Fourteen call sites, one line, and no call site able to do
/// anything about it, because the hue is not knowable there.
///
/// **A rendered-pixel assertion cannot catch this, and that is the whole point of this file.**
/// Every machine this app has been developed on has a blue accent, so `BrandColour.read` of the old
/// `Ink.accent` came back on brand here and would have come back on brand in CI — and shipped
/// purple to the user who chose purple. The defect is not the *value*, it is that the value is read
/// off the machine at all. So the value is asserted (it must still be on brand) and the *source of
/// the value* is asserted separately, twice, in the two ways that survive being run on a blue Mac:
///
/// 1. `testTheAccentIsNotTheMachinesOwnAccent` — a runtime identity check. `NSColor` keeps the
///    catalog entry it was built from (`controlAccentColor` vs `systemBlueColor`) through the
///    SwiftUI round trip, so the token can be asked *what it is* rather than what it looks like.
///    This is behavioural: it interrogates the shipped object.
/// 2. `testNoUISourceReadsTheMachinesAccent` — a **static tripwire**, explicitly not behavioural
///    coverage. It reads source text, which proves nothing about what the app draws; it exists only
///    to catch a *new* call site reaching past `Ink` for `controlAccentColor` directly, which check
///    (1) cannot see because it only knows about the tokens it is handed.
///
/// The brand predicate itself lives once, in `BrandColourGuard`, and is not restated here. A second
/// copy of the rule is the mistake that produced the original defect.
final class InkAccentTests: XCTestCase {

    // MARK: - The value

    /// The accent renders on brand — through the shared predicate, on the rendered pixel.
    ///
    /// Necessary and nowhere near sufficient: see the note above. This is the check that passes on
    /// a blue Mac no matter which of the two implementations is in the file.
    func testTheAccentRendersOnBrand() {
        assertReadsOnBrand(NSColor(Ink.accent), "Ink.accent")

        // The negative control, and the exact colour that shipped: macOS's Purple accent, which is
        // what `Ink.accent` resolved to on that machine before this change. A guard that accepts
        // this is not a guard.
        assertReadsOffBrand(.systemPurple, "the accent macOS ships as Purple")
    }

    /// **The fix reaches the pixels**, on one of the controls that was drawing the machine's accent.
    ///
    /// `TutorialScrollDemo` is the tutorial's drag hint — the accented panel under the fingers, at
    /// `Ink.accent.opacity(0.85)`, and one of the two sites this sweep started from. (It was three
    /// travelling capsules at that same alpha when this test was written; then a hand sweeping over a
    /// strip, so the beat showed the *gesture* rather than its outcome; and now two fingers on a
    /// drawn trackpad beside that strip, because the words said "two fingers" and no picture ever
    /// did. The alpha did not move through any of it, deliberately — the composited hue below was
    /// measured at it.) Asserting the token alone would leave the interesting half unproven: that
    /// this view spends the token rather than a colour of its own. So the view is rendered and its
    /// most saturated pixel is read.
    ///
    /// The pixel is composited — `Ink.accent` at 0.85 over `Ink.wash` over white — so it is compared
    /// to the token by **hue, within 8°**, and not by equality. `BrandColour`'s clearance is
    /// blend-invariant over a neutral ground *when the blend happens in the space the components are
    /// measured in*, and SwiftUI's does not: it composites in linear light and encodes afterwards.
    /// Measured here, that moves this capsule from the token's 205.9° to 203.3° and its clearance
    /// from 0.569 to 0.612 — small, real, and not a number to pretend away. 8° covers it four times
    /// over and still separates `systemBlue` from every other hue in the product: `systemTeal` is
    /// 20° off it and `systemIndigo` 28°.
    ///
    /// What this deliberately does **not** claim is that the capsule is not the machine's accent —
    /// on this machine that accent renders at 211.3°, inside the tolerance. Hue cannot answer that
    /// question and no rendered pixel can; `testTheAccentIsNotTheMachinesOwnAccent` answers it by
    /// identity instead. This test's job is the other half: that the view spends the token the other
    /// test guards, rather than a colour of its own.
    @MainActor
    func testTheTutorialDragHintDrawsTheGuardedAccent() throws {
        // Big enough for the hint's own layout — a 112 pt trackpad, a gap, and a strip beside it, all
        // 68 pt tall — because a frame that clipped it could leave the accented panel outside the
        // bitmap, which would fail this test for a reason that has nothing to do with the accent.
        let renderer = ImageRenderer(
            content: TutorialScrollDemo()
                .frame(width: 440, height: 96)
                .background(Color.white))
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.nsImage, "TutorialScrollDemo did not render")
        let pixel = try XCTUnwrap(Self.mostSaturatedPixel(of: image), "the hint rendered no colour at all")

        assertReadsOnBrand(pixel, "TutorialScrollDemo's accented panel, as rendered")

        let drawn = try XCTUnwrap(BrandColour.read(pixel))
        let token = try XCTUnwrap(BrandColour.read(NSColor(Ink.accent)))
        XCTAssertEqual(
            drawn.hue, token.hue, accuracy: 8,
            "the capsule is not Ink.accent — it renders at hue \(drawn.hue) where the token is at "
                + "\(token.hue), so the guard over the token says nothing about this view")
    }

    /// The other half of the same tutorial pass, and the newer of the two views: the launch gesture's
    /// keyboard row, whose pressed ⌘ caps fill with `Ink.accent` and whose tie between them is
    /// stroked in it.
    ///
    /// Rendered rather than asserted on the token for the same reason as above — the interesting
    /// claim is that *this view* spends the token — and it is worth its own case because it is the
    /// one place in the tutorial where the accent is used to say that two things belong to one
    /// gesture, which is exactly the kind of "make it stand out" drawing that reaches for a hue of
    /// its own (`INV-UI-1`).
    ///
    /// The pose at tick 0 is the pair **down**, under Reduce Motion and without it alike
    /// (`TutorialCommandPair.pose`), so there is always accent in the bitmap and this does not
    /// depend on what the running machine has that setting at.
    @MainActor
    func testTheTutorialLaunchGestureDrawsTheGuardedAccent() throws {
        let renderer = ImageRenderer(
            content: TutorialCommandPairDemo()
                .frame(width: 260, height: 60)
                .background(Color.white))
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.nsImage, "TutorialCommandPairDemo did not render")
        let pixel = try XCTUnwrap(
            Self.mostSaturatedPixel(of: image), "the keyboard row rendered no colour at all")

        assertReadsOnBrand(pixel, "TutorialCommandPairDemo's pressed Command caps, as rendered")

        let drawn = try XCTUnwrap(BrandColour.read(pixel))
        let token = try XCTUnwrap(BrandColour.read(NSColor(Ink.accent)))
        XCTAssertEqual(
            drawn.hue, token.hue, accuracy: 8,
            "the pressed cap is not Ink.accent — it renders at hue \(drawn.hue) where the token is "
                + "at \(token.hue), so the guard over the token says nothing about this view")
    }

    /// The rendered pixel carrying the most hue, which for this view is a capsule's interior: the
    /// ground is white and `Ink.wash` under the capsules is a near-neutral label alpha.
    private static func mostSaturatedPixel(of image: NSImage) -> NSColor? {
        guard
            let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
            let bitmap = NSBitmapImageRep(cgImage: cgImage).converting(
                to: .sRGB, renderingIntent: .default)
        else { return nil }

        var best: NSColor?
        var bestChroma = 0.0
        for x in 0..<bitmap.pixelsWide {
            for y in 0..<bitmap.pixelsHigh {
                guard let pixel = bitmap.colorAt(x: x, y: y), pixel.alphaComponent > 0.99 else { continue }
                let r = Double(pixel.redComponent)
                let g = Double(pixel.greenComponent)
                let b = Double(pixel.blueComponent)
                let chroma = max(r, max(g, b)) - min(r, min(g, b))
                if chroma > bestChroma {
                    bestChroma = chroma
                    best = pixel
                }
            }
        }
        return best
    }

    // MARK: - The source of the value

    /// **The accent is chosen by this app, not reported by the machine.**
    ///
    /// The assertion that actually holds the line. `NSColor` built from a system colour is a catalog
    /// colour that remembers its entry — `controlAccentColor` for the machine's accent,
    /// `systemBlueColor` for the one this app picks — and it keeps it through
    /// `Color(nsColor:)`/`NSColor(_:)`, so the identity survives the token being declared in
    /// SwiftUI. That makes this independent of what the running machine's accent happens to be:
    /// re-point `Ink.accent` at `controlAccentColor` and this fails on a blue Mac, which is the one
    /// thing the pixel check above cannot do.
    func testTheAccentIsNotTheMachinesOwnAccent() {
        // The detector fires on the real thing — otherwise the assertion below is vacuous and this
        // whole file is decoration.
        XCTAssertTrue(
            Self.isTheMachinesAccent(.controlAccentColor),
            "the detector no longer recognises NSColor.controlAccentColor, so nothing below means "
                + "anything — check whether AppKit renamed the catalog entry")
        XCTAssertFalse(Self.isTheMachinesAccent(.systemBlue), "systemBlue is not the machine's accent")

        XCTAssertFalse(
            Self.isTheMachinesAccent(NSColor(Ink.accent)),
            "Ink.accent is NSColor.controlAccentColor — the accent the user picked in System "
                + "Settings, which macOS lets them set to Purple. Every token spending the accent "
                + "then renders purple on that machine and no call site can correct it. Pick a "
                + "named system colour instead (INV-UI-1, docs/product/invariants/brand-ui.md).")
    }

    /// Is this colour the machine's own accent, rather than a hue this app chose?
    ///
    /// Identity, not appearance. Both are catalog colours in the `System` catalog; only the entry
    /// name distinguishes them, and only the entry name is stable when the user changes their
    /// accent.
    private static func isTheMachinesAccent(_ color: NSColor) -> Bool {
        color.type == .catalog && color.colorNameComponent == "controlAccentColor"
    }

    // MARK: - Static tripwire

    /// **STATIC TRIPWIRE — not behavioural coverage.**
    ///
    /// This test reads source text. It cannot tell you what the app draws and must never be counted
    /// as evidence that it draws the right thing; `testTheAccentRendersOnBrand` and
    /// `testTheAccentIsNotTheMachinesOwnAccent` are the tests that do that, and they cover the
    /// tokens. What no assertion over a token can cover is a view that skips `Ink` and writes
    /// `Color(nsColor: .controlAccentColor)` inline — a fresh instance of the same defect, in a file
    /// no guard has ever heard of. Catching that is a question about the source, so it is answered
    /// with a check on the source, labelled as one.
    ///
    /// Comments are stripped before matching, deliberately: several files in `Sources/ContextApp`
    /// explain *why* they do not use the machine's accent, and a check that punished them for
    /// naming it would delete the reasoning it is trying to preserve.
    func testNoUISourceReadsTheMachinesAccent() {
        let root = InkSourceSweep.uiSourceRoot
        var scanned = 0
        var offenders: [String] = []

        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        while let url = files?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            guard let text = try? String(contentsOf: url, encoding: .utf8) else {
                return XCTFail("could not read \(url.path)")
            }
            scanned += 1
            let relative = url.path.replacingOccurrences(of: root.path + "/", with: "")
            for (offset, line) in InkSourceSweep.strippingComments(from: text).components(separatedBy: "\n")
                .enumerated()
            where line.contains("controlAccentColor") {
                offenders.append("\(relative):\(offset + 1)")
            }
        }

        // A scan that found nothing because it looked nowhere passes silently, which is the failure
        // mode of every check like this one.
        XCTAssertGreaterThan(scanned, 40, "the sweep found almost no Swift files — check \(root.path)")

        XCTAssertEqual(
            offenders, [],
            "these read NSColor.controlAccentColor, the accent the user picked in System Settings, "
                + "which macOS lets them set to Purple — off brand everywhere in this product "
                + "(INV-UI-1). Use Ink.accent, which is a named system colour this app chooses.")
    }

    // **There is no allowlist here, and there must not be one again.**
    //
    // There was: `Settings/SettingsPreferences.swift` was exempted from the sweep for the
    // `AccentChoice.system` preference, whose `nsColor` resolved to `controlAccentColor` so a
    // purple-accent Mac got a purple Settings window without ever choosing purple. That was written
    // down as an exposure that was open rather than settled, and it was left in place because
    // `SettingsTests.testSystemAccentIsTheUsersOwn` was said to pin the behaviour deliberately.
    //
    // `AccentChoice` has since been deleted, and so has the test that was cited as the reason to keep
    // the entry. What was left was an exemption that named a file with nothing to exempt — which is
    // the worst state for one to be in, because it reads as settled and *stays* green: a
    // `Color(nsColor: .controlAccentColor)` added to that file tomorrow would ship purple on a
    // purple-accent Mac and this sweep would never see it. The file passes with no exemption at all,
    // so it has none.
    //
    // Anything proposed for a new allowlist has to answer the same question this one could not: what
    // catches the *next* line added to the exempted file. Skipping a whole file is a hole; the
    // per-spelling counts `InkGlassTests` uses are the shape to copy if an exception is ever genuinely
    // needed.
}
