import XCTest

@testable import OmiKit

final class AuthCallbackRequestTargetTests: XCTestCase {
    func testAcceptsExactCallbackPathWithOrWithoutQuery() {
        XCTAssertTrue(isLoopbackAuthCallbackRequestTarget("/callback"))
        XCTAssertTrue(isLoopbackAuthCallbackRequestTarget("/callback?code=x&state=s"))
        XCTAssertTrue(isLoopbackAuthCallbackRequestTarget("/callback?"))
    }

    func testRejectsCallbackPathPrefixesAndNonOriginTargets() {
        for target in [
            "/callback-extra?code=x&state=s",
            "/callback/extra?code=x&state=s",
            "/callback%2Dextra?code=x&state=s",
            "/favicon.ico",
            "http://127.0.0.1/callback?code=x&state=s",
            "/callback?code=x&state=s#fragment",
        ] {
            XCTAssertFalse(
                isLoopbackAuthCallbackRequestTarget(target),
                "Unexpectedly accepted request target: \(target)")
        }
    }
}
