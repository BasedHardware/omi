import XCTest

@testable import Omi_Computer

final class LocalVoiceprintStoreTests: XCTestCase {
  private func vector(_ axis: Int) -> [Float] {
    var v = [Float](repeating: 0, count: 256)
    v[axis] = 1
    return v
  }

  func testRoundTripsThroughTheFile() throws {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("voiceprint-store-\(UUID().uuidString)", isDirectory: true)
      .appendingPathComponent(LocalVoiceprintStore.fileName)
    defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
    let store = LocalVoiceprintStore(fileURL: url)
    XCTAssertEqual(store.load(), [])

    let saved = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: nil, embedding: vector(0), speechSeconds: 30, isEnrolled: true), to: [])
    store.save(saved)
    let loaded = store.load()
    XCTAssertEqual(loaded.count, 1)
    XCTAssertNil(loaded.first?.personId)
    XCTAssertEqual(loaded.first?.isEnrolled, true)
    XCTAssertEqual(loaded.first?.embedding.count, 256)
  }

  func testAGuessBlendsIntoAnExistingPrintButAnEnrollmentReplacesAGuess() throws {
    let guessed = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: nil, embedding: vector(0), speechSeconds: 20, isEnrolled: false), to: [])
    let stillGuessed = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: nil, embedding: vector(1), speechSeconds: 20, isEnrolled: false), to: guessed)
    let blended = try XCTUnwrap(stillGuessed.first)
    XCTAssertFalse(blended.isEnrolled)
    XCTAssertEqual(blended.speechSeconds, 40)
    XCTAssertEqual(blended.embedding[0], blended.embedding[1], accuracy: 1e-5, "a guess blends 50/50")

    let enrolled = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: nil, embedding: vector(2), speechSeconds: 5, isEnrolled: true), to: stillGuessed)
    let replaced = try XCTUnwrap(enrolled.first)
    XCTAssertTrue(replaced.isEnrolled)
    XCTAssertEqual(replaced.speechSeconds, 5)
    XCTAssertEqual(replaced.embedding[2], 1, accuracy: 1e-5, "an enrollment replaces a guess outright")
    XCTAssertEqual(enrolled.count, 1)
  }

  /// Files written before favorites, usage and samples existed must still load.
  func testLegacyFileWithoutTheNewFieldsStillDecodes() throws {
    let json = """
      [{"personId":null,"embedding":[1,0],"speechSeconds":30,"updatedAt":"2026-09-07T22:00:00Z","isEnrolled":false}]
      """
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    let prints = try decoder.decode([StoredVoiceprint].self, from: Data(json.utf8))
    XCTAssertEqual(prints.count, 1)
    XCTAssertFalse(prints[0].isFavorite)
    XCTAssertEqual(prints[0].useScore, 0)
    XCTAssertNil(prints[0].lastUsedAt)
    XCTAssertEqual(prints[0].sampleFiles, [])
  }

  func testSamplesAreWrittenAsWavAndRemovedWithTheVoice() throws {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("voiceprint-samples-\(UUID().uuidString)", isDirectory: true)
      .appendingPathComponent(LocalVoiceprintStore.fileName)
    defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
    let store = LocalVoiceprintStore(fileURL: url)
    let tone = (0..<16_000).map { Float(sin(Double($0) * 0.05)) * 0.3 }

    let file = try XCTUnwrap(store.addSample(personId: "anna", samples: tone))
    XCTAssertTrue(file.hasPrefix("anna/"))
    let written = store.sampleURL(for: file)
    XCTAssertTrue(FileManager.default.fileExists(atPath: written.path))
    XCTAssertGreaterThan(try Data(contentsOf: written).count, 30_000, "one second of 16-bit mono audio")

    store.removeAllSamples(personId: "anna")
    XCTAssertFalse(FileManager.default.fileExists(atPath: written.path))
  }

  func testPeopleAreKeptApartFromTheUser() {
    var prints = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: nil, embedding: vector(0), speechSeconds: 20, isEnrolled: true), to: [])
    prints = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: "anna", embedding: vector(1), speechSeconds: 8, isEnrolled: true), to: prints)
    XCTAssertEqual(prints.map(\.personId), [nil, "anna"])
  }
}

extension LocalVoiceprintStoreTests {
  /// Rebuild decodes only the cut it needs; a range in the middle of a file comes back at the
  /// right length and with the right audio.
  func testDecoderReadsOneRangeOfAFile() throws {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("range-\(UUID().uuidString)", isDirectory: true)
      .appendingPathComponent(LocalVoiceprintStore.fileName)
    defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
    let store = LocalVoiceprintStore(fileURL: url)
    // 3 s: silence, then a tone for the middle second, then silence.
    var samples = [Float](repeating: 0, count: 48_000)
    for i in 16_000..<32_000 { samples[i] = Float(sin(Double(i) * 0.05)) * 0.5 }
    let file = try XCTUnwrap(store.addSample(personId: "range", samples: samples))

    let reader = try AudioClipDecoder.Reader(url: store.sampleURL(for: file))
    XCTAssertEqual(reader.durationSeconds, 3, accuracy: 0.01)
    let middle = try reader.read(fromSeconds: 1, toSeconds: 2)
    XCTAssertEqual(middle.count, 16_000, accuracy: 64)
    XCTAssertGreaterThan(middle.map { abs($0) }.max() ?? 0, 0.3, "the tone is in the middle second")
    let leading = try reader.read(fromSeconds: 0, toSeconds: 0.5)
    XCTAssertLessThan(leading.map { abs($0) }.max() ?? 1, 0.01, "the first half second is silent")
    XCTAssertEqual(try AudioClipDecoder.decode16kMono(url: store.sampleURL(for: file)).count, 48_000, accuracy: 64)
  }
}
