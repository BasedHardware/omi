package com.friend.ios.features.tasks

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.text.format.DateFormat
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.features.components.displayTitle
import com.friend.ios.features.components.relativeDay
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.canTakeOver
import com.friend.ios.service.stores.deleteWithUndo
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.time.temporal.ChronoUnit

/**
 * Port of `TaskDetailSheet` (`NewTaskSheet.swift`): one task from Home (a Needs you card, a task
 * link): the same detail as tapping it in the list, with where it came from (the conversation opens
 * from there). Medium, drags to large.
 */
@Composable
fun TaskDetailSheet(
    task: ActionItem,
    onDismiss: () -> Unit,
    onOpenConversation: (String) -> Unit,
    onHandOver: ((ActionItem) -> Unit)? = null,
) {
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        TaskFormSheet(task, onDismiss = onDismiss, onOpenConversation = onOpenConversation, onHandOver = onHandOver)
    }
}

/**
 * Port of `TaskFormSheet.swift`: write a task down by hand, or one task's own screen: what and by
 * when (editable), where it came from (the conversation opens, with the words it was based on),
 * and every answer: Omi takes over (where Omi can), done, later, not a task, share, delete (with
 * Undo). `task == null` creates.
 */
@Composable
fun TaskFormSheet(
    task: ActionItem?,
    onDismiss: () -> Unit,
    onOpenConversation: (String) -> Unit = {},
    /** "Omi takes over": the hand-over sheet, once this one is gone. */
    onHandOver: ((ActionItem) -> Unit)? = null,
    /** Opens the share sheet with a link to these tasks. */
    onShare: ((List<String>) -> Unit)? = null,
) {
    val store = LocalTasksStore.current
    val conversations = LocalConversationsStore.current
    val agent = LocalAgentStore.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    val zone = ZoneId.systemDefault()
    var text by remember { mutableStateOf(task?.description ?: "") }
    var hasDue by remember { mutableStateOf(task?.dueAt != null) }
    var due by remember { mutableStateOf(task?.dueAt ?: Instant.now().plus(1, ChronoUnit.DAYS)) }
    var isSaving by remember { mutableStateOf(false) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { if (task == null) focus.requestFocus() }

    /** The task as the store has it now (ticked off from here, the sheet stays open). */
    val current = task?.let { t -> store.tasks.firstOrNull { it.id == t.id } ?: t }
    val dueAt = if (hasDue) due else null
    val hasChanges = task == null || text.trim() != task.description || dueAt != task.dueAt
    val canSave = text.isNotBlank() && !isSaving && hasChanges

    fun save() {
        isSaving = true
        scope.launch {
            val saved = if (task != null) store.update(task.id, text, dueAt) else store.add(text, dueAt)
            if (saved) {
                haptics.success()
                onDismiss()
            }
            isSaving = false
        }
    }

    Column {
        Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
            Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onDismiss))
            Text(if (task == null) L("newTask") else L("nativeTaskTitle"), style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
            Text(
                L("save"), style = TextStyles.headline, color = if (canSave) DS.Palette.ink else DS.Palette.inkDisabled,
                modifier = Modifier.align(Alignment.CenterEnd).plainButton(enabled = canSave, onClick = ::save),
            )
        }
        val placeholder = L("nativeTaskPlaceholder")
        val addDue = L("addDueDate")
        val dueLabel = L("dueDate")
        val statusLine = current?.let { status(it) }
        val source = current?.let { conversations.source(it) }
        val quote = current?.let { conversations.quote(it) }
        if (current != null && source == null) LaunchedEffect(current.id) { conversations.loadSources(listOf(current)) }
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section(header = statusLine?.ifEmpty { null }) {
                row {
                    Box(Modifier.fillMaxWidth()) {
                        if (text.isEmpty()) Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary)
                        BasicTextField(
                            text, { text = it }, maxLines = 4,
                            textStyle = DS.Typography.body.copy(color = DS.Palette.ink), cursorBrush = SolidColor(DS.Palette.agent),
                            modifier = Modifier.fillMaxWidth().focusRequester(focus),
                        )
                    }
                }
                row { OmiToggleRow(hasDue, { hasDue = it }) { Text(addDue, style = DS.Typography.body, color = DS.Palette.ink) } }
                if (hasDue) row { DueDateRow(dueLabel, due, zone) { due = it } }
                store.lastError?.let { error -> row { Text(error, style = DS.Typography.caption, color = DS.Palette.live) } }
            }
            if (current != null && source != null) {
                section(header = L("nativeTaskFrom")) {
                    row(onClick = {
                        onDismiss()
                        onOpenConversation(source.id)
                    }) { SourceRow(source) }
                    if (quote != null) {
                        row { Text("“$quote”", style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
                    }
                }
            }
            if (current != null) {
                val takeOver = L("nativeOmiTakesOver")
                val done = if (current.isCompleted) L("nativeMarkNotDone") else L("nativeMarkDone")
                val later = L("nativeForYouLater")
                val notTask = L("nativeNotATask")
                // Every answer to the task, the one Omi can take first.
                section(footer = if (!current.isCompleted) L("nativeTaskAnswersFooter") else null) {
                    if (onHandOver != null && !current.isCompleted && agent.canTakeOver(current)) {
                        row(onClick = {
                            onDismiss()
                            // After this sheet is gone: two sheets cannot overlap.
                            agent.background {
                                delay(450)
                                onHandOver(current)
                            }
                        }) { AnswerLabel(takeOver, "sparkles") }
                    }
                    row(onClick = {
                        haptics.selection()
                        scope.launch { store.setCompleted(current.id, !current.isCompleted) }
                    }) { AnswerLabel(done, if (current.isCompleted) "arrow.uturn.backward.circle" else "checkmark.circle") }
                    if (!current.isCompleted) {
                        row(onClick = {
                            haptics.selection()
                            store.snooze(listOf(current.id))
                            onDismiss()
                        }) { AnswerLabel(later, "clock") }
                        row(onClick = {
                            onDismiss()
                            agent.background { store.markNotTask(listOf(current.id)) }
                        }) { AnswerLabel(notTask, "xmark.circle", DS.Palette.live) }
                    }
                }
                val delete = L("deleteActionItem")
                val share = L("nativeShareLink")
                section {
                    if (onShare != null) {
                        row(onClick = {
                            onDismiss()
                            onShare(listOf(current.id))
                        }) { Text(share, style = DS.Typography.body, color = DS.Palette.agent) }
                    }
                    row(onClick = {
                        onDismiss()
                        store.deleteWithUndo(listOf(current.id))
                    }) { Text(delete, style = DS.Typography.body, color = DS.Palette.live) }
                }
            }
        }
    }
}

/** "Done", "Overdue · Due Wed, 7 Oct", "Due today", or "On Home again tomorrow". */
@Composable
private fun status(task: ActionItem): String {
    val store = LocalTasksStore.current
    val zone = ZoneId.systemDefault()
    val parts = mutableListOf<String>()
    val dueAt = task.dueAt
    if (task.isCompleted) {
        parts += L("nativeForYouMarkDone")
    } else if (dueAt != null) {
        if (dueAt < LocalDate.now(zone).atStartOfDay(zone).toInstant()) parts += L("nativeOverdue")
        parts += L("taskDueDate", Formatting.relativeDay(dueAt))
    }
    if (!task.isCompleted && store.snoozes[task.id]?.let { it > Instant.now() } == true) parts += L("nativeTaskOnHomeTomorrow")
    return parts.joinToString(" · ")
}

/** A `Label` row in the form: the glyph, then the title, tinted ink (destructive in red). */
@Composable
private fun AnswerLabel(title: String, symbol: String, tint: Color = DS.Palette.ink) {
    HStack(spacing = DS.Spacing.md) {
        SFImage(symbol, tint = tint)
        Text(title, style = DS.Typography.body, color = tint)
    }
}

/** The conversation it came from: its emoji, title and when. */
@Composable
private fun SourceRow(conversation: Conversation) {
    val context = LocalContext.current
    HStack(spacing = DS.Spacing.md) {
        Text(conversation.emoji ?: "💬", style = TextStyles.system(22))
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(conversation.displayTitle(context), style = DS.Typography.cardTitle, color = DS.Palette.ink)
            val date = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT).format(conversation.createdAt.atZone(ZoneId.systemDefault()))
            Text(date, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
    }
}

/**
 * The compact `DatePicker`: the label, then the date and the time as gray capsules; each opens
 * the system picker. An overdue task keeps its date selectable (no lower bound before today).
 */
@Composable
private fun DueDateRow(label: String, value: Instant, zone: ZoneId, onChange: (Instant) -> Unit) {
    val context = LocalContext.current
    val local = value.atZone(zone)
    HStack(Modifier.fillMaxWidth()) {
        Text(label, style = DS.Typography.body, color = DS.Palette.ink)
        Spacer(Modifier.weight(1f))
        Capsule(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).format(local)) {
            DatePickerDialog(context, { _, year, month, day ->
                onChange(LocalDate.of(year, month + 1, day).atTime(local.toLocalTime()).atZone(zone).toInstant())
            }, local.year, local.monthValue - 1, local.dayOfMonth).show()
        }
        Capsule(DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).format(local)) {
            TimePickerDialog(context, { _, hour, minute ->
                onChange(local.toLocalDate().atTime(LocalTime.of(hour, minute)).atZone(zone).toInstant())
            }, local.hour, local.minute, DateFormat.is24HourFormat(context)).show()
        }
    }
}

@Composable
private fun Capsule(text: String, onClick: () -> Unit) {
    Text(
        text, style = DS.Typography.body, color = DS.Palette.ink,
        modifier = Modifier.plainButton(onClick = onClick).background(DS.Palette.fill, CircleShape).padding(horizontal = 11.dp, vertical = 6.dp),
    )
}
