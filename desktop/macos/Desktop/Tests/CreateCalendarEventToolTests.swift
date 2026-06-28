import XCTest
@testable import Omi_Computer

final class CreateCalendarEventToolTests: XCTestCase {
    func testCreateCalendarEventIsHandledByExecutor() async {
        let toolCall = ToolCall(
            name: "create_calendar_event",
            arguments: [
                "title": "Design review",
                "start_time": "2026-06-28T14:00:00-04:00"
            ],
            thoughtSignature: nil
        )

        let result = await ChatToolExecutor.execute(toolCall)

        XCTAssertFalse(result.hasPrefix("Unknown tool"), "create_calendar_event must be handled directly")
        XCTAssertEqual(result, "Error: end_time is required")
    }

    func testCreateCalendarEventRequiresTimezoneDates() async {
        let toolCall = ToolCall(
            name: "create_calendar_event",
            arguments: [
                "title": "Design review",
                "start_time": "2026-06-28T14:00:00",
                "end_time": "2026-06-28T15:00:00-04:00"
            ],
            thoughtSignature: nil
        )

        let result = await ChatToolExecutor.execute(toolCall)

        XCTAssertTrue(result.contains("start_time must be ISO format with timezone offset"))
    }
}
