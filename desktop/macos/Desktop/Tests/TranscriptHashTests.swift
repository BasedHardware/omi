import XCTest

@testable import Omi_Computer

final class TranscriptHashTests: XCTestCase {
  func testEncodingVersionIsV5() {
    XCTAssertEqual(TranscriptHash.encodingVersion, 5)
  }

  func testKnownAnswerVectorPinsAliceBobToThePythonDigest() {
    let digest = "6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40"
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(speaker: "Alice", text: "I agree"),
        TranscriptHash.Segment(speaker: "Bob", text: "I refuse"),
      ]),
      digest
    )
  }

  func testEmptyListHashesTheEmptyByteString() {
    XCTAssertEqual(
      TranscriptHash.sha256(segments: []),
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    let emptyText = TranscriptHash.sha256(segments: [TranscriptHash.Segment(text: "")])
    XCTAssertEqual(emptyText, "1f4edaaa8c0b550ed42040ed654a8bccfd34e121da991f1b986f9821e3d360a8")
    XCTAssertNotEqual(
      emptyText,
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
  }

  func testHelloWorldAndUnicodeMatchPythonFixtures() {
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(text: "hello"),
        TranscriptHash.Segment(text: "world"),
      ]),
      "8c07ee1d1a21bd1f1f319362b1435d6e875f8e24ef326dc08ecf113e226e3410"
    )
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [TranscriptHash.Segment(text: "café 你好")]),
      "de349219ac8122fb4f1bd000167d933ed6657dff1ad3835e1deb06a2bf79eef5"
    )
  }

  func testAttributionAndSpeakerIdChangeTheDigest() {
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(isUser: true, text: "I approved the transfer")
      ]),
      "51d7fb6fb4e3cf863a1210d21280cbfb91e8dd16d818d9d6208af00470a5e3c9"
    )
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(personId: "alice", text: "I approved the transfer")
      ]),
      "55629d482ae03ac3ca5f315ff39a6ac156e1ada4e4f6428b2a6fb9ec88b36a8d"
    )
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(speakerId: 0, text: "I approved the transfer")
      ]),
      "863cf7938e692d22b06f5b757ad5330a517c87f60d115e5dd97a973fbc248d50"
    )
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(speakerId: 7, text: "I approved the transfer")
      ]),
      "d7dfcd646cda9e7d068693db981c82e11d144d376c800ba0640b611d3768ecdf"
    )
  }

  func testSpeaker07WithoutSpeakerIdDerives7() {
    let fromLabel = TranscriptHash.sha256(segments: [
      TranscriptHash.Segment(speaker: "SPEAKER_07", text: "hello")
    ])
    let explicit = TranscriptHash.sha256(segments: [
      TranscriptHash.Segment(speaker: "SPEAKER_07", speakerId: 7, text: "hello")
    ])
    XCTAssertEqual(fromLabel, explicit)
    XCTAssertEqual(TranscriptHash.derivedSpeakerId("SPEAKER_07"), 7)
  }

  func testPaddedSpeakerAndTextStripToTheSameDigest() {
    XCTAssertEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(speaker: "  SPEAKER_07  ", text: "  hello  ")
      ]),
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(speaker: "SPEAKER_07", text: "hello")
      ])
    )
  }

  func testSwappedAttributionIsADifferentDigest() {
    let original = "6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40"
    XCTAssertNotEqual(
      TranscriptHash.sha256(segments: [
        TranscriptHash.Segment(speaker: "Bob", text: "I agree"),
        TranscriptHash.Segment(speaker: "Alice", text: "I refuse"),
      ]),
      original
    )
  }
}
