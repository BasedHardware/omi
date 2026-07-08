import Darwin
import GRDB
import XCTest

@testable import Omi_Computer

final class FileIndexingFailureTests: XCTestCase {
    func testClassifiesSQLiteFullAsDiskFull() {
        let error = DatabaseError(resultCode: .SQLITE_FULL, message: "database or disk is full")

        XCTAssertEqual(FileIndexingFailure.classify(error), .diskFull)
    }

    func testClassifiesPOSIXNoSpaceAsDiskFull() {
        let error = NSError(domain: NSPOSIXErrorDomain, code: Int(ENOSPC))

        XCTAssertEqual(FileIndexingFailure.classify(error), .diskFull)
    }

    func testDoesNotClassifyGenericSQLiteIOAsDiskFull() {
        let error = DatabaseError(resultCode: .SQLITE_IOERR, message: "disk I/O error")

        XCTAssertEqual(FileIndexingFailure.classify(error), .localWriteFailed)
    }

    func testDoesNotClassifyGenericPOSIXIOAsDiskFull() {
        let error = NSError(domain: NSPOSIXErrorDomain, code: Int(EIO))

        XCTAssertEqual(FileIndexingFailure.classify(error), .localWriteFailed)
    }

    func testClassifiesInitializationFailureSeparatelyFromWriteFailure() {
        XCTAssertEqual(
            FileIndexingFailure.classifyInitializationFailure(FileIndexerError.databaseNotInitialized),
            .localIndexUnavailable
        )
    }

    func testClassifiesInitializationDiskFullAsDiskFull() {
        let error = NSError(
            domain: NSCocoaErrorDomain,
            code: NSFileWriteUnknownError,
            userInfo: [NSUnderlyingErrorKey: NSError(domain: NSPOSIXErrorDomain, code: Int(ENOSPC))]
        )

        XCTAssertEqual(FileIndexingFailure.classifyInitializationFailure(error), .diskFull)
    }

    func testUserFacingMessagesAreShortAndActionable() {
        XCTAssertEqual(
            FileIndexingFailure.diskFull.toolErrorMessage,
            "Error: Mac storage is full. Free up space and try again."
        )
        XCTAssertEqual(
            FileIndexingFailure.localIndexUnavailable.toolErrorMessage,
            "Error: Omi couldn't open the file index. Try again."
        )
        XCTAssertEqual(
            FileIndexingFailure.localWriteFailed.toolErrorMessage,
            "Error: Omi couldn't save the file index. Try again."
        )
    }
}
