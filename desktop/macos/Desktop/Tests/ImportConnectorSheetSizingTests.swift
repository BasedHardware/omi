import CoreGraphics
import XCTest

@testable import Omi_Computer

final class ImportConnectorSheetSizingTests: XCTestCase {
    func testSimpleImportConnectorsUseCompactSheetSize() {
        let memoryImportIDs: Set<String> = ["chatgpt", "claude"]

        for connector in ImportConnector.all where !memoryImportIDs.contains(connector.id) {
            XCTAssertEqual(connector.sheetPreferredSize, CGSize(width: 520, height: 360), connector.id)
        }
    }

    func testMemoryImportConnectorsKeepEditorSheetSize() throws {
        for connectorID in ["chatgpt", "claude"] {
            let connector = try XCTUnwrap(ImportConnector.all.first { $0.id == connectorID })
            XCTAssertEqual(connector.sheetPreferredSize, CGSize(width: 520, height: 620), connectorID)
        }
    }
}
