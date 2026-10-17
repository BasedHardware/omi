package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.core.models.DeviceToolResult
import kotlinx.coroutines.CancellationException

/*
 * Port of `AgentStore+Asks.swift`. "Omi asks": device tool calls during a run
 * (`DeviceToolResolver`). The agent's stream waits while the user decides; nothing is sent,
 * shared or allowed without their tap.
 */

/**
 * A `tool:` frame: answered at once when there is nothing to ask (malformed, unsupported), else
 * it waits for the user as "Omi asks". The agent's stream waits meanwhile.
 */
internal suspend fun AgentStore.ask(request: DeviceToolRequest, task: ActionItem) {
    DeviceToolResolver.immediateResult(request, deviceTools)?.let { immediate ->
        post(immediate, request)
        return
    }
    val performer = deviceTools ?: return
    val pending = DeviceToolResolver.prepare(request, task.id, task.description, performer)
    deviceToolRequests = deviceToolRequests + (task.id to pending)
    update(task.id) { it?.copy(lastProgressAt = now()) }
    onDeviceToolRequest?.invoke(pending)
}

/**
 * The user's tap on "Omi asks". Nothing is sent, shared or allowed without it; a message only
 * opens the messaging app, where the user sends it themselves.
 */
suspend fun AgentStore.answer(pending: PendingDeviceTool, choice: DeviceToolChoice) {
    val current = deviceToolRequests[pending.taskID]?.takeIf { it.id == pending.id } ?: return
    // Off the card while the system sheet is up, so a second tap cannot answer twice.
    deviceToolRequests = deviceToolRequests - pending.taskID
    val performer = deviceTools
    val resolution = if (performer != null) {
        DeviceToolResolver.result(current, choice, performer)
    } else {
        DeviceToolResolver.Resolution(DeviceToolResult.failure("surface_unavailable", "This device cannot run tools right now."), current)
    }
    val result = resolution.result
    if (result == null) {
        // Contacts allowed: the matches show and the user still picks one.
        if (runs[pending.taskID]?.isActive == true) deviceToolRequests = deviceToolRequests + (pending.taskID to resolution.pending)
        return
    }
    post(result, current.request)
}

private suspend fun AgentStore.post(result: DeviceToolResult, request: DeviceToolRequest) {
    try {
        api.sendDeviceToolResult(request.id, result)
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        // The agent stopped waiting (timeout or the turn ended); it answers without it.
    }
}

/** Debug builds: an "Omi asks" card without a run (screenshots). Answers reach no agent. */
fun AgentStore.showDemoQuestion(pending: PendingDeviceTool) {
    deviceToolRequests = deviceToolRequests + (pending.taskID to pending)
}
