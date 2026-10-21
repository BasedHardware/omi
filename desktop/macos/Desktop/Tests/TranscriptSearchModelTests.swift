import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

final class TranscriptSearchModelTests: XCTestCase {
  private let transcript: [(id: String, text: String)] = [
    (id: "a", text: "Let's meet at the Café tomorrow."),
    (id: "b", text: "Which cafe? The cafe on Main?"),
    (id: "c", text: "No idea."),
    (id: "d", text: "CAFE hours are short."),
  ]

  private func search(_ query: String) -> TranscriptSearchModel {
    var model = TranscriptSearchModel()
    model.update(query: query, segments: transcript)
    return model
  }

  private func matchedText(_ model: TranscriptSearchModel, in id: String) -> [String] {
    let text = transcript.first { $0.id == id }?.text ?? ""
    return model.ranges(inSegment: id).map { String(text[$0]) }
  }

  func testMatchingIgnoresCaseAndDiacriticsAcrossSpeakers() {
    let model = search("cafe")
    XCTAssertEqual(model.matches.map(\.segmentID), ["a", "b", "b", "d"])
    XCTAssertEqual(matchedText(model, in: "a"), ["Café"])
    XCTAssertEqual(matchedText(model, in: "b"), ["cafe", "cafe"])
    XCTAssertEqual(matchedText(model, in: "d"), ["CAFE"])
    XCTAssertEqual(model.ranges(inSegment: "c"), [])
    XCTAssertEqual(model.countLabel, "1 of 4")
  }

  func testEmptyOrBlankQueryMatchesNothingAndShowsNoCount() {
    for query in ["", "   ", "\n"] {
      let model = search(query)
      XCTAssertFalse(model.isActive)
      XCTAssertTrue(model.matches.isEmpty)
      XCTAssertNil(model.currentMatch)
      XCTAssertEqual(model.countLabel, "")
      XCTAssertEqual(model.ranges(inSegment: "a"), [])
    }
  }

  func testQueryWithoutMatchesSaysSoAndStepsNowhere() {
    var model = search("zebra")
    XCTAssertTrue(model.isActive)
    XCTAssertEqual(model.countLabel, "No matches")
    model.next()
    model.previous()
    XCTAssertNil(model.currentIndex)
  }

  func testNextAndPreviousWrapAround() {
    var model = search("cafe")
    model.previous()
    XCTAssertEqual(model.currentIndex, 3)
    XCTAssertEqual(model.countLabel, "4 of 4")
    model.next()
    XCTAssertEqual(model.countLabel, "1 of 4")
    model.next()
    model.next()
    XCTAssertEqual(model.currentMatch?.segmentID, "b")
    XCTAssertEqual(model.countLabel, "3 of 4")
  }

  func testCurrentRangeBelongsOnlyToTheCurrentSegment() {
    var model = search("cafe")
    model.next()
    XCTAssertNil(model.currentRange(inSegment: "a"))
    XCTAssertEqual(model.currentRange(inSegment: "b"), model.ranges(inSegment: "b").first)
  }

  func testEveryStepRequestsARevealEvenOnASingleMatch() {
    var model = search("idea")
    let afterSearch = model.revealRequest
    model.next()
    XCTAssertEqual(model.currentIndex, 0)
    XCTAssertEqual(model.revealRequest, afterSearch + 1)
  }

  func testRerunningTheSameQueryKeepsTheCurrentMatch() {
    var model = search("cafe")
    model.next()
    model.next()
    model.update(query: "cafe", segments: transcript + [(id: "e", text: "cafe again")])
    XCTAssertEqual(model.countLabel, "3 of 5")
    model.update(query: "Cafe", segments: transcript)
    XCTAssertEqual(model.countLabel, "1 of 4")
  }

  func testMatchesDoNotOverlap() {
    XCTAssertEqual(TranscriptSearchModel.ranges(of: "aa", in: "aaaa").count, 2)
  }

  func testHighlightingPaintsOnlyTheMatchesAndTheCurrentOneStronger() {
    let text = "cafe and Café"
    let ranges = TranscriptSearchModel.ranges(of: "cafe", in: text)
    let attributed = TranscriptSearchModel.highlighted(
      text, ranges: ranges, current: ranges.last, matchColor: .yellow, currentColor: .orange)
    let painted = attributed.runs.compactMap { run -> (String, Color)? in
      guard let color = run.backgroundColor else { return nil }
      return (String(attributed[run.range].characters), color)
    }
    XCTAssertEqual(painted.map(\.0), ["cafe", "Café"])
    XCTAssertEqual(painted.map(\.1), [.yellow, .orange])
    XCTAssertEqual(String(attributed.characters), text)
  }
}

/// The live capture and the saved transcript draw one bubble, so a turn must be named, tinted and
/// avatared the same way whichever source it came from.
@MainActor
final class SharedTranscriptBubbleTests: XCTestCase {
  private func saved(speaker: String, isUser: Bool, personName: String? = nil) -> SpeakerBubbleView {
    let segment = TranscriptSegment(
      id: "s", backendId: nil, text: "Hello", speaker: speaker, isUser: isUser, personId: nil, start: 3, end: 4)
    return SpeakerBubbleView(segment: segment, isUser: isUser, personName: personName)
  }

  private func live(speaker: Int, isUser: Bool, personName: String? = nil) -> SpeakerBubbleView {
    SpeakerBubbleView(
      liveSegment: SpeakerSegment(speaker: speaker, text: "Hello", start: 3, end: 4, isUser: isUser),
      personName: personName)
  }

  func testLiveAndSavedOtherSpeakerRenderIdentically() {
    let pairs = [
      (saved(speaker: "SPEAKER_02", isUser: false), live(speaker: 2, isUser: false)),
      (saved(speaker: "SPEAKER_00", isUser: false), live(speaker: 0, isUser: false)),
      (
        saved(speaker: "SPEAKER_01", isUser: false, personName: "ada"),
        live(speaker: 1, isUser: false, personName: "ada")
      ),
    ]
    for (savedBubble, liveBubble) in pairs {
      XCTAssertEqual(liveBubble.speakerLabel, savedBubble.speakerLabel)
      XCTAssertEqual(liveBubble.avatarInitial, savedBubble.avatarInitial)
      XCTAssertEqual(liveBubble.bubbleColor, savedBubble.bubbleColor)
    }
    XCTAssertEqual(live(speaker: 2, isUser: false).speakerLabel, "Speaker 3")
    XCTAssertEqual(
      live(speaker: 2, isUser: false).bubbleColor, PageGlass.speakerTints[2 % PageGlass.speakerTints.count])
    XCTAssertEqual(live(speaker: 1, isUser: false, personName: "ada").avatarInitial, "A")
  }

  func testTheUserBubbleIsNeutralInBothSources() {
    let liveBubble = live(speaker: 0, isUser: true)
    XCTAssertEqual(liveBubble.bubbleColor, Ink.rowFillHover)
    XCTAssertEqual(liveBubble.bubbleColor, saved(speaker: "SPEAKER_00", isUser: true).bubbleColor)
    XCTAssertEqual(liveBubble.speakerLabel, "You")
    XCTAssertEqual(liveBubble.avatarInitial, "Y")
  }
}
