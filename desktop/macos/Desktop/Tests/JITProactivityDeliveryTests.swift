import Foundation
import XCTest

@testable import Omi_Computer

final class JITProactivityDeliveryTests: XCTestCase {
  private final class AuthorizationProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var checks = 0

    func current(_: RuntimeOwnerAuthorizationSnapshot) -> Bool {
      lock.lock()
      defer { lock.unlock() }
      checks += 1
      return checks == 1
    }

    var checkCount: Int {
      lock.lock()
      defer { lock.unlock() }
      return checks
    }
  }

  private actor CandidateRecorder {
    private(set) var calls: [(String, [String])] = []

    func record(deliveryID: String, factIDs: [String]) {
      calls.append((deliveryID, factIDs))
    }
  }

  private func snapshot() throws -> RuntimeOwnerAuthorizationSnapshot {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    return try XCTUnwrap(authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
  }

  private func request(mode: String = "ask") throws -> JITProactivityAgentRequest {
    JITProactivityAgentRequest(
      surface: .service("jit-test"),
      prompt: "prompt",
      systemPrompt: "system",
      mode: mode,
      authorizationSnapshot: try snapshot())
  }

  func testAgentAuthorityRequiresAskModeBeforeRunnerSubmission() async throws {
    let invoked = AuthorizationProbe()
    do {
      _ = try await JITProactivityAgentAuthority.run(
        request(mode: "act"),
        runner: { request in
          _ = invoked.current(request.authorizationSnapshot)
          return JITProactivityAgentResult(text: "", runID: "run", inputTokens: 0, outputTokens: 0)
        },
        authorizationCurrent: { _ in true })
      XCTFail("act mode must be rejected")
    } catch {
      XCTAssertEqual(error as? JITProactivityAgentAuthorityError, .readOnlyModeRequired)
    }
    XCTAssertEqual(invoked.checkCount, 0)
  }

  func testAgentAuthorityRejectsOwnerTransitionAcrossFullAwait() async throws {
    let probe = AuthorizationProbe()
    do {
      _ = try await JITProactivityAgentAuthority.run(
        request(),
        runner: { _ in
          await Task.yield()
          return JITProactivityAgentResult(text: "{}", runID: "run", inputTokens: 1, outputTokens: 1)
        },
        authorizationCurrent: probe.current)
      XCTFail("stale owner result must not publish")
    } catch {
      XCTAssertEqual(error as? JITProactivityAgentAuthorityError, .ownerChanged)
    }
  }

  func testOutputContractKeepsPlannedInsightOnlyAndAmbientTaskCandidateExplicit() throws {
    let task = """
      {"decision":"task_candidate","title":"Ship","message":"Ship build","reasoning":"fact",\
      "bucket_entry_refs":[],"fact_ids":["fact:1"]}
      """
    XCTAssertThrowsError(try JITProactivityOutputPolicy.decode(task, lane: .planned))
    XCTAssertEqual(try JITProactivityOutputPolicy.decode(task, lane: .ambient).decision, "task_candidate")
    XCTAssertThrowsError(
      try JITProactivityOutputPolicy.decode(
        task.replacingOccurrences(of: "[\"fact:1\"]", with: "[]"), lane: .ambient))
  }

  func testTaskCandidateUsesInjectedCandidateSinkBoundaryBeforePresentation() async throws {
    let recorder = CandidateRecorder()
    let delivery = JITProactivityDelivery(
      agentRunner: { _ in
        JITProactivityAgentResult(text: "", runID: "", inputTokens: 0, outputTokens: 0)
      },
      candidateGraduator: { deliveryID, factIDs, _ in
        await recorder.record(deliveryID: deliveryID, factIDs: factIDs)
        return .graduated
      })

    let result = await delivery.graduateCandidate(
      decisionType: "task_candidate",
      deliveryID: "delivery",
      factIDs: ["fact:1"],
      authorizationSnapshot: try snapshot())
    let insight = await delivery.graduateCandidate(
      decisionType: "insight",
      deliveryID: "not-a-candidate",
      factIDs: ["fact:2"],
      authorizationSnapshot: try snapshot())

    XCTAssertEqual(result, .graduated)
    XCTAssertEqual(insight, .graduated)
    let calls = await recorder.calls
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(calls.first?.0, "delivery")
    XCTAssertEqual(calls.first?.1, ["fact:1"])
  }
}
