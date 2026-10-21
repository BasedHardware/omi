import XCTest

@testable import Omi_Computer

/// The first-use popup's model: four concrete places, and "Try it now" opening one with the question
/// waiting in the bar rather than already sent.
@MainActor
final class FirstUseCaseTests: XCTestCase {

  func testTheFourCasesAreTheOnesTheProductNamesInOrder() {
    XCTAssertEqual(FirstUseCase.all.map(\.id), ["game", "design", "post", "shop"])
    XCTAssertEqual(
      FirstUseCase.all.map(\.label),
      ["Play a game", "Get design feedback", "Write a post", "Shop"])
  }

  func testEveryCaseOpensASecureSiteAndCarriesAQuestion() {
    for useCase in FirstUseCase.all {
      XCTAssertEqual(useCase.url.scheme, "https", useCase.id)
      XCTAssertFalse(useCase.question.trimmingCharacters(in: .whitespaces).isEmpty, useCase.id)
      XCTAssertFalse(useCase.siteName.isEmpty, useCase.id)
      XCTAssertEqual(FirstUseCase.named(useCase.id), useCase)
    }
    XCTAssertNil(FirstUseCase.named("steam"))
  }

  /// Minecraft in the browser: no launcher, no install, no account.
  func testTheGameIsBrowserMinecraft() {
    XCTAssertEqual(FirstUseCase.game.url.host, "eaglercraft.com")
  }

  func testTryItNowOpensTheSite() {
    var opened: [URL] = []

    XCTAssertTrue(
      FirstUseCaseLauncher.launch(
        .design,
        open: {
          opened.append($0)
          return true
        }))

    XCTAssertEqual(opened.map(\.absoluteString), ["https://www.figma.com/"])
  }

  func testASiteThatFailsToOpenReportsIt() {
    XCTAssertFalse(FirstUseCaseLauncher.launch(.shop, open: { _ in false }))
  }
}
