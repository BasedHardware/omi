import XCTest

@testable import Omi_Computer

/// Exercises how a person profile finds the memories that belong to one person: the durable
/// `person:<id>` tag written by `PeopleMemoryWriter`, the name-prefix fallback that rescues facts
/// written before tagging existed, and the merge rules between them.
///
/// The fallback assertions run against text produced by the **real** `generateFacts`, so a change to
/// the writer's fact format breaks these tests instead of silently emptying the profile page.
final class PersonMemoriesTests: XCTestCase {

  // MARK: - Fixtures

  /// A name-prefix collision on purpose: "Sam" is a strict prefix of "Samantha".
  private func realFacts() -> [PeopleMemoryWriter.Fact] {
    let people: [[String: Any]] = [
      [
        "id": "sam",
        "name": "Sam",
        "groups": [["name": "Tahoe Trip", "category": "friends"]],
        "channels": [["label": "iMessage"]],
      ],
      [
        "id": "samantha",
        "name": "Samantha",
        "groups": [["name": "Tahoe Trip", "category": "friends"]],
      ],
    ]
    let edges: [[String: Any]] = [["a": "sam", "b": "samantha", "context": ["Tahoe Trip"]]]
    return PeopleMemoryWriter.generateFacts(
      people: people, edges: edges, idName: ["sam": "Sam", "samantha": "Samantha"])
  }

  private func candidate(
    id: String, content: String, tags: [String] = [], secondsAgo: TimeInterval = 0
  ) -> PersonMemoryCandidate {
    PersonMemoryCandidate(
      id: id,
      content: content,
      createdAt: Date(timeIntervalSince1970: 1_800_000_000 - secondsAgo),
      tags: tags)
  }

  // MARK: - Name-prefix fallback

  func testPrefixFallbackMatchesTheWritersRealFactFormat() throws {
    let texts = realFacts().map { $0.text }
    let samFact = try XCTUnwrap(texts.first { $0.hasPrefix("Sam \u{2014}") })
    let samanthaFact = try XCTUnwrap(texts.first { $0.hasPrefix("Samantha \u{2014}") })
    let pairFact = try XCTUnwrap(texts.first { $0.contains("both belong to your") })

    XCTAssertTrue(
      PersonMemoryMatcher.matches(content: samFact, displayName: "Sam"),
      "a per-person fact must match the person it is about")
    XCTAssertTrue(
      PersonMemoryMatcher.matches(content: samanthaFact, displayName: "Samantha"),
      "the same holds for a name that merely contains another")
    XCTAssertTrue(
      PersonMemoryMatcher.matches(content: pairFact, displayName: "Sam"),
      "a pair fact must match the person named first")
    XCTAssertTrue(
      PersonMemoryMatcher.matches(content: pairFact, displayName: "Samantha"),
      "and the person named second")
  }

  func testPrefixFallbackDoesNotStealAnotherPersonWhoseNameSharesThePrefix() {
    let texts = realFacts().map { $0.text }
    for text in texts where text.hasPrefix("Samantha") {
      XCTAssertFalse(
        PersonMemoryMatcher.matches(content: text, displayName: "Sam"),
        "\"Sam\" must never absorb Samantha's facts: \(text)")
    }
    XCTAssertFalse(
      PersonMemoryMatcher.matches(
        content: "Samantha and Bob both belong to your \u{201C}Tahoe Trip\u{201D} group "
          + "\u{2014} they know each other.",
        displayName: "Sam"),
      "a pair fact led by a longer name is not Sam's either")
    XCTAssertFalse(
      PersonMemoryMatcher.matches(
        content: "Bob and Samantha both belong to your \u{201C}Tahoe Trip\u{201D} group "
          + "\u{2014} they know each other.",
        displayName: "Sam"),
      "nor is one where the longer name sits second")
  }

  func testPrefixFallbackIgnoresIncidentalMentions() {
    XCTAssertFalse(
      PersonMemoryMatcher.matches(content: "You met Sam at the airport.", displayName: "Sam"),
      "a name appearing mid-sentence is not a relationship fact about that person")
    XCTAssertFalse(
      PersonMemoryMatcher.matches(content: "Sam and Bob grabbed lunch.", displayName: "Sam"),
      "the pair form requires the writer's own marker, not just a conjunction")
    XCTAssertFalse(
      PersonMemoryMatcher.matches(content: "Sam \u{2014} anything.", displayName: "   "),
      "a blank display name matches nothing")
  }

  // MARK: - Merge rules

  func testTagMatchWinsOverPrefixMatchForTheSameMemory() {
    let tagged = candidate(
      id: "m1", content: "Sam \u{2014} in your group.", tags: ["people_intelligence", "person:sam"])
    let named = candidate(id: "m1", content: "Sam \u{2014} in your group.")

    let merged = PersonMemoryMatcher.merge(
      personID: "sam", displayName: "Sam", tagged: [tagged], named: [named])

    XCTAssertEqual(merged.count, 1, "one memory reached by both paths stays one row")
    XCTAssertTrue(merged[0].isTagged, "the durable tag outranks the name-prefix guess")
  }

  func testDeduplicatesByMemoryIDAcrossBothPaths() {
    let shared = candidate(
      id: "m1", content: "Sam \u{2014} in your group.", tags: ["person:sam"], secondsAgo: 0)
    let taggedOnly = candidate(
      id: "m2", content: "Something the prefix would miss.", tags: ["person:sam"], secondsAgo: 60)
    let namedOnly = candidate(id: "m3", content: "Sam \u{2014} plays chess.", secondsAgo: 120)

    let merged = PersonMemoryMatcher.merge(
      personID: "sam",
      displayName: "Sam",
      tagged: [shared, taggedOnly],
      named: [shared, namedOnly])

    XCTAssertEqual(merged.map { $0.id }, ["m1", "m2", "m3"], "deduped by id, newest first")
    XCTAssertEqual(merged.map { $0.isTagged }, [true, true, false])
  }

  func testTagMatchRequiresTheExactTag() {
    // The store matches tags with a JSON LIKE; a neighbouring id must not leak through.
    let other = candidate(id: "m1", content: "Sammy's fact.", tags: ["person:sammy"])

    let merged = PersonMemoryMatcher.merge(
      personID: "sam", displayName: "Sam", tagged: [other], named: [])

    XCTAssertTrue(merged.isEmpty, "person:sammy is not person:sam")
  }

  // MARK: - Model states

  func testEmptyStoreLoadsWithNoRowsRatherThanFailing() async {
    let model = await PersonMemoriesModel(source: StubPersonMemorySource())

    await model.load(personID: "sam", displayName: "Sam")

    let state = await model.state
    let memories = await model.memories
    XCTAssertEqual(state, .loaded, "no matching memories is a successful empty load, not a failure")
    XCTAssertTrue(memories.isEmpty)
  }

  func testLoadPublishesNewestFirst() async {
    let source = StubPersonMemorySource(
      tagged: [
        candidate(id: "old", content: "Sam \u{2014} a.", tags: ["person:sam"], secondsAgo: 600),
        candidate(id: "new", content: "Sam \u{2014} b.", tags: ["person:sam"], secondsAgo: 0),
      ])
    let model = await PersonMemoriesModel(source: source)

    await model.load(personID: "sam", displayName: "Sam")

    let memories = await model.memories
    XCTAssertEqual(memories.map { $0.id }, ["new", "old"])
  }

  func testStoreErrorSurfacesAsFailedNotAsAnEmptyList() async {
    let model = await PersonMemoriesModel(source: StubPersonMemorySource(shouldThrow: true))

    await model.load(personID: "sam", displayName: "Sam")

    let state = await model.state
    XCTAssertEqual(state, .failed(PersonMemoriesModel.failureMessage))
  }

  func testBlankIdentityIsUnavailable() async {
    let model = await PersonMemoriesModel(source: StubPersonMemorySource())

    await model.load(personID: "  ", displayName: "  ")

    let state = await model.state
    XCTAssertEqual(state, .unavailable, "nothing to look a person up by")
  }

  func testResetReturnsToIdleAndClearsRows() async {
    let source = StubPersonMemorySource(
      tagged: [candidate(id: "m1", content: "Sam \u{2014} a.", tags: ["person:sam"])])
    let model = await PersonMemoriesModel(source: source)
    await model.load(personID: "sam", displayName: "Sam")
    let loaded = await model.memories
    XCTAssertEqual(loaded.count, 1, "precondition: a row was loaded")

    await model.reset()

    let state = await model.state
    let memories = await model.memories
    XCTAssertEqual(state, .idle)
    XCTAssertTrue(memories.isEmpty)
  }
}

/// In-memory stand-in for `MemoryStorage`, so the model's real load path runs without SQLite.
private struct StubPersonMemorySource: PersonMemorySource {
  var tagged: [PersonMemoryCandidate] = []
  var named: [PersonMemoryCandidate] = []
  var shouldThrow = false

  struct Failure: Error {}

  func memories(taggedWith tag: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    if shouldThrow { throw Failure() }
    return tagged
  }

  func memories(containing text: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    if shouldThrow { throw Failure() }
    return named
  }
}
