package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiSectionBuilder
import java.text.Normalizer

/** Port of `SettingsSearch.swift`: one searchable setting, what it is called and the screen that holds it. */
data class SettingsSearchEntry(val title: String, val topic: SettingsTopic) {
    val id: String get() = "${topic.rawValue}.$title"

    companion object {
        /** Every setting by the name it shows under, in the screen that holds it. */
        @Composable
        fun all(): List<SettingsSearchEntry> {
            val titles: List<Pair<SettingsTopic, List<String>>> = listOf(
                SettingsTopic.Account to listOf(L("account"), L("profile"), L("name"), L("email"), L("nativeRedoOnboarding"), L("nativeSignOut"), L("nativeDeleteAccount")),
                SettingsTopic.PlanUsage to listOf(
                    L("nativeSettingsPlanUsage"), L("nativePlan"), L("upgrade"), L("managePlan"), L("cancelSubscription"),
                    L("nativeUsage"), L("nativeSettingsActivity"), L("fairUsePolicy"),
                ),
                SettingsTopic.Referral to listOf(L("nativeSettingsInviteFriends"), L("referralProgram"), L("nativeYourInviteLink")),
                SettingsTopic.Devices to listOf(L("nativeSettingsMyOmi"), L("nativeMyDevices")),
                SettingsTopic.Listening to listOf(
                    L("nativeSettingsListening"), L("language"), L("nativeSpokenLanguage"), L("nativeDetectLanguages"),
                    L("nativeSettingsVocabulary"), L("nativeCustomVocabulary"), L("nativeSettingsEndsAfter"),
                    L("conversationTimeout"), L("nativeSettingsAdvanced"), L("nativeSpeechModel"), L("nativeOnDeviceTranscription"),
                    L("nativeTranscribeLater"), L("nativeTranscriptionLog"), L("nativeRecordingsOnPhone"),
                ),
                SettingsTopic.Voices to listOf(
                    L("nativeSettingsVoices"), L("people"), L("nativeRecordYourVoiceAgain"),
                    L("nativeSettingsAskWhoSpoke"), L("nativeSettingsRememberVoices"), L("nativeSettingsIgnoredVoices"), L("nativeSettingsCleanUp"),
                ),
                SettingsTopic.Memory to listOf(
                    L("nativeSettingsMemory"), L("nativeWhatIKnowAboutYou"), L("memories"), L("memoryGraph"),
                    L("nativeSettingsImportHistory"), L("importData"), L("nativeDeleteAllMemories"),
                ),
                SettingsTopic.Assistant to listOf(
                    L("nativeAssistant"), L("nativeSpokenReplies"), L("nativeAssistantVoice"),
                    L("nativeProactiveNotifications"), L("notificationFrequency"), L("nativeDailyRecap"), L("nativeDailySummary"),
                ),
                SettingsTopic.Apps to listOf(
                    L("nativeSettingsApps"), L("nativeCapabilities"), L("nativeAppsKindIntegrations"), "Google Calendar", "Gmail",
                    "Todoist", "Asana", "ClickUp", "Google Tasks", "Health Connect", L("nativeRemindersName"), L("nativeSettingsInstalledApps"),
                ),
                SettingsTopic.BrowseApps to listOf(L("nativeBrowseApps"), L("nativeOmiApps")),
                SettingsTopic.ConnectAI to listOf(L("nativeConnectAI"), "Claude", "ChatGPT", "MCP"),
                SettingsTopic.PhoneCalls to listOf(L("nativeSettingsPhoneCalls")),
                SettingsTopic.Appearance to listOf(L("appearance"), L("nativeAppearanceSystem"), L("nativeAppearanceLight"), L("nativeAppearanceDark"), L("nativeAppLanguage")),
                SettingsTopic.Notifications to listOf(L("notifications"), L("nativeNotificationsAllow")),
                SettingsTopic.Privacy to listOf(
                    L("nativeSettingsPrivacy"), L("dataAndPrivacy"), L("nativeStoreRecordings"), L("nativeSettingsAudioOnPhone"),
                    L("location"), L("nativePermissions"), L("nativeSettingsAppAccess"), L("exportAllData"), L("privacyPolicy"),
                ),
                SettingsTopic.Help to listOf(L("nativeSettingsHelp"), L("helpCenter"), L("whatsNew"), L("nativeSendFeedback"), L("nativeReplayIntroduction"), L("nativeDeveloperMode")),
            )
            return titles.flatMap { (topic, names) -> names.map { SettingsSearchEntry(it, topic) } }
        }

        /** Case- and accent-insensitive match on the setting's name; one row per name and screen. */
        fun matching(all: List<SettingsSearchEntry>, query: String): List<SettingsSearchEntry> {
            val needle = fold(query.trim())
            if (needle.isEmpty()) return emptyList()
            val seen = HashSet<String>()
            return all.filter { fold(it.title).contains(needle) && seen.add(it.id) }
        }

        private fun fold(text: String): String =
            Normalizer.normalize(text, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase()
    }
}

/**
 * `SettingsSearchResults`: the results under the Settings search field; picking one opens its
 * screen. Nothing found: `ContentUnavailableView.search(text:)`.
 */
@Composable
internal fun OmiSectionBuilder.settingsSearchResults(query: String, onOpen: (SettingsTopic) -> Unit) {
    plainRow { SearchResults(query, onOpen) }
}

@Composable
private fun SearchResults(query: String, onOpen: (SettingsTopic) -> Unit) {
    val haptics = rememberHaptics()
    val results = SettingsSearchEntry.matching(SettingsSearchEntry.all(), query)
    if (results.isEmpty()) {
        Column(Modifier.fillMaxWidth().padding(top = 80.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            SFImage("magnifyingglass", size = 44.sp(), tint = DS.Palette.inkSecondary)
            // The system's own "No Results for ..." text has no key in the catalog; Omi's closest one.
            Text(L("noResultsFound"), style = TextStyles.title2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Bold), color = DS.Palette.ink, textAlign = TextAlign.Center)
            Text("\u201C$query\u201D", style = DS.Typography.callout, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
        }
        return
    }
    Column(Modifier.fillMaxWidth()) {
        results.forEachIndexed { index, entry ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .plainButton {
                        haptics.selection()
                        onOpen(entry.topic)
                    }
                    .heightIn(min = OmiListMetrics.minRowHeight)
                    .padding(horizontal = OmiListMetrics.rowInset, vertical = 13.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
            ) {
                SettingsIcon(entry.topic.systemImage)
                Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                    Text(entry.title, style = DS.Typography.body, color = DS.Palette.ink)
                    Text(entry.topic.title(), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                }
            }
            if (index < results.lastIndex) com.friend.ios.design.OmiHairline(Modifier.padding(end = OmiListMetrics.rowInset), leading = OmiListMetrics.iconSeparatorInset)
        }
    }
}

private fun Int.sp() = androidx.compose.ui.unit.TextUnit(this.toFloat(), androidx.compose.ui.unit.TextUnitType.Sp)

/**
 * The search field the top bar's magnifier reveals: the quiet search capsule of Tasks and
 * Memories, focused at once, a clear button while typing and Cancel beside it.
 */
@Composable
fun SettingsSearchField(text: String, onTextChange: (String) -> Unit, onCancel: () -> Unit) {
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { if (text.isEmpty()) focus.requestFocus() }
    Row(Modifier.fillMaxWidth().padding(top = DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Row(
            Modifier.weight(1f).heightIn(min = DS.Size.searchField).omiSurface(CircleShape).padding(horizontal = DS.Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
        ) {
            SFImage("magnifyingglass", tint = DS.Palette.inkSecondary)
            Box(Modifier.weight(1f)) {
                if (text.isEmpty()) Text(L("nativeSearchSettings"), style = DS.Typography.body, color = DS.Palette.inkTertiary, maxLines = 1)
                BasicTextField(
                    value = text,
                    onValueChange = onTextChange,
                    singleLine = true,
                    textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                    cursorBrush = SolidColor(DS.Palette.agent),
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, imeAction = ImeAction.Search),
                    modifier = Modifier.fillMaxWidth().focusRequester(focus),
                )
            }
            if (text.isNotEmpty()) {
                SFImage("xmark.circle.fill", tint = DS.Palette.inkTertiary, modifier = Modifier.plainButton { onTextChange("") }, contentDescription = L("close"))
            }
        }
        Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.plainButton(onClick = onCancel))
    }
}
