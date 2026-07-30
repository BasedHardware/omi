import AppKit
import XCTest

@testable import ContextApp

// MARK: - The step machine

/// The ordering, the skip and the back button.
///
/// These are pure functions on `OnboardingStep` precisely so they can be asserted: the order the
/// cards come in is a product decision with a wrong answer available — asking macOS for a microphone
/// before the account those recordings land in is known — and a `View` is not a place a decision like
/// that can be tested.
final class OnboardingStepMachineTests: XCTestCase {

    /// The spec's order, `docs/first-run-experience.md` Phase 4: welcome → value → sign in →
    /// permissions → connectors → tutorial intro.
    ///
    /// Sign-in before permissions is the load-bearing part. Everything this app records lands in an
    /// Omi account, the permissions are what start the recording, so the account has to be known
    /// first. The connector is local configuration and can wait; consent cannot.
    func testTheItineraryFollowsTheSpecOrder() {
        XCTAssertEqual(
            OnboardingStep.itinerary(signedIn: false),
            [.welcome, .value, .signIn, .permissions, .connector, .tutorial, .done])
    }

    /// A restored session skips the sign-in card and nothing else, which is what keeps a reinstall
    /// one click.
    func testARestoredSessionSkipsSignInAndOnlySignIn() {
        let itinerary = OnboardingStep.itinerary(signedIn: true)
        XCTAssertEqual(itinerary, [.welcome, .value, .permissions, .connector, .tutorial, .done])
        XCTAssertFalse(itinerary.contains(.signIn))
        XCTAssertEqual(OnboardingStep.next(after: .value, signedIn: true), .permissions)
    }

    func testNextWalksTheItineraryAndEndsAtDone() {
        for signedIn in [true, false] {
            let itinerary = OnboardingStep.itinerary(signedIn: signedIn)
            for (index, step) in itinerary.enumerated() where index + 1 < itinerary.count {
                XCTAssertEqual(
                    OnboardingStep.next(after: step, signedIn: signedIn),
                    itinerary[index + 1],
                    "after \(step), signedIn: \(signedIn)")
            }
            XCTAssertNil(
                OnboardingStep.next(after: .done, signedIn: signedIn),
                "the flow has to end; a next step after .done would loop the finale")
        }
    }

    /// Back exists only while nothing irreversible has happened.
    ///
    /// From `.permissions` onward there is nothing to go back to: macOS shows each TCC prompt exactly
    /// once and will not un-ask, so a card reached by "back" could not do anything. A button that
    /// cannot work is worse than no button, which is why these are nil rather than best-effort.
    func testBackIsOfferedOnlyBeforeAnythingIrreversibleHasHappened() {
        XCTAssertNil(OnboardingStep.back(from: .welcome, signedIn: false), "nothing precedes welcome")
        XCTAssertEqual(OnboardingStep.back(from: .value, signedIn: false), .welcome)
        XCTAssertEqual(OnboardingStep.back(from: .signIn, signedIn: false), .value)

        for step: OnboardingStep in [.permissions, .connector, .tutorial, .done] {
            XCTAssertNil(
                OnboardingStep.back(from: step, signedIn: false),
                "\(step) is past the point where anything can be un-asked")
        }
    }

    /// A skipped card is not a card you can reach backwards either.
    func testBackNeverLandsOnACardTheItinerarySkipped() {
        XCTAssertNil(OnboardingStep.back(from: .signIn, signedIn: true))
        for signedIn in [true, false] {
            let itinerary = Set(OnboardingStep.itinerary(signedIn: signedIn))
            for step in OnboardingStep.allCases {
                guard let target = OnboardingStep.back(from: step, signedIn: signedIn) else { continue }
                XCTAssertTrue(itinerary.contains(target), "back from \(step) reached a skipped card")
            }
        }
    }

    /// The dots count work, not screens: the welcome card is before the flow starts and `.done` is
    /// after it ends.
    func testProgressDotsCountOnlyTheCardsOfActualWork() {
        XCTAssertEqual(
            OnboardingStep.progressSteps(signedIn: false),
            [.value, .signIn, .permissions, .connector, .tutorial])
        XCTAssertEqual(OnboardingStep.progressSteps(signedIn: true).count, 4)

        XCTAssertNil(OnboardingStep.progressIndex(of: .welcome, signedIn: false))
        XCTAssertNil(OnboardingStep.progressIndex(of: .done, signedIn: false))
        XCTAssertEqual(OnboardingStep.progressIndex(of: .value, signedIn: false), 0)
        XCTAssertEqual(OnboardingStep.progressIndex(of: .tutorial, signedIn: false), 4)
        // The lit dot never runs off the end of the row it is drawn in.
        for step in OnboardingStep.allCases {
            guard let index = OnboardingStep.progressIndex(of: step, signedIn: true) else { continue }
            XCTAssertLessThan(index, OnboardingStep.progressSteps(signedIn: true).count)
        }
    }
}

// MARK: - Asking one at a time

/// A `PermissionAsking` that records the shape of the run rather than the answers.
///
/// The overlap check is the point: it fails if a second `request` is ever in flight while the first
/// has not returned, which is the exact bug the one-at-a-time pacing exists to prevent — macOS shows
/// one TCC alert at a time, and three fired concurrently stack dialogs the user answers blind.
@MainActor
private final class RecordingAsker: PermissionAsking {
    /// Capabilities that answer "granted" when asked.
    var grants: Set<Capability>
    /// Capabilities already granted before the run starts.
    var alreadyGranted: Set<Capability> = []

    private(set) var asked: [Capability] = []
    private(set) var sawOverlap = false
    private var inFlight = 0

    init(grants: Set<Capability>) {
        self.grants = grants
    }

    func isGranted(_ capability: Capability) -> Bool {
        alreadyGranted.contains(capability)
    }

    func request(_ capability: Capability) async -> Bool {
        if inFlight > 0 { sawOverlap = true }
        inFlight += 1
        asked.append(capability)
        // A suspension point inside the ask, so a caller that fired two of these concurrently would
        // genuinely interleave here rather than happening to run to completion in order.
        await Task.yield()
        inFlight -= 1
        let granted = grants.contains(capability)
        if granted { alreadyGranted.insert(capability) }
        return granted
    }
}

/// The pacing constants are real seconds in production. Every test drives the run at zero, so the
/// suite stays hermetic and instant while the ordering, the non-overlap and the refusal handling —
/// the parts with bugs in them — are exercised exactly as they ship.
@MainActor
private func instantRun(_ asker: PermissionAsking) -> PermissionRun {
    PermissionRun(
        asking: asker,
        leadIn: .zero,
        afterGrant: .zero,
        settleDeadline: .zero,
        settlePoll: .zero)
}

final class PermissionSequencingTests: XCTestCase {

    /// One at a time, in the fixed order, never two at once.
    @MainActor
    func testPermissionsAreAskedOneAtATimeInTheFixedOrder() async {
        let asker = RecordingAsker(grants: [.microphone, .systemAudio, .screen])
        let landed = await instantRun(asker).run([.microphone, .systemAudio, .screen])

        XCTAssertEqual(asker.asked, [.microphone, .systemAudio, .screen])
        XCTAssertFalse(asker.sawOverlap, "two TCC dialogs were in flight at once")
        XCTAssertEqual(landed, [.microphone, .systemAudio, .screen])
    }

    /// A refusal must not stall the rest of the run.
    ///
    /// `settle` polls for a grant that will never arrive, so the only thing that gets the sequence
    /// past a "no" is the deadline. Without it the run stops on the first decline and the user is
    /// left on a card that never finishes — with two permissions they were never asked for.
    @MainActor
    func testADeclineDoesNotStallTheRestOfTheRun() async {
        let asker = RecordingAsker(grants: [.microphone, .screen])  // system audio says no
        let landed = await instantRun(asker).run([.microphone, .systemAudio, .screen])

        XCTAssertEqual(
            asker.asked, [.microphone, .systemAudio, .screen],
            "the run stopped at the refusal instead of carrying on")
        XCTAssertEqual(landed, [.microphone, .screen])
        XCTAssertFalse(landed.contains(.systemAudio))
    }

    /// Anything already granted is not asked about again. A returning user re-prompted for a
    /// permission they gave last week has been told the app forgot.
    @MainActor
    func testAlreadyGrantedCapabilitiesAreNotAskedAgain() async {
        let asker = RecordingAsker(grants: [.systemAudio, .screen])
        asker.alreadyGranted = [.microphone]
        let landed = await instantRun(asker).run([.microphone, .systemAudio, .screen])

        XCTAssertEqual(asker.asked, [.systemAudio, .screen])
        XCTAssertEqual(landed, [.microphone, .systemAudio, .screen])
    }

    /// The production pacing is what it is because it was tuned once and must not silently drift:
    /// the row is lit alone long enough to read before the dialog covers it, and the new checkmark
    /// is on screen long enough to be witnessed before the next dialog opens over it.
    func testTheDeliberatePacingIsStillInPlace() {
        XCTAssertEqual(PermissionRun.leadIn, .milliseconds(900))
        XCTAssertEqual(PermissionRun.afterGrant, .milliseconds(1_100))
        XCTAssertEqual(PermissionRun.settleDeadline, .seconds(2))
    }
}

// MARK: - Grouping

final class CapabilityGroupTests: XCTestCase {

    /// A group reads "Granted" only when **every** member is.
    ///
    /// This is the one thing the menu bar row cannot get wrong. "Microphone" stands for the mic *and*
    /// the system-audio tap; "Screen" for the pixels *and* the window text. A row that says granted
    /// over a half-missing capability is the row lying about what the app can do.
    func testAGroupIsGrantedOnlyWhenEveryMemberIs() {
        XCTAssertEqual(CapabilityGroup.microphone.members, [.microphone, .systemAudio])
        XCTAssertEqual(CapabilityGroup.screen.members, [.screen, .accessibility])

        for group in CapabilityGroup.allCases {
            XCTAssertTrue(group.isGranted { group.members.contains($0) }, "\(group) with all members in")
            for missing in group.members {
                XCTAssertFalse(
                    group.isGranted { $0 != missing },
                    "\(group) read as granted while \(missing) was missing")
            }
        }
    }

    /// The status word comes from the first member still waiting, so the row describes the work that
    /// remains rather than the best case.
    func testTheGroupReportsTheNearestMissingMemberFirst() {
        XCTAssertEqual(CapabilityGroup.screen.firstMissing { $0 != .accessibility }, .accessibility)
        XCTAssertEqual(CapabilityGroup.screen.firstMissing { _ in false }, .screen)
        XCTAssertNil(CapabilityGroup.microphone.firstMissing { _ in true })
    }

    /// The same rule through the report the menu bar actually renders.
    func testTheGroupedReportCarriesTheRuleThroughToTheMenuBar() {
        let halfMissing = Permissions.groupedReport { $0 == .microphone }
        let microphone = halfMissing.first { $0.name == CapabilityGroup.microphone.rawValue }
        XCTAssertEqual(microphone?.granted, false, "the mic alone must not read as the group granted")

        let all = Permissions.groupedReport { _ in true }
        XCTAssertEqual(all.count, CapabilityGroup.allCases.count)
        XCTAssertTrue(all.allSatisfy(\.granted))
    }
}

// MARK: - Locating the real row

/// A stand-in accessibility tree, so the locator runs with no System Settings, no grant, and no
/// window server.
private struct FakeElement: SettingsElement {
    var elementRole: String?
    var elementIdentifier: String?
    var elementValue: String?
    var elementFrame: CGRect?
    var children: [FakeElement] = []

    var elementChildren: [any SettingsElement] { children }
}

/// The two pane shapes measured on macOS 26.5.2 (build 25F84), reproduced from the real trees dumped
/// off this machine — different structures, one pair of identifiers.
private enum PaneFixture {
    static let appName = "Context for Claude"

    static func title(_ name: String, y: CGFloat) -> FakeElement {
        FakeElement(
            elementRole: kAXStaticTextRole,
            elementIdentifier: "\(name)_Title",
            elementValue: name,
            elementFrame: CGRect(x: 611, y: y, width: 146, height: 24))
    }

    static func toggle(_ name: String, y: CGFloat, on: Bool) -> FakeElement {
        FakeElement(
            elementRole: kAXCheckBoxRole,
            elementIdentifier: "\(name)_Toggle",
            elementValue: on ? "1" : "0",
            elementFrame: CGRect(x: 1017, y: y + 6, width: 36, height: 16))
    }

    /// Microphone: flat. Label and switch are sibling leaves of one group.
    static func flatPane(apps: [String], on: Bool = false, scrollHeight: CGFloat = 800) -> FakeElement {
        var leaves: [FakeElement] = []
        for (index, app) in apps.enumerated() {
            let y = 132 + CGFloat(index) * 43
            leaves.append(title(app, y: y))
            leaves.append(toggle(app, y: y, on: on))
        }
        return FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: CGRect(x: 360, y: 34, width: 723, height: 948),
            children: [
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 583, y: 86, width: 500, height: scrollHeight),
                    children: [
                        FakeElement(
                            elementRole: kAXGroupRole,
                            elementFrame: CGRect(x: 603, y: 86, width: 460, height: 1068),
                            children: leaves)
                    ])
            ])
    }

    /// Screen Recording and Accessibility: an outline of `AXRow` → `AXCell` → leaves. `sections` is
    /// what makes the Screen Recording pane's two lists — an app appears in both.
    static func outlinePane(sections: [[String]], on: Bool = false) -> FakeElement {
        var groups: [FakeElement] = []
        var y: CGFloat = 145
        for apps in sections {
            var rows: [FakeElement] = []
            for app in apps {
                rows.append(
                    FakeElement(
                        elementRole: kAXRowRole,
                        elementFrame: CGRect(x: 603, y: y, width: 460, height: 40),
                        children: [
                            FakeElement(
                                elementRole: kAXCellRole,
                                elementFrame: CGRect(x: 603, y: y, width: 460, height: 40),
                                children: [title(app, y: y + 8), toggle(app, y: y + 8, on: on)])
                        ]))
                y += 40
            }
            groups.append(
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 603, y: 145, width: 460, height: 1_600),
                    children: [
                        FakeElement(
                            elementRole: kAXOutlineRole,
                            elementFrame: CGRect(x: 603, y: 145, width: 460, height: 1_600),
                            children: rows)
                    ]))
            y += 60
        }
        return FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: CGRect(x: 360, y: 34, width: 723, height: 2_000),
            children: [
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 583, y: 86, width: 500, height: 1_900),
                    children: groups)
            ])
    }
}

final class SettingsRowLocatorTests: XCTestCase {
    private let locator = SettingsRowLocator(appName: PaneFixture.appName)

    /// The flat pane. The ring is the label through the switch — not the switch alone, which on a
    /// 460 pt row reads as a dot beside the thing instead of around it.
    func testFindsTheRowInTheFlatMicrophonePane() {
        let pane = PaneFixture.flatPane(apps: ["Arc", "Claude", PaneFixture.appName, "Cursor"])
        guard case .visible(let located) = locator.locate(in: pane) else {
            return XCTFail("the row was not located in the flat pane")
        }
        XCTAssertEqual(located.toggle.minX, 1017)
        XCTAssertEqual(located.row.minX, 611, "the ring starts at the label, not at the switch")
        XCTAssertEqual(located.row.maxX, 1053)
        XCTAssertFalse(located.isOn)
    }

    /// The outline pane, with its extra two levels of wrapping.
    func testFindsTheRowInTheOutlinePane() {
        let pane = PaneFixture.outlinePane(sections: [["Claude", PaneFixture.appName, "Cursor"]], on: true)
        guard case .visible(let located) = locator.locate(in: pane) else {
            return XCTFail("the row was not located in the outline pane")
        }
        XCTAssertTrue(located.isOn, "the switch's own state has to come off the switch")
        XCTAssertTrue(located.row.contains(located.toggle.center))
    }

    /// The Screen Recording pane on macOS 26 lists an app **twice** — once under "Screen & System
    /// Audio Recording" and again under "System Audio Recording Only". Ringing the wrong one is the
    /// mispositioned overlay arriving by a plausible route, so the section is chosen explicitly.
    func testDisambiguatesTheTwoSectionsOfTheScreenRecordingPane() {
        let pane = PaneFixture.outlinePane(sections: [
            ["Claude", PaneFixture.appName, "Cursor"],
            [PaneFixture.appName, "Granola"],
        ])
        guard case .visible(let screen) = locator.locate(in: pane, preferring: 0),
            case .visible(let audio) = locator.locate(in: pane, preferring: 1)
        else { return XCTFail("both sections should hold a row") }

        XCTAssertNotEqual(screen.row, audio.row)
        XCTAssertLessThan(screen.row.minY, audio.row.minY, "section 0 is the upper list")
    }

    /// Every capability picks a section explicitly, and every one picks the first.
    ///
    /// The value matters less than the fact that it is stated: the pane each capability opens has one
    /// list that is the right one, and "whichever row the walk reached first" would be correct only by
    /// luck. Measured live: a probe run against the Accessibility pane produced 477 locations, all at
    /// the identical rect, and 112 refusals — every refusal while a different pane was on screen.
    func testEveryCapabilityChoosesItsSectionExplicitly() {
        for capability in Capability.allCases {
            XCTAssertEqual(
                PermissionChoreography.sectionOccurrence(for: capability), 0,
                "\(capability) opens a pane whose first list is the right one")
        }
    }

    /// An app that is not in the list is not somebody else's row.
    func testDoesNotMistakeAnotherApplicationsRowForOurs() {
        let pane = PaneFixture.flatPane(apps: ["Arc", "Claude", "Cursor"])
        XCTAssertEqual(locator.locate(in: pane), .notFound)
    }

    /// A row scrolled out of its list still answers with a perfectly plausible frame — one that is
    /// nowhere the user can see. Reporting it as visible is exactly how a ring ends up drawn over
    /// empty screen, so the clip stack is checked against every ancestor scroll area.
    func testARowScrolledOutOfTheListIsReportedAsOffscreenRatherThanPointedAt() {
        let pane = PaneFixture.flatPane(
            apps: ["Arc", "Claude", "Comet", "Discord", "Figma", PaneFixture.appName],
            scrollHeight: 120)
        guard case .offscreen = locator.locate(in: pane) else {
            return XCTFail("a clipped row must not be reported as visible")
        }
    }

    /// The bounds are not decoration. An application can claim any number of children and nest
    /// without end, and this walk runs while the user is waiting on it.
    func testTheWalkIsBounded() {
        var deep = FakeElement(
            elementRole: kAXGroupRole, elementFrame: .zero,
            children: [
                PaneFixture.title(PaneFixture.appName, y: 0),
                PaneFixture.toggle(PaneFixture.appName, y: 0, on: true),
            ])
        for _ in 0..<80 {
            deep = FakeElement(elementRole: kAXGroupRole, elementFrame: .zero, children: [deep])
        }
        let window = FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: CGRect(x: 0, y: 0, width: 1_000, height: 1_000),
            children: [deep])
        // Nested past `maxDepth`, so it is never reached — and the walk returns rather than
        // recursing until the stack gives out.
        XCTAssertEqual(locator.locate(in: window), .notFound)
    }
}

// MARK: - Degrading honestly

final class PermissionGuidanceTests: XCTestCase {

    /// The whole contract of this file in one assertion: **a failed lookup produces a sentence, never
    /// a ring.** A confident arrow aimed at empty screen is worse than text, because the user follows
    /// it and finds nothing there.
    func testAFailedLookupDegradesToAPlainInstructionAndNeverPoints() {
        // Nothing found at all — which is what happens when Accessibility itself is not yet granted
        // and `LiveSettingsElement.systemSettingsWindows()` comes back empty.
        let nothing = PermissionChoreography.guidance(
            for: .accessibility, appName: PaneFixture.appName, windows: [])
        XCTAssertFalse(nothing.isPointing)
        guard case .instruction(let sentence) = nothing else { return XCTFail("expected an instruction") }
        XCTAssertTrue(sentence.contains("Accessibility"), "the sentence has to name the pane: \(sentence)")
        XCTAssertTrue(sentence.contains(PaneFixture.appName), "and the row: \(sentence)")

        // Found, but scrolled out of view. Still a sentence — a different one, because "scroll down"
        // is something the user can act on and "open the pane" is not.
        let clipped = PermissionChoreography.guidance(
            for: .microphone,
            appName: PaneFixture.appName,
            windows: [
                PaneFixture.flatPane(
                    apps: ["Arc", "Claude", "Comet", "Discord", "Figma", PaneFixture.appName],
                    scrollHeight: 120)
            ])
        XCTAssertFalse(clipped.isPointing)
        guard case .instruction(let scrolledSentence) = clipped else { return XCTFail("expected an instruction") }
        XCTAssertTrue(
            scrolledSentence.lowercased().contains("scroll"),
            "a row that exists but is out of view should say so: \(scrolledSentence)")
        XCTAssertNotEqual(sentence, scrolledSentence)
    }

    /// And the positive case, so the test above is not passing because nothing ever points.
    func testAVisibleRowIsPointedAt() {
        let guidance = PermissionChoreography.guidance(
            for: .microphone,
            appName: PaneFixture.appName,
            windows: [PaneFixture.flatPane(apps: ["Arc", PaneFixture.appName])])
        guard case .pointing(let located) = guidance else {
            return XCTFail("a visible row must be pointed at, or the overlay is never useful")
        }
        XCTAssertGreaterThan(located.row.width, located.toggle.width)
        XCTAssertTrue(guidance.isPointing)
    }

    /// A pane whose layout we have never seen: the identifiers gone, the labels still there. The
    /// label's text is the fallback, and it is what keeps the overlay working on a macOS that
    /// renamed the identifier rather than degrading everyone to a sentence.
    func testFallsBackToTheLabelTextWhenTheIdentifiersAreGone() {
        var pane = PaneFixture.flatPane(apps: [PaneFixture.appName])
        pane.children[0].children[0].children = pane.children[0].children[0].children.map { leaf in
            var leaf = leaf
            leaf.elementIdentifier = nil
            return leaf
        }
        guard case .pointing = PermissionChoreography.guidance(
            for: .microphone, appName: PaneFixture.appName, windows: [pane])
        else { return XCTFail("the label's own text should still find the row") }
    }

    /// Every capability has a sentence, and every sentence names a place. A capability that fell
    /// through to a generic "check System Settings" would be the degraded path degrading further.
    func testEveryCapabilityHasAnInstructionThatNamesItsPane() {
        for capability in Capability.allCases {
            let sentence = PermissionChoreography.instruction(
                for: capability, appName: PaneFixture.appName, scrolled: false)
            XCTAssertTrue(sentence.contains("Privacy & Security"), "\(capability): \(sentence)")
            XCTAssertTrue(sentence.contains(PaneFixture.appName), "\(capability): \(sentence)")
        }
    }
}

extension CGRect {
    fileprivate var center: CGPoint { CGPoint(x: midX, y: midY) }
}
