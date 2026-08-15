import XCTest

@testable import Omi_Computer

/// Regression coverage for Settings ▸ Transcription losing "Single Language" on reload.
///
/// The account's `single_language_mode` has two writers, and one of them is a side effect:
/// `PATCH /v1/users/language` stores the language *and* overwrites the mode with
/// `not supports_live_multilingual_mode(language)`. The pane used to issue that PATCH and the
/// transcription-preferences PATCH as two unordered tasks, so the side effect landed last and
/// erased the mode the user had picked. `loadBackendSettings()` then read the account back and
/// pushed the pane to Auto-Detect.
///
/// The fake below reproduces the server rule rather than asserting on call order alone, so the
/// test fails for the reason the user experienced: the account ends up in the wrong mode.
@MainActor
final class TranscriptionLanguageWriteOrderTests: XCTestCase {

  /// The two account fields these writes share, with the backend's own coupling between them.
  private final class FakeAccount {
    private(set) var language = ""
    private(set) var singleLanguageMode = false
    private(set) var writes: [String] = []

    /// Languages the live provider can auto-detect. Mirrors the backend predicate whose truth is
    /// what makes the language write destructive.
    private let multilingualLanguages: Set<String> = ["en", "es", "fr", "de", "pt"]

    func setLanguage(_ value: String) {
      language = value
      singleLanguageMode = !multilingualLanguages.contains(value)
      writes.append("language")
    }

    func setSingleLanguageMode(_ value: Bool) {
      singleLanguageMode = value
      writes.append("mode")
    }
  }

  private struct WriteFailure: Error {}

  func testSingleLanguageSurvivesTheLanguageWritesSideEffect() async {
    let account = FakeAccount()

    let outcome = await TranscriptionLanguageWriter.apply(
      language: "en",
      singleLanguageMode: true,
      setLanguage: { account.setLanguage($0) },
      setSingleLanguageMode: { account.setSingleLanguageMode($0) }
    )

    XCTAssertTrue(outcome.isComplete)
    XCTAssertEqual(account.language, "en")
    // The whole point: "en" is auto-detectable, so the language write set the mode to false.
    // The account must still end the operation in the mode the user chose.
    XCTAssertTrue(account.singleLanguageMode)
    XCTAssertEqual(account.writes, ["language", "mode"])
  }

  func testAutoDetectSelectionIsAlsoTheFinalWrite() async {
    let account = FakeAccount()

    // Ukrainian is not auto-detectable, so the language write forces single-language mode on.
    // A user asking for auto-detect must still be the last word on the account.
    let outcome = await TranscriptionLanguageWriter.apply(
      language: "uk",
      singleLanguageMode: false,
      setLanguage: { account.setLanguage($0) },
      setSingleLanguageMode: { account.setSingleLanguageMode($0) }
    )

    XCTAssertTrue(outcome.isComplete)
    XCTAssertFalse(account.singleLanguageMode)
    XCTAssertEqual(account.writes, ["language", "mode"])
  }

  func testModeIsStillAssertedWhenTheLanguageWriteFails() async {
    let account = FakeAccount()

    let outcome = await TranscriptionLanguageWriter.apply(
      language: "en",
      singleLanguageMode: true,
      setLanguage: { _ in throw WriteFailure() },
      setSingleLanguageMode: { account.setSingleLanguageMode($0) }
    )

    XCTAssertFalse(outcome.languageWritten)
    XCTAssertTrue(outcome.modeWritten)
    XCTAssertFalse(outcome.isComplete)
    XCTAssertTrue(account.singleLanguageMode)
    XCTAssertEqual(account.writes, ["mode"])
  }

  func testPartialWriteIsReportedWhenTheModeWriteFails() async {
    let account = FakeAccount()

    let outcome = await TranscriptionLanguageWriter.apply(
      language: "en",
      singleLanguageMode: true,
      setLanguage: { account.setLanguage($0) },
      setSingleLanguageMode: { _ in throw WriteFailure() }
    )

    XCTAssertTrue(outcome.languageWritten)
    XCTAssertFalse(outcome.modeWritten)
    XCTAssertFalse(outcome.isComplete)
    XCTAssertEqual(account.writes, ["language"])
  }
}
