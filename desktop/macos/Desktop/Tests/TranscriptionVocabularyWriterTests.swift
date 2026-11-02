import XCTest

@testable import Omi_Computer

/// Regression coverage for Settings ▸ Transcription ▸ Custom Vocabulary erasing the account's words.
///
/// `PATCH /v1/users/transcription-preferences` stores the list it is sent as the account's whole
/// vocabulary. The pane shows the local copy in `AssistantSettings` until it has read the account's
/// list, and kept showing it when that read failed. Adding a word saved the copy plus the word, so on
/// a new Mac, where the copy is empty, the account was left with just that word.
///
/// The fake below replaces its list on every save, as the backend does, so these tests fail for the
/// reason the user saw: the account loses its words. Applying the edit to the pane's list as it
/// stands, as the pane used to, fails every test below that passes `loadedFromAccount: false`: the
/// account ends up with `["omi"]`, `["alpha", "omi"]` or `[]`.
@MainActor
final class TranscriptionVocabularyWriterTests: XCTestCase {

  /// The account's vocabulary. A save replaces the whole list.
  private final class FakeAccount {
    private(set) var vocabulary: [String]
    private(set) var reads = 0
    private(set) var saves: [[String]] = []

    init(vocabulary: [String]) {
      self.vocabulary = vocabulary
    }

    func read() -> [String] {
      reads += 1
      return vocabulary
    }

    func save(_ terms: [String]) {
      vocabulary = terms
      saves.append(terms)
    }
  }

  private struct ReadFailure: Error {}

  func testAddSavesNothingWhenTheAccountListCannotBeRead() async {
    let account = FakeAccount(vocabulary: ["alpha", "beta"])

    // A new Mac: the local copy is empty and loading the account's list failed.
    let terms = await TranscriptionVocabularyWriter.apply(
      .add("omi"),
      to: [],
      loadedFromAccount: false,
      readAccountTerms: { throw ReadFailure() },
      save: { account.save($0) }
    )

    XCTAssertNil(terms)
    XCTAssertEqual(account.saves, [])
    XCTAssertEqual(account.vocabulary, ["alpha", "beta"])
  }

  func testAddReadsTheAccountListFirstSoItsWordsAreKept() async {
    let account = FakeAccount(vocabulary: ["alpha", "beta"])

    // The local copy is out of date: "beta" was added on the phone.
    let terms = await TranscriptionVocabularyWriter.apply(
      .add("omi"),
      to: ["alpha"],
      loadedFromAccount: false,
      readAccountTerms: { account.read() },
      save: { account.save($0) }
    )

    XCTAssertEqual(terms, ["alpha", "beta", "omi"])
    XCTAssertEqual(account.reads, 1)
    XCTAssertEqual(account.vocabulary, ["alpha", "beta", "omi"])
  }

  func testRemoveSavesNothingWhenTheAccountListCannotBeRead() async {
    let account = FakeAccount(vocabulary: ["alpha", "beta"])

    let terms = await TranscriptionVocabularyWriter.apply(
      .remove("alpha"),
      to: ["alpha"],
      loadedFromAccount: false,
      readAccountTerms: { throw ReadFailure() },
      save: { account.save($0) }
    )

    XCTAssertNil(terms)
    XCTAssertEqual(account.saves, [])
    XCTAssertEqual(account.vocabulary, ["alpha", "beta"])
  }

  func testRemoveReadsTheAccountListFirstSoTheOtherWordsAreKept() async {
    let account = FakeAccount(vocabulary: ["alpha", "beta"])

    let terms = await TranscriptionVocabularyWriter.apply(
      .remove("alpha"),
      to: ["alpha"],
      loadedFromAccount: false,
      readAccountTerms: { account.read() },
      save: { account.save($0) }
    )

    XCTAssertEqual(terms, ["beta"])
    XCTAssertEqual(account.vocabulary, ["beta"])
  }

  func testLoadedListIsEditedWithoutReadingTheAccountAgain() async {
    let account = FakeAccount(vocabulary: ["alpha", "beta"])

    let terms = await TranscriptionVocabularyWriter.apply(
      .add("omi"),
      to: ["alpha", "beta"],
      loadedFromAccount: true,
      readAccountTerms: { account.read() },
      save: { account.save($0) }
    )

    XCTAssertEqual(terms, ["alpha", "beta", "omi"])
    XCTAssertEqual(account.reads, 0)
    XCTAssertEqual(account.saves, [["alpha", "beta", "omi"]])
  }

  func testAddingAWordAlreadyOnTheListSavesNothing() async {
    let account = FakeAccount(vocabulary: ["Omi"])

    let terms = await TranscriptionVocabularyWriter.apply(
      .add("omi"),
      to: ["Omi"],
      loadedFromAccount: true,
      readAccountTerms: { account.read() },
      save: { account.save($0) }
    )

    XCTAssertEqual(terms, ["Omi"])
    XCTAssertEqual(account.saves, [])
  }
}
