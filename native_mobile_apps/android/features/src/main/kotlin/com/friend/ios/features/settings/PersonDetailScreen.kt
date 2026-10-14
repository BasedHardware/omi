package com.friend.ios.features.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.PersonConversation
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.EmojiBadge
import com.friend.ios.design.Formatted
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.semibold
import com.friend.ios.features.components.AudioClipPlayer
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiDisclosureChevron
import com.friend.ios.features.components.rememberAudioClipPlayer
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.conversations
import com.friend.ios.service.stores.deleteSample
import com.friend.ios.service.stores.loadPeopleWithStats
import com.friend.ios.service.stores.person
import com.friend.ios.service.stores.setPinned
import kotlinx.coroutines.launch

/**
 * Port of `PersonDetailScreen.swift`: one person: talk time, when Omi last heard them, their voice
 * samples and conversations (Flutter `person_detail_page`).
 */
@Composable
fun PersonDetailScreen(personID: String, onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val navigator = LocalSettingsNavigator.current
    val scope = rememberCoroutineScope()
    val conversations = remember { mutableStateListOf<PersonConversation>() }
    var page by remember { mutableIntStateOf(0) }
    var hasMore by remember { mutableStateOf(true) }
    var loadFailed by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf(false) }
    var renameText by remember { mutableStateOf("") }
    var confirmsDelete by remember { mutableStateOf(false) }
    var deletingSample by remember { mutableStateOf<Int?>(null) }
    val player = rememberAudioClipPlayer()

    suspend fun loadMore() {
        if (!hasMore || isLoading) return
        isLoading = true
        val next = settings.conversations(personID, page + 1)
        isLoading = false
        if (next == null) {
            loadFailed = true
            return
        }
        loadFailed = false
        page += 1
        val known = conversations.map { it.id }.toSet()
        conversations += next.filter { it.id !in known }
        hasMore = next.size == 20
    }
    LaunchedEffect(Unit) { if (settings.person(personID) == null) settings.loadPeopleWithStats() }
    LaunchedEffect(Unit) { loadMore() }

    val person = settings.person(personID)
    SettingsListPage(
        person?.name.orEmpty(),
        onBack,
        trailing = {
            if (person != null) {
                // Pin, rename and delete: the rarer actions, in the one menu.
                OmiMenu(
                    listOf(
                        MenuSection(
                            items = listOf(
                                MenuItem(L("pinAction"), if (person.isPinned) "checkmark" else "pin") { scope.launch { settings.setPinned(person.id, !person.isPinned) } },
                                MenuItem(L("nativeRename"), "pencil") {
                                    renameText = person.name
                                    renaming = true
                                },
                                MenuItem(L("deletePersonLabel"), "trash", destructive = true) { confirmsDelete = true },
                            ),
                        ),
                    ),
                    contentDescription = L("nativeMore"),
                ) { GlassCircleLabel("ellipsis") }
            }
        },
    ) {
        if (person != null) {
            stats(person)
            samples(person, player) { deletingSample = it }
            conversationSection(conversations, loadFailed, hasMore, navigator.openConversation?.let { open -> { id: String -> navigator.dismiss(); open(id) } }) {
                scope.launch { loadMore() }
            }
        }
    }

    if (renaming) {
        OmiAlert(
            L("nativeRename"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("save")) {
                    val name = renameText
                    scope.launch { settings.renamePerson(personID, name) }
                },
            ),
            onDismiss = { renaming = false },
            textField = L("nativeYourName") to renameText,
            onTextChange = { renameText = it },
        )
    }
    if (confirmsDelete) {
        OmiConfirmationDialog(
            L("nativeDeletePersonQuestion", person?.name.orEmpty()),
            listOf(
                DialogButton(L("deletePersonLabel"), DialogButton.Role.Destructive) {
                    onBack()
                    scope.launch { settings.deletePerson(personID) }
                },
            ),
            onDismiss = { confirmsDelete = false },
            message = L("nativeDeletePersonMessage"),
        )
    }
    deletingSample?.let { index ->
        OmiConfirmationDialog(
            L("deleteSampleQuestion"),
            listOf(
                DialogButton(L("deleteSample"), DialogButton.Role.Destructive) {
                    player.stop()
                    scope.launch { settings.deleteSample(personID, index) }
                },
            ),
            onDismiss = { deletingSample = null },
            message = L("deleteSampleConfirmation", person?.name.orEmpty()),
        )
    }
}

@Composable
private fun com.friend.ios.features.components.OmiListBuilder.stats(person: Person) {
    section {
        row {
            Row(Modifier.fillMaxWidth()) {
                Stat(person.conversationCount?.toString() ?: "–", L("conversations"), Modifier.weight(1f))
                Stat(person.talkSeconds?.let(::talkTime) ?: "–", L("personTalkTime"), Modifier.weight(1f))
                Stat(person.lastHeardAt?.let(::relative) ?: "–", L("personLastHeard"), Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun Stat(value: String, label: String, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
        Text(value, style = DS.Typography.cardTitle.semibold(), color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
        Text(label, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun com.friend.ios.features.components.OmiListBuilder.samples(person: Person, player: AudioClipPlayer, onDelete: (Int) -> Unit) {
    section(header = L("nativeVoiceProfile"), footer = L("voiceSettingsSaveOthersSubtitle")) {
        if (person.sampleURLs.isEmpty()) {
            row { Text(L("nativeNoVoiceSamples"), style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
        }
        val delete = L("delete")
        person.sampleURLs.forEachIndexed { index, url ->
            // A tap plays the sample (or stops it); `.swipeActions` Delete is the long press here.
            val playing = player.playingID == url
            val label = if (playing) L("pausePlayback") else L("play")
            row(key = url) {
                ContextMenuBox(
                    { listOf(MenuSection(items = listOf(MenuItem(delete, "trash", destructive = true) { onDelete(index) }))) },
                    Modifier.fillMaxWidth(),
                    onTap = { player.toggle(url, url) },
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                        SFImage(if (playing) "stop.circle" else "play.circle", size = 22.sp, tint = DS.Palette.ink, contentDescription = label)
                        Text(L("nativeSampleNumber", (index + 1).toString()), style = DS.Typography.body, color = DS.Palette.ink)
                    }
                }
            }
        }
    }
}

@Composable
private fun com.friend.ios.features.components.OmiListBuilder.conversationSection(
    conversations: List<PersonConversation>,
    loadFailed: Boolean,
    hasMore: Boolean,
    onOpen: ((String) -> Unit)?,
    onLoadMore: () -> Unit,
) {
    section(header = L("conversations")) {
        if (conversations.isEmpty() && loadFailed) {
            row(onClick = onLoadMore) { Text(L("tryAgain"), style = DS.Typography.body, color = DS.Palette.agent) }
        } else if (conversations.isEmpty() && !hasMore) {
            row { Text(L("noConversationsYet"), style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
        }
        conversations.forEach { conversation ->
            row(key = conversation.id, onClick = onOpen?.let { { it(conversation.id) } }, enabled = onOpen != null, separatorInset = 68.dp) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    EmojiBadge(conversation.emoji)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text(conversation.title.ifEmpty { L("untitledConversation") }, style = DS.Typography.body, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(Formatted.abbreviatedDate(conversation.date) + ", " + Formatted.shortTime(conversation.date), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                    if (onOpen != null) OmiDisclosureChevron()
                }
                if (conversation.id == conversations.lastOrNull()?.id) LaunchedEffect(conversation.id) { onLoadMore() }
            }
        }
        if (hasMore && conversations.isNotEmpty()) {
            row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
        }
    }
}

/** [GlassCircleButton]'s look without its own tap, as the label of a pull-down menu. */
@Composable
internal fun GlassCircleLabel(systemImage: String) {
    val dark = com.friend.ios.design.LocalOmiDark.current
    Box(
        Modifier
            .size(44.dp)
            .background(if (dark) com.friend.ios.design.hex(0x282828) else com.friend.ios.design.hex(0xF5F5F5), androidx.compose.foundation.shape.CircleShape)
            .border(1.dp, if (dark) com.friend.ios.design.hex(0x363636) else com.friend.ios.design.hex(0xE4E4E4), androidx.compose.foundation.shape.CircleShape),
        contentAlignment = Alignment.Center,
    ) { SFImage(systemImage, size = 19.sp, tint = DS.Palette.ink) }
}
