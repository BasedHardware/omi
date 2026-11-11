import ContextCore
import Foundation
import XCTest

@testable import ContextMCPKit

/// What `status` is allowed to tell Claude about a recorder that is only half working.
///
/// The sentence "Context for Claude is capturing right now" was printed for twenty-nine hours over
/// a Mac whose screen had not been captured since the previous afternoon — macOS dropped the Screen
/// Recording grant when the bundle was re-signed, the microphone's grant survived, and the boolean
/// behind that sentence was true if *any* sensor was alive. Worse, `Queries.status` cleared
/// `pausedReason` whenever that boolean was true, so the one sentence that named the dead half was
/// deleted on its way here. A model reading this tool had no way at all to know.
final class StatusHonestyTests: XCTestCase {

    // MARK: - The headline

    func testAHalfDeadRecorderIsNotHeadlinedAsCapturing() {
        let headline = Tools.headline(
            for: status(
                health: .degraded,
                pausedReason: "Screen off — Screen Recording permission not granted",
                streams: [
                    StreamReport(name: StreamName.microphone, state: .live),
                    StreamReport(name: StreamName.systemAudio, state: .live),
                    StreamReport(name: StreamName.screen, state: .blocked, detail: "grant dropped"),
                ]))

        XCTAssertFalse(
            headline.contains("is capturing right now"),
            "the exact sentence that was wrong for twenty-nine hours: \(headline)")
        XCTAssertTrue(headline.contains("partly"), headline)
        XCTAssertTrue(
            headline.contains("screen capture"),
            "a reader has to be told *which* half stopped, not merely that something did: \(headline)")
        XCTAssertTrue(
            headline.contains("the microphone"),
            "…and which half is still real, or the model discards good audio too: \(headline)")
        XCTAssertTrue(
            headline.contains("missing rather than absent"),
            "the whole point of this tool is that an empty answer from the dead half is not "
                + "evidence: \(headline)")
    }

    func testAWholeRecorderIsStillReportedPlainly() {
        let headline = Tools.headline(
            for: status(
                health: .capturing,
                capturing: true,
                streams: [StreamReport(name: StreamName.screen, state: .live)]))

        XCTAssertEqual(headline, "Context for Claude is capturing right now.")
    }

    func testCapturingPlusTranscriptionGapStaysVisible() {
        let gap =
            "Transcription needs a network connection to Omi — audio is still captured but nothing is being transcribed"
        let headline = Tools.headline(
            for: status(
                health: .capturing,
                capturing: true,
                pausedReason: gap,
                streams: [
                    StreamReport(name: StreamName.microphone, state: .live),
                    StreamReport(name: StreamName.systemAudio, state: .live),
                    StreamReport(name: StreamName.screen, state: .live),
                ]))

        XCTAssertEqual(
            headline,
            "Context for Claude is capturing right now — \(gap).")
    }

    func testAStoppedRecorderKeepsItsReason() {
        let headline = Tools.headline(
            for: status(health: .off, pausedReason: "Context for Claude is not running"))

        XCTAssertEqual(
            headline,
            "Context for Claude is not capturing right now — Context for Claude is not running.")
    }

    // MARK: - The per-stream block

    /// The case a permission list structurally cannot report: a grant that still reads "granted"
    /// over a stream producing nothing. That is what a Screen Recording grant made after launch
    /// looks like — window-server capture rights are fixed when a process connects — and it is
    /// invisible to every capability check in the product.
    func testAStreamThatIsGrantedAndProducingNothingIsCalledOut() throws {
        let lastFrame: Double = 1_785_795_648
        let block = try XCTUnwrap(
            Tools.failingStreamsBlock(
                status(
                    health: .degraded,
                    capabilities: [
                        CapabilityReport(name: "microphone", granted: true, detail: "Granted"),
                        CapabilityReport(name: "screen", granted: true, detail: "Granted"),
                    ],
                    streams: [
                        StreamReport(name: StreamName.microphone, state: .live),
                        StreamReport(
                            name: StreamName.screen,
                            state: .stalled,
                            detail: "Screen capture has produced nothing for 31 minutes",
                            lastOutputAt: lastFrame),
                    ])))

        XCTAssertTrue(block.contains("screen capture"), block)
        XCTAssertTrue(block.contains("producing nothing"), block)
        XCTAssertTrue(
            block.contains(ContextTime.describe(lastFrame)),
            "when it last worked is the fact that turns a complaint into a diagnosis: \(block)")
        XCTAssertFalse(
            block.contains("the microphone"),
            "a working stream must not appear in a list of broken ones: \(block)")
    }

    func testAHealthyRecorderGetsNoFailureBlockAtAll() {
        XCTAssertNil(
            Tools.failingStreamsBlock(
                status(
                    health: .capturing,
                    capturing: true,
                    streams: [
                        StreamReport(name: StreamName.microphone, state: .live),
                        StreamReport(
                            name: StreamName.systemAudio, state: .off,
                            detail: "Call audio off — permission not granted"),
                    ])),
            "a capability the user declined is in the permission list; it is not a failure")
    }

    // MARK: - The clause on an empty answer

    /// `deniedCaptureClause` is what appears under an answer that found nothing, and it used to be
    /// driven entirely by the permission list — so a stream that was granted and dead contributed
    /// nothing, and an empty `screen` search read as proof that nothing was on screen.
    func testAnEmptyAnswerSaysWhenAStreamStoppedEvenWithEveryPermissionGranted() throws {
        let clause = try XCTUnwrap(
            Tools.deniedCaptureClause(
                CaptureState(
                    streams: [
                        StreamReport(name: StreamName.storage, state: .live),
                        StreamReport(name: StreamName.microphone, state: .live),
                        StreamReport(name: StreamName.systemAudio, state: .live),
                        StreamReport(
                            name: StreamName.screen, state: .blocked,
                            detail: "Screen Recording has stopped working",
                            lastOutputAt: 1_785_795_648),
                    ],
                    capabilities: [
                        CapabilityReport(name: "microphone", granted: true, detail: "Granted"),
                        CapabilityReport(name: "screen", granted: true, detail: "Granted"),
                    ])))

        XCTAssertTrue(clause.contains("Stopped working"), clause)
        XCTAssertTrue(clause.contains("screen capture"), clause)
        XCTAssertTrue(
            clause.contains("missing rather than empty"),
            "the sentence has to forbid the inference, not merely report the fact: \(clause)")
    }

    /// **The mirror image, and the one that told Claude something false about the user's data.**
    ///
    /// A running install wrote a live `screen` stream and a `screen` permission reading
    /// `granted: false` into the same heartbeat, because the app had begun publishing the menu
    /// bar's *grouped* rows — where "Screen" stands for the pixels and the window text together —
    /// under a name every reader here takes for the Screen Recording grant. This clause then told a
    /// model that screen context "was never captured at all" over frames that were landing every
    /// few seconds, which is worse than an empty answer: it licenses a confident wrong one.
    func testAPermissionIsNeverReportedDeniedOverAStreamThatIsLive() {
        let clause = Tools.deniedCaptureClause(
            CaptureState(
                streams: [
                    StreamReport(name: StreamName.storage, state: .live),
                    StreamReport(
                        name: StreamName.microphone, state: .live, lastOutputAt: 1_786_684_315),
                    StreamReport(name: StreamName.screen, state: .live, lastOutputAt: 1_786_684_216),
                ],
                capabilities: [
                    CapabilityReport(name: "microphone", granted: true, detail: "Granted"),
                    CapabilityReport(name: "screen", granted: false, detail: "Action required"),
                ]))

        XCTAssertNil(
            clause,
            "a recorder whose every stream is live has nothing to warn about: \(clause ?? "")")
    }

    /// The same pair through the tool a user is sent to when something looks wrong.
    func testTheStatusListDoesNotCallACapturingScreenUngranted() {
        let state = CaptureState(
            streams: [
                StreamReport(name: StreamName.screen, state: .live, lastOutputAt: 1_786_684_216)
            ],
            capabilities: [
                CapabilityReport(name: "screen", granted: false, detail: "Action required")
            ])
        let rendered = Tools.renderStatus(
            status(
                health: .capturing, capturing: true, capabilities: state.capabilities,
                streams: state.streams))

        XCTAssertTrue(rendered.contains("**screen**: granted"), rendered)
        XCTAssertFalse(
            rendered.contains("At least one capture permission is off"),
            "the sentence that made a model report missing context over a live screen: \(rendered)")
    }

    /// The pre-existing behaviour, unchanged: a heartbeat with no stream detail at all still
    /// reports its denied permissions and says nothing about streams it knows nothing about.
    func testAStateWithNoStreamDetailStillReportsDeniedPermissions() throws {
        let clause = try XCTUnwrap(
            Tools.deniedCaptureClause(
                CaptureState(
                    capturing: true,
                    capabilities: [
                        CapabilityReport(name: "screen", granted: false, detail: "Open")
                    ])))

        XCTAssertTrue(clause.contains("Not granted"), clause)
        XCTAssertFalse(clause.contains("Stopped working"), clause)
    }

    // MARK: - Helpers

    private func status(
        health: CaptureHealth,
        capturing: Bool = false,
        pausedReason: String? = nil,
        capabilities: [CapabilityReport] = [],
        streams: [StreamReport] = []
    ) -> StatusInfo {
        StatusInfo(
            capturing: capturing,
            health: health,
            pausedReason: pausedReason,
            capabilities: capabilities,
            streams: streams,
            segmentCount: 1_148,
            frameCount: 2_026,
            sessionCount: 40,
            oldestAt: 1_785_600_000,
            newestAt: 1_785_899_940,
            databasePath: "/tmp/context.db")
    }
}
