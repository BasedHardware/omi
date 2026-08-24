import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerPromptSnapshotTests: XCTestCase {
  func testExhaustiveCursorWalkProducesAuthoritativeSnapshot() async throws {
    let client = APIClient.shared
    let pages = [
      page(ids: ["fact-a"], nextCursor: "next"),
      page(ids: ["playbook-b"], nextCursor: nil),
    ]
    var calls = 0

    let snapshot = try await client.collectKnowledgeLedgerPromptSnapshot(pageLimit: 3) { cursor in
      defer { calls += 1 }
      XCTAssertEqual(cursor, calls == 0 ? nil : "next")
      return pages[calls]
    }

    XCTAssertEqual(snapshot.authority, .enabled)
    XCTAssertEqual(snapshot.memories.map(\.id), ["fact-a", "playbook-b"])
    XCTAssertEqual(calls, 2)
  }

  func testDisabledAndKilledAuthorityNeverReturnRows() async throws {
    for authority in [
      APIClient.KnowledgeLedgerPromptAuthority.disabled,
      APIClient.KnowledgeLedgerPromptAuthority.killed,
    ] {
      let snapshot = try await APIClient.shared.collectKnowledgeLedgerPromptSnapshot(pageLimit: 1) { _ in
        self.page(ids: ["must-not-leak"], authority: authority)
      }
      XCTAssertEqual(snapshot.authority, authority)
      XCTAssertTrue(snapshot.memories.isEmpty)
    }
  }

  func testPartialDuplicateLoopAndBoundedWalkFailClosed() async {
    await assertSnapshotError(.incompletePage) { _ in
      self.page(ids: ["partial"], truncated: true)
    }
    var duplicateCall = 0
    await assertSnapshotError(.duplicateMemoryID, pageLimit: 2) { _ in
      defer { duplicateCall += 1 }
      return self.page(ids: ["same"], nextCursor: duplicateCall == 0 ? "next" : nil)
    }
    await assertSnapshotError(.repeatedCursor, pageLimit: 3) { _ in
      self.page(ids: [], nextCursor: "same")
    }
    var boundCall = 0
    await assertSnapshotError(.pageLimitExceeded, pageLimit: 2) { _ in
      defer { boundCall += 1 }
      return self.page(ids: ["row-\(boundCall)"], nextCursor: "next-\(boundCall)")
    }
  }

  func testAuthorityCannotChangeMidSnapshot() async {
    var call = 0
    await assertSnapshotError(.authorityChanged, pageLimit: 2) { _ in
      defer { call += 1 }
      return self.page(
        ids: ["row-\(call)"],
        nextCursor: call == 0 ? "next" : nil,
        authority: call == 0 ? .enabled : .killed)
    }
  }

  private func assertSnapshotError(
    _ expected: APIClient.KnowledgeLedgerPromptSnapshotError,
    pageLimit: Int = 1,
    fetch: @escaping (String?) async throws -> APIClient.MemoryListPage
  ) async {
    do {
      _ = try await APIClient.shared.collectKnowledgeLedgerPromptSnapshot(
        pageLimit: pageLimit, fetchPage: fetch)
      XCTFail("Expected \(expected)")
    } catch let error as APIClient.KnowledgeLedgerPromptSnapshotError {
      XCTAssertEqual(error, expected)
    } catch {
      XCTFail("Unexpected error: \(error)")
    }
  }

  private func page(
    ids: [String],
    nextCursor: String? = nil,
    truncated: Bool = false,
    authority: APIClient.KnowledgeLedgerPromptAuthority = .enabled
  ) -> APIClient.MemoryListPage {
    APIClient.MemoryListPage(
      memories: ids.map(memory),
      nextCursor: nextCursor,
      canonicalLifecycleExposed: true,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: truncated,
      ledgerPromptAuthority: authority)
  }

  private func memory(id: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: id,
      category: .system,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "test",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil,
      ledgerMetadata: ["ledger_schema_version": "knowledge_ledger.v1"])
  }
}
