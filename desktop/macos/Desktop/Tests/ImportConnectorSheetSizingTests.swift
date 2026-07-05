import CoreGraphics
import XCTest

@testable import Omi_Computer

final class ImportConnectorSheetSizingTests: XCTestCase {
    func testSimpleImportConnectorsUseCompactSheetSize() {
        let simpleImportConnectors = ImportConnector.all.filter { !$0.isManualMemoryImport }

        XCTAssertFalse(simpleImportConnectors.isEmpty)

        for connector in simpleImportConnectors {
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
