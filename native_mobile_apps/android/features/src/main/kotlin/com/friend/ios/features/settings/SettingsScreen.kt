package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.NavPath
import com.friend.ios.design.OmiNavigationStack
import com.friend.ios.design.rememberNavPath
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.OmiFlatList
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiSectionLabel
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.LocalDeveloperStore
import com.friend.ios.service.LocalPreferences
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.LocalSettingsStore
import kotlinx.coroutines.delay
import com.friend.ios.design.AppearanceMode

/**
 * Port of `SettingsScreen.swift`. Settings hold configuration only, every topic exactly once
 * (docs/STRUCTURE.md, "Settings tree"): the profile on top, four live tiles (the Omi, the plan,
 * apps, voices), then one flat list of the other topics and "More" for the rare ones. Search sits
 * behind the magnifier in the top bar.
 *
 * [initialTopic] opens a screen directly (deep links, headless QA): a topic's raw value
 * ("account", "listening"), a pushed screen ("referral", "planUsage", "browseApps"), or a
 * "/"-separated stack ("listening/vocabulary", "browseApps/app:<id>", "voices/person:<id>").
 * Without one, the debug extra `omiSettingsTopic` is used (once).
 */
@Composable
fun SettingsScreen(
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    initialTopic: String? = null,
    onOpenChat: () -> Unit = {},
    onOpenConversation: ((String) -> Unit)? = null,
) {
    val settings = LocalSettingsStore.current
    val developer = LocalDeveloperStore.current
    val preferences = LocalPreferences.current
    val context = LocalContext.current
    val appVersion = remember { runCatching { context.packageManager.getPackageInfo(context.packageName, 0).versionName }.getOrNull().orEmpty() }
    val topic = remember { initialTopic ?: DebugLaunch.string("omiSettingsTopic")?.also { DebugLaunch.values = DebugLaunch.values - "omiSettingsTopic" } }
    // "search:<text>" opens Settings with that search typed (headless QA of the search).
    var isSearching by rememberSaveable { mutableStateOf(topic?.startsWith("search:") == true) }
    var searchText by rememberSaveable { mutableStateOf(topic?.takeIf { it.startsWith("search:") }?.removePrefix("search:").orEmpty()) }
    val path = rememberNavPath<SettingsRoute>()
    LaunchedEffect(Unit) {
        if (topic != null && !topic.startsWith("search:")) SettingsRoute.path(topic).forEach(path::push)
    }
    LaunchedEffect(Unit) { settings.loadSubscription() }
    LaunchedEffect(Unit) { settings.loadProfile() }
    LaunchedEffect(Unit) { if (settings.people.isEmpty()) settings.loadPeople() }
    val capabilities = com.friend.ios.service.LocalCapabilitiesStore.current
    LaunchedEffect(Unit) { capabilities.load() }
    // Reminders (reminders.refresh()) is dropped on Android.
    val health = com.friend.ios.service.LocalAppleHealthStore.current
    LaunchedEffect(Unit) { health.load() }

    val navigator = remember(path) { SettingsNavigator(path, onDismiss, onOpenChat, onOpenConversation) }
    CompositionLocalProvider(LocalSettingsNavigator provides navigator) {
        OmiNavigationStack(
            path,
            // The sheet reaches under the status bar on Android; iOS starts it below the safe area.
            modifier.statusBarsPadding(),
            root = {
                SettingsPage(
                    title = null,
                    onBack = onDismiss,
                    leadingSymbol = "xmark",
                    scrollsUnderBar = true,
                    trailing = {
                        if (!isSearching) GlassCircleButton("magnifyingglass", contentDescription = L("nativeSearchSettings")) { isSearching = true }
                    },
                ) {
                    val appearance = AppearanceMode.from(settings.appearanceMode).raw
                    val scroll = rememberScrollState()
                    // `-omiSettingsScroll bottom` (Debug): scrolls to the end of the list for screenshots.
                    LaunchedEffect(Unit) {
                        if (DebugLaunch.string("omiSettingsScroll") == "bottom") {
                            delay(1_500)
                            scroll.animateScrollTo(scroll.maxValue)
                        }
                    }
                    OmiFlatList(contentPadding = PaddingValues(top = SettingsMetrics.navBarHeight + DS.Spacing.xs, bottom = DS.Spacing.section), scrollState = scroll) {
                        if (isSearching) {
                            section {
                                plainRow {
                                    SettingsSearchField(searchText, { searchText = it }, onCancel = {
                                        searchText = ""
                                        isSearching = false
                                    })
                                }
                            }
                            if (searchText.isNotBlank()) {
                                section {
                                    settingsSearchResults(searchText) { found ->
                                        searchText = ""
                                        isSearching = false
                                        path.popToRoot()
                                        SettingsRoute.path(found.rawValue).forEach(path::push)
                                    }
                                }
                            }
                        } else {
                            // The profile and the four tiles, on the page itself.
                            section {
                                plainRow {
                                    SettingsProfileHeader(
                                        onOpenAccount = { path.push(SettingsRoute.Topic(SettingsTopic.Account)) },
                                        onUpgrade = { SettingsRoute.path(SettingsTopic.PlanUsage.rawValue).forEach(path::push) },
                                    )
                                }
                                plainRow {
                                    SettingsHubTiles { tile ->
                                        SettingsRoute.path(tile.rawValue).forEach(path::push)
                                    }
                                }
                            }
                            // Everything else in one flat list; the rarely used ones under "More".
                            section {
                                topicRow(SettingsTopic.Listening, path)
                                topicRow(SettingsTopic.Memory, path)
                                topicRow(SettingsTopic.Assistant, path)
                                topicRow(SettingsTopic.Notifications, path)
                                topicRow(SettingsTopic.Privacy, path)
                                topicRow(SettingsTopic.Appearance, path, valueKey = appearance)
                                topicRow(SettingsTopic.ConnectAI, path)
                                topicRow(SettingsTopic.Help, path)
                            }
                            section(
                                header = null,
                                headerContent = { OmiSectionLabel(L("nativeSettingsMore")) },
                                footerContent = {
                                    Text(
                                        "Omi $appVersion",
                                        style = DS.Typography.caption,
                                        color = DS.Palette.inkSecondary,
                                        textAlign = TextAlign.Center,
                                        modifier = Modifier.fillMaxWidth().padding(top = DS.Spacing.lg),
                                    )
                                },
                            ) {
                                topicRow(SettingsTopic.PhoneCalls, path)
                                if (developer.isDeveloperMode) topicRow(SettingsTopic.Developer, path)
                            }
                        }
                    }
                }
            },
            destination = { route -> SettingsDestination(route) },
        )
    }
}

/** A topic row of the root list: glyph, title, the current value, the chevron. */
@Composable
private fun com.friend.ios.features.components.OmiSectionBuilder.topicRow(topic: SettingsTopic, path: NavPath<SettingsRoute>, valueKey: String? = null) {
    row(key = topic.rawValue, onClick = { path.push(SettingsRoute.Topic(topic)) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
        SettingsRowLabel(topic.title(), topic.systemImage, value = valueKey?.let { AppearanceScreenTitle(it) })
    }
}

/** What a settings screen uses to move in the Settings stack (`NavigationLink(value:)`, `dismiss`). */
class SettingsNavigator(
    val path: NavPath<SettingsRoute>,
    /** Closes Settings. */
    val dismiss: () -> Unit,
    /** Opens the chat (an app page's "Chat with..."). */
    val openChat: () -> Unit,
    /** A person's conversation was tapped: the shell closes Settings and opens it. */
    val openConversation: ((String) -> Unit)?,
) {
    fun push(topic: SettingsTopic) = path.push(SettingsRoute.Topic(topic))
    fun push(route: SettingsRoute) = path.push(route)
    fun pop() = path.pop()
}

val LocalSettingsNavigator = staticCompositionLocalOf<SettingsNavigator> { error("SettingsNavigator not provided") }

/** One entry of the Settings stack: a topic, an app's page or a person's page. */
sealed interface SettingsRoute {
    data class Topic(val topic: SettingsTopic) : SettingsRoute
    /** `browseApps/app:<id>`. */
    data class App(val id: String) : SettingsRoute
    /** `voices/person:<id>` (`PersonLink`). */
    data class Person(val id: String) : SettingsRoute
    /** Privacy & data > Which apps see what. */
    data object AppAccess : SettingsRoute
    /** Apps & integrations > a connected task app's settings (`TaskAppSettingsScreen`). */
    data class TaskApp(val id: String) : SettingsRoute
    /** Developer > API keys ("dev") or MCP keys ("mcp"). */
    data class DeveloperKeys(val kind: String) : SettingsRoute
    /** Phone calls > Get started: your number as caller ID (`phoneCalls/phoneSetup`), and-calls. */
    data object PhoneNumberSetup : SettingsRoute

    companion object {
        /** The stack for an `initialTopic` (see [SettingsScreen]). */
        fun path(raw: String): List<SettingsRoute> {
            val parts = raw.split("/").filter { it.isNotEmpty() }
            val first = parts.firstOrNull() ?: return emptyList()
            val routes = SettingsTopic.path(first).map<SettingsTopic, SettingsRoute>(::Topic).toMutableList()
            for (part in parts.drop(1)) {
                when {
                    part.startsWith("app:") -> routes += App(part.removePrefix("app:"))
                    part.startsWith("person:") -> routes += Person(part.removePrefix("person:"))
                    part == "phoneSetup" -> routes += PhoneNumberSetup // and-calls
                    else -> SettingsTopic.from(part)?.let { routes += Topic(it) }
                }
            }
            return routes
        }
    }
}

enum class SettingsTopic(val rawValue: String) {
    Account("account"), Devices("devices"), Listening("listening"), Voices("voices"), Memory("memory"),
    Assistant("assistant"), Apps("apps"), ConnectAI("connectAI"), PhoneCalls("phoneCalls"),
    Appearance("appearance"), Notifications("notifications"), Privacy("privacy"), Help("help"), Developer("developer"),
    /** Pushed screens a link or the search can open directly. */
    PlanUsage("planUsage"), Referral("referral"), BrowseApps("browseApps"),
    /** Deeper screens, reached through their parent ("listening/vocabulary"). */
    Vocabulary("vocabulary"), ListeningAdvanced("listeningAdvanced"), VoicePicker("voicePicker"), ImportHistory("importHistory"),
    WhatsNew("whatsNew"), AppleHealth("appleHealth"), Webhooks("webhooks"), Logs("logs");

    @Composable
    fun title(): String = when (this) {
        Account -> L("account")
        Devices -> L("nativeSettingsMyOmi")
        Listening -> L("nativeSettingsListening")
        Voices -> L("nativeSettingsVoices")
        Memory -> L("nativeSettingsMemory")
        Assistant -> L("nativeAssistant")
        Apps -> L("nativeSettingsApps")
        ConnectAI -> L("nativeConnectAI")
        PhoneCalls -> L("nativeSettingsPhoneCalls")
        Appearance -> L("appearance")
        Notifications -> L("notifications")
        Privacy -> L("nativeSettingsPrivacy")
        Help -> L("nativeSettingsHelp")
        Developer -> L("nativeDeveloper")
        PlanUsage -> L("nativeSettingsPlanUsage")
        Referral -> L("nativeSettingsInviteFriends")
        BrowseApps -> L("nativeBrowseApps")
        Vocabulary -> L("nativeSettingsVocabulary")
        ListeningAdvanced -> L("nativeSettingsAdvanced")
        VoicePicker -> L("nativeAssistantVoice")
        ImportHistory -> L("nativeSettingsImportHistory")
        WhatsNew -> L("whatsNew")
        // Health Connect is Android's Apple Health (docs/PLAN.md platform mapping).
        AppleHealth -> "Health Connect"
        Webhooks -> L("nativeDevWebhooks")
        Logs -> L("nativeDevLogs")
    }

    val systemImage: String
        get() = when (this) {
            Account -> "person.crop.circle"
            Devices -> "circle.circle"
            Listening -> "waveform"
            Voices -> "person.2"
            Memory -> "brain.head.profile"
            Assistant -> "sparkles"
            Apps -> "square.grid.2x2"
            ConnectAI -> "link"
            PhoneCalls -> "phone"
            Appearance -> "circle.lefthalf.filled"
            Notifications -> "bell"
            Privacy -> "hand.raised"
            Help -> "questionmark.circle"
            Developer -> "chevron.left.forwardslash.chevron.right"
            PlanUsage -> "chart.bar"
            Referral -> "gift"
            BrowseApps -> "magnifyingglass"
            Vocabulary -> "text.book.closed"
            ListeningAdvanced -> "slider.horizontal.3"
            VoicePicker -> "person.wave.2"
            ImportHistory -> "square.and.arrow.down"
            WhatsNew -> "gift"
            AppleHealth -> "heart"
            Webhooks -> "arrow.triangle.branch"
            Logs -> "list.bullet.rectangle"
        }

    companion object {
        fun from(raw: String): SettingsTopic? = entries.firstOrNull { it.rawValue == raw }

        /**
         * The stack that shows `raw`: a pushed screen opens on top of its parent. Earlier names
         * ("capture", "capabilities", ...) still work for old links and QA scripts.
         */
        fun path(raw: String): List<SettingsTopic> {
            val aliases = mapOf(
                "capture" to Listening, "voiceAndPeople" to Voices, "memories" to Memory, "capabilities" to Apps,
                "notificationsAndDisplay" to Notifications, "usage" to PlanUsage, "fairUse" to PlanUsage,
            )
            val topic = from(raw) ?: aliases[raw] ?: return emptyList()
            return when (topic) {
                PlanUsage, Referral -> listOf(Account, topic)
                BrowseApps -> listOf(Apps, topic)
                Vocabulary, ListeningAdvanced -> listOf(Listening, topic)
                VoicePicker -> listOf(Assistant, topic)
                ImportHistory -> listOf(Memory, topic)
                WhatsNew -> listOf(Help, topic)
                AppleHealth -> listOf(Apps, topic)
                Webhooks, Logs -> listOf(Developer, topic)
                else -> listOf(topic)
            }
        }
    }
}

/** `destination(_:)`: the screen for one entry of the stack. */
@Composable
private fun SettingsDestination(route: SettingsRoute) {
    val navigator = LocalSettingsNavigator.current
    val session = LocalSessionStore.current
    val back = { navigator.pop() }
    when (route) {
        is SettingsRoute.App -> AppDetailScreen(route.id, back)
        is SettingsRoute.Person -> PersonDetailScreen(route.id, back)
        SettingsRoute.AppAccess -> AppAccessScreen(back)
        is SettingsRoute.TaskApp -> TaskAppSettingsScreen(route.id, back)
        is SettingsRoute.DeveloperKeys -> DeveloperKeysScreen(route.kind, back)
        SettingsRoute.PhoneNumberSetup -> PhoneNumberSetupScreen(back) // and-calls
        is SettingsRoute.Topic -> when (route.topic) {
            SettingsTopic.Account -> AccountScreen(back)
            SettingsTopic.Appearance -> AppearanceScreen(back)
            SettingsTopic.Notifications -> NotificationsScreen(back)
            SettingsTopic.Privacy -> PrivacyScreen(back)
            SettingsTopic.Help -> HelpScreen(back) {
                navigator.dismiss()
                session.replayIntroduction()
            }
            SettingsTopic.WhatsNew -> WhatsNewScreen(back)
            SettingsTopic.Assistant -> AssistantScreen(back)
            SettingsTopic.VoicePicker -> VoicePickerScreen(back)
            // Listening, Voices & people, Memory.
            SettingsTopic.Listening -> CaptureSettingsScreen(back)
            SettingsTopic.Vocabulary -> VocabularyScreen(back)
            SettingsTopic.ListeningAdvanced -> ListeningAdvancedScreen(back)
            SettingsTopic.Voices -> PeopleScreen(back)
            SettingsTopic.Memory -> KnowledgeSummaryScreen(back)
            SettingsTopic.ImportHistory -> ImportScreen(back)
            // Apps, Connect your AI, Phone calls, Plan & usage, Developer.
            SettingsTopic.Apps -> CapabilitiesScreen(back)
            SettingsTopic.BrowseApps -> AppsBrowserScreen(back)
            SettingsTopic.AppleHealth -> AppleHealthScreen(back)
            SettingsTopic.ConnectAI -> ConnectAIScreen(back)
            SettingsTopic.PhoneCalls -> PhoneScreen(back)
            SettingsTopic.PlanUsage -> PlanUsageScreen(back)
            SettingsTopic.Referral -> ReferralScreen(back)
            SettingsTopic.Developer -> DeveloperScreen(back)
            SettingsTopic.Webhooks -> WebhooksScreen(back)
            SettingsTopic.Logs -> DeveloperLogsScreen(back)
            // My Omi (and-device), with the button lessons as `tutorial` (DeviceScreen's default).
            SettingsTopic.Devices -> com.friend.ios.features.device.DeviceScreen(onBack = back)
        }
    }
}

/** A bare page with only its bar (a step another screen supplies, such as People's voice screen). */
@Composable
internal fun SettingsPlaceholderScreen(title: String, onBack: () -> Unit) {
    SettingsPage(title, onBack) { Box(Modifier) }
}
