import XCTest

@testable import Omi_Computer

@MainActor
final class ReferralViewModelTests: XCTestCase {
  func testLoadPublishesReferralLink() async {
    let model = ReferralViewModel {
      ReferralLinkResponse(referralURL: "https://api.omi.me/r/ref1.example.signature")
    }

    await model.load()

    XCTAssertEqual(model.state, .loaded("https://api.omi.me/r/ref1.example.signature"))
  }

  func testFailedLoadCanRetry() async {
    var attempts = 0
    let model = ReferralViewModel {
      attempts += 1
      if attempts == 1 { throw ReferralTestError.unavailable }
      return ReferralLinkResponse(referralURL: "https://api.omi.me/r/ref1.retry.signature")
    }

    await model.load()
    XCTAssertEqual(model.state, .failed)

    await model.load()
    XCTAssertEqual(model.state, .loaded("https://api.omi.me/r/ref1.retry.signature"))
    XCTAssertEqual(attempts, 2)
  }

  func testReferralResponseDecodesBackendWireKey() throws {
    let response = try JSONDecoder().decode(
      ReferralLinkResponse.self,
      from: Data(#"{"referral_url":"https://api.omi.me/r/ref1.example.signature"}"#.utf8)
    )

    XCTAssertEqual(response.referralURL, "https://api.omi.me/r/ref1.example.signature")
  }
}

private enum ReferralTestError: Error {
  case unavailable
}
