import XCTest

@testable import Omi_Computer

final class ChatProviderOAuthURLTests: XCTestCase {
  func testAcceptsClaudePKCELoopbackAuthorizeURL() {
    let url = ChatProvider.validatedClaudeOAuthURL(
      "https://claude.ai/oauth/authorize?response_type=code&client_id=test-client&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=test-state&code_challenge=test-challenge&code_challenge_method=S256"
    )

    XCTAssertEqual(url?.host, "claude.ai")
    XCTAssertEqual(url?.path, "/oauth/authorize")
  }

  func testRejectsUnexpectedOAuthHostsPathsAndPKCEParameters() {
    let invalidURLs = [
      "https://evil.example/oauth/authorize?response_type=code&client_id=test-client&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=test-state&code_challenge=test-challenge&code_challenge_method=S256",
      "https://claude.ai/other?response_type=code&client_id=test-client&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=test-state&code_challenge=test-challenge&code_challenge_method=S256",
      "https://claude.ai/oauth/authorize?response_type=code&client_id=test-client&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=test-state&code_challenge=test-challenge",
      "https://claude.ai/oauth/authorize?response_type=code&client_id=test-client&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&state=test-state&code_challenge=test-challenge&code_challenge_method=S256",
    ]

    for url in invalidURLs {
      XCTAssertNil(ChatProvider.validatedClaudeOAuthURL(url), "Expected rejected OAuth URL: \(url)")
    }
  }

  func testFreshOAuthURLResetsTheOneLaunchPerAttemptLatch() {
    XCTAssertFalse(
      ChatProvider.isNewClaudeOAuthAttempt(
        previousAuthURL: "https://claude.ai/oauth/authorize?state=current",
        nextAuthURL: "https://claude.ai/oauth/authorize?state=current"
      )
    )
    XCTAssertTrue(
      ChatProvider.isNewClaudeOAuthAttempt(
        previousAuthURL: "https://claude.ai/oauth/authorize?state=expired",
        nextAuthURL: "https://claude.ai/oauth/authorize?state=retry"
      )
    )
  }
}
