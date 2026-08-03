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

  // MARK: - Cold local cache (the server leg)

  func testMemoriesResolveWithAColdLocalCache() async {
    // The machine has never synced a memory: both local legs are empty, exactly as they are on a
    // fresh install or after the scoring-ordered pages skipped these rows.
    let source = StubPersonMemorySource(
      server: [
        candidate(
          id: "s1", content: "Sam \u{2014} in your “Tahoe Trip” group.", tags: ["person:sam"],
          secondsAgo: 0),
        candidate(id: "s2", content: "Sam \u{2014} you know them via iMessage.", secondsAgo: 60),
      ],
      tagged: [],
      named: [])
    let model = await PersonMemoriesModel(source: source)

    await model.load(personID: "sam", displayName: "Sam")

    let state = await model.state
    let memories = await model.memories
    XCTAssertEqual(state, .loaded)
    XCTAssertEqual(memories.map { $0.id }, ["s1", "s2"], "the server answered with a cold cache")
    XCTAssertEqual(memories.map { $0.isTagged }, [true, true], "server attribution is real provenance")
  }

  func testServerRowNeedsNoLocalTagToBeAccepted() async {
    // A fact attributed by `subject_entity_id` alone carries no `person:` tag. Re-deriving the
    // match from the row's tags here would drop exactly the rows the server leg exists to deliver.
    let source = StubPersonMemorySource(
      server: [candidate(id: "s1", content: "A fact with no client-side tag at all.", tags: [])])
    let model = await PersonMemoriesModel(source: source)

    await model.load(personID: "sam", displayName: "Sam")

    let memories = await model.memories
    XCTAssertEqual(memories.map { $0.id }, ["s1"])
  }

  func testOfflineMachineStillShowsItsCachedRows() async {
    let source = StubPersonMemorySource(
      tagged: [candidate(id: "m1", content: "Sam \u{2014} cached.", tags: ["person:sam"])],
      serverShouldThrow: true)
    let model = await PersonMemoriesModel(source: source)

    await model.load(personID: "sam", displayName: "Sam")

    let state = await model.state
    let memories = await model.memories
    XCTAssertEqual(state, .loaded, "a dropped network must not blank a profile the cache can render")
    XCTAssertEqual(memories.map { $0.id }, ["m1"])
  }

  func testColdMachineSurvivesAFailingLocalStore() async {
    let source = StubPersonMemorySource(
      server: [candidate(id: "s1", content: "Sam \u{2014} from the server.")],
      localShouldThrow: true)
    let model = await PersonMemoriesModel(source: source)

    await model.load(personID: "sam", displayName: "Sam")

    let state = await model.state
    let memories = await model.memories
    XCTAssertEqual(state, .loaded)
    XCTAssertEqual(memories.map { $0.id }, ["s1"])
  }

  func testSameMemoryFromServerAndCacheStaysOneRow() async {
    let shared = candidate(
      id: "m1", content: "Sam \u{2014} in your group.", tags: ["person:sam"])
    let source = StubPersonMemorySource(server: [shared], tagged: [shared], named: [shared])
    let model = await PersonMemoriesModel(source: source)

    await model.load(personID: "sam", displayName: "Sam")

    let memories = await model.memories
    XCTAssertEqual(memories.map { $0.id }, ["m1"])
    XCTAssertTrue(memories[0].isTagged)
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

/// In-memory stand-in for the server query and `MemoryStorage`, so the model's real load path runs
/// without a network or SQLite.
///
/// `shouldThrow` fails every leg (the historical "the whole store is broken" case);
/// `serverShouldThrow` / `localShouldThrow` fail one side so the per-leg tolerance is assertable.
private struct StubPersonMemorySource: PersonMemorySource {
  var server: [PersonMemoryCandidate] = []
  var tagged: [PersonMemoryCandidate] = []
  var named: [PersonMemoryCandidate] = []
  var shouldThrow = false
  var serverShouldThrow = false
  var localShouldThrow = false

  struct Failure: Error {}

  func serverMemories(forPerson personID: String, limit: Int) async throws
    -> [PersonMemoryCandidate]
  {
    if shouldThrow || serverShouldThrow { throw Failure() }
    return server
  }

  func memories(taggedWith tag: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    if shouldThrow || localShouldThrow { throw Failure() }
    return tagged
  }

  func memories(containing text: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    if shouldThrow || localShouldThrow { throw Failure() }
    return named
  }
}
