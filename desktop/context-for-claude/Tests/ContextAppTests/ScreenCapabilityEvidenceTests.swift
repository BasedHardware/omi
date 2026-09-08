import ContextCore
import XCTest

@testable import ContextApp

/// **A permission report that contradicts the capture it is about.**
///
/// Measured on a running install: `capture-state.json` carried
/// `{"name":"screen","state":"live","lastOutputAt":1786684216.66}` and
/// `{"name":"screen","granted":false,"detail":"Action required"}` in the same write, over a
/// database that had taken screen frames minutes earlier. The menu bar showed "Action required"
/// against a screen that was being captured, and the MCP `status` tool told Claude "at least one
/// capture permission is off, so a whole class of local context is missing" — a claim about the
/// user's data that the same file disproved two lines up.
///
/// Two rules end it, and they are separable because they fail in opposite directions. Observed
/// capture outranks the preflight, so a grant this process is demonstrably using cannot read as
/// missing. And a report may not be *published* as missing over a live stream, so even a writer
/// that gets the first rule wrong cannot put the contradiction on disk.
///
/// The inverse is the half worth guarding hardest: an install that has never captured must still
/// say "Action required", or this becomes a recorder that claims permissions it does not have.
final class ScreenCapabilityEvidenceTests: XCTestCase {

    // MARK: - Evidence outranks the preflight

    func testAScreenThatIsCapturingIsGrantedWhateverThePreflightSays() {
        // The reported state. `CGPreflightScreenCaptureAccess` answers a question about TCC's
        // records; pixels answer the question anyone actually asked.
        XCTAssertTrue(
            Permissions.screenIsGranted(preflight: false, capturedRecently: true),
            "a stream that produced pixels a moment ago cannot lack the permission to produce them")
    }

    func testAFreshInstallWithNoGrantAndNoCaptureStillNeedsTheUser() {
        XCTAssertFalse(
            Permissions.screenIsGranted(preflight: false, capturedRecently: false),
            "nothing granted and nothing ever captured is the user's own choice, not a stale probe")
    }

    func testAGrantedScreenIsGrantedBeforeItHasCapturedAnything() {
        // The launch window. Evidence is an *or*: it adds an answer where there was none, and never
        // takes one away.
        XCTAssertTrue(Permissions.screenIsGranted(preflight: true, capturedRecently: false))
    }

    /// Evidence is proof about *now*, so it has to expire — otherwise a grant that dies mid-life
    /// would go on being vouched for by a frame from hours ago, which is the twenty-nine-hour
    /// failure with a better alibi.
    func testEvidenceExpiresRatherThanVouchingForever() {
        Permissions.noteCaptureSucceeded(.accessibility)
        let now = ContextTime.now

        XCTAssertTrue(
            Permissions.capturedRecently(.accessibility, within: 150, now: now),
            "output that has just landed is evidence")
        XCTAssertFalse(
            Permissions.capturedRecently(.accessibility, within: 150, now: now + 151),
            "and stops being evidence once it is older than the window")
        XCTAssertFalse(
            Permissions.capturedRecently(.accessibility, within: 150, now: now - 3_600),
            "a clock that moved backwards is not fresher evidence — it is no evidence")
    }

    /// A capability this process has never produced anything from has nothing to offer, which is
    /// the state a fresh install is in for all four.
    func testACapabilityThatHasNeverProducedAnythingIsNotEvidence() {
        XCTAssertFalse(Permissions.capturedRecently(.systemAudio))
    }

    // MARK: - The write that cannot contradict itself

    func testALiveStreamRepublishesItsPermissionAsGranted() {
        let state = CaptureState(
            streams: [
                StreamReport(name: StreamName.storage, state: .live),
                StreamReport(name: StreamName.microphone, state: .live, lastOutputAt: 1_786_684_315),
                StreamReport(name: StreamName.screen, state: .live, lastOutputAt: 1_786_684_216),
            ],
            capabilities: [
                CapabilityReport(name: "microphone", granted: true, detail: "Granted"),
                CapabilityReport(name: "screen", granted: false, detail: "Action required"),
            ])

        let screen = state.capabilities.first { $0.name == "screen" }
        XCTAssertEqual(
            screen?.granted, true,
            "the exact pair this file wrote: a live screen stream beside a screen permission "
                + "reported missing")
        XCTAssertEqual(
            screen?.detail, CapabilityReport.grantedDetail,
            "a republished grant must carry the granted word too, or the row reads "
                + "\"granted — Action required\"")
    }

    func testAStreamThatIsNotLiveLeavesItsPermissionExactlyAsReported() {
        let state = CaptureState(
            streams: [
                StreamReport(name: StreamName.storage, state: .live),
                StreamReport(
                    name: StreamName.screen, state: .off,
                    detail: "Screen off — Screen Recording permission not granted"),
            ],
            capabilities: [
                CapabilityReport(name: "screen", granted: false, detail: "Action required")
            ])

        let screen = state.capabilities.first { $0.name == "screen" }
        XCTAssertEqual(
            screen?.granted, false, "a permission nobody has demonstrated is still missing")
        XCTAssertEqual(
            screen?.detail, "Action required",
            "and the word that tells the user there is work to do survives untouched")
    }

    /// The rule is per stream, not per file. A microphone that is recording says nothing whatever
    /// about the separate consent for the system-audio tap, and reconciling one from the other
    /// would hide a genuinely denied permission — the same mistake, pointing the other way.
    func testALiveStreamVouchesOnlyForItsOwnPermission() {
        let state = CaptureState(
            streams: [
                StreamReport(name: StreamName.microphone, state: .live, lastOutputAt: 1_786_684_315),
                StreamReport(
                    name: StreamName.systemAudio, state: .off,
                    detail: "Call audio off — permission not granted"),
            ],
            capabilities: [
                CapabilityReport(name: "microphone", granted: false, detail: "Action required"),
                CapabilityReport(name: "systemAudio", granted: false, detail: "Action required"),
            ])

        XCTAssertEqual(
            state.capabilities.first { $0.name == "microphone" }?.granted, true,
            "the live one is proven")
        XCTAssertEqual(
            state.capabilities.first { $0.name == "systemAudio" }?.granted, false,
            "the one that is not running has nothing vouching for it and must stay missing")
    }

    /// `accessibility` is not a capture stream — it enriches the screen stream's text — so nothing
    /// on the wire is evidence about it and the writer's answer stands.
    func testACapabilityWithNoStreamOfItsOwnIsLeftAlone() {
        let state = CaptureState(
            streams: [StreamReport(name: StreamName.screen, state: .live, lastOutputAt: 1)],
            capabilities: [
                CapabilityReport(name: "accessibility", granted: false, detail: "Action required")
            ])

        XCTAssertEqual(state.capabilities.first?.granted, false)
    }
}

/// **A capability whose prompt does not exist has already been spent.**
///
/// `PermissionRun` decides between "ask macOS" and "send them to the pane" on `promptIsSpent`, and
/// the will-prompt branch also hides the card and captions it "macOS is asking. I'll wait." For
/// Accessibility there is no dialog at any point — `Permissions.request(.accessibility)` opens the
/// pane and nothing else — so answering `false` made one press open System Settings, caption a
/// dialog that could never appear, and then open the pane a second time about two seconds later when
/// the wait that follows did its own open.
final class AccessibilityPromptTests: XCTestCase {

    func testAccessibilityHasNoPromptToSpendSoItIsAlwaysSpent() {
        XCTAssertTrue(
            Permissions.promptIsSpent(.accessibility),
            "macOS shows no Accessibility dialog, so the run must go straight to the pane rather "
                + "than waiting for one")
    }

    /// The three that really do prompt must **not** be constants. Without this, the fix above reads
    /// as "nothing ever prompts" and every capability skips its ask — the opposite defect, and a
    /// worse one, because a capability that is never requested can never be granted.
    func testTheCapabilitiesThatDoPromptStillDependOnWhetherTheyHave() {
        for capability in [Capability.microphone, .systemAudio, .screen] {
            XCTAssertFalse(
                Permissions.promptIsSpent(capability, hasPrompted: false),
                "\(capability) has a real dialog, so an unshown one is not spent")
            XCTAssertTrue(
                Permissions.promptIsSpent(capability, hasPrompted: true),
                "\(capability)'s dialog is shown exactly once; after that the pane is the only route")
        }
    }

    /// And Accessibility ignores it in both directions, because there is nothing to have shown.
    func testAccessibilityIsSpentEvenThoughItWasNeverPrompted() {
        XCTAssertTrue(Permissions.promptIsSpent(.accessibility, hasPrompted: false))
        XCTAssertTrue(Permissions.promptIsSpent(.accessibility, hasPrompted: true))
    }
}
