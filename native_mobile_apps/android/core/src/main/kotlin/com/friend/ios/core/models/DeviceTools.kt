package com.friend.ios.core.models

/**
 * Port of `DeviceTools.swift`. A tool the agent asks the phone to run mid-answer (backend
 * `utils/device_tools.py`): the chat stream sends a `tool:` frame and waits until the app posts
 * the result. Nothing here runs without the user's tap: a message only opens the system
 * composer, contacts are shared one at a time, and a permission is the system prompt.
 */
data class DeviceToolRequest(
    /** The backend's `call_id`. */
    val id: String,
    /** The tool name as sent; [tool] is null for a name this app does not know. */
    val toolName: String,
    /** propose_message: recipients (phone numbers or emails), the body, an optional subject. */
    val recipients: List<String> = emptyList(),
    val text: String = "",
    val subject: String? = null,
    /** search_contacts: the name to look up and how many matches at most. */
    val query: String = "",
    val limit: Int = 10,
    /** request_permission: which one (Android, like iOS: `contacts`). */
    val permission: String = "",
) {
    enum class Tool(val rawValue: String) {
        ProposeMessage("propose_message"),
        SearchContacts("search_contacts"),
        RequestPermission("request_permission"),
        ;

        companion object {
            fun from(raw: String): Tool? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    val tool: Tool? get() = Tool.from(toolName)
}

/** One person from the phone's contacts, as `search_contacts` reports it. */
data class DeviceContact(
    val id: String,
    val name: String,
    val phoneNumbers: List<Handle>,
    val emailAddresses: List<Handle>,
    /** The mobile number when there is one, else the first number or email. */
    val preferredHandle: String,
) {
    data class Handle(val label: String, val value: String)
}

/**
 * What the app posts back for a call (`POST v2/messages/device-tool/{call_id}/result`). Same
 * shape as the Flutter and desktop clients: `ok`, a `status` or `reason`, and an `error` text.
 */
data class DeviceToolResult(
    val ok: Boolean,
    val status: String? = null,
    val reason: String? = null,
    val error: String? = null,
    val query: String? = null,
    val contacts: List<DeviceContact>? = null,
) {
    companion object {
        fun failure(reason: String, message: String) = DeviceToolResult(ok = false, reason = reason, error = message)
    }
}

enum class ContactsAccess(val rawValue: String) {
    Granted("granted"),
    Limited("limited"),
    NotDetermined("not_determined"),
    Denied("denied"),
    Restricted("restricted"),
    ;

    val isUsable: Boolean get() = this == Granted || this == Limited
}

/**
 * How the system message composer ended. Android only: [Opened], the composer (an SMS app) was
 * opened with the message but Android does not report whether the user sent it.
 */
enum class MessageComposeOutcome(val rawValue: String) {
    Sent("sent"),
    Cancelled("cancelled"),
    Failed("failed"),
    Unavailable("unavailable"),
    Opened("opened"),
}

/**
 * The phone's side of the device tools (contacts, the message composer), implemented by the app
 * module so the libraries never touch ContactsContract or intents.
 */
interface DeviceToolPerforming {
    /** This device can open a message composer (an SMS app is installed). */
    val canSendMessages: Boolean
    val contactsAccess: ContactsAccess
    /** Reads matches from the phone's contacts. Nothing leaves the phone here. */
    suspend fun searchContacts(query: String, limit: Int): List<DeviceContact>
    /** Shows the system prompt (only after the user tapped Allow). */
    suspend fun requestContactsAccess(): ContactsAccess
    /** Opens the composer prefilled; the user sends (or not) in the messaging app. */
    suspend fun composeMessage(recipients: List<String>, text: String, subject: String?): MessageComposeOutcome
}
