package com.friend.ios.features.settings

import android.text.format.DateUtils
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Person
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.SFImage
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.features.onboarding.LocalVoiceIntroFactory
import com.friend.ios.features.onboarding.VoiceProfileScreen
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.LocalVoicesStore
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.stores.VoiceIntroStore
import com.friend.ios.service.stores.cleanUpCandidates
import com.friend.ios.service.stores.loadPeopleWithStats
import com.friend.ios.service.stores.people
import kotlinx.coroutines.launch
import java.time.Instant
import java.util.Locale

/**
 * Port of `PeopleScreen.swift`. How Omi helps > Voices & people: your own voice, the people Omi
 * tells apart, and how it learns voices (asking to tag, remembering named voices, ignored voices,
 * clean up).
 */
@Composable
fun PeopleScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val voices = LocalVoicesStore.current
    val navigator = LocalSettingsNavigator.current
    val voiceIntro = LocalVoiceIntroFactory.current
    val devices = LocalDeviceStore.current
    val scope = rememberCoroutineScope()
    var query by rememberSaveable { mutableStateOf("") }
    var adding by rememberSaveable { mutableStateOf(false) }
    var newName by rememberSaveable { mutableStateOf("") }
    var renaming by rememberSaveable { mutableStateOf<String?>(null) }
    var renameText by rememberSaveable { mutableStateOf("") }
    var page by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { settings.loadPeopleWithStats() }
    LaunchedEffect(Unit) { voices.loadSettings() }

    SettingsSubPageHost(
        page = page,
        onClose = { page = null },
        base = {
            val people = settings.people(query)
            val searchable = settings.people("").size >= SEARCH_THRESHOLD
            SettingsListPage(L("nativeSettingsVoices"), onBack) {
                // The people search, only once there are enough people to need it (`.searchable`).
                if (searchable) {
                    section { plainRow { OmiSearchField(L("peopleSearchPlaceholder"), query, { query = it }, L("nativeClearSearch")) } }
                }
                // The voice screen (onboarding's voice step) needs the app's listening session.
                if (voiceIntro != null && query.isEmpty()) {
                    section(header = L("nativeKickerYourVoice")) {
                        row(onClick = { page = "voice" }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                            SettingsRowLabel(L("nativeRecordYourVoiceAgain"), "waveform")
                        }
                    }
                }
                section(header = L("people")) {
                    if (people.isEmpty() && query.isEmpty()) {
                        row { Text(L("nativePeopleFooter"), style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
                    }
                    val renameTitle = L("nativeRename")
                    val deleteTitle = L("delete")
                    people.forEach { person ->
                        row(key = person.id, onClick = { navigator.push(SettingsRoute.Person(person.id)) }, chevron = true, separatorInset = 28.dp) {
                            // `.swipeActions` (Delete, Rename) on iOS; a long press offers them here.
                            ContextMenuBox(
                                {
                                    listOf(
                                        MenuSection(
                                            items = listOf(
                                                MenuItem(renameTitle, "pencil") {
                                                    renameText = person.name
                                                    renaming = person.id
                                                },
                                                MenuItem(deleteTitle, "trash", destructive = true) { scope.launch { settings.deletePerson(person.id) } },
                                            ),
                                        ),
                                    )
                                },
                                Modifier.fillMaxWidth(),
                                onTap = { navigator.push(SettingsRoute.Person(person.id)) },
                            ) { PersonRow(person) }
                        }
                    }
                    if (query.isEmpty()) {
                        row(onClick = {
                            newName = ""
                            adding = true
                        }) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                                SettingsIcon("plus", tint = DS.Palette.ink)
                                Text(L("nativeAddPerson"), style = DS.Typography.body, color = DS.Palette.ink)
                            }
                        }
                    }
                }
                if (query.isEmpty()) {
                    // The two voice-learning switches (Flutter `voice_profile_settings_section`), ignored voices and clean up.
                    val candidates = settings.cleanUpCandidates
                    section(header = L("nativeSettingsRecognition"), footer = L("voiceSettingsSaveOthersSubtitle")) {
                        row {
                            OmiToggleRow(voices.settings?.asksToTag ?: true, { value -> scope.launch { voices.setAsksToTag(value) } }, enabled = voices.settings != null) {
                                Text(L("nativeSettingsAskWhoSpoke"), style = DS.Typography.body, color = DS.Palette.ink)
                            }
                        }
                        row {
                            OmiToggleRow(voices.settings?.savesOtherVoices ?: true, { value -> scope.launch { voices.setSavesOtherVoices(value) } }, enabled = voices.settings != null) {
                                Text(L("nativeSettingsRememberVoices"), style = DS.Typography.body, color = DS.Palette.ink)
                            }
                        }
                        row(onClick = { page = "ignored" }, chevron = true) { SettingsButtonText(L("nativeSettingsIgnoredVoices")) }
                        if (candidates.isNotEmpty()) {
                            row(onClick = { page = "cleanUp" }, chevron = true) { SettingsLabeledContent(L("nativeSettingsCleanUp"), candidates.size.toString()) }
                        }
                    }
                }
            }
        },
    ) { current ->
        when (current) {
            "ignored" -> IgnoredVoicesScreen { page = null }
            "cleanUp" -> PeopleCleanUpScreen { page = null }
            else -> voiceIntro?.let { make ->
                val voice = remember { make() }
                // Through the Omi when it is connected, else the phone.
                val source = if (devices.connection == DeviceStore.Connection.Connected) VoiceIntroStore.Source.Device else VoiceIntroStore.Source.Phone
                VoiceProfileScreen(voice, source, settings.spokenLanguage ?: Locale.getDefault().language.ifEmpty { "en" }) { page = null }
            }
        }
    }

    if (adding) {
        OmiAlert(
            L("nativeAddPerson"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("nativeAdd"), enabled = newName.isNotBlank()) {
                    val name = newName
                    scope.launch { settings.addPerson(name) }
                },
            ),
            onDismiss = { adding = false },
            textField = L("name") to newName,
            onTextChange = { newName = it },
        )
    }
    renaming?.let { id ->
        OmiAlert(
            L("nativeRename"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("nativeDone")) {
                    val name = renameText
                    scope.launch { settings.renamePerson(id, name) }
                },
            ),
            onDismiss = { renaming = null },
            textField = L("name") to renameText,
            onTextChange = { renameText = it },
        )
    }
}

/** Past this many people a search field helps; below it, it is only clutter. */
private const val SEARCH_THRESHOLD = 8

/** Name, pin, and what Omi knows about the voice. */
@Composable
fun PersonRow(person: Person, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Monogram(person.name, size = 32.dp)
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                Text(person.name, style = DS.Typography.body, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (person.isPinned) SFImage("pin.fill", size = 11.sp, tint = DS.Palette.inkTertiary)
            }
            val parts = listOfNotNull(
                L("nativeVoiceSamples", person.sampleCount.toString()),
                person.lastHeardAt?.let { L("nativePersonLastHeardAgo", relative(it)) },
            )
            Text(parts.joinToString(" · "), style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** `.formatted(.relative(presentation: .named))`: "yesterday", "2 days ago". */
fun relative(instant: Instant): String =
    DateUtils.getRelativeTimeSpanString(instant.toEpochMilli(), System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS).toString()

/** `Formatting.talkTime`: "45s", "3m 20s", "1h 5m": how long someone spoke. */
fun talkTime(seconds: Double): String {
    val total = maxOf(0L, Math.round(seconds))
    val h = total / 3600
    val m = (total % 3600) / 60
    val s = total % 60
    val units = listOf(h to "h", m to "m", s to "s").dropWhile { it.first == 0L }.ifEmpty { listOf(0L to "s") }
    return units.take(2).filter { it.first > 0 || units.size == 1 }.joinToString(" ") { "${it.first}${it.second}" }
}

/** Voices marked Not a Person (TV, podcasts); restoring one lets Omi ask about it again (Flutter `ignored_voices_sheet`). */
@Composable
fun IgnoredVoicesScreen(onBack: () -> Unit) {
    val voices = LocalVoicesStore.current
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { voices.loadIgnored() }
    SettingsListPage(L("ignoredVoicesTitle"), onBack) {
        if (voices.ignoredLoaded && voices.ignored.isEmpty()) {
            section {
                plainRow {
                    com.friend.ios.design.OmiEmptyState(L("ignoredVoicesEmpty"), "speaker.slash", Modifier.padding(top = 72.dp))
                }
            }
        }
        if (voices.ignored.isNotEmpty()) {
            section(footer = L("voiceRestoredToast")) {
                voices.ignored.forEach { voice ->
                    row(key = voice.id) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                            Text(voice.conversationTitle.ifEmpty { L("untitledConversation") }, style = DS.Typography.body, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(L("speakerWithId", (voice.speakerID + 1).toString()), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                        }
                        com.friend.ios.design.OmiPillButton(L("restoreAction"), prominent = false) { scope.launch { voices.restore(voice) } }
                    }
                }
            }
        }
    }
}
