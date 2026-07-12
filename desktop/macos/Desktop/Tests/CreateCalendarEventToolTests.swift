import XCTest
@testable import Omi_Computer

final class CreateCalendarEventToolTests: XCTestCase {
    private var previousAuthOwner: Any?
    private var previousAutomationOwner: Any?

    override func setUp() {
        super.setUp()
        previousAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
        previousAutomationOwner = UserDefaults.standard.object(forKey: .automationOwnerOverride)
        UserDefaults.standard.set("calendar-tool-test-owner", forKey: .authUserId)
        UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    }

    override func tearDown() {
        if let previousAuthOwner {
            UserDefaults.standard.set(previousAuthOwner, forKey: .authUserId)
        } else {
            UserDefaults.standard.removeObject(forKey: .authUserId)
        }
        if let previousAutomationOwner {
            UserDefaults.standard.set(previousAutomationOwner, forKey: .automationOwnerOverride)
        } else {
            UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
        }
        super.tearDown()
    }

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
