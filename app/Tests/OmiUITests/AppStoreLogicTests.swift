import OmiKit
import XCTest

@testable import OmiUI

// Tests for the pure logic added with the App/AppStore wave: the chat
// transcript settle and the rewind capture-group → timeline-summary mapping.
@MainActor
final class AppStoreLogicTests: XCTestCase {
    private func message(
        _ id: String, _ text: String, _ sender: ChatSender,
        outcome: GenerationOutcome? = nil, localOnly: Bool? = nil
    ) -> ChatMessage {
        ChatMessage(
            id: id, text: text, sender: sender, createdAt: 1,
            generationOutcome: outcome, localOnly: localOnly)
    }

    func testSettleReplacesEchoAndPendingAtEchoPosition() {
        let older = message("a", "earlier", .human, outcome: .completed)
        let local = message("local", "hi", .human, localOnly: true)
        let pending = message(
            "pending:local", "", .ai, localOnly: true)
        let canonicalHuman = message("c-human", "hi", .human)
        let canonicalAssistant = message("c-ai", "hello", .ai, outcome: .completed)
        let settled = settleChatTranscript(
            current: [older, local, pending], echoId: "local",
            pendingId: "pending:local", human: canonicalHuman,
            assistant: canonicalAssistant)
        XCTAssertEqual(
            settled.map { $0.id }, ["a", "c-human", "c-ai"])
    }

    func testSettleAppendsWhenEchoIsMissing() {
        let canonicalHuman = message("c-human", "hi", .human)
        let settled = settleChatTranscript(
            current: [], echoId: "local", pendingId: "pending:local",
            human: canonicalHuman, assistant: nil)
        XCTAssertEqual(settled.map { $0.id }, ["c-human"])
    }

    func testSettleKeepsUnrelatedRowsAroundInsertion() {
        let before = message("b1", "before", .human)
        let after = message("a1", "after", .ai, outcome: .completed)
        let local = message("local", "hi", .human, localOnly: true)
        let human = message("c-human", "hi", .human)
        let assistant = message("c-ai", "hello", .ai, outcome: .completed)
        let settled = settleChatTranscript(
            current: [before, local, after], echoId: "local",
            pendingId: "pending:local", human: human, assistant: assistant)
        XCTAssertEqual(
            settled.map { $0.id }, ["b1", "c-human", "c-ai", "a1"])
    }

    func testCaptureSummariesMapGroupsToTimelineSummaries() {
        let frame = RewindFrame(
            id: "f1", capturedAtMs: 5_000, appName: "Xcode",
            windowTitle: "AppStore.swift")
        let older = RewindFrame(
            id: "f0", capturedAtMs: 1_000, appName: "Xcode",
            windowTitle: "AppStore.swift")
        // groupRewindFrames is the public constructor path for groups.
        let groups = groupRewindFrames([frame, older])
        XCTAssertEqual(groups.count, 1)
        let summaries = captureSummaries(from: groups)
        XCTAssertEqual(summaries.count, 1)
        XCTAssertEqual(summaries[0].id, "f1")
        XCTAssertEqual(summaries[0].appName, "Xcode")
        XCTAssertEqual(summaries[0].count, 2)
        XCTAssertEqual(summaries[0].capturedAtMs, 5_000)
    }

    func testAppServicesDefaultsToNilDependencies() {
        let services = AppServices()
        XCTAssertNil(services.auth)
        XCTAssertNil(services.chat)
        XCTAssertNil(services.reads)
        XCTAssertNil(services.tasks)
        XCTAssertNil(services.cloud)
        XCTAssertNil(services.settings)
        XCTAssertNil(services.devices)
        XCTAssertNil(services.rewindCapture)
        XCTAssertNil(services.transport)
    }

    /// The completed-onboarding marker + a session the user can use right
    /// now must open the ready shell (the gate regression: `authState` used
    /// to stay `.signedOut` forever).
    func testSessionGateOpensReadyShellForCompletedOnboarding() async {
        let settings = GateTestSettingsStore(onboardingSetupCompleted: true)
        let store = AppStore(
            services: AppServices(
                auth: GateTestAuthSession(), settings: settings))
        await store.loadPreferencesTask()
        await store.probeOnboarding()
        XCTAssertEqual(store.authState, .signedIn)
        XCTAssertFalse(store.returningUser)
        XCTAssertFalse(store.onboardingRequired ?? true)
        // The marker lives on its own key; explore progress stays pure CSV.
        XCTAssertTrue(store.preferences.exploreProgress.isEmpty)
    }

    /// A completed onboarding with no usable session is a returning user:
    /// the Welcome-back gate, never a faked ready shell.
    func testSessionGateShowsReturningUserWithoutSession() async {
        let settings = GateTestSettingsStore(onboardingSetupCompleted: true)
        let store = AppStore(
            services: AppServices(
                auth: GateTestAuthSession(hasSession: false), settings: settings))
        await store.loadPreferencesTask()
        await store.probeOnboarding()
        XCTAssertEqual(store.authState, .signedOut)
        XCTAssertTrue(store.returningUser)
    }

    /// The Rewind reader loads frames through the bridge and collapses them
    /// with the 12-minute grouping (`DesktopRewind.tsx` reader effect).
    func testRefreshRewindTimelineGroupsFrames() async {
        let bridge = RewindTimelineBridge { source, _, cursor, _ in
            // Cursor-respecting page like the real bridges: stamps < cursor.
            // The captured store owns this fixture; shipping history is empty
            // (the reader interleaves both sources).
            guard source == .captured else {
                return RewindFramePage(frames: [], nextCursor: nil)
            }
            let all = [
                RewindFrame(id: "3", capturedAtMs: 3_000, appName: "Xcode", windowTitle: "a"),
                RewindFrame(id: "2", capturedAtMs: 2_000, appName: "Xcode", windowTitle: "a"),
                RewindFrame(id: "1", capturedAtMs: 1_000, appName: "Safari", windowTitle: "b"),
            ]
            let remaining = cursor.flatMap { stamp in
                all.filter { $0.capturedAtMs < (Int64(stamp) ?? .max) }
            } ?? all
            return RewindFramePage(frames: remaining, nextCursor: nil)
        }
        let store = AppStore(services: AppServices(rewindTimeline: bridge))
        await store.refreshRewindTimeline(query: "")
        XCTAssertEqual(store.rewindGroups.map { $0.id }, ["3", "1"])
        XCTAssertEqual(store.rewindGroups.first?.count, 2)
        XCTAssertFalse(store.rewindTimelineHasMore)
        XCTAssertNil(store.rewindTimelineWarning)
        XCTAssertFalse(store.rewindTimelineBusy)
    }

    /// A missing history source is normal: the list clears with no warning
    /// (upstream `OMI_REWIND_UNAVAILABLE`).
    func testRewindTimelineUnavailableClearsQuietly() async {
        let bridge = RewindTimelineBridge { _, _, _, _ in
            throw RewindTimelineFailure.unavailable
        }
        let store = AppStore(services: AppServices(rewindTimeline: bridge))
        await store.refreshRewindTimeline(query: "")
        XCTAssertTrue(store.rewindGroups.isEmpty)
        XCTAssertFalse(store.rewindTimelineHasMore)
        XCTAssertNil(store.rewindTimelineWarning)
    }

    /// No bridge → honestly empty, never a fabricated history.
    func testRewindTimelineWithoutBridgeStaysEmpty() async {
        let store = AppStore(services: AppServices())
        await store.refreshRewindTimeline(query: "")
        XCTAssertTrue(store.rewindGroups.isEmpty)
        XCTAssertFalse(store.rewindTimelineHasMore)
    }
}

/// Optimistic authenticator with an explicit session-probe result.
private final class GateTestAuthSession: SessionProbeCapable, @unchecked Sendable {
    private let handoffs = AsyncStream<DesktopHandoff>.makeStream()
    private let invalidations = AsyncStream<Void>.makeStream()
    private let hasSession: Bool

    init(hasSession: Bool = true) {
        self.hasSession = hasSession
    }

    var desktopHandoffs: AsyncStream<DesktopHandoff> { handoffs.stream }
    var sessionInvalidated: AsyncStream<Void> { invalidations.stream }

    func signIn() async throws -> Bool { hasSession }
    func cancelSignIn() async {}
    func signOut() async throws -> Bool { true }
    func hasCloudSession() async -> Bool { hasSession }
}

/// In-memory `SettingsStoring` carrying one explore-progress value.
private final class GateTestSettingsStore: SettingsStoring {
    private let onboardingSetupCompleted: Bool
    private let exploreProgress: String

    init(onboardingSetupCompleted: Bool, exploreProgress: String = "") {
        self.onboardingSetupCompleted = onboardingSetupCompleted
        self.exploreProgress = exploreProgress
    }

    func loadPreferences() async -> DesktopPreferences {
        var preferences = DesktopPreferences()
        preferences.onboardingSetupCompleted = onboardingSetupCompleted
        preferences.exploreProgress = exploreProgress
        return preferences
    }

    func setPreference(
        _ key: String, _ value: PreferenceValue
    ) async -> DesktopPreferences {
        await loadPreferences()
    }

    func permissionStatus() async -> [PermissionKind: PermissionState] { [:] }
    func requestPermission(_ kind: PermissionKind) async -> PermissionState { .unknown }
}
