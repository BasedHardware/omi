import XCTest

@testable import Omi_Computer

final class ImportConnectorErrorMessageTests: XCTestCase {
    func testConnectorErrorMessagePreservesGmailActionableCopy() {
        XCTAssertEqual(
            connectorUserMessage(for: GmailReaderError.sessionExpired, connectorTitle: "Gmail"),
            "Your Gmail session expired. Reload mail.google.com in your browser to refresh it, then try again."
        )
    }

    func testConnectorErrorMessageMapsConnectivityFailures() {
        XCTAssertEqual(
            connectorUserMessage(for: URLError(.timedOut), connectorTitle: "Calendar"),
            "You appear to be offline. Check your connection and try again."
        )
    }

    func testConnectorErrorMessageHidesGmailNetworkDetails() {
        XCTAssertEqual(
            connectorUserMessage(
                for: GmailReaderError.networkError(
                    "Could not reach Gmail (<urlopen error [Errno 51] Network is unreachable>)."
                ),
                connectorTitle: "Gmail"
            ),
            "Couldn't reach Gmail. Check your connection and try again."
        )
    }

    func testConnectorErrorMessageHidesCalendarNetworkDetails() {
        XCTAssertEqual(
            connectorUserMessage(
                for: CalendarReaderError.networkError(
                    "Python returned invalid JSON: traceback"
                ),
                connectorTitle: "Calendar"
            ),
            "Couldn't reach Calendar. Check your connection and try again."
        )
    }

    func testConnectorErrorMessageHidesUnknownRawErrors() {
        let error = NSError(
            domain: NSCocoaErrorDomain,
            code: 4864,
            userInfo: [NSLocalizedDescriptionKey: "The data couldn't be read because it isn't in the correct format."]
        )

        XCTAssertEqual(
            connectorUserMessage(for: error, connectorTitle: "Calendar"),
            "Couldn't sync Calendar. Try again."
        )
    }

    func testImportConnectorErrorsOfferRetryThroughPrimaryAction() throws {
        let normalizedSource = try normalizedAppsPageSource()

        XCTAssertTrue(normalizedSource.contains("Button(\"Try again\") { runPrimaryAction() }"))
        XCTAssertTrue(normalizedSource.contains("private func runPrimaryAction()"))
        XCTAssertFalse(normalizedSource.contains("Button(\"Try again\") { Task {"))
    }
}

private func normalizedAppsPageSource() throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
    let sourceURL = testsURL
        .appendingPathComponent("Sources/MainWindow/Pages/AppsPage.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    return source.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
}
