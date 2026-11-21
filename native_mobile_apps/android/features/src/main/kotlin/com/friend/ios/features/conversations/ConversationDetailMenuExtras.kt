package com.friend.ios.features.conversations

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDigest
import com.friend.ios.core.models.shareURL
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.features.components.PlaceLinks
import com.friend.ios.features.components.displayTitle
import com.friend.ios.service.LocalTasksStore

// Port of `ConversationDetailMenu+Extras.swift`: the "..." menu's entries for the newer actions,
// next to Reprocess.

@Composable
fun extraMenuItems(state: ConversationDetailState): List<MenuItem> {
    val context = LocalContext.current
    val conversation = state.conversation
    val store = state.store
    return buildList {
        if (!conversation.isDiscarded && !(store.isReprocessing || conversation.status == Conversation.Status.Processing)) {
            add(MenuItem(L("summaryTemplate"), "square.grid.2x2") { state.extras.showsTemplates = true })
        }
        if (store.detail?.calendarEvent == null) {
            add(MenuItem(L("linkEvent"), "calendar.badge.plus") { state.extras.linkEvent(store, state.scope) })
        }
        val recordings = store.detail?.recordings.orEmpty()
        if (recordings.isNotEmpty()) {
            add(MenuItem(L("nativeRecordingsCount", "${recordings.size}"), "square.stack.3d.up") { state.extras.showsRecordings = true })
        }
        // Where it happened is not on the page any more (the conversation map has it); it stays one tap away here.
        val place = store.detail?.conversation?.location ?: conversation.location
        if (place != null) {
            val title = place.shortAddress?.let { L("nativeOpenPlaceInMaps", it) } ?: L("nativeOpenInMaps")
            add(MenuItem(title, "map") { openURL(context, PlaceLinks.maps(place)) })
        }
    }
}

/**
 * "Send to my AI": the conversation as clean Markdown (title, date, summary, action items,
 * transcript with times, link) in the share sheet, ready for Claude, ChatGPT or notes.
 */
@Composable
fun rememberSendToMyAI(state: ConversationDetailState): () -> Unit {
    val tasks = LocalTasksStore.current
    val labels = ConversationDigest.Labels(L("summary"), L("nativeActionItems"), L("transcript"), L("nativeLink"))
    val title = state.conversation.displayTitle()
    return {
        val conversation = state.conversation
        val detail = state.store.detail
        val canonical = tasks.tasks(conversation.id)
        val items = if (canonical.isEmpty()) {
            detail?.summaryActionItems.orEmpty().map { ConversationDigest.ActionItemLine(it) }
        } else {
            canonical.map { ConversationDigest.ActionItemLine(it.description, it.isCompleted) }
        }
        val export = ConversationDigest.Export(
            title = title,
            date = conversation.date,
            duration = conversation.duration,
            summary = detail?.summary ?: conversation.overview,
            actionItems = items,
            transcript = detail?.transcript.orEmpty(),
            link = Conversation.shareURL(conversation.id),
        )
        state.haptics?.tap()
        state.share(ShareRequest(listOf(ConversationDigest.markdown(export, labels))))
    }
}
