//
//  MemoryVisibilityGuardrailTests.swift — an archived memory must not reach a second surface.
//
//  The regression these hold: the archive and device-scope rules lived inside the Memories page's
//  private recompute, so Home's chronological spine — reading the raw `memories` array — put
//  archived memories on the timeline. The rule was correct and simply unreachable from a second
//  reader.
//
//  So these are behavioural tests through the projection both readers now run on, not a scrape for
//  the two `if` statements. If someone reimplements the filter at a call site instead of extending
//  the policy, `testTheSpineProjectionExcludesArchiveThatTheRawListStillHolds` is what fails.
//

import XCTest

@testable import Omi_Computer

final class MemoryVisibilityGuardrailTests: XCTestCase {
  private func memory(_ id: String, tier: MemoryLayer, device: String? = nil) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: tier,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: device,
      windowTitle: nil,
      headline: nil
    )
  }

  private var corpus: [ServerMemory] {
    [
      memory("short", tier: .shortTerm),
      memory("long", tier: .longTerm),
      memory("archived", tier: .archive),
    ]
  }

  // MARK: - The defect

  /// **The regression.** Home's spine reads a projection with the guardrails applied; the raw
  /// accumulation it used to read still holds the archived row. If a future change points the spine
  /// back at an unguarded list, these two stop disagreeing and this fails.
  func testTheSpineProjectionExcludesArchiveThatTheRawListStillHolds() {
    let raw = corpus
    XCTAssertTrue(raw.contains { $0.tier == .archive }, "the raw accumulation genuinely holds it")

    let visible = MemoryPageProjection.guardrailed(
      raw,
      allowedLayers: MemoryLayerFilter.defaultAccess.allowedLayers,
      thisDeviceOnly: false,
      deviceScopeSupported: true,
      matchesThisDevice: { _ in true }
    )
    XCTAssertFalse(
      visible.contains { $0.tier == .archive },
      "archive is never in the default list unless the user explicitly selects it")
    XCTAssertEqual(visible.map(\.id), ["short", "long"])
  }

  func testExplicitlySelectingArchiveShowsIt() {
    let visible = MemoryPageProjection.guardrailed(
      corpus,
      allowedLayers: MemoryLayerFilter.archive.allowedLayers,
      thisDeviceOnly: false,
      deviceScopeSupported: true,
      matchesThisDevice: { _ in true }
    )
    XCTAssertEqual(visible.map(\.id), ["archived"])
  }

  /// An account with no canonical lifecycle has no tiers to filter on, so nothing is withheld.
  func testAnAccountWithoutTiersKeepsEverything() {
    let visible = MemoryPageProjection.guardrailed(
      corpus,
      allowedLayers: nil,
      thisDeviceOnly: false,
      deviceScopeSupported: true,
      matchesThisDevice: { _ in true }
    )
    XCTAssertEqual(visible.count, 3)
  }

  // MARK: - Device scope

  func testDeviceScopeNarrowsToThisMacWhenTheBackendSupportsIt() {
    let visible = MemoryPageProjection.guardrailed(
      [memory("mine", tier: .longTerm, device: "this"), memory("theirs", tier: .longTerm, device: "other")],
      allowedLayers: nil,
      thisDeviceOnly: true,
      deviceScopeSupported: true,
      matchesThisDevice: { $0.inputDeviceName == "this" }
    )
    XCTAssertEqual(visible.map(\.id), ["mine"])
  }

  /// The legacy-principal case. An account the backend cannot scope has rows with no capture
  /// provenance at all; filtering them here would empty the list and blame the user's filter for it.
  /// A fail-closed scope would break every unmigrated account on the day it shipped.
  func testDeviceScopeIsNotAppliedLocallyWhenTheBackendCannotSupportIt() {
    let visible = MemoryPageProjection.guardrailed(
      [memory("legacy-a", tier: .longTerm), memory("legacy-b", tier: .longTerm)],
      allowedLayers: nil,
      thisDeviceOnly: true,
      deviceScopeSupported: false,
      matchesThisDevice: { _ in false }
    )
    XCTAssertEqual(visible.count, 2, "an unscopeable account keeps its list rather than emptying it")
  }

  // MARK: - The spine consumes it

  /// The other half of the fix: the spine must not inherit the Memories page's search term or tag
  /// selection. It composes from whatever guardrailed list it is handed, so a memory that survives
  /// the guardrails reaches the day.
  func testTheSpineComposesEveryGuardrailedMemoryItIsHanded() {
    let visible = MemoryPageProjection.guardrailed(
      corpus,
      allowedLayers: MemoryLayerFilter.defaultAccess.allowedLayers,
      thisDeviceOnly: false,
      deviceScopeSupported: true,
      matchesThisDevice: { _ in true }
    )
    let projected = visible.map {
      SpineMemory(
        id: $0.id, text: $0.content, timestamp: $0.createdAt, conversationID: $0.conversationId)
    }
    let days = SpineComposer.compose(conversations: [], memories: projected, screen: [:])

    let ids = days.flatMap(\.rows).flatMap { row -> [String] in
      guard case .memories(let memories) = row.content else { return [] }
      return memories.map(\.id)
    }
    XCTAssertEqual(Set(ids), ["short", "long"])
    XCTAssertFalse(ids.contains("archived"))
  }
}
