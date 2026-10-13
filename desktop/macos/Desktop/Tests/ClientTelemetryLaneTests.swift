import Foundation
import XCTest

@testable import Omi_Computer

#if DEBUG
  extension DesktopDiagnosticsManagerTests {
    func testTelemetryFlagsStayOffAndDoNotRetireHealthEvents() throws {
      XCTAssertFalse(ClientTelemetryFlags.transportShadowEnabled)
      XCTAssertFalse(ClientTelemetryFlags.postHogRetirementEnabled)
      XCTAssertFalse(ClientTelemetryFlags.retiresInfrastructurePostHog)
      ClientTelemetryFlags.setPostHogRetirementForTests(true)
      XCTAssertTrue(ClientTelemetryFlags.postHogRetirementEnabled)
      XCTAssertFalse(ClientTelemetryFlags.retiresInfrastructurePostHog)

      DesktopDiagnosticsManager.shared.recordVoiceTurnTerminal(
        turnID: UUID().uuidString,
        reason: "success",
        route: "hub",
        intent: "hold",
        durationMs: 1_000,
        answerDelivered: true,
        staleEventCount: 0,
        invalidTransitionCount: 0)
      let snapshot = try telemetrySnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "voice_turn_terminal")
    }

    func testVoiceAndFallbackShadowKeepsPostHogAndExactPopulations() throws {
      ClientTelemetryFlags.setTransportShadowForTests(true)
      ClientTelemetryFlags.setChannelForTests("production")
      ClientTelemetryIdentity.setOwnerForTests { "owner-physical" }
      let box = TelemetryObservationBox()
      ClientTelemetryShadow.setRecorderForTests { box.append($0) }

      let physical = UUID()
      DesktopDiagnosticsManager.shared.recordVoiceTurnStarted(turnID: physical.uuidString, intent: "hold")
      DesktopDiagnosticsManager.shared.recordVoiceTurnTerminal(
        turnID: physical.uuidString,
        reason: "success",
        route: "hub",
        intent: "hold",
        durationMs: 4_200,
        answerDelivered: true,
        staleEventCount: 0,
        invalidTransitionCount: 0)
      DesktopDiagnosticsManager.shared.recordVoiceTurnTerminal(
        turnID: UUID().uuidString,
        reason: "too_short",
        route: "hub",
        intent: "locked",
        durationMs: 100,
        answerDelivered: false,
        staleEventCount: 0,
        invalidTransitionCount: 0)
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "brand_new_area",
        from: "Cloud Tasks!",
        to: "",
        reason: "totally_novel_failure",
        outcome: .degraded)
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: "openai",
        to: "gemini",
        reason: "auth",
        outcome: .recovered)

      let snapshot = try telemetrySnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
      XCTAssertEqual(snapshot["area"] as? String, "realtime_hub")
      XCTAssertEqual(snapshot["reason"] as? String, "auth")

      let voice = box.items.filter { $0.family == "voice_turn" }
      XCTAssertEqual(voice.filter { $0.attributes["population"] == .string("physical_shortcut") }.count, 3)
      XCTAssertEqual(voice.filter { $0.attributes["population"] == .string("floating_voice") }.count, 0)
      let success = try XCTUnwrap(voice.first { $0.attributes["outcome"] == .string("success") })
      XCTAssertEqual(success.attributes["latency_ms"], .int(4_200))
      XCTAssertEqual(success.attributes["route"], .string("hub"))
      let excluded = try XCTUnwrap(voice.first { $0.attributes["outcome"] == .string("excluded") })
      XCTAssertNil(excluded.attributes["latency_ms"])
      let started = try XCTUnwrap(voice.first { $0.attributes["phase"] == .string("started") })
      XCTAssertEqual(started.attributes["operation_id"], success.attributes["operation_id"])

      let novel = try XCTUnwrap(
        box.items.first { $0.family == "fallback" && $0.attributes["area"] == .string("other") })
      XCTAssertEqual(novel.attributes["reason"], .string("unknown"))
      XCTAssertEqual(novel.attributes["from"], .string("unknown"))
      XCTAssertEqual(novel.attributes["to"], .string("unknown"))
      XCTAssertEqual(novel.attributes["outcome"], .string("degraded"))
      let known = try XCTUnwrap(
        box.items.first { $0.family == "fallback" && $0.attributes["area"] == .string("realtime_hub") })
      XCTAssertEqual(known.attributes["from"], .string("openai"))
      XCTAssertEqual(known.attributes["to"], .string("gemini"))
      XCTAssertEqual(known.attributes["reason"], .string("auth"))
      XCTAssertEqual(known.attributes["outcome"], .string("recovered"))
    }

    func testFloatingVoiceShadowStaysDistinctFromPhysical() {
      _ = ChatQueryTelemetryEvent.started(floatingContext(attempt: "33333333-3333-3333-3333-333333333333"))
      let completed = ChatQueryTelemetryEvent.completed(
        floatingContext(attempt: "33333333-3333-3333-3333-333333333333"),
        durationMs: 1_800,
        metrics: emptyChatMetrics())
      let failed = ChatQueryTelemetryEvent.failed(
        floatingContext(attempt: "44444444-4444-4444-4444-444444444444"),
        durationMs: 50,
        errorClass: .timeout,
        partialResponse: false,
        detail: nil)
      let mainChat = ChatQueryTelemetryEvent.started(
        ChatQueryTelemetryContext(attemptId: UUID().uuidString, surface: "main_chat", harness: "test"))
      let owner = "owner-float"
      let channel = "beta"
      let startedObservation = ClientTelemetryShadow.voiceObservation(
        ownerID: owner,
        channel: channel,
        population: "floating_voice",
        phase: "started",
        operationRaw: "33333333-3333-3333-3333-333333333333",
        intent: "legacy",
        route: "floating_voice",
        reason: nil,
        durationMs: nil,
        outcome: nil)
      let completedObservation = ClientTelemetryShadow.captureMapping(completed, ownerID: owner, channel: channel)
      let failedObservation = ClientTelemetryShadow.captureMapping(failed, ownerID: owner, channel: channel)
      XCTAssertNil(ClientTelemetryShadow.captureMapping(mainChat, ownerID: owner, channel: channel))
      XCTAssertEqual(startedObservation?.attributes["population"], .string("floating_voice"))
      XCTAssertEqual(completedObservation?.attributes["population"], .string("floating_voice"))
      XCTAssertEqual(completedObservation?.attributes["latency_ms"], .int(1_800))
      XCTAssertEqual(completedObservation?.attributes["operation_id"], startedObservation?.attributes["operation_id"])
      XCTAssertEqual(failedObservation?.attributes["outcome"], .string("failure"))
      XCTAssertEqual(failedObservation?.attributes["reason"], .string("timeout"))
      XCTAssertNil(failedObservation?.attributes["latency_ms"])
      XCTAssertNotEqual(failedObservation?.attributes["operation_id"], startedObservation?.attributes["operation_id"])
    }

    func testTelemetryDedupRetryOverflowAndAuthSwap() async throws {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: directory) }
      let now = Date(timeIntervalSince1970: 1_760_227_200)
      let script = TelemetryScript()
      let sleeps = TelemetrySleepLog()
      let limits = ClientTelemetryLimits.production
      let transport = telemetryTransport(
        directory: directory, limits: limits, script: script, sleeps: sleeps, now: now, jitter: 0.5)

      let eventID = UUID()
      let observation = telemetryObservation(ownerID: "owner-a", eventID: eventID, enqueuedAt: now)
      await transport.enqueue(observation)
      await transport.enqueue(observation)
      let pending = await transport.pending(ownerID: "owner-a")
      XCTAssertEqual(pending.count, 1)
      XCTAssertEqual(pending.first?.eventID, eventID)

      script.steps = [.network, .success(1, 0)]
      await transport.flush()
      let requests = script.snapshotRequests()
      XCTAssertEqual(requests.count, 2)
      guard requests.count == 2 else { return }
      XCTAssertEqual(requests[0].batchID, requests[1].batchID)
      XCTAssertEqual(requests[0].timeout, 10)
      XCTAssertEqual(requests[0].url.path, "/v1/telemetry/client/batches")
      XCTAssertEqual(requests.map(\.token), ["token-a", "token-a"])
      let firstBody = try XCTUnwrap(String(data: requests[0].body, encoding: .utf8))
      let secondBody = try XCTUnwrap(String(data: requests[1].body, encoding: .utf8))
      XCTAssertTrue(firstBody.contains(eventID.uuidString.lowercased()))
      XCTAssertEqual(firstBody, secondBody)
      XCTAssertFalse(firstBody.contains("owner-a"))
      XCTAssertFalse(firstBody.contains("token-a"))
      XCTAssertEqual(sleeps.snapshot(), [1])
      let pendingAfterFlush = await transport.pending(ownerID: "owner-a")
      XCTAssertTrue(pendingAfterFlush.isEmpty)

      let parkedDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: parkedDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: parkedDirectory) }
      let parkedScript = TelemetryScript()
      parkedScript.steps = [.status(429, 301)]
      let parked = telemetryTransport(
        directory: parkedDirectory, limits: limits, script: parkedScript, sleeps: TelemetrySleepLog(), now: now,
        jitter: 0)
      let parkedID = UUID()
      await parked.enqueue(telemetryObservation(ownerID: "owner-a", eventID: parkedID, enqueuedAt: now))
      await parked.flush()
      let parkedAttempts = await parked.pending(ownerID: "owner-a").first?.attemptCount
      XCTAssertEqual(parkedAttempts, 1)
      XCTAssertEqual(parkedScript.snapshotRequests().count, 1)
      let restartedScript = TelemetryScript()
      restartedScript.steps = [.success(0, 1)]
      let restarted = telemetryTransport(
        directory: parkedDirectory,
        limits: limits,
        script: restartedScript,
        sleeps: TelemetrySleepLog(),
        now: now,
        jitter: 0)
      let restartedAttempts = await restarted.pending(ownerID: "owner-a").first?.attemptCount
      XCTAssertEqual(restartedAttempts, 1)
      await restarted.flush()
      let restartedRequests = restartedScript.snapshotRequests()
      guard !restartedRequests.isEmpty else { return }
      let restartedBody = try XCTUnwrap(String(data: restartedRequests[0].body, encoding: .utf8))
      XCTAssertTrue(restartedBody.contains(parkedID.uuidString.lowercased()))
      let restartedPending = await restarted.pending(ownerID: "owner-a")
      XCTAssertTrue(restartedPending.isEmpty)

      var tight = ClientTelemetryLimits.production
      tight.maxOutboxObservations = 2
      let overflowDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: overflowDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: overflowDirectory) }
      let overflow = telemetryTransport(
        directory: overflowDirectory,
        limits: tight,
        script: TelemetryScript(),
        sleeps: TelemetrySleepLog(),
        now: now,
        jitter: 0)
      let oldest = UUID(uuidString: "00000000-0000-0000-0000-000000000001") ?? UUID()
      let middle = UUID(uuidString: "00000000-0000-0000-0000-000000000002") ?? UUID()
      let newest = UUID(uuidString: "00000000-0000-0000-0000-000000000003") ?? UUID()
      await overflow.enqueue(telemetryObservation(ownerID: "owner-a", eventID: oldest, enqueuedAt: now))
      await overflow.enqueue(
        telemetryObservation(ownerID: "owner-a", eventID: middle, enqueuedAt: now.addingTimeInterval(1)))
      await overflow.enqueue(
        telemetryObservation(ownerID: "owner-a", eventID: newest, enqueuedAt: now.addingTimeInterval(2)))
      let kept = await overflow.pending(ownerID: "owner-a").map(\.eventID)
      XCTAssertEqual(kept, [middle, newest])
      let drops = await overflow.dropCounts()
      XCTAssertEqual(drops.overflowCount, 1)

      let sample = telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now)
      var byteLimits = ClientTelemetryLimits.production
      byteLimits.maxOutboxBytes = sample.encodedObservationBytes()
      let byteDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: byteDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: byteDirectory) }
      let byteTransport = telemetryTransport(
        directory: byteDirectory, limits: byteLimits, script: TelemetryScript(), sleeps: TelemetrySleepLog(), now: now,
        jitter: 0)
      await byteTransport.enqueue(sample)
      await byteTransport.enqueue(
        telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now.addingTimeInterval(1)))
      let bytePendingCount = await byteTransport.pending(ownerID: "owner-a").count
      let byteOverflowBytes = await byteTransport.dropCounts().overflowBytes
      XCTAssertEqual(bytePendingCount, 1)
      XCTAssertGreaterThan(byteOverflowBytes, 0)

      let swapDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: swapDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: swapDirectory) }
      let swap = TelemetryScript()
      let swapTransport = telemetryTransport(
        directory: swapDirectory, limits: limits, script: swap, sleeps: TelemetrySleepLog(), now: now, jitter: 0)
      await swapTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now))
      swap.setOwner("owner-b")
      swap.setToken("owner-b", "token-b")
      swap.steps = [.success(1, 0)]
      await swapTransport.flush()
      XCTAssertTrue(swap.snapshotRequests().isEmpty)
      let swapPendingBeforePurge = await swapTransport.pending(ownerID: "owner-a").count
      XCTAssertEqual(swapPendingBeforePurge, 1)
      await swapTransport.purgeOwner("owner-a")
      let swapPendingAfterPurge = await swapTransport.pending(ownerID: "owner-a")
      XCTAssertTrue(swapPendingAfterPurge.isEmpty)
      await swapTransport.enqueue(telemetryObservation(ownerID: "owner-b", eventID: UUID(), enqueuedAt: now))
      await swapTransport.flush()
      let swapRequest = try XCTUnwrap(swap.snapshotRequests().first)
      XCTAssertEqual(swapRequest.token, "token-b")
      let swapBody = try XCTUnwrap(String(data: swapRequest.body, encoding: .utf8))
      XCTAssertFalse(swapBody.contains("owner-a"))
      XCTAssertFalse(swapBody.contains("owner-b"))

      let refresh = TelemetryScript()
      refresh.steps = [.status(401, nil), .success(1, 0)]
      refresh.refreshedToken = "token-a2"
      let refreshDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: refreshDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: refreshDirectory) }
      let refreshTransport = telemetryTransport(
        directory: refreshDirectory, limits: limits, script: refresh, sleeps: TelemetrySleepLog(), now: now, jitter: 0)
      await refreshTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now))
      await refreshTransport.flush()
      XCTAssertEqual(refresh.refreshCount, 1)
      XCTAssertEqual(refresh.snapshotRequests().map(\.token), ["token-a", "token-a2"])

      let hijack = TelemetryScript()
      hijack.swapOwnerOnRefresh = "owner-b"
      hijack.setToken("owner-b", "token-b")
      hijack.steps = [.status(401, nil), .success(1, 0)]
      let hijackDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: hijackDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: hijackDirectory) }
      let hijackTransport = telemetryTransport(
        directory: hijackDirectory, limits: limits, script: hijack, sleeps: TelemetrySleepLog(), now: now, jitter: 0)
      await hijackTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now))
      await hijackTransport.flush()
      XCTAssertEqual(hijack.snapshotRequests().map(\.token), ["token-a"])
      let hijackUnauthorized = await hijackTransport.dropCounts().unauthorized
      let hijackPending = await hijackTransport.pending(ownerID: "owner-a")
      XCTAssertEqual(hijackUnauthorized, 1)
      XCTAssertTrue(hijackPending.isEmpty)

      let permanent = TelemetryScript()
      permanent.steps = [.status(422, nil)]
      let permanentDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: permanentDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: permanentDirectory) }
      let permanentTransport = telemetryTransport(
        directory: permanentDirectory, limits: limits, script: permanent, sleeps: TelemetrySleepLog(), now: now,
        jitter: 0)
      await permanentTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now))
      await permanentTransport.flush()
      XCTAssertEqual(permanent.snapshotRequests().count, 1)
      let permanentDrops = await permanentTransport.dropCounts().permanent
      XCTAssertEqual(permanentDrops, 1)

      let conflict = TelemetryScript()
      conflict.steps = [.status(409, nil)]
      let conflictDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: conflictDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: conflictDirectory) }
      let conflictTransport = telemetryTransport(
        directory: conflictDirectory, limits: limits, script: conflict, sleeps: TelemetrySleepLog(), now: now, jitter: 0
      )
      await conflictTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now))
      await conflictTransport.flush()
      let conflictDrops = await conflictTransport.dropCounts().conflict
      XCTAssertEqual(conflictDrops, 1)
      XCTAssertEqual(conflict.snapshotRequests().count, 1)

      let exhaustedSleeps = TelemetrySleepLog()
      let exhausted = TelemetryScript()
      exhausted.steps = Array(repeating: .network, count: 6)
      let exhaustedDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: exhaustedDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: exhaustedDirectory) }
      let exhaustedTransport = telemetryTransport(
        directory: exhaustedDirectory, limits: limits, script: exhausted, sleeps: exhaustedSleeps, now: now, jitter: 0)
      let exhaustedID = UUID()
      await exhaustedTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: exhaustedID, enqueuedAt: now))
      await exhaustedTransport.flush()
      XCTAssertEqual(exhausted.snapshotRequests().count, 5)
      let exhaustedDrops = await exhaustedTransport.dropCounts().exhausted
      XCTAssertEqual(exhaustedDrops, 1)
      XCTAssertEqual(
        Set(exhausted.snapshotRequests().map { String(data: $0.body, encoding: .utf8) ?? "" }),
        [String(data: exhausted.snapshotRequests().first?.body ?? Data(), encoding: .utf8) ?? ""])

      let stale = telemetryTransport(
        directory: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true),
        limits: limits, script: TelemetryScript(), sleeps: TelemetrySleepLog(), now: now, jitter: 0)
      var staleObservation = telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now)
      staleObservation.occurredAt = now.addingTimeInterval(-(25 * 60 * 60))
      await stale.enqueue(staleObservation)
      let stalePending = await stale.pending(ownerID: "owner-a")
      let staleTtlDrops = await stale.dropCounts().ttl
      XCTAssertTrue(stalePending.isEmpty)
      XCTAssertEqual(staleTtlDrops, 1)

      let honored = TelemetryScript()
      honored.steps = [.status(429, 2), .success(1, 0)]
      let honoredSleeps = TelemetrySleepLog()
      let honoredDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: honoredDirectory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: honoredDirectory) }
      let honoredTransport = telemetryTransport(
        directory: honoredDirectory, limits: limits, script: honored, sleeps: honoredSleeps, now: now, jitter: 1)
      await honoredTransport.enqueue(telemetryObservation(ownerID: "owner-a", eventID: UUID(), enqueuedAt: now))
      await honoredTransport.flush()
      XCTAssertEqual(honoredSleeps.snapshot(), [2])
      let honoredPending = await honoredTransport.pending(ownerID: "owner-a")
      XCTAssertTrue(honoredPending.isEmpty)
    }

    func testLane3ParityFixtureMatchesVoiceFallbackAndScreenPopulations() throws {
      let observations = lane3FixtureObservations()
      let receipt = ClientTelemetryParity.receipt(observations: observations)
      let fixtureURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("docs/finops/lane3-parity-fixture.json")
      let data = try Data(contentsOf: fixtureURL)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let acceptance = try XCTUnwrap(root["acceptance"] as? [String: Any])
      XCTAssertEqual(acceptance["live_canary"] as? String, "pending")
      XCTAssertEqual(acceptance["lane4_voice_panel"] as? String, "pending")
      XCTAssertEqual(acceptance["lane4_fallback_triage"] as? String, "pending")
      XCTAssertEqual(acceptance["transport_shadow_flag"] as? String, "default_off")
      XCTAssertEqual(acceptance["desktop_health_event"] as? String, "retained")
      XCTAssertEqual(acceptance["device_disconnected"] as? String, "retained")
      let measured = try XCTUnwrap(root["measured"] as? [String: Any])
      XCTAssertTrue(telemetryJSONEqual(receipt, measured))

      let encoded = try XCTUnwrap(ClientTelemetryCodec.batchData(batchID: UUID(), observations: observations))
      let body = try XCTUnwrap(String(data: encoded, encoding: .utf8))
      XCTAssertFalse(body.contains("owner-fixture"))
      XCTAssertFalse(body.contains("@"))
      let physical = observations.filter { $0.attributes["population"] == .string("physical_shortcut") }
      let floating = observations.filter { $0.attributes["population"] == .string("floating_voice") }
      XCTAssertEqual(physical.count, 4)
      XCTAssertEqual(floating.count, 4)
      XCTAssertTrue(physical.allSatisfy { $0.attributes["population"] == .string("physical_shortcut") })
      XCTAssertTrue(floating.allSatisfy { $0.attributes["population"] == .string("floating_voice") })
    }

    private func telemetrySnapshot() throws -> [String: Any] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return try XCTUnwrap(snapshots.last)
    }
  }
#endif

extension ScreenTaskPipelineTests {
  func testScreenTaskTerminalsKeepExactDenominatorsAndDoNotRewriteEarlierFrames() throws {
    let occurredAt = Date(timeIntervalSince1970: 1_760_227_200)
    let completed = Self.screenMetrics(
      outcome: "completed",
      gateOutcome: "passed",
      extractor: "gemini_3_8",
      errorClass: "none",
      eligible: 1,
      gateAttempts: 1,
      extractionAttempts: 1,
      policyRejected: 0,
      pendingDelivered: 1,
      failed: 0,
      ocr: 100,
      retrieval: 200,
      gate: 50,
      extraction: 800,
      delivery: 40,
      capture: 1_500)
    let rejected = Self.screenMetrics(
      outcome: "gate_rejected",
      gateOutcome: "rejected",
      extractor: "none",
      errorClass: "none",
      eligible: 1,
      gateAttempts: 1,
      extractionAttempts: 0,
      policyRejected: 1,
      pendingDelivered: 0,
      failed: 0,
      ocr: 80,
      retrieval: 20,
      gate: 30,
      extraction: 0,
      delivery: 0,
      capture: 400)
    let preUpload = Self.screenMetrics(
      outcome: "failed",
      gateOutcome: "none",
      extractor: "none",
      errorClass: "auth",
      eligible: 1,
      gateAttempts: 0,
      extractionAttempts: 0,
      policyRejected: 0,
      pendingDelivered: 0,
      failed: 1,
      ocr: 0,
      retrieval: 0,
      gate: 0,
      extraction: 0,
      delivery: 0,
      capture: 90)
    let observations = [completed, rejected, preUpload].map { properties in
      ClientTelemetryShadow.screenTaskObservation(
        ownerID: "owner-fixture",
        properties: properties,
        occurredAt: occurredAt,
        channel: "production")
    }
    let mapped = try observations.map { try XCTUnwrap($0) }
    let section = try XCTUnwrap(ClientTelemetryParity.receipt(observations: mapped)["screen_task"] as? [String: Any])
    XCTAssertEqual(section["terminals"] as? Int, 3)
    XCTAssertEqual(section["eligible_frames"] as? Int, 3)
    XCTAssertEqual(section["rejected"] as? Int, 1)
    XCTAssertEqual(section["pre_upload_failed"] as? Int, 1)
    XCTAssertEqual(section["policy_rejected"] as? Int, 1)
    let durations = try XCTUnwrap(section["durations"] as? [String: Any])
    let extraction = try XCTUnwrap(durations["extraction_ms"] as? [String: Any])
    XCTAssertEqual(extraction["count"] as? Int, 1)
    XCTAssertEqual(extraction["sum_ms"] as? Int, 800)
    XCTAssertEqual(mapped[1].attributes["extraction_ms"], .int(0))
    XCTAssertEqual(mapped[2].attributes["eligible_frames"], .int(1))
    XCTAssertEqual(mapped[2].attributes["failed"], .int(1))
    XCTAssertEqual(mapped[0].attributes["schema_version"], .int(2))
    XCTAssertEqual(mapped[0].attributes["pipeline"], .string("screen_task_v2"))

    var rewritten = completed
    rewritten["pending_delivered"] = 9
    let rewrittenObservation = ClientTelemetryShadow.screenTaskObservation(
      ownerID: "owner-fixture", properties: rewritten, occurredAt: occurredAt, channel: "production")
    XCTAssertEqual(mapped[0].attributes["pending_delivered"], .int(1))
    XCTAssertEqual(rewrittenObservation?.attributes["pending_delivered"], .int(9))
    XCTAssertNotEqual(mapped[0].eventID, rewrittenObservation?.eventID)
  }

  fileprivate static func screenMetrics(
    outcome: String,
    gateOutcome: String,
    extractor: String,
    errorClass: String,
    eligible: Int,
    gateAttempts: Int,
    extractionAttempts: Int,
    policyRejected: Int,
    pendingDelivered: Int,
    failed: Int,
    ocr: Double,
    retrieval: Double,
    gate: Double,
    extraction: Double,
    delivery: Double,
    capture: Double
  ) -> [String: Any] {
    let metrics = ScreenTaskFrameMetrics()
    metrics.eligibleFrames = eligible
    metrics.featureEnabledAtStart = true
    metrics.pipeline = "screen_task_v2"
    metrics.gateOutcome = gateOutcome
    metrics.extractor = extractor
    metrics.outcome = outcome
    metrics.errorClass = errorClass
    metrics.fallbackReason = "none"
    metrics.gateAttempts = gateAttempts
    metrics.extractionAttempts = extractionAttempts
    metrics.ocrMS = ocr
    metrics.retrievalMS = retrieval
    metrics.gateMS = gate
    metrics.extractionMS = extraction
    metrics.deliveryMS = delivery
    metrics.counts.policyRejected = policyRejected
    metrics.counts.pendingDelivered = pendingDelivered
    metrics.counts.failed = failed
    return metrics.properties(captureToTerminalMS: capture)
  }
}

extension ClientTelemetryShadow {
  fileprivate static func captureMapping(
    _ event: ChatQueryTelemetryEvent, ownerID: String, channel: String
  ) -> ClientTelemetryObservation? {
    switch event {
    case .started(let context):
      guard context.surface == "floating_voice" else { return nil }
      return voiceObservation(
        ownerID: ownerID, channel: channel, population: "floating_voice", phase: "started",
        operationRaw: context.attemptId, intent: "legacy", route: "floating_voice", reason: nil, durationMs: nil,
        outcome: nil)
    case .completed(let context, let durationMs, _):
      guard context.surface == "floating_voice" else { return nil }
      return voiceObservation(
        ownerID: ownerID, channel: channel, population: "floating_voice", phase: "terminal",
        operationRaw: context.attemptId, intent: "legacy", route: "floating_voice", reason: nil, durationMs: durationMs,
        outcome: "success")
    case .failed(let context, let durationMs, let errorClass, _, _, _):
      guard context.surface == "floating_voice" else { return nil }
      return voiceObservation(
        ownerID: ownerID, channel: channel, population: "floating_voice", phase: "terminal",
        operationRaw: context.attemptId, intent: "legacy", route: "floating_voice", reason: errorClass.rawValue,
        durationMs: durationMs, outcome: "failure")
    case .cancelled(let context, let durationMs, let reason, _):
      guard context.surface == "floating_voice" else { return nil }
      return voiceObservation(
        ownerID: ownerID, channel: channel, population: "floating_voice", phase: "terminal",
        operationRaw: context.attemptId, intent: "legacy", route: "floating_voice", reason: reason.rawValue,
        durationMs: durationMs, outcome: "excluded")
    }
  }
}

private func lane3FixtureObservations() -> [ClientTelemetryObservation] {
  let occurredAt = Date(timeIntervalSince1970: 1_760_227_200)
  let owner = "owner-fixture"
  let channel = "production"
  func voice(
    population: String, phase: String, operation: String, intent: String, route: String, reason: String?,
    duration: Int?, outcome: String?
  ) -> ClientTelemetryObservation {
    let observation = ClientTelemetryShadow.voiceObservation(
      ownerID: owner, channel: channel, population: population, phase: phase, operationRaw: operation,
      intent: intent, route: route, reason: reason, durationMs: duration, outcome: outcome,
      occurredAt: occurredAt)
    return observation
      ?? ClientTelemetryObservation(
        eventID: UUID(),
        occurredAt: occurredAt,
        platform: "macos",
        channel: channel,
        family: "voice_turn",
        attributes: [
          "operation_id": .string(operation),
          "phase": .string(phase),
          "population": .string(population),
          "route": .string(route),
          "intent": .string(intent),
        ],
        ownerID: owner,
        enqueuedAt: occurredAt,
        attemptCount: 0
      )
  }
  let physicalA = "11111111-1111-1111-1111-111111111111"
  let physicalB = "22222222-2222-2222-2222-222222222222"
  let floatingA = "33333333-3333-3333-3333-333333333333"
  let floatingB = "44444444-4444-4444-4444-444444444444"
  let screen = ScreenTaskPipelineTests.screenTerminalsForFixture(occurredAt: occurredAt)
  return [
    voice(
      population: "physical_shortcut", phase: "started", operation: physicalA, intent: "hold", route: "unknown",
      reason: nil, duration: nil, outcome: nil),
    voice(
      population: "physical_shortcut", phase: "terminal", operation: physicalA, intent: "hold", route: "hub",
      reason: "success", duration: 4_200, outcome: "success"),
    voice(
      population: "physical_shortcut", phase: "started", operation: physicalB, intent: "locked", route: "unknown",
      reason: nil, duration: nil, outcome: nil),
    voice(
      population: "physical_shortcut", phase: "terminal", operation: physicalB, intent: "locked", route: "hub",
      reason: "too_short", duration: 100, outcome: "excluded"),
    voice(
      population: "floating_voice", phase: "started", operation: floatingA, intent: "legacy", route: "floating_voice",
      reason: nil, duration: nil, outcome: nil),
    voice(
      population: "floating_voice", phase: "terminal", operation: floatingA, intent: "legacy", route: "floating_voice",
      reason: nil, duration: 1_800, outcome: "success"),
    voice(
      population: "floating_voice", phase: "started", operation: floatingB, intent: "legacy", route: "floating_voice",
      reason: nil, duration: nil, outcome: nil),
    voice(
      population: "floating_voice", phase: "terminal", operation: floatingB, intent: "legacy", route: "floating_voice",
      reason: "timeout", duration: 50, outcome: "failure"),
    fallbackObservation(area: "realtime_hub", from: "openai", to: "gemini", reason: "auth", outcome: "recovered"),
    fallbackObservation(
      area: "screen_task_gate", from: "jev", to: "gemini_3_8", reason: "ocr_unusable", outcome: "degraded"),
    fallbackObservation(area: "ptt_cascade", from: "primary", to: "none", reason: "timeout", outcome: "exhausted"),
  ] + screen
}

private func fallbackObservation(
  area: String, from: String, to: String, reason: String, outcome: String
) -> ClientTelemetryObservation {
  ClientTelemetryObservation(
    eventID: UUID(),
    occurredAt: Date(timeIntervalSince1970: 1_760_227_200),
    platform: "macos",
    channel: "production",
    family: "fallback",
    attributes: [
      "area": .string(area),
      "from": .string(from),
      "operation_id": .string(UUID().uuidString.lowercased()),
      "outcome": .string(outcome),
      "reason": .string(reason),
      "to": .string(to),
    ],
    ownerID: "owner-fixture",
    enqueuedAt: Date(timeIntervalSince1970: 1_760_227_200),
    attemptCount: 0)
}

extension ScreenTaskPipelineTests {
  fileprivate static func screenTerminalsForFixture(occurredAt: Date) -> [ClientTelemetryObservation] {
    let completed = screenMetrics(
      outcome: "completed", gateOutcome: "passed", extractor: "gemini_3_8", errorClass: "none", eligible: 1,
      gateAttempts: 1, extractionAttempts: 1, policyRejected: 0, pendingDelivered: 1, failed: 0, ocr: 100,
      retrieval: 200, gate: 50, extraction: 800, delivery: 40, capture: 1_500)
    let rejected = screenMetrics(
      outcome: "gate_rejected", gateOutcome: "rejected", extractor: "none", errorClass: "none", eligible: 1,
      gateAttempts: 1, extractionAttempts: 0, policyRejected: 1, pendingDelivered: 0, failed: 0, ocr: 80,
      retrieval: 20, gate: 30, extraction: 0, delivery: 0, capture: 400)
    let preUpload = screenMetrics(
      outcome: "failed", gateOutcome: "none", extractor: "none", errorClass: "auth", eligible: 1, gateAttempts: 0,
      extractionAttempts: 0, policyRejected: 0, pendingDelivered: 0, failed: 1, ocr: 0, retrieval: 0, gate: 0,
      extraction: 0, delivery: 0, capture: 90)
    return [completed, rejected, preUpload].compactMap {
      ClientTelemetryShadow.screenTaskObservation(
        ownerID: "owner-fixture", properties: $0, occurredAt: occurredAt, channel: "production")
    }
  }
}

private func telemetryObservation(ownerID: String, eventID: UUID, enqueuedAt: Date) -> ClientTelemetryObservation {
  ClientTelemetryObservation(
    eventID: eventID,
    occurredAt: enqueuedAt,
    platform: "macos",
    channel: "production",
    family: "fallback",
    attributes: [
      "area": .string("realtime_hub"),
      "from": .string("openai"),
      "operation_id": .string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
      "outcome": .string("recovered"),
      "reason": .string("auth"),
      "to": .string("gemini"),
    ],
    ownerID: ownerID,
    enqueuedAt: enqueuedAt,
    attemptCount: 0)
}

private func telemetryTransport(
  directory: URL,
  limits: ClientTelemetryLimits,
  script: TelemetryScript,
  sleeps: TelemetrySleepLog,
  now: Date,
  jitter: Double
) -> ClientTelemetryTransport {
  let dependencies = ClientTelemetryDependencies(
    now: { now },
    sleep: { seconds in sleeps.record(seconds) },
    jitterUnit: { jitter },
    currentOwnerID: { script.currentOwner() },
    token: { ownerID, force in script.token(ownerID: ownerID, force: force) },
    endpointBaseURL: { "https://collector.test" },
    send: { request in script.send(request) },
    automaticFlush: false)
  return ClientTelemetryTransport(directory: directory, limits: limits, dependencies: dependencies)
}

private func floatingContext(attempt: String) -> ChatQueryTelemetryContext {
  ChatQueryTelemetryContext(attemptId: attempt, surface: "floating_voice", harness: "test")
}

private func emptyChatMetrics() -> ChatQueryCompletionMetrics {
  ChatQueryCompletionMetrics(
    toolCallCount: 0, toolNames: [], costUsd: 0, responseLength: 0, screenToolRequested: false,
    screenToolSucceeded: false, screenToolApprovalRequired: false, screenToolFailureCodes: [])
}

private final class TelemetryObservationBox: @unchecked Sendable {
  private let lock = NSLock()
  private var storage: [ClientTelemetryObservation] = []
  func append(_ observation: ClientTelemetryObservation) {
    lock.lock()
    storage.append(observation)
    lock.unlock()
  }
  var items: [ClientTelemetryObservation] {
    lock.lock()
    defer { lock.unlock() }
    return storage
  }
}

private final class TelemetrySleepLog: @unchecked Sendable {
  private let lock = NSLock()
  private var intervals: [TimeInterval] = []
  func record(_ seconds: TimeInterval) {
    lock.lock()
    intervals.append(seconds)
    lock.unlock()
  }
  func snapshot() -> [TimeInterval] {
    lock.lock()
    defer { lock.unlock() }
    return intervals
  }
}

private final class TelemetryScript: @unchecked Sendable {
  private let lock = NSLock()
  private var owner = "owner-a"
  private var tokens = ["owner-a": "token-a"]
  var refreshedToken = "token-refreshed"
  var swapOwnerOnRefresh: String?
  private(set) var refreshCount = 0
  var steps: [Step] = []
  private var requests: [ClientTelemetryRequest] = []

  enum Step {
    case status(Int, TimeInterval?)
    case network
    case timeout
    case success(Int, Int)
  }

  func setOwner(_ owner: String) {
    lock.lock()
    self.owner = owner
    lock.unlock()
  }

  func setToken(_ owner: String, _ token: String) {
    lock.lock()
    tokens[owner] = token
    lock.unlock()
  }

  func currentOwner() -> String {
    lock.lock()
    defer { lock.unlock() }
    return owner
  }

  func token(ownerID: String, force: Bool) -> String? {
    lock.lock()
    defer { lock.unlock() }
    if force {
      refreshCount += 1
      if let swapOwnerOnRefresh {
        owner = swapOwnerOnRefresh
        return tokens[swapOwnerOnRefresh]
      }
      tokens[ownerID] = refreshedToken
    }
    guard owner == ownerID else { return nil }
    return tokens[ownerID]
  }

  func send(_ request: ClientTelemetryRequest) -> ClientTelemetryHTTPResult {
    lock.lock()
    requests.append(request)
    let step = steps.isEmpty ? Step.network : steps.removeFirst()
    lock.unlock()
    switch step {
    case .status(let status, let retryAfter):
      return .response(status: status, retryAfter: retryAfter, body: Data("{}".utf8))
    case .network:
      return .network
    case .timeout:
      return .timeout
    case .success(let accepted, let duplicate):
      let payload: [String: Any] = [
        "accepted_count": accepted,
        "batch_id": request.batchID.uuidString.lowercased(),
        "duplicate_count": duplicate,
        "schema_version": 1,
      ]
      let body = (try? JSONSerialization.data(withJSONObject: payload)) ?? Data()
      return .response(status: 200, retryAfter: nil, body: body)
    }
  }

  func snapshotRequests() -> [ClientTelemetryRequest] {
    lock.lock()
    defer { lock.unlock() }
    return requests
  }
}

private func telemetryJSONEqual(_ lhs: Any, _ rhs: Any) -> Bool {
  if let left = lhs as? String, let right = rhs as? String { return left == right }
  if let left = lhs as? [Any], let right = rhs as? [Any] {
    return left.count == right.count && zip(left, right).allSatisfy { telemetryJSONEqual($0, $1) }
  }
  if let left = lhs as? [String: Any], let right = rhs as? [String: Any] {
    return left.count == right.count
      && left.allSatisfy { key, value in
        guard let other = right[key] else { return false }
        return telemetryJSONEqual(value, other)
      }
  }
  let leftNumber = lhs as? NSNumber
  let rightNumber = rhs as? NSNumber
  if let leftNumber, let rightNumber {
    if CFGetTypeID(leftNumber) == CFBooleanGetTypeID() || CFGetTypeID(rightNumber) == CFBooleanGetTypeID() {
      return leftNumber.boolValue == rightNumber.boolValue
    }
    return leftNumber.doubleValue == rightNumber.doubleValue
  }
  if let left = lhs as? Int, let right = rhs as? NSNumber { return Double(left) == right.doubleValue }
  if let left = lhs as? NSNumber, let right = rhs as? Int { return left.doubleValue == Double(right) }
  if let left = lhs as? Double, let right = rhs as? NSNumber { return left == right.doubleValue }
  if let left = lhs as? NSNumber, let right = rhs as? Double { return left.doubleValue == right }
  if let left = lhs as? Int, let right = rhs as? Int { return left == right }
  if let left = lhs as? Double, let right = rhs as? Double { return left == right }
  if let left = lhs as? Int, let right = rhs as? Double { return Double(left) == right }
  if let left = lhs as? Double, let right = rhs as? Int { return left == Double(right) }
  return false
}
