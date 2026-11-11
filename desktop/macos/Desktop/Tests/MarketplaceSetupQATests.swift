import XCTest

@testable import Omi_Computer

final class MarketplaceSetupQATests: XCTestCase {
  func testFixtureCannotTargetPublicServersCredentialsOrOtherPaths() throws {
    let entry = try MarketplaceSetupQA.fixture(url: "http://127.0.0.1:54321/mcp")
    XCTAssertEqual(entry.id, MarketplaceSetupQA.fixtureID)
    XCTAssertEqual(entry.install, .mcpRemote(url: "http://127.0.0.1:54321/mcp", transport: "http", secretHeader: nil))
    for rejected in [
      "https://mcp.linear.app/mcp", "http://localhost:54321/mcp", "http://127.0.0.1/mcp",
      "http://127.0.0.1:54321/other", "http://user@127.0.0.1:54321/mcp",
      "http://127.0.0.1:54321/mcp?token=value", "http://127.0.0.1:54321/mcp#fragment",
    ] {
      XCTAssertThrowsError(try MarketplaceSetupQA.fixture(url: rejected), rejected)
    }
  }
}
