package com.friend.ios.features.today

import android.content.Context
import android.media.MediaPlayer
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.SpeakerPrompt
import com.friend.ios.core.models.SpeakerPromptAnswer
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.service.LocalVoicesStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Port of `SpeakerPromptSheet`: "Who is this?" as a sheet from Home's For you row; closes once nothing is left to ask. */
@Composable
internal fun SpeakerPromptSheet(onDismiss: () -> Unit) {
    val voices = LocalVoicesStore.current
    LaunchedEffect(voices.currentPrompt == null) { if (voices.currentPrompt == null) onDismiss() }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            SpeakerPromptCard(Modifier.padding(DS.Spacing.gutter))
        }
    }
}

/**
 * Port of `SpeakerPromptCard.swift`: one voice from a recent conversation at a time, answered in a
 * tap (Flutter `speaker_tag_prompt_card`). Closing it tells Omi to ask less often.
 */
@Composable
internal fun SpeakerPromptCard(modifier: Modifier = Modifier) {
    val voices = LocalVoicesStore.current
    val prompt = voices.currentPrompt ?: return
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val player = remember { AudioClipPlayer(context) }
    var unplayable by remember { mutableStateOf(setOf<String>()) }
    var naming by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    DisposableEffect(Unit) { onDispose { player.stop() } }
    LaunchedEffect(prompt.id) { voices.promptsShown() }

    fun answer(answer: SpeakerPromptAnswer) {
        haptics.selection()
        player.stop()
        scope.launch { voices.answer(prompt, answer) }
    }

    Column(modifier.omiCard(padding = DS.Spacing.lg), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        HStack(Modifier.fillMaxWidth(), spacing = DS.Spacing.sm) {
            SFImage("person.wave.2", size = 17.sp, tint = DS.Palette.ink)
            Text(SpeakerPromptCard.question(prompt), style = DS.Typography.cardTitle, color = DS.Palette.ink)
            Spacer(Modifier.weight(1f))
            SFImage(
                "xmark", size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary,
                modifier = Modifier.plainButton {
                    player.stop()
                    scope.launch { voices.dismissPrompts() }
                },
                contentDescription = L("close"),
            )
        }
        HStack(Modifier.fillMaxWidth(), spacing = DS.Spacing.md, alignment = Alignment.Top) {
            val disabled = prompt.id in unplayable
            SFImage(
                if (player.playingID == prompt.id) "stop.circle.fill" else "play.circle.fill",
                size = 34.sp,
                tint = if (disabled) DS.Palette.inkDisabled else DS.Palette.agent,
                modifier = Modifier.plainButton(enabled = !disabled) {
                    scope.launch {
                        val played = player.toggle(prompt.id) { voices.clip(prompt) }
                        if (!played) unplayable = unplayable + prompt.id
                    }
                },
                contentDescription = L("speakerTagPromptPlayClip"),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                if (prompt.excerpt.isNotEmpty()) {
                    Text("“${prompt.excerpt}”", style = DS.Typography.callout.copy(fontStyle = FontStyle.Italic), color = DS.Palette.ink, maxLines = 3)
                }
                Text(prompt.conversationTitle.ifEmpty { L("untitledConversation") }, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                if (disabled) Text(L("speakerTagPromptClipUnavailable"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
            }
        }
        Answers(prompt, ::answer) {
            newName = ""
            naming = true
        }
    }
    if (naming) {
        OmiAlert(
            title = L("speakerTagPromptWhoIsThis"),
            buttons = listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("save")) {
                    val name = newName.trim()
                    if (name.length >= 2) answer(SpeakerPromptAnswer.NewPerson(name.take(40)))
                },
            ),
            onDismiss = { naming = false },
            textField = L("speakerTagPromptNameHint") to newName,
            onTextChange = { newName = it },
        )
    }
}

@Composable
private fun Answers(prompt: SpeakerPrompt, answer: (SpeakerPromptAnswer) -> Unit, onNewPerson: () -> Unit) {
    when (prompt.kind) {
        SpeakerPrompt.Kind.OwnerCheck -> Chips(
            listOf(L("yes") to SpeakerPromptAnswer.Me, L("no") to SpeakerPromptAnswer.NotMe, L("speakerTagPromptNotSureAction") to SpeakerPromptAnswer.Skip),
            answer,
        )
        SpeakerPrompt.Kind.ConfirmPerson -> {
            val yes = prompt.suggestedPersonID?.let { SpeakerPromptAnswer.Person(it) } ?: SpeakerPromptAnswer.Skip
            Chips(
                listOf(L("yes") to yes, L("no") to SpeakerPromptAnswer.SomeoneElse, L("speakerTagPromptNotSureAction") to SpeakerPromptAnswer.Skip),
                answer,
            )
        }
        SpeakerPrompt.Kind.Identify -> HStack(Modifier.horizontalScroll(rememberScrollState()), spacing = DS.Spacing.sm) {
            prompt.candidates.forEach { candidate -> OmiPillButton(candidate.name) { answer(SpeakerPromptAnswer.Person(candidate.id)) } }
            OmiPillButton(L("speakerTagPromptThatsMeAction"), prominent = false) { answer(SpeakerPromptAnswer.Me) }
            OmiPillButton(L("newPersonEllipsis"), prominent = false, onClick = onNewPerson)
            OmiPillButton(L("speakerTagPromptNotAPerson"), prominent = false) { answer(SpeakerPromptAnswer.NotAPerson) }
            OmiPillButton(L("speakerTagPromptNotSureAction"), prominent = false) { answer(SpeakerPromptAnswer.Skip) }
        }
    }
}

@Composable
private fun Chips(options: List<Pair<String, SpeakerPromptAnswer>>, answer: (SpeakerPromptAnswer) -> Unit) {
    HStack(spacing = DS.Spacing.sm) {
        options.forEachIndexed { index, (title, value) -> OmiPillButton(title, prominent = index == 0) { answer(value) } }
    }
}

object SpeakerPromptCard {
    @Composable
    fun question(prompt: SpeakerPrompt): String = when (prompt.kind) {
        SpeakerPrompt.Kind.OwnerCheck -> L("speakerTagPromptIsThisYou")
        SpeakerPrompt.Kind.ConfirmPerson -> L("speakerTagPromptIsThisPerson", prompt.suggestedPersonName ?: "")
        SpeakerPrompt.Kind.Identify -> L("speakerTagPromptWhoIsThis")
    }
}

/**
 * Port of `AudioClipPlayer` (OmiComponents): plays one short WAV clip at a time; [toggle] stops the
 * one playing. Returns false when the clip cannot be loaded or played.
 */
@Stable
internal class AudioClipPlayer(private val context: Context) {
    var playingID: String? by mutableStateOf(null)
        private set
    private var player: MediaPlayer? = null

    suspend fun toggle(id: String, load: suspend () -> ByteArray?): Boolean {
        if (playingID == id) {
            stop()
            return true
        }
        stop()
        val data = load() ?: return false
        val file = withContext(Dispatchers.IO) {
            File(context.cacheDir, "clips").apply { mkdirs() }.resolve("clip.wav").also { it.writeBytes(data) }
        }
        return try {
            val media = MediaPlayer().apply {
                setDataSource(file.path)
                setOnCompletionListener { stop() }
                prepare()
                start()
            }
            player = media
            playingID = id
            true
        } catch (e: Exception) {
            stop()
            false
        }
    }

    fun stop() {
        player?.runCatching { stop() }
        player?.release()
        player = null
        playingID = null
    }
}
