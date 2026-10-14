package com.friend.ios.features.conversations

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.CaptureRecording
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.Formatted
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiField
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.separate
import com.friend.ios.service.stores.testPrompt
import kotlinx.coroutines.launch

/**
 * Port of `CaptureRecordingsSheet.swift`: "Recordings of this conversation": the same moment
 * recorded by other devices (Flutter `capture_recordings`). Tap one to open it; "Separate..." makes
 * it its own conversation for good.
 */
@Composable
fun CaptureRecordingsSheet(store: ConversationDetailStore, onOpen: (CaptureRecording) -> Unit, onDismiss: () -> Unit) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    var separating by remember { mutableStateOf<CaptureRecording?>(null) }
    var working by remember { mutableStateOf<String?>(null) }
    var failed by remember { mutableStateOf<String?>(null) }
    val viewing = L("captureRecordingViewing")
    val separateFailed = L("captureRecordingSeparateFailed")
    val separateTitle = L("captureRecordingSeparate")

    fun separate(recording: CaptureRecording) {
        working = recording.id
        failed = null
        scope.launch {
            if (store.separate(recording, conversations)) onDismiss() else failed = recording.id
            working = null
        }
    }

    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(L("captureRecordingsSheetTitle"), trailing = { SheetBarButton(L("done"), prominent = true, onClick = onDismiss) })
        OmiGroupedList {
            section {
                store.detail?.recordings.orEmpty().forEach { recording ->
                    row(key = recording.id, enabled = working == null, onClick = { if (!recording.isCurrent) onOpen(recording) }) {
                        Box(Modifier.width(24.dp), contentAlignment = Alignment.Center) {
                            SFImage(CaptureRecordingsSheet.symbol(recording.source), tint = DS.Palette.inkSecondary)
                        }
                        Column(Modifier.weight(1f).padding(start = DS.Spacing.md)) {
                            Text(CaptureRecordingsSheet.label(recording), style = DS.Typography.cardTitle, color = DS.Palette.ink)
                            if (recording.isCurrent) {
                                Text(viewing, style = DS.Typography.caption, color = DS.Palette.inkSecondary, modifier = Modifier.padding(top = DS.Spacing.xxs))
                            } else if (failed == recording.id) {
                                Text(separateFailed, style = DS.Typography.caption, color = DS.Palette.live, modifier = Modifier.padding(top = DS.Spacing.xxs))
                            }
                        }
                        when {
                            recording.isCurrent -> SFImage("checkmark", tint = DS.Palette.agent)
                            working == recording.id -> OmiProgress()
                            else -> OmiPillButton(separateTitle, prominent = false) { separating = recording }
                        }
                    }
                }
            }
        }
    }
    separating?.let { recording ->
        OmiAlert(
            L("captureRecordingSeparateTitle"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("captureRecordingSeparateConfirm"), DialogButton.Role.Destructive) { separate(recording) },
            ),
            onDismiss = { separating = null },
            message = L("captureRecordingSeparateMessage", CaptureRecordingsSheet.label(recording)),
        )
    }
}

object CaptureRecordingsSheet {
    /** "Desktop · 13:57 – 14:59". */
    fun label(recording: CaptureRecording): String {
        var time = recording.start?.let(Formatted::shortTime) ?: ""
        val end = recording.end
        if (end != null && recording.start != null) time += " – ${Formatted.shortTime(end)}"
        return listOf(source(recording.source), time).filter { it.isNotEmpty() }.joinToString(" · ")
    }

    /** Device names stay untranslated, as on iOS; the phone is "Phone" here (iOS says "iPhone"). */
    fun source(source: String?): String = when (source) {
        "phone", "phone_call" -> "Phone"
        "apple_watch" -> "Apple Watch"
        "desktop", "screenpipe" -> "Desktop"
        null, "" -> "Omi"
        else -> source.take(1).uppercase() + source.drop(1).replace("_", " ")
    }

    fun symbol(source: String?): String = when (source) {
        "phone", "phone_call" -> "iphone"
        "apple_watch" -> "applewatch"
        "desktop", "screenpipe" -> "desktopcomputer"
        else -> "waveform"
    }
}

/**
 * Developer > "Test a Conversation Prompt": runs a prompt over this transcript once and shows the
 * result; nothing is saved (Flutter `test_prompts.dart`).
 */
@Composable
fun TestPromptSheet(store: ConversationDetailStore, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val focus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    var prompt by remember { mutableStateOf("") }
    var result by remember { mutableStateOf<String?>(null) }
    var running by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { focus.requestFocus() }

    fun run() {
        running = true
        failed = false
        focusManager.clearFocus()
        scope.launch {
            val summary = store.testPrompt(prompt)
            result = summary
            failed = summary == null
            running = false
        }
    }

    OmiSheet(onDismiss = onDismiss) {
        SheetBar(
            L("testConversationPrompt"),
            leading = { SheetBarButton(L("cancel"), onClick = onDismiss) },
            trailing = {
                if (running) OmiProgress() else SheetBarIcon("paperplane.fill", enabled = prompt.isNotBlank(), onClick = ::run)
            },
        )
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(DS.Spacing.gutter),
        ) {
            val placeholder = L("prompt")
            Box(Modifier.fillMaxWidth().omiField().padding(DS.Spacing.lg)) {
                if (prompt.isEmpty()) Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary)
                BasicTextField(
                    value = prompt,
                    onValueChange = { prompt = it },
                    textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                    cursorBrush = SolidColor(DS.Palette.agent),
                    minLines = 4,
                    maxLines = 12,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 80.dp).focusRequester(focus),
                )
            }
            if (failed) {
                Text(L("somethingWentWrong"), style = DS.Typography.callout, color = DS.Palette.live, modifier = Modifier.padding(top = DS.Spacing.lg))
            }
            val text = result
            if (!text.isNullOrEmpty()) {
                Text(L("result"), style = DS.Typography.sectionTitle, color = DS.Palette.ink, modifier = Modifier.padding(top = DS.Spacing.lg))
                SelectionContainer(Modifier.padding(top = DS.Spacing.lg)) {
                    Text(text, style = DS.Typography.body, color = DS.Palette.ink)
                }
            }
        }
    }
}
