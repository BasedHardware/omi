import Foundation
import OmiCore

/// A device tool call waiting for the user ("Omi asks"), with what the phone already found for
/// it (contact matches stay on the phone until the user picks one).
public struct PendingDeviceTool: Identifiable, Equatable, Sendable {
    /// The task the run belongs to (empty in the chat).
    public let taskID: String
    public let taskTitle: String
    public let request: DeviceToolRequest
    /// search_contacts: matches read from the phone's contacts (not shared yet).
    public var matches: [DeviceContact]
    /// search_contacts: the phone may not read contacts yet, so the card asks first.
    public var needsContactsAccess: Bool

    public var id: String {
        request.id
    }

    public init(
        taskID: String,
        taskTitle: String,
        request: DeviceToolRequest,
        matches: [DeviceContact] = [],
        needsContactsAccess: Bool = false
    ) {
        self.taskID = taskID
        self.taskTitle = taskTitle
        self.request = request
        self.matches = matches
        self.needsContactsAccess = needsContactsAccess
    }
}

/// The user's answer to "Omi asks". Only these taps ever produce a result that does something.
public enum DeviceToolChoice: Equatable, Sendable {
    /// propose_message: open the composer with this text (the user sends in the system sheet).
    case send(text: String)
    /// search_contacts: share this one contact with the agent.
    case pick(DeviceContact)
    /// request_permission, or search_contacts without access: show the system prompt.
    case allow
    /// "Not now": the agent hears the user declined.
    case decline
}

/// Turns device tool calls and the user's answers into results (`DeviceToolResult`), the same
/// shapes the Flutter and desktop clients send. Shared by agent runs and the chat.
@MainActor
public enum DeviceToolResolver {
    /// What to declare in `device_tools`: only what this phone can actually do.
    public static func declaredTools(_ performer: (any DeviceToolPerforming)?) -> [String] {
        guard let performer else { return [] }
        var tools = [DeviceToolRequest.Tool.searchContacts, .requestPermission]
        if performer.canSendMessages { tools.insert(.proposeMessage, at: 0) }
        return tools.map(\.rawValue)
    }

    /// A call the app answers without asking (malformed, unknown tool, nothing to run it on);
    /// nil when the user has to decide.
    public static func immediateResult(for request: DeviceToolRequest, performer: (any DeviceToolPerforming)?) -> DeviceToolResult? {
        guard let tool = request.tool else {
            return request.toolName.isEmpty
                ? .failure("malformed_request", "The device could not read this tool call.")
                : .failure("unsupported_tool", "This device has no tool called \(request.toolName).")
        }
        guard let performer else { return .failure("surface_unavailable", "This device cannot run tools right now.") }
        switch tool {
        case .proposeMessage:
            if !performer.canSendMessages { return .failure("messaging_unavailable", "This device is not configured to send messages.") }
            if request.recipients.isEmpty { return .failure("empty_recipient", "Provide at least one recipient.") }
            if request.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return .failure("empty_body", "Provide the message text to propose.")
            }
        case .searchContacts:
            if request.query.isEmpty { return .failure("missing_query", "Provide a name to search for.") }
        case .requestPermission:
            if request.permission != "contacts" { return .failure(
                "unsupported_permission",
                "iOS can only prompt for the contacts permission."
            ) }
        }
        return nil
    }

    /// The pending card for a call: contact matches are read now (only when access was already
    /// given; the card never triggers the system prompt by itself).
    public static func prepare(
        _ request: DeviceToolRequest, taskID: String, taskTitle: String, performer: any DeviceToolPerforming
    ) async -> PendingDeviceTool {
        var pending = PendingDeviceTool(taskID: taskID, taskTitle: taskTitle, request: request)
        if request.tool == .searchContacts {
            if performer.contactsAccess.isUsable {
                pending.matches = await performer.searchContacts(request.query, limit: request.limit)
            } else {
                pending.needsContactsAccess = true
            }
        }
        return pending
    }

    /// The result for the user's answer, or nil when the answer only moved the card on (Allow
    /// on a contact search: matches appear and the user still picks one).
    public static func result(
        for pending: inout PendingDeviceTool, choice: DeviceToolChoice, performer: any DeviceToolPerforming
    ) async -> DeviceToolResult? {
        let request = pending.request
        switch (request.tool, choice) {
        case (_, .decline):
            return declined(request)
        case let (.proposeMessage, .send(text)):
            let body = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !body.isEmpty else { return .failure("empty_body", "The message was empty.") }
            let outcome = await performer.composeMessage(to: request.recipients, text: body, subject: request.subject)
            return DeviceToolResult(
                ok: outcome == .sent, status: outcome.rawValue,
                error: outcome == .sent ? nil : "The user did not send the message (\(outcome.rawValue))."
            )
        case let (.searchContacts, .pick(contact)):
            return DeviceToolResult(ok: true, query: request.query, contacts: [contact])
        case (.searchContacts, .allow):
            let access = await performer.requestContactsAccess()
            guard access.isUsable else { return contactsDenied(access) }
            pending.needsContactsAccess = false
            pending.matches = await performer.searchContacts(request.query, limit: request.limit)
            return nil
        case (.requestPermission, .allow):
            let access = await performer.requestContactsAccess()
            return access.isUsable ? DeviceToolResult(ok: true, status: access.rawValue) : contactsDenied(access)
        default:
            return .failure("invalid_choice", "The device could not apply that answer.")
        }
    }

    private static func declined(_ request: DeviceToolRequest) -> DeviceToolResult {
        switch request.tool {
        case .proposeMessage:
            DeviceToolResult(
                ok: false, status: "cancelled", reason: "declined",
                error: "The user chose not to send this message. Do not retry; ask what they want instead."
            )
        case .requestPermission:
            DeviceToolResult(ok: false, status: "denied", reason: "authorization_denied", error: "The user declined the permission.")
        default:
            .failure("declined", "The user chose not to share a contact. Do not ask again this turn.")
        }
    }

    private static func contactsDenied(_ access: ContactsAccess) -> DeviceToolResult {
        DeviceToolResult(
            ok: false, status: access.rawValue, reason: "authorization_denied",
            error: "Contacts access is off. The user can turn it on in Settings."
        )
    }
}
