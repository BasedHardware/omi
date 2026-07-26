import XCTest

@testable import Omi_Computer

final class SBOnboardingRepositoryTests: XCTestCase {
  func testGitHubLinkUsesOfficialOmiRepository() {
    XCTAssertEqual(SBOnboardingRepository.url.absoluteString, "https://github.com/BasedHardware/omi")
  }
}
