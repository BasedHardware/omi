import CoreGraphics
import XCTest

@testable import Omi_Computer

final class ImportConnectorSheetSizingTests: XCTestCase {
    func testSimpleImportConnectorsUseCompactSheetSize() {
        for connector in ImportConnector.all where !connector.isManualMemoryImport {
            XCTAssertEqual(connector.sheetPreferredSize, CGSize(width: 520, height: 360), connector.id)
        }
    }

    func testMemoryImportConnectorsKeepEditorSheetSize() throws {
        let memoryImportConnectors = ImportConnector.all.filter(\.isManualMemoryImport)

        XCTAssertFalse(memoryImportConnectors.isEmpty)

        for connector in memoryImportConnectors {
            XCTAssertEqual(connector.sheetPreferredSize, CGSize(width: 520, height: 620), connector.id)
        }
    }
}
