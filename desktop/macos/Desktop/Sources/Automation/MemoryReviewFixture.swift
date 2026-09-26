//
//  MemoryReviewFixture.swift — the shared bring-up and drive helpers for the "Things I learned
//  today" automation actions.
//
//  The `memory_review_*` actions in `DesktopAutomationActivationActions.swift` are second callers
//  of production code, never a second implementation; this file holds what those actions need to
//  reach a mounted card on a hermetic bundle: a deterministic row catalog, the local-only daily
//  summary seed contract, and bounded waits against the mounted section's own store.
//
//  Restored as its own file after the knows-list action family was pruned from
//  `DesktopAutomationActivationActions.swift` and took this enum down with it while the
//  memory-review actions and their flow still reference it.
//
//  Registered from `DesktopAutomationActionRegistry.registerBuiltins()`.
//

import Foundation

@MainActor
enum MemoryReviewFixture {
  static let seedEndpoint = "v1/dev-harness/daily-summary/seed"
  /// Four, so a flow can seed more learned memories than the card renders and prove the bound.
  static let defaultCount = 4

  struct CatalogRow {
    let content: String
    let category: MemoryCategory
  }

  /// Deterministic and asserted verbatim by `memory-review.yaml`: change one and change the flow
  /// in the same commit.
  static let catalog: [CatalogRow] = [
    CatalogRow(content: "Prefers async standups over daily calls.", category: .system),
    CatalogRow(content: "Ships desktop releases on Wednesdays.", category: .workflow),
    CatalogRow(content: "Reviews the storage migration with Priya.", category: .interesting),
    CatalogRow(content: "Keeps a written weekly plan before Monday.", category: .system),
  ]

  static func rows(count: Int) -> [CatalogRow]? {
    guard count >= 1, count <= catalog.count else { return nil }
    return Array(catalog.prefix(count))
  }

  struct WireMemory: Encodable {
    let memoryID: String
    let content: String
    let category: String

    enum CodingKeys: String, CodingKey {
      case memoryID = "memory_id"
      case content, category
    }
  }

  struct SeedRequest: Encodable {
    let memories: [WireMemory]
  }

  struct SeedResponse: Decodable {
    let status: String
    let summaryID: String
    let date: String
    let memoriesLearned: Int

    enum CodingKeys: String, CodingKey {
      case status, date
      case summaryID = "summary_id"
      case memoriesLearned = "memories_learned"
    }
  }

  /// Bounded so an error string can never carry an unbounded response body into flow evidence.
  static func reason(_ error: Error) -> String {
    String(String(describing: error).prefix(200))
  }

  static func event(for verdict: String) -> MemoryReviewEvent? {
    switch verdict {
    case "accept": return .accept
    case "reject": return .reject
    default: return nil
    }
  }

  /// What one row shows, named by index so a flow can assert two rows in one snapshot.
  static func rowDetail(
    index: Int, item: MemoryReviewItem, store: MemoryReviewCardStore
  ) -> [String: String] {
    let model = store.row(item.memoryID)
    let prefix = "row\(index)_"
    return [
      prefix + "id": item.memoryID,
      prefix + "content": item.content,
      prefix + "category": item.categoryLabel ?? "",
      prefix + "verdict": verdictName(model.displayed),
      prefix + "status": model.statusText ?? "",
      prefix + "settled": model.isSettled ? "true" : "false",
      prefix + "faded": model.isFaded ? "true" : "false",
      prefix + "busy": model.isBusy ? "true" : "false",
      prefix + "error": model.errorMessage ?? "",
    ]
  }

  private static func verdictName(_ verdict: MemoryReviewVerdict) -> String {
    switch verdict {
    case .none: return "none"
    case .accepted: return "accepted"
    case .rejected: return "rejected"
    case .updated: return "updated"
    }
  }

  /// How many rows the mounted section bound, once the store's refresh has reached the card.
  ///
  /// Waits for the section built from *these* memory ids, not merely for a mounted section. A
  /// re-run of the flow overwrites the same day's summary with freshly created memories, and the
  /// previous run's card — same content, already voted on — stays mounted until SwiftUI rebuilds
  /// it. Waiting on "any rows" would read that one and see a settled verdict on a row the flow
  /// has not clicked yet.
  static func waitForMountedRows(seeded ids: Set<String>, timeoutMs: Int) async -> Int {
    await waitUntil(timeoutMs: timeoutMs) {
      guard let items = MemoryReviewCardRegistry.mounted?.items, !items.isEmpty else { return false }
      return items.allSatisfy { ids.contains($0.memoryID) }
    }
    let items = MemoryReviewCardRegistry.mounted?.items ?? []
    return items.allSatisfy { ids.contains($0.memoryID) } ? items.count : 0
  }

  /// True when the row's request finished inside the budget. A timeout is reported rather than
  /// thrown: the row detail beside it says what the row settled on, which is the finding.
  static func waitForSettled(
    store: MemoryReviewCardStore, item: MemoryReviewItem, timeoutMs: Int
  ) async -> Bool {
    await waitUntil(timeoutMs: timeoutMs) { !store.row(item.memoryID).isBusy }
  }

  @discardableResult
  private static func waitUntil(timeoutMs: Int, _ isDone: @MainActor () -> Bool) async -> Bool {
    let deadline = Date().addingTimeInterval(Double(max(0, timeoutMs)) / 1000.0)
    while !isDone() {
      guard Date() < deadline else { return false }
      try? await Task.sleep(nanoseconds: 100_000_000)
    }
    return true
  }
}
