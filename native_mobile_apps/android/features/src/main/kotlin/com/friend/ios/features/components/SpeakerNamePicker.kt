package com.friend.ios.features.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarButton
import com.friend.ios.features.settings.OmiSegmentedPicker
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.TranscriptSpeakersStore
import com.friend.ios.service.stores.people
import java.text.Normalizer

/**
 * Port of `SpeakerNamePicker.swift`: "Who is this?" for one transcript line: you, one of your
 * people, a new name, or (finished conversations only) not a person (Flutter `name_speaker_sheet`).
 * The search field doubles as the new-name field. Shared by the conversation page and the live
 * transcript.
 */
object SpeakerNamePicker {
    /** The line being named. */
    class Line(
        val text: String,
        val isUser: Boolean,
        val personID: String?,
        /** The line has a voice (speaker number): naming can cover all of its lines. */
        val hasVoice: Boolean,
        /** How many lines share its voice. */
        val sameVoiceCount: Int,
        offersNotAPerson: Boolean,
    ) {
        /** "Not a person" is offered (finished conversations). */
        val offersNotAPerson: Boolean = offersNotAPerson && hasVoice
    }
}

/** [onChoose] runs as the sheet closes; the scope is `Line` for a line without a voice. */
@Composable
fun SpeakerNamePicker(
    line: SpeakerNamePicker.Line,
    isSaving: Boolean,
    onDismiss: () -> Unit,
    onChoose: (TranscriptSpeakersStore.Choice, TranscriptSpeakersStore.Scope) -> Unit,
) {
    val settings = LocalSettingsStore.current
    val haptics = rememberHaptics()
    var query by remember { mutableStateOf("") }
    var scope by remember { mutableStateOf(TranscriptSpeakersStore.Scope.Voice) }

    /** The transcript changes at once; the sheet closes without waiting for the server. */
    fun choose(choice: TranscriptSpeakersStore.Choice) {
        haptics.selection()
        val chosen = if (line.hasVoice) scope else TranscriptSpeakersStore.Scope.Line
        onDismiss()
        onChoose(choice, chosen)
    }

    /** The typed text when it is not already one of your people (or your own name). */
    val newName: String? = run {
        val name = query.trim()
        val length = name.codePointCount(0, name.length)
        if (length < 2 || length > 40) return@run null
        val taken = settings.people.any { fold(it.name) == fold(name) }
        if (taken) null else name.take(1).uppercase() + name.drop(1)
    }

    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(L("speakerTagPromptWhoIsThis"), leading = { SheetBarButton(L("cancel"), onClick = onDismiss) })
        OmiSearchField(L("nativeSpeakerSearchOrName"), query, { query = it }, L("nativeClearSearch"), Modifier.padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.xs))
        OmiGroupedList(Modifier.weight(1f, fill = false), contentPadding = androidx.compose.foundation.layout.PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                row {
                    Text(
                        "“${line.text}”",
                        style = DS.Typography.callout.copy(fontStyle = FontStyle.Italic),
                        color = DS.Palette.inkSecondary,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (line.sameVoiceCount > 1) {
                    row {
                        val scopeLabel = L("nativeSpeakerScope")
                        Column(Modifier.fillMaxWidth().semantics { contentDescription = scopeLabel }) {
                            OmiSegmentedPicker(
                                listOf(L("nativeSpeakerAllLines", "${line.sameVoiceCount}"), L("nativeSpeakerOnlyThisLine")),
                                selected = if (scope == TranscriptSpeakersStore.Scope.Voice) 0 else 1,
                                textStyle = DS.Typography.callout,
                            ) { scope = if (it == 0) TranscriptSpeakersStore.Scope.Voice else TranscriptSpeakersStore.Scope.Line }
                        }
                    }
                }
            }
            section {
                row(onClick = { choose(TranscriptSpeakersStore.Choice.Me) }, enabled = !isSaving) {
                    PickerRow(L("speakerTagPromptThatsMeAction"), "person.crop.circle", selected = line.isUser)
                }
            }
            section(headerContent = if (settings.people.isNotEmpty()) ({ OmiSectionLabel(L("people")) }) else null) {
                settings.people(query).forEach { person ->
                    row(key = person.id, onClick = { choose(TranscriptSpeakersStore.Choice.PersonChoice(person)) }, enabled = !isSaving) {
                        PickerRow(person.name, "person", selected = !line.isUser && line.personID == person.id)
                    }
                }
                if (newName != null) {
                    row(onClick = { choose(TranscriptSpeakersStore.Choice.NewPerson(newName)) }, enabled = !isSaving) {
                        PickerRow(L("addNamedPersonAction", newName), "plus.circle", selected = false)
                    }
                } else if (settings.people.isEmpty()) {
                    row { Text(L("nativeSpeakerTypeName"), style = DS.Typography.caption, color = DS.Palette.inkSecondary) }
                }
            }
            if (line.offersNotAPerson) {
                section(footer = L("nativeNotAPersonFooter")) {
                    row(onClick = { choose(TranscriptSpeakersStore.Choice.NotAPerson) }, enabled = !isSaving) {
                        Text(L("speakerTagPromptNotAPerson"), style = DS.Typography.body, color = DS.Palette.live)
                    }
                }
            }
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.PickerRow(title: String, systemImage: String, selected: Boolean) {
    HStack(Modifier.weight(1f), spacing = DS.Spacing.md) {
        SFImage(systemImage, tint = DS.Palette.agent)
        Text(title, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
        if (selected) SFImage("checkmark", tint = DS.Palette.agent)
    }
}

private fun fold(text: String): String = Normalizer.normalize(text, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase()
