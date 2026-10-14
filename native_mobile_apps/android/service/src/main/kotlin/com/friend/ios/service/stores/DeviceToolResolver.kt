package com.friend.ios.service.stores

import com.friend.ios.core.models.ContactsAccess
import com.friend.ios.core.models.DeviceContact
import com.friend.ios.core.models.DeviceToolPerforming
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.core.models.DeviceToolResult
import com.friend.ios.core.models.MessageComposeOutcome

/**
 * A device tool call waiting for the user ("Omi asks"), with what the phone already found for
 * it (contact matches stay on the phone until the user picks one).
 */
data class PendingDeviceTool(
    /** The task the run belongs to (empty in the chat). */
    val taskID: String,
    val taskTitle: String,
    val request: DeviceToolRequest,
    /** search_contacts: matches read from the phone's contacts (not shared yet). */
    val matches: List<DeviceContact> = emptyList(),
    /** search_contacts: the phone may not read contacts yet, so the card asks first. */
    val needsContactsAccess: Boolean = false,
) {
    val id: String get() = request.id
}

/** The user's answer to "Omi asks". Only these taps ever produce a result that does something. */
sealed interface DeviceToolChoice {
    /** propose_message: open the composer with this text (the user sends in the messaging app). */
    data class Send(val text: String) : DeviceToolChoice
    /** search_contacts: share this one contact with the agent. */
    data class Pick(val contact: DeviceContact) : DeviceToolChoice
    /** request_permission, or search_contacts without access: show the system prompt. */
    data object Allow : DeviceToolChoice
    /** "Not now": the agent hears the user declined. */
    data object Decline : DeviceToolChoice
}

/**
 * Port of `DeviceToolResolver.swift`: turns device tool calls and the user's answers into results
 * ([DeviceToolResult]), the same shapes the Flutter and desktop clients send. Shared by agent
 * runs and the chat.
 */
object DeviceToolResolver {
    /** What to declare in `device_tools`: only what this phone can actually do. */
    fun declaredTools(performer: DeviceToolPerforming?): List<String> {
        performer ?: return emptyList()
        val tools = mutableListOf(DeviceToolRequest.Tool.SearchContacts, DeviceToolRequest.Tool.RequestPermission)
        if (performer.canSendMessages) tools.add(0, DeviceToolRequest.Tool.ProposeMessage)
        return tools.map { it.rawValue }
    }

    /**
     * A call the app answers without asking (malformed, unknown tool, nothing to run it on);
     * null when the user has to decide.
     */
    fun immediateResult(request: DeviceToolRequest, performer: DeviceToolPerforming?): DeviceToolResult? {
        val tool = request.tool ?: return if (request.toolName.isEmpty()) {
            DeviceToolResult.failure("malformed_request", "The device could not read this tool call.")
        } else {
            DeviceToolResult.failure("unsupported_tool", "This device has no tool called ${request.toolName}.")
        }
        performer ?: return DeviceToolResult.failure("surface_unavailable", "This device cannot run tools right now.")
        when (tool) {
            DeviceToolRequest.Tool.ProposeMessage -> {
                if (!performer.canSendMessages) return DeviceToolResult.failure("messaging_unavailable", "This device is not configured to send messages.")
                if (request.recipients.isEmpty()) return DeviceToolResult.failure("empty_recipient", "Provide at least one recipient.")
                if (request.text.isBlank()) return DeviceToolResult.failure("empty_body", "Provide the message text to propose.")
            }
            DeviceToolRequest.Tool.SearchContacts ->
                if (request.query.isEmpty()) return DeviceToolResult.failure("missing_query", "Provide a name to search for.")
            DeviceToolRequest.Tool.RequestPermission ->
                if (request.permission != "contacts") {
                    return DeviceToolResult.failure("unsupported_permission", "Android can only prompt for the contacts permission.")
                }
        }
        return null
    }

    /**
     * The pending card for a call: contact matches are read now (only when access was already
     * given; the card never triggers the system prompt by itself).
     */
    suspend fun prepare(request: DeviceToolRequest, taskID: String, taskTitle: String, performer: DeviceToolPerforming): PendingDeviceTool {
        var pending = PendingDeviceTool(taskID, taskTitle, request)
        if (request.tool == DeviceToolRequest.Tool.SearchContacts) {
            pending = if (performer.contactsAccess.isUsable) {
                pending.copy(matches = performer.searchContacts(request.query, request.limit))
            } else {
                pending.copy(needsContactsAccess = true)
            }
        }
        return pending
    }

    /**
     * The result for the user's answer, or null when the answer only moved the card on (Allow on
     * a contact search: matches appear and the user still picks one; [Resolution.pending] then
     * holds the updated card).
     */
    data class Resolution(val result: DeviceToolResult?, val pending: PendingDeviceTool)

    suspend fun result(pending: PendingDeviceTool, choice: DeviceToolChoice, performer: DeviceToolPerforming): Resolution {
        val request = pending.request
        val tool = request.tool
        if (choice is DeviceToolChoice.Decline) return Resolution(declined(request), pending)
        return when {
            tool == DeviceToolRequest.Tool.ProposeMessage && choice is DeviceToolChoice.Send -> {
                val body = choice.text.trim()
                if (body.isEmpty()) return Resolution(DeviceToolResult.failure("empty_body", "The message was empty."), pending)
                val outcome = performer.composeMessage(request.recipients, body, request.subject)
                Resolution(composed(outcome), pending)
            }
            tool == DeviceToolRequest.Tool.SearchContacts && choice is DeviceToolChoice.Pick ->
                Resolution(DeviceToolResult(ok = true, query = request.query, contacts = listOf(choice.contact)), pending)
            tool == DeviceToolRequest.Tool.SearchContacts && choice is DeviceToolChoice.Allow -> {
                val access = performer.requestContactsAccess()
                if (!access.isUsable) return Resolution(contactsDenied(access), pending)
                val matches = performer.searchContacts(request.query, request.limit)
                Resolution(null, pending.copy(needsContactsAccess = false, matches = matches))
            }
            tool == DeviceToolRequest.Tool.RequestPermission && choice is DeviceToolChoice.Allow -> {
                val access = performer.requestContactsAccess()
                Resolution(if (access.isUsable) DeviceToolResult(ok = true, status = access.rawValue) else contactsDenied(access), pending)
            }
            else -> Resolution(DeviceToolResult.failure("invalid_choice", "The device could not apply that answer."), pending)
        }
    }

    /**
     * Android: the messaging app does not report whether the user sent the message, so an opened
     * composer is reported as such and the agent must not claim it was sent.
     */
    private fun composed(outcome: MessageComposeOutcome): DeviceToolResult = when (outcome) {
        MessageComposeOutcome.Sent -> DeviceToolResult(ok = true, status = outcome.rawValue)
        MessageComposeOutcome.Opened -> DeviceToolResult(
            ok = true, status = outcome.rawValue,
            error = "The messaging app opened with the message; Android does not report whether the user sent it. Do not say it was sent.",
        )
        else -> DeviceToolResult(ok = false, status = outcome.rawValue, error = "The user did not send the message (${outcome.rawValue}).")
    }

    private fun declined(request: DeviceToolRequest): DeviceToolResult = when (request.tool) {
        DeviceToolRequest.Tool.ProposeMessage -> DeviceToolResult(
            ok = false, status = "cancelled", reason = "declined",
            error = "The user chose not to send this message. Do not retry; ask what they want instead.",
        )
        DeviceToolRequest.Tool.RequestPermission ->
            DeviceToolResult(ok = false, status = "denied", reason = "authorization_denied", error = "The user declined the permission.")
        else -> DeviceToolResult.failure("declined", "The user chose not to share a contact. Do not ask again this turn.")
    }

    private fun contactsDenied(access: ContactsAccess) = DeviceToolResult(
        ok = false, status = access.rawValue, reason = "authorization_denied",
        error = "Contacts access is off. The user can turn it on in Settings.",
    )
}
