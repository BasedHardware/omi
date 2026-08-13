#if DEBUG
  import Foundation
  import XCTest

  @testable import Omi_Computer

  final class ContextBucketDirectorProbeTests: XCTestCase {
    private actor CallRecorder {
      struct Record {
        let operation: String
        let prompt: String
        let imageData: Data?
        let schemaKeys: Set<String>
        let cacheKey: String?
        let maxCompletionTokens: Int
        let authorizationSnapshotWasPresent: Bool
      }

      private(set) var record: Record?

      func save(
        operation: String,
        prompt: String,
        imageData: Data?,
        schemaKeys: Set<String>,
        cacheKey: String?,
        maxCompletionTokens: Int,
        authorizationSnapshotWasPresent: Bool
      ) {
        record = Record(
          operation: operation,
          prompt: prompt,
          imageData: imageData,
          schemaKeys: schemaKeys,
          cacheKey: cacheKey,
          maxCompletionTokens: maxCompletionTokens,
          authorizationSnapshotWasPresent: authorizationSnapshotWasPresent)
      }
    }

    func testReplayUsesProductionPromptSchemaCacheAndTokenContract() async throws {
      let recorder = CallRecorder()
      let params: [String: String] = [
        "bucket_id": "synthetic-bucket",
        "version": "7",
        "header": "Synthetic header",
        "frozen": "frozen:entry-1\n",
        "tail": #"["entry:tail-1"]"#,
        "validated_facts": #"["fact:validated-1"]"#,
        "tasks": #"["Review synthetic item"]"#,
        "app": "SyntheticEditor",
        "window": "Synthetic window",
      ]
      let probe = ContextBucketDirectorProbe(
        completion: {
          operation, prompt, imageData, schema, cacheKey,
          maxCompletionTokens, authorizationSnapshot in
          await recorder.save(
            operation: operation,
            prompt: prompt,
            imageData: imageData,
            schemaKeys: Set(schema.keys),
            cacheKey: cacheKey,
            maxCompletionTokens: maxCompletionTokens,
            authorizationSnapshotWasPresent: authorizationSnapshot != nil)
          let content =
            #"{"decision":"suggest","title":"Synthetic title","message":"Synthetic message","reasoning":"Synthetic reasoning","bucket_entry_refs":["entry:tail-1"],"fact_ids":["fact:validated-1"]}"#
          return ProactiveLaneResult(
            operation: operation,
            lane: "omi:auto:desktop-proactive-reasoning",
            providerModel: "gpt-5.6-luna",
            usage: ProactiveLaneUsage(cachedTokens: 1, cacheWriteTokens: 0),
            cacheWrite: false,
            fallbackClass: "unknown",
            content: content)
        }, isNonProduction: true)

      let result = try await probe.run(params: params)
      let captured = await recorder.record
      let expectedSnapshot = ContextBucketSnapshot(
        bucketID: "synthetic-bucket",
        versionID: 7,
        version: 7,
        header: "Synthetic header",
        frozenRankedSegment: Data("frozen:entry-1\n".utf8),
        tail: ["entry:tail-1"],
        validatedFacts: ["fact:validated-1"],
        notifyWorthiness: 1)
      let expectedFrame = CapturedFrame(
        jpegData: Data(), appName: "SyntheticEditor", windowTitle: "Synthetic window", frameNumber: 0)
      let expectedPrompt = ContextProactivityPromptBuilder.directorPrompt(
        snapshot: expectedSnapshot,
        tasks: ["Review synthetic item"],
        frame: expectedFrame)

      XCTAssertEqual(captured?.operation, ModelQoS.Proactivity.reasoningOperation)
      XCTAssertEqual(captured?.prompt, expectedPrompt)
      XCTAssertNil(captured?.imageData)
      XCTAssertEqual(captured?.cacheKey, "bucket:synthetic-bucket:v7")
      XCTAssertEqual(captured?.maxCompletionTokens, 800)
      XCTAssertFalse(captured?.authorizationSnapshotWasPresent ?? true)
      XCTAssertEqual(captured?.schemaKeys, Set(["type", "properties", "required", "additionalProperties"]))
      XCTAssertEqual(result["decision"], "suggest")
      XCTAssertEqual(result["bucket_entry_ref_count"], "1")
      XCTAssertEqual(result["fact_ref_count"], "1")
      XCTAssertEqual(result["model"], "gpt-5.6-luna")
      XCTAssertNotNil(result["latency_ms"])
    }

    func testReplayClampsUntrustedDecisionAndDoesNotInvokeDelivery() async throws {
      let recorder = CallRecorder()
      let probe = ContextBucketDirectorProbe(
        completion: { operation, _, _, _, _, _, _ in
          await recorder.save(
            operation: operation,
            prompt: "",
            imageData: nil,
            schemaKeys: [],
            cacheKey: nil,
            maxCompletionTokens: 0,
            authorizationSnapshotWasPresent: false)
          let decision = ContextDirectorDecision(
            decision: "task_candidate",
            title: String(repeating: "t", count: 500),
            message: String(repeating: "m", count: 1_000),
            reasoning: String(repeating: "r", count: 2_000),
            bucketEntryRefs: (0..<40).map { "entry:\($0)" },
            factIDs: (0..<40).map { "fact:\($0)" })
          let data = try JSONEncoder().encode(decision)
          return ProactiveLaneResult(
            operation: operation,
            lane: "test",
            providerModel: "attacker-controlled-model",
            usage: ProactiveLaneUsage(cachedTokens: 0, cacheWriteTokens: 0),
            cacheWrite: false,
            fallbackClass: "unknown",
            content: String(decoding: data, as: UTF8.self))
        }, isNonProduction: true)

      let result = try await probe.run(params: [
        "bucket_id": "synthetic-bucket",
        "version": "1",
        "header": "header",
        "frozen": "frozen",
        "tail": "[]",
        "validated_facts": "[]",
        "tasks": "[]",
        "app": "SyntheticApp",
        "window": "SyntheticWindow",
      ])

      XCTAssertEqual(result["decision"], "task_candidate")
      XCTAssertEqual(result["title"]?.count, 120)
      XCTAssertEqual(result["message"]?.count, 600)
      XCTAssertEqual(result["reasoning"]?.count, 1_200)
      XCTAssertEqual(result["bucket_entry_ref_count"], "20")
      XCTAssertEqual(result["fact_ref_count"], "20")
      XCTAssertEqual(result["model"], "other")
      let recorded = await recorder.record
      XCTAssertEqual(recorded?.operation, ModelQoS.Proactivity.reasoningOperation)
    }

    @MainActor
    func testAutomationDescriptorDeclaresNetworkOnlyAndNoDelivery() {
      DesktopAutomationActionRegistry.shared.registerBuiltins()
      let descriptor = DesktopAutomationActionRegistry.shared.descriptors().first {
        $0.name == "probe_context_bucket_director"
      }
      XCTAssertEqual(descriptor?.safety, "network_or_model")
      XCTAssertTrue(descriptor?.sideEffects.contains(where: { $0.contains("deliver notifications") }) == true)
      XCTAssertEqual(
        descriptor?.params,
        ["bucket_id", "version", "header", "frozen", "tail", "validated_facts", "tasks", "app", "window"])
    }

    func testReplayFailsClosedOutsideNonProductionBeforeClientCall() async {
      let recorder = CallRecorder()
      let probe = ContextBucketDirectorProbe(
        completion: { operation, _, _, _, _, _, _ in
          await recorder.save(
            operation: operation,
            prompt: "called",
            imageData: nil,
            schemaKeys: [],
            cacheKey: nil,
            maxCompletionTokens: 0,
            authorizationSnapshotWasPresent: false)
          return ProactiveLaneResult(
            operation: operation,
            lane: "test",
            providerModel: "test",
            usage: ProactiveLaneUsage(cachedTokens: 0, cacheWriteTokens: 0),
            cacheWrite: false,
            fallbackClass: "unknown",
            content: "{}")
        },
        isNonProduction: false)

      do {
        _ = try await probe.run(params: [:])
        XCTFail("production replay should fail closed")
      } catch ContextBucketDirectorProbeError.nonProductionOnly {
        // Expected.
      } catch {
        XCTFail("unexpected error: \(error)")
      }
      let recorded = await recorder.record
      XCTAssertNil(recorded)
    }
  }
#endif
