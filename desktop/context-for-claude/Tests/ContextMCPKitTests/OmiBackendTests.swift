import ContextCore
import XCTest
@testable import ContextMCPKit

final class OmiBackendTests: XCTestCase {
    func testCredentialIsReevaluatedAfterSignOut() {
        var credential: (key: String, source: OmiKeySource)? = ("key-a", .appSupportFile)
        let backend = OmiBackend(credentialProvider: { credential })

        XCTAssertTrue(backend.isConfigured)
        XCTAssertEqual(backend.keySourceLabel, "~/Library/Application Support/ContextForClaude/mcp-key")

        credential = nil

        XCTAssertFalse(backend.isConfigured)
        XCTAssertNil(backend.keySourceLabel)
    }

    func testCredentialChangeKeepsConfigurationLive() {
        var credential: (key: String, source: OmiKeySource)? = ("key-a", .appSupportFile)
        let backend = OmiBackend(credentialProvider: { credential })

        credential = ("key-b", .environment)

        XCTAssertTrue(backend.isConfigured)
        XCTAssertEqual(backend.keySourceLabel, "the CONTEXT_OMI_MCP_KEY environment variable")
    }
}
