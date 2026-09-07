@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class ProactiveLaneClientTests: XCTestCase {
  private var priorAuthUserID: String?

  override func setUp() {
    super.setUp()
    priorAuthUserID = UserDefaults.standard.string(forKey: .authUserId)
  }

  override func tearDown() {
    // The JIT authority routes re-validate the runtime owner against the
    // shared authorization authority; restore the durable auth user and the
    // authority owner the rest of the suite expects.
    let authority = RuntimeOwnerAuthorizationAuthority.shared
    authority.beginTransition()
    if let priorAuthUserID {
      UserDefaults.standard.set(priorAuthUserID, forKey: .authUserId)
      authority.endTransition(ownerID: priorAuthUserID)
    } else {
      UserDefaults.standard.removeObject(forKey: .authUserId)
      authority.endTransition(ownerID: nil)
    }
    super.tearDown()
  }

  func testEnvelopeParsingPreservesGatewayAccounting() throws {
    let data = try JSONSerialization.data(withJSONObject: [
      "operation": "proactive_reasoning",
      "lane": "omi:auto:desktop-proactive-reasoning",
      "provider_model": "gpt-5.6-luna",
      "usage": ["cached_tokens": 900, "cache_write_tokens": 0],
      "cache_write": false,
      "fallback_class": "unknown",
      "response": [
        "id": "response-123",
        "choices": [["message": ["content": "{\"decision\":\"silence\"}"]]],
        "usage": [
          "prompt_tokens": 80, "completion_tokens": 7, "total_tokens": 87,
          "cached_tokens": 12, "cache_write_tokens": 4,
        ],
      ],
    ])
    let parsed = try ProactiveLaneClient.parseEnvelope(data, requestID: "request-123")
    XCTAssertEqual(parsed.usage.cachedTokens, 900)
    XCTAssertEqual(parsed.lane, "omi:auto:desktop-proactive-reasoning")
    XCTAssertEqual(parsed.content, "{\"decision\":\"silence\"}")
    XCTAssertEqual(parsed.requestID, "request-123")
    XCTAssertEqual(parsed.providerResponseID, "response-123")
    XCTAssertEqual(parsed.usage.inputTokens, 80)
    XCTAssertEqual(parsed.usage.outputTokens, 7)
    XCTAssertEqual(parsed.usage.totalTokens, 87)
    XCTAssertEqual(parsed.usage.reportedCachedTokens, 12)
    XCTAssertEqual(parsed.usage.reportedCacheWriteTokens, 4)
  }

  func testEnvelopeParsingKeepsMalformedProviderUsageUnknown() throws {
    let data = try JSONSerialization.data(withJSONObject: [
      "operation": "proactive_extraction",
      "lane": "omi:auto:desktop-proactive-extraction",
      "provider_model": "gpt-5-nano",
      "usage": ["cached_tokens": 9],
      "cache_write": false,
      "fallback_class": "unknown",
      "response": [
        "choices": [["message": ["content": "{\"approved\":true}"]]],
        "usage": [
          "prompt_tokens": true,
          "completion_tokens": 1.5,
          "total_tokens": NSNumber(value: UInt64.max),
          "cached_tokens": false,
        ],
      ],
    ])

    let parsed = try ProactiveLaneClient.parseEnvelope(data)
    XCTAssertNil(parsed.usage.inputTokens)
    XCTAssertNil(parsed.usage.outputTokens)
    XCTAssertNil(parsed.usage.totalTokens)
    XCTAssertNil(parsed.usage.reportedCachedTokens)
    XCTAssertNil(parsed.usage.reportedCacheWriteTokens)
    // The provider cache field is malformed, but the gateway's legacy
    // envelope accounting remains independently valid.
    XCTAssertEqual(parsed.usage.cachedTokens, 9)
  }

  func testNanoBillingObservationUsesProviderUsageAndNeverInfersCost() throws {
    let result = ProactiveLaneResult(
      operation: ModelQoS.Proactivity.extractionOperation,
      lane: "omi:auto:desktop-proactive-extraction",
      providerModel: "gpt-5-nano",
      usage: ProactiveLaneUsage(
        cachedTokens: 12, cacheWriteTokens: 4, inputTokens: 80, outputTokens: 7, totalTokens: 87),
      cacheWrite: true,
      fallbackClass: "none",
      content: "{\"approved\":true}",
      requestID: "request-123",
      provider: "openai",
      providerResponseID: "response-123")
    let transport = ProactiveLaneResponseObservation(
      statusCode: 200,
      requestID: "request-123",
      operation: result.operation,
      provider: result.provider,
      providerModel: result.providerModel,
      providerResponseID: result.providerResponseID,
      usage: result.usage,
      fallbackClass: result.fallbackClass,
      failure: nil)
    let observed = JITProactivityNanoBillingObservation.observed(
      lane: .ambient,
      ownerID: JITProactivitySourceProjection.qaOwnerID,
      accountGeneration: 3,
      snapshotRevision: "revision",
      budgetDay: "2026-09-06",
      contextID: "context-1",
      candidateID: "candidate-1",
      executionID: "execution-1",
      triage: .approved,
      transport: transport)
    XCTAssertEqual(observed.dispatch, "observed")
    XCTAssertEqual(observed.inputTokens, 80)
    XCTAssertEqual(observed.outputTokens, 7)
    XCTAssertEqual(observed.providerModel, "gpt-5-nano")
    XCTAssertEqual(observed.providerResponseID, "response-123")
    XCTAssertEqual(observed.requestID, "request-123")
    XCTAssertEqual(observed.usageStatus, "reported")
    XCTAssertEqual(observed.costStatus, "unknown")
    XCTAssertNil(observed.estimatedCostMicroUSD)
    XCTAssertNil(observed.providerAttempts)
    let json = try JSONSerialization.data(withJSONObject: observed.wireDictionary)
    let wire = try XCTUnwrap(JSONSerialization.jsonObject(with: json) as? [String: Any])
    XCTAssertNil(wire["content"])
    XCTAssertNil(wire["prompt"])
    XCTAssertEqual(wire["cost_status"] as? String, "unknown")
  }

  func testNanoBillingObservationClassifiesMalformedAndNoDispatchWithoutZeroUsage() {
    let malformed = JITProactivityNanoBillingObservation.observed(
      lane: .planned,
      ownerID: JITProactivitySourceProjection.qaOwnerID,
      accountGeneration: 3,
      snapshotRevision: "revision",
      budgetDay: "2026-09-06",
      contextID: "context-1",
      candidateID: "candidate-1",
      executionID: nil,
      triage: .unknown,
      transport: ProactiveLaneResponseObservation(
        statusCode: 422,
        requestID: "request-422",
        failure: ProactiveLaneFailureClassification(
          failure: "invalid_structured_output", status: 422, errorType: nil)))
    XCTAssertEqual(malformed.outcome, "malformed")
    XCTAssertEqual(malformed.dispatch, "observed")
    XCTAssertEqual(malformed.usageStatus, "unknown")
    XCTAssertNil(malformed.inputTokens)
    XCTAssertNil(malformed.outputTokens)
    XCTAssertEqual(malformed.costStatus, "unknown")

    let noDispatch = JITProactivityNanoBillingObservation.notDispatched(
      lane: .planned,
      ownerID: JITProactivitySourceProjection.qaOwnerID,
      accountGeneration: 3,
      snapshotRevision: "revision",
      budgetDay: "2026-09-06",
      contextID: "planned:trigger",
      candidateID: "candidate-1",
      executionID: "candidate-1")
    XCTAssertEqual(noDispatch.outcome, "not_dispatched")
    XCTAssertEqual(noDispatch.providerAttempts, 0)
    XCTAssertEqual(noDispatch.usageStatus, "not_applicable")
    XCTAssertEqual(noDispatch.costStatus, "not_applicable")
  }

  func testCompleteObserverCapturesRequestIdentityAndMalformedOutcomeMetadata() async throws {
    ProactiveLaneURLStub.reset()
    let client = ProactiveLaneClient(
      session: makeStubSession(), baseURL: { "https://proactive.test" }, authorization: { "Bearer test" })
    let probe = ResponseObservationProbe()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation),
      headers: ["X-Omi-Request-ID": "request-observed"])
    _ = try await client.complete(
      operation: ModelQoS.Proactivity.extractionOperation,
      prompt: "nano",
      jsonSchema: ["type": "object"],
      responseObserver: { observation in await probe.set(observation) })
    let successValue = await probe.value
    let success = try XCTUnwrap(successValue)
    XCTAssertEqual(success.statusCode, 200)
    XCTAssertEqual(success.requestID, "request-observed")
    XCTAssertNil(success.failure)

    ProactiveLaneURLStub.enqueue(
      statusCode: 200, body: Data("malformed".utf8), headers: ["X-Omi-Request-ID": "request-malformed"])
    do {
      _ = try await client.complete(
        operation: ModelQoS.Proactivity.extractionOperation,
        prompt: "nano",
        jsonSchema: ["type": "object"],
        responseObserver: { observation in await probe.set(observation) })
      XCTFail("expected malformed response")
    } catch ProactiveLaneClientError.invalidResponse {
      // The bounded observer still receives the route request identity.
    }
    let malformedValue = await probe.value
    let malformed = try XCTUnwrap(malformedValue)
    XCTAssertEqual(malformed.requestID, "request-malformed")
    XCTAssertEqual(malformed.failure?.failure, "invalid_response")
  }

  func testTelemetryProviderModelIsBounded() {
    XCTAssertEqual(ContextProactivityTelemetry.boundedProviderModel("gpt-5.6-luna"), "gpt-5.6-luna")
    XCTAssertEqual(ContextProactivityTelemetry.boundedProviderModel("attacker-controlled-model"), "other")
  }

  func testTelemetryDirectorDecisionIsBounded() {
    for allowed in ["suggest", "insight", "task_candidate", "resurface", "silence"] {
      XCTAssertEqual(ContextProactivityTelemetry.boundedDirectorDecision(allowed), allowed)
    }
    XCTAssertEqual(
      ContextProactivityTelemetry.boundedDirectorDecision("model-invented-decision"), "other",
      "decision strings come from model output and must collapse to a bounded set")
  }

  func testClientErrorsExposeOnlyStableSafeClassifications() {
    XCTAssertEqual(ProactiveLaneClientError.invalidResponse.localizedDescription, "proactive_invalid_response")
    XCTAssertEqual(
      ProactiveLaneClientError.http(status: 429, retryAfterSeconds: nil).localizedDescription,
      "proactive_http_error status=429")
    XCTAssertEqual(ProactiveLaneClientError.ownerChanged.localizedDescription, "proactive_owner_changed")
    XCTAssertEqual(
      ProactiveLaneClientError.quotaCooldown(retryAfterSeconds: 12).localizedDescription,
      "proactive_quota_cooldown status=429")
    XCTAssertEqual(ProactiveLaneClientError.planGated.localizedDescription, "proactive_plan_gated")
  }

  func testPlanGatedIsNotClassifiedAsNetworkOrRetryableHTTP() {
    let classified = ProactiveLaneFailureClassification.classify(ProactiveLaneClientError.planGated)
    XCTAssertEqual(classified.failure, "plan_gated")
    XCTAssertEqual(classified.status, 402)
    XCTAssertNotEqual(classified.failure, "network")
    XCTAssertNotEqual(classified.failure, "http_error")
  }

  func testPixelCompleteThrowsPlanGatedWithoutNetwork() async throws {
    ProactiveLaneURLStub.reset()
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      managedPixelDecision: { .planGated })
    ProactiveLaneURLStub.enqueue(
      statusCode: 200, body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))
    do {
      _ = try await client.complete(
        operation: ModelQoS.Proactivity.extractionOperation,
        prompt: "extract",
        imageData: Data("jpeg".utf8),
        jsonSchema: ["type": "object"])
      XCTFail("expected planGated")
    } catch ProactiveLaneClientError.planGated {
      XCTAssertTrue(ProactiveLaneURLStub.requestedPaths.isEmpty)
    }
  }

  func testTextOnlyCompleteIsNotPreGatedByBasicPlan() async throws {
    ProactiveLaneURLStub.reset()
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      managedPixelDecision: { .planGated })
    ProactiveLaneURLStub.enqueue(
      statusCode: 200, body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))
    let result = try await client.complete(
      operation: ModelQoS.Proactivity.extractionOperation,
      prompt: "extract",
      jsonSchema: ["type": "object"])
    XCTAssertEqual(result.operation, ModelQoS.Proactivity.extractionOperation)
    XCTAssertEqual(ProactiveLaneURLStub.requestedPaths, ["/v1/desktop/proactivity/completions"])
  }

  func testHTTP402PlanGatedBodyMapsToPlanGated() async throws {
    ProactiveLaneURLStub.reset()
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      managedPixelDecision: { .allowManagedProactivity })
    ProactiveLaneURLStub.enqueue(
      statusCode: 402,
      body: Data(#"{"detail":{"error":"plan_gated","plan_type":"basic"}}"#.utf8))
    do {
      _ = try await client.complete(
        operation: ModelQoS.Proactivity.extractionOperation,
        prompt: "extract",
        jsonSchema: ["type": "object"])
      XCTFail("expected planGated")
    } catch ProactiveLaneClientError.planGated {
    }
  }

  func testUnprocessableEntityIsClassifiedAsInvalidStructuredOutputNotHttpError() throws {
    let classified = ProactiveLaneFailureClassification.classify(
      ProactiveLaneClientError.http(status: 422, retryAfterSeconds: nil))
    XCTAssertEqual(classified.failure, "invalid_structured_output")
    XCTAssertEqual(classified.status, 422)
    XCTAssertEqual(classified.logDescription, "invalid_structured_output status=422")
    let json = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(classified.provenanceJSON.utf8)) as? [String: Any])
    XCTAssertEqual(json["failure"] as? String, "invalid_structured_output")
    XCTAssertEqual((json["status"] as? NSNumber)?.intValue, 422)
    XCTAssertNil(json["error_type"])

    let transport = ProactiveLaneFailureClassification.classify(
      ProactiveLaneClientError.http(status: 502, retryAfterSeconds: nil))
    XCTAssertEqual(transport.failure, "http_error")
    XCTAssertEqual(transport.status, 502)
    XCTAssertNotEqual(classified.failure, transport.failure)
  }

  func testGarbageEnvelopeThrowsInvalidResponseNotARawSerializationError() {
    do {
      _ = try ProactiveLaneClient.parseEnvelope(Data("not-json".utf8))
      XCTFail("expected invalid_response")
    } catch ProactiveLaneClientError.invalidResponse {
      // Expected: envelope parse failures are a bounded class, not a Cocoa error.
    } catch {
      XCTFail("unexpected error: \(error)")
    }
  }

  func testRetryAfterHeaderIsParsedAsSeconds() throws {
    let url = try XCTUnwrap(URL(string: "https://proactive.test/v1/desktop/proactivity/completions"))
    let response = try XCTUnwrap(
      HTTPURLResponse(
        url: url,
        statusCode: 429,
        httpVersion: nil,
        headerFields: ["Retry-After": " 45 "]))
    XCTAssertEqual(ProactiveLaneClient.parseRetryAfterSeconds(from: response), 45)
  }

  func testQuotaHeadersLogWhenRemainingIsLowAndAlwaysOn429() throws {
    let url = try XCTUnwrap(URL(string: "https://proactive.test/v1/desktop/proactivity/completions"))
    let low = try XCTUnwrap(
      HTTPURLResponse(
        url: url,
        statusCode: 200,
        httpVersion: nil,
        headerFields: [
          "X-Proactive-Quota-Limit": "200",
          "X-Proactive-Quota-Remaining": "12",
          "X-Proactive-Quota-Reset": "3600",
        ]))
    let healthy = try XCTUnwrap(
      HTTPURLResponse(
        url: url,
        statusCode: 200,
        httpVersion: nil,
        headerFields: [
          "X-Proactive-Quota-Limit": "200",
          "X-Proactive-Quota-Remaining": "180",
          "X-Proactive-Quota-Reset": "3600",
        ]))
    let rateLimited = try XCTUnwrap(
      HTTPURLResponse(
        url: url,
        statusCode: 429,
        httpVersion: nil,
        headerFields: [
          "X-Proactive-Quota-Limit": "200",
          "X-Proactive-Quota-Remaining": "0",
          "X-Proactive-Quota-Reset": "3600",
        ]))
    let rateLimitedWithoutHeaders = try XCTUnwrap(
      HTTPURLResponse(url: url, statusCode: 429, httpVersion: nil, headerFields: [:]))

    let lowObservation = try XCTUnwrap(ProactiveQuotaObservation.parse(from: low))
    XCTAssertEqual(lowObservation.remaining, 12)
    XCTAssertEqual(lowObservation.limit, 200)
    XCTAssertEqual(lowObservation.resetSeconds, 3600)
    XCTAssertTrue(lowObservation.isLow)
    XCTAssertTrue(ProactiveQuotaObservation.shouldLog(lowObservation, statusCode: 200))
    XCTAssertEqual(
      ProactiveQuotaObservation.logLine(operation: "proactive_extraction", observation: lowObservation),
      "ProactiveLaneClient: quota extraction remaining=12/200 reset=3600s")

    let healthyObservation = try XCTUnwrap(ProactiveQuotaObservation.parse(from: healthy))
    XCTAssertFalse(healthyObservation.isLow)
    XCTAssertFalse(ProactiveQuotaObservation.shouldLog(healthyObservation, statusCode: 200))

    let denied = try XCTUnwrap(ProactiveQuotaObservation.parse(from: rateLimited))
    XCTAssertTrue(ProactiveQuotaObservation.shouldLog(denied, statusCode: 429))
    XCTAssertTrue(ProactiveQuotaObservation.shouldLog(nil, statusCode: 429))
    XCTAssertEqual(
      ProactiveQuotaObservation.logLine(operation: "proactive_extraction", observation: nil),
      "ProactiveLaneClient: quota extraction remaining=unknown")
    XCTAssertNil(ProactiveQuotaObservation.parse(from: rateLimitedWithoutHeaders))
  }

  func testExtractionSkipsNetworkDuringQuotaCooldownThenResumesAfterDeadline() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(#"{"detail":"Proactive request limit exceeded"}"#.utf8),
      headers: ["Retry-After": "120"])

    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the first extraction attempt to throw 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertEqual(retryAfter, 120)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 10)
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the in-window extraction attempt to skip the network")
    } catch ProactiveLaneClientError.quotaCooldown(let retryAfter) {
      XCTAssertEqual(retryAfter, 110)
    }
    XCTAssertEqual(
      ProactiveLaneURLStub.requestCount, 1,
      "an extraction attempt before Retry-After must not hit the network")

    clock.advance(by: 111)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))

    let result = try await completeExtraction(on: client)
    XCTAssertEqual(result.operation, ModelQoS.Proactivity.extractionOperation)
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)
  }

  func testMissingRetryAfterUsesConservativeDefaultCooldown() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(statusCode: 429, body: Data(), headers: [:])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertNil(retryAfter)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: TimeInterval(ProactiveLaneClient.defaultQuotaCooldownSeconds - 1))
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected cooldown skip")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Expected: a missing Retry-After still arms the conservative default.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)
  }

  func testExtractionQuotaCooldownDoesNotSuppressReasoning() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(#"{"detail":"Proactive request limit exceeded"}"#.utf8),
      headers: ["Retry-After": "120"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected extraction 429")
    } catch ProactiveLaneClientError.http(let status, _) {
      XCTAssertEqual(status, 429)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestedOperations, [ModelQoS.Proactivity.extractionOperation])

    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.reasoningOperation))
    let reasoning = try await completeReasoning(on: client)
    XCTAssertEqual(reasoning.operation, ModelQoS.Proactivity.reasoningOperation)
    XCTAssertEqual(
      ProactiveLaneURLStub.requestedOperations,
      [ModelQoS.Proactivity.extractionOperation, ModelQoS.Proactivity.reasoningOperation],
      "reasoning must still reach the network after an extraction 429")

    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected extraction to remain in cooldown")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Extraction stays suppressed in its own window.
    }
    XCTAssertEqual(
      ProactiveLaneURLStub.requestedOperations,
      [ModelQoS.Proactivity.extractionOperation, ModelQoS.Proactivity.reasoningOperation],
      "a later extraction attempt in the same window must not hit the network")
  }

  func testRetryAfterAboveADayIsClampedToOneHour() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(),
      headers: ["Retry-After": "86400"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertEqual(retryAfter, 86400)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: TimeInterval(ProactiveLaneClient.maxQuotaCooldownSeconds - 1))
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the clamped hour cooldown to still skip the network")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Still inside the 3600s ceiling.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 2)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))
    let result = try await completeExtraction(on: client)
    XCTAssertEqual(result.operation, ModelQoS.Proactivity.extractionOperation)
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)
  }

  func testTinyOrZeroRetryAfterArmsAtLeastTheFloor() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(),
      headers: ["Retry-After": "1"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(_, _) {
      // Server 429 with a sub-floor Retry-After.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: TimeInterval(ProactiveLaneClient.minQuotaCooldownSeconds - 1))
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the 60s floor to still skip the network")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Tiny Retry-After is raised to the 60s floor.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 2)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))
    _ = try await completeExtraction(on: client)
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)

    ProactiveLaneURLStub.enqueue(statusCode: 429, body: Data(), headers: ["Retry-After": "0"])
    do {
      _ = try await completeReasoning(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(_, _) {
      // Zero Retry-After falls through to the conservative default.
    }
    clock.advance(by: TimeInterval(ProactiveLaneClient.minQuotaCooldownSeconds - 1))
    do {
      _ = try await completeReasoning(on: client)
      XCTFail("expected at least the 60s floor")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Zero/absent Retry-After must not arm a sub-floor cooldown.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 3)
  }

  // MARK: - JIT authority wire contract

  func testRolloutDecisionEffectiveEnabledAdmitsEvenWhenRawFlagsAreNotAKnownGoodPair() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "unknown", killSwitch: "disabled", effective: "enabled"))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertEqual(flags.effective, .enabled)
    XCTAssertTrue(flags.permitsNewLane)
  }

  func testRolloutDecisionToleratesMissingKillSwitchWhenEffectiveEnabled() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "enabled", killSwitch: nil, effective: "enabled"))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertFalse(flags.killSwitchPresent)
    XCTAssertEqual(flags.killSwitch, .unknown)
    XCTAssertTrue(flags.permitsNewLane)
  }

  func testRolloutDecisionUnknownStatesStillFailClosed() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "unknown", killSwitch: "unknown", effective: "unknown"))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertFalse(flags.permitsNewLane)
  }

  func testRolloutDecisionPresentUnknownKillSwitchWithoutEffectiveFailsClosed() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "enabled", killSwitch: "unknown", effective: nil))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertTrue(flags.killSwitchPresent)
    XCTAssertFalse(flags.permitsNewLane)
  }

  /// The live gap: a complete, empty, snake_case watchlist had to decode, and a
  /// failing ledger-mirror sync had to stop blocking the trigger snapshot the
  /// client already holds.
  func testTriggerSnapshotDecodesEmptyWatchlistAndReturnsDespiteMirrorSyncFailure() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(statusCode: 200, body: try triggerSnapshotBody(ownerID: "owner"))
    let mirror = MirrorSyncProbe()
    let client = makeJITAuthorityClient(
      mirrorSync: { _, _ in
        await mirror.record()
        throw URLError(.notConnectedToInternet)
      })

    let snapshot = try await client.fetchJITTriggerSnapshot(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertTrue(snapshot.complete)
    XCTAssertEqual(snapshot.rows, [])
    XCTAssertNil(snapshot.failureReason)
    XCTAssertEqual(snapshot.ownerID, "owner")
    let attempts = await mirror.attempts
    XCTAssertEqual(attempts, 1, "the ledger mirror must still be attempted exactly once")
  }

  func testTriggerSnapshotDecodesServerBudgetAuthority() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try triggerSnapshotBody(
        ownerID: "owner", budgetDay: "2026-08-23", budgetTimezone: "America/Los_Angeles"))
    let client = makeJITAuthorityClient()

    let snapshot = try await client.fetchJITTriggerSnapshot(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertEqual(snapshot.budgetDay, "2026-08-23")
    XCTAssertEqual(snapshot.budgetTimezone, "America/Los_Angeles")
  }

  func testTriggerSnapshotRefreshAdoptsTimezoneChangeWithUnchangedRevision() async throws {
    ProactiveLaneURLStub.reset()
    // A profile timezone update does not necessarily change the ledger head or
    // snapshot revision. The mirror must still consume the new budget authority
    // returned by the next refresh rather than treating the revision as a cache key.
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try triggerSnapshotBody(
        ownerID: "owner", budgetDay: "2026-08-23", budgetTimezone: "America/Los_Angeles"))
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try triggerSnapshotBody(
        ownerID: "owner", budgetDay: "2026-08-24", budgetTimezone: "America/New_York"))
    let client = makeJITAuthorityClient()

    let first = try await client.fetchJITTriggerSnapshot(
      authorizationSnapshot: try jitAuthorizationSnapshot())
    let second = try await client.fetchJITTriggerSnapshot(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertEqual(first.snapshotRevision, second.snapshotRevision)
    XCTAssertEqual(first.budgetTimezone, "America/Los_Angeles")
    XCTAssertEqual(second.budgetTimezone, "America/New_York")
    XCTAssertEqual(first.budgetDay, "2026-08-23")
    XCTAssertEqual(second.budgetDay, "2026-08-24")
  }

  func testDisabledTriggerSnapshotReturnsContentFreeReceiptWithoutTouchingTheMirror() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try triggerSnapshotBody(ownerID: "owner", complete: false, failureReason: "rollout_not_enabled"))
    let mirror = MirrorSyncProbe()
    let client = makeJITAuthorityClient(
      mirrorSync: { _, _ in
        await mirror.record()
      })

    let snapshot = try await client.fetchJITTriggerSnapshot(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertFalse(snapshot.complete)
    XCTAssertEqual(snapshot.failureReason, "rollout_not_enabled")
    let attempts = await mirror.attempts
    XCTAssertEqual(attempts, 0, "a stub snapshot must not attempt the ledger mirror")
  }

  func testTriggerSnapshotForAnotherOwnerFailsClosed() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(statusCode: 200, body: try triggerSnapshotBody(ownerID: "other-owner"))
    let client = makeJITAuthorityClient()

    do {
      _ = try await client.fetchJITTriggerSnapshot(
        authorizationSnapshot: try jitAuthorizationSnapshot())
      XCTFail("a snapshot for another owner must fail closed")
    } catch let error as ProactiveLaneClientError {
      guard case .invalidResponse = error else {
        return XCTFail("expected invalidResponse, got \(error)")
      }
    } catch {
      XCTFail("expected ProactiveLaneClientError, got \(error)")
    }
  }

  func testGarbageTriggerSnapshotThrowsInvalidResponse() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200, body: try JSONSerialization.data(withJSONObject: ["unexpected": true]))
    let client = makeJITAuthorityClient()

    do {
      _ = try await client.fetchJITTriggerSnapshot(
        authorizationSnapshot: try jitAuthorizationSnapshot())
      XCTFail("an undecodable snapshot body must fail closed")
    } catch let error as ProactiveLaneClientError {
      guard case .invalidResponse = error else {
        return XCTFail("expected invalidResponse, got \(error)")
      }
    } catch {
      XCTFail("expected ProactiveLaneClientError, got \(error)")
    }
  }

  // MARK: - Signed-in startup snapshot sync (wire)

  /// Signed-in startup must fetch the trigger snapshot without any context
  /// visit: the runtime's startup sync drives the real client routes in
  /// order — rollout-decision, then trigger-snapshot — and a complete empty
  /// watchlist still persists the local receipt.
  func testStartupSnapshotSyncIssuesRolloutThenSnapshotGETAndWritesReceipt() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "unknown", killSwitch: "disabled", effective: "enabled"))
    ProactiveLaneURLStub.enqueue(statusCode: 200, body: try triggerSnapshotBody(ownerID: "owner"))
    let client = makeJITAuthorityClient()
    let queue = try migratedMirrorQueue()
    let runtime = JITProactivityRuntime(
      flags: { await client.jitProactivityFlags(authorizationSnapshot: $0) },
      snapshots: { try await client.fetchJITTriggerSnapshot(authorizationSnapshot: $0) },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
      })

    await runtime.syncTriggerSnapshot(authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertEqual(
      ProactiveLaneURLStub.requestedPaths, ["/v1/jit/rollout-decision", "/v1/jit/trigger-snapshot"])
    let receipts = try await queue.read { db in
      try Row.fetchAll(db, sql: "SELECT ownerID, rowCount FROM jit_trigger_snapshot_receipts")
    }
    XCTAssertEqual(receipts.count, 1)
    let receipt = try XCTUnwrap(receipts.first)
    let ownerID: String = receipt["ownerID"]
    let rowCount: Int = receipt["rowCount"]
    XCTAssertEqual(ownerID, "owner")
    XCTAssertEqual(rowCount, 0, "an empty watchlist still persists its receipt")
  }

  /// Fail-closed startup: an `effective=disabled` authority reads only the
  /// rollout decision and never issues the trigger-snapshot GET.
  func testStartupSnapshotSyncWithEffectiveDisabledNeverIssuesSnapshotGET() async throws {
    ProactiveLaneURLStub.reset()
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "unknown", killSwitch: "unknown", effective: "disabled"))
    let client = makeJITAuthorityClient()
    let queue = try migratedMirrorQueue()
    let runtime = JITProactivityRuntime(
      flags: { await client.jitProactivityFlags(authorizationSnapshot: $0) },
      snapshots: { try await client.fetchJITTriggerSnapshot(authorizationSnapshot: $0) },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
      })

    await runtime.syncTriggerSnapshot(authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertEqual(ProactiveLaneURLStub.requestedPaths, ["/v1/jit/rollout-decision"])
    let receipts = try await queue.read { db in
      try String.fetchAll(db, sql: "SELECT ownerID FROM jit_trigger_snapshot_receipts")
    }
    XCTAssertTrue(receipts.isEmpty)
  }

  /// The JIT authority routes re-validate the runtime owner against
  /// `RuntimeOwnerAuthorizationAuthority.shared` and the durable auth user, so
  /// the shared authority has to hold this test owner at a known generation.
  private func jitAuthorizationSnapshot(ownerID: String = "owner") throws
    -> RuntimeOwnerAuthorizationSnapshot
  {
    UserDefaults.standard.set(ownerID, forKey: .authUserId)
    let authority = RuntimeOwnerAuthorizationAuthority.shared
    authority.beginTransition()
    authority.endTransition(ownerID: ownerID)
    return try XCTUnwrap(authority.capture(ownerID: ownerID, expectedOwnerID: ownerID))
  }

  private func makeJITAuthorityClient(
    mirrorSync:
      @escaping @Sendable (
        RuntimeOwnerAuthorizationSnapshot, JITTriggerSnapshot
      ) async throws -> Void = { _, _ in }
  ) -> ProactiveLaneClient {
    ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://jit-authority.test" },
      jitAuthorization: { ownerID in "Bearer test-\(ownerID)" },
      ledgerMirrorSync: mirrorSync)
  }

  private func migratedMirrorQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    var migrator = DatabaseMigrator()
    JITTriggerMirrorSchema.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    return queue
  }

  private func rolloutDecisionBody(
    rollout: String?, killSwitch: String?, effective: String?
  ) throws -> Data {
    var object: [String: Any] = [
      "reason": "rollout_enabled",
      "error_class": "none",
      "cache_hit": false,
      "cache_ttl_seconds": 30,
    ]
    object["rollout"] = rollout
    object["kill_switch"] = killSwitch
    object["effective"] = effective
    return try JSONSerialization.data(withJSONObject: object)
  }

  private func triggerSnapshotBody(
    ownerID: String, complete: Bool = true, failureReason: String? = nil,
    budgetDay: String? = nil, budgetTimezone: String? = nil
  ) throws -> Data {
    var object: [String: Any] = [
      "owner_id": ownerID,
      "snapshot_revision": "revision-4",
      "account_generation": 3,
      "head_commit_id": "head-4",
      "commit_sequence": 4,
      "complete": complete,
      "rows": [] as [[String: Any]],
      "policy": ratifiedPolicyWireJSON(),
      "failure_reason": (failureReason as Any?) ?? NSNull(),
    ]
    if let budgetDay { object["budget_day"] = budgetDay }
    if let budgetTimezone { object["budget_timezone"] = budgetTimezone }
    return try JSONSerialization.data(withJSONObject: object)
  }
  private func ratifiedPolicyWireJSON() -> [String: Any] {
    [
      "schema_version": "jit_trigger_policy.v1",
      "planned_notifications_per_trigger_per_day": 1,
      "total_proactive_notifications_per_day": 3,
      "ambiguous_nano_triages_per_day": 8,
      "full_agent_turns_per_candidate": 1,
      "max_calendar_events": 32,
      "valid_for_seconds": 30,
      "paid_boundary_refresh_required": true,
      "embedding": [
        "enabled": false,
        "match_similarity": 0.82,
        "triage_similarity": 0.74,
        "model_id": NSNull(),
        "model_version": NSNull(),
        "language": NSNull(),
      ] as [String: Any],
    ]
  }

  private func completeExtraction(on client: ProactiveLaneClient) async throws -> ProactiveLaneResult {
    try await complete(operation: ModelQoS.Proactivity.extractionOperation, prompt: "extract", on: client)
  }

  private func completeReasoning(on client: ProactiveLaneClient) async throws -> ProactiveLaneResult {
    try await complete(operation: ModelQoS.Proactivity.reasoningOperation, prompt: "reason", on: client)
  }

  /// Two 429s that were already in flight together must leave the *longer* window armed.
  ///
  /// Both attempts have to reach the network for the shorter window to be able to shorten
  /// anything, and once a cooldown is armed the client refuses the next attempt before it sends —
  /// so a second *sequential* attempt could never carry a competing Retry-After. Overlapping calls
  /// are the only way the two windows race, which is exactly the reentrancy `armQuotaCooldown`
  /// guards: `complete` suspends at the request, letting a second call past the cooldown check
  /// before the first has armed anything.
  ///
  /// Held open deterministically rather than by hoping the two calls interleave: the stub parks
  /// every request until both are in flight, so both are guaranteed past the cooldown check before
  /// either response — and therefore either `armQuotaCooldown` — is delivered.
  func testLaterShorterRetryWindowDoesNotShortenActiveCooldown() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    // A long window (300s) and a much shorter one (60s), racing on the same operation.
    ProactiveLaneURLStub.enqueue(
      statusCode: 429, body: Data(), headers: ["Retry-After": "300"])
    ProactiveLaneURLStub.enqueue(
      statusCode: 429, body: Data(), headers: ["Retry-After": "60"])
    let bothInFlight = expectation(description: "both extraction attempts reached the network")
    ProactiveLaneURLStub.holdRequests(until: 2, reaching: bothInFlight)

    // Captures only the client, never the test case: an `async let` may not send a non-Sendable
    // XCTestCase across the concurrency boundary, so the outcomes come back as values.
    @Sendable func attemptExtraction() async -> Error? {
      do {
        _ = try await client.complete(
          operation: ModelQoS.Proactivity.extractionOperation,
          prompt: "extract",
          jsonSchema: ["type": "object"])
        return nil
      } catch {
        return error
      }
    }

    async let first = attemptExtraction()
    async let second = attemptExtraction()
    await fulfillment(of: [bothInFlight], timeout: 5)
    ProactiveLaneURLStub.releaseHeldRequests()
    for outcome in await [first, second] {
      guard case ProactiveLaneClientError.http(let status, _)? = outcome else {
        XCTFail("expected both overlapping attempts to see the server's 429, got \(String(describing: outcome))")
        continue
      }
      XCTAssertEqual(status, 429)
    }

    XCTAssertEqual(
      ProactiveLaneURLStub.requestCount, 2,
      "both overlapping attempts must have reached the network, or nothing raced")

    // Advance 70s — past the short window but inside the long one.
    clock.advance(by: 70)
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected quota cooldown — longer deadline must be preserved")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Still inside the 300s window the first response asked for.
    } catch {
      XCTFail("the shorter window won: extraction left cooldown early with \(error)")
    }

    XCTAssertEqual(
      ProactiveLaneURLStub.requestCount, 2,
      "the later shorter Retry-After must not have shortened the active cooldown")
  }

  private func complete(
    operation: String,
    prompt: String,
    on client: ProactiveLaneClient
  ) async throws -> ProactiveLaneResult {
    try await client.complete(
      operation: operation,
      prompt: prompt,
      jsonSchema: ["type": "object"])
  }

  private func successEnvelope(operation: String) throws -> Data {
    try JSONSerialization.data(withJSONObject: [
      "operation": operation,
      "lane": "omi:auto:desktop-\(operation.replacingOccurrences(of: "_", with: "-"))",
      "provider_model": "gpt-5.6-luna",
      "usage": ["cached_tokens": 0, "cache_write_tokens": 0],
      "cache_write": false,
      "fallback_class": "unknown",
      "response": ["choices": [["message": ["content": "{\"narrative\":\"ok\",\"facts\":[]}"]]]],
    ])
  }

  private func makeStubSession() -> URLSession {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ProactiveLaneURLStub.self]
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    return URLSession(configuration: configuration)
  }
}

private actor MirrorSyncProbe {
  private(set) var attempts = 0

  func record() {
    attempts += 1
  }
}

private actor ResponseObservationProbe {
  private(set) var value: ProactiveLaneResponseObservation?

  func set(_ value: ProactiveLaneResponseObservation) {
    self.value = value
  }
}

private final class ManualDateClock: @unchecked Sendable {
  private let lock = NSLock()
  private var date: Date

  init(_ date: Date) {
    self.date = date
  }

  var now: Date {
    lock.lock()
    defer { lock.unlock() }
    return date
  }

  func advance(by interval: TimeInterval) {
    lock.lock()
    date = date.addingTimeInterval(interval)
    lock.unlock()
  }
}

private final class ProactiveLaneURLStub: URLProtocol, @unchecked Sendable {
  struct StubResponse {
    let statusCode: Int
    let body: Data
    let headers: [String: String]
  }

  private static let lock = NSLock()
  private nonisolated(unsafe) static var responses: [StubResponse] = []
  private nonisolated(unsafe) static var served = 0
  private nonisolated(unsafe) static var operations: [String] = []
  private nonisolated(unsafe) static var paths: [String] = []
  /// How many requests must be in flight before any of them is answered, if the caller asked for
  /// that. Nil is the ordinary case: answer each request as it arrives.
  private nonisolated(unsafe) static var holdThreshold: Int?
  private nonisolated(unsafe) static var holdReached: XCTestExpectation?
  private nonisolated(unsafe) static var held: [() -> Void] = []

  static var requestCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return served
  }

  static var requestedOperations: [String] {
    lock.lock()
    defer { lock.unlock() }
    return operations
  }

  /// Request URL paths in issue order, for asserting which authority routes a
  /// caller actually reached.
  static var requestedPaths: [String] {
    lock.lock()
    defer { lock.unlock() }
    return paths
  }

  static func reset() {
    lock.lock()
    responses = []
    served = 0
    operations = []
    paths = []
    holdThreshold = nil
    holdReached = nil
    held = []
    lock.unlock()
  }

  /// Park every request instead of answering it until `count` of them have been issued, then
  /// fulfill `expectation`. This is a synchronisation point, not a wait: it makes "these calls
  /// overlapped" a fact the test establishes rather than one it hopes for.
  static func holdRequests(until count: Int, reaching expectation: XCTestExpectation) {
    lock.lock()
    holdThreshold = count
    holdReached = expectation
    held = []
    lock.unlock()
  }

  /// Answer everything parked by `holdRequests`, and stop parking.
  static func releaseHeldRequests() {
    lock.lock()
    let pending = held
    held = []
    holdThreshold = nil
    holdReached = nil
    lock.unlock()
    for deliver in pending { deliver() }
  }

  static func enqueue(statusCode: Int, body: Data, headers: [String: String] = [:]) {
    lock.lock()
    responses.append(StubResponse(statusCode: statusCode, body: body, headers: headers))
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    let operation = Self.operation(from: request)
    Self.lock.lock()
    Self.operations.append(operation)
    Self.paths.append(url.path)
    let stub = Self.responses.isEmpty ? nil : Self.responses.removeFirst()
    Self.served += 1
    let deliver = { self.deliver(stub, for: url) }
    let isHeld = Self.holdThreshold != nil
    if isHeld { Self.held.append(deliver) }
    let reached = Self.holdThreshold.map { Self.served >= $0 } ?? false
    let holdReached = reached ? Self.holdReached : nil
    if reached { Self.holdReached = nil }
    Self.lock.unlock()

    holdReached?.fulfill()
    if !isHeld { deliver() }
  }

  private func deliver(_ stub: StubResponse?, for url: URL) {
    guard let stub else {
      client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
      return
    }
    guard
      let response = HTTPURLResponse(
        url: url, statusCode: stub.statusCode, httpVersion: nil, headerFields: stub.headers)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: stub.body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func operation(from request: URLRequest) -> String {
    guard let data = bodyData(from: request),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let operation = object["operation"] as? String
    else { return "" }
    return operation
  }

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let count = stream.read(buffer, maxLength: 4_096)
      guard count > 0 else { break }
      data.append(buffer, count: count)
    }
    return data.isEmpty ? nil : data
  }
}
