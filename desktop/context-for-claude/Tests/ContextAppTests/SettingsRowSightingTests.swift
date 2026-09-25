import AppKit
import XCTest

@testable import ContextApp

//  Reading our row out of System Settings' pixels, in the parts that have a wrong answer available.
//
//  Everything here runs against **observations a live pass actually printed**, not against numbers
//  invented to make the arithmetic come out. `PaneSighting` below is a transcript: the window rects
//  are what `SCContentFilter.contentRect` answered, the normalised boxes are what
//  `VNRecognizeTextRequest` answered against those windows, and the pixel rects the assertions check
//  against were measured out of the same screenshot by looking at where the row separators and the
//  switch's own blue actually are. Two independent readings of one frame, which is the only way a
//  test of a coordinate conversion is worth anything — an assertion derived from the same formula it
//  is checking passes forever and proves nothing.
//
//  Captured on macOS 26.5.2 (build 25F84), 723 × 948 System Settings window on a 2× display.

/// The live transcript. One place, so the two suites below cannot drift from each other or from the
/// frame they were taken off.
enum PaneSighting {
    static let appName = PaneFixture.appName

    // MARK: Privacy & Security ▸ Accessibility

    /// The window `SCContentFilter.contentRect` reported, which measured identical to `SCWindow.frame`
    /// and to `CGWindowListCopyWindowInfo`'s bounds.
    static let accessibilityWindow = CGRect(x: 576, y: 65, width: 723, height: 948)

    /// **Ground truth, measured off the pixels rather than derived.** The row separators either side
    /// of our row sat at image y 657 and 737 in the 1446 × 1896 capture — global y 393.5 and 433.5, a
    /// 40 pt row centred on 413.5.
    static let accessibilityRowTop: CGFloat = 393.5
    static let accessibilityRowBottom: CGFloat = 433.5

    /// The switch's blue pill, found by scanning the same frame for saturated blue inside the row
    /// band: image x 1314…1385, y 686…717 — global (1233, 408) 36 × 16.
    static let accessibilitySwitch = CGRect(x: 1_233, y: 408, width: 36, height: 16)

    /// What Vision read, in the order it read it. Confidences are the reported ones.
    ///
    /// The three near-misses are kept deliberately: "Claude", "claude" and "Coast Local" were really
    /// in the list a few rows above ours on this machine, and a locator matching on `contains` would
    /// have aimed at one of them.
    static let accessibilityLabels: [RecognizedLabel] = [
        RecognizedLabel(
            text: "Accessibility",
            boundingBox: CGRect(
                x: 0.43605545504575094, y: 0.9616249447105338,
                width: 0.12598432907589896, height: 0.018610576034095216),
            confidence: 1),
        RecognizedLabel(
            text: "Allow the applications below to control your computer.",
            boundingBox: CGRect(
                x: 0.34857143669769425, y: 0.9156118145617731,
                width: 0.4571428523188969, height: 0.01607423190829116),
            confidence: 1),
        RecognizedLabel(
            text: "claude",
            boundingBox: CGRect(
                x: 0.3904761911858512, y: 0.8343023259932975,
                width: 0.05714285653986212, height: 0.01308139467038183),
            confidence: 1),
        RecognizedLabel(
            text: "Claude",
            boundingBox: CGRect(
                x: 0.39047619045329135, y: 0.7921511626905227,
                width: 0.05904761983151258, height: 0.013081395676367458),
            confidence: 1),
        RecognizedLabel(
            text: "Coast Local",
            boundingBox: CGRect(
                x: 0.39047619002613665, y: 0.7499999997726448,
                width: 0.10095238059058392, height: 0.013185654008438852),
            confidence: 1),
        RecognizedLabel(
            text: "Codex Computer Use",
            boundingBox: CGRect(
                x: 0.39047619159443003, y: 0.7062236288333502,
                width: 0.18095237552542576, height: 0.016350210970464185),
            confidence: 1),
        ourRow,
    ]

    /// The observation this whole file exists for.
    static let ourRow = RecognizedLabel(
        text: "Context for Claude",
        boundingBox: CGRect(
            x: 0.3904761920878382, y: 0.6234177217437293,
            width: 0.1580952371304461, height: 0.013210184966461536),
        confidence: 1)

    // MARK: Privacy & Security ▸ Screen & System Audio Recording

    /// The same window, dragged. Carried because a locator that only ever ran against a window at
    /// (576, 65) could hide an origin it forgot to add in.
    static let screenWindow = CGRect(x: -64, y: 109, width: 723, height: 948)

    /// This pane lists an application **twice** — "Screen & System Audio Recording", then "System
    /// Audio Recording Only" — and both of these were read off it in one pass, at global y 435.5 and
    /// 1011.5.
    static let screenLabels: [RecognizedLabel] = [
        RecognizedLabel(
            text: "Claude",
            boundingBox: CGRect(
                x: 0.39033839182314123, y: 0.7685243020099191,
                width: 0.05932321719938621, height: 0.013823489096597252),
            confidence: 1),
        RecognizedLabel(
            text: "Context for Claude",
            boundingBox: CGRect(
                x: 0.3904761920878382, y: 0.6424050634132346,
                width: 0.1580952371304461, height: 0.013185654008438852),
            confidence: 1),
        RecognizedLabel(
            text: "Context for Claude",
            boundingBox: CGRect(
                x: 0.3904761920878382, y: 0.03481012643533121,
                width: 0.1580952371304461, height: 0.01318565400843874),
            confidence: 1),
    ]
}

// MARK: - The row, from the pixels

final class SettingsRowSightingTests: XCTestCase {
    private let sighting = SettingsRowSighting(appName: PaneSighting.appName)

    private func sighted(
        _ labels: [RecognizedLabel], window: CGRect, preferring occurrence: Int = 0,
        file: StaticString = #filePath, line: UInt = #line
    ) throws -> SettingsSpotlightTarget {
        guard case .sighted(let target) = sighting.locate(
            in: labels, window: window, preferring: occurrence)
        else {
            XCTFail("the row was not sighted", file: file, line: line)
            throw XCTSkip("no sighting")
        }
        return target
    }

    /// **The report, answered.** *"Specifically context for claude needs to be dotted around."* The
    /// user was standing on Privacy & Security ▸ Accessibility with their own row in the list, and the
    /// overlay had nothing to dash — the accessibility tree is closed to an untrusted process, which
    /// is every process on that pane by definition.
    ///
    /// This is the same pane read the other way. The band that gets dashed has to land on **that** row
    /// and no other, and the row is 40 pt tall with identical rows 40 pt above and below it, so
    /// "close enough" is a different application's permission.
    func testTheRowRingedOnTheAccessibilityPaneIsTheOneWithOurNameOnIt() throws {
        let target = try sighted(PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow)

        let measured = CGRect(
            x: target.row.minX, y: PaneSighting.accessibilityRowTop,
            width: target.row.width,
            height: PaneSighting.accessibilityRowBottom - PaneSighting.accessibilityRowTop)
        XCTAssertEqual(
            target.row.midY, measured.midY, accuracy: 3,
            "the dashed band is centred on a row the pixels say is somewhere else")
        XCTAssertEqual(target.row.height, SettingsRowSighting.rowHeight)

        // The claim that actually matters: nearer this row's centre than either neighbour's. The rows
        // are 40 pt apart, so anything else is a boundary drawn round somebody else's application.
        for neighbour in [measured.midY - 40, measured.midY + 40] {
            XCTAssertLessThan(
                abs(target.row.midY - measured.midY), abs(target.row.midY - neighbour),
                "the band is closer to the neighbouring row than to ours")
        }
    }

    /// The switch is derived rather than measured — OCR cannot see a control with no text on it — so
    /// the derivation is checked against the switch's **own pixels**, found by scanning the same frame
    /// for its blue.
    ///
    /// Within a third of a point on both axes. That is what makes the two constants this locator
    /// carries (`toggleTrailingInset`, `toggleSize`) a measurement rather than a guess.
    func testTheSwitchIsDerivedOntoWhereTheSwitchActuallyIs() throws {
        let target = try sighted(PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow)
        let real = PaneSighting.accessibilitySwitch
        XCTAssertEqual(target.toggle.minX, real.minX, accuracy: 0.5)
        XCTAssertEqual(target.toggle.maxX, real.maxX, accuracy: 0.5)
        XCTAssertEqual(target.toggle.midY, real.midY, accuracy: 1)
        XCTAssertEqual(target.toggle.size, real.size)

        // And the glow gets the same floor the accessibility walk applies, centred on it.
        XCTAssertEqual(target.focus.size, CGSize(width: 56, height: 30))
        XCTAssertEqual(target.focus.midX, target.toggle.midX)
        XCTAssertEqual(target.focus.midY, target.toggle.midY)
    }

    /// The band runs label-to-switch, which is the **same rect** `SettingsRowLocator` reports for a
    /// walked row (`label.union(toggle)`). Two locators, one dashed rectangle — the user cannot tell
    /// which one found it, and neither can a screenshot.
    func testTheBandRunsFromTheLabelToTheSwitchJustAsTheWalkedOneDoes() throws {
        let target = try sighted(PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow)
        XCTAssertEqual(target.row.maxX, target.toggle.maxX)
        XCTAssertEqual(target.row.minX, 858.31, accuracy: 0.5, "the label's own left edge")
        XCTAssertTrue(PaneSighting.accessibilityWindow.contains(target.row))
        XCTAssertTrue(target.isListed)
        XCTAssertEqual(target.gesture, .click)
        XCTAssertFalse(target.isOn, "nothing in a screenshot says a switch is on, and nothing claims it")
    }

    /// **The Y flip, which is the one line here that is silently wrong in a way nothing else catches.**
    ///
    /// Vision measures from the bottom-left; every rect this overlay draws is measured from the
    /// top-left. The flip is `1 - y - height` and not `1 - y` — the latter maps a box's bottom edge
    /// onto the new top edge, which on a 40 pt row is the wrong row and on the pane's title is the
    /// wrong end of the window. Asserted against a label near the **top** of the window, where the two
    /// formulas differ most visibly, and against ours in the middle.
    func testVisionsBottomLeftBoxesLandTheRightWayUp() throws {
        let window = PaneSighting.accessibilityWindow
        // "Accessibility" — the pane's own heading, 4% down from the top of the window.
        let heading = try XCTUnwrap(
            SettingsRowSighting.pointRect(
                of: PaneSighting.accessibilityLabels[0].boundingBox, in: window))
        XCTAssertEqual(heading.minY, window.minY + 0.0198 * window.height, accuracy: 2)
        XCTAssertLessThan(heading.midY, window.midY, "the heading belongs in the top half")

        let ours = try XCTUnwrap(SettingsRowSighting.pointRect(of: PaneSighting.ourRow.boundingBox, in: window))
        XCTAssertEqual(ours.minY, 409.48, accuracy: 0.5)
        XCTAssertEqual(ours.minX, 858.31, accuracy: 0.5)
    }

    /// A window somewhere else. The conversion is one multiply and one flip against the rect the
    /// capture was taken of, and it must carry that rect's origin — including a negative one, which is
    /// what a window dragged off the left of the primary display really answers.
    func testTheConversionFollowsTheWindowItWasCapturedAgainst() throws {
        let target = try sighted(PaneSighting.screenLabels, window: PaneSighting.screenWindow)
        XCTAssertEqual(target.row.minY, 435.5 - SettingsRowSighting.rowHeight / 2 + 6.25, accuracy: 1.5)
        XCTAssertLessThan(target.row.minX, 576, "a window at negative x cannot produce a row at 858")
        XCTAssertTrue(PaneSighting.screenWindow.contains(target.row))
    }

    // MARK: The two lists

    /// Screen & System Audio Recording lists this application twice, and system audio's switch is in
    /// the **second** list. Sections are laid out top to bottom, so the ordinal the accessibility walk
    /// gets structurally is the one sorting the matches by y reproduces.
    ///
    /// Ringing the wrong one is not a near miss: it is the screen-recording switch offered as the
    /// system-audio one, with total confidence.
    func testTheTwoListsOnTheScreenPaneAreToldApartByTheSameOrdinalTheWalkUses() throws {
        let upper = try sighted(PaneSighting.screenLabels, window: PaneSighting.screenWindow, preferring: 0)
        let lower = try sighted(PaneSighting.screenLabels, window: PaneSighting.screenWindow, preferring: 1)
        XCTAssertLessThan(upper.row.minY, lower.row.minY)
        XCTAssertEqual(
            PermissionChoreography.sectionOccurrence(for: .screen), 0,
            "screen recording is the upper list")
        XCTAssertEqual(
            PermissionChoreography.sectionOccurrence(for: .systemAudio), 1,
            "system audio is the lower one")
    }

    /// **The ordinal is not clamped, unlike the walk's.** A section is a structural fact and a match
    /// is not, so asking for the second of one match is a question with no answer — and answering it
    /// with the first would point the system-audio arrow at the screen-recording switch.
    func testAskingForASecondRowThatIsNotThereRefusesRatherThanTakingTheFirst() {
        XCTAssertEqual(
            sighting.locate(
                in: PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow,
                preferring: 1),
            .notFound)
    }

    // MARK: Refusing

    /// Whole-string, never `contains`. Measured on the very pane this exists for, the list held
    /// "Claude", "claude" and "Coast Local" a few rows above ours — a substring rule would have aimed
    /// at one of them, and a longer name that contains ours ("Context for Claude Helper") is the same
    /// mistake from the other side.
    func testAnotherApplicationsNameIsNotOurs() {
        let others = PaneSighting.accessibilityLabels.filter { $0.text != PaneSighting.appName }
        XCTAssertEqual(sighting.locate(in: others, window: PaneSighting.accessibilityWindow), .notFound)

        var impostor = PaneSighting.ourRow
        impostor.text = PaneSighting.appName + " Helper"
        XCTAssertEqual(
            sighting.locate(in: [impostor], window: PaneSighting.accessibilityWindow), .notFound)
    }

    /// A half-drawn frame — captured mid pane-transition — can still be read as something. Reported as
    /// faint rather than found, and faint never points.
    func testAFaintMatchIsRefusedAndSaidToBeFaint() {
        var blurred = PaneSighting.ourRow
        blurred.confidence = 0.3
        XCTAssertEqual(sighting.locate(in: [blurred], window: PaneSighting.accessibilityWindow), .faint)
    }

    /// **A row scrolled out of the list cannot be sighted, and that is a property rather than a
    /// check.** The accessibility walk needs a whole clip stack to notice that a row it can see in the
    /// tree is nowhere the user can look; text that was never drawn was never recognised.
    func testARowScrolledOutOfViewIsSimplyNotInTheReading() {
        let scrolled = PaneSighting.accessibilityLabels.filter { $0.text != PaneSighting.appName }
        XCTAssertEqual(sighting.locate(in: scrolled, window: PaneSighting.accessibilityWindow), .notFound)
    }

    /// Degenerate inputs answer nothing rather than a rectangle of negative width drawn somewhere it
    /// does not belong.
    func testNonsenseGeometryRefuses() {
        XCTAssertEqual(sighting.locate(in: PaneSighting.accessibilityLabels, window: .zero), .notFound)

        // A window too narrow to hold this label and a switch side by side: the label runs to 54.9%
        // of the window's width, and the switch occupies the last 66 pt, so anything under about
        // 146 pt wide has them overlapping. A band drawn from those two would have negative width.
        let narrow = CGRect(x: 576, y: 65, width: 120, height: 948)
        XCTAssertEqual(sighting.locate(in: PaneSighting.accessibilityLabels, window: narrow), .notFound)

        var absurd = PaneSighting.ourRow
        absurd.boundingBox = CGRect(x: .nan, y: 0.5, width: 0.1, height: 0.01)
        XCTAssertEqual(sighting.locate(in: [absurd], window: PaneSighting.accessibilityWindow), .notFound)
    }
}

// MARK: - What the overlay does with it

final class SightedSpotlightSceneTests: XCTestCase {
    private let display = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_920, height: 1_080), backingScaleFactor: 2)
    private var space: ScreenSpace { ScreenSpace(displays: [display]) }

    /// **The end of the reported defect, at the seam the drawing consumes.**
    ///
    /// `SettingsSpotlightTests.testTheFramingTierDashesNothingAtAll` asserts the other half: a tier
    /// that knows a window and nothing inside it dashes nothing, because a dotted boundary round forty
    /// rows says "somewhere in here". This is what replaces it on the Accessibility pane — one dashed
    /// region, round one row, small enough that it cannot be a pane wearing a row's name.
    func testASightedRowIsDashedAndTheWindowIsNot() throws {
        guard case .sighted(let target) = SettingsRowSighting(appName: PaneSighting.appName)
            .locate(in: PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow)
        else { return XCTFail("expected a sighting") }

        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(
                target: target, caption: "Click this switch", display: display, space: space))

        XCTAssertEqual(scene.dashedRegions.count, 1)
        let dashed = try XCTUnwrap(scene.dashedRegions.first)
        XCTAssertEqual(dashed.rect, target.row)
        XCTAssertLessThan(
            dashed.rect.height, PaneSighting.accessibilityWindow.height / 10,
            "a 'row' a tenth of the window tall is the boundary this fix removed, renamed")
        XCTAssertNotNil(scene.arrow, "a sighting that draws no arrow has not replaced anything")
        XCTAssertNotNil(scene.focus)
        XCTAssertTrue(scene.isDrawable)
    }

    /// **The decision, not just the locator.** A locator nothing consults is a locator that fixes
    /// nothing, and the two failures a locator cannot have on its own live here: the section ordinal
    /// picked for this capability, and the two gates every target passes before it may be drawn.
    ///
    /// Driven through `PermissionChoreography.sighting`, which is the function `liveGuidance` calls —
    /// the same seam `guidance(for:appName:windows:…)` is for the accessibility walk.
    func testTheChoreographyAnswersPointingWhenThePixelsHoldOurRow() throws {
        let guidance = PermissionChoreography.sighting(
            for: .accessibility, appName: PaneSighting.appName, labels: PaneSighting.accessibilityLabels,
            frame: PaneSighting.accessibilityWindow, space: space)
        guard case .pointing(let target) = guidance else {
            return XCTFail("the Accessibility step must point once the pane can be read: \(String(describing: guidance))")
        }
        XCTAssertEqual(target.row.midY, (PaneSighting.accessibilityRowTop + PaneSighting.accessibilityRowBottom) / 2, accuracy: 3)
        XCTAssertEqual(target.window, PaneSighting.accessibilityWindow)
    }

    /// Nothing read yet — the ticks before the first pass lands, and every tick of a process without
    /// Screen Recording. Answers nothing rather than something, so the caller falls to the boundary
    /// and the sentence it was already showing.
    func testNoReadingMeansNoGuidanceRatherThanAGuess() {
        XCTAssertNil(
            PermissionChoreography.sighting(
                for: .accessibility, appName: PaneSighting.appName, labels: [],
                frame: PaneSighting.accessibilityWindow, space: space))
    }

    /// The row is sighted, and the window it was sighted in is on no display — a monitor unplugged
    /// between the pass and the draw. The pixel route reaches the screen through the same vet the walk
    /// does, so it refuses too.
    func testASightingOnNoDisplayRefusesJustAsAWalkedOneDoes() {
        let offscreen = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_920, height: 1_080))
        ])
        XCTAssertNil(
            PermissionChoreography.sighting(
                for: .accessibility, appName: PaneSighting.appName, labels: PaneSighting.accessibilityLabels,
                frame: PaneSighting.accessibilityWindow.offsetBy(dx: 8_000, dy: 0), space: offscreen))
    }

    /// System audio is the **second** of the Screen Recording pane's two lists, and the pixel route has
    /// to pick the same one the walk would. Ringing the other is the screen-recording switch offered
    /// as the system-audio one.
    func testTheCapabilityChoosesTheSameListItWouldHaveWalkedTo() throws {
        let space = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_920, height: 1_400))
        ])
        guard case .pointing(let screen) = PermissionChoreography.sighting(
            for: .screen, appName: PaneSighting.appName, labels: PaneSighting.screenLabels,
            frame: PaneSighting.screenWindow, space: space),
            case .pointing(let audio) = PermissionChoreography.sighting(
                for: .systemAudio, appName: PaneSighting.appName, labels: PaneSighting.screenLabels,
                frame: PaneSighting.screenWindow, space: space)
        else { return XCTFail("both lists must be pointable") }
        XCTAssertLessThan(screen.row.minY, audio.row.minY)
    }

    /// The scrim still opens on the window, because the window is the only region this tier measured —
    /// exactly what the `framing` tier already lights. A pane dimmed everywhere but one row reads as
    /// broken rendering.
    func testTheScrimStillOpensOnTheWholeWindow() throws {
        guard case .sighted(let target) = SettingsRowSighting(appName: PaneSighting.appName)
            .locate(in: PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow)
        else { return XCTFail("expected a sighting") }
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(
                target: target, caption: "x", display: display, space: space))
        XCTAssertEqual(scene.area, PaneSighting.accessibilityWindow)
    }

    /// A sighting reaches the screen through the same two gates a walked target does. A row measured
    /// against a window that is no longer on any display is a stale rect, and a stale rect drawn is
    /// the mispositioned arrow this whole surface refuses.
    func testASightingIsClampedAndVettedLikeAnyOtherTarget() throws {
        guard case .sighted(let target) = SettingsRowSighting(appName: PaneSighting.appName)
            .locate(in: PaneSighting.accessibilityLabels, window: PaneSighting.accessibilityWindow)
        else { return XCTFail("expected a sighting") }

        // Same rects, a window that has moved out from under them.
        let elsewhere = CGRect(x: 4_000, y: 4_000, width: 723, height: 948)
        XCTAssertNil(PermissionChoreography.clamped(target, to: elsewhere))
        XCTAssertNil(
            SettingsSpotlightScene.make(
                target: target, caption: "x",
                display: DisplayGeometry(appKitFrame: CGRect(x: 4_000, y: 0, width: 100, height: 100)),
                space: ScreenSpace(displays: [
                    DisplayGeometry(appKitFrame: CGRect(x: 4_000, y: 0, width: 100, height: 100))
                ])))
    }
}

// MARK: - Paying for it once

final class SettingsPaneSightingsTests: XCTestCase {
    private let window = PaneSighting.accessibilityWindow

    /// A fresh object per test rather than `SettingsPaneSightings.shared`. The singleton owns a pass
    /// that outlives the call that started it, so two tests sharing it are two tests sharing a piece
    /// of in-flight state — which is a suite that fails on ordering, not a suite that means anything.
    private func sightings() -> SettingsPaneSightings { SettingsPaneSightings() }

    /// A reading answers the question it was taken for and no other.
    func testAReadingIsHandedBackForTheWindowAndCapabilityItWasTakenFor() {
        let sightings = sightings()
        sightings.remember(PaneSighting.accessibilityLabels, for: .accessibility, of: window)
        XCTAssertEqual(
            sightings.labels(for: .accessibility, of: window).count,
            PaneSighting.accessibilityLabels.count)
    }

    /// **System Settings keeps the same window when it changes pane.** So the window alone cannot tell
    /// "Accessibility, still" from "Microphone, now" — and both panes list this application, so the
    /// stale boxes would land on a real row in the wrong pane with nothing to give it away.
    func testAReadingOfADifferentPaneIsWithheldRatherThanReused() {
        let sightings = sightings()
        sightings.remember(PaneSighting.accessibilityLabels, for: .accessibility, of: window)
        XCTAssertTrue(
            sightings.labels(for: .microphone, of: window).isEmpty,
            "the pane changed under a window that did not")
    }

    /// The normalised boxes mean nothing against any other rect, so a moved or resized window
    /// invalidates the reading outright rather than shifting it.
    func testAReadingOfADifferentWindowIsWithheld() {
        let sightings = sightings()
        sightings.remember(PaneSighting.accessibilityLabels, for: .accessibility, of: window)
        XCTAssertTrue(
            sightings.labels(for: .accessibility, of: window.offsetBy(dx: 40, dy: 0)).isEmpty)
    }

    /// **Age triggers the next pass; it never withholds the answer.** Blinking the arrow off every
    /// 800 ms while a perfectly good pass is running would be the flapping `SpotlightHysteresis`
    /// exists to stop, one layer lower and self-inflicted.
    func testAStaleReadingIsStillAnsweredWhileTheNextOneIsBeingTaken() {
        let sightings = sightings()
        let taken = ContinuousClock.now
        sightings.remember(PaneSighting.accessibilityLabels, for: .accessibility, of: window, takenAt: taken)
        let later = taken.advanced(by: SettingsPaneSightings.refreshInterval * 4)
        XCTAssertFalse(sightings.labels(for: .accessibility, of: window, now: later).isEmpty)
    }

    /// A pass that was in flight when the episode ended belongs to a pane nobody is looking at. It
    /// must not be able to hand the next episode the last one's pixels.
    func testAnEpisodeThatEndedTakesItsPassWithIt() {
        let sightings = sightings()
        sightings.remember(PaneSighting.accessibilityLabels, for: .accessibility, of: window)
        sightings.forget()
        XCTAssertTrue(sightings.labels(for: .accessibility, of: window).isEmpty)
        XCTAssertEqual(sightings.passesStarted, 1, "and the new episode may look again immediately")
    }

    /// One schedule per cost. A pass measured 407–434 ms warm against the accessibility walk's
    /// 270–727 ms, so it is rationed by the same number the walk is.
    func testTheSightingIsRationedOnTheSolveScheduleAndNotOnTheTick() {
        XCTAssertEqual(SettingsPaneSightings.refreshInterval, SpotlightTrackPolicy().fullSolve)
        XCTAssertGreaterThan(SettingsPaneSightings.refreshInterval, SpotlightTrackPolicy().tick)
        XCTAssertGreaterThan(SettingsPaneSightings.refreshInterval, SpotlightTrackPolicy().trustWatch)
    }

    /// **The schedule has to be on the attempt, not on the answer — and the case that proves it is the
    /// one with no answer at all.**
    ///
    /// A process without Screen Recording never produces a reading, so a refresh gated on "the reading
    /// is missing or stale" is a refresh gated on a condition that is permanently true: one pass per
    /// 40 ms tick, twenty-five detached tasks a second, for the whole length of a permission step,
    /// every one of them to re-learn the same no. Cheap individually — they stop at
    /// `CGPreflightScreenCaptureAccess` — and exactly the kind of churn the tracker above it was
    /// rewritten to remove.
    ///
    /// The overlay ticks at 40 ms and `refreshInterval` is 800, so this asserts the ratio the live
    /// loop actually runs at: twenty ticks inside one interval, one pass.
    func testTheTicksInsideOneIntervalStartExactlyOnePass() {
        let sightings = sightings()
        let start = ContinuousClock.now
        let tick = SpotlightTrackPolicy().tick
        for step in 0..<20 {
            _ = sightings.labels(for: .accessibility, of: window, now: start.advanced(by: tick * step))
        }
        XCTAssertEqual(
            sightings.passesStarted, 1,
            "a tier that can never answer must not launch a screenshot and a Vision pass per tick")
    }
}

//  The ordering this locator forces is guarded where the ordering guard already lived —
//  `OnboardingResumeTests.testTheScreenIsAskedForFirstBecauseTheOtherLocatorNeedsItsPixels`. One rule,
//  one test; a second copy here would be a second thing to update and a second thing to forget.
