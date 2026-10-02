import Foundation
import XCTest

@testable import Omi_Computer

private final class RampState: @unchecked Sendable {
  let lock = NSLock()
  var owner = "synthetic-a"
  var generation = 0
  var excluded = false
  var feature = true
  var time: TimeInterval = 100
  var uploads: [String] = []
  var suspendAt: String?
  var sameOwner = false
  var change: String?
  var gateError: Error?
  var extractionError: Error?

  func boundary(_ stage: String) {
    lock.withLock {
      guard stage == suspendAt else { return }
      switch change {
      case "owner":
        generation += 1
        if !sameOwner { owner = "synthetic-b" }
      case "exclusion": excluded = true
      case "feature": feature = false
      default: break
      }
    }
  }
  func frameValid() throws {
    try lock.withLock {
      guard owner == "synthetic-a", generation == 0 else { throw ScreenTaskFailure.ownerRevoked }
      guard !excluded else { throw ScreenTaskFailure.privacyRevoked }
    }
  }
  func featureValid() throws { try lock.withLock { if !feature { throw ScreenTaskFailure.stopped } } }
  func append(_ name: String) { lock.withLock { uploads.append(name) } }
  var sent: [String] { lock.withLock { uploads } }
  var now: TimeInterval { lock.withLock { time } }
}

final class ScreenTaskRampBoundaryTests: XCTestCase {
  private let empty = #"{"screen_kind":"other","context_summary":"synthetic","current_activity":"reading","tasks":[]}"#

  private func services(_ state: RampState) -> ScreenTaskPipelineServices {
    let output = empty
    return ScreenTaskPipelineServices(
      validateFrame: { try state.frameValid() }, validateFeature: { try state.featureValid() },
      quota: { state.boundary("quota") },
      ocr: { _ in
        state.boundary("ocr")
        return OCRResult(
          fullText: "synthetic request",
          blocks: [
            OCRTextBlock(text: "synthetic request", x: 0.5, y: 0.5, width: 0.1, height: 0.02, confidence: 1)
          ], processedAt: Date())
      },
      retrieve: { _ in
        state.boundary("retrieval")
        return []
      },
      profile: {
        state.boundary("profile")
        return ""
      },
      gate: { _, _, _ in
        try ScreenTaskWorkAuthority.require()
        state.append("gate")
        state.boundary("gate")
        if let error = state.gateError { throw error }
        return ScreenTaskAdmission(shouldExtract: true, gateOutcome: "passed", auditSample: false)
      },
      extract: { _, _ in
        try ScreenTaskWorkAuthority.require()
        state.append("extraction")
        state.boundary("extraction")
        if let error = state.extractionError { throw error }
        return output
      },
      legacy: {
        try ScreenTaskWorkAuthority.require()
        state.append("legacy")
        return ScreenTaskExtraction(results: [], searchCount: 0, extractor: "legacy")
      }, fallback: { _, _ in }, now: { state.now })
  }

  private func frame(title: String = "synthetic conversation") -> CapturedFrame {
    CapturedFrame(
      jpegData: Data([1]), appName: "Messages", windowTitle: title, frameNumber: 1,
      captureTime: Date(timeIntervalSince1970: 1))
  }

  @MainActor func testCapturedButUndistributedDepartingFrameReachesPipelineWithCaptureOwner() async throws {
    let state = RampState()
    let authority = RuntimeOwnerAuthorizationAuthority()
    let original = try XCTUnwrap(authority.capture(ownerID: "synthetic-a", expectedOwnerID: "synthetic-a"))
    let binding = ScreenTaskFrameBinding(
      authorization: original,
      exclusion: RewindCaptureExclusionSnapshot(
        appName: "Messages", generation: 0,
        ownerSnapshot: RewindCaptureOwnerSnapshot(
          ownerID: "synthetic-a", generation: 0, authorizationSnapshot: original)))
    let spy = DepartingPipelineSpy(services: services(state))
    let coordinator = AssistantCoordinator.shared
    coordinator.register(spy)
    defer { coordinator.unregister(identifier: spy.spyIdentifier) }
    for _ in 0..<1000 where coordinator.assistant(withIdentifier: spy.spyIdentifier) == nil { await Task.yield() }
    XCTAssertNotNil(coordinator.assistant(withIdentifier: spy.spyIdentifier))
    _ = await coordinator.checkContextSwitch(
      newApp: "Messages", newWindowTitle: "synthetic chat", bucketsEnabled: false)
    let captured = CapturedFrame(
      jpegData: Data([42]), appName: "Messages", windowTitle: "synthetic chat",
      frameNumber: 2, taskBinding: binding)
    coordinator.trackFrame(captured)
    // Distribution is suppressed: analyze(frame:) is never called for this capture.
    _ = await coordinator.checkContextSwitch(
      newApp: "Synthetic editor", newWindowTitle: "document", bucketsEnabled: false)
    let received = await spy.received
    XCTAssertEqual(received?.taskBinding?.authorization, original)
    XCTAssertEqual(received?.jpegData, Data([42]))
    XCTAssertEqual(state.sent, ["gate", "extraction"])
  }

  func testOwnerSwapAtEveryExtractionSuspensionIncludingSameUIDNeverDispatchesLaterStage() async {
    for sameOwner in [false, true] {
      for stage in ["ocr", "quota", "retrieval", "profile", "gate", "extraction"] {
        let state = RampState()
        state.suspendAt = stage
        state.change = "owner"
        state.sameOwner = sameOwner
        do {
          _ = try await ScreenTaskPipeline().run(
            frame: frame(), key: "owner:1:window", services: services(state), metrics: ScreenTaskFrameMetrics())
          XCTFail("revoked owner returned a result at \(stage)")
        } catch {}
        let expected = stage == "extraction" ? ["gate", "extraction"] : (stage == "gate" ? ["gate"] : [])
        XCTAssertEqual(state.sent, expected, "owner swap at \(stage), same UID=\(sameOwner)")
      }
    }
  }

  func testExclusionDuringOCRAndGateWaitPreventsNextUpload() async {
    for stage in ["ocr", "gate"] {
      let state = RampState()
      state.suspendAt = stage
      state.change = "exclusion"
      do {
        _ = try await ScreenTaskPipeline().run(
          frame: frame(), key: "owner:1:window", services: services(state), metrics: ScreenTaskFrameMetrics())
        XCTFail("excluded frame returned a result")
      } catch {}
      XCTAssertEqual(state.sent, stage == "gate" ? ["gate"] : [])
    }
  }

  func testDisableDuringGateRollsBackWithOriginalFrameAuthorityAndNoNewScreenshotCall() async throws {
    let state = RampState()
    state.suspendAt = "gate"
    state.change = "feature"
    let metrics = ScreenTaskFrameMetrics()
    let result = try await ScreenTaskPipeline().run(
      frame: frame(), key: "owner:1:window", services: services(state), metrics: metrics)
    XCTAssertEqual(state.sent, ["gate", "legacy"])
    XCTAssertEqual(result.extractor, "legacy")
    XCTAssertEqual(metrics.fallbackReason, "dispatch_disabled")
    state.change = "owner"
    state.boundary("gate")
    do {
      _ = try await ScreenTaskPipeline().run(
        frame: frame(), key: "owner:1:window", services: services(state), metrics: ScreenTaskFrameMetrics())
      XCTFail("rollback rebound a revoked frame")
    } catch {}
    XCTAssertEqual(state.sent, ["gate", "legacy"])
  }

  func testExpiredLeaseStopsWithoutReloadAndDoesNotReauthorizeOldGeneration() throws {
    let state = RampState()
    let authority = ScreenTaskAdmissionAuthority(now: { state.now })
    authority.refresh(enabled: true)
    let token = try XCTUnwrap(authority.snapshot())
    state.time += 54
    XCTAssertTrue(authority.isCurrent(token))
    state.time += 1
    XCTAssertFalse(authority.isCurrent(token))
    XCTAssertNil(authority.snapshot())
    authority.refresh(enabled: true)
    XCTAssertFalse(authority.isCurrent(token))
    authority.disable()
    XCTAssertNil(authority.snapshot())
  }

  func testAdmissionLeaseCannotCrossOwnerOrSameUIDSessionTransition() throws {
    for sameUID in [false, true] {
      let state = RampState()
      let runtime = RuntimeOwnerAuthorizationAuthority()
      let original = try XCTUnwrap(runtime.capture(ownerID: state.owner, expectedOwnerID: state.owner))
      let lease = ScreenTaskAdmissionAuthority(
        now: { state.now },
        ownerIsCurrent: { snapshot in
          runtime.isCurrent(snapshot, ownerID: state.lock.withLock { state.owner })
        })
      lease.refresh(enabled: true, authorization: original)
      let token = try XCTUnwrap(lease.snapshot())
      runtime.beginTransition()
      let nextOwner = sameUID ? "synthetic-a" : "synthetic-b"
      runtime.endTransition(ownerID: nextOwner)
      state.lock.withLock { state.owner = nextOwner }
      XCTAssertNil(lease.snapshot())
      XCTAssertFalse(lease.isCurrent(token))
      let fresh = try XCTUnwrap(runtime.capture(ownerID: nextOwner, expectedOwnerID: nextOwner))
      lease.refresh(enabled: true, authorization: fresh)
      XCTAssertNotNil(lease.snapshot())
      XCTAssertFalse(lease.isCurrent(token))
    }
  }

  func testFlagTransportErrorsAndDelayedResponsesCannotRenewCachedTrueLease() throws {
    let state = RampState()
    let authority = ScreenTaskAdmissionAuthority(now: { state.now })
    authority.refresh(enabled: true, requestedAt: state.time)
    let old = try XCTUnwrap(authority.snapshot())
    XCTAssertThrowsError(
      try ScreenTaskFreshFlagResponse.enabled(
        Data(#"{"featureFlags":{"screen_task_jev_gate":true},"quotaLimited":["feature_flags"]}"#.utf8)))
    XCTAssertThrowsError(
      try ScreenTaskFreshFlagResponse.enabled(
        Data(#"{"featureFlags":{"screen_task_jev_gate":true},"errorsWhileComputingFlags":true}"#.utf8)))
    XCTAssertFalse(
      try ScreenTaskFreshFlagResponse.enabled(Data(#"{"featureFlags":{"screen_task_jev_gate":false}}"#.utf8)))
    state.time += 60
    authority.refresh(enabled: true, requestedAt: 100)
    XCTAssertNil(authority.snapshot())
    XCTAssertFalse(authority.isCurrent(old))
  }

  private func httpFailure(_ status: Int, retryable: String? = nil, retryAfter: String? = nil) throws
    -> ScreenTaskHTTPFailure
  {
    var headers: [String: String] = [:]
    headers["X-Omi-Retryable"] = retryable
    headers["Retry-After"] = retryAfter
    let url = try XCTUnwrap(URL(string: "http://local"))
    let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: headers))
    return ScreenTaskHTTPFailure(response: response, data: Data())
  }

  func testTerminalGateAndExtractionFailuresNeverEnterLegacyAndOutageEntersOnce() async throws {
    for gate in [true, false] {
      for error in [
        try httpFailure(401), try httpFailure(402), try httpFailure(429, retryable: "true", retryAfter: "60"),
        try httpFailure(503, retryable: "false"), ScreenTaskFailure.planGated, ScreenTaskFailure.invalidResponse,
      ] as [Error] {
        let state = RampState()
        if gate { state.gateError = error } else { state.extractionError = error }
        do {
          _ = try await ScreenTaskPipeline().run(
            frame: frame(), key: "owner:1:window", services: services(state), metrics: ScreenTaskFrameMetrics())
          XCTFail("terminal error was recovered")
        } catch {}
        XCTAssertFalse(state.sent.contains("legacy"))
      }
    }
    for error in [try httpFailure(503, retryable: "true"), URLError(.timedOut), URLError(.notConnectedToInternet)]
      as [Error]
    {
      let state = RampState()
      state.extractionError = error
      let metrics = ScreenTaskFrameMetrics()
      _ = try await ScreenTaskPipeline().run(
        frame: frame(), key: "owner:1:window", services: services(state), metrics: metrics)
      XCTAssertEqual(state.sent, ["gate", "extraction", "legacy"])
      XCTAssertEqual(metrics.legacyAttempts, 1)
      XCTAssertNotEqual(metrics.fallbackReason, "none")
    }
    XCTAssertEqual(try httpFailure(429, retryAfter: "60").retryAfter, 60)
  }

  func testGateAuthDenialRemainsTerminalWhenFeatureStopsDuringResponse() async throws {
    let state = RampState()
    state.suspendAt = "gate"
    state.change = "feature"
    state.gateError = try httpFailure(401)
    do {
      _ = try await ScreenTaskPipeline().run(
        frame: frame(), key: "owner:1:window", services: services(state), metrics: ScreenTaskFrameMetrics())
      XCTFail("auth denial became stop recovery")
    } catch {
      XCTAssertEqual(ScreenTaskErrorPolicy.errorClass(error), "auth")
    }
    XCTAssertEqual(state.sent, ["gate"])
  }

  func testRetryAfterDefersOnlyOriginalOwnerSession() throws {
    let state = RampState()
    let cooldown = ScreenTaskBackpressure(now: { state.now })
    let authority = RuntimeOwnerAuthorizationAuthority()
    let original = try XCTUnwrap(authority.capture(ownerID: "synthetic-a", expectedOwnerID: "synthetic-a"))
    cooldown.record(try httpFailure(429, retryAfter: "60"), owner: original)
    XCTAssertTrue(cooldown.isBlocked(original))
    state.time += 60
    XCTAssertFalse(cooldown.isBlocked(original))
    cooldown.record(try httpFailure(429, retryAfter: "60"), owner: original)
    authority.beginTransition()
    authority.endTransition(ownerID: "synthetic-a")
    let fresh = try XCTUnwrap(authority.capture(ownerID: "synthetic-a", expectedOwnerID: "synthetic-a"))
    XCTAssertFalse(cooldown.isBlocked(fresh))
  }

  func testRetainedOldCaptureExpiresByProcessingClockAndWindowIdentitySeparatesChats() async throws {
    let pipeline = ScreenTaskPipeline()
    let state = RampState()
    _ = try await pipeline.run(
      frame: frame(), key: "owner:1:window-a", services: services(state), metrics: ScreenTaskFrameMetrics())
    _ = try await pipeline.run(
      frame: frame(), key: "owner:1:window-a", services: services(state), metrics: ScreenTaskFrameMetrics())
    XCTAssertEqual(state.sent.count, 2)
    _ = try await pipeline.run(
      frame: frame(title: "other conversation"), key: "owner:1:window-b", services: services(state),
      metrics: ScreenTaskFrameMetrics())
    XCTAssertEqual(state.sent.count, 4)
    state.time += 61
    _ = try await pipeline.run(
      frame: frame(), key: "owner:1:window-a", services: services(state), metrics: ScreenTaskFrameMetrics())
    XCTAssertEqual(state.sent.count, 6)
  }

  func testExclusionPurgesMatchingQueuedPixelsWithoutDroppingAnotherApp() {
    let mailbox = ScreenTaskFrameMailbox()
    mailbox.enqueue(frame(), kind: .contextSwitch)
    mailbox.purge(app: "Synthetic editor")
    XCTAssertNotNil(mailbox.take())
    mailbox.enqueue(frame(), kind: .timerFallback)
    mailbox.purge(app: "Messages")
    XCTAssertNil(mailbox.take())
  }

  func testPrivateBrowserTitlesCannotPassAllowedKeywordAdmission() {
    for app in TaskAssistantSettings.browserApps {
      for marker in ["Incognito", "Private Browsing", "InPrivate", "Private Window", "Private Tab", "(Private)"] {
        XCTAssertTrue(ScreenTaskPrivacy.isPrivateWindow(app: app, title: "Gmail \(marker)"))
      }
      XCTAssertFalse(ScreenTaskPrivacy.isPrivateWindow(app: app, title: "Gmail Inbox"))
    }
  }

  func testOwnerSwapAtHandlerAndDeliverySuspensionsIncludingSameUIDRejectsMutation() async throws {
    for sameUID in [false, true] {
      for stage in ["confidence", "storage_pool", "workflow_control", "candidate_create", "receipt_update"] {
        let authority = RuntimeOwnerAuthorizationAuthority()
        let snapshot = try XCTUnwrap(authority.capture(ownerID: "synthetic-a", expectedOwnerID: "synthetic-a"))
        let nextOwner = sameUID ? "synthetic-a" : "synthetic-b"
        let mutation = LocalMutationAuthorization { authority.isCurrent(snapshot, ownerID: "synthetic-a") }
        var applied = false
        do {
          _ = try await ScreenTaskAuthorizedOperation.run(authorization: mutation) {
            authority.beginTransition()
            authority.endTransition(ownerID: nextOwner)
            await Task.yield()
            return stage
          }
          applied = true
        } catch {}
        XCTAssertFalse(applied, "late value applied at \(stage), same UID=\(sameUID)")
        XCTAssertThrowsError(try mutation.require())
      }
    }
  }

  func testTerminalTelemetryContainsOnlyDeclaredShapeFieldsAndDeliveredAuditCounts() {
    let metrics = ScreenTaskFrameMetrics()
    metrics.eligibleFrames = 1
    metrics.counts = ScreenTaskDeliveryCounts(
      policyRejected: 2, outboxSaved: 4, coalesced: 1, pendingDelivered: 1, failed: 1)
    let properties = metrics.properties(captureToTerminalMS: 42)
    XCTAssertEqual(properties["pending_delivered"] as? Int, 1)
    XCTAssertEqual(properties["eligible_frames"] as? Int, 1)
    XCTAssertEqual(properties["schema_version"] as? Int, 2)
    for forbidden in ["screen_text", "task_text", "title", "score", "owner_id", "app_name"] {
      XCTAssertNil(properties[forbidden])
    }
    XCTAssertEqual(properties["capture_to_terminal_ms"] as? Double, 42)
  }
}

private actor DepartingPipelineSpy: ProactiveAssistant {
  nonisolated let spyIdentifier = "departure-pipeline-\(UUID().uuidString)"
  var identifier: String { spyIdentifier }
  var displayName: String { "Departure pipeline fixture" }
  var isEnabled: Bool { true }
  var needsFrameDuringDelay: Bool { false }
  let services: ScreenTaskPipelineServices
  private(set) var received: CapturedFrame?
  init(services: ScreenTaskPipelineServices) { self.services = services }
  func analyze(frame: CapturedFrame) async -> AssistantResult? {
    XCTFail("fixture must suppress distribution")
    return nil
  }
  func handleResult(_ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void) async {}
  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    guard let departingFrame, let owner = departingFrame.taskBinding?.authorization else { return }
    received = departingFrame
    do {
      _ = try await ScreenTaskPipeline().run(
        frame: departingFrame, key: "\(owner.ownerID):\(owner.authorizationGeneration):window",
        services: services, metrics: ScreenTaskFrameMetrics())
    } catch { XCTFail("departing capture failed: \(error)") }
  }
  func clearPendingWork() async {}
  func stop() async {}
}
