package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Recommendation
import com.friend.ios.network.endpoints.ForYouItem
import java.time.Instant
import java.time.ZoneId

/**
 * Port of `HomeAttention.swift`: Home's "Needs you" (docs/CHAT-FIRST.md): at most
 * [needsYouLimit] cards in a fixed order (the day's tidy-up, Omi asks, finished runs to review,
 * What matters now, the condensed important tasks, one connection), and "Later" for everything
 * else that wants attention some time (put off tasks, overflow, Omi's running work, tips). Pure,
 * so the order is testable.
 *
 * Home task card (docs/HOME_TASK_CARD.md): a task whose run is active keeps its card in place
 * (the card shows the run); once the run ends, the finished or needs-help card replaces it.

 */
object HomeAttention {
    sealed interface Item {
        val id: String

        /** The daily AI tidy-up's suggestion ("Tidy up: merge 6, mark 4 done"). */
        data class TidyUp(val proposal: TaskTidyUp.Proposal) : Item {
            override val id: String get() = "tidyup"
        }

        /** Omi is waiting on the user mid-run ("Omi asks"): first, since the run waits for it. */
        data class OmiAsks(val pending: PendingDeviceTool) : Item {
            override val id: String get() = "asks.${pending.id}"
        }

        /** A finished run the user has not opened yet. */
        data class Finished(val run: AgentStore.Run) : Item {
            override val id: String get() = "finished.${run.id}"
        }

        /** Several finished runs as one card ("Omi finished 3 tasks"); each is in Later too. */
        data class FinishedGroup(val runs: List<AgentStore.Run>) : Item {
            override val id: String get() = "finished"
        }

        data class Working(val run: AgentStore.Run) : Item {
            override val id: String get() = "working.${run.id}"
        }

        /** A run Omi could not finish: the user takes it from here. */
        data class NeedsHelp(val run: AgentStore.Run) : Item {
            override val id: String get() = "help.${run.id}"
        }

        /** A backend recommendation ("What matters now") without a task of its own. */
        data class RecommendationItem(val recommendation: Recommendation) : Item {
            override val id: String get() = "recommendation.${recommendation.id}"
        }

        /** A condensed task card (duplicates merged, ranked; [TaskConsolidation]). */
        data class Task(val card: TaskConsolidation.Card) : Item {
            override val id: String get() = "task.${card.id}"
        }

        data class Nudge(val item: ForYouItem) : Item {
            override val id: String get() = "nudge.${item.id}"
        }

        /** "Who is this?": a voice from a recent conversation to name (VoicesStore). */
        data class SpeakerPrompt(val prompt: com.friend.ios.core.models.SpeakerPrompt) : Item {
            override val id: String get() = "speaker.${prompt.id}"
        }

        /** "Ask Omi with Siri", until tapped or dismissed. */
        data object SiriTip : Item {
            override val id: String get() = "siri"
        }

        /**
         * "Connect Google Calendar?": a connection Omi works better with (calendar, mail, health),
         * offered one at a time while the account is new.
         */
        data class Connect(val connection: String) : Item {
            override val id: String get() = "connect.$connection"
        }
    }

    /** Cards in "Needs you", hard. */
    const val needsYouLimit = 5
    /** Backend recommendations without a task taken at most (the rest wait for the next refresh). */
    const val maxRecommendations = 2

    data class Input(
        val runs: List<AgentStore.Run> = emptyList(),
        /** Device tool calls waiting for the user (`AgentStore.pendingDeviceTools`). */
        val asks: List<PendingDeviceTool> = emptyList(),
        val openedRunIDs: Set<String> = emptySet(),
        val recommendations: List<Recommendation> = emptyList(),
        /** Every task (`TasksStore.tasks`); the cards come from [TaskConsolidation]. */
        val tasks: List<ActionItem> = emptyList(),
        /** Task id -> "Later" until. */
        val snoozes: Map<String, Instant> = emptyMap(),
        /** Task id -> the words it was extracted from, when its conversation is loaded. */
        val quotes: Map<String, String> = emptyMap(),
        /** The tidy-up's suggestion, when it has changes; its `important` list ranks tasks. */
        val tidyUp: TaskTidyUp.Proposal? = null,
        /** The next "Who is this?" question (`VoicesStore.currentPrompt`). */
        val speakerPrompt: com.friend.ios.core.models.SpeakerPrompt? = null,
        val nudges: List<ForYouItem> = emptyList(),
        val showsSiriTip: Boolean = false,
        /** Connections to suggest, most useful first (Home shows the first). */
        val connect: List<String> = emptyList(),
        val now: Instant = Instant.now(),
        val zone: ZoneId = ZoneId.systemDefault(),
    )

    data class Inbox(val needsYou: List<Item>, val later: List<Item>) {
        val isEmpty: Boolean get() = needsYou.isEmpty() && later.isEmpty()
    }

    fun inbox(input: Input): Inbox {
        val runs = input.runs.sortedByDescending { it.startedAt }
        val ranked = mutableListOf<Item>()
        input.tidyUp?.let { if (!it.isEmpty) ranked += Item.TidyUp(it) }
        ranked += input.asks.map(Item::OmiAsks)

        // Finished runs to review: two or more fold into one card, each one waits in Later.
        val finished = runs.filter { it.state is AgentStore.RunState.Done && it.id !in input.openedRunIDs }
        val laterRuns = mutableListOf<Item>()
        if (finished.size > 1) {
            ranked += Item.FinishedGroup(finished)
            laterRuns += finished.map(Item::Finished)
        } else {
            ranked += finished.map(Item::Finished)
        }
        runs.filter { it.state is AgentStore.RunState.Failed }.forEach { ranked += Item.NeedsHelp(it) }

        // What matters now, then the condensed tasks (a recommendation with a task is that task's card).
        // A running task keeps its card (it shows the run in place); an ended run replaces it.
        val runIDs = input.runs.map { it.id }.toSet()
        val running = input.runs.filter { it.isActive }.map { it.id }.toSet()
        val ended = runIDs - running
        val taskIDs = input.tasks.map { it.id }.toSet()
        val recommendations = input.recommendations.filter { recommendation -> recommendation.taskID?.let { it !in ended } ?: true }
        val (active, snoozed) = TaskConsolidation.cards(
            input.tasks,
            recommendations = recommendations.filter { recommendation -> recommendation.taskID?.let { it in taskIDs } ?: false },
            signals = TaskConsolidation.Signals(
                picks = input.tidyUp?.important.orEmpty().toSet(),
                waiting = recommendations.filter { it.origin == RecommendationOrigin.WaitingOnYou }.mapNotNull { it.taskID }.toSet(),
                handled = ended, running = running, snoozes = input.snoozes, quotes = input.quotes, now = input.now, zone = input.zone,
            ),
        )
        ranked += active.filter { it.recommendation != null }.map(Item::Task)
        // A recommendation whose task is not loaded (or has none) stays a suggestion of its own.
        ranked += recommendations.filter { recommendation -> recommendation.taskID?.let { it !in taskIDs } ?: true }
            .take(maxRecommendations).map(Item::RecommendationItem)
        ranked += active.filter { it.recommendation == null }.map(Item::Task)
        input.connect.firstOrNull()?.let { ranked += Item.Connect(it) }

        val needsYou = ranked.take(needsYouLimit)
        val later = ranked.drop(needsYouLimit).toMutableList<Item>()
        later += snoozed.map(Item::Task)
        later += laterRuns
        // A run that waits on the user shows as its question, and a running task as its own card,
        // not as "working" too.
        val carded = (active + snoozed).flatMap { it.group.ids }.toSet()
        val asking = input.asks.map { it.taskID }.toSet()
        later += runs.filter { it.isActive && it.id !in asking && it.id !in carded }.map(Item::Working)
        input.speakerPrompt?.let { later += Item.SpeakerPrompt(it) }
        later += input.nudges.map(Item::Nudge)
        if (input.showsSiriTip) later += Item.SiriTip
        return Inbox(needsYou, later)
    }
}

/**
 * Port of `HomeTapTargets.swift`: where tapping a Home card goes. Every card goes somewhere (no
 * dead taps): a task opens its detail, a suggestion its task or conversation (or the chat, asked
 * about it), the tidy-up its review. The card's pills keep their own actions.
 */
object HomeTapTargets {
    sealed interface Target {
        /** Omi's run on this task (progress, question, result). */
        data class Run(val id: String) : Target
        /** Unfolds Later (several finished runs). */
        data object Later : Target
        data object SiriTip : Target
        /** The "Who is this?" sheet. */
        data object SpeakerPrompt : Target
        data class Conversation(val id: String) : Target
        /** The task's detail sheet. */
        data class Task(val id: String) : Target
        /** The Chat tab with this question in the composer. */
        data class Ask(val text: String) : Target
        data object TidyUp : Target
        /** The connect flow for this integration. */
        data class Connect(val id: String) : Target
    }

    fun target(item: HomeAttention.Item): Target = when (item) {
        is HomeAttention.Item.TidyUp -> Target.TidyUp
        is HomeAttention.Item.OmiAsks -> Target.Run(item.pending.taskID)
        is HomeAttention.Item.Finished -> Target.Run(item.run.id)
        is HomeAttention.Item.Working -> Target.Run(item.run.id)
        is HomeAttention.Item.NeedsHelp -> Target.Run(item.run.id)
        is HomeAttention.Item.FinishedGroup -> Target.Later
        is HomeAttention.Item.RecommendationItem -> target(item.recommendation)
        is HomeAttention.Item.Task -> Target.Task(item.card.task.id)
        is HomeAttention.Item.Nudge -> when (val target = item.item.target) {
            is ForYouItem.Target.Conversation -> Target.Conversation(target.id)
            is ForYouItem.Target.Task -> Target.Task(target.id)
            null -> Target.Ask(item.item.title)
        }
        HomeAttention.Item.SiriTip -> Target.SiriTip
        is HomeAttention.Item.SpeakerPrompt -> Target.SpeakerPrompt
        is HomeAttention.Item.Connect -> Target.Connect(item.connection)
    }

    private fun target(recommendation: Recommendation): Target {
        recommendation.taskID?.let { return Target.Task(it) }
        recommendation.conversationIDs.firstOrNull()?.let { return Target.Conversation(it) }
        return Target.Ask(recommendation.action.ifEmpty { recommendation.headline })
    }
}
