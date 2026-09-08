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

  func testPeopleAreKeptApartFromTheUser() {
    var prints = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: nil, embedding: vector(0), speechSeconds: 20, isEnrolled: true), to: [])
    prints = LocalVoiceprintStore.applying(
      VoiceprintUpdate(personId: "anna", embedding: vector(1), speechSeconds: 8, isEnrolled: true), to: prints)
    XCTAssertEqual(prints.map(\.personId), [nil, "anna"])
  }
}
