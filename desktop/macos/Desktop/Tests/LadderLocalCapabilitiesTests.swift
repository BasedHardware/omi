import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class LadderLocalCapabilitiesTests: XCTestCase {
  func testRemoteEmergencyStopOverridesExplicitEnablesWithoutGrantingGemini() throws {
    let defaults = try makeIsolatedDefaults()
    XCTAssertFalse(LocalCapabilityRemoteKill.resolve(nil))
    XCTAssertFalse(LocalCapabilityRemoteKill.resolve("true"))
    XCTAssertFalse(LocalCapabilityRemoteKill.resolve(false))
    XCTAssertTrue(LocalCapabilityRemoteKill.resolve(true))
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: ["OMI_LOCAL_EMBEDDINGS": "1"], defaults: defaults, remoteDisabled: true)
    XCTAssertTrue(flags.isDisabled)
    let free = ScreenEmbeddingPolicy(plan: .basic, status: .active, localRoute: .none, killSwitches: flags)
    XCTAssertFalse(free.shouldEmbedWithGemini)
    XCTAssertEqual(free.searchRoute, .ftsOnly)
    XCTAssertFalse(
      FreeTierLocalProcessingFlag.isEnabled(
        environment: [FreeTierLocalProcessingFlag.environmentKey: "1"], defaults: defaults, remoteDisabled: true))
  }

  func testFundingMatrixPreservesAllowanceAndUnknownPaidPlans() throws {
    for plan in ["basic", "plus", "operator", "architect", "future_plan"] {
      for mode in ["managed", "on_device", "blocked", "future_mode", "missing"] {
        for remaining in [0, 60] {
          for reason in [
            "usage_budget_exhausted", "plan_allowance_exhausted", "subscription_inactive",
            "allowance_unavailable", "usage_invalid", "future_reason",
          ] {
            let allowance: [String: Any]? =
              mode == "missing"
              ? nil
              : [
                "mode": mode, "remaining_seconds": remaining, "reason": reason,
              ]
            var payload: [String: Any] = [
              "subscription": [
                "plan": plan, "status": "active", "features": [], "cancel_at_period_end": false, "limits": [:],
              ]
            ]
            if let allowance { payload["transcription_allowance"] = allowance }
            let response = try JSONDecoder().decode(
              UserSubscriptionResponse.self, from: JSONSerialization.data(withJSONObject: payload))
            let unavailable = LocalProjectionFinalization.fundingUnavailable(
              subscription: response, isByokActive: false)
            let exhausted =
              reason == "usage_budget_exhausted"
              || (plan == "basic" && ["plan_allowance_exhausted", "subscription_inactive"].contains(reason))
            XCTAssertEqual(
              unavailable,
              (mode == "on_device" && remaining == 0 && exhausted)
                || (mode == "missing" && plan == "basic"), "\(plan)/\(mode)/\(reason)")
            XCTAssertFalse(LocalProjectionFinalization.fundingUnavailable(subscription: response, isByokActive: true))
          }
        }
      }
    }
    XCTAssertFalse(LocalProjectionFinalization.fundingUnavailable(subscription: nil, isByokActive: false))
  }

  func testActualSingleAndBatchEmbeddingAPIsDenyBeforeAuthOrHTTP() async {
    let auth = EmbeddingTestAuthorization()
    let service = EmbeddingService(
      cloudEmbeddingAllowed: { _ in false },
      acquireAuth: { _ in
        XCTFail("no-entitlement request acquired credentials")
        return "synthetic"
      },
      dispatch: { _ in
        XCTFail("no-entitlement request dispatched")
        throw CancellationError()
      }, ownerIsCurrent: auth.source.isCurrent)
    do {
      _ = try await service.embed(text: "synthetic", authorization: auth.snapshot)
      XCTFail("single embed must be gated")
    } catch let error as EmbeddingService.EmbeddingError {
      XCTAssertTrue(error.isExpectedProductState)
    } catch { XCTFail("unexpected error: \(error)") }
    do {
      _ = try await service.embedBatch(texts: ["synthetic"], authorization: auth.snapshot)
      XCTFail("batch embed must be gated")
    } catch let error as EmbeddingService.EmbeddingError {
      XCTAssertTrue(error.isExpectedProductState)
    } catch { XCTFail("unexpected error: \(error)") }
  }

  func testEntitledSingleAndBatchRequestsPreservePayloadAndResponses() async throws {
    let auth = EmbeddingTestAuthorization()
    let service = EmbeddingService(
      cloudEmbeddingAllowed: { _ in true }, acquireAuth: { _ in "Bearer synthetic" },
      dispatch: { request in
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Omi-Local-Embeddings"), "1")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Omi-Lane"), "embedding")
        let body = try XCTUnwrap(request.httpBody)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        let batch = request.url?.path.hasSuffix(":batchEmbedContents") == true
        let response: [String: Any]
        if batch {
          let requests = try XCTUnwrap(object["requests"] as? [[String: Any]])
          XCTAssertEqual(requests.count, 2)
          XCTAssertEqual(requests.first?["taskType"] as? String, "RETRIEVAL_DOCUMENT")
          response = ["embeddings": [["values": [1, 0]], ["values": [0, 1]]]]
        } else {
          XCTAssertTrue(request.url?.path.hasSuffix(":embedContent") == true)
          XCTAssertEqual(object["taskType"] as? String, "RETRIEVAL_QUERY")
          response = ["embedding": ["values": [1, 0]]]
        }
        return (
          try JSONSerialization.data(withJSONObject: response),
          try XCTUnwrap(
            HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil))
        )
      }, ownerIsCurrent: auth.source.isCurrent)
    let single = try await service.embed(
      text: "synthetic query", taskType: "RETRIEVAL_QUERY", authorization: auth.snapshot)
    let batch = try await service.embedBatch(
      texts: ["synthetic A", "synthetic B"], taskType: "RETRIEVAL_DOCUMENT", authorization: auth.snapshot)
    XCTAssertEqual(single, [1, 0])
    XCTAssertEqual(batch, [[1, 0], [0, 1]])
  }

  func testEntitlementIsRecheckedAfterAuthForBothAPIs() async {
    for batch in [false, true] {
      let auth = EmbeddingTestAuthorization()
      let counter = EmbedCallCounter()
      let service = EmbeddingService(
        cloudEmbeddingAllowed: { _ in counter.snapshot() == 0 },
        acquireAuth: { _ in
          counter.add(1)
          return "synthetic"
        },
        dispatch: { _ in
          XCTFail("downgraded request dispatched")
          throw CancellationError()
        }, ownerIsCurrent: auth.source.isCurrent)
      do {
        if batch {
          _ = try await service.embedBatch(texts: ["synthetic"], authorization: auth.snapshot)
        } else {
          _ = try await service.embed(text: "synthetic", authorization: auth.snapshot)
        }
        XCTFail("downgraded request must be gated")
      } catch let error as EmbeddingService.EmbeddingError {
        XCTAssertTrue(error.isExpectedProductState)
      } catch { XCTFail("unexpected error: \(error)") }
      XCTAssertEqual(counter.snapshot(), 1)
    }
  }

  func testRevokedOwnerIsRejectedBeforeCredentialAcquisition() async throws {
    let auth = EmbeddingTestAuthorization()
    let original = auth.snapshot
    auth.authority.beginTransition()
    let service = EmbeddingService(
      cloudEmbeddingAllowed: { _ in true },
      acquireAuth: { _ in
        XCTFail("revoked work acquired credentials")
        throw CancellationError()
      },
      dispatch: { _ in
        XCTFail("revoked work dispatched")
        throw CancellationError()
      },
      ownerIsCurrent: auth.source.isCurrent)
    for batch in [false, true] {
      do {
        if batch {
          _ = try await service.embedBatch(texts: ["old OCR"], authorization: original)
        } else {
          _ = try await service.embed(text: "old query", authorization: original)
        }
        XCTFail("revoked work succeeded")
      } catch { XCTAssertEqual(ScreenTaskErrorPolicy.errorClass(error), "owner_revoked") }
    }
  }

  func testOwnerRevocationDuringAuthPreventsBothHTTPDispatches() async throws {
    for batch in [false, true] {
      for nextOwner in ["synthetic-a", "synthetic-b", "transitional"] {
        let auth = EmbeddingTestAuthorization(ownerID: "synthetic-a")
        let original = auth.snapshot
        let dispatches = EmbedCallCounter()
        let service = EmbeddingService(
          cloudEmbeddingAllowed: { _ in true },
          acquireAuth: { snapshot in
            XCTAssertEqual(snapshot, original)
            await Task.yield()
            auth.authority.beginTransition()
            if nextOwner != "transitional" { auth.authority.endTransition(ownerID: nextOwner) }
            return "Bearer next-owner"
          },
          dispatch: { _ in
            dispatches.add(1)
            throw CancellationError()
          }, ownerIsCurrent: auth.source.isCurrent)
        do {
          if batch {
            _ = try await service.embedBatch(texts: ["old OCR"], authorization: original)
          } else {
            _ = try await service.embed(text: "old query", authorization: original)
          }
          XCTFail("revoked request succeeded")
        } catch { XCTAssertEqual(ScreenTaskErrorPolicy.errorClass(error), "owner_revoked") }
        XCTAssertEqual(dispatches.snapshot(), 0)
      }
    }
  }

  func testLegacySyncDeliversVectorlessOCRAndWaitsForOpenBuckets() throws {
    let db = try DatabaseQueue()
    try db.write { db in
      try db.execute(
        sql: """
          CREATE TABLE screenshots (
            id INTEGER PRIMARY KEY, timestamp DATETIME, appName TEXT, windowTitle TEXT,
            ocrText TEXT, embedding BLOB, deviceName TEXT, clientDeviceId TEXT, screenActivitySyncState INTEGER DEFAULT 0)
          """)
      for (id, timestamp, text) in [(1, 1200, "synthetic OCR"), (2, 1250, ""), (3, 1501, "new bucket")] {
        try db.execute(
          sql: "INSERT INTO screenshots (id, timestamp, ocrText) VALUES (?, ?, ?)",
          arguments: [id, Date(timeIntervalSince1970: Double(timestamp)), text])
      }
      let first = try ScreenActivitySyncService.fetchLegacySyncRows(
        db: db, afterId: 0, limit: 100, now: Date(timeIntervalSince1970: 1501))
      XCTAssertEqual(first.map { $0["id"] as Int64 }, [1])
      XCTAssertNil(first.first?["embedding"] as Data?)
      let payload = try XCTUnwrap(first.first.flatMap(ScreenActivitySyncService.payloadRow(from:)))
      XCTAssertEqual(payload["ocrText"] as? String, "synthetic OCR")
      XCTAssertNil(payload["embedding"])
      let later = try ScreenActivitySyncService.fetchLegacySyncRows(
        db: db, afterId: 1, limit: 100, now: Date(timeIntervalSince1970: 1800))
      XCTAssertEqual(later.map { $0["id"] as Int64 }, [3])
    }
  }

  func testFreePlusAndUnknownHardKillSearchRoutesNeverUseGemini() async throws {
    for plan in [SubscriptionPlanType.basic, .plus, .unknown("future")] {
      let runtime = LocalEmbeddingRuntime(
        engines: [], killSwitches: LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: nil),
        record: { _, _ in })
      let policy = ScreenEmbeddingPolicy(
        plan: plan, status: .active, localRoute: .disabled, killSwitches: runtime.killSwitches)
      let result = try await ScreenHistorySearchRoute.search(runtime: runtime, policy: policy) { engine in
        XCTAssertNil(engine)
        return "synthetic FTS result"
      } legacy: {
        XCTFail("hard kill bypassed screen entitlement")
        return "Gemini"
      }
      XCTAssertEqual(result, "synthetic FTS result")
    }
  }
}
