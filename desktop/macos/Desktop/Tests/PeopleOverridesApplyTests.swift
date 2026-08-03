import XCTest

@testable import Omi_Computer

/// Exercises the human-in-the-loop core of the People engine: weak-signal detection
/// (`annotateAndReview`) and the pure overrides-apply logic (`applyOverrides`) that guarantees
/// **user truth wins over inference** — confirmed merges/splits, corrected/dropped facts, and
/// dismissed items. No file IO: everything runs on in-memory `[[String: Any]]` people dicts.
final class PeopleOverridesApplyTests: XCTestCase {

  // MARK: - Helpers

  private func person(
    _ id: String, name: String, closeness: Double, facts: [String] = [],
    needsConfirmation: Bool = false
  ) -> [String: Any] {
    var p: [String: Any] = ["id": id, "name": name, "closeness": closeness]
    if !facts.isEmpty { p["facts"] = facts }
    if needsConfirmation { p["needsConfirmation"] = true }
    return p
  }

  private func identityItem(a: String, b: String, aName: String, bName: String) -> [String: Any] {
    let key = a < b ? "\(a)|\(b)" : "\(b)|\(a)"
    return [
      "id": "identity:\(key)",
      "name": aName,
      "kind": "identity",
      "question": "Are \(aName) and \(bName) the same person?",
      "a": a,
      "b": b,
    ]
  }

  private func factItem(personId: String, name: String, fact: String) -> [String: Any] {
    [
      "id": "fact:\(personId)",
      "name": name,
      "kind": "fact",
      "question": "Is this right about \(name)? \(fact)",
      "personId": personId,
      "fact": fact,
    ]
  }

  private func names(_ people: [[String: Any]]) -> [String] {
    people.compactMap { $0["name"] as? String }
  }

  private func reviewIDs(_ queue: [[String: Any]]) -> [String] {
    queue.compactMap { $0["id"] as? String }
  }

  // MARK: - Identity: confirmed SAME → merge

  func testIdentityConfirmSameMergesPeopleAndClearsReviewItem() {
    let people = [
      person("prisha", name: "Prisha", closeness: 120, needsConfirmation: true),
      person("pritha", name: "Pritha", closeness: 40, needsConfirmation: true),
    ]
    let review = [identityItem(a: "prisha", b: "pritha", aName: "Prisha", bName: "Pritha")]
    let overrides = PeopleOverrides(
      identity: [.init(a: "prisha", b: "pritha", same: true)])

    let result = PeopleGraphBuilder.applyOverrides(
      people: people, reviewQueue: review, overrides: overrides)

    // The two cards collapse to one (survivor = higher closeness = Prisha).
    XCTAssertEqual(result.people.count, 1, "a confirmed-same identity must merge the two cards")
    let survivor = result.people[0]
    XCTAssertEqual(survivor["name"] as? String, "Prisha", "the higher-closeness card survives")
    // The absorbed name is retained as an alias so the link is never lost.
    XCTAssertEqual(survivor["aliases"] as? [String], ["Pritha"], "absorbed name kept as an alias")
    // Combined closeness reflects both.
    XCTAssertEqual(survivor["closeness"] as? Double, 160, "closeness sums on merge")
    // The survivor is no longer flagged, and the question is gone.
    XCTAssertEqual(survivor["needsConfirmation"] as? Bool, false, "survivor confirmation cleared")
    XCTAssertTrue(result.reviewQueue.isEmpty, "a decided identity item must not resurface")
  }

  // MARK: - Identity: confirmed NOT the same → keep both, stop asking

  func testIdentityNotSameKeepsBothAndClearsReviewItem() {
    let people = [
      person("prisha", name: "Prisha", closeness: 120, needsConfirmation: true),
      person("pritha", name: "Pritha", closeness: 40, needsConfirmation: true),
    ]
    let review = [identityItem(a: "prisha", b: "pritha", aName: "Prisha", bName: "Pritha")]
    let overrides = PeopleOverrides(
      identity: [.init(a: "prisha", b: "pritha", same: false)])

    let result = PeopleGraphBuilder.applyOverrides(
      people: people, reviewQueue: review, overrides: overrides)

    XCTAssertEqual(result.people.count, 2, "confirmed-different people stay separate")
    XCTAssertEqual(Set(names(result.people)), ["Prisha", "Pritha"])
    for p in result.people {
      XCTAssertEqual(p["needsConfirmation"] as? Bool, false, "both cards stop being flagged")
    }
    XCTAssertTrue(result.reviewQueue.isEmpty, "a decided identity item must not resurface")
  }

  // MARK: - Fact edit: replace and drop

  func testFactEditReplacesFactAndClearsItem() {
    let people = [
      person("dev", name: "Dev", closeness: 10, facts: ["Works at Acme", "Lives in NYC"])
    ]
    let review = [factItem(personId: "dev", name: "Dev", fact: "Works at Acme")]
    let overrides = PeopleOverrides(
      factEdits: [.init(id: "dev", original: "Works at Acme", corrected: "Works at Globex")])

    let result = PeopleGraphBuilder.applyOverrides(
      people: people, reviewQueue: review, overrides: overrides)

    let facts = result.people[0]["facts"] as? [String]
    XCTAssertEqual(facts, ["Works at Globex", "Lives in NYC"], "corrected fact replaces the original")
    XCTAssertTrue(result.reviewQueue.isEmpty, "an edited fact item must not resurface")
  }

  func testFactEditBlankDropsFact() {
    let people = [
      person("dev", name: "Dev", closeness: 10, facts: ["Works at Acme", "Lives in NYC"])
    ]
    let review = [factItem(personId: "dev", name: "Dev", fact: "Works at Acme")]
    // A blank correction means "this fact is wrong — drop it" (the "No" path).
    let overrides = PeopleOverrides(
      factEdits: [.init(id: "dev", original: "Works at Acme", corrected: "")])

    let result = PeopleGraphBuilder.applyOverrides(
      people: people, reviewQueue: review, overrides: overrides)

    XCTAssertEqual(result.people[0]["facts"] as? [String], ["Lives in NYC"], "the wrong fact is dropped")
    XCTAssertTrue(result.reviewQueue.isEmpty, "a rejected fact item must not resurface")
  }

  // MARK: - Dismiss

  func testDismissHidesItemWithoutMutatingPeople() {
    let people = [
      person("prisha", name: "Prisha", closeness: 120, needsConfirmation: true),
      person("pritha", name: "Pritha", closeness: 40, needsConfirmation: true),
    ]
    let item = identityItem(a: "prisha", b: "pritha", aName: "Prisha", bName: "Pritha")
    let itemID = item["id"] as? String ?? ""
    let overrides = PeopleOverrides(dismissed: [itemID])

    let result = PeopleGraphBuilder.applyOverrides(
      people: people, reviewQueue: [item], overrides: overrides)

    XCTAssertEqual(result.people.count, 2, "dismiss does not merge or drop anyone")
    XCTAssertFalse(
      reviewIDs(result.reviewQueue).contains(itemID), "a dismissed item never resurfaces")
    XCTAssertTrue(result.reviewQueue.isEmpty)
  }

  // MARK: - Weak-signal detection + full round trip

  func testAnnotateFlagsEditDistanceCloseNamesAsIdentityQuestion() {
    // The motivating bug: two near-identical names must be *asked about*, never silently merged.
    let people = [
      person("prisha", name: "Prisha", closeness: 120),
      person("pritha", name: "Pritha", closeness: 40),
      person("bob", name: "Bob", closeness: 200),
    ]
    let result = PeopleGraphBuilder.annotateAndReview(persons: people, overrides: PeopleOverrides())

    // No decision yet → nobody merged, both similar names flagged, exactly one identity question.
    XCTAssertEqual(result.people.count, 3, "with no decision, weak signals never auto-merge")
    let identityItems = result.reviewQueue.filter { ($0["kind"] as? String) == "identity" }
    XCTAssertEqual(identityItems.count, 1, "Prisha/Pritha surface one identity question")
    let flagged = result.people.filter { ($0["needsConfirmation"] as? Bool) == true }
      .compactMap { $0["name"] as? String }
    XCTAssertEqual(Set(flagged), ["Prisha", "Pritha"], "both near-identical names are flagged")
  }

  func testAnnotateFlagsFirstNameOnlyCollision() {
    // Two distinct single-token "Alex" cards is an ambiguous identity — ask which, don't assume.
    let people = [
      person("alex", name: "Alex", closeness: 90),
      person("alex-2", name: "Alex", closeness: 30),
      person("bob", name: "Bob", closeness: 200),
    ]
    let result = PeopleGraphBuilder.annotateAndReview(persons: people, overrides: PeopleOverrides())

    XCTAssertEqual(result.people.count, 3, "no decision yet → nobody merged")
    let identityItems = result.reviewQueue.filter { ($0["kind"] as? String) == "identity" }
    XCTAssertEqual(identityItems.count, 1, "the two Alex cards raise exactly one identity question")
    let flagged = Set(
      result.people.filter { ($0["needsConfirmation"] as? Bool) == true }
        .compactMap { $0["id"] as? String })
    XCTAssertEqual(flagged, ["alex", "alex-2"], "both colliding first-name-only cards are flagged")
  }

  func testAnnotateThenConfirmSameResolvesTheQuestionEndToEnd() {
    let people = [
      person("prisha", name: "Prisha", closeness: 120),
      person("pritha", name: "Pritha", closeness: 40),
    ]
    // First run surfaces the question; the user confirms they are the same.
    let overrides = PeopleOverrides(identity: [.init(a: "prisha", b: "pritha", same: true)])
    let result = PeopleGraphBuilder.annotateAndReview(persons: people, overrides: overrides)

    XCTAssertEqual(result.people.count, 1, "confirming same merges end-to-end through annotate")
    XCTAssertTrue(result.reviewQueue.isEmpty, "the resolved question does not linger")
    XCTAssertEqual(
      PeopleGraphBuilder.editDistance("prisha", "pritha"), 1,
      "Prisha/Pritha are one edit apart — the signal the detector keys on")
  }
}
