import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// `tool:` frames in, results out, as the backend (`utils/device_tools.py`) and the Flutter client define them.
struct DeviceToolFrameTests {
    private func frame(_ object: [String: Any]) throws -> String {
        try "tool: " + JSONSerialization.data(withJSONObject: object).base64EncodedString()
    }

    @Test func parsesAProposedMessage() throws {
        let line = try frame([
            "call_id": "c1", "tool": "propose_message",
            "arguments": ["to": ["+49 170 1234567"], "text": "Hi Anna", "subject": ""],
        ])
        guard case let .deviceTool(request) = ChatStreamEvent.parse(line) else { Issue.record("no tool event"); return }
        #expect(request.id == "c1")
        #expect(request.tool == .proposeMessage)
        #expect(request.recipients == ["+49 170 1234567"])
        #expect(request.text == "Hi Anna")
        #expect(request.subject == nil)
    }

    @Test func parsesSearchAndPermissionArguments() throws {
        let search = try #require(DeviceToolFrame.parse(
            JSONSerialization.data(withJSONObject: [
                "call_id": "c2",
                "tool": "search_contacts",
                "arguments": ["query": " Anna ", "limit": 200],
            ])
            .base64EncodedString()
        ))
        #expect(search.query == "Anna")
        #expect(search.limit == 50)
        let single = try #require(DeviceToolFrame.parse(
            JSONSerialization.data(withJSONObject: ["call_id": "c3", "tool": "propose_message", "arguments": ["to": "anna@example.com"]])
                .base64EncodedString()
        ))
        #expect(single.recipients == ["anna@example.com"])
    }

    @Test func aDamagedFrameKeepsItsCallIDOrIsDropped() throws {
        let noTool = try #require(DeviceToolFrame.parse(JSONSerialization.data(withJSONObject: ["call_id": "c4"]).base64EncodedString()))
        #expect(noTool.tool == nil && noTool.toolName.isEmpty && noTool.id == "c4")
        #expect(DeviceToolFrame.parse("not base64!") == nil)
        #expect(DeviceToolFrame.parse(Data("{\"tool\":\"x\"}".utf8).base64EncodedString()) == nil)
    }

    @Test func resultPayloadsMatchTheFlutterShape() {
        let sent = DeviceToolFrame.payload(DeviceToolResult(ok: true, status: "sent"))
        #expect(sent["ok"] as? Bool == true)
        #expect(sent["status"] as? String == "sent")
        #expect(sent["contacts"] == nil)
        let contact = DeviceContact(
            id: "c-anna", name: "Anna", phoneNumbers: [.init(label: "mobile", value: "+49")], emailAddresses: [], preferredHandle: "+49"
        )
        let found = DeviceToolFrame.payload(DeviceToolResult(ok: true, query: "Ann", contacts: [contact]))
        #expect(found["count"] as? Int == 1)
        let first = (found["contacts"] as? [[String: Any]])?.first
        #expect(first?["preferred_messaging_handle"] as? String == "+49")
        #expect((first?["phone_numbers"] as? [[String: String]])?.first?["value"] == "+49")
        let failed = DeviceToolFrame.payload(.failure("declined", "No."))
        #expect(failed["ok"] as? Bool == false && failed["reason"] as? String == "declined")
    }
}
