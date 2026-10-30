package com.friend.ios.features.today

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Recommendation
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.rememberHaptics
import com.friend.ios.network.endpoints.ForYouItem
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.decide
import com.friend.ios.service.stores.HomeAttention
import com.friend.ios.service.stores.TasksStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/**
 * Port of `NeedsYouSection+Actions.swift`: the long-press menus, feedback to the backend and the
 * small helpers the cards share.
 */
internal class NeedsYouActions(
    private val state: NeedsYouState,
    val tasks: TasksStore,
    val conversations: ConversationsStore,
    val agent: AgentStore,
    private val scope: CoroutineScope,
    private val haptics: DSHaptics,
    /** The "Who is this?" prompts (`VoicesStore`). */
    val voices: com.friend.ios.service.stores.VoicesStore? = null,
) {
    suspend fun appeared(item: HomeAttention.Item) {
        when (item) {
            is HomeAttention.Item.Nudge -> state.forYou?.markShown(item.item)
            // The card is the prompt on screen: starts the backend's daily cooldown.
            is HomeAttention.Item.SpeakerPrompt -> voices?.promptsShown()
            else -> Unit
        }
    }

    fun task(id: String): ActionItem? = tasks.tasks.firstOrNull { it.id == id }

    fun send(feedback: ForYouItem.Feedback, nudge: ForYouItem) {
        haptics.selection()
        scope.launch { state.forYou?.send(feedback, nudge) }
    }

    fun open(nudge: ForYouItem) {
        scope.launch { state.forYou?.send(ForYouItem.Feedback.Opened, nudge) }
        when (val target = nudge.target) {
            is ForYouItem.Target.Conversation -> state.onOpenConversation(target.id)
            // A task opens the conversation it came from.
            is ForYouItem.Target.Task -> task(target.id)?.conversationID?.let(state.onOpenConversation)
            null -> Unit
        }
    }

    /** "Not now" / Dismiss on the "Who is this?" card: Omi asks less often. */
    fun dismissPrompts() {
        scope.launch { voices?.dismissPrompts() }
    }

    /** A nudge the user followed: the proactivity feed hears it. */
    fun opened(item: HomeAttention.Item) {
        if (item is HomeAttention.Item.Nudge) scope.launch { state.forYou?.send(ForYouItem.Feedback.Opened, item.item) }
    }

    fun decide(recommendation: Recommendation, decision: Recommendation.Decision) {
        haptics.selection()
        agent.background { agent.decide(recommendation, decision) }
    }

    fun resume(task: ActionItem) {
        haptics.tap(DSHaptics.Style.Medium)
        agent.background { agent.resume(task, conversations.source(task)?.title) }
    }

    /** Omi starts on the task now (the hand-over sheet's primary button, without the sheet). */
    fun takeOver(task: ActionItem) {
        agent.background { agent.takeOver(task, conversations.source(task)?.title) }
    }
}

@Composable
internal fun rememberNeedsYouActions(state: NeedsYouState): NeedsYouActions =
    NeedsYouActions(
        state, LocalTasksStore.current, LocalConversationsStore.current, LocalAgentStore.current, rememberCoroutineScope(), rememberHaptics(),
        voices = com.friend.ios.service.LocalVoicesStore.current,
    )

/** The long-press menu of a decision card (empty: none). */
@Composable
internal fun menu(item: HomeAttention.Item, actions: NeedsYouActions): List<MenuSection> = when (item) {
    is HomeAttention.Item.Nudge -> {
        val nudge = item.item
        listOf(
            MenuSection(
                items = listOf(
                    MenuItem(L("helpful"), if (nudge.feedback == ForYouItem.Feedback.Helpful.rawValue) "hand.thumbsup.fill" else "hand.thumbsup") {
                        actions.send(ForYouItem.Feedback.Helpful, nudge)
                    },
                    MenuItem(L("notHelpful"), if (nudge.feedback == ForYouItem.Feedback.NotHelpful.rawValue) "hand.thumbsdown.fill" else "hand.thumbsdown") {
                        actions.send(ForYouItem.Feedback.NotHelpful, nudge)
                    },
                ),
            ),
            MenuSection(
                items = listOf(
                    MenuItem(L("dismiss"), "xmark") { actions.send(ForYouItem.Feedback.Dismissed, nudge) },
                    MenuItem(L("stopThese"), "bell.slash", destructive = true) { actions.send(ForYouItem.Feedback.StopThese, nudge) },
                ),
            ),
        )
    }
    is HomeAttention.Item.SpeakerPrompt -> listOf(
        MenuSection(items = listOf(MenuItem(L("dismiss"), "xmark") { actions.dismissPrompts() })),
    )
    // The Siri tip is iOS only; Android never shows the card, so it has no menu.
    HomeAttention.Item.SiriTip -> emptyList()
    is HomeAttention.Item.RecommendationItem -> {
        val recommendation = item.recommendation
        listOf(
            MenuSection(
                items = listOf(
                    MenuItem(L("nativeForYouAlreadyHandled"), "checkmark.seal") { actions.decide(recommendation, Recommendation.Decision.AlreadyHandled) },
                    MenuItem(L("nativeForYouLater"), "clock") { actions.decide(recommendation, Recommendation.Decision.Later) },
                ),
            ),
            MenuSection(items = listOf(MenuItem(L("notNow"), "xmark") { actions.decide(recommendation, Recommendation.Decision.Dismiss) })),
        )
    }
    else -> emptyList()
}
