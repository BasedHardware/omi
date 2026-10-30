package com.friend.ios.features.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Port of `TaskRow.swift`: one task: check circle, text, then quiet lines: due date and where it
 * came from (the conversation's emoji and title, tappable), the words it was extracted from,
 * Omi's status; "Omi takes over" at the end. [agentStatus] is set when Omi worked or works on
 * this task; tapping it opens Omi's work ([onHandOver]).
 */
@Composable
fun TaskRow(
    task: ActionItem,
    modifier: Modifier = Modifier,
    source: String? = null,
    sourceEmoji: String? = null,
    quote: String? = null,
    onOpenSource: (() -> Unit)? = null,
    agentStatus: AgentTaskStatus? = null,
    onToggle: () -> Unit,
    onHandOver: (() -> Unit)? = null,
) {
    val haptics = rememberHaptics()
    Row(modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        SFImage(
            if (task.isCompleted) "checkmark.circle.fill" else "circle",
            Modifier.padding(top = 1.dp).plainButton {
                if (!task.isCompleted) haptics.success()
                onToggle()
            },
            size = 20.sp,
            tint = if (task.isCompleted) DS.Palette.success else DS.Palette.inkTertiary,
            contentDescription = if (task.isCompleted) L("nativeMarkOpen") else L("nativeMarkDone"),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(
                task.description,
                style = DS.Typography.body.copy(textDecoration = if (task.isCompleted) TextDecoration.LineThrough else null),
                color = if (task.isCompleted) DS.Palette.inkTertiary else DS.Palette.ink,
            )
            if (task.dueAt != null || source != null) Meta(task, source, sourceEmoji, onOpenSource)
            if (!quote.isNullOrEmpty()) {
                Text("“$quote”", style = DS.Typography.caption, color = DS.Palette.inkTertiary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (agentStatus != null) AgentStatusChip(agentStatus, Modifier.padding(top = DS.Spacing.xxs), action = onHandOver)
        }
        // Hand-over as one small round button at the end, not a labeled chip under every task.
        if (agentStatus == null && onHandOver != null && !task.isCompleted) HandOverButton(onHandOver)
    }
}

/** "Omi takes over" as a thin sparkles glyph at the end of a task row (Omi blue: Omi's work). */
@Composable
internal fun HandOverButton(action: () -> Unit) {
    Box(Modifier.size(36.dp).pressable(onClick = action), contentAlignment = Alignment.Center) {
        SFImage("sparkles", size = 16.sp, tint = DS.Palette.agent, contentDescription = L("nativeOmiTakesOver"))
    }
}

/** Due date (red when overdue) and the source conversation, which stays quiet either way. */
@Composable
private fun Meta(task: ActionItem, source: String?, sourceEmoji: String?, onOpenSource: (() -> Unit)?) {
    val due = task.dueAt
    val zone = ZoneId.systemDefault()
    val isOverdue = due != null && !task.isCompleted && due.atZone(zone).toLocalDate() < LocalDate.now(zone)
    HStack(spacing = DS.Spacing.xs) {
        if (due != null) {
            Text(Formatting.relativeDay(due), style = DS.Typography.caption, color = if (isOverdue) DS.Palette.live else DS.Palette.inkSecondary, maxLines = 1, softWrap = false)
        }
        if (due != null && source != null) Text("·", style = DS.Typography.caption, color = DS.Palette.inkTertiary)
        if (source != null) {
            Text(
                sourceEmoji?.let { "$it $source" } ?: source,
                style = DS.Typography.caption,
                color = DS.Palette.inkSecondary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = if (onOpenSource != null) {
                    val label = L("nativeFromConversation", source)
                    Modifier.plainButton(onClick = onOpenSource).semantics { contentDescription = label }
                } else {
                    Modifier
                },
            )
        }
    }
}

/** "Today", "Tomorrow", "Yesterday", or "Fri, 9 Oct" (`Formatting.relativeDay`). */
@Composable
fun Formatting.relativeDay(date: Instant, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()): String {
    val day = date.atZone(zone).toLocalDate()
    val today = now.atZone(zone).toLocalDate()
    return when (day) {
        today -> L("today")
        today.plusDays(1) -> L("nativeTomorrow")
        today.minusDays(1) -> L("yesterday")
        else -> weekdayMonthDay(day)
    }
}
