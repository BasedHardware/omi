import Foundation
import XCTest

@testable import Omi_Computer

/// "Things I learned today": what the wire carries, what the row machine does with a click, and
/// what happens when the mutation behind that click fails.
final class MemoryReviewCardTests: XCTestCase {

  // MARK: - Record decoding

  private func decodeRecord(_ json: String) throws -> DailySummaryRecord {
    try JSONDecoder().decode(DailySummaryRecord.self, from: Data(json.utf8))
  }

  func testRecordDecodesMemoriesLearned() throws {
    let record = try decodeRecord(
      """
      {
        "id": "ds_1",
        "date": "2026-09-01",
        "headline": "A focused day",
        "memories_learned": [
          {
            "memory_id": "mem_1",
            "content": "David prefers async standups.",
            "category": "system",
            "captured_at": "2026-09-01T18:04:00Z"
          },
          { "memory_id": "mem_2", "content": "Ships desktop on Wednesdays.", "category": "interesting" }
        ]
      }
      """)
    XCTAssertEqual(record.memoriesLearned.count, 2)
    XCTAssertEqual(record.memoriesLearned.first?.memoryID, "mem_1")
    XCTAssertEqual(record.memoriesLearned.first?.content, "David prefers async standups.")
    XCTAssertEqual(record.memoriesLearned.first?.category, "system")
    XCTAssertEqual(record.memoriesLearned.first?.capturedAt, "2026-09-01T18:04:00Z")
    XCTAssertNil(record.memoriesLearned.last?.capturedAt)
  }

  /// A backend that predates the field, and a day that produced nothing to review, must be the
  /// same thing for every reader: an empty list, never a nil the card has to interpret.
  func testRecordDecodesWithoutMemoriesLearned() throws {
    let record = try decodeRecord(#"{"id": "ds_1", "date": "2026-09-01", "headline": "Quiet"}"#)
    XCTAssertTrue(record.memoriesLearned.isEmpty)
    XCTAssertEqual(record.headline, "Quiet")
  }

  /// One malformed entry must not cost the reader the whole summary, and a row with no id could
  /// never be voted on or corrected.
  func testRecordDropsUnusableLearnedEntriesWithoutLosingTheSummary() throws {
    let record = try decodeRecord(
      """
      {
        "id": "ds_1",
        "overview": "You shipped the card.",
        "memories_learned": [
          { "memory_id": "", "content": "no id" },
          { "memory_id": "mem_2", "content": "" },
          { "memory_id": "mem_3", "content": "Keeps a Wednesday release train." }
        ]
      }
      """)
    XCTAssertEqual(record.overview, "You shipped the card.")
    XCTAssertEqual(record.memoriesLearned.map(\.memoryID), ["mem_3"])
  }

  /// One entry of the wrong shape is one row lost, not the whole section: the rest of the array
  /// decodes independently around it.
  func testOneMalformedLearnedEntryDoesNotDiscardTheValidRowsBesideIt() throws {
    let record = try decodeRecord(
      """
      {
        "id": "ds_1",
        "memories_learned": [
          { "memory_id": 17, "content": "id is a number" },
          "not an object at all",
          { "memory_id": "mem_2", "content": "Keeps a Wednesday release train." }
        ]
      }
      """)
    XCTAssertEqual(record.memoriesLearned.map(\.memoryID), ["mem_2"])
  }

  /// A blank-but-present id passes an emptiness check and produces a row whose ✓ / ✗ / Fix would
  /// address no memory at all.
  func testAWhitespaceOnlyMemoryIDIsNotAReviewRow() throws {
    let record = try decodeRecord(
      #"{"id": "ds_1", "memories_learned": [{"memory_id": "  ", "content": "Real content."}]}"#)
    XCTAssertTrue(record.memoriesLearned.isEmpty)

    let summary = DailySummaryRecord(
      id: "ds_1", date: "2026-09-01", headline: nil, overview: nil,
      memoriesLearned: [DailySummaryRecord.LearnedMemory(memoryID: " ", content: "Real content.")])
    XCTAssertTrue(ChatDailySummaryPresentation.memoriesLearned(in: summary).isEmpty)
  }

  func testRecordSurvivesAMemoriesLearnedFieldOfTheWrongShape() throws {
    let record = try decodeRecord(#"{"id": "ds_1", "headline": "Still here", "memories_learned": "nope"}"#)
    XCTAssertEqual(record.headline, "Still here")
    XCTAssertTrue(record.memoriesLearned.isEmpty)
  }

  // MARK: - Card projection

  func testCardShowsAtMostThreeRowsAndNeverFallsBackToProse() {
    let summary = DailySummaryRecord(
      id: "ds_1", date: "2026-09-01", headline: "A day", overview: "Prose about the day.",
      memoriesLearned: (1...5).map {
        DailySummaryRecord.LearnedMemory(memoryID: "mem_\($0)", content: "Fact \($0)", category: "system")
      })
    let rows = ChatDailySummaryPresentation.memoriesLearned(in: summary)
    XCTAssertEqual(rows.count, MemoryReviewSection.maxRows)
    XCTAssertEqual(rows.map(\.memoryID), ["mem_1", "mem_2", "mem_3"])
  }

  /// The empty state is nothing at all — not a header, not a placeholder row.
  func testCardRendersNoReviewRowsWhenTheDayLearnedNothing() {
    let summary = DailySummaryRecord(
      id: "ds_1", date: "2026-09-01", headline: "Quiet", overview: "A quiet day.")
    XCTAssertTrue(ChatDailySummaryPresentation.memoriesLearned(in: summary).isEmpty)

    let blank = DailySummaryRecord(
      id: "ds_2", date: "2026-09-01", headline: "Quiet", overview: nil,
      memoriesLearned: [DailySummaryRecord.LearnedMemory(memoryID: "mem_1", content: "   ")])
    XCTAssertTrue(ChatDailySummaryPresentation.memoriesLearned(in: blank).isEmpty)
  }

  /// The section captures its rows when it is built, so a summary regenerated under the same id
  /// must not reuse the old one: new memories would never appear and corrected ones would keep the
  /// text the record no longer contains.
  func testTheReviewSectionIsRebuiltWhenARegeneratedSummaryChangesItsRows() {
    let first = [MemoryReviewItem(memoryID: "mem_1", content: "Prefers async standups.")]
    let corrected = [MemoryReviewItem(memoryID: "mem_1", content: "Prefers written standups.")]
    let added = first + [MemoryReviewItem(memoryID: "mem_2", content: "Ships on Wednesdays.")]

    let identity = ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: "ds_1", items: first)
    XCTAssertEqual(
      identity, ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: "ds_1", items: first))
    XCTAssertNotEqual(
      identity, ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: "ds_1", items: corrected))
    XCTAssertNotEqual(
      identity, ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: "ds_1", items: added))
    XCTAssertNotEqual(
      identity, ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: "ds_2", items: first))
  }

  func testCategoryLabelIsBoundedButNeverInvented() {
    XCTAssertEqual(MemoryReviewItem(memoryID: "m", content: "c", category: "system").categoryLabel, "About You")
    XCTAssertEqual(MemoryReviewItem(memoryID: "m", content: "c", category: "workflow").categoryLabel, "Workflow")
    XCTAssertEqual(MemoryReviewItem(memoryID: "m", content: "c", category: "brand-new").categoryLabel, "Brand-New")
    XCTAssertNil(MemoryReviewItem(memoryID: "m", content: "c", category: "  ").categoryLabel)
  }

  // MARK: - Codec

  private func reviewBlockJSON(items: [[String: Any]]) -> [String: Any] {
    [
      "type": "memoryReviewCard",
      "id": "ds_1:memories",
      "summaryId": "ds_1",
      "date": "2026-09-01",
      "items": items,
    ]
  }

  func testCodecRoundTripsAMemoryReviewCard() throws {
    let wire = reviewBlockJSON(items: [
      ["memoryId": "mem_1", "content": "Prefers async standups.", "category": "system"],
      ["memoryId": "mem_2", "content": "Ships on Wednesdays.", "category": "interesting"],
    ])
    let decoded = ChatContentBlockCodec.decode([wire])
    XCTAssertEqual(decoded.count, 1)
    guard case .memoryReviewCard(let id, let summaryId, let date, let items) = decoded[0] else {
      return XCTFail("expected a memoryReviewCard block, got \(decoded)")
    }
    XCTAssertEqual(id, "ds_1:memories")
    XCTAssertEqual(summaryId, "ds_1")
    XCTAssertEqual(date, "2026-09-01")
    XCTAssertEqual(items.map(\.memoryID), ["mem_1", "mem_2"])
    XCTAssertEqual(items.map(\.category), ["system", "interesting"])

    let encoded = ChatContentBlockCodec.encodeArray(decoded)
    let reDecoded = ChatContentBlockCodec.decode(encoded)
    XCTAssertEqual(reDecoded.count, 1)
    guard case .memoryReviewCard(_, _, _, let reItems) = reDecoded[0] else {
      return XCTFail("round trip lost the block: \(reDecoded)")
    }
    XCTAssertEqual(reItems, items)
  }

  func testCodecRoundTripsThroughTheMessageMetadataEnvelope() throws {
    let block = ChatContentBlock.memoryReviewCard(
      id: "ds_1:memories", summaryId: "ds_1", date: "2026-09-01",
      items: [MemoryReviewItem(memoryID: "mem_1", content: "Prefers async standups.", category: "system")])
    let metadata = ChatContentBlockCodec.mergeIntoMessageMetadata(nil, contentBlocks: [block])
    let recovered = ChatContentBlockCodec.decodeFromMessageMetadata(metadata)
    XCTAssertEqual(recovered.count, 1)
    XCTAssertEqual(recovered.first?.id, "ds_1:memories")
  }

  /// A card with nothing votable in it is not a card. Dropping it here is what keeps an empty
  /// frame off the transcript.
  func testCodecDropsAReviewCardWithNoUsableRows() {
    XCTAssertTrue(ChatContentBlockCodec.decode([reviewBlockJSON(items: [])]).isEmpty)
    XCTAssertTrue(
      ChatContentBlockCodec.decode([
        reviewBlockJSON(items: [["memoryId": "", "content": "no id"], ["memoryId": "mem", "content": " "]])
      ]).isEmpty)
  }

  // MARK: - Chat-first block validation

  func testValidationAcceptsAMemoryReviewCardInBothDirections() throws {
    let journalShaped: [String: Any] = [
      "blocks": [
        reviewBlockJSON(items: [["memoryId": "mem_1", "content": "Prefers async standups.", "category": "system"]])
      ]
    ]
    let backend = try XCTUnwrap(ChatFirstBlockWire.backendBlocks(from: journalShaped))
    XCTAssertEqual(backend.count, 1)
    XCTAssertEqual(backend[0]["type"] as? String, "memoryReviewCard")
    XCTAssertEqual(backend[0]["summary_id"] as? String, "ds_1")
    let backendItems = try XCTUnwrap(backend[0]["items"] as? [[String: Any]])
    XCTAssertEqual(backendItems.first?["memory_id"] as? String, "mem_1")

    var receiptBlock = backend[0]
    receiptBlock["id"] = "ds_1:memories"
    let receipt = ChatFirstBlockValidationReceipt(
      accepted: true, code: "ok", blocks: [OmiAnyCodable(receiptBlock)])
    let journal = try XCTUnwrap(ChatFirstBlockWire.journalBlocks(from: receipt))
    XCTAssertEqual(journal.count, 1)
    let decoded = ChatContentBlockCodec.decode(journal)
    guard case .memoryReviewCard(_, let summaryId, _, let items) = try XCTUnwrap(decoded.first) else {
      return XCTFail("validation round trip lost the block: \(decoded)")
    }
    XCTAssertEqual(summaryId, "ds_1")
    XCTAssertEqual(items.map(\.memoryID), ["mem_1"])
  }

  func testValidationRejectsAMemoryReviewCardWithNoItems() {
    XCTAssertNil(ChatFirstBlockWire.backendBlocks(from: ["blocks": [reviewBlockJSON(items: [])]]))
    XCTAssertNil(
      ChatFirstBlockWire.backendBlocks(from: [
        "blocks": [reviewBlockJSON(items: [["content": "no id at all"]])]
      ]))
  }

  // MARK: - Reducer

  private func drive(
    _ start: MemoryReviewRowModel = MemoryReviewRowModel(),
    events: [MemoryReviewEvent]
  ) -> (MemoryReviewRowModel, [MemoryReviewEffect]) {
    var model = start
    var effects: [MemoryReviewEffect] = []
    for event in events {
      let (next, effect) = MemoryReviewReducer.reduce(model, event)
      model = next
      effects.append(effect)
    }
    return (model, effects)
  }

  func testAcceptShowsConfirmedOptimisticallyAndSettlesOnSuccess() {
    let (pending, effects) = drive(events: [.accept])
    XCTAssertEqual(effects, [.review(keep: true)])
    XCTAssertEqual(pending.displayed, .accepted)
    XCTAssertEqual(pending.statusText, "Confirmed. I'll act on this.")
    XCTAssertTrue(pending.isBusy)
    XCTAssertFalse(pending.isFaded)

    let (settled, more) = drive(pending, events: [.requestSucceeded(.accept)])
    // Success re-reads the memory rather than trusting the override indefinitely.
    XCTAssertEqual(more, [.refreshLiveState])
    XCTAssertEqual(settled.live, .accepted)
    XCTAssertNil(settled.optimistic)
    XCTAssertFalse(settled.isBusy)
  }

  func testRejectFadesTheRowButKeepsIt() {
    let (model, effects) = drive(events: [.reject, .requestSucceeded(.reject)])
    XCTAssertEqual(effects.first, .review(keep: false))
    XCTAssertEqual(model.displayed, .rejected)
    XCTAssertEqual(model.statusText, "Dropped. I'll avoid facts like this.")
    XCTAssertTrue(model.isFaded)
    XCTAssertTrue(model.isSettled)
  }

  /// The honest failure: the row goes back exactly where it was, and says so.
  func testAFailedVerdictRevertsAndSaysSo() {
    let (model, _) = drive(events: [.accept, .requestFailed(.accept)])
    XCTAssertEqual(model.displayed, .none)
    XCTAssertNil(model.optimistic)
    XCTAssertNil(model.statusText)
    XCTAssertEqual(model.errorMessage, MemoryReviewReducer.failureMessage)
    XCTAssertFalse(model.isBusy)
  }

  func testAFailedEditRevertsToThePreviousSettledState() {
    var settled = MemoryReviewRowModel()
    settled.live = .accepted
    let (model, _) = drive(
      settled, events: [.beginEdit(prefill: "old"), .draftChanged("new"), .saveEdit, .requestFailed(.edit)])
    XCTAssertEqual(model.displayed, .accepted)
    XCTAssertEqual(model.errorMessage, MemoryReviewReducer.failureMessage)
  }

  func testEditSavesTheTrimmedDraftAndReadsUpdated() {
    let (model, effects) = drive(events: [
      .beginEdit(prefill: "Prefers async standups."),
      .draftChanged("  Prefers written standups.  "),
      .saveEdit,
    ])
    XCTAssertEqual(effects.last, .edit(content: "Prefers written standups."))
    XCTAssertFalse(model.isEditing)
    // An edit is not a promotion: the consolidation job still decides, so the copy is "Updated."
    XCTAssertEqual(model.statusText, "Updated.")
    XCTAssertEqual(model.displayed, .updated)
  }

  func testEscapeCancelsAnEditWithoutMutatingAnything() {
    let (model, effects) = drive(events: [.beginEdit(prefill: "Prefers async standups."), .cancelEdit])
    XCTAssertEqual(effects, [.none, .none])
    XCTAssertFalse(model.isEditing)
    XCTAssertEqual(model.displayed, .none)
  }

  /// Blanking the field and saving is a cancel, not a request that empties the memory.
  func testSavingAnEmptyDraftMutatesNothing() {
    let (model, effects) = drive(events: [.beginEdit(prefill: "Something"), .draftChanged("   "), .saveEdit])
    XCTAssertEqual(effects.last, MemoryReviewEffect.none)
    XCTAssertFalse(model.isEditing)
    XCTAssertEqual(model.displayed, .none)
  }

  func testASecondClickWhileARequestIsInFlightIsIgnored() {
    let (model, effects) = drive(events: [.accept, .reject, .beginEdit(prefill: "x")])
    XCTAssertEqual(effects, [.review(keep: true), .none, .none])
    XCTAssertEqual(model.inFlight, .accept)
    XCTAssertEqual(model.displayed, .accepted)
  }

  /// Render derives the row from the memory, so a vote made on the phone shows on the Mac.
  func testLiveStateFromTheMemoryDrivesTheRow() {
    let (model, _) = drive(events: [.liveStateLoaded(.rejected)])
    XCTAssertEqual(model.displayed, .rejected)
    XCTAssertTrue(model.isSettled)
  }

  /// The local mirror can lag the write it is being asked to confirm; an empty read must not
  /// erase a verdict this device just made, in flight or already settled.
  func testAnEmptyLiveReadDoesNotEraseAVerdictThisDeviceMade() {
    let (pending, _) = drive(events: [.accept])
    let (inFlight, _) = drive(pending, events: [.liveStateLoaded(.none)])
    XCTAssertEqual(inFlight.displayed, .accepted)

    let (settled, _) = drive(pending, events: [.requestSucceeded(.accept), .liveStateLoaded(.none)])
    XCTAssertEqual(settled.displayed, .accepted)
  }

  /// But a verdict made on another device does land, which is the whole reason the row reads the
  /// memory instead of remembering its own clicks.
  func testALiveReadFromAnotherDeviceOverridesTheRow() {
    let (settled, _) = drive(events: [.accept, .requestSucceeded(.accept)])
    let (model, _) = drive(settled, events: [.liveStateLoaded(.updated)])
    XCTAssertEqual(model.displayed, .updated)
    XCTAssertEqual(model.statusText, "Updated.")
  }

  // MARK: - Live verdict derivation

  func testVerdictReadsRejectionFirstThenCorrectionThenAcceptance() {
    let item = MemoryReviewItem(memoryID: "mem_1", content: "Prefers async standups.", category: "system")
    XCTAssertEqual(
      LiveMemoryReviewStateReader.verdict(for: item, memory: memory(content: item.content, review: false)),
      .rejected)
    XCTAssertEqual(
      LiveMemoryReviewStateReader.verdict(
        for: item, memory: memory(content: "Prefers written standups.", review: true)),
      .updated)
    XCTAssertEqual(
      LiveMemoryReviewStateReader.verdict(for: item, memory: memory(content: item.content, review: true)),
      .accepted)
    XCTAssertEqual(
      LiveMemoryReviewStateReader.verdict(for: item, memory: memory(content: " \(item.content) ", review: nil)),
      .none)
  }

  // MARK: - Live read

  /// A failed mirror read used to burn the once-per-mount flag: every row then read as unreviewed
  /// for as long as the card stayed mounted, indistinguishable from a day nobody voted on.
  @MainActor
  func testAFailedLiveReadIsRetriedInsteadOfSettlingEveryRowAsUnreviewed() async {
    let reader = FlakyStateReader()
    let item = MemoryReviewItem(memoryID: "mem_1", content: "Prefers async standups.")
    let store = MemoryReviewCardStore(
      items: [item], source: .dailySummaryChat, mutator: UnusedMutator(), stateReader: reader)

    await store.loadLiveStateIfNeeded()
    XCTAssertEqual(reader.reads, 1)
    XCTAssertEqual(store.row("mem_1").displayed, .none)

    reader.result = ["mem_1": .accepted]
    await store.loadLiveStateIfNeeded()
    XCTAssertEqual(reader.reads, 2)
    XCTAssertEqual(store.row("mem_1").displayed, .accepted)

    // Once it has succeeded the section stops reading: it is chrome, not a poller.
    await store.loadLiveStateIfNeeded()
    XCTAssertEqual(reader.reads, 2)
  }

  // MARK: - Telemetry shape

  func testTelemetryCategoryStaysBounded() {
    XCTAssertEqual(AnalyticsManager.boundedMemoryCategory("system"), "system")
    XCTAssertEqual(AnalyticsManager.boundedMemoryCategory("workflow"), "workflow")
    XCTAssertEqual(AnalyticsManager.boundedMemoryCategory("something_new"), "other")
    XCTAssertEqual(AnalyticsManager.boundedMemoryCategory(""), "unknown")
  }

  // MARK: - Harness handle (memory-review.yaml)

  /// The bridge reaches a mounted card through this handle; without it `memory-review.yaml` could
  /// see a card render but never read which rows it bound or vote on one.
  @MainActor
  func testTheMountedHandleIsIdentityCheckedAcrossARebuild() {
    let first = store(items: [MemoryReviewItem(memoryID: "mem_1", content: "One.")])
    let second = store(items: [MemoryReviewItem(memoryID: "mem_2", content: "Two.")])

    MemoryReviewCardRegistry.register(first, enabled: true)
    MemoryReviewCardRegistry.register(second, enabled: true)
    // The card rebuilds its section when the rows change, and both are mounted for a frame. The
    // outgoing one must not clear the handle the incoming one just took.
    MemoryReviewCardRegistry.unregister(first)
    XCTAssertTrue(MemoryReviewCardRegistry.mounted === second)

    MemoryReviewCardRegistry.unregister(second)
    XCTAssertNil(MemoryReviewCardRegistry.mounted)
  }

  @MainActor
  func testAProductionBundleRegistersNothing() {
    // Compared against whatever was mounted rather than asserted nil, so the test says the same
    // thing whichever order the suite runs in.
    let before = MemoryReviewCardRegistry.mounted
    MemoryReviewCardRegistry.register(
      store(items: [MemoryReviewItem(memoryID: "mem_1", content: "One.")]), enabled: false)
    XCTAssertTrue(MemoryReviewCardRegistry.mounted === before)
  }

  // MARK: - Fixture wire shape

  /// Pinned against `backend/tests/unit/test_daily_summary_e2e_fixture.py`: the seed writes
  /// `memory_id`, and a rename on either side leaves the card rendering no rows at all.
  func testTheSeedRequestUsesTheKeysTheFixtureRouterReads() throws {
    let request = MemoryReviewFixture.SeedRequest(
      memories: [
        MemoryReviewFixture.WireMemory(memoryID: "mem_1", content: "One.", category: "system")
      ])
    let json = try XCTUnwrap(
      JSONSerialization.jsonObject(with: try JSONEncoder().encode(request)) as? [String: Any])
    let memories = try XCTUnwrap(json["memories"] as? [[String: Any]])
    XCTAssertEqual(memories[0]["memory_id"] as? String, "mem_1")
    XCTAssertEqual(memories[0]["content"] as? String, "One.")
    XCTAssertEqual(memories[0]["category"] as? String, "system")
  }

  func testTheSeedResponseDecodesTheFixtureRouterReply() throws {
    let response = try JSONDecoder().decode(
      MemoryReviewFixture.SeedResponse.self,
      from: Data(
        """
        {"status":"ok","summary_id":"dev-harness-daily-summary-2026-03-04",
         "date":"2026-03-04","memories_learned":4}
        """.utf8))
    XCTAssertEqual(response.summaryID, "dev-harness-daily-summary-2026-03-04")
    XCTAssertEqual(response.memoriesLearned, 4)
  }

  /// The flow seeds four and asserts three rows, so the catalog must be able to overfill the card.
  @MainActor
  func testTheFixtureCatalogCanOverfillTheCard() {
    XCTAssertGreaterThan(MemoryReviewFixture.catalog.count, MemoryReviewSection.maxRows)
    XCTAssertNil(MemoryReviewFixture.rows(count: 0))
    XCTAssertNil(MemoryReviewFixture.rows(count: MemoryReviewFixture.catalog.count + 1))
    // Asserted verbatim by `memory-review.yaml` S6.
    XCTAssertEqual(
      MemoryReviewFixture.rows(count: 4)?.map(\.content).first,
      "Prefers async standups over daily calls.")
    XCTAssertEqual(MemoryReviewFixture.rows(count: 4)?.count, 4)
  }

  @MainActor
  func testOnlyTheTwoDrivableVerdictsAreAccepted() {
    XCTAssertEqual(MemoryReviewFixture.event(for: "accept"), .accept)
    XCTAssertEqual(MemoryReviewFixture.event(for: "reject"), .reject)
    // `edit` needs a draft the row view owns, so the bridge refuses rather than half-driving it.
    XCTAssertNil(MemoryReviewFixture.event(for: "edit"))
    XCTAssertNil(MemoryReviewFixture.event(for: ""))
  }

  /// What the bridge reports is the row's own model, so the flow's expectations and the reducer
  /// cannot drift: this asserts the exact strings `memory-review.yaml` S7 pins.
  @MainActor
  func testRowDetailReportsTheSettledRowTheFlowAsserts() async {
    let item = MemoryReviewItem(memoryID: "mem_1", content: "Prefers async standups.", category: "system")
    let card = store(items: [item])

    let before = MemoryReviewFixture.rowDetail(index: 0, item: item, store: card)
    XCTAssertEqual(before["row0_id"], "mem_1")
    XCTAssertEqual(before["row0_category"], "About You")
    XCTAssertEqual(before["row0_verdict"], "none")
    XCTAssertEqual(before["row0_settled"], "false")

    card.send(.accept, to: item)
    _ = await MemoryReviewFixture.waitForSettled(store: card, item: item, timeoutMs: 2_000)

    let after = MemoryReviewFixture.rowDetail(index: 0, item: item, store: card)
    XCTAssertEqual(after["row0_verdict"], "accepted")
    XCTAssertEqual(after["row0_settled"], "true")
    XCTAssertEqual(after["row0_status"], "Confirmed. I'll act on this.")
    XCTAssertEqual(after["row0_error"], "")
    XCTAssertEqual(after["row0_busy"], "false")
  }

  // MARK: - Helpers

  /// Fails until it is given a result, so "the read failed" and "nobody has voted" are two
  /// different observable outcomes rather than the same empty dictionary.
  private final class FlakyStateReader: MemoryReviewStateReading, @unchecked Sendable {
    struct ReadFailed: Error {}

    var result: [String: MemoryReviewVerdict]?
    private(set) var reads = 0

    func verdicts(for items: [MemoryReviewItem]) async throws -> [String: MemoryReviewVerdict] {
      reads += 1
      guard let result else { throw ReadFailed() }
      return result
    }
  }

  @MainActor
  private func store(items: [MemoryReviewItem]) -> MemoryReviewCardStore {
    MemoryReviewCardStore(
      items: items, source: .dailySummaryChat, mutator: UnusedMutator(),
      stateReader: FlakyStateReader(), analytics: { _, _, _, _ in })
  }

  private struct UnusedMutator: MemoryReviewMutating {
    func review(memoryID: String, keep: Bool) async throws {}
    func edit(memoryID: String, content: String) async throws {}
  }

  private func memory(content: String, review: Bool?) -> ServerMemory {
    ServerMemory(
      id: "mem_1",
      content: content,
      category: .system,
      createdAt: Date(timeIntervalSince1970: 1_000),
      updatedAt: Date(timeIntervalSince1970: 1_000),
      conversationId: nil,
      reviewed: review != nil,
      userReview: review,
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
      inputDeviceName: nil)
  }
}
