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

    private static var bundledFacesRegistered: Bool { InkTestFonts.registered }

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

    /// The scale, and the two things about it that are not a matter of taste.
    ///
    /// Onboarding shipped a step smaller than this — 32/25/15/13/11/14 — and was reported as being
    /// set too small to read comfortably. What is asserted here is not "these are the right sizes",
    /// which no test can know, but the floor the complaint established and the shape of the ladder,
    /// so the next person to reach for these numbers cannot quietly walk them back down.
    ///
    /// `InkType.minimumSize` is the floor. It is 12 pt and not an aesthetic preference: it is where
    /// the tracking ladder stops (below it, closing a geometric sans's counters costs more than
    /// locking its words up buys), so a role under it is both illegible and outside the part of the
    /// system where tracking is defined.
    func testEveryRoleClearsTheLegibilityFloorAndTheLadderStaysOrdered() {
        for role in InkType.allRoles {
            XCTAssertGreaterThanOrEqual(
                role.size, InkType.minimumSize,
                "a role at \(role.size) pt is under the \(InkType.minimumSize) pt legibility floor")
        }

        // The ladder, largest to smallest, and each rung distinct — one size used for two roles that
        // are meant to read as different steps is the ladder collapsing.
        XCTAssertEqual(InkType.introHero.size, 34)
        XCTAssertEqual(InkType.stepHeadline.size, 27)
        XCTAssertEqual(
            InkType.firstTitle.size, InkType.stepHeadline.size, "one headline size, as on the site")
        XCTAssertEqual(InkType.prose.size, 17)
        XCTAssertEqual(InkType.rowCopy.size, 15)
        XCTAssertEqual(InkType.buttonLabel.size, 15)
        XCTAssertEqual(InkType.statusLabel.size, InkType.minimumSize, "the smallest role sits on the floor")

        XCTAssertGreaterThan(InkType.introHero.size, InkType.stepHeadline.size)
        XCTAssertGreaterThan(InkType.stepHeadline.size, InkType.prose.size)
        XCTAssertGreaterThan(InkType.prose.size, InkType.rowCopy.size)
        XCTAssertGreaterThan(InkType.rowCopy.size, InkType.statusLabel.size)

        // `prose` is the step that carries paragraphs, and it is held under 18 pt on purpose: at 18
        // WCAG reclassifies it as large text and the label ladder's contrast bar would drop from
        // 4.5:1 to 3:1 — the bar must not get easier because the type got bigger.
        // (`testTheLabelLadderMeetsWCAGAAInBothAppearances` is the assertion that bar is met.)
        XCTAssertLessThan(InkType.prose.size, 18)
    }

    /// Tracking is `em × size`, and the `em` ratios are the fixed part.
    ///
    /// This is the rule a size change is most likely to break silently. Tracking is stored in points,
    /// so a role that grows and keeps the point value it was struck at has quietly *loosened* — the
    /// letterforms are bigger and the space between them did not follow. Nothing on screen says so;
    /// it just stops looking like the same typeface it did at the smaller size. Recomputing from the
    /// documented `em` is the whole of the fix, and this asserts the arithmetic rather than the taste.
    func testEveryRoleTracksAtItsDocumentedEmRatioForItsOwnSize() {
        // role, em, and the tracking that ratio produces at the role's size.
        let ladder: [(name: String, style: InkTextStyle, em: CGFloat)] = [
            ("introHero", .introHero, -0.035),
            ("stepHeadline", .stepHeadline, -0.03),
            ("firstTitle", .firstTitle, -0.03),
            ("prose", .prose, -0.01),
            ("rowCopy", .rowCopy, -0.01),
            ("buttonLabel", .buttonLabel, -0.01),
        ]
        for role in ladder {
            XCTAssertEqual(
                role.style.tracking, role.style.size * role.em, accuracy: 0.005,
                "\(role.name) is \(role.style.size) pt at \(role.style.tracking) pt of tracking, which is "
                    + "\(role.style.tracking / role.style.size) em and not \(role.em) em")
        }

        // The one role with none, and the reason it is also the smallest: the ladder tightens above
        // the floor, never on it or under it.
        XCTAssertEqual(InkType.statusLabel.tracking, 0)
        XCTAssertEqual(InkType.statusLabel.size, InkType.minimumSize)
    }

    /// The permissions card has to *fit the window*, which the type scale alone cannot promise.
    ///
    /// The step is a headline, a four-line preamble and four rows whose copy is a whole sentence, and
    /// at 488 pt every one of those rows wrapped to two lines once row copy reached 15 pt — which put
    /// the card past the bottom of a 520 pt window and silently truncated the sentences the step
    /// exists to have read. The width is what pays for the size, so the width is asserted with it.
    @MainActor
    func testTheListColumnIsWideEnoughToHoldTheLargerTypeAndNarrowEnoughToStayOnTheSheet() {
        XCTAssertGreaterThan(
            InkLayout.permissionsMaxWidth, InkLayout.contentMaxWidth,
            "the list column is wider than the reading column; that difference is what fits the rows")

        // The sheet is an ellipse that starts dissolving past ~0.78 of the frame radius. A column
        // wider than that is drawn on the desktop rather than on the card.
        let card = OnboardingWindow.cardSize.width
        XCTAssertLessThanOrEqual(
            InkLayout.permissionsMaxWidth, card * 0.78,
            "a \(InkLayout.permissionsMaxWidth) pt column runs past the backdrop's falloff on a \(card) pt card"
        )

        // The reading column keeps its measure: at 17 pt, 488 pt is already near 80 characters a
        // line, and a paragraph does not get more readable by getting wider.
        XCTAssertLessThanOrEqual(
            InkLayout.contentMaxWidth / InkType.prose.size, 30,
            "the reading column is \(InkLayout.contentMaxWidth / InkType.prose.size) em of prose")

        // Vertical padding is not a place to find height for bigger type: the falloff is far steeper
        // vertically, so anything taken from here is type dissolving into the desktop.
        XCTAssertGreaterThanOrEqual(InkLayout.pagePaddingVertical, 34)
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

    // MARK: - Colour

    /// The label ladder has to stay *readable*, in both appearances, and not only ordered.
    ///
    /// It shipped once on `secondaryLabelColor` / `tertiaryLabelColor`, whose alphas are tuned for
    /// dense system chrome: over `Ink.surface` in Light those measure 3.95:1 and 1.88:1, so the step
    /// that carries onboarding's prose was under WCAG AA for body text and the step below it was
    /// barely a shade. It was reported as exactly that — onboarding being hard to read. Restoring
    /// either system colour, or thinning the alphas towards them, has to fail here.
    ///
    /// Every value is read back out of `Ink` itself and resolved under a real `NSAppearance`, so
    /// this asserts what the app draws rather than a constant copied alongside it.
    @MainActor
    func testTheLabelLadderMeetsWCAGAAInBothAppearances() {
        for appearance in [NSAppearance.Name.aqua, .darkAqua] {
            let ladder = InkContrastProbe.ladder(under: appearance)

            // Body copy: `prose` and `rowCopy` are set in these two, and both are under 18 pt, so
            // the bar is AA's 4.5:1 for normal text and not the 3:1 large-text allowance.
            XCTAssertGreaterThanOrEqual(
                ladder.secondary, 4.5,
                "secondary carries whole sentences and is \(ladder.secondary):1 in \(appearance.rawValue)")
            XCTAssertGreaterThanOrEqual(
                ladder.tertiary, 4.5,
                "tertiary is \(ladder.tertiary):1 in \(appearance.rawValue)")

            // The step that carries sustained reading is held to AAA, which is what the 0.80 alpha
            // was chosen for; without this the pair could satisfy AA and still be flat.
            XCTAssertGreaterThanOrEqual(ladder.secondary, 7.0, appearance.rawValue)

            // …and it is still a ladder: three distinct steps, in order, not one colour three times.
            XCTAssertGreaterThan(ladder.primary, ladder.secondary, appearance.rawValue)
            XCTAssertGreaterThan(ladder.secondary, ladder.tertiary, appearance.rawValue)
        }
    }

    /// The rungs have to stay *visibly* apart, which contrast ratio alone does not say — a ratio is
    /// a legibility measure, not a perceptual distance. L* is, so the gaps are asserted in L*.
    ///
    /// 8 is the floor rather than a target: it is comfortably above the ~2 L* two large fields of
    /// flat colour can be told apart at, and it is the guard against the obvious wrong fix for a
    /// contrast complaint, which is to drag every step up to `primary` and lose the hierarchy.
    @MainActor
    func testTheLabelLadderKeepsVisibleStepsBetweenItsRungs() {
        for appearance in [NSAppearance.Name.aqua, .darkAqua] {
            let lightness = InkContrastProbe.lightness(under: appearance)
            XCTAssertGreaterThanOrEqual(
                abs(lightness.primary - lightness.secondary), 8,
                "primary/secondary are \(lightness.primary) / \(lightness.secondary) L* in \(appearance.rawValue)"
            )
            XCTAssertGreaterThanOrEqual(
                abs(lightness.secondary - lightness.tertiary), 8,
                "secondary/tertiary are \(lightness.secondary) / \(lightness.tertiary) L* in \(appearance.rawValue)"
            )
        }
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

    // MARK: - Capability rows

    /// A row built the way the popover builds it, from the same grouped report the engine publishes.
    private func rows(granted isGranted: @escaping (Capability) -> Bool) -> [MenuBarCapabilityRow] {
        Permissions.groupedReport(granted: isGranted)
            .map { MenuBarCapabilityRow(report: $0, isGranted: isGranted) }
    }

    private func row(_ group: CapabilityGroup, granted: @escaping (Capability) -> Bool)
        -> MenuBarCapabilityRow
    {
        rows(granted: granted).first { $0.group == group }!
    }

    /// **The row that could not say which half was missing.**
    ///
    /// `CapabilityGroup.screen` is Screen Recording *and* Accessibility, and `groupedReport` ANDs
    /// them — so with the screen granted and Accessibility not, the popover read
    /// `Screen — Action required` over a screen that was being captured perfectly well. The user
    /// opened Privacy & Security ▸ Screen Recording, found this app already ticked, and had nothing
    /// to tell them the missing grant was in a different pane. The four-word status vocabulary
    /// cannot express which member, and is not asked to: the **noun** names the work that remains.
    func testAHalfGrantedGroupNamesTheMemberThatIsMissingRatherThanTheGroup() {
        let screen = row(.screen, granted: { $0 != .accessibility })
        XCTAssertEqual(screen.noun, "Accessibility")
        XCTAssertFalse(screen.granted)

        // The symmetrical case, which had the same defect: the microphone works, the system-audio
        // tap does not, and the row said "Microphone".
        let microphone = row(.microphone, granted: { $0 != .systemAudio })
        XCTAssertEqual(microphone.noun, "System audio")
        XCTAssertFalse(microphone.granted)
    }

    /// With nothing granted, the noun is the group's own — the first thing to do is the thing the
    /// group is named after, so renaming the row there would be churn with no information in it.
    func testAWhollyMissingGroupKeepsItsOwnNoun() {
        XCTAssertEqual(row(.screen, granted: { _ in false }).noun, "Screen")
        XCTAssertEqual(row(.microphone, granted: { _ in false }).noun, "Microphone")
    }

    /// And a settled group is called what it has always been called. A row whose name moved while
    /// nothing was wrong would make the popover unreadable at a glance, which is its only job.
    func testAGrantedGroupKeepsItsOwnNounAndReportsGranted() {
        for row in rows(granted: { _ in true }) {
            XCTAssertTrue(row.granted)
            XCTAssertEqual(row.noun, row.group.namesake.noun)
        }
        XCTAssertEqual(rows(granted: { _ in true }).map(\.noun), ["Microphone", "Screen"])
    }

    /// **The status column is untouched.** `docs/design-system.md` § Permission row fixes it at four
    /// words, and the whole point of moving the noun is that the vocabulary did not have to grow a
    /// fifth. `Permissions` stays its only author — this type passes `detail` through unchanged.
    func testTheStatusWordStaysInsideTheDesignSystemVocabulary() {
        let vocabulary: Set<String> = ["Granted", "Open", "Checking", "Action required"]
        for granted in [
            { (_: Capability) in true }, { (_: Capability) in false }, { $0 != Capability.accessibility },
        ] {
            for (row, report) in zip(rows(granted: granted), Permissions.groupedReport(granted: granted)) {
                XCTAssertTrue(vocabulary.contains(row.status), row.status)
                XCTAssertEqual(row.status, report.detail, "the status word is not this type's to decide")
                XCTAssertEqual(row.granted, report.granted)
            }
        }
    }

    /// The noun names the pane the row's own tap opens (`StatusView.handle`), which is what makes it
    /// actionable rather than merely more precise: both read `firstMissing`, so a user sent to
    /// Accessibility was told the row was about Accessibility.
    func testTheNounNamesThePaneTheTapWouldOpen() {
        for missing in Capability.allCases {
            let isGranted: (Capability) -> Bool = { $0 != missing }
            guard let group = CapabilityGroup.allCases.first(where: { $0.members.contains(missing) }) else {
                return XCTFail("\(missing) belongs to no group")
            }
            XCTAssertEqual(row(group, granted: isGranted).noun, missing.noun)
        }
    }
}

// MARK: - The bundled faces

/// Registers the bundled faces the way the app shell does, so every type assertion in the suite
/// exercises the real resolution path rather than a stand-in.
///
/// The test bundle is not the app bundle, so `Bundle.main.resourceURL` cannot be used here; the
/// files are found relative to this source file instead. `CTFontManagerRegisterFontsForURL` returns
/// false when a face is already registered in the process, so the return value is deliberately
/// ignored and resolution is what gets checked.
///
/// Free-standing and not private to one test class, because two suites now measure type — this one
/// and `TalkingMarkTests`, which measures whether the welcome hero fits — and a lazy static each
/// would mean whichever ran second silently measured SF Pro.
enum InkTestFonts {
    static let registered: Bool = {
        let fonts = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Resources/Fonts", isDirectory: true)
        let contents =
            (try? FileManager.default.contentsOfDirectory(at: fonts, includingPropertiesForKeys: nil)) ?? []
        for url in contents where ["otf", "ttf"].contains(url.pathExtension.lowercased()) {
            var error: Unmanaged<CFError>?
            _ = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error)
            error?.release()
        }
        InkFonts.invalidate()
        return !contents.isEmpty
    }()
}

// MARK: - Measuring the ladder

/// WCAG 2.1 contrast and CIE L*, computed on the colours `Ink` actually hands SwiftUI.
///
/// Nothing here may be a stored constant: the palette is dynamic, so every value is resolved *inside*
/// `performAsCurrentDrawingAppearance` and only then converted to sRGB — a colour read outside an
/// appearance is whatever the test host happens to be running in, which is how an assertion like this
/// silently stops covering one of the two appearances.
///
/// The lower two steps are translucent and their alpha is the whole point, so each is composited over
/// `Ink.surface` the way the compositor does before anything is measured.
@MainActor
enum InkContrastProbe {

    /// One reading of the three type steps, in whatever unit the caller asked for.
    struct Ladder {
        let primary: Double
        let secondary: Double
        let tertiary: Double
    }

    /// Contrast ratio of each step against `Ink.surface`, 1…21.
    static func ladder(under appearance: NSAppearance.Name) -> Ladder {
        measure(under: appearance, material: nil, scrim: nil, over: nil) { step, ground in
            contrast(step, ground)
        }
    }

    /// The same, against the ground the app's glass produces: `Ink.surface` at `scrim`, over the
    /// material (white at `InkGlass.measuredMaterialTint`, at `InkGlass.measuredMaterialOpacity`),
    /// over `desktop`.
    ///
    /// - Parameters:
    ///   - system: the appearance the *machine* is in. It is passed, and it is expected not to
    ///     matter: the glass pins itself, so this exists precisely so a test can prove the pin wins.
    ///   - desktop: whatever is behind the window. Callers pass the extremes — solid black and solid
    ///     solid white — because those are the two grounds a translucent panel can be worst on.
    ///
    /// The two-layer model is the only way to assert this at all in a process that has no desktop
    /// behind its windows. It is not a guess: `InkGlass.measuredMaterialOpacity` and
    /// `measuredMaterialTint` are sampled off the real material, and the model reproduces the
    /// sampled composite to under 1/255 at every scrim it was checked at.
    static func glassLadder(system: NSAppearance.Name, over desktop: Color) -> Ladder {
        var ladder = Ladder(primary: 0, secondary: 0, tertiary: 0)
        // The machine's appearance on the outside, the glass's pin on the inside — the same nesting
        // the view produces, where a pinned `NSView` inside a Dark window resolves its colours light.
        NSAppearance(named: system)!.performAsCurrentDrawingAppearance {
            NSAppearance(named: InkGlass.appearanceName)!.performAsCurrentDrawingAppearance {
                let tint = RGBA(
                    r: 255 * Double(InkGlass.measuredMaterialTint),
                    g: 255 * Double(InkGlass.measuredMaterialTint),
                    b: 255 * Double(InkGlass.measuredMaterialTint),
                    a: Double(InkGlass.measuredMaterialOpacity))
                // Sampled in 0…255, everything else in 0…1: normalise before compositing.
                let frosted = composite(
                    RGBA(r: tint.r / 255, g: tint.g / 255, b: tint.b / 255, a: tint.a),
                    over: components(desktop))
                let scrim = InkGlass.groundAlpha(reduceTransparency: false)
                let ground = composite(components(Ink.surface, alpha: scrim), over: frosted)
                ladder = Ladder(
                    primary: contrast(components(Ink.primary), ground),
                    secondary: contrast(components(Ink.secondary), ground),
                    tertiary: contrast(components(Ink.tertiary), ground))
            }
        }
        return ladder
    }

    /// The relative luminance of a colour resolved under the glass's own appearance, so a test can
    /// assert the thing that is easiest to get catastrophically wrong: that the type on a light panel
    /// is *dark*.
    static func glassLuminance(_ color: Color) -> Double {
        var value = 0.0
        NSAppearance(named: InkGlass.appearanceName)!.performAsCurrentDrawingAppearance {
            value = luminance(components(color))
        }
        return value
    }

    /// CIE L* of each step once composited — perceptual lightness, which is what "these two are
    /// visibly different" actually means.
    static func lightness(under appearance: NSAppearance.Name) -> Ladder {
        measure(under: appearance, material: nil, scrim: nil, over: nil) { step, ground in
            let y = luminance(composite(step, over: ground))
            return y > 0.008856 ? 116 * pow(y, 1.0 / 3.0) - 16 : 903.3 * y
        }
    }

    private struct RGBA {
        var r: Double, g: Double, b: Double, a: Double
    }

    private static func contrast(_ step: RGBA, _ ground: RGBA) -> Double {
        let luminances = [luminance(composite(step, over: ground)), luminance(ground)]
        return (luminances.max()! + 0.05) / (luminances.min()! + 0.05)
    }

    /// The opaque sheet. Everything is resolved *inside* the appearance, which is the whole reason
    /// this takes values rather than a prepared ground — a dynamic colour read outside one is
    /// whatever the host happens to be in.
    private static func measure(
        under appearance: NSAppearance.Name,
        material: CGFloat?,
        scrim: CGFloat?,
        over desktop: Color?,
        _ body: (RGBA, RGBA) -> Double
    ) -> Ladder {
        var ladder = Ladder(primary: 0, secondary: 0, tertiary: 0)
        NSAppearance(named: appearance)!.performAsCurrentDrawingAppearance {
            let ground = components(Ink.surface)
            ladder = Ladder(
                primary: body(components(Ink.primary), ground),
                secondary: body(components(Ink.secondary), ground),
                tertiary: body(components(Ink.tertiary), ground))
        }
        return ladder
    }

    private static func components(_ color: Color, alpha: CGFloat = 1) -> RGBA {
        let resolved = NSColor(color).usingColorSpace(.sRGB)!
        return RGBA(
            r: Double(resolved.redComponent),
            g: Double(resolved.greenComponent),
            b: Double(resolved.blueComponent),
            a: Double(resolved.alphaComponent) * Double(alpha))
    }

    /// Source-over, in the same premultiplied form the compositor uses.
    private static func composite(_ fg: RGBA, over bg: RGBA) -> RGBA {
        RGBA(
            r: fg.r * fg.a + bg.r * (1 - fg.a),
            g: fg.g * fg.a + bg.g * (1 - fg.a),
            b: fg.b * fg.a + bg.b * (1 - fg.a),
            a: 1)
    }

    /// Relative luminance, WCAG 2.1 §Relative luminance: linearise each channel, then weight.
    private static func luminance(_ c: RGBA) -> Double {
        func linear(_ channel: Double) -> Double {
            channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(c.r) + 0.7152 * linear(c.g) + 0.0722 * linear(c.b)
    }
}
