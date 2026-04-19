import XCTest
@testable import Omi_Computer

@MainActor
final class DateValidationTests: XCTestCase {

    // MARK: - Valid dates (should be accepted)

    func testAcceptsNegativeTimezoneOffset() {
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00-08:00", paramName: "start_date")
        XCTAssertNotNil(result.valid)
        XCTAssertNil(result.error)
    }

    func testAcceptsPositiveTimezoneOffset() {
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00+07:00", paramName: "start_date")
        XCTAssertNotNil(result.valid)
        XCTAssertNil(result.error)
    }

    func testAcceptsUTCZ() {
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00Z", paramName: "end_date")
        XCTAssertNotNil(result.valid)
        XCTAssertNil(result.error)
    }

    func testAcceptsFractionalSeconds() {
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00.123-08:00", paramName: "start_date")
        XCTAssertNotNil(result.valid)
        XCTAssertNil(result.error)
    }

    func testAcceptsZeroOffset() {
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00+00:00", paramName: "start_date")
        XCTAssertNotNil(result.valid)
        XCTAssertNil(result.error)
    }

    // MARK: - Invalid dates (should be rejected)

    func testRejectsNoTimezone() {
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00", paramName: "start_date")
        XCTAssertNil(result.valid)
        XCTAssertNotNil(result.error)
        XCTAssert(result.error!.contains("start_date"))
    }

    func testRejectsDateOnly() {
        let result = ChatToolExecutor.validateISODate("2024-01-19", paramName: "end_date")
        XCTAssertNil(result.valid)
        XCTAssertNotNil(result.error)
        XCTAssert(result.error!.contains("end_date"))
    }

    func testRejectsGarbageInput() {
        let result = ChatToolExecutor.validateISODate("not-a-date", paramName: "due_at")
        XCTAssertNil(result.valid)
        XCTAssertNotNil(result.error)
        XCTAssert(result.error!.contains("due_at"))
    }

    func testRejectsEmptyString() {
        let result = ChatToolExecutor.validateISODate("", paramName: "start_date")
        XCTAssertNil(result.valid)
        XCTAssertNotNil(result.error)
    }

    func testRejectsSpaceInsteadOfPlus() {
        // This is the original bug from #6427 — space decoded from +
        let result = ChatToolExecutor.validateISODate("2024-01-19T15:00:00 07:00", paramName: "start_date")
        XCTAssertNil(result.valid)
        XCTAssertNotNil(result.error)
    }

    // MARK: - Error message quality

    func testErrorIncludesParamName() {
        let result = ChatToolExecutor.validateISODate("bad", paramName: "due_start_date")
        XCTAssertNotNil(result.error)
        XCTAssert(result.error!.contains("due_start_date"))
    }

    func testErrorIncludesFormatExample() {
        let result = ChatToolExecutor.validateISODate("bad", paramName: "start_date")
        XCTAssertNotNil(result.error)
        XCTAssert(result.error!.contains("2024-01-19T15:00:00-08:00"))
    }

    func testErrorIncludesOriginalValue() {
        let result = ChatToolExecutor.validateISODate("2024-01-19", paramName: "start_date")
        XCTAssertNotNil(result.error)
        XCTAssert(result.error!.contains("2024-01-19"))
    }
}
