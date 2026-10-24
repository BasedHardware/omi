package com.friend.ios.features.conversations

import android.text.format.DateFormat
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationDigest
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.MarkdownBlocks
import com.friend.ios.features.components.TaskRow
import com.friend.ios.features.components.inline
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.SummaryEditFailure
import com.friend.ios.service.stores.SummaryEditOutcome
import com.friend.ios.service.stores.canEditSummary
import com.friend.ios.service.stores.editSummary
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Port of `ConversationSummaryView.swift`: the summary at the top of the page: its first two or
 * three sentences, "More" for the rest. A failed summary offers a retry. The summary can be edited
 * in place (the backend's `PATCH v1/conversations/{id}/summary`): the new text shows at once, the
 * old one comes back when the backend refuses, and the editor stays open with the draft and what
 * went wrong.
 */
@Composable
fun ConversationSummaryView(
    store: ConversationDetailStore,
    conversation: Conversation,
    onRetry: () -> Unit,
    /** The edited summary was stored; the screen shows its "Summary saved" toast. */
    onSaved: () -> Unit = {},
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    var editing by rememberSaveable { mutableStateOf(false) }
    var draft by rememberSaveable { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    /** Why the last save did not go through; the editor stays open and says so. */
    var failed by remember { mutableStateOf<SummaryEditFailure?>(null) }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()

    // Editing waits until Omi is done with this conversation: during processing or a reprocess the
    // summary on screen is about to be replaced.
    val canEdit = !store.isReprocessing && conversation.status != Conversation.Status.Processing && !conversation.summaryFailed &&
        store.canEditSummary

    fun startEditing(summary: String) {
        haptics.tap(DSHaptics.Style.Medium)
        draft = summary
        failed = null
        editing = true
    }

    fun stopEditing() {
        editing = false
        draft = ""
        failed = null
    }

    suspend fun save() {
        val text = draft.trim()
        if (text.isEmpty() || saving) return
        saving = true
        val outcome = store.editSummary(text)
        saving = false
        when (outcome) {
            SummaryEditOutcome.Saved -> {
                haptics.success()
                stopEditing()
                onSaved()
            }
            // Nothing to send (the text is what the summary already shows).
            SummaryEditOutcome.Unchanged -> stopEditing()
            // The draft stays; the summary behind it is back to the old text.
            is SummaryEditOutcome.Failed -> failed = outcome.failure
        }
    }

    Column(Modifier.fillMaxWidth().animateContentSize(DS.Motion.standard()), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        // Processing shows in the strip under the title (ProcessingStrip).
        if (!store.isReprocessing && conversation.status != Conversation.Status.Processing && conversation.summaryFailed) {
            Failed(onRetry)
        }
        val summary = store.detail?.summary ?: conversation.overview
        when {
            editing -> SummaryEditor(draft, { draft = it }, saving, failed, onCancel = { stopEditing() }, onSave = { scope.launch { save() } })
            summary.isBlank() -> Text(L("nativeNoSummary"), style = DS.Typography.body, color = DS.Palette.inkSecondary)
            else -> SummaryText(store, summary, expanded, canEdit, onToggle = { expanded = !expanded }, onEdit = { startEditing(summary) })
        }
    }
}

@Composable
private fun SummaryText(
    store: ConversationDetailStore,
    summary: String,
    expanded: Boolean,
    canEdit: Boolean,
    onToggle: () -> Unit,
    onEdit: () -> Unit,
) {
    // The backend's own gist when it kept one, else the summary's first sentences.
    val lead = store.detail?.gist?.let { ConversationDigest.Lead(it, it != summary) } ?: ConversationDigest.lead(summary)
    SelectionContainer {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            if (expanded || !lead.isShortened) {
                MarkdownBlocks(summary, style = DS.Typography.body.copy(lineHeight = DS.Typography.body.lineHeight * 1.14f), color = DS.Palette.ink)
            } else {
                Text(lead.text, style = DS.Typography.body.copy(lineHeight = DS.Typography.body.lineHeight * 1.14f), color = DS.Palette.ink)
            }
            if (lead.isShortened) {
                Text(
                    if (expanded) L("nativeLess") else L("nativeMore"),
                    style = DS.Typography.callout.medium(),
                    color = DS.Palette.inkSecondary,
                    modifier = Modifier.plainButton(onClick = onToggle),
                )
            }
            if (canEdit) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) { EditSummaryButton(onEdit) }
            }
        }
    }
}

/** `Label(L("nativeEditSummary"), systemImage: "square.and.pencil")` in an `.omiPillSubtle`. */
@Composable
private fun EditSummaryButton(onClick: () -> Unit) {
    HStack(
        Modifier
            .pressable(pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onClick)
            .background(DS.Palette.cardRaised, CircleShape)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
        spacing = 6.dp,
    ) {
        SFImage("square.and.pencil", size = 14.sp, tint = DS.Palette.ink)
        Text(L("nativeEditSummary"), style = TextStyles.subheadline.semibold(), color = DS.Palette.ink)
    }
}

/**
 * The summary in place: a text editor, what went wrong last time, the count, and save/cancel. The
 * keyboard comes up on the text, the way tapping into any editor does.
 */
@Composable
private fun SummaryEditor(
    draft: String,
    onDraftChange: (String) -> Unit,
    saving: Boolean,
    failed: SummaryEditFailure?,
    onCancel: () -> Unit,
    onSave: () -> Unit,
) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    LaunchedEffect(Unit) {
        focus.requestFocus()
        keyboard?.show()
    }
    val canSave = draft.trim().isNotEmpty()
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Box(
            Modifier
                .fillMaxWidth()
                .heightIn(min = 150.dp)
                .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.md))
                .padding(DS.Spacing.sm),
        ) {
            BasicTextField(
                value = draft,
                onValueChange = { text -> onDraftChange(text.take(LIMIT)) },
                enabled = !saving,
                textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                cursorBrush = SolidColor(DS.Palette.agent),
                modifier = Modifier.fillMaxWidth().focusRequester(focus),
            )
        }
        failed?.let {
            HStack(spacing = DS.Spacing.sm) {
                SFImage("exclamationmark.triangle", size = 14.sp, tint = DS.Palette.live)
                Text(summaryEditMessage(it), style = DS.Typography.caption, color = DS.Palette.live, modifier = Modifier.weight(1f))
            }
        }
        HStack(spacing = DS.Spacing.sm) {
            Text("${draft.length}/$LIMIT", style = DS.Typography.caption, color = DS.Palette.inkTertiary)
            Spacer(Modifier.weight(1f))
            if (saving) {
                OmiProgress(Modifier.size(20.dp))
            } else {
                OmiPillButton(L("cancel"), prominent = false, onClick = onCancel)
                SavePill(canSave, onSave)
            }
        }
    }
}

/** `Button(L("save")).buttonStyle(.omiPill).disabled(...)`: an empty draft cannot be saved. */
@Composable
private fun SavePill(enabled: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .pressable(enabled = enabled, pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onClick)
            .background(DS.Palette.accent, CircleShape)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
        contentAlignment = Alignment.Center,
    ) {
        Text(L("save"), style = TextStyles.subheadline.semibold(), color = DS.Palette.onAccent)
    }
}

/** The backend's own ceiling on the summary (`PATCH` refuses more). */
private const val LIMIT = 10_000

/** What went wrong, in words. (`ConversationSummaryView.message`, and `L` is composable here.) */
@Composable
internal fun summaryEditMessage(failure: SummaryEditFailure): String = when (failure) {
    SummaryEditFailure.AppResultGone -> L("nativeSummarySaveAppResultGone")
    SummaryEditFailure.AppResultAmbiguous -> L("nativeSummarySaveAppResultAmbiguous")
    SummaryEditFailure.ConversationGone -> L("nativeSummarySaveConversationGone")
    SummaryEditFailure.Offline -> L("nativeSummarySaveOffline")
    SummaryEditFailure.SignedOut -> L("nativeSummarySaveSignedOut")
    is SummaryEditFailure.Refused -> failure.status?.let { L("nativeSummarySaveRefusedStatus", "$it") } ?: L("nativeSummarySaveRefused")
}

@Composable
private fun Failed(onRetry: () -> Unit) {
    HStack(Modifier.omiCard(padding = DS.Spacing.md), spacing = DS.Spacing.md) {
        SFImage("exclamationmark.triangle", tint = DS.Palette.warning)
        Text(L("nativeSummaryFailed"), style = DS.Typography.callout.medium(), color = DS.Palette.ink, modifier = Modifier.weight(1f))
        OmiPillButton(L("retry"), prominent = false, onClick = onRetry)
    }
}

/**
 * The page's three ways to use a conversation: ask about it, check it in the transcript, send it
 * to your own AI. One row; stacked when large text does not fit (`ViewThatFits`, here a wrapping row).
 */
@Composable
fun DetailActions(onAsk: () -> Unit, onCheck: () -> Unit, onSend: () -> Unit) {
    FlowRow(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        Action(L("nativeAsk"), "bubble.left", onAsk)
        Action(L("nativeCheck"), "text.magnifyingglass", onCheck)
        Action(L("nativeSendToMyAI"), "square.and.arrow.up", onSend)
    }
}

@Composable
private fun Action(title: String, symbol: String, perform: () -> Unit) {
    val haptics = rememberHaptics()
    HStack(
        Modifier
            .pressable(pressedScale = 0.97f, pressedAlpha = 0.85f, haptic = false) {
                haptics.tap()
                perform()
            }
            .heightIn(min = 38.dp)
            .border(1.dp, DS.Palette.fill, CircleShape)
            .padding(horizontal = 14.dp),
        spacing = 6.dp,
    ) {
        SFImage(symbol, size = 14.sp, tint = DS.Palette.ink)
        Text(title, style = TextStyles.subheadline.medium(), color = DS.Palette.ink, maxLines = 1)
    }
}

/**
 * Everything beyond the summary and action items, behind one "More details": what was decided and
 * found (key points, events, other apps' summaries), who took part, the linked event, photos, what
 * was on screen, and "Was this helpful?".
 */
@Composable
fun MoreDetailsSection(store: ConversationDetailStore, extras: DetailExtras, conversation: Conversation, modifier: Modifier = Modifier) {
    val detail = store.detail ?: return
    var expanded by rememberSaveable { mutableStateOf(DebugLaunch.flag("omiMoreDetails")) }
    val haptics = rememberHaptics()
    val tasks = LocalTasksStore.current
    val scope = rememberCoroutineScope()
    val rotation by animateFloatAsState(if (expanded) 180f else 0f, DS.Motion.standard(), label = "chevron")
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl)) {
        HStack(
            Modifier.plainButton {
                haptics.selection()
                expanded = !expanded
            },
            spacing = DS.Spacing.xs,
        ) {
            Text(L("nativeMoreDetails"), style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary)
            SFImage("chevron.down", Modifier.rotate(rotation), size = 12.sp, tint = DS.Palette.inkSecondary)
        }
        AnimatedVisibility(expanded, enter = fadeIn(DS.Motion.standard()), exit = fadeOut(DS.Motion.standard())) {
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl)) {
                ConversationInsightsView(detail, onEvent = { extras.addingEvent = it })
                SummaryExtrasSection(store, extras)
                ParticipantsRow(store) { extras.showsEvent = true }
                val others = tasks.othersTasks(conversation.id)
                if (others.isNotEmpty()) {
                    DetailGroup(L("nativeWaitingOnOthers")) {
                        others.forEach { task ->
                            TaskRow(task, onToggle = { scope.launch { tasks.setCompleted(task.id, !task.isCompleted) } })
                        }
                    }
                }
                ConversationPhotosGrid(store)
            }
        }
    }
    // Loads what the extras need (feedback, screenshots) whether or not they show yet.
    SummaryExtrasLoader(store, extras)
}

/** A labeled group inside "More details": small gray label, rows on the page. */
@Composable
fun DetailGroup(title: String, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Text(title, style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary, modifier = Modifier.semantics { heading() })
        content()
    }
}

/** Key points, events Omi found, and what the user's other apps wrote. */
@Composable
fun ConversationInsightsView(detail: ConversationDetail, onEvent: (Int) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl)) {
        if (detail.keyPoints.isNotEmpty()) {
            DetailGroup(L("nativeKeyPoints")) {
                detail.keyPoints.forEach { point ->
                    Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                        Text("•", style = DS.Typography.body, color = DS.Palette.inkSecondary)
                        Text(inline(point, DS.Palette.agent), style = DS.Typography.body, color = DS.Palette.ink)
                    }
                }
            }
        }
        val shown = detail.events.indices.filter { detail.events[it].title.isNotEmpty() }
        if (shown.isNotEmpty()) {
            DetailGroup(L("nativeEvents")) {
                shown.forEach { index ->
                    val event = detail.events[index]
                    Box(Modifier.plainButton(enabled = !event.isCreated) { onEvent(index) }) { EventRow(event) }
                }
            }
        }
        detail.otherSummaries.forEach { other ->
            DetailGroup(L("nativeFromYourApps")) { MarkdownBlocks(other.content, color = DS.Palette.ink) }
        }
    }
}

/** One found event; tapping it adds it to the calendar (a check once it is there). */
@Composable
private fun EventRow(event: ConversationDetail.Event) {
    Row(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Box(Modifier.width(22.dp).padding(top = 2.dp), contentAlignment = Alignment.Center) { SFImage("calendar", tint = DS.Palette.inkSecondary) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(event.title, style = DS.Typography.cardTitle, color = DS.Palette.ink)
            event.start?.let { Text(DetailDates.weekdayDateTime(it), style = DS.Typography.caption, color = DS.Palette.inkSecondary) }
            if (event.description.isNotEmpty()) Text(event.description, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
        SFImage(
            if (event.isCreated) "checkmark" else "plus",
            Modifier.padding(top = 2.dp),
            size = 15.sp,
            tint = if (event.isCreated) DS.Palette.success else DS.Palette.inkSecondary,
            contentDescription = if (event.isCreated) L("nativeAddedToCalendar") else L("nativeAddToCalendar"),
        )
    }
}

/** The detail page's date styles (`Date.formatted(...)`). */
object DetailDates {
    /** `.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute()`: "Wed, Oct 7, 3:18 PM". */
    fun weekdayDateTime(instant: Instant, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
        DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, "EEEMMMdjmm"), locale).format(instant.atZone(zone))

    /** `.dateTime.month(.abbreviated).day()`: "Oct 7". */
    fun monthDay(instant: Instant, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
        DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, "MMMd"), locale).format(instant.atZone(zone))
}
