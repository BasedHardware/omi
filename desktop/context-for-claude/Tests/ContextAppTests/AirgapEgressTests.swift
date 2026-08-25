import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// Airgap Mode has to stop the app reaching the network — all of it, not just favicons.
///
/// The switch shipped meaning exactly one thing (`ExclusionEngine.faviconFetch`) while the app went
/// on POSTing the OCR'd contents of the user's screen to a remote endpoint every sixty seconds.
/// That uploader is retired outright, so its tripwire tests retired with it; every remaining
/// remote client keeps a transport-level tripwire or an all-cases gate assertion here.
final class AirgapEgressTests: XCTestCase {

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
      NetworkEgress.isSuppressed(.conversationUpload, airgapMode: engine.current.airgapMode),
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

  /// Records what a transport was asked to send. A class so the closure shares one instance rather
  /// than capturing a copy of a struct.
  private final class Recorder: @unchecked Sendable {
    private(set) var requests: [URLRequest] = []
    func record(_ request: URLRequest) { requests.append(request) }
  }

  private static func ok(for request: URLRequest) -> HTTPURLResponse {
    HTTPURLResponse(
      url: request.url ?? URL(string: "https://example.invalid")!,
      statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
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
