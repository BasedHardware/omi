import XCTest

@testable import Omi_Computer

/// Regression coverage for Settings ▸ Transcription ▸ Custom Vocabulary showing a change the account
/// never stored.
///
/// The pane shows an edit, and writes it to the local copy, before
/// `PATCH /v1/users/transcription-preferences` answers. When that PATCH failed, the failure was only
/// logged: the pane and the local copy kept the new list while the account, which live transcription
/// reads, still held the old one, and the next Settings load dropped the word without a message.
///
/// The fake account below replaces its whole list on every save, like the backend, and refuses saves
/// while offline. The pane used to keep the edited list whatever the PATCH answered, which in these
/// terms is `.saved` for a save the account refused. That fails
/// `testFailedSavePutsBackTheListTheAccountHolds` and `testFailedRemovalPutsBackTheRemovedWord`, where
/// the account still holds the list Settings read from it.
@MainActor
final class TranscriptionVocabularySaverTests: XCTestCase {

  /// The account's vocabulary. A save replaces the whole list.
  private final class FakeAccount {
    private(set) var vocabulary: [String]
    var isOffline = false

    init(vocabulary: [String]) {
      self.vocabulary = vocabulary
    }

    func save(_ terms: [String]) throws -> [String] {
      guard !isOffline else { throw SaveFailure() }
      vocabulary = terms
      return vocabulary
    }
  }

  /// The list the pane keeps between saves: the one the account last confirmed.
  private final class PaneState {
    var confirmed: [String]?

    init(confirmed: [String]?) {
      self.confirmed = confirmed
    }
  }

  private struct SaveFailure: Error {}

  func testFailedSavePutsBackTheListTheAccountHolds() async {
    let account = FakeAccount(vocabulary: ["alpha"])
    account.isOffline = true

    // The pane already shows "omi"; Settings read ["alpha"] from the account.
    let outcome = await TranscriptionVocabularySaver.save(
      ["alpha", "omi"],
      lastConfirmed: { ["alpha"] },
      isLatestEdit: { true },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .failed(restore: ["alpha"]))
    XCTAssertEqual(account.vocabulary, ["alpha"])
  }

  func testFailedRemovalPutsBackTheRemovedWord() async {
    let account = FakeAccount(vocabulary: ["alpha", "omi"])
    account.isOffline = true

    // The pane already dropped "omi".
    let outcome = await TranscriptionVocabularySaver.save(
      ["alpha"],
      lastConfirmed: { ["alpha", "omi"] },
      isLatestEdit: { true },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .failed(restore: ["alpha", "omi"]))
    XCTAssertEqual(account.vocabulary, ["alpha", "omi"])
  }

  func testFailureIsReportedEvenBeforeSettingsReadTheAccount() async {
    let account = FakeAccount(vocabulary: ["alpha"])
    account.isOffline = true

    // Settings has not read the account's list, so no list is known to put back.
    let outcome = await TranscriptionVocabularySaver.save(
      ["omi"],
      lastConfirmed: { nil },
      isLatestEdit: { true },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .failed(restore: nil))
  }

  func testFailurePutsBackAListConfirmedWhileTheSaveRan() async {
    let account = FakeAccount(vocabulary: ["alpha"])
    let pane = PaneState(confirmed: ["alpha"])

    // The earlier save of ["alpha", "beta"] is confirmed while this one is in flight; then this one fails.
    let outcome = await TranscriptionVocabularySaver.save(
      ["alpha", "beta", "omi"],
      lastConfirmed: { pane.confirmed },
      isLatestEdit: { true },
      write: { _ in
        pane.confirmed = try account.save(["alpha", "beta"])
        account.isOffline = true
        throw SaveFailure()
      }
    )

    XCTAssertEqual(outcome, .failed(restore: ["alpha", "beta"]))
    XCTAssertEqual(account.vocabulary, ["alpha", "beta"])
  }

  func testFailureIsLeftToANewerEdit() async {
    let account = FakeAccount(vocabulary: ["alpha"])
    account.isOffline = true

    // Another word was added while this save ran. That save sends this change too, so this failure
    // must not put the old list back over it.
    let outcome = await TranscriptionVocabularySaver.save(
      ["alpha", "omi"],
      lastConfirmed: { ["alpha"] },
      isLatestEdit: { false },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .superseded)
  }

  func testSavedListIsTheListTheAccountHolds() async {
    let account = FakeAccount(vocabulary: ["alpha"])

    let outcome = await TranscriptionVocabularySaver.save(
      ["alpha", "omi"],
      lastConfirmed: { ["alpha"] },
      isLatestEdit: { true },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .saved(stored: ["alpha", "omi"]))
    XCTAssertEqual(account.vocabulary, ["alpha", "omi"])
  }
}
