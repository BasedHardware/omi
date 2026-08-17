import XCTest

@testable import Omi_Computer

final class ContextBucketSyncPayloadTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)

  private func bucket(
    _ bucketID: String = "bucket-1",
    workstreamID: String? = nil,
    displayLabel: String? = "Design doc"
  ) -> ContextBucketSyncBucket {
    ContextBucketSyncBucket(
      bucketID: bucketID,
      subjectKind: "document",
      subjectID: "design-doc",
      workstreamID: workstreamID,
      displayLabel: displayLabel,
      notifyWorthiness: 0.7,
      visitCount: 3,
      lastVisitedAt: now,
      updatedAt: now)
  }

  private func fact(
    _ factID: String = "fact-1",
    bucketID: String = "bucket-1",
    workstreamTag: String? = nil,
    expiresAt: Date? = nil
  ) -> ContextBucketSyncFact {
    ContextBucketSyncFact(
      factID: factID,
      bucketID: bucketID,
      statement: "Ship the parity pack",
      identifiers: ["parity-pack"],
      confidence: 0.9,
      notifyWorthiness: 0.8,
      dispositionState: "none",
      workstreamTag: workstreamTag,
      expiresAt: expiresAt,
      updatedAt: now)
  }

  private func buckets(in body: [String: Any]) -> [[String: Any]] {
    (body["buckets"] as? [[String: Any]]) ?? []
  }

  private func facts(in bucket: [String: Any]) -> [[String: Any]] {
    (bucket["facts"] as? [[String: Any]]) ?? []
  }

  func testBodyGroupsFactsUnderTheirBucket() {
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc",
      buckets: [bucket("bucket-1"), bucket("bucket-2")],
      facts: [fact("fact-1"), fact("fact-2", bucketID: "bucket-2"), fact("fact-3")])

    let published = buckets(in: body)
    XCTAssertEqual(body["device_id"] as? String, "macos_abc")
    XCTAssertEqual(published.count, 2)
    XCTAssertEqual(facts(in: published[0]).compactMap { $0["fact_id"] as? String }, ["fact-1", "fact-3"])
    XCTAssertEqual(facts(in: published[1]).compactMap { $0["fact_id"] as? String }, ["fact-2"])
  }

  func testFactWithoutItsBucketIsDroppedRatherThanOrphaned() {
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc",
      buckets: [bucket("bucket-1")],
      facts: [fact("fact-1"), fact("stray", bucketID: "bucket-missing")])

    let published = buckets(in: body)
    XCTAssertEqual(published.count, 1)
    XCTAssertEqual(facts(in: published[0]).compactMap { $0["fact_id"] as? String }, ["fact-1"])
  }

  func testPayloadCarriesNoScreenContentAndNoUnresolvableProvenance() {
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc", buckets: [bucket()], facts: [fact()])

    let payload = facts(in: buckets(in: body)[0])[0]
    // The device boundary: nothing quoted from the screen may appear in a payload.
    for forbidden in ["evidence_text", "narrative", "raw_context_key", "normalized_context_key"] {
      XCTAssertNil(payload[forbidden], "\(forbidden) must never be published")
    }
    // The device has no id a consumer could resolve back to a screen frame, so it
    // must not assert provenance it cannot support.
    XCTAssertNil(payload["evidence_refs"])
  }

  func testOptionalFieldsAreOmittedRatherThanSentAsNull() {
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc",
      buckets: [bucket(workstreamID: nil, displayLabel: nil)],
      facts: [fact(workstreamTag: nil, expiresAt: nil)])

    let published = buckets(in: body)[0]
    XCTAssertNil(published["workstream_id"])
    XCTAssertNil(published["display_label"])
    let payload = facts(in: published)[0]
    XCTAssertNil(payload["workstream_tag"])
    XCTAssertNil(payload["expires_at"])
  }

  func testOptionalFieldsAreSentWhenPresent() {
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc",
      buckets: [bucket(workstreamID: "ws-1", displayLabel: "Design doc")],
      facts: [fact(workstreamTag: "ws-1", expiresAt: now)])

    let published = buckets(in: body)[0]
    XCTAssertEqual(published["workstream_id"] as? String, "ws-1")
    XCTAssertEqual(published["display_label"] as? String, "Design doc")
    XCTAssertEqual(facts(in: published)[0]["workstream_tag"] as? String, "ws-1")
    XCTAssertNotNil(facts(in: published)[0]["expires_at"])
  }

  func testRetractionIsSplitAcrossRequestsRatherThanTruncated() {
    let ids = (0..<(ContextBucketSyncPayload.purgeBatchSize * 2 + 7)).map { "bucket-\($0)" }

    let batches = ContextBucketSyncPayload.purgeBatches(bucketIDs: ids)

    XCTAssertEqual(batches.count, 3)
    XCTAssertEqual(batches.flatMap { $0 }, ids, "every excluded bucket must still be retracted")
    XCTAssertTrue(batches.allSatisfy { $0.count <= ContextBucketSyncPayload.purgeBatchSize })
  }

  func testBodyRespectsTheBackendBucketLimit() {
    let overLimit = (0...ContextBucketSyncPayload.bucketLimit).map { bucket("bucket-\($0)") }

    let body = ContextBucketSyncPayload.body(deviceID: "macos_abc", buckets: overLimit, facts: [])

    XCTAssertEqual(buckets(in: body).count, ContextBucketSyncPayload.bucketLimit)
  }

  func testBodyIsJSONSerializable() throws {
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc",
      buckets: [bucket(workstreamID: "ws-1")],
      facts: [fact(workstreamTag: "ws-1", expiresAt: now)])

    XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: body))
  }

  func testPurgeBodyCarriesExactlyWhatItWasGiven() {
    let body = ContextBucketSyncPayload.purgeBody(bucketIDs: ["bucket-1", "bucket-2"])

    XCTAssertEqual(body["bucket_ids"] as? [String], ["bucket-1", "bucket-2"])
  }

}
