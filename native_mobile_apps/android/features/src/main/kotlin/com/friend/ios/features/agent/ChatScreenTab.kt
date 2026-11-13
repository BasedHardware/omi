package com.friend.ios.features.agent

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.citations
import com.friend.ios.core.models.ChatQuote
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiChip
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.ChatGrouping
import com.friend.ios.service.stores.ChatStacking
import com.friend.ios.service.stores.ChatStore
import com.friend.ios.service.stores.ChatThreadFilter
import com.friend.ios.service.stores.TasksStore
import com.friend.ios.service.stores.isServiceFailure
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.ZoneId

/**
 * One row of the thread: a message, hand-overs that finished while the app was open (a run of
 * them in a row is one stack), or the line where a new day starts.
 */
sealed interface ChatRow {
    data class Message(val message: ChatMessage) : ChatRow
    data class Run(val run: AgentStore.Run) : ChatRow
    data class Runs(val runs: List<AgentStore.Run>) : ChatRow
    data class Day(val date: Instant) : ChatRow

    val id: String
        get() = when (this) {
            is Message -> message.id
            is Run -> "run-${run.id}"
            is Runs -> "runs-${runs.firstOrNull()?.id ?: ""}"
            is Day -> "day-${date.epochSecond}"
        }

    private val date: Instant?
        get() = when (this) {
            is Message -> message.createdAt
            is Run -> run.finishedAt ?: run.startedAt
            is Runs -> runs.firstOrNull()?.let { it.finishedAt ?: it.startedAt }
            is Day -> null
        }

    companion object {
        /** Finished runs in a row become one stack (the first and "2 more"): never two such cards in a row. */
        fun stacked(rows: List<ChatRow>): List<ChatRow> =
            ChatStacking.stacks(rows) { row -> if (row is Run) "run" else row.id }
                .map { stack -> if (stack.size > 1) Runs(stack.mapNotNull { (it as? Run)?.run }) else stack[0] }

        /**
         * Messages in their order, each finished run (oldest first) before the first message that
         * came after it ended, and a day line before the first row of every day.
         */
        fun merge(messages: List<ChatMessage>, runs: List<AgentStore.Run>, zone: ZoneId = ZoneId.systemDefault()): List<ChatRow> {
            val rows = mutableListOf<ChatRow>()
            val pending = ArrayDeque(runs)
            for (message in messages) {
                while (pending.isNotEmpty() && (pending.first().finishedAt ?: pending.first().startedAt) < message.createdAt) {
                    rows.add(Run(pending.removeFirst()))
                }
                rows.add(Message(message))
            }
            pending.forEach { rows.add(Run(it)) }
            val dated = mutableListOf<ChatRow>()
            var lastDay: java.time.LocalDate? = null
            for (row in rows) {
                row.date?.let { date ->
                    val day = date.atZone(zone).toLocalDate()
                    if (day != lastDay) dated.add(Day(day.atStartOfDay(zone).toInstant()))
                    lastDay = day
                }
                dated.add(row)
            }
            return dated
        }

        /** Room above a row: a few points inside a group, more between groups. */
        fun gap(row: ChatRow, index: Int, positions: Map<String, ChatGrouping.Position>): Dp {
            if (index == 0) return 0.dp
            if (row is Message && positions[row.id]?.isFirst == false) return ChatGroupSpacing
            return DS.Spacing.md
        }
    }
}

/** Hand-overs that ended while the app was open, oldest first. */
internal fun finishedRuns(agent: AgentStore): List<AgentStore.Run> =
    agent.runs.values.filter { !it.isActive && it.finishedAt != null }.sortedBy { it.finishedAt }

/**
 * Where each message sits in its group: steps or cards above an answer start a new group, anything
 * below one (sources, a chart, a failure) ends it.
 */
internal fun groupPositions(rows: List<ChatRow>, chat: ChatStore, playingID: String?): Map<String, ChatGrouping.Position> {
    val latest = chat.messages.lastOrNull()?.id
    return ChatGrouping.positions(
        rows.map { row ->
            val message = (row as? ChatRow.Message)?.message ?: return@map ChatGrouping.Item(row.id, sender = null)
            if (message.sender != ChatMessage.Sender.Omi) {
                return@map ChatGrouping.Item(message.id, ChatMessage.Sender.User, message.createdAt, leadsWithExtras = message.files.isNotEmpty())
            }
            val leads = message.steps.any { !AgentStore.isHeartbeat(it) } || chat.cards(message.id).isNotEmpty() ||
                chat.pendingDeviceToolMessageID == message.id
            val ends = message.citations().isNotEmpty() || message.chart != null || message.failure != null || message.isServiceFailure ||
                (message.id == latest && message.followUp != null) || playingID == message.id
            ChatGrouping.Item(message.id, ChatMessage.Sender.Omi, message.createdAt, leadsWithExtras = leads, endsWithExtras = ends)
        },
    )
}

/** The hand-over a run belongs to, opened from Running now or a finished run's row (`open(_ run:)`). */
internal fun handOverTask(run: AgentStore.Run, tasks: TasksStore): ActionItem =
    tasks.tasks.firstOrNull { it.id == run.id } ?: ActionItem(
        id = run.id, description = run.taskTitle, isCompleted = false, dueAt = null, conversationID = null,
        owner = ActionItem.Owner.User, workstreamID = run.workstreamID, createdAt = null,
    )

/**
 * The tab has no bar of its own (the app header above holds search and "…"): only the search
 * field while searching, the offline line and Running now, each only while it applies.
 */
@Composable
internal fun ChatTabHeader(state: ChatScreenState, offline: Boolean, onOpenRun: (AgentStore.Run) -> Unit) {
    val agent = LocalAgentStore.current
    val hasTopBar = state.isSearching || offline || agent.activeRuns.isNotEmpty()
    Column(
        Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.lg).padding(bottom = if (hasTopBar) DS.Spacing.sm else 0.dp),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        AnimatedVisibility(state.isSearching, enter = fadeIn(), exit = fadeOut()) { SearchBar(state) }
        AnimatedVisibility(offline, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) { OfflineHint() }
        if (!state.isSearching) RunningStrip(onOpen = onOpenRun)
    }
}

@Composable
private fun SearchBar(state: ChatScreenState) {
    val haptics = rememberHaptics()
    val keyboard = LocalSoftwareKeyboardController.current
    val focus = remember { FocusRequester() }
    LaunchedEffect(state.focusSearch) {
        if (!state.focusSearch) return@LaunchedEffect
        delay(50)
        runCatching { focus.requestFocus() }
        keyboard?.show()
        state.focusSearch = false
    }
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        HStack(spacing = DS.Spacing.md) {
            OmiSearchField(L("nativeChatSearchPrompt"), state.query, { state.query = it }, L("nativeChatSearchClear"), Modifier.weight(1f).focusRequester(focus))
            Text(
                L("cancel"), style = DS.Typography.callout, color = DS.Palette.ink,
                modifier = Modifier.plainButton {
                    keyboard?.hide()
                    state.stopSearching()
                },
            )
        }
        HStack(Modifier.horizontalScroll(rememberScrollState()), spacing = DS.Spacing.sm) {
            for (item in ChatThreadFilter.entries) {
                OmiChip(
                    filterTitle(item), systemImage = filterSymbol(item), tint = if (state.filter == item) DS.Palette.agent else null,
                    modifier = Modifier
                        .plainButton {
                            haptics.selection()
                            state.filter = if (state.filter == item) null else item
                        }
                        .semantics { selected = state.filter == item },
                )
            }
        }
    }
}

/**
 * The thread, newest at the bottom by the composer, grouped as in Messages (a few points inside a
 * group, more between groups). Laid out from the bottom (`reverseLayout`), so it opens at the
 * latest message and follows a streaming answer only while the user is at the bottom; scrolling up
 * to read is never yanked back, and older pages land above without a jump.
 */
@Composable
internal fun ChatList(
    list: LazyListState,
    rows: List<ChatRow>,
    state: ChatScreenState,
    historySettled: Boolean,
    bottomPadding: Dp,
    onReply: (ChatMessage) -> Unit,
    onSend: (String) -> Unit,
    onOpenConversation: (String) -> Unit,
    onUpgrade: (() -> Unit)?,
    onJump: (String) -> Unit,
    onAskAboutFile: (String) -> Unit,
    onOpenRun: (AgentStore.Run) -> Unit,
    modifier: Modifier,
) {
    val chat = LocalChatStore.current
    val agent = LocalAgentStore.current
    val voice = com.friend.ios.service.LocalVoicePlaybackStore.current
    val density = LocalDensity.current
    val askAboutFile = L("nativeChatAboutFileDraft", "%s")
    // The widest a bubble gets: 78 % of the thread's width inside its gutters.
    var bubbleWidth by remember { mutableStateOf(300.dp) }
    val positions = groupPositions(rows, chat, voice?.playingID)
    CompositionLocalProvider(LocalChatBubbleWidth provides bubbleWidth) {
        LazyColumn(
            modifier.onSizeChanged { bubbleWidth = with(density) { (it.width.toDp() - DS.Spacing.lg * 2) * 0.78f } },
            state = list,
            reverseLayout = true,
            // Clear of the top fade while the thread rests at its start; clear of the composer below.
            contentPadding = PaddingValues(start = DS.Spacing.lg, end = DS.Spacing.lg, top = DS.Spacing.md, bottom = DS.Spacing.lg + bottomPadding),
        ) {
            if (state.isFiltering) {
                matches(chat.visibleMessages(state.query, state.filter), if (state.filter == ChatThreadFilter.Jobs && state.query.isEmpty()) finishedRuns(agent) else emptyList(), onJump, onOpenRun)
            } else {
                val lastID = chat.messages.lastOrNull()?.id
                for (index in rows.indices.reversed()) {
                    val row = rows[index]
                    item(key = row.id, contentType = row::class.simpleName) {
                        val place = Modifier.animateItem().padding(top = ChatRow.gap(row, index, positions))
                        when (row) {
                            is ChatRow.Message -> {
                                val message = row.message
                                val isLast = message.id == lastID
                                val failed = if (message.sender == ChatMessage.Sender.User) chat.failedAnswer(message.id) else null
                                MessageBubble(
                                    message = message,
                                    isStreaming = chat.isStreaming && isLast,
                                    isLatest = isLast,
                                    position = positions[message.id] ?: ChatGrouping.Position.alone,
                                    // Only the newest answer offers a follow-up; the others need not redraw while typing.
                                    draftIsEmpty = !isLast || state.draft.isEmpty(),
                                    onRetry = { chat.retry(message.id) },
                                    onTryAgain = failed?.let { answer -> { chat.retry(answer.id) } },
                                    onReply = { onReply(message) },
                                    onDelete = { chat.hide(message.id) },
                                    onOpenConversation = onOpenConversation,
                                    onUpgrade = onUpgrade,
                                    onFollowUp = onSend,
                                    onSend = onSend,
                                    onAskAboutFile = { file -> onAskAboutFile(askAboutFile.replace("%s", file.name)) },
                                    modifier = place,
                                )
                            }
                            is ChatRow.Run -> RunOutcomeRow(row.run, onOpen = { onOpenRun(row.run) }, modifier = place.omiColumn())
                            is ChatRow.Runs -> ChatCardStack(row.runs, stackKey = row.id, modifier = place.omiColumn()) { run ->
                                RunOutcomeRow(run, onOpen = { onOpenRun(run) })
                            }
                            is ChatRow.Day -> DayDivider(row.date, place)
                        }
                    }
                }
            }
            if (chat.hasEarlier && !state.isFiltering) {
                item(key = "earlier") {
                    // Reaching the top loads the page before it, again while it stays on screen (the
                    // pause lets a prepended page scroll it away, which cancels the wait).
                    LaunchedEffect(historySettled, chat.messages.size) {
                        if (!historySettled) return@LaunchedEffect
                        delay(200)
                        chat.loadEarlier()
                    }
                    androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(bottom = DS.Spacing.md), contentAlignment = Alignment.Center) { OmiProgress() }
                }
            }
            if (chat.messages.isEmpty() && chat.hasLoaded && chat.chatApp == null && !state.isFiltering) {
                item(key = "greeting") {
                    // Lined up with the app header's words above.
                    Greeting(Modifier.padding(horizontal = DS.Spacing.gutter - DS.Spacing.lg))
                }
            }
            if (chat.messages.isEmpty() && chat.hasLoaded && chat.chatApp != null && !state.isFiltering) {
                item(key = "appGreeting") { Greeting(Modifier) }
            }
        }
    }
}

/**
 * The matches while searching, in thread order (the newest by the composer): a tap goes back to
 * the full thread at that one. Emitted bottom first (the list is laid out from the bottom).
 */
private fun androidx.compose.foundation.lazy.LazyListScope.matches(
    found: List<ChatMessage>,
    runs: List<AgentStore.Run>,
    onJump: (String) -> Unit,
    onOpenRun: (AgentStore.Run) -> Unit,
) {
    // Bottom first: the newest match sits by the composer, the others a row's gap above it.
    found.asReversed().forEachIndexed { index, message ->
        item(key = "match-${message.id}") { SearchMatchRow(message, Modifier.padding(bottom = if (index > 0) DS.Spacing.md else 0.dp)) { onJump(message.id) } }
    }
    runs.asReversed().forEachIndexed { index, run ->
        val below = found.isNotEmpty() || index > 0
        item(key = "matchrun-${run.id}") { RunOutcomeRow(run, onOpen = { onOpenRun(run) }, modifier = Modifier.padding(bottom = if (below) DS.Spacing.md else 0.dp)) }
    }
    if (found.isEmpty() && runs.isEmpty()) {
        item(key = "nothing") {
            androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(top = DS.Spacing.xl * 2), contentAlignment = Alignment.Center) {
                Text(L("nativeChatSearchNothing"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            }
        }
    }
}

/** A message found by search or a filter: who, when, a few lines. */
@Composable
private fun SearchMatchRow(message: ChatMessage, modifier: Modifier, onTap: () -> Unit) {
    Column(
        modifier
            .fillMaxWidth()
            .plainButton(onClick = onTap)
            .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.card))
            .padding(DS.Spacing.md),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
    ) {
        HStack(spacing = DS.Spacing.xs) {
            Text(if (message.sender == ChatMessage.Sender.User) L("nativeChatYou") else "Omi", style = DS.Typography.caption.semibold(), color = DS.Palette.ink)
            Text(MessageTime.dayAndTime(message.createdAt), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
            if (message.files.isNotEmpty()) SFImage("paperclip", size = 11.sp, tint = DS.Palette.inkTertiary)
        }
        Text(
            if (message.text.isEmpty()) message.files.joinToString(", ") { it.name } else ChatQuote.split(message.text).body,
            style = DS.Typography.callout,
            color = DS.Palette.ink,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
    }
}
