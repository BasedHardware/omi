import XCTest

@testable import Omi_Computer

/// What a People "Rebuild" is allowed to change about a remembered voice, and what belongs to
/// the person and must survive it.
final class LocalSpeakerDiarizerRebuildTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)
  private var directory: URL?

  private func makeStore() throws -> LocalVoiceprintStore {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("diarizer-rebuild-\(UUID().uuidString)", isDirectory: true)
    directory = root
    return LocalVoiceprintStore(fileURL: root.appendingPathComponent(LocalVoiceprintStore.fileName))
  }

  override func tearDown() async throws {
    if let directory { try? FileManager.default.removeItem(at: directory) }
    try await super.tearDown()
  }

  private func vector(_ axis: Int) -> [Float] {
    var v = [Float](repeating: 0, count: 256)
    v[axis] = 1
    return v
  }

  private func diarizer(_ store: LocalVoiceprintStore) -> LocalSpeakerDiarizer {
    let fixedNow = now
    return LocalSpeakerDiarizer(
      store: store,
      loadModels: { throw CocoaError(.featureUnsupported) },
      now: { fixedNow })
  }

  func testRebuildKeepsAPinnedVoicePinnedAndItsClipsWhenItHeardNone() async throws {
    let store = try makeStore()
    let clip = try XCTUnwrap(store.addSample(personId: "anna", samples: [Float](repeating: 0.2, count: 16_000)))
    store.save([
      StoredVoiceprint(
        personId: "anna", embedding: vector(0), speechSeconds: 40, updatedAt: now.addingTimeInterval(-86_400),
        isEnrolled: true, isFavorite: true, useScore: 9, lastUsedAt: now.addingTimeInterval(-86_400),
        sampleFiles: [clip])
    ])

    let subject = diarizer(store)
    let saved = await subject.applyRebuild([
      RebuiltVoice(
        personId: "anna", embeddings: [vector(1)], speechSeconds: 120, clips: [], conversationCount: 3, lastHeardAt: now
      )
    ])

    XCTAssertEqual(saved, 0)
    let summaries = await subject.voiceSummaries()
    let summary = try XCTUnwrap(summaries.first { $0.personId == "anna" })
    XCTAssertTrue(summary.isFavorite, "a pin is the person's choice and survives a rebuild")
    XCTAssertEqual(summary.speechSeconds, 120, "the voiceprint itself is replaced by what the rebuild heard")
    XCTAssertEqual(summary.sampleURLs.count, 1, "a rebuild that heard no audio must not leave the voice mute")
    XCTAssertTrue(FileManager.default.fileExists(atPath: summary.sampleURLs[0].path))
    XCTAssertEqual(summary.lastHeardAt, now)
    // Reloading the store sees the same thing: the change was persisted, not just in memory.
    XCTAssertEqual(store.load().first?.isFavorite, true)
    // Carried over and aged one day (9 × 2^(-1/14) ≈ 8.57), not reset to the rebuild's count of 3.
    XCTAssertEqual(try XCTUnwrap(store.load().first).useScore, 8.57, accuracy: 0.02)
  }

  func testRebuildWithAudioReplacesTheClips() async throws {
    let store = try makeStore()
    let stale = try XCTUnwrap(store.addSample(personId: "bob", samples: [Float](repeating: 0.2, count: 16_000)))
    store.save([
      StoredVoiceprint(
        personId: "bob", embedding: vector(0), speechSeconds: 10, updatedAt: now, isEnrolled: true,
        sampleFiles: [stale])
    ])

    let subject = diarizer(store)
    let saved = await subject.applyRebuild([
      RebuiltVoice(
        personId: "bob", embeddings: [vector(2)], speechSeconds: 30,
        clips: [[Float](repeating: 0.1, count: 32_000), [Float](repeating: 0.1, count: 16_000)],
        conversationCount: 2, lastHeardAt: now)
    ])

    XCTAssertEqual(saved, 2)
    let summaries = await subject.voiceSummaries()
    let summary = try XCTUnwrap(summaries.first { $0.personId == "bob" })
    XCTAssertEqual(summary.sampleURLs.count, 2)
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: store.sampleURL(for: stale).path),
      "the clips the rebuild replaced are deleted, not orphaned on disk")
  }
}
