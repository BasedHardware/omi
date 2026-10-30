package com.friend.ios.service.stores

import com.friend.ios.core.models.CalendarEventCandidate
import com.friend.ios.core.models.CalendarEventLink
import com.friend.ios.core.models.CaptureRecording
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationPhoto
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import java.time.Instant

// Port of `ConversationDetailStore+Extras.swift`: the detail page's other actions: staying current
// while the backend processes, the linked calendar event, events added to a calendar, photos, other
// devices' recordings and the developer test prompt.

/** Loads again without the loading state (a failure keeps what is shown). */
suspend fun ConversationDetailStore.refresh() {
    try {
        detail = api.conversationDetail(preview.id)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
    }
}

/**
 * Reloads every [intervalMillis] while the conversation is processing, at most [attempts] times
 * (Flutter's activity strip: 5 s, 36 times). Returns when it is done or the coroutine is cancelled.
 */
suspend fun ConversationDetailStore.followProcessing(list: ConversationsStore, intervalMillis: Long = 5_000, attempts: Int = 36) {
    repeat(attempts) {
        val status = conversation.status
        if (!(status == Conversation.Status.Processing || status == Conversation.Status.InProgress) || !currentCoroutineContext().isActive) return
        delay(intervalMillis)
        refresh()
        list.remember(conversation)
    }
}

// Calendar

/** Google Calendar is connected (linking needs it). */
suspend fun ConversationDetailStore.isCalendarConnected(): Boolean = try {
    api.integrationConnected("google_calendar")
} catch (e: Exception) {
    if (e is CancellationException) throw e
    false
}

/** Events from two hours before to two hours after the conversation (an hour long if it has no end). */
suspend fun ConversationDetailStore.calendarCandidates(): List<CalendarEventCandidate>? {
    val (start, end) = window
    return try {
        api.calendarEvents(start.minusSeconds(7200), end.plusSeconds(7200))
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        null
    }
}

/** When the conversation ran, for the "Suggested" event. */
val ConversationDetailStore.window: Pair<Instant, Instant>
    get() {
        val start = conversation.startedAt ?: conversation.createdAt
        return start to (conversation.finishedAt ?: start.plusSeconds(3600))
    }

suspend fun ConversationDetailStore.linkCalendarEvent(eventID: String): CalendarEventLink? {
    val link = try {
        api.linkCalendarEvent(conversation.id, eventID)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        return null
    }
    detail = detail?.copy(calendarEvent = link)
    return link
}

/** Optimistic; the link comes back if the backend refuses. */
suspend fun ConversationDetailStore.unlinkCalendarEvent(): Boolean {
    val old = detail?.calendarEvent
    detail = detail?.copy(calendarEvent = null)
    return try {
        api.unlinkCalendarEvent(conversation.id)
        true
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        detail = detail?.copy(calendarEvent = old)
        false
    }
}

/** An event Omi found was added to the user's calendar (`created`). */
suspend fun ConversationDetailStore.markEventAdded(index: Int) {
    val events = detail?.events ?: return
    if (index !in events.indices || events[index].isCreated) return
    fun set(created: Boolean) {
        val current = detail ?: return
        detail = current.copy(events = current.events.mapIndexed { i, event -> if (i == index) event.copy(isCreated = created) else event })
    }
    set(true)
    try {
        api.setEventsCreated(conversation.id, listOf(index), true)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        set(false)
    }
}

// Photos, recordings, test prompt

/** A photo's image: inline bytes, else fetched (stored photos). */
suspend fun ConversationDetailStore.image(photo: ConversationPhoto): ByteArray? {
    photo.data?.let { return it }
    if (!photo.isStored) return null
    return try {
        api.conversationPhoto(conversation.id, photo.id)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        null
    }
}

/** Takes a recording out of this conversation's group for good, then reloads the page and the list. */
suspend fun ConversationDetailStore.separate(recording: CaptureRecording, list: ConversationsStore): Boolean {
    try {
        api.separateRecording(recording.id)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        return false
    }
    refresh()
    list.load()
    return true
}

/** A store for another conversation (a recording of the same moment) on the same client. */
fun ConversationDetailStore.sibling(conversation: Conversation): ConversationDetailStore =
    ConversationDetailStore(conversation, api, temporaryDirectory)

/** Runs [prompt] over the transcript once (nothing saved); null when it failed. */
suspend fun ConversationDetailStore.testPrompt(prompt: String): String? {
    val text = prompt.trim()
    if (text.isEmpty()) return null
    val summary = try {
        api.testConversationPrompt(conversation.id, text)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        return null
    }
    return summary.replace("**", "")
}
