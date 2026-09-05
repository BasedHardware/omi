import XCTest

@testable import Omi_Computer

/// The refresh grant carries the audience the token was minted for.
///
/// The authorization request and the code exchange both send RFC 8707
/// `resource`, so hosted providers fronting several resources issue an
/// audience-scoped token. A refresh that drops it asks for an unscoped token,
/// and the MCP server rejects every call made with what comes back.
final class LocalMcpOAuthRefreshFormTests: XCTestCase {
  func testRefreshCarriesTheAudienceTheTokenWasMintedFor() {
    let form = LocalMcpStore.refreshForm(
      auth: ["resource": "https://mcp.example.com", "client_secret": "s3cret"],
      refreshToken: "rt-1", clientId: "cid-1")

    XCTAssertEqual(form["resource"], "https://mcp.example.com")
    XCTAssertEqual(form["grant_type"], "refresh_token")
    XCTAssertEqual(form["refresh_token"], "rt-1")
    XCTAssertEqual(form["client_id"], "cid-1")
    XCTAssertEqual(form["client_secret"], "s3cret")
  }

  /// An entry authorized before the resource was persisted has no audience to
  /// send. It must refresh exactly as it did rather than fail closed on a key
  /// that was never written for it.
  func testAnEntryAuthorizedBeforeTheResourceWasStoredStillRefreshes() {
    let legacy = LocalMcpStore.refreshForm(
      auth: ["client_secret": "s3cret"], refreshToken: "rt-2", clientId: "cid-2")
    XCTAssertNil(legacy["resource"])
    XCTAssertEqual(legacy["grant_type"], "refresh_token")

    // A public client that stored an empty resource is the same case: sending
    // `resource=` is not a narrower request, it is a malformed one.
    let empty = LocalMcpStore.refreshForm(
      auth: ["resource": ""], refreshToken: "rt-3", clientId: "cid-3")
    XCTAssertNil(empty["resource"])
    XCTAssertNil(empty["client_secret"])
  }
}
