import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// **A live microphone must never be allowed to hide a dead screen.**
///
/// The failure this file exists for is dated and measured. On 2 August 2026 the app bundle was
/// re-signed at 14:33:28; macOS keys a Screen Recording grant to the code signature, so the grant
/// died with the old signature while the microphone's — keyed differently — survived. The last
/// screen frame in the database is from 14:20:48, thirteen minutes earlier. Audio segments kept
/// landing for another twenty-nine hours. Throughout, `capture-state.json` read:
///
///     {"capturing": true, "pausedReason": "Screen off — Screen Recording permission not granted"}
///
/// `capturing` came from `!isPaused && !running.isEmpty && !storageFailed`, which is an **or** over
/// three independent sensors read by every surface downstream as an **and**. The menu bar drew
/// "Listening", the MCP `status` tool headlined "Context for Claude is capturing right now" — and
/// `Queries.status` had already discarded that `pausedReason`, because it cleared the reason
/// whenever `capturing` was true. Claude then answered "what was I looking at?" from a screen record
/// that had stopped the previous afternoon.
///
/// The assertions below run the real published-state function over real component states rather
/// than checking that some source string exists. `Engine.publishedState` is the exact code
/// `Engine.publishState()` calls on every transition, and the `CaptureState` it returns is the exact
/// value written to `capture-state.json` and read by `context-for-claude-mcp`.
@MainActor
final class CaptureHealthTests: XCTestCase {

    // MARK: - The regression

    /// The whole bug in one assertion: microphone live, screen blocked, storage open.
    func testALiveMicrophoneDoesNotMakeADeadScreenReadAsCapturing() {
        let state = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .live,
                .systemAudio: .live,
                .screen: .blocked("Screen off — Screen Recording permission not granted"),
            ],
            isPaused: false)

        XCTAssertFalse(
            state.capturing,
            "this is the twenty-nine-hour lie: one live sensor reported as a capturing recorder")
        XCTAssertEqual(
            state.health, .degraded,
            "audio really is being recorded, so `off` would be the opposite lie — the app has to "
                + "be able to say *half*")
        XCTAssertEqual(
            state.stream(StreamName.screen)?.state, .blocked,
            "the heartbeat has to name which half is down, not just that something is")
        XCTAssertEqual(state.stream(StreamName.microphone)?.state, .live)
        XCTAssertEqual(
            state.pausedReason,
            "Screen off — Screen Recording permission not granted",
            "the reason survives to the file rather than being cleared by a true `capturing`")
    }

    /// …and the same facts have to survive the trip through `capture-state.json`, because that file
    /// is the only channel between the app and every reader of it.
    func testTheDeadHalfSurvivesEncodingToTheHeartbeatFile() throws {
        let published = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .live,
                .systemAudio: .off("Call audio off — permission not granted"),
                .screen: .stalled("Screen capture has produced nothing for 31 minutes"),
            ],
            isPaused: false)

        let round = try JSONDecoder().decode(
            CaptureState.self, from: try JSONEncoder().encode(published))

        XCTAssertFalse(round.capturing)
        XCTAssertEqual(round.health, .degraded)
        XCTAssertEqual(round.failingStreams.map(\.name), [StreamName.screen])
        XCTAssertEqual(
            round.stream(StreamName.systemAudio)?.state, .off,
            "a capability the user never granted is the app doing as it was told, not a failure")
    }

    /// An older `context-for-claude-mcp` binary reading a file this app writes.
    ///
    /// The MCP server is spawned per Claude session from whatever path `~/.claude.json` records, so
    /// a stale binary reading a fresh heartbeat is the ordinary case rather than the exotic one. It
    /// knows nothing about `streams`, so all it can see is `capturing` — and what it must see there
    /// is `false`, which renders as "not capturing right now — Screen off …". Strictly better than
    /// the confident falsehood it used to print.
    func testAnOlderReaderSeesAnHonestBooleanAndAReason() throws {
        let published = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .live,
                .systemAudio: .live,
                .screen: .blocked("Screen Recording has stopped working"),
            ],
            isPaused: false)

        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: try JSONEncoder().encode(published))
                as? [String: Any])

        XCTAssertEqual(json["capturing"] as? Bool, false)
        XCTAssertEqual(json["pausedReason"] as? String, "Screen Recording has stopped working")
    }

    /// The other direction: this app's reader meeting a heartbeat an older app wrote, which has no
    /// `streams` key at all. A synthesised `Codable` would throw on the missing key, and a decode
    /// failure here reads to the user as "Context for Claude is not running" while it demonstrably
    /// is — so the tolerance is asserted rather than assumed.
    func testAHeartbeatWithNoStreamsStillDecodes() throws {
        let legacy = Data(
            """
            {"capturing":true,"pausedReason":null,"capabilities":[],"updatedAt":1785799844.868408}
            """.utf8)

        let state = try JSONDecoder().decode(CaptureState.self, from: legacy)

        XCTAssertTrue(state.capturing)
        XCTAssertTrue(state.streams.isEmpty)
        XCTAssertEqual(
            state.health, .capturing,
            "with no per-stream detail the boolean is all there is, and it has to be honoured")
    }

    // MARK: - The states that must NOT read as broken

    /// A user who declined system audio has not got a broken recorder, and telling them they have —
    /// every day, forever — is how a warning stops being read. `off` is the app doing as it was
    /// told; only a promise that has stopped being kept is `blocked`.
    func testACapabilityTheUserNeverGrantedDoesNotDegradeTheApp() {
        let state = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .live,
                .systemAudio: .off("Call audio off — permission not granted"),
                .screen: .live,
            ],
            isPaused: false)

        XCTAssertTrue(state.capturing)
        XCTAssertEqual(state.health, .capturing)
        XCTAssertEqual(
            state.pausedReason, "Call audio off — permission not granted",
            "still said out loud — a gap the user chose is still a gap in the record")
    }

    /// "Pause on Inactivity" is the same shape of fact and gets the same treatment: capture is
    /// standing down exactly as the switch promises, so the sentence appears and the app does not
    /// start calling itself broken every time its owner goes to lunch.
    func testTheIdlePauseDoesNotReadAsAFailure() {
        let state = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .live,
                .systemAudio: .live,
                .screen: .off(CaptureActivity.pausedSentence),
            ],
            isPaused: false)

        XCTAssertEqual(state.health, .capturing)
        XCTAssertTrue(state.failingStreams.isEmpty)
        XCTAssertEqual(state.pausedReason, CaptureActivity.pausedSentence)
    }

    // MARK: - The states that must read as off

    /// A database that will not open makes every live sensor pointless: nothing is being recorded,
    /// whatever the microphone thinks it is doing.
    func testAStoreThatWillNotOpenMakesTheWholeAppOff() {
        let state = Engine.publishedState(
            components: [
                .storage: .blocked("Could not open the database: disk full"),
                .microphone: .live,
                .systemAudio: .live,
                .screen: .live,
            ],
            isPaused: false)

        XCTAssertFalse(state.capturing)
        XCTAssertEqual(state.health, .off)
    }

    /// A store still opening is **not** that: the sensors are genuinely capturing and `EngineStore`
    /// is holding what they produce until there is somewhere to put it.
    func testAStoreThatIsStillOpeningDoesNotStopCapture() {
        let state = Engine.publishedState(
            components: [
                .storage: .starting(nil),
                .microphone: .live,
                .systemAudio: .live,
                .screen: .live,
            ],
            isPaused: false)

        XCTAssertTrue(state.capturing)
        XCTAssertEqual(state.health, .capturing)
    }

    func testPausedIsPausedAndSaysOnlyThat() {
        let state = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .off("Paused"),
                .systemAudio: .off("Paused"),
                .screen: .off("Paused"),
            ],
            isPaused: true)

        XCTAssertFalse(state.capturing)
        XCTAssertEqual(state.health, .off)
        XCTAssertEqual(
            state.pausedReason, "Paused",
            "a paused pipeline must not recite the three reasons a paused pipeline has")
    }

    /// The launch window. Nothing live and nothing yet wrong is not "everything is fine" — an empty
    /// reason next to `capturing: false` is exactly the silence this app was already fixed once for.
    func testTheLaunchWindowSaysSoInsteadOfSayingNothing() {
        let state = Engine.publishedState(components: [:], isPaused: false)

        XCTAssertFalse(state.capturing)
        XCTAssertEqual(state.health, .off)
        XCTAssertEqual(state.pausedReason, "Starting up")
        XCTAssertEqual(
            state.streams.count, CaptureComponent.allCases.count,
            "every component reports, even the ones that have not started")
    }

    // MARK: - Every reason reaches the file

    /// Nothing a component has to say may be dropped on the way out, and the order is fixed so the
    /// popover's sentence does not shuffle between renders.
    func testEveryComponentsReasonReachesThePublishedState() {
        let state = Engine.publishedState(
            components: [
                .storage: .live,
                .microphone: .blocked("Microphone stopped — the audio device went away"),
                .systemAudio: .off("Call audio off — needs macOS 14.4 or later"),
                .screen: .stalled("Screen capture has produced nothing for 5 minutes"),
            ],
            isPaused: false)

        XCTAssertEqual(state.health, .off, "no sensor is live, so nothing at all is being recorded")
        let reason = state.pausedReason ?? ""
        for expected in [
            "Microphone stopped", "needs macOS 14.4 or later", "produced nothing for 5 minutes",
        ] {
            XCTAssertTrue(reason.contains(expected), "\(expected) was dropped from: \(reason)")
        }
    }

    /// `lastOutputAt` is the field that distinguishes "started" from "producing", which is the whole
    /// difference between the two failure modes this file is about.
    func testTheHeartbeatCarriesWhenEachStreamLastProducedAnything() {
        let audioAt: Double = 1_785_899_940
        let screenAt: Double = 1_785_795_648

        let state = Engine.publishedState(
            components: [.storage: .live, .microphone: .live, .systemAudio: .live, .screen: .live],
            isPaused: false,
            lastOutput: [.microphone: audioAt, .screen: screenAt])

        XCTAssertEqual(state.stream(StreamName.microphone)?.lastOutputAt, audioAt)
        XCTAssertEqual(
            state.stream(StreamName.screen)?.lastOutputAt, screenAt,
            "a reader has to be able to see that the screen half last produced anything a day ago")
    }

    // MARK: - The menu bar

    /// Three states, three glyphs. Two glyphs over one boolean is what drew a recorder with a dead
    /// screen exactly like a healthy one on the surface a user actually glances at.
    func testTheMenuBarDrawsAllThreeStatesDifferently() {
        let marks = [
            StatusItemController.mark(for: .capturing),
            StatusItemController.mark(for: .degraded),
            StatusItemController.mark(for: .off),
        ]

        for mark in marks {
            XCTAssertTrue(mark.isTemplate, "macOS owns the colour of a menu bar glyph")
            XCTAssertEqual(mark.size, ContextMark.menuBarSize)
        }
        XCTAssertNotIdentical(marks[0], marks[1], "degraded must not be drawn as healthy")
        XCTAssertNotIdentical(marks[1], marks[2], "degraded must not be drawn as off either")
        XCTAssertTrue(
            StatusItemController.tooltip(for: .degraded).lowercased().contains("stopped"),
            "the tooltip is the only text this surface has: \(StatusItemController.tooltip(for: .degraded))")
    }
}
