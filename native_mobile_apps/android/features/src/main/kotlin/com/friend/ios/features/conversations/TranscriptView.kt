package com.friend.ios.features.conversations

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationDigest
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.design.DSHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.TranscriptSpeakersStore
import kotlinx.coroutines.launch

/** Where each paragraph sits on screen (root y), so the page can scroll a search match into view (`ScrollViewReader`). */
@Stable
class TranscriptAnchors {
    internal val positions = mutableStateMapOf<Int, Float>()
}

/**
 * Port of `TranscriptView.swift`: the transcript page, typeset like a document: the recording (if
 * kept), then one paragraph per turn (a speaker's consecutive lines merged), each under a small
 * "Anna · 4:05" label. Search opens from the magnifier above the page or the "..." menu.
 * Long-press a paragraph to correct its words; tap the name to say who it was.
 */
@Composable
fun TranscriptView(
    store: ConversationDetailStore,
    query: String,
    onQueryChange: (String) -> Unit,
    /** Index into `matches` of the line being shown. */
    cursor: Int,
    onCursorChange: (Int) -> Unit,
    /** The search field is open. */
    showsSearch: Boolean,
    onShowsSearchChange: (Boolean) -> Unit,
    onShareAudio: () -> Unit,
    anchors: TranscriptAnchors,
) {
    val settings = LocalSettingsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var editing by remember { mutableStateOf<ConversationDetail.Line?>(null) }
    /** A paragraph of several lines being corrected: pick which line first. */
    var choosingLine by remember { mutableStateOf<ConversationDigest.Paragraph?>(null) }
    /** Chapters opened past their first turns ("Show all"). */
    var expanded by rememberSaveable { mutableStateOf(setOf<Int>()) }
    // Speaker naming (SpeakerTranscript.kt).
    val speakers = remember(store) { TranscriptSpeakersStore(store) }
    var naming by remember { mutableStateOf<ConversationDetail.Line?>(null) }
    var reviewsMatches by remember { mutableStateOf(false) }
    val matches = store.detail?.lines(query).orEmpty()

    LaunchedEffect(Unit) { if (settings.people.isEmpty()) settings.loadPeople() }
    LaunchedEffect(query) { onCursorChange(0) }

    /** One line opens its editor at once; a merged paragraph asks which line first. */
    fun correct(paragraph: ConversationDigest.Paragraph) {
        val editable = paragraph.lines.filter { it.segmentID != null }
        if (editable.isEmpty()) return
        haptics.tap(DSHaptics.Style.Medium)
        if (editable.size == 1) editing = editable[0] else choosingLine = paragraph
    }

    Column(Modifier.fillMaxWidth().animateContentSize(DS.Motion.standard()), verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
        if (store.detail?.hasAudio == true) AudioPlayerBar(store, onShareAudio)
        val lines = store.detail?.transcript.orEmpty()
        if (lines.isNotEmpty()) {
            if (showsSearch || query.isNotEmpty()) {
                SearchField(query, onQueryChange, matches, cursor, onCursorChange, showsSearch) {
                    onQueryChange("")
                    onShowsSearchChange(false)
                }
            }
            SpeakerTools(speakers) { reviewsMatches = true }
            val chapters = ConversationDigest.chapters(lines, store.detail?.chapters.orEmpty())
            val hits = matches.toSet()
            val current = if (matches.isEmpty()) null else matches[minOf(cursor, matches.size - 1)]
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.section)) {
                chapters.forEach { chapter ->
                    // A chapter with a search hit opens by itself.
                    val open = chapter.id in expanded || chapter.paragraphs.any { paragraph -> paragraph.lines.any { it.id in hits } }
                    Chapter(
                        chapter, open, chapter.id in expanded, query, current,
                        speakerName = { settings.speakerNameOrNull(it) },
                        onName = { naming = it },
                        onCorrect = ::correct,
                        anchors = anchors,
                    ) {
                        haptics.selection()
                        expanded = if (chapter.paragraphs.size > (if (open) chapter.paragraphs.size else TranscriptView.closedTurns) && chapter.id !in expanded) {
                            expanded + chapter.id
                        } else {
                            expanded - chapter.id
                        }
                    }
                }
            }
        } else {
            Text(if (store.detail == null) L("loading") else L("noTranscriptMessage"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
        }
    }

    editing?.let { line ->
        EditLineSheet(line, onDismiss = { editing = null }) { text -> scope.launch { store.editLine(line.id, text) } }
    }
    choosingLine?.let { paragraph ->
        OmiConfirmationDialog(
            L("nativeEditText"),
            paragraph.lines.filter { it.segmentID != null }.map { line -> DialogButton(TranscriptView.preview(line.text)) { editing = line } } +
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
            onDismiss = { choosingLine = null },
        )
    }
    naming?.let { line -> NameSpeakerSheet(line, speakers) { naming = null } }
    if (reviewsMatches) VoiceMatchesSheet(speakers) { reviewsMatches = false }
}

/** `TranscriptView`'s static helpers. */
object TranscriptView {
    /** Turns shown while a chapter is closed. */
    const val closedTurns = 3

    /** The paragraph a line belongs to, for scrolling to a search match. */
    fun paragraphID(lineID: Int, lines: List<ConversationDetail.Line>): Int? =
        ConversationDigest.paragraphs(lines).firstOrNull { it.contains(lineID) }?.id

    /** The start of a line, for choosing which one to correct. */
    fun preview(text: String): String = if (text.length > 48) text.take(48) + "…" else text

    /** Every occurrence of [query] gets a highlight (case and diacritics ignored). */
    fun highlighted(text: String, query: String, highlight: Color): AnnotatedString {
        val needle = ConversationDetail.fold(query.trim())
        if (needle.isEmpty()) return AnnotatedString(text)
        // The folded text, and for each folded character the original index it came from.
        val folded = StringBuilder()
        val origin = ArrayList<Int>()
        var index = 0
        while (index < text.length) {
            val next = index + Character.charCount(text.codePointAt(index))
            val piece = ConversationDetail.fold(text.substring(index, next))
            repeat(piece.length) { origin += index }
            folded.append(piece)
            index = next
        }
        return buildAnnotatedString {
            append(text)
            var from = 0
            while (true) {
                val found = folded.indexOf(needle, from)
                if (found < 0) break
                val start = origin[found]
                val endFolded = found + needle.length
                val end = if (endFolded < origin.size) origin[endFolded] else text.length
                if (end > start) addStyle(SpanStyle(background = highlight), start, end)
                from = endFolded
            }
        }
    }
}

@Composable
private fun SearchField(
    query: String,
    onQueryChange: (String) -> Unit,
    matches: List<Int>,
    cursor: Int,
    onCursorChange: (Int) -> Unit,
    showsSearch: Boolean,
    onClose: () -> Unit,
) {
    val haptics = rememberHaptics()
    val focus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    LaunchedEffect(showsSearch) { if (showsSearch) runCatching { focus.requestFocus() } }
    fun step(delta: Int) {
        if (matches.isEmpty()) return
        haptics.selection()
        onCursorChange((cursor + delta + matches.size) % matches.size)
    }
    HStack(
        Modifier.fillMaxWidth().heightIn(min = 40.dp).omiSurface(CircleShape).padding(horizontal = DS.Spacing.md),
        spacing = DS.Spacing.sm,
    ) {
        SFImage("magnifyingglass", size = 15.sp, tint = DS.Palette.inkTertiary)
        Box(Modifier.weight(1f)) {
            if (query.isEmpty()) Text(L("searchTranscriptOrSummary"), style = DS.Typography.callout, color = DS.Palette.inkTertiary, maxLines = 1)
            BasicTextField(
                value = query,
                onValueChange = onQueryChange,
                singleLine = true,
                textStyle = DS.Typography.callout.copy(color = DS.Palette.ink),
                cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { step(1) }),
                modifier = Modifier.fillMaxWidth().focusRequester(focus),
            )
        }
        if (query.isNotEmpty()) {
            Text(
                if (matches.isEmpty()) L("noResultsFound") else L("nativeMatchPosition", "${cursor + 1}", "${matches.size}"),
                style = DS.Typography.micro.copy(fontFeatureSettings = "tnum"),
                color = DS.Palette.inkSecondary,
                maxLines = 1,
            )
            SFImage("chevron.up", Modifier.plainButton(enabled = matches.size >= 2) { step(-1) }, size = 15.sp,
                tint = if (matches.size >= 2) DS.Palette.agent else DS.Palette.inkDisabled, contentDescription = L("nativePreviousMatch"))
            SFImage("chevron.down", Modifier.plainButton(enabled = matches.size >= 2) { step(1) }, size = 15.sp,
                tint = if (matches.size >= 2) DS.Palette.agent else DS.Palette.inkDisabled, contentDescription = L("nativeNextMatch"))
        }
        SFImage(
            "xmark.circle.fill",
            Modifier.plainButton {
                focusManager.clearFocus()
                onClose()
            },
            size = 15.sp,
            tint = DS.Palette.inkTertiary,
            contentDescription = L("cancel"),
        )
    }
}

/**
 * A chapter: its heading (the notes' section) or its start time, the first turns, and "Show all (n)"
 * for the rest.
 */
@Composable
private fun Chapter(
    chapter: ConversationDigest.Chapter,
    isOpen: Boolean,
    isExpanded: Boolean,
    query: String,
    current: Int?,
    speakerName: @Composable (ConversationDetail.Line) -> String,
    onName: (ConversationDetail.Line) -> Unit,
    onCorrect: (ConversationDigest.Paragraph) -> Unit,
    anchors: TranscriptAnchors,
    onToggle: () -> Unit,
) {
    val shown = if (isOpen) chapter.paragraphs else chapter.paragraphs.take(TranscriptView.closedTurns)
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
        HStack(spacing = DS.Spacing.sm, alignment = Alignment.Bottom) {
            chapter.title?.let { Text(it, style = DS.Typography.callout.semibold(), color = DS.Palette.ink) }
            Text(
                ConversationDigest.timestamp(chapter.start),
                style = (if (chapter.title == null) DS.Typography.callout.semibold() else DS.Typography.caption).copy(fontFeatureSettings = "tnum"),
                color = if (chapter.title == null) DS.Palette.ink else DS.Palette.inkTertiary,
            )
        }
        shown.forEach { paragraph ->
            Paragraph(paragraph, query, current?.let(paragraph::contains) ?: false, speakerName, onName, onCorrect, anchors)
        }
        val hidden = chapter.paragraphs.size - shown.size
        if (hidden > 0 || (isOpen && isExpanded && chapter.paragraphs.size > TranscriptView.closedTurns)) {
            HStack(Modifier.plainButton(onClick = onToggle), spacing = DS.Spacing.xs) {
                Text(
                    if (hidden > 0) L("nativeShowAllTurns", "${chapter.paragraphs.size}") else L("nativeLess"),
                    style = DS.Typography.caption.medium(),
                    color = DS.Palette.inkSecondary,
                )
                SFImage(if (hidden > 0) "chevron.down" else "chevron.up", size = 11.sp, tint = DS.Palette.inkSecondary)
            }
        }
    }
}

/**
 * One turn as a paragraph: "Anna  4:05" small and gray above (just the time when the same speaker
 * goes on), the words in callout size with room between the lines. The paragraph holding the
 * current search match gets a soft amber wash.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun Paragraph(
    paragraph: ConversationDigest.Paragraph,
    query: String,
    isCurrent: Boolean,
    speakerName: @Composable (ConversationDetail.Line) -> String,
    onName: (ConversationDetail.Line) -> Unit,
    onCorrect: (ConversationDigest.Paragraph) -> Unit,
    anchors: TranscriptAnchors,
) {
    val highlight = DS.Palette.warning.copy(alpha = 0.35f)
    val text = buildAnnotatedString {
        paragraph.lines.forEachIndexed { index, line ->
            if (index > 0) append(" ")
            append(TranscriptView.highlighted(line.text, query, highlight))
        }
    }
    Column(
        Modifier
            .fillMaxWidth()
            .onGloballyPositioned { anchors.positions[paragraph.id] = it.positionInRoot().y }
            .bleed(DS.Spacing.sm)
            .background(if (isCurrent) DS.Palette.warning.copy(alpha = 0.12f) else Color.Transparent, ContinuousRoundedShape(DS.Radius.sm))
            .padding(horizontal = DS.Spacing.sm, vertical = if (isCurrent) DS.Spacing.sm else 0.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        HStack(spacing = DS.Spacing.sm, alignment = Alignment.Bottom) {
            if (!paragraph.continuesTurn) SpeakerLabel(speakerName(paragraph.first), paragraph.first, onName)
            Text(
                ConversationDigest.timestamp(paragraph.first.start),
                style = DS.Typography.caption.copy(fontFeatureSettings = "tnum"),
                color = DS.Palette.inkTertiary,
            )
        }
        Text(
            text,
            style = DS.Typography.callout.copy(lineHeight = DS.Typography.callout.lineHeight * 1.2f),
            color = DS.Palette.ink,
            modifier = Modifier.combinedClickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = {},
                onLongClick = { onCorrect(paragraph) },
            ),
        )
    }
}

/** `.padding(.horizontal, -n)`: the content reaches [horizontal] past both sides of its slot. */
private fun Modifier.bleed(horizontal: Dp): Modifier = layout { measurable, constraints ->
    val extra = horizontal.roundToPx() * 2
    val placeable = measurable.measure(constraints.copy(maxWidth = constraints.maxWidth + extra, minWidth = constraints.minWidth + extra))
    layout(placeable.width - extra, placeable.height) { placeable.place(-extra / 2, 0) }
}

/** The speaker name, read in composition (the `@Composable` form of `SettingsStore.speakerName`). */
@Composable
private fun com.friend.ios.service.stores.SettingsStore.speakerNameOrNull(line: ConversationDetail.Line): String = speakerName(line)

/** Port of `EditLineSheet`: correcting what Omi heard in one line. */
@Composable
private fun EditLineSheet(line: ConversationDetail.Line, onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var text by remember { mutableStateOf(line.text) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium)) {
        SheetBar(
            line.speaker,
            leading = { SheetBarButton(L("cancel"), onClick = onDismiss) },
            trailing = {
                SheetBarButton(L("save"), enabled = text.isNotBlank(), prominent = true) {
                    onSave(text)
                    onDismiss()
                }
            },
        )
        Box(
            Modifier
                .padding(DS.Spacing.gutter)
                .fillMaxWidth()
                .heightIn(min = 160.dp)
                .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.md))
                .padding(DS.Spacing.md),
        ) {
            BasicTextField(
                value = text,
                onValueChange = { text = it },
                textStyle = TextStyles.body.copy(color = DS.Palette.ink),
                cursorBrush = SolidColor(DS.Palette.agent),
                modifier = Modifier.fillMaxWidth().focusRequester(focus),
            )
        }
    }
}
