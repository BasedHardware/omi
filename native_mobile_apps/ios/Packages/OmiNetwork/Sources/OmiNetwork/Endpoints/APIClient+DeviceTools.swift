import Foundation
import OmiCore

/// Device tools on the chat stream (backend `utils/device_tools.py`, `routers/chat.py`): the
/// request declares what this phone can run, a `tool:` frame (base64 JSON `{call_id, tool,
/// arguments}`) asks for one, and the result goes to `POST v2/messages/device-tool/{call_id}/result`.
enum DeviceToolFrame {
    /// A frame that will not decode is dropped; one whose call id survived comes back with an
    /// empty tool name, so the app can answer "malformed" instead of leaving the agent waiting.
    static func parse(_ encoded: String) -> DeviceToolRequest? {
        guard let data = Data(base64Encoded: encoded.trimmingCharacters(in: .whitespaces)),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let callID = object["call_id"] as? String, !callID.isEmpty else { return nil }
        guard let tool = object["tool"] as? String, !tool.isEmpty else { return DeviceToolRequest(id: callID, toolName: "") }
        let arguments = object["arguments"] as? [String: Any] ?? [:]
        let recipients: [String] = if let list = arguments["to"] as? [String] {
            list.filter { !$0.isEmpty }
        } else if let one = arguments["to"] as? String, !one.isEmpty {
            [one]
        } else {
            []
        }
        return DeviceToolRequest(
            id: callID,
            toolName: tool,
            recipients: recipients,
            text: arguments["text"] as? String ?? "",
            subject: (arguments["subject"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            query: (arguments["query"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "",
            limit: min(max((arguments["limit"] as? NSNumber)?.intValue ?? 10, 1), 50),
            permission: (arguments["type"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        )
    }

    /// The result object, in the shape the Flutter and desktop clients send.
    static func payload(_ result: DeviceToolResult) -> [String: Any] {
        var payload: [String: Any] = ["ok": result.ok]
        if let status = result.status { payload["status"] = status }
        if let reason = result.reason { payload["reason"] = reason }
        if let error = result.error { payload["error"] = error }
        if let query = result.query { payload["query"] = query }
        if let contacts = result.contacts {
            payload["count"] = contacts.count
            payload["contacts"] = contacts.map { contact in
                [
                    "id": contact.id,
                    "name": contact.name,
                    "phone_numbers": contact.phoneNumbers.map { ["label": $0.label, "value": $0.value] },
                    "email_addresses": contact.emailAddresses.map { ["label": $0.label, "value": $0.value] },
                    "preferred_messaging_handle": contact.preferredHandle,
                ] as [String: Any]
            }
        }
        return payload
    }
}

public extension APIClient {
    /// `POST v2/messages` for an agent run: declares the device tools this phone can run (so the
    /// agent can ask mid-run), and reports typed `error:` frames as `.failed(<code>)`.
    func streamAgent(
        _ text: String, context: ChatContext?, sessionID: String?, deviceTools: [String]
    ) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var body: [String: Any] = ["text": text, "file_ids": [String](), "time_zone": TimeZone.current.identifier]
                    if let context { body["context"] = ["type": context.kind.rawValue, "id": context.id, "title": context.title] }
                    if !deviceTools.isEmpty { body["device_tools"] = deviceTools }
                    let query = sessionID.map { [URLQueryItem(name: "chat_session_id", value: $0)] } ?? []
                    var streaming = try await request(
                        .post, "v2/messages", query: query, body: .json(JSONSerialization.data(withJSONObject: body))
                    )
                    streaming.setValue("1", forHTTPHeaderField: "X-Omi-Chat-Failure-Protocol")
                    // A device tool waits for a person; the turn's own budget bounds it server-side.
                    streaming.timeoutInterval = 300
                    let (bytes, response) = try await session.bytes(for: streaming)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200 ..< 300).contains(status) else { throw APIError.http(status: status, body: "") }
                    for try await line in bytes.lines where !line.isEmpty && !line.hasPrefix(":") {
                        if let code = ChatStreamEvent.errorCode(line) {
                            continuation.yield(.failed(code))
                        } else if let event = ChatStreamEvent.parse(line) {
                            continuation.yield(event)
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// `POST v2/messages/device-tool/{call_id}/result`. 404 when the call is no longer waiting
    /// (the agent timed out or the turn ended).
    func sendDeviceToolResult(callID: String, result: DeviceToolResult) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["result": DeviceToolFrame.payload(result)])
        _ = try await data(.post, "v2/messages/device-tool/\(callID)/result", body: .json(body))
    }
}
