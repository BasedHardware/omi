import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// Airgap Mode has to stop the app reaching the network — all of it, not just favicons.
///
/// The switch shipped meaning exactly one thing (`ExclusionEngine.faviconFetch`) while the app went
/// on POSTing the OCR'd contents of the user's screen to a remote endpoint every sixty seconds. The
/// central test here is `testAirgapModeStopsTheScreenActivityUploadBeforeAnythingIsSent`, and the
/// transport it installs is a tripwire: if a frame ever reaches it under Airgap Mode, the test fails
/// rather than the network succeeding.
final class AirgapEgressTests: XCTestCase {

    // MARK: - The screen-activity upload path

    /// **The regression test.** With Airgap Mode on, a drain must send nothing at all.
    ///
    /// It fails against the code as it shipped for two separate reasons, and both matter:
    ///
    /// 1. It does not compile. `ScreenActivityUploader` had a `private init()`, a `private func
    ///    drain()` returning `Void`, and no notion of Airgap Mode anywhere — there was no seam to
    ///    ask the question through, which is precisely why nobody noticed the answer was wrong.
    /// 2. Given the seam but not the guard, it fails at runtime: the drain walks on to
    ///    `loadPending()` and `send(_:)`, hands a batch of frames to `transport`, and trips the
    ///    `XCTFail` below.
    @MainActor
    func testAirgapModeStopsTheScreenActivityUploadBeforeAnythingIsSent() async throws {
        let store = try TemporaryStore()
        try store.seedFrame(ocrText: "a line of text that was on the user's screen")
        // Captured as the store itself rather than through the fixture, so the closure holds only a
        // `ContextStore` — which is `Sendable` — and not the test-local box around it.
        let contextStore = store.store

        let uploader = ScreenActivityUploader(
            isAirgapped: { true },
            isSignedIn: { true },
            openStore: { contextStore },
            authHeaders: { _ in ["Authorization": "Bearer test"] },
            transport: { request in
                XCTFail("Airgap Mode must not let screen content reach \(request.url?.host() ?? "the network")")
                throw CancellationError()
            },
            defaults: store.defaults)

        let outcome = await uploader.drain()

        XCTAssertEqual(outcome, .suppressedByAirgap)
        XCTAssertNil(
            uploader.lastSyncedAt,
            "a suppressed drain must never stamp a sync time — that is the failure that looks like success")
        XCTAssertEqual(
            store.defaults.integer(forKey: Self.cursorKey), 0,
            "the cursor must not move, so the whole backlog is still owed once Airgap Mode goes off")
    }

    /// The control for the test above: the *same* uploader with the *same* seeded frame does reach
    /// the transport when Airgap Mode is off.
    ///
    /// Without this, a guard that accidentally suppressed everything — a broken store, a typo in the
    /// query — would pass the airgap test while proving nothing about Airgap Mode.
    @MainActor
    func testTheSameDrainDoesSendWhenAirgapModeIsOff() async throws {
        let store = try TemporaryStore()
        let frameId = try store.seedFrame(ocrText: "a line of text that was on the user's screen")
        let contextStore = store.store

        let sent = Recorder()
        let uploader = ScreenActivityUploader(
            isAirgapped: { false },
            isSignedIn: { true },
            openStore: { contextStore },
            authHeaders: { _ in ["Authorization": "Bearer test"] },
            transport: { request in
                sent.record(request)
                return (Self.syncResponseBody(lastId: frameId), Self.ok(for: request))
            },
            defaults: store.defaults)

        let outcome = await uploader.drain()

        XCTAssertEqual(outcome, .caughtUp)
        XCTAssertEqual(sent.requests.count, 1, "one batch, one request")
        XCTAssertEqual(sent.requests.first?.httpMethod, "POST")
        XCTAssertEqual(
            store.defaults.integer(forKey: Self.cursorKey), Int(frameId),
            "an accepted batch advances the cursor")
    }

    /// Airgap Mode is checked ahead of sign-in, so a suppression is reported as a suppression rather
    /// than mislabelled as "signed out". The reason is what the UI shows and what a support log
    /// records, and a switch the user can undo must not be reported as an account problem.
    @MainActor
    func testAirgapModeIsReportedAheadOfSignedOut() async throws {
        let store = try TemporaryStore()
        let contextStore = store.store

        func drain(airgapped: Bool, signedIn: Bool) async -> ScreenActivityUploader.DrainOutcome {
            let uploader = ScreenActivityUploader(
                isAirgapped: { airgapped },
                isSignedIn: { signedIn },
                openStore: { contextStore },
                authHeaders: { _ in [:] },
                transport: { _ in
                    XCTFail("nothing may be sent while signed out or airgapped")
                    throw CancellationError()
                },
                defaults: store.defaults)
            return await uploader.drain()
        }

        let bothOff = await drain(airgapped: false, signedIn: false)
        XCTAssertEqual(bothOff, .signedOut)

        let airgappedAndSignedOut = await drain(airgapped: true, signedIn: false)
        XCTAssertEqual(airgappedAndSignedOut, .suppressedByAirgap)

        let airgappedAndSignedIn = await drain(airgapped: true, signedIn: true)
        XCTAssertEqual(airgappedAndSignedIn, .suppressedByAirgap)
    }

    // MARK: - The exclusion observer

    /// `ExclusionEngine.mutate` calls **every** observer on **every** change, so ticking any checkbox
    /// in Settings › Exclusions reaches the screen-sync observer too. Exactly one state may resume
    /// the loop, and "the loop is not running" is not that state.
    ///
    /// The bug this pins: after a trial expiry the loop nils itself while `wantsPeriodicSync` stays
    /// true, and the observer's resume branch keyed on `loop == nil` alone. Excluding an app then
    /// logged "Airgap Mode off — resuming screen sync" about a switch that had never been on, cleared
    /// `isTrialExpired`, and spent another authenticated round trip re-learning the trial was over.
    /// `ListenSocket.observeAirgap` never had it, because its resume branch asks `state == .airgapped`.
    @MainActor
    func testOnlyAnAirgapSuspensionResumesTheSyncLoopAndAnExclusionTickDoesNot() async throws {
        let store = try TemporaryStore()
        try store.seedFrame(ocrText: "a line of text that was on the user's screen")
        let contextStore = store.store
        let sent = Recorder()
        // The uploader's own egress question, injected as it is in every test above. The engine below
        // is a separate thing: it is only what the observer is registered on, and it is left airgapped
        // for the whole test so the live observer stays inert (`loop == nil` answers `.ignore` to it)
        // and the assertions below are about `airgapTransition` and nothing else.
        let airgapped = Toggle(true)
        XCTAssertEqual(store.exclusions.setAirgapMode(true), .applied)

        let uploader = ScreenActivityUploader(
            isAirgapped: { airgapped.value },
            isSignedIn: { true },
            openStore: { contextStore },
            authHeaders: { _ in ["Authorization": "Bearer test"] },
            transport: { request in
                sent.record(request)
                return (Data(), Self.paywalled(for: request))
            },
            defaults: store.defaults,
            exclusions: store.exclusions)

        // 1. Airgap Mode on at launch. No loop is started, and the switch is *why* — so turning it
        //    off is exactly what has to bring the loop back.
        uploader.start()
        XCTAssertEqual(sent.requests.count, 0, "nothing may be sent while the switch is on")
        XCTAssertEqual(
            uploader.airgapTransition(airgapMode: false), .resume,
            "an airgap suspension is the one stop that an airgap change may undo")

        // 2. Airgap Mode off, and the account's desktop trial has expired. One request learns that,
        //    the drain halts, and nothing is running — the state the observer used to misread.
        airgapped.value = false
        let outcome = await uploader.drain()
        guard case .halted = outcome else {
            return XCTFail("a 402 has to halt the drain, got \(outcome)")
        }
        XCTAssertEqual(sent.requests.count, 1)

        // 3. The user now excludes an app. Same observer, same stopped loop, different reason.
        XCTAssertEqual(
            uploader.airgapTransition(airgapMode: false), .ignore,
            "a checkbox in Exclusions must not restart a loop the paywall deliberately stopped")
        XCTAssertEqual(sent.requests.count, 1, "and must not spend a second authenticated round trip")

        // 4. Turning Airgap Mode *on* now must not relabel the paywall's stop as an airgap one —
        //    otherwise the same restart would happen one step later, on the way back off.
        XCTAssertEqual(
            uploader.airgapTransition(airgapMode: true), .ignore,
            "there is no running loop to suspend, so nothing is suspended by the switch")
        XCTAssertEqual(uploader.airgapTransition(airgapMode: false), .ignore)

        // 5. And a deliberate stop stays stopped, whatever the switch does afterwards.
        uploader.stop()
        XCTAssertEqual(uploader.airgapTransition(airgapMode: false), .ignore)
    }

    // MARK: - The speech model

    /// **The regression test for the largest egress this app performs.** Airgap Mode on, no weights
    /// on this Mac: the ~600 MB fetch must not happen.
    ///
    /// It fails against the code as it shipped for the same two reasons the screen-sync test does.
    /// It does not compile — there was no `SpeechModelAccess` and no
    /// `NetworkEgress.Client.speechModelDownload`, which is precisely why nobody noticed this client
    /// was missing from the audited list. And given the seam but not the guard it fails at runtime:
    /// `Transcriber.prepareModels` and `ModelPool` both called `AsrModels.downloadAndLoad`
    /// unconditionally, so the `fetch` tripwire below trips.
    ///
    /// `exclusions.json` survives an app reinstall, so this is not hypothetical: a user who had
    /// turned the switch on and then reinstalled watched 600 MB go to a third-party host on first run
    /// with no suppression, no record, and nothing on screen tying it to a setting they had set.
    func testAirgapModeRefusesTheSpeechModelDownloadRatherThanPullingSixHundredMegabytes() async {
        do {
            // The stand-in model is a `String`, and the type is written out rather than inferred:
            // both closures below are multi-statement tripwires, so there is nothing else to pin it.
            let unexpected: String = try await SpeechModelAccess.obtain(
                airgapMode: true,
                isOnDisk: { false },
                loadFromDisk: {
                    XCTFail("there is nothing on disk to load")
                    return "unreachable"
                },
                fetch: {
                    XCTFail("Airgap Mode must not fetch ~600 MB of model weights from a third party")
                    return "unreachable"
                })
            XCTFail("a refusal has to be thrown, not returned as a model that half exists: \(unexpected)")
        } catch {
            // The throw is what the user reads: `Engine.startAudio` renders it as the paused reason
            // against that capture source. Silence here would look exactly like a quiet room.
            XCTAssertEqual(
                error.localizedDescription, NetworkEgress.explanation(.speechModelDownload))
        }
    }

    /// The other half of the promise, and the more important one: **Airgap Mode must not break
    /// offline transcription.** Weights already on this Mac load exactly as they would with the
    /// switch off, because loading a local file is not egress and on-device transcription is the
    /// thing the switch exists to protect.
    func testAModelAlreadyOnThisMacStillLoadsUnderAirgapMode() async throws {
        let model: String = try await SpeechModelAccess.obtain(
            airgapMode: true,
            isOnDisk: { true },
            loadFromDisk: { "the weights that were already here" },
            fetch: {
                XCTFail("nothing needs fetching when the model is on disk")
                return "unreachable"
            })
        XCTAssertEqual(model, "the weights that were already here")
    }

    /// The control: the same missing model is fetched normally when the switch is off. Without this,
    /// a guard that refused unconditionally would pass the test above and prove nothing.
    func testTheModelIsFetchedNormallyWhenAirgapModeIsOff() async throws {
        let model: String = try await SpeechModelAccess.obtain(
            airgapMode: false,
            isOnDisk: { false },
            loadFromDisk: {
                XCTFail("there is nothing on disk to load")
                return "unreachable"
            },
            fetch: { "freshly downloaded weights" })
        XCTAssertEqual(model, "freshly downloaded weights")
    }

    /// All four combinations, so the ordering of the two questions is pinned: what is on disk is read
    /// first, because Airgap Mode governs the *fetch* and has nothing to say about a local file.
    func testTheModelDecisionAsksWhatIsOnDiskBeforeItAsksAboutTheSwitch() {
        XCTAssertEqual(SpeechModelAccess.decide(airgapMode: false, isOnDisk: false), .fetch)
        XCTAssertEqual(SpeechModelAccess.decide(airgapMode: false, isOnDisk: true), .loadWhatIsAlreadyHere)
        XCTAssertEqual(SpeechModelAccess.decide(airgapMode: true, isOnDisk: true), .loadWhatIsAlreadyHere)
        XCTAssertEqual(SpeechModelAccess.decide(airgapMode: true, isOnDisk: false), .refuse)
    }

    // MARK: - The gate itself

    /// Every remote client in the app is suppressed, with no exception for any of them.
    ///
    /// Written over `Client.allCases` rather than as a list, so a client added later is covered by
    /// this test the moment it names itself — which is the only way the enumeration stays honest.
    func testAirgapModeSuppressesEveryRemoteClientIncludingSignIn() {
        for client in NetworkEgress.Client.allCases {
            XCTAssertTrue(
                NetworkEgress.isSuppressed(client, airgapMode: true),
                "\(client.rawValue) must not reach the network under Airgap Mode")
            XCTAssertFalse(
                NetworkEgress.isSuppressed(client, airgapMode: false),
                "\(client.rawValue) must be unaffected when Airgap Mode is off")
        }

        XCTAssertTrue(
            NetworkEgress.isSuppressed(.signIn, airgapMode: true),
            "sign-in is the interesting case and is deliberately not excepted")
    }

    /// A refusal a person cannot connect to a switch they flipped is indistinguishable from the app
    /// being broken, so every explanation names the setting and where to change it.
    func testEverySuppressionExplanationNamesTheSettingAndWhereToFindIt() {
        for client in NetworkEgress.Client.allCases {
            let sentence = NetworkEgress.explanation(client)
            XCTAssertTrue(
                sentence.contains("Airgap Mode"), "\(client.rawValue) must name the setting: \(sentence)")
        }
        XCTAssertTrue(
            NetworkEgress.explanation(.signIn).contains("Settings"),
            "a blocked sign-in has to say where to turn Airgap Mode off")
    }

    /// The live reader is the exclusion engine's flag, and the engine forces it on when the
    /// exclusion configuration fails closed. A configuration we cannot parse may carry exclusions we
    /// cannot express, and uploading a frame we might have been told to withhold is unrecoverable.
    func testAnUnreadableExclusionConfigurationAlsoStopsEgress() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("airgap-egress-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        let configuration = root.appendingPathComponent("exclusions.json")
        try Data("this is not the configuration you are looking for".utf8).write(to: configuration)

        let engine = ExclusionEngine(
            configurationURL: configuration,
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))

        XCTAssertTrue(engine.current.health.isFailClosed)
        XCTAssertTrue(
            NetworkEgress.isSuppressed(.screenActivitySync, airgapMode: engine.current.airgapMode),
            "a configuration that cannot be trusted must stop uploads as well as captures")
    }

    /// Every client that refuses must also *say* it refused.
    ///
    /// The two halves come apart easily and did: `MCPKeyProvisioner.retire` guarded correctly and
    /// recorded nothing, so it was the one suppression in the app invisible to telemetry — and the
    /// answer to "what did Airgap Mode actually stop?" was wrong by exactly one client, in the
    /// direction that hides one rather than inventing one. This pins the record's shape for every
    /// client at once: the area it lands in, and the slug it is attributed by.
    func testEverySuppressionIsRecordedUnderItsOwnClient() {
        let recorder = AirgapSuppressionRecorder()
        defer { recorder.stop() }

        for client in NetworkEgress.Client.allCases {
            NetworkEgress.recordSuppression(client, outcome: .degraded)
        }

        XCTAssertEqual(
            recorder.records.map { $0.client }, NetworkEgress.Client.allCases,
            "a refusal has to be attributable, so each client reports under its own name")
    }

    // MARK: - The sibling process

    /// `context-for-claude-mcp` is a different process with its own `URLSession`, and for a while it
    /// was outside this list entirely — so `Client.allCases`, the thing every test above iterates to
    /// prove coverage, reported a complete audit of an app whose largest per-request disclosure
    /// (the user's own recall queries) it could not see.
    ///
    /// `ContextApp` cannot link `ContextMCPKit`, so the two halves are tied by a shared slug rather
    /// than by a shared symbol. This is the app's half; `AirgapTests.testTheMCPClientAnswersToTheName…`
    /// is the other, and both name the same string on purpose — if one moves, the pair stops agreeing.
    func testTheMCPProcessIsInTheAuditedListUnderTheNameItReportsItselfBy() {
        XCTAssertEqual(NetworkEgress.Client.mcpOmiBackend.rawValue, "omi-backend")
        XCTAssertEqual(
            NetworkEgress.Client.mcpOmiBackend.area, .mcp,
            "the sibling's suppressions have to land beside the app's other MCP degradations")
        XCTAssertTrue(NetworkEgress.explanation(.mcpOmiBackend).contains("Airgap Mode"))
    }

    // MARK: - Sign-in

    /// **The regression test for a switch flipped mid-round-trip.** Sign-in was guarded once, at the
    /// press, and then waited on a browser — so every request after that wait ran on an answer taken
    /// minutes earlier.
    ///
    /// `waitForCode()` is unbounded by construction: what it waits for is a person. Turning Airgap
    /// Mode on *while the browser tab is open* — the exact moment someone reaches for it — used to
    /// still ship the authorization code to `api.omi.me` and a custom token to Google, because
    /// neither request asked again. The transport below is a tripwire: reaching it is the failure.
    @MainActor
    func testAirgapModeTurnedOnDuringSignInStopsTheRequestsThatFollowTheBrowser() async {
        let recorder = AirgapSuppressionRecorder()
        defer { recorder.stop() }

        do {
            _ = try await OmiAuth.post(
                url: URL(string: "https://api.omi.me/v1/auth/token")!,
                contentType: "application/x-www-form-urlencoded",
                body: Data("grant_type=authorization_code".utf8),
                client: .signIn,
                isSuppressed: { _ in true },
                transport: { request in
                    XCTFail("Airgap Mode must not let a sign-in reach \(request.url?.host() ?? "the network")")
                    throw CancellationError()
                })
            XCTFail("a suppressed request has to throw rather than return a half-finished sign-in")
        } catch let error as OmiAuthError {
            guard case .airgapMode = error else {
                return XCTFail("a suppression must not be reported as an account or transport failure: \(error)")
            }
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertEqual(recorder.records.count, 1)
        XCTAssertEqual(recorder.records.first?.client, .signIn)
        XCTAssertEqual(
            recorder.records.first?.outcome, .bypassed,
            "the whole attempt is abandoned and the user is told, so it is bypassed rather than degraded")
    }

    /// The control: the same function, the same request, with the switch off — it reaches the
    /// transport and answers. Without this, a guard that refused unconditionally would pass the test
    /// above and leave nobody able to sign in.
    @MainActor
    func testTheSameSignInRequestIsSentNormallyWhenAirgapModeIsOff() async throws {
        let recorder = AirgapSuppressionRecorder()
        defer { recorder.stop() }
        let sent = Recorder()

        let (data, response) = try await OmiAuth.post(
            url: URL(string: "https://api.omi.me/v1/auth/token")!,
            contentType: "application/x-www-form-urlencoded",
            body: Data("grant_type=authorization_code".utf8),
            client: .signIn,
            isSuppressed: { _ in false },
            transport: { request in
                sent.record(request)
                return (Data("{}".utf8), Self.ok(for: request))
            })

        XCTAssertEqual(sent.requests.count, 1)
        XCTAssertEqual(sent.requests.first?.httpMethod, "POST")
        XCTAssertEqual(response.statusCode, 200)
        XCTAssertEqual(data, Data("{}".utf8))
        XCTAssertTrue(recorder.records.isEmpty, "nothing was suppressed, so nothing is reported")
    }

    /// A refresh is the other request on this path, and it answers to a different client and a
    /// different outcome: the stored session is left completely untouched, so the account resumes
    /// with no browser round trip the moment the switch goes off. Reporting that as `bypassed` would
    /// read as an abandoned sign-in in the telemetry.
    @MainActor
    func testASuppressedTokenRefreshIsReportedAsDegradedRatherThanAsAnAbandonedSignIn() async {
        let recorder = AirgapSuppressionRecorder()
        defer { recorder.stop() }

        do {
            _ = try await OmiAuth.post(
                url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
                contentType: "application/x-www-form-urlencoded",
                body: Data("grant_type=refresh_token".utf8),
                client: .tokenRefresh,
                isSuppressed: { _ in true },
                transport: { _ in
                    XCTFail("Airgap Mode must not let a refresh token leave this Mac")
                    throw CancellationError()
                })
            XCTFail("a suppressed refresh has to throw")
        } catch {}

        XCTAssertEqual(recorder.records.first?.client, .tokenRefresh)
        XCTAssertEqual(recorder.records.first?.outcome, .degraded)
    }

    // MARK: - The superseded MCP key

    /// Retiring a key this Mac can no longer read is a `DELETE` to `api.omi.me` built by hand, so it
    /// does not inherit `OmiAPI`'s guard and carries its own. It refused correctly and **reported
    /// nothing**, which made it the only suppression in the app that never reached telemetry.
    ///
    /// The outcome is returned rather than inferred because the alternative is issuing the request
    /// to find out, against a live account behind a rate limit.
    @MainActor
    func testASupersededKeyIsNotRevokedUnderAirgapModeAndTheRefusalIsReported() async {
        let recorder = AirgapSuppressionRecorder()
        defer { recorder.stop() }

        let outcome = await MCPKeyProvisioner.retire("a-key-id", isSuppressed: { true })

        XCTAssertEqual(outcome, .suppressedByAirgap)
        XCTAssertEqual(recorder.records.count, 1, "the one suppression that used to report nothing")
        XCTAssertEqual(recorder.records.first?.client, .mcpKeyProvisioning)
        XCTAssertEqual(recorder.records.first?.outcome, .degraded)
    }

    /// The control, and it has to be one that still sends nothing: an unusable id refuses *after*
    /// the airgap gate with the switch off. That proves the assertion above is about Airgap Mode
    /// rather than about a function that returns early for everything — without spending a request
    /// on the user's account to show it.
    @MainActor
    func testARefusalWithTheSwitchOffIsNotReportedAsAnAirgapSuppression() async {
        let recorder = AirgapSuppressionRecorder()
        defer { recorder.stop() }

        let outcome = await MCPKeyProvisioner.retire("", isSuppressed: { false })

        XCTAssertEqual(outcome, .unusableId)
        XCTAssertTrue(recorder.records.isEmpty, "nothing was suppressed by the switch, so nothing is reported")
    }

    /// Blocking sign-in is only defensible because the user is told. `OmiAuthError.airgapMode` is
    /// what both sign-in surfaces render — the menu bar through `OmiAuth.lastSignInError`, onboarding
    /// through its own `catch` — so its sentence is the whole of that promise.
    func testABlockedSignInExplainsItselfRatherThanFailingSilently() {
        let message = OmiAuthError.airgapMode.errorDescription
        XCTAssertEqual(message, NetworkEgress.explanation(.signIn))
        XCTAssertNotNil(message)
        XCTAssertFalse(message?.isEmpty ?? true)
    }

    /// A queued upload has to tell "the switch is on" apart from "the network failed": the first
    /// waits, the second retries with backoff, and folding them together would spend a rate-limit
    /// budget proving that a setting is still set.
    func testTheAPIsAirgapErrorIsDistinctFromATransportFailure() {
        XCTAssertNotEqual(
            OmiAPIError.airgapMode.errorDescription,
            OmiAPIError.transport("offline").errorDescription)
        XCTAssertEqual(OmiAPIError.airgapMode.errorDescription, NetworkEgress.explanation(.omiAPI))
    }

    // MARK: - Cloud transcription

    /// Airgap Mode must not cost the user their transcript, only its quality: the local transcriber
    /// keeps ownership of new audio in every cloud state that is not `.live`.
    func testLocalTranscriptionKeepsRunningWhileTheCloudSocketIsAirgapped() {
        XCTAssertTrue(TranscriptOwnership.shouldFeedLocalFallback(when: .airgapped))
    }

    // MARK: - Helpers

    private static let cursorKey = "context.screenSync.lastId"

    private static func ok(for request: URLRequest) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url ?? URL(string: "https://example.invalid")!,
            statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
    }

    /// What the backend answers once the desktop trial is over. A decision about the account, not a
    /// transient failure — which is why the loop stops rather than backing off.
    private static func paywalled(for request: URLRequest) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url ?? URL(string: "https://example.invalid")!,
            statusCode: 402, httpVersion: "HTTP/1.1", headerFields: nil)!
    }

    private static func syncResponseBody(lastId: Int64) -> Data {
        Data("{\"synced\":1,\"last_id\":\(lastId)}".utf8)
    }

    /// A `var` the injected closures and the test body can share. A class, so both see one value.
    private final class Toggle: @unchecked Sendable {
        var value: Bool
        init(_ value: Bool) { self.value = value }
    }

    /// Records what a transport was asked to send. A class so the closure shares one instance rather
    /// than capturing a copy of a struct.
    private final class Recorder: @unchecked Sendable {
        private(set) var requests: [URLRequest] = []
        func record(_ request: URLRequest) { requests.append(request) }
    }

    /// A throwaway database and a throwaway `UserDefaults` suite, so a test never reads the
    /// developer's own captures or moves the real sync cursor.
    private final class TemporaryStore {
        let root: URL
        let store: ContextStore
        let defaults: UserDefaults
        /// A throwaway exclusion engine too, so a test that registers an observer registers it here
        /// and not on the process-wide `ExclusionEngine.shared` — and so flipping Airgap Mode in a
        /// test never touches the developer's own `exclusions.json`.
        let exclusions: ExclusionEngine
        private let suiteName: String

        init() throws {
            root = URL(fileURLWithPath: NSTemporaryDirectory())
                .appendingPathComponent("airgap-store-\(UUID().uuidString)", isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            store = try ContextStore(url: root.appendingPathComponent("context.db"))
            suiteName = "airgap-tests-\(UUID().uuidString)"
            defaults = UserDefaults(suiteName: suiteName) ?? .standard
            exclusions = ExclusionEngine(
                configurationURL: root.appendingPathComponent("exclusions.json"),
                framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
        }

        @discardableResult
        func seedFrame(ocrText: String) throws -> Int64 {
            try store.insertFrame(
                Frame(
                    capturedAt: 1_760_000_000,
                    appName: "Notes",
                    windowTitle: "Untitled",
                    ocrText: ocrText))
        }

        deinit {
            defaults.removePersistentDomain(forName: suiteName)
            try? FileManager.default.removeItem(at: root)
        }
    }
}

/// Watches `NetworkEgress.recordSuppression` for the life of one test.
///
/// "Gated" and "gated *and* reported" are different claims, and only the first shows up in a return
/// value: `ContextTelemetry` writes to `os.Logger`, which nothing can read back. This is what makes
/// the second one checkable, and it exists because a client that refused without reporting
/// (`MCPKeyProvisioner.retire`) went unnoticed for as long as it existed.
///
/// Top-level rather than nested, so `UpdatePolicyTests` can make the same assertions about Sparkle's
/// three steps. It must be stopped before a test ends, or the next test inherits the recorder.
final class AirgapSuppressionRecorder {
    private(set) var records: [(client: NetworkEgress.Client, outcome: ContextFallbackOutcome)] = []

    init() {
        NetworkEgress.observer = { [self] client, outcome in
            records.append((client, outcome))
        }
    }

    func stop() { NetworkEgress.observer = nil }
}
