import Foundation

/// A tool the agent asks the phone to run mid-answer (backend `utils/device_tools.py`): the chat
/// stream sends a `tool:` frame and waits until the app posts the result. Nothing here runs
/// without the user's tap: a message only opens the system composer, contacts are shared one
/// at a time, and a permission is the system prompt.
public struct DeviceToolRequest: Identifiable, Hashable, Sendable {
    public enum Tool: String, CaseIterable, Sendable {
        case proposeMessage = "propose_message"
        case searchContacts = "search_contacts"
        case requestPermission = "request_permission"
    }

    /// The backend's `call_id`.
    public let id: String
    /// The tool name as sent; `tool` is nil for a name this app does not know.
    public let toolName: String
    public var tool: Tool? {
        Tool(rawValue: toolName)
    }

    /// propose_message: recipients (phone numbers or emails), the body, an optional subject.
    public let recipients: [String]
    public let text: String
    public let subject: String?
    /// search_contacts: the name to look up and how many matches at most.
    public let query: String
    public let limit: Int
    /// request_permission: which one (iOS: `contacts`).
    public let permission: String

    public init(
        id: String, toolName: String, recipients: [String] = [], text: String = "", subject: String? = nil, query: String = "",
        limit: Int = 10, permission: String = ""
    ) {
        self.id = id
        self.toolName = toolName
        self.recipients = recipients
        self.text = text
        self.subject = subject
        self.query = query
        self.limit = limit
        self.permission = permission
    }
}

/// One person from the phone's contacts, as `search_contacts` reports it.
public struct DeviceContact: Identifiable, Hashable, Sendable {
    public struct Handle: Hashable, Sendable {
        public let label: String
        public let value: String

        public init(label: String, value: String) {
            self.label = label
            self.value = value
        }
    }

    public let id: String
    public let name: String
    public let phoneNumbers: [Handle]
    public let emailAddresses: [Handle]
    /// The mobile number when there is one, else the first number or email.
    public let preferredHandle: String

    public init(id: String, name: String, phoneNumbers: [Handle], emailAddresses: [Handle], preferredHandle: String) {
        self.id = id
        self.name = name
        self.phoneNumbers = phoneNumbers
        self.emailAddresses = emailAddresses
        self.preferredHandle = preferredHandle
    }
}

/// What the app posts back for a call (`POST v2/messages/device-tool/{call_id}/result`). Same
/// shape as the Flutter and desktop clients: `ok`, a `status` or `reason`, and an `error` text.
public struct DeviceToolResult: Hashable, Sendable {
    public let ok: Bool
    public let status: String?
    public let reason: String?
    public let error: String?
    public let query: String?
    public let contacts: [DeviceContact]?

    public init(
        ok: Bool, status: String? = nil, reason: String? = nil, error: String? = nil, query: String? = nil,
        contacts: [DeviceContact]? = nil
    ) {
        self.ok = ok
        self.status = status
        self.reason = reason
        self.error = error
        self.query = query
        self.contacts = contacts
    }

    public static func failure(_ reason: String, _ message: String) -> DeviceToolResult {
        DeviceToolResult(ok: false, reason: reason, error: message)
    }
}

public enum ContactsAccess: String, Sendable {
    case granted, limited, notDetermined = "not_determined", denied, restricted

    public var isUsable: Bool {
        self == .granted || self == .limited
    }
}

/// How the system message composer ended.
public enum MessageComposeOutcome: String, Sendable {
    case sent, cancelled, failed, unavailable
}

/// The phone's side of the device tools (contacts, the message composer), implemented by the app
/// target so the packages never link Contacts or MessageUI.
@MainActor
public protocol DeviceToolPerforming: AnyObject {
    /// This device can open the message composer (false on a simulator or an iPad without iMessage).
    var canSendMessages: Bool { get }
    var contactsAccess: ContactsAccess { get }
    /// Reads matches from the phone's contacts. Nothing leaves the phone here.
    func searchContacts(_ query: String, limit: Int) async -> [DeviceContact]
    /// Shows the system prompt (only after the user tapped Allow).
    func requestContactsAccess() async -> ContactsAccess
    /// Opens the composer prefilled; the user sends (or not) in the system sheet.
    func composeMessage(to recipients: [String], text: String, subject: String?) async -> MessageComposeOutcome
}
