package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.core.models.DeviceToolResult
import com.friend.ios.network.endpoints.AgentAPI
import com.friend.ios.network.endpoints.VoiceMessagesAPI
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/*
 * Port of `ChatStore+DeviceTools.swift`: "Omi asks" in the chat, the same device tool round trip
 * as agent runs (`DeviceToolResolver`), for the chat UI to render `pendingDeviceTool`. Nothing
 * runs without the user's tap. Also `ask(voiceFile:)` of `ChatStore.swift`.
 *
 * The chat's API is `ChatAPI`; the result post (`AgentAPI`) and the transcription
 * (`VoiceMessagesAPI`) come from the same client in the app (`APIClientProtocol`).
 */

/** The user's answer to the pending call. */
suspend fun ChatStore.answerDeviceTool(choice: DeviceToolChoice) {
    val current = pendingDeviceTool ?: return
    val messageID = pendingDeviceToolMessageID
    // Off the card while the system sheet is up, so a second tap cannot answer twice.
    pendingDeviceTool = null
    val performer = deviceTools
    val resolution = if (performer != null) {
        DeviceToolResolver.result(current, choice, performer)
    } else {
        DeviceToolResolver.Resolution(DeviceToolResult.failure("surface_unavailable", "This device cannot run tools right now."), current)
    }
    val result = resolution.result
    if (result == null) {
        // Contacts allowed: the matches show and the user still picks one.
        if (isStreaming && pendingDeviceToolMessageID == messageID) pendingDeviceTool = resolution.pending
        return
    }
    pendingDeviceToolMessageID = null
    postDeviceToolResult(current.request.id, result)
}

/**
 * A `tool:` frame: answered at once when there is nothing to ask, else it waits under the answer
 * as "Omi asks" (the agent's stream waits meanwhile).
 */
internal fun ChatStore.receive(request: DeviceToolRequest, messageID: String) {
    pendingDeviceToolMessageID = messageID
    scope.launch {
        val immediate = DeviceToolResolver.immediateResult(request, deviceTools)
        if (immediate != null) {
            pendingDeviceToolMessageID = null
            postDeviceToolResult(request.id, immediate)
            return@launch
        }
        val performer = deviceTools ?: return@launch
        val pending = DeviceToolResolver.prepare(request, "", "", performer)
        // The turn may have ended while the phone looked up contacts.
        if (pendingDeviceToolMessageID != messageID || !isStreaming) return@launch
        pendingDeviceTool = pending
    }
}

private suspend fun ChatStore.postDeviceToolResult(callID: String, result: DeviceToolResult) {
    try {
        (api as? AgentAPI)?.sendDeviceToolResult(callID, result)
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        // The agent stopped waiting (timeout or the turn ended); it answers without it.
    }
}

/** Debug builds: an "Omi asks" card under the newest answer without a turn (screenshots). Answers reach no agent. */
fun ChatStore.showDemoQuestion(pending: PendingDeviceTool) {
    pendingDeviceToolMessageID = messages.lastOrNull { it.sender == ChatMessage.Sender.Omi }?.id
    pendingDeviceTool = pending
}

/**
 * A question spoken into the Omi that the phone could not transcribe: the backend writes it down
 * (`v2/voice-message/transcribe`, nothing stored) and it is asked like a typed one in the pinned
 * main chat. [onFirstAnswer] fires when the answer starts (the Omi buzzes).
 */
suspend fun ChatStore.ask(voiceFile: String, audio: ByteArray, onFirstAnswer: () -> Unit = {}): ChatStore.VoiceAnswer {
    if (isStreaming) return ChatStore.VoiceAnswer.Failed
    if (chatApp != null) talk(null)
    val transcriber = api as? VoiceMessagesAPI ?: return ChatStore.VoiceAnswer.Failed
    val question = try {
        transcriber.transcribeVoiceMessage(voiceFile, audio)
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        return ChatStore.VoiceAnswer.Failed
    }
    if (question.isEmpty()) return ChatStore.VoiceAnswer.NoSpeech
    return ask(question, onFirstAnswer)
}
