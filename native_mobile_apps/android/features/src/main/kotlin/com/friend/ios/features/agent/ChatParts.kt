package com.friend.ios.features.agent

import android.text.format.DateFormat
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ChatFile
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ChatQuote
import com.friend.ios.core.models.citations
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.Formatted
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuPopup
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.MarkdownBlocks
import com.friend.ios.features.components.copyToClipboard
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.ChatAnswerExtras
import com.friend.ios.service.stores.ChatBlockLayout
import com.friend.ios.service.stores.ChatBubbleSplit
import com.friend.ios.service.stores.ChatGrouping
import com.friend.ios.service.stores.ChatDay
import com.friend.ios.service.stores.isServiceFailure
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Port of `MessageBubble` (`ChatParts.swift`). One message in the thread, as in Messages: yours in
 * soft blue on the right, Omi's on the card color on the left, a long answer in a few bubbles
 * (split at its paragraphs), bubbles of one sender grouped, Omi's avatar beside the last bubble of
 * its group. What Omi did (steps, the cards the app draws) sits above its answer in Omi's column,
 * sources and the follow-up below it (only on the newest answer; an older one folds its sources
 * into "2 sources"). Everything you can do with a message is in its long-press menu (reply, copy,
 * rate, delete); a tap shows when it was sent.
 */
@Composable
fun MessageBubble(
    message: ChatMessage,
    isStreaming: Boolean,
    modifier: Modifier = Modifier,
    /** The newest answer: it keeps its source chips and offers its follow-up question. */
    isLatest: Boolean = false,
    /** Where the message sits in its group of one sender. */
    position: ChatGrouping.Position = ChatGrouping.Position.alone,
    /** Nothing typed in the composer (the follow-up question only shows then). */
    draftIsEmpty: Boolean = true,
    /** The failure row's retry (on a failed answer). */
    onRetry: () -> Unit = {},
    /** A question whose answer failed: "Try again" in its menu. */
    onTryAgain: (() -> Unit)? = null,
    onReply: () -> Unit = {},
    onDelete: () -> Unit = {},
    onOpenConversation: ((String) -> Unit)? = null,
    onUpgrade: (() -> Unit)? = null,
    onFollowUp: (String) -> Unit = {},
    /** A prepared answer on a question card: sent as if the user had typed it. */
    onSend: (String) -> Unit = {},
    /** "Ask about it" on a sent file: a question about it waits in the composer. */
    onAskAboutFile: ((ChatFile) -> Unit)? = null,
) {
    var showsTime by rememberSaveable(message.id) { mutableStateOf(false) }
    val haptics = rememberHaptics()
    val toggleTime = {
        haptics.selection()
        showsTime = !showsTime
    }
    if (message.sender == ChatMessage.Sender.User) {
        Question(message, position, showsTime, toggleTime, onTryAgain, onReply, onDelete, onAskAboutFile, modifier)
    } else {
        Answer(
            message, isStreaming, isLatest, position, draftIsEmpty, showsTime, toggleTime, onRetry, onReply, onDelete,
            onOpenConversation, onUpgrade, onFollowUp, onSend, modifier,
        )
    }
}

/** Between the bubbles of one group (and the parts of one answer). */
internal val ChatGroupSpacing = 3.dp

// Yours

@Composable
private fun Question(
    message: ChatMessage,
    position: ChatGrouping.Position,
    showsTime: Boolean,
    toggleTime: () -> Unit,
    onTryAgain: (() -> Unit)?,
    onReply: () -> Unit,
    onDelete: () -> Unit,
    onAskAboutFile: ((ChatFile) -> Unit)?,
    modifier: Modifier,
) {
    val (quote, text) = ChatQuote.split(message.text)
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val labels = MenuLabels.current()
    Column(modifier.fillMaxWidth(), horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        if (message.files.isNotEmpty()) MessageFiles(message.files, onAsk = onAskAboutFile)
        if (text.isNotEmpty()) {
            Box(Modifier.widthIn(max = LocalChatBubbleWidth.current)) {
                ContextMenuBox(
                    sections = {
                        listOfNotNull(
                            MenuSection(
                                header = MessageTime.format(message.createdAt),
                                items = listOfNotNull(
                                    MenuItem(labels.reply, "arrowshape.turn.up.left", action = onReply),
                                    MenuItem(labels.copy, "doc.on.doc") {
                                        copyToClipboard(context, text)
                                        haptics.success()
                                    },
                                    onTryAgain?.let { MenuItem(labels.tryAgain, "arrow.clockwise", action = it) },
                                ),
                            ),
                            MenuSection(items = listOf(MenuItem(labels.hide, "eye.slash", action = onDelete))),
                        )
                    },
                    onTap = toggleTime,
                ) {
                    Column(
                        Modifier.chatBubble(DS.Palette.bubbleUser, isUser = true, position = position),
                        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp),
                    ) {
                        if (quote != null) QuoteLine(quote, onInk = true)
                        Text(text, style = DS.Typography.bubble, color = DS.Palette.onBubbleUser)
                    }
                }
            }
        }
        AnimatedVisibility(showsTime, enter = fadeIn(), exit = fadeOut()) { TimeLabel(message.createdAt) }
    }
}

// Omi's

@Composable
private fun Answer(
    message: ChatMessage,
    isStreaming: Boolean,
    isLatest: Boolean,
    position: ChatGrouping.Position,
    draftIsEmpty: Boolean,
    showsTime: Boolean,
    toggleTime: () -> Unit,
    onRetry: () -> Unit,
    onReply: () -> Unit,
    onDelete: () -> Unit,
    onOpenConversation: ((String) -> Unit)?,
    onUpgrade: (() -> Unit)?,
    onFollowUp: (String) -> Unit,
    onSend: (String) -> Unit,
    modifier: Modifier,
) {
    val failure = answerFailure(message)
    val voice = com.friend.ios.service.LocalVoicePlaybackStore.current
    var showsSources by rememberSaveable(message.id) { mutableStateOf(false) }
    // Keep-alive frames ("Preparing response…") say nothing about the work.
    val steps = message.steps.filter { !AgentStore.isHeartbeat(it) }
    val citations = remember(message.references, message.evidence) { message.citations() }
    val extras = ChatAnswerExtras.shown(
        ChatAnswerExtras.Answer(
            isLatest = isLatest, isStreaming = isStreaming, failed = failure != null, citations = citations.size,
            hasFollowUp = message.followUp != null && message.failure == null && !message.isServiceFailure,
        ),
        draftIsEmpty = draftIsEmpty, isSpeaking = voice != null && voice.playingID == message.id, sourcesExpanded = showsSources,
    )
    val chart = message.chart?.takeIf { failure == null }
    val ended = message.failure == ChatMessage.Failure.Interrupted || message.failure == ChatMessage.Failure.Stopped
    val hasBelow = chart != null || ended || !extras.isEmpty || showsTime
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        if (steps.isNotEmpty()) StepList(steps, isWorking = isStreaming && message.text.isEmpty(), Modifier.omiColumn())
        AnswerCards(message, Modifier.omiColumn())
        ChatBlocks(message, Modifier.omiColumn(), onSend = onSend, onOpenConversation = onOpenConversation)
        when {
            message.text.isEmpty() && isStreaming && steps.isEmpty() -> OmiRow(isLast = true) { TypingBubble() }
            // No reply came through (the backend also streams canned failures as text).
            failure != null -> FailureRow(failure, onRetry, onUpgrade, Modifier.omiColumn())
            // The day's summary is a list, not prose.
            message.kind == ChatMessage.Kind.DaySummary && message.text.isNotEmpty() -> DaySummaryCard(message, Modifier.omiColumn())
            message.text.isNotEmpty() && !ChatBlockLayout.blocksReplaceBody(message) ->
                AnswerBubbles(message, position, onReply, onDelete, toggleTime)
            // The cards carry the turn; only the lines they cannot draw stay as text.
            else -> ChatBlockFallbacks(ChatBlockLayout.fallbackLines(message.blocks), Modifier.omiColumn())
        }
        if (hasBelow) {
            Column(Modifier.omiColumn(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                if (chart != null) ChartCard(chart)
                if (message.failure == ChatMessage.Failure.Interrupted) {
                    FailureRow(ChatMessage.Failure.Interrupted, onRetry, onUpgrade)
                } else if (message.failure == ChatMessage.Failure.Stopped) {
                    HStack(spacing = DS.Spacing.xs + 2.dp) {
                        SFImage("stop.circle", size = 13.sp, tint = DS.Palette.inkTertiary)
                        Text(L("nativeChatStopped"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                    }
                }
                if (extras.stopReading && voice != null) StopReading(voice, message)
                when (val sources = extras.sources) {
                    ChatAnswerExtras.Sources.Chips -> CitationChips(citations, onOpenConversation)
                    is ChatAnswerExtras.Sources.Collapsed -> SourcesLine(sources.count) { showsSources = true }
                    ChatAnswerExtras.Sources.None -> Unit
                }
                AnimatedVisibility(showsTime, enter = fadeIn(), exit = fadeOut()) { TimeLabel(message.createdAt) }
                val followUp = message.followUp
                if (extras.followUp && followUp != null) FollowUpChip(followUp, onFollowUp)
            }
        }
    }
}

/** The answer in a few bubbles, split where its paragraphs end; each one's menu is the whole answer's. */
@Composable
private fun AnswerBubbles(message: ChatMessage, position: ChatGrouping.Position, onReply: () -> Unit, onDelete: () -> Unit, toggleTime: () -> Unit) {
    val parts = remember(message.text) { ChatBubbleSplit.split(message.text) }
    Column(verticalArrangement = Arrangement.spacedBy(ChatGroupSpacing)) {
        parts.forEachIndexed { index, part ->
            val place = ChatGrouping.Position(isFirst = position.isFirst && index == 0, isLast = position.isLast && index == parts.size - 1)
            OmiRow(isLast = place.isLast) {
                AnswerMenuBox(message, onReply, onDelete, MessageTime.format(message.createdAt), toggleTime) {
                    MarkdownBlocks(
                        part, Modifier.chatBubble(DS.Palette.bubbleAssistant, isUser = false, position = place),
                        style = DS.Typography.bubble, color = DS.Palette.ink,
                    )
                }
            }
        }
    }
}

/** One bubble in Omi's column: the avatar beside the group's last one. */
@Composable
private fun OmiRow(isLast: Boolean, bubble: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(OmiAvatarColumn - DS.Size.chatAvatar), verticalAlignment = Alignment.Bottom) {
        OmiAvatar(shows = isLast)
        Box(Modifier.weight(1f, fill = false).widthIn(max = LocalChatBubbleWidth.current)) { bubble() }
    }
}

/** An older answer's sources, folded: "2 sources", a tap shows the chips. */
@Composable
private fun SourcesLine(count: Int, onOpen: () -> Unit) {
    val haptics = rememberHaptics()
    HStack(
        Modifier
            .heightIn(min = 24.dp)
            .plainButton {
                haptics.selection()
                onOpen()
            }
            .padding(horizontal = DS.Spacing.xs),
        spacing = DS.Spacing.xs,
    ) {
        SFImage("bubble.left", size = 10.sp, tint = DS.Palette.inkTertiary)
        Text(if (count == 1) L("nativeChatOneSource") else L("nativeChatSourcesCount", count.toString()), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
    }
}

/** The failure shown instead of the answer (an interrupted or stopped answer keeps its text). */
private fun answerFailure(message: ChatMessage): ChatMessage.Failure? = when (message.failure) {
    ChatMessage.Failure.CouldNotAnswer, ChatMessage.Failure.Offline, ChatMessage.Failure.Timeout, ChatMessage.Failure.QuotaExceeded -> message.failure
    ChatMessage.Failure.Interrupted, ChatMessage.Failure.Stopped -> null
    null -> if (message.isServiceFailure) ChatMessage.Failure.CouldNotAnswer else null
}

@Composable
private fun FollowUpChip(question: String, onFollowUp: (String) -> Unit) {
    val haptics = rememberHaptics()
    Box(
        Modifier
            .plainButton {
                haptics.tap()
                onFollowUp(question)
            }
            .heightIn(min = 40.dp)
            .border(1.dp, DS.Palette.hairline, CircleShape)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(question.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" "), style = DS.Typography.callout, color = DS.Palette.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun FailureRow(failure: ChatMessage.Failure, onRetry: () -> Unit, onUpgrade: (() -> Unit)?, modifier: Modifier = Modifier) {
    val text = when (failure) {
        ChatMessage.Failure.Offline -> L("chatReplyOffline")
        ChatMessage.Failure.Timeout -> L("chatReplyTimeout")
        ChatMessage.Failure.QuotaExceeded -> L("chatQuotaExceededReply")
        ChatMessage.Failure.Interrupted -> L("nativeChatInterrupted")
        ChatMessage.Failure.CouldNotAnswer, ChatMessage.Failure.Stopped -> L("nativeChatCouldNotAnswer")
    }
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f, fill = false), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
            SFImage(if (failure == ChatMessage.Failure.QuotaExceeded) "sparkles" else "exclamationmark.triangle.fill", size = 14.sp, tint = DS.Palette.inkSecondary)
            Text(text, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
        }
        if (failure == ChatMessage.Failure.QuotaExceeded) {
            if (onUpgrade != null) Text(L("upgrade"), style = DS.Typography.callout.semibold(), color = DS.Palette.agent, modifier = Modifier.plainButton(onClick = onUpgrade))
        } else {
            Text(L("retry"), style = DS.Typography.callout.semibold(), color = DS.Palette.agent, modifier = Modifier.plainButton(onClick = onRetry))
        }
    }
}

// Shared

@Composable
private fun TimeLabel(date: Instant) {
    Text(
        MessageTime.format(date),
        style = DS.Typography.micro.copy(fontWeight = FontWeight.Normal),
        color = DS.Palette.inkTertiary,
        modifier = Modifier.padding(horizontal = DS.Spacing.xs),
    )
}

/** The menu titles, read once per composition (menus build their rows outside composition). */
internal data class MenuLabels(val reply: String, val copy: String, val tryAgain: String, val hide: String) {
    companion object {
        @Composable
        fun current() = MenuLabels(L("reply"), L("copy"), L("tryAgain"), L("nativeChatHide"))
    }
}

/** When a message was sent: "14:05" today, "Tue 14:05" this week, "3 Oct, 14:05" before. */
object MessageTime {
    fun format(date: Instant, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
        val day = date.atZone(zone).toLocalDate()
        if (day == now.atZone(zone).toLocalDate()) return Formatted.shortTime(date, locale, zone)
        if (Duration.between(date, now).seconds < 6 * 86400) return skeleton("EEEjmm", locale).format(date.atZone(zone))
        return skeleton("dMMMjmm", locale).format(date.atZone(zone))
    }

    /** "Today", "Yesterday", "Monday", "3 Oct" (another year: "3 Oct 2025"), as `DayDivider.title`. */
    fun day(date: LocalDate, wide: Boolean, withYear: Boolean, locale: Locale = Locale.getDefault()): String =
        skeleton(if (wide) "EEEE" else if (withYear) "yMMMd" else "MMMMd", locale).format(date)

    /** `.dateTime.day().month(.abbreviated).hour().minute()`: "8 Oct, 14:05". */
    fun dayAndTime(date: Instant, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String =
        skeleton("dMMMjmm", locale).format(date.atZone(zone))

    private val cache = HashMap<Pair<String, Locale>, DateTimeFormatter>()

    internal fun skeleton(skeleton: String, locale: Locale): DateTimeFormatter = synchronized(cache) {
        cache.getOrPut(skeleton to locale) { DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, skeleton), locale) }
    }
}

/** What a reply refers to, at the top of its bubble: who, and the first words. [onInk]: in your bubble rather than on the page. */
@Composable
fun QuoteLine(quote: ChatQuote, modifier: Modifier = Modifier, onInk: Boolean = false) {
    val color = if (onInk) DS.Palette.onBubbleUser.copy(alpha = 0.7f) else DS.Palette.inkSecondary
    val who = if (quote.quotesOmi) "Omi" else L("you")
    Row(modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Box(Modifier.width(2.dp).fillMaxHeight().background(color.copy(alpha = color.alpha * 0.6f), CircleShape))
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(who) }
                append("  " + quote.snippet)
            },
            style = DS.Typography.caption,
            color = color,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** Omi is thinking: three dots in a bubble until the first words arrive. */
@Composable
fun TypingBubble(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "typing")
    val phase by transition.animateFloat(0f, 1f, infiniteRepeatable(tween(1100, easing = LinearEasing), RepeatMode.Restart), label = "phase")
    val label = L("nativeChatOmiIsTyping")
    HStack(
        modifier
            .clearAndSetSemantics { contentDescription = label }
            .background(DS.Palette.bubbleAssistant, ChatBubbleShape(isUser = false, position = ChatGrouping.Position.alone))
            .padding(horizontal = 14.dp, vertical = 13.dp),
        spacing = 5.dp,
    ) {
        val dot = DS.Palette.inkTertiary
        repeat(3) { index ->
            val wave = ((kotlin.math.sin((phase - index * 0.33) * 2 * Math.PI) + 1) / 2).toFloat()
            Box(
                Modifier
                    .size(7.dp)
                    .graphicsLayer {
                        val scale = 0.7f + wave * 0.5f
                        scaleX = scale
                        scaleY = scale
                        alpha = 0.35f + wave * 0.65f
                    }
                    .background(dot, CircleShape),
            )
        }
    }
}

/** "Today", "Yesterday", "Monday", "3 Oct": a quiet line where a new day starts in the thread. */
@Composable
fun DayDivider(date: Instant, modifier: Modifier = Modifier) {
    val title = when (val day = ChatDay.of(date)) {
        ChatDay.Today -> L("today")
        ChatDay.Yesterday -> L("yesterday")
        is ChatDay.Weekday -> MessageTime.day(day.date, wide = true, withYear = false)
        is ChatDay.Date -> MessageTime.day(day.date, wide = false, withYear = day.showsYear)
    }
    Box(modifier.fillMaxWidth().padding(top = DS.Spacing.sm).semantics { heading() }, contentAlignment = Alignment.Center) {
        Text(title, style = DS.Typography.micro, color = DS.Palette.inkTertiary)
    }
}

/**
 * The agent's tool steps: done ones checked, the current one spinning. Each distinct step once,
 * in the order it first happened, with how often Omi did it: an agent searching six times reads
 * as one line, not six.
 */
@Composable
fun StepList(steps: List<String>, isWorking: Boolean, modifier: Modifier = Modifier) {
    val grouped = remember(steps) {
        val result = LinkedHashMap<String, Int>()
        steps.filter { it.isNotEmpty() }.forEach { result[it] = (result[it] ?: 0) + 1 }
        result.toList()
    }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        grouped.forEachIndexed { index, (title, count) ->
            HStack(spacing = DS.Spacing.sm) {
                if (isWorking && index == grouped.size - 1) {
                    OmiProgress(Modifier.size(12.dp), tint = DS.Palette.inkSecondary)
                } else {
                    SFImage("checkmark.circle.fill", size = 13.sp, tint = DS.Palette.agent)
                }
                Text(title, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                if (count > 1) Text("×$count", style = DS.Typography.caption.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkTertiary)
            }
        }
    }
}

/** An answer's long-press menu around [content], with the "Not helpful" reasons as a second menu. */
@Composable
private fun AnswerMenuBox(
    message: ChatMessage,
    onReply: () -> Unit,
    onDelete: () -> Unit,
    title: String,
    onTap: () -> Unit,
    content: @Composable () -> Unit,
) {
    var reasonsOpen by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val actions = answerMenu(message, onReply, onDelete, title, scope, onNotHelpful = { reasonsOpen = true })
    Box {
        ContextMenuBox(sections = actions.sections, onTap = onTap, content = content)
        if (reasonsOpen) MenuPopup(actions.reasons) { reasonsOpen = false }
    }
}

/** While this answer is read aloud, stopping is one tap away. */
@Composable
private fun StopReading(voice: com.friend.ios.service.stores.VoicePlaybackStore, message: ChatMessage) {
    val haptics = rememberHaptics()
    HStack(
        Modifier
            .heightIn(min = 30.dp)
            .plainButton {
                haptics.selection()
                voice.toggle(message)
            }
            .background(DS.Palette.fill, CircleShape)
            .padding(horizontal = DS.Spacing.md),
        spacing = DS.Spacing.xs,
    ) {
        if (voice.isLoading) {
            com.friend.ios.design.OmiProgress(Modifier.size(12.dp), tint = DS.Palette.ink)
        } else {
            SFImage("stop.fill", size = 10.sp, tint = DS.Palette.ink)
        }
        Text(L("nativeStopReading"), style = DS.Typography.caption.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium), color = DS.Palette.ink)
    }
}
