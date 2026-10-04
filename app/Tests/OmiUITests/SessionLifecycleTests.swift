import Foundation
import OmiKit
import XCTest

@testable import OmiUI

@MainActor
final class SessionLifecycleTests: XCTestCase {
    func testInterruptedSignInIgnoresLateSuccessAfterCancel() async {
        let auth = LifecycleAuth()
        let store = AppStore(services: AppServices(auth: auth, settings: LifecycleSettings()))
        await store.loadPreferencesTask()

        let signIn = Task { @MainActor in await store.startSignIn() }
        await auth.waitUntilSignInStarts()
        XCTAssertTrue(store.signingIn)

        await store.cancelSignIn()
        XCTAssertFalse(store.signingIn)
        XCTAssertNil(store.authErrorCopy)

        await auth.finishSignIn(.success(true))
        await signIn.value

        XCTAssertFalse(store.signingIn)
        XCTAssertNil(store.authErrorCopy)
        XCTAssertNotEqual(store.authState, .signedIn)
        let cancelCount = await auth.cancelCount()
        XCTAssertEqual(cancelCount, 1)
    }

    func testSignInTransportFailureShowsRetryableCopyAndAllowsRetry() async {
        let auth = LifecycleAuth()
        let store = AppStore(services: AppServices(auth: auth, settings: LifecycleSettings()))
        await store.loadPreferencesTask()

        let first = Task { @MainActor in await store.startSignIn() }
        await auth.waitUntilSignInStarts()
        await auth.finishSignIn(.failure(AuthError.transport))
        await first.value
        XCTAssertEqual(store.authErrorCopy, "Could not reach Omi to finish sign in.")
        XCTAssertFalse(store.signingIn)

        let second = Task { @MainActor in await store.startSignIn() }
        await auth.waitUntilSignInStarts(count: 2)
        XCTAssertNil(store.authErrorCopy)
        await auth.finishSignIn(.success(true), index: 1)
        await second.value
        XCTAssertNil(store.authErrorCopy)
        XCTAssertFalse(store.signingIn)
    }

    func testSupersededSignInCannotClobberNewerAttempt() async {
        let auth = LifecycleAuth()
        let store = AppStore(services: AppServices(auth: auth, settings: LifecycleSettings()))
        await store.loadPreferencesTask()

        let stale = Task { @MainActor in await store.startSignIn() }
        await auth.waitUntilSignInStarts()
        let fresh = Task { @MainActor in await store.startSignIn() }
        await auth.waitUntilSignInStarts(count: 2)

        await auth.finishSignIn(.failure(AuthError.expired), index: 0)
        await stale.value
        XCTAssertTrue(store.signingIn)
        XCTAssertNil(store.authErrorCopy)

        await auth.finishSignIn(.success(true), index: 1)
        await fresh.value
        XCTAssertFalse(store.signingIn)
    }

    func testSignOutDuringChatRequestRetiresTranscriptAndIgnoresLateResult() async throws {
        let chat = LifecycleChat()
        let store = try await readyStore(chat: chat)

        let send = Task { @MainActor in await store.sendChat("private question") }
        await chat.waitUntilSendStarts()
        XCTAssertTrue(store.chatBusy)
        XCTAssertEqual(store.chatMessages.count, 2)

        await store.signOut()
        XCTAssertTrue(store.returningUser)
        XCTAssertTrue(store.chatMessages.isEmpty)
        XCTAssertFalse(store.chatBusy)

        await chat.finishSend(.success(chat.canonicalResult(text: "late answer")))
        await send.value

        XCTAssertTrue(store.chatMessages.isEmpty)
        XCTAssertFalse(store.chatBusy)
        XCTAssertNil(store.chatErrorCopy)
        XCTAssertTrue(store.returningUser)
    }

    func testStoppedGenerationMarksPendingRowCancelledWithoutSigningOut() async throws {
        let chat = LifecycleChat()
        let store = try await readyStore(chat: chat)

        let send = Task { @MainActor in await store.sendChat("long question") }
        await chat.waitUntilSendStarts()
        await store.cancelChatGeneration()
        await chat.finishSend(.failure(TransportFailure.cancelled))
        await send.value

        XCTAssertEqual(
            store.chatErrorCopy,
            "Response stopped locally. It may still complete on the server.")
        XCTAssertEqual(store.chatMessages.last?.generationOutcome, .cancelled)
        XCTAssertFalse(store.chatBusy)
        XCTAssertFalse(store.returningUser)
        XCTAssertEqual(store.authState, .signedIn)
    }

    func testNetworkDropMidStreamKeepsSessionAndAllowsResend() async throws {
        let chat = LifecycleChat()
        let store = try await readyStore(chat: chat)

        let first = Task { @MainActor in await store.sendChat("first") }
        await chat.waitUntilSendStarts()
        await chat.finishSend(.failure(TransportFailure.transportFailed))
        await first.value

        XCTAssertEqual(
            store.chatErrorCopy, "Response interrupted. It may still complete.")
        XCTAssertFalse(store.returningUser)
        XCTAssertEqual(store.authState, .signedIn)
        XCTAssertFalse(store.chatBusy)
        guard store.sessionReady else { return XCTFail("transport failure retired the session") }

        let second = Task { @MainActor in await store.sendChat("second") }
        await chat.waitUntilSendStarts(count: 2)
        await chat.finishSend(.success(chat.canonicalResult(text: "answer")), index: 1)
        await second.value
        XCTAssertEqual(store.chatMessages.last?.text, "answer")
        XCTAssertNil(store.chatErrorCopy)
    }

    func testUnauthorizedChatRequestRevalidatesSession() async throws {
        let chat = LifecycleChat()
        let store = try await readyStore(chat: chat)

        let send = Task { @MainActor in await store.sendChat("question") }
        await chat.waitUntilSendStarts()
        await chat.finishSend(.failure(TransportFailure.unauthorized))
        await send.value

        XCTAssertTrue(store.returningUser)
        XCTAssertTrue(store.chatMessages.isEmpty)
    }

    func testStopRetiresBackgroundLoopsAndLateChatResultStillSettlesOnce() async throws {
        let chat = LifecycleChat()
        let store = try await readyStore(chat: chat)

        let send = Task { @MainActor in await store.sendChat("question") }
        await chat.waitUntilSendStarts()

        store.stop()
        XCTAssertTrue(store.runtime.streamTasks.isEmpty)
        XCTAssertFalse(store.runtime.started)

        await chat.finishSend(.success(chat.canonicalResult(text: "answer")))
        await send.value
        XCTAssertEqual(store.chatMessages.filter { $0.sender == .ai }.count, 1)
        XCTAssertEqual(store.chatMessages.last?.text, "answer")
        XCTAssertFalse(store.chatBusy)

        store.start()
        XCTAssertTrue(store.runtime.started)
        store.stop()
    }

    private func readyStore(chat: LifecycleChat) async throws -> AppStore {
        let store = AppStore(
            services: AppServices(
                auth: LifecycleAuth(), chat: chat,
                settings: LifecycleSettings(onboardingSetupCompleted: true)))
        await store.loadPreferencesTask()
        await store.probeOnboarding()
        XCTAssertTrue(store.sessionReady)
        return store
    }
}

private actor LifecycleChatState {
    var starts = 0
    var continuations: [CheckedContinuation<ChatSendResult, Error>] = []
    var startWaiters: [(Int, CheckedContinuation<Void, Never>)] = []

    func begin(_ continuation: CheckedContinuation<ChatSendResult, Error>) {
        continuations.append(continuation)
        starts += 1
        let ready = startWaiters.filter { $0.0 <= starts }
        startWaiters.removeAll { $0.0 <= starts }
        for waiter in ready { waiter.1.resume() }
    }

    func waitForStart(count: Int) async {
        if starts >= count { return }
        await withCheckedContinuation { startWaiters.append((count, $0)) }
    }

    func finish(_ result: Result<ChatSendResult, Error>, index: Int) {
        continuations[index].resume(with: result)
    }
}

private final class LifecycleChat: ChatServicing, @unchecked Sendable {
    private let state = LifecycleChatState()

    func waitUntilSendStarts(count: Int = 1) async { await state.waitForStart(count: count) }
    func finishSend(_ result: Result<ChatSendResult, Error>, index: Int = 0) async {
        await state.finish(result, index: index)
    }

    func canonicalResult(text: String) -> ChatSendResult {
        (
            ChatMessage(id: "human-canonical", text: "q", sender: .human, createdAt: 1),
            ChatMessage(
                id: "ai-canonical", text: text, sender: .ai, createdAt: 2,
                generationOutcome: .completed)
        )
    }

    func loadNewestChatHistory() async throws -> ChatHistoryPage {
        ChatHistoryPage(messages: [], olderCursor: nil, hasOlder: false)
    }

    func loadOlderChatHistory(olderCursor: String) async throws -> ChatHistoryPage {
        ChatHistoryPage(messages: [], olderCursor: nil, hasOlder: false)
    }

    func sendChatMessage(
        _ text: String, now: Int64,
        onGenerationStarted: (@Sendable (String) -> Void)?,
        localMessage: ChatMessage?,
        onRequestStarted: (@Sendable (String) -> Bool)?,
        onAssistantText: (@Sendable (String) -> Void)?
    ) async throws -> ChatSendResult {
        onGenerationStarted?("generation-1")
        return try await withCheckedThrowingContinuation { continuation in
            Task { await state.begin(continuation) }
        }
    }

    func cancelChatGeneration(_ generationId: String) async throws {}
}

private actor LifecycleAuthState {
    var starts = 0
    var cancels = 0
    var continuations: [CheckedContinuation<Bool, Error>] = []
    var waiters: [(Int, CheckedContinuation<Void, Never>)] = []

    func begin(_ continuation: CheckedContinuation<Bool, Error>) {
        continuations.append(continuation)
        starts += 1
        let ready = waiters.filter { $0.0 <= starts }
        waiters.removeAll { $0.0 <= starts }
        for waiter in ready { waiter.1.resume() }
    }

    func wait(count: Int) async {
        if starts >= count { return }
        await withCheckedContinuation { waiters.append((count, $0)) }
    }

    func finish(_ result: Result<Bool, Error>, index: Int) {
        continuations[index].resume(with: result)
    }

    func cancel() { cancels += 1 }
}

private final class LifecycleAuth: SessionProbeCapable, @unchecked Sendable {
    private let handoffs = AsyncStream<DesktopHandoff>.makeStream()
    private let invalidations = AsyncStream<Void>.makeStream()
    private let state = LifecycleAuthState()

    var desktopHandoffs: AsyncStream<DesktopHandoff> { handoffs.stream }
    var sessionInvalidated: AsyncStream<Void> { invalidations.stream }

    func waitUntilSignInStarts(count: Int = 1) async { await state.wait(count: count) }
    func finishSignIn(_ result: Result<Bool, Error>, index: Int = 0) async {
        await state.finish(result, index: index)
    }
    func cancelCount() async -> Int { await state.cancels }

    func signIn() async throws -> Bool {
        try await withCheckedThrowingContinuation { continuation in
            Task { await state.begin(continuation) }
        }
    }

    func cancelSignIn() async { await state.cancel() }
    func signOut() async throws -> Bool { true }
    func hasCloudSession() async -> Bool { true }
}

private final class LifecycleSettings: SettingsStoring {
    private let onboardingSetupCompleted: Bool

    init(onboardingSetupCompleted: Bool = false) {
        self.onboardingSetupCompleted = onboardingSetupCompleted
    }

    func loadPreferences() async -> DesktopPreferences {
        var preferences = DesktopPreferences()
        preferences.onboardingSetupCompleted = onboardingSetupCompleted
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
