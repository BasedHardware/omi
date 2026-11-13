package com.friend.ios.features.today

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DecisionCard
import com.friend.ios.features.components.displayTitle
import com.friend.ios.network.endpoints.ForYouItem
import com.friend.ios.core.models.Recommendation
import com.friend.ios.features.components.AgentWording
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.canTakeOver
import com.friend.ios.service.stores.openRecommendations
import com.friend.ios.service.stores.ForYouStore
import com.friend.ios.service.stores.HomeAttention
import com.friend.ios.service.stores.HomeTapTargets
import com.friend.ios.service.stores.TaskTidyUp
import com.friend.ios.service.stores.specificWhyNow

/**
 * Port of `NeedsYouSection.swift`: Home's "Needs you": at most five decision cards in
 * `HomeAttention` order (the day's tidy-up, Omi asks, finished runs, What matters now, the
 * condensed tasks, one connection), then "Later (n)" folded, then a quiet "All tasks (n)" row to
 * the full list. Gone when empty. Health Connect takes Apple Health's place among the connections
 * to suggest (`ConnectSuggestion`). The Siri tip is iOS only (Siri and App Shortcuts): Android
 * never shows it (`showsSiriTip = false`); its launcher shortcuts need no tip.
 */
@Composable
fun NeedsYouSection(
    forYou: ForYouStore?,
    onOpenRun: (String) -> Unit,
    onHandOver: (ActionItem) -> Unit,
    onOpenConversation: (String) -> Unit,
    onOpenSiriTip: () -> Unit,
    onOpenAllTasks: () -> Unit,
    onOpenTask: (ActionItem) -> Unit,
    onAskOmi: (String) -> Unit,
    modifier: Modifier = Modifier,
    /** "Moved to Later" with Undo after a swipe (shown by the screen, above the Omi bar). */
    laterUndo: TaskLaterUndo? = null,
) {
    val tasks = LocalTasksStore.current
    val conversations = LocalConversationsStore.current
    val agent = LocalAgentStore.current
    var showsLater by rememberSaveable { mutableStateOf(DebugLaunch.flag("omiShowLater")) }
    var reviewsTidyUp by rememberSaveable { mutableStateOf(false) }
    var showsSpeakerPrompt by rememberSaveable { mutableStateOf(false) }
    val voices = com.friend.ios.service.LocalVoicesStore.current
    val capabilities = com.friend.ios.service.LocalCapabilitiesStore.current
    val health = com.friend.ios.service.LocalAppleHealthStore.current
    val defaults = androidx.compose.ui.platform.LocalContext.current.getSharedPreferences("omi.native", android.content.Context.MODE_PRIVATE)
    var connectDismissed by remember { mutableStateOf(defaults.getString(ConnectSuggestion.dismissedKey, "") ?: "") }
    val firstHomeAt = remember { ConnectSuggestion.firstHomeAt(defaults) }
    /**
     * The recommendation of a card Omi started on, while its run lasts: "do now" takes it out of
     * the open ones, and without it the card would drop below the others mid-run.
     */
    var kept by remember { mutableStateOf(mapOf<String, Recommendation>()) }
    val state = NeedsYouState(
        forYou = forYou, onOpenRun = onOpenRun, onHandOver = onHandOver, onOpenConversation = onOpenConversation,
        onOpenSiriTip = onOpenSiriTip, onOpenAllTasks = onOpenAllTasks, onOpenTask = onOpenTask, onAskOmi = onAskOmi,
        showLater = { showsLater = true }, reviewTidyUp = { reviewsTidyUp = true },
        showSpeakerPrompt = { showsSpeakerPrompt = true },
        dismissConnect = { id ->
            connectDismissed = if (connectDismissed.isEmpty()) id else "$connectDismissed,$id"
            defaults.edit().putString(ConnectSuggestion.dismissedKey, connectDismissed).apply()
        },
        keepRecommendation = { id, recommendation -> kept = kept + (id to recommendation) },
        laterUndo = laterUndo,
    )

    // The words each open task was extracted from, where its conversation is loaded.
    val quotes = tasks.tasks.filter { it.isOpen }.mapNotNull { task -> conversations.quote(task)?.let { task.id to it } }.toMap()
    val open = agent.openRecommendations(tasks.tasks)
    val keptNow = kept.filterKeys { agent.runs[it]?.isActive == true }.values.filter { keep -> open.none { it.id == keep.id } }
    val inbox = HomeAttention.inbox(
        HomeAttention.Input(
            // A failed run on a task Omi should not take (a climb, someone else's job) is not news.
            runs = agent.workItems(tasks.tasks).filter { run ->
                if (run.state !is AgentStore.RunState.Failed) return@filter true
                val task = tasks.tasks.firstOrNull { it.id == run.id } ?: return@filter true
                agent.canTakeOver(task)
            },
            asks = agent.pendingDeviceTools,
            openedRunIDs = agent.openedRunIDs,
            recommendations = open + keptNow,
            tasks = tasks.tasks,
            snoozes = tasks.snoozes,
            quotes = quotes,
            tidyUp = tasks.currentTidyUp,
            speakerPrompt = voices.currentPrompt,
            nudges = forYou?.items.orEmpty(),
            showsSiriTip = false,
            connect = ConnectSuggestion.ids(capabilities, health, connectDismissed, firstHomeAt),
        ),
    )

    // Where open tasks came from: the "From: ..." line, and the words that tell a request to
    // someone else or a guessed deadline apart (newest first, each conversation once).
    LaunchedEffect(tasks.tasks.size) { conversations.loadSources(tasks.tasks.filter { it.isOpen }) }
    LaunchedEffect(Unit) { ConnectSuggestion.prepare(capabilities, health) }

    Column(
        modifier
            .fillMaxWidth()
            .animateContentSize(DS.Motion.standard())
            .padding(bottom = if (inbox.isEmpty && tasks.openCount == 0) 0.dp else DS.Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm + 2.dp),
    ) {
        if (inbox.needsYou.isNotEmpty()) {
            SectionLabel(L("nativeForYouNeedsYou"))
            inbox.needsYou.forEach { item -> key(item.id) { Card(item, state) } }
        }
        if (inbox.later.isNotEmpty()) {
            LaterRow(inbox.later.size, showsLater) { showsLater = !showsLater }
            if (showsLater) inbox.later.forEach { item -> key(item.id) { Card(item, state) } }
        }
        if (tasks.openCount > 0) AllTasksRow(tasks.openCount, onOpenAllTasks)
    }
    if (reviewsTidyUp && tasks.currentTidyUp != null) {
        TidyUpSheet(onDismiss = { reviewsTidyUp = false })
    }
    if (showsSpeakerPrompt) SpeakerPromptSheet(onDismiss = { showsSpeakerPrompt = false })
}

/** What the cards need from the section (the Swift section's properties and closures). */
internal class NeedsYouState(
    val forYou: ForYouStore?,
    val onOpenRun: (String) -> Unit,
    val onHandOver: (ActionItem) -> Unit,
    val onOpenConversation: (String) -> Unit,
    val onOpenSiriTip: () -> Unit,
    val onOpenAllTasks: () -> Unit,
    val onOpenTask: (ActionItem) -> Unit,
    val onAskOmi: (String) -> Unit,
    val showLater: () -> Unit,
    val reviewTidyUp: () -> Unit,
    /** The "Who is this?" sheet. */
    val showSpeakerPrompt: () -> Unit = {},
    /** "Not now" on a connection: hidden for good (Settings still has it). */
    val dismissConnect: (String) -> Unit = {},
    /** Keeps a started card's recommendation while its run lasts (task id, recommendation). */
    val keepRecommendation: (String, Recommendation) -> Unit = { _, _ -> },
    val laterUndo: TaskLaterUndo? = null,
)

@Composable
private fun SectionLabel(text: String) {
    Text(text, style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary, modifier = Modifier.semantics { heading() })
}

/** "Later (3)": tap to unfold what can wait. */
@Composable
private fun LaterRow(count: Int, showsLater: Boolean, onToggle: () -> Unit) {
    val haptics = rememberHaptics()
    val rotation by animateFloatAsState(if (showsLater) 180f else 0f, DS.Motion.standard(), label = "later")
    HStack(
        Modifier
            .padding(top = DS.Spacing.xs)
            .fillMaxWidth()
            .heightIn(min = 36.dp)
            .plainButton {
                haptics.selection()
                onToggle()
            },
        spacing = DS.Spacing.xs,
    ) {
        Text(L("nativeHomeLaterCount", "$count"), style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary)
        SFImage("chevron.down", Modifier.rotate(rotation), size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary)
        Spacer(Modifier.weight(1f))
    }
}

/** The full task list, one level down. */
@Composable
private fun AllTasksRow(openCount: Int, onOpenAllTasks: () -> Unit) {
    HStack(Modifier.fillMaxWidth().heightIn(min = 40.dp).plainButton(onClick = onOpenAllTasks), spacing = DS.Spacing.sm) {
        SFImage("checklist", size = 15.sp, tint = DS.Palette.inkSecondary)
        Text(L("nativeHomeAllTasksCount", "$openCount"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
        Spacer(Modifier.weight(1f))
        SFImage("chevron.right", size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
    }
}

// Cards

@Composable
private fun Card(item: HomeAttention.Item, state: NeedsYouState) {
    when (item) {
        is HomeAttention.Item.Connect -> ConnectSuggestionCard(item.connection) { state.dismissConnect(item.connection) }
        is HomeAttention.Item.Task -> TaskCard(item.card, state)
        is HomeAttention.Item.TidyUp -> TidyUpCard(item.proposal, state)
        // Omi waits on the user mid-run: the question with its own choices; the card opens the run.
        is HomeAttention.Item.OmiAsks -> com.friend.ios.features.components.OmiAsksCard(item.pending, onOpen = { state.onOpenRun(item.pending.taskID) })
        else -> DecisionItemCard(item, state)
    }
}

@Composable
private fun TidyUpCard(proposal: TaskTidyUp.Proposal, state: NeedsYouState) {
    val tasks = LocalTasksStore.current
    DecisionCard(
        kicker = DecisionCard.Kicker("sparkles", L("nativeForYouSuggestion"), DS.Palette.agent),
        title = TidyUpWording.title(proposal),
        subtitle = L("nativeTidyUpSubtitle"),
        pills = listOf(
            DecisionCard.Pill(L("nativeTidyUpReview"), isPrimary = true) { state.reviewTidyUp() },
            DecisionCard.Pill(L("notNow")) { tasks.dismissTidyUp() },
        ),
        onTap = { state.reviewTidyUp() },
    )
}

/** Omi's runs, nudges, tips and suggestions without a task (as before on Home). */
@Composable
private fun DecisionItemCard(item: HomeAttention.Item, state: NeedsYouState) {
    val conversations = LocalConversationsStore.current
    val context = androidx.compose.ui.platform.LocalContext.current
    val content = ForYouRow.Content.from(item) { task -> conversations.source(task)?.displayTitle(context) }
    val pills = pills(item, state)
    val lines = contextLines(item, content)
    val actions = rememberNeedsYouActions(state)
    val menu = menu(item, actions)
    LaunchedEffect(item.id) { actions.appeared(item) }
    // Buttons only for a real choice; a single action is the tap on the card.
    DecisionCard(
        kicker = kicker(item),
        title = content.title,
        subtitle = lines.first,
        source = lines.second,
        pulses = content.pulses,
        pills = if (pills.size > 1) pills else emptyList(),
        onTap = action(item, state, actions),
        menu = if (menu.isEmpty()) null else ({ menu }),
    )
}

/** What kind of item this is, in one colored line above the title. */
@Composable
private fun kicker(item: HomeAttention.Item): DecisionCard.Kicker = when (item) {
    is HomeAttention.Item.Finished, is HomeAttention.Item.FinishedGroup ->
        DecisionCard.Kicker("checkmark.circle", L("nativeForYouDone"), DS.Palette.success)
    is HomeAttention.Item.Working -> DecisionCard.Kicker("sparkles", L("nativeForYouWorking"), DS.Palette.agent)
    is HomeAttention.Item.NeedsHelp -> DecisionCard.Kicker(
        if (item.run.isStopped) "pause.circle" else "exclamationmark.triangle",
        if (item.run.isStopped) L("nativeForYouStopped") else L("nativeForYouNeedsYou"), DS.Palette.warning,
    )
    is HomeAttention.Item.RecommendationItem, is HomeAttention.Item.TidyUp, is HomeAttention.Item.Task ->
        DecisionCard.Kicker("sparkles", L("nativeForYouSuggestion"), DS.Palette.agent)
    is HomeAttention.Item.OmiAsks -> com.friend.ios.features.components.OmiAsksPresentation.kicker
    is HomeAttention.Item.Connect -> DecisionCard.Kicker("link", L("nativeForYouConnect"), DS.Palette.agent)
    is HomeAttention.Item.SpeakerPrompt -> DecisionCard.Kicker("person.wave.2", L("nativeForYouWhoWasThat"), DS.Palette.agent)
    is HomeAttention.Item.Nudge, HomeAttention.Item.SiriTip -> DecisionCard.Kicker("lightbulb", L("nativeForYouTip"), DS.Palette.warning)
}

/** The card's buttons: the main thing first (filled), then the quiet way out. */
@Composable
private fun pills(item: HomeAttention.Item, state: NeedsYouState): List<DecisionCard.Pill> {
    val actions = rememberNeedsYouActions(state)
    return when (item) {
        is HomeAttention.Item.Finished -> listOf(DecisionCard.Pill(L("nativeForYouView"), isPrimary = true) { state.onOpenRun(item.run.id) })
        is HomeAttention.Item.NeedsHelp -> buildList {
            // Try again (or resume a stopped run) right here; the reason is the card's line.
            val run = item.run
            val action = run.failure?.let { AgentWording.action(it) }
            val task = actions.task(run.id)
            if (action != null && task != null && actions.agent.canTakeOver(task)) {
                add(DecisionCard.Pill(action, isPrimary = true) { actions.resume(task) })
            }
            add(DecisionCard.Pill(L("nativeForYouView"), isPrimary = isEmpty()) { state.onOpenRun(run.id) })
        }
        is HomeAttention.Item.FinishedGroup -> listOf(DecisionCard.Pill(L("nativeForYouShowAll"), isPrimary = true) { state.showLater() })
        is HomeAttention.Item.Working -> emptyList()
        is HomeAttention.Item.RecommendationItem -> listOf(
            DecisionCard.Pill(L("nativeForYouMarkDone"), isPrimary = true) { actions.decide(item.recommendation, com.friend.ios.core.models.Recommendation.Decision.Complete) },
            DecisionCard.Pill(L("nativeForYouLater")) { actions.decide(item.recommendation, com.friend.ios.core.models.Recommendation.Decision.Later) },
        )
        is HomeAttention.Item.Nudge -> buildList {
            if (item.item.target != null) add(DecisionCard.Pill(L("nativeForYouView"), isPrimary = true) { actions.open(item.item) })
            add(DecisionCard.Pill(L("notNow")) { actions.send(ForYouItem.Feedback.Dismissed, item.item) })
        }
        is HomeAttention.Item.SpeakerPrompt -> listOf(
            DecisionCard.Pill(L("nativeForYouAssign"), isPrimary = true) { state.showSpeakerPrompt() },
            DecisionCard.Pill(L("notNow")) { actions.dismissPrompts() },
        )
        HomeAttention.Item.SiriTip -> listOf(
            DecisionCard.Pill(L("nativeForYouView"), isPrimary = true) { state.onOpenSiriTip() },
            DecisionCard.Pill(L("notNow")) {},
        )
        is HomeAttention.Item.OmiAsks, is HomeAttention.Item.Connect, is HomeAttention.Item.Task, is HomeAttention.Item.TidyUp -> emptyList()
    }
}

/** The tap on the card itself: every card opens something (`HomeTapTargets` names where). */
private fun action(item: HomeAttention.Item, state: NeedsYouState, actions: NeedsYouActions): () -> Unit =
    when (val target = HomeTapTargets.target(item)) {
        is HomeTapTargets.Target.Run -> {
            { state.onOpenRun(target.id) }
        }
        HomeTapTargets.Target.Later -> state.showLater
        HomeTapTargets.Target.SiriTip -> state.onOpenSiriTip
        HomeTapTargets.Target.SpeakerPrompt -> state.showSpeakerPrompt
        is HomeTapTargets.Target.Conversation -> {
            {
                actions.opened(item)
                state.onOpenConversation(target.id)
            }
        }
        is HomeTapTargets.Target.Task -> {
            {
                actions.opened(item)
                val task = actions.task(target.id)
                if (task != null) state.onOpenTask(task) else state.onOpenAllTasks()
            }
        }
        is HomeTapTargets.Target.Ask -> {
            {
                actions.opened(item)
                state.onAskOmi(target.text)
            }
        }
        HomeTapTargets.Target.TidyUp -> state.reviewTidyUp
        // Connection cards run their own flow (`ConnectSuggestionCard`); here for completeness.
        is HomeTapTargets.Target.Connect -> state.onOpenAllTasks
    }

/** A suggestion without a task: the backend's reason when specific, then where it comes from. */
@Composable
private fun contextLines(item: HomeAttention.Item, content: ForYouRow.Content): Pair<String, String?> {
    if (item !is HomeAttention.Item.RecommendationItem) return content.subtitle to null
    val source = TaskCardWording.origin(item.recommendation)
    item.recommendation.specificWhyNow?.let { return it to source }
    return (source ?: "") to null
}
