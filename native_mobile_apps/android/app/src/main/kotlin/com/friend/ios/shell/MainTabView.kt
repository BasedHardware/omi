package com.friend.ios.shell

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import com.friend.ios.DebugLaunchOptions
import com.friend.ios.design.CalmBackground
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.TextStyles
import com.friend.ios.design.bold
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.memory.MemoryScreen
import com.friend.ios.features.today.TodayScreen
import com.friend.ios.features.agent.ChatScreen
import com.friend.ios.features.agent.HandOverSheet
import com.friend.ios.features.tasks.TaskDetailSheet
import com.friend.ios.features.today.TaskLaterUndo
import com.friend.ios.features.today.TaskLaterUndoToast
import com.friend.ios.core.models.ActionItem
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.features.agent.ChatScreenRequest
import com.friend.ios.features.agent.ChatHeaderActions
import com.friend.ios.features.settings.SettingsScreen
import com.friend.ios.design.NavPath
import com.friend.ios.design.OmiNavigationStack
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.rememberNavPath
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch

/**
 * Port of `MainTabView.swift`: device pill + round buttons, the big "Home  Chat  Memories"
 * switcher, the pages, and the bottom bar (Ask Omi + record) on Home and Memories.
 */
enum class Tab(val raw: String) {
    Home("home"), Chat("chat"), Memory("memory");

    @Composable
    fun title(): String = when (this) {
        Home -> L("home")
        Chat -> L("nativeTabChat")
        Memory -> L("memories")
    }

    companion object {
        fun from(debugName: String?): Tab? {
            if (debugName == null) return null
            // Old names: Tasks moved onto Home.
            val name = if (debugName in listOf("today", "conversations", "tasks")) "home" else debugName
            return entries.firstOrNull { it.raw == name }
        }
    }
}

@Composable
fun MainTabView() {
    val path = rememberNavPath<Route>()
    var showsSettings by remember { mutableStateOf(DebugLaunchOptions.current.showsSettings) }
    // Deep links (system): Settings at a topic (`h.omi.me/unlimited`) and an app's page (`h.omi.me/apps/<id>`).
    var settingsTopic by remember { mutableStateOf<String?>(null) }
    // The Omi (and-device): `-omiShowDevice YES` opens My Omi; the paired Omi connects and waiting
    // recordings upload once the shell is up (`MainTabView.swift` `.task`).
    var showsDevice by remember { mutableStateOf(com.friend.ios.features.components.DebugLaunch.flag("omiShowDevice")) }
    val devices = com.friend.ios.service.LocalDeviceStore.current
    val sync = com.friend.ios.service.LocalSyncStore.current
    LaunchedEffect(Unit) {
        devices.start()
        sync.start()
    }
    // "Ask Omi" from a pushed screen (the conversation page) goes to the Chat tab at the root.
    var chatOpens by remember { mutableStateOf(0) }
    // Phone calls (and-calls): banner + call screen while a call runs outside Settings.
    com.friend.ios.features.settings.OngoingCallPresenter {
    Box(Modifier.fillMaxSize()) {
        OmiNavigationStack(path, root = {
            Tabs(
                path, onOpenSettings = { showsSettings = true }, onOpenDevice = { showsDevice = true }, chatOpens = chatOpens,
                onLinkOpens = { showsSettings = false; settingsTopic = null; showsDevice = false },
                onLinkSheet = { destination ->
                    when (destination) {
                        com.friend.ios.system.DeepLinkRouter.Destination.Account -> { settingsTopic = "account"; showsSettings = true }
                        // The app page lives in the Settings stack (it navigates there: reviews, setup, chat).
                        is com.friend.ios.system.DeepLinkRouter.Destination.App -> { settingsTopic = "browseApps/app:${destination.id}"; showsSettings = true }
                        else -> Unit
                    }
                },
            )
        }) { route ->
            RouteDestination(route, onBack = { path.pop() }, push = { path.push(it) }, onAskOmi = {
                path.popToRoot()
                chatOpens += 1
            })
        }
        // Above every screen, clear of the Omi bar: a delete from the detail page is undone on Home.
        com.friend.ios.features.components.UndoDeleteToast(
            Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = DS.Size.omiBarHeight + DS.Spacing.lg),
        )
    }
    } // OngoingCallPresenter (and-calls)
    // `-omiOpenConversation <id>` pushes that conversation once Home has loaded it (`DebugHooks.swift`).
    val conversations = LocalConversationsStore.current
    LaunchedEffect(conversations.conversations.size) {
        val id = com.friend.ios.features.components.DebugLaunch.string("omiOpenConversation") ?: return@LaunchedEffect
        if (path.isEmpty && conversations.conversations.any { it.id == id }) path.push(Route.Conversation(id))
    }
    if (showsSettings) {
        OmiSheet(onDismiss = { showsSettings = false; settingsTopic = null }) {
            androidx.compose.runtime.key(settingsTopic) { SettingsScreen(onDismiss = { showsSettings = false; settingsTopic = null }, initialTopic = settingsTopic) }
        }
    }
    if (showsDevice) {
        OmiSheet(onDismiss = { showsDevice = false }) { com.friend.ios.features.device.DeviceScreen(onDone = { showsDevice = false }) }
    }
    // What's new after an update, then pending announcements (one sheet at a time).
    com.friend.ios.features.settings.WhatsNewPresenter("${com.friend.ios.BuildConfig.VERSION_NAME}+${com.friend.ios.BuildConfig.VERSION_CODE}")
}

@Composable
private fun Tabs(
    path: NavPath<Route>,
    onOpenSettings: () -> Unit,
    onOpenDevice: () -> Unit,
    chatOpens: Int = 0,
    onLinkOpens: () -> Unit = {},
    onLinkSheet: (com.friend.ios.system.DeepLinkRouter.Destination) -> Unit = {},
) {
    /** A new value reaches the Chat page once (dictation, a draft, the header's search or filter). */
    var chatRequest by remember { mutableStateOf<ChatScreenRequest?>(null) }
    val initial = Tab.from(DebugLaunchOptions.current.initialTab) ?: Tab.Home
    val pager = rememberPagerState(initialPage = initial.ordinal) { Tab.entries.size }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val tab = Tab.entries[pager.targetPage]
    fun select(item: Tab) = scope.launch { pager.animateScrollToPage(item.ordinal, animationSpec = DS.Motion.snappy()) }
    LaunchedEffect(pager) { snapshotFlow { pager.currentPage }.collect { haptics.selection() } }
    LaunchedEffect(chatOpens) { if (chatOpens > 0) select(Tab.Chat) }
    // Home task card: the task's detail and Omi's hand-over (`MainTabView+Sheets.swift`).
    var handOverTask by remember { mutableStateOf<ActionItem?>(null) }
    var detailTask by remember { mutableStateOf<ActionItem?>(null) }
    val laterUndo = remember { TaskLaterUndo() }
    // Capture (and-capture): long press on record (`-omiShowRecordWith YES` opens it).
    var showsRecordWith by remember { mutableStateOf(com.friend.ios.features.components.DebugLaunch.flag("omiShowRecordWith")) }
    val tasks = LocalTasksStore.current
    val conversations = LocalConversationsStore.current
    fun conversationTitle(task: ActionItem): String? =
        task.conversationID?.let { id -> conversations.conversations.firstOrNull { it.id == id }?.title }
    // Deep links (system): `openPendingLink()` closes what is open, then shows the destination.
    var showsNewTask by remember { mutableStateOf(false) }
    val capture = com.friend.ios.service.LocalCaptureStore.current
    com.friend.ios.system.OpenPendingLinks { destination ->
        onLinkOpens()
        handOverTask = null
        detailTask = null
        showsNewTask = false
        path.popToRoot()
        when (destination) {
            is com.friend.ios.system.DeepLinkRouter.Destination.Push -> { select(Tab.Home); path.push(destination.route) }
            is com.friend.ios.system.DeepLinkRouter.Destination.SelectTab -> select(destination.tab)
            is com.friend.ios.system.DeepLinkRouter.Destination.HandOver -> handOverTask = destination.task
            is com.friend.ios.system.DeepLinkRouter.Destination.TaskDetail -> detailTask = destination.task
            com.friend.ios.system.DeepLinkRouter.Destination.Chat -> select(Tab.Chat)
            is com.friend.ios.system.DeepLinkRouter.Destination.ChatDraft -> { chatRequest = ChatScreenRequest.draft(destination.text); select(Tab.Chat) }
            com.friend.ios.system.DeepLinkRouter.Destination.NewTask -> { select(Tab.Home); showsNewTask = true }
            com.friend.ios.system.DeepLinkRouter.Destination.Device -> onOpenDevice()
            com.friend.ios.system.DeepLinkRouter.Destination.Record -> scope.launch { if (!capture.isLive) capture.startPhone() }
            com.friend.ios.system.DeepLinkRouter.Destination.Account, is com.friend.ios.system.DeepLinkRouter.Destination.App -> onLinkSheet(destination)
        }
    }
    if (showsNewTask) {
        OmiSheet(onDismiss = { showsNewTask = false }, detents = setOf(com.friend.ios.design.Detent.Medium, com.friend.ios.design.Detent.Large)) {
            com.friend.ios.features.tasks.TaskFormSheet(null, onDismiss = { showsNewTask = false }, onOpenConversation = { path.push(Route.Conversation(it)) })
        }
    }

    Box(Modifier.fillMaxSize()) {
        CalmBackground()
        Column(Modifier.fillMaxSize().statusBarsPadding()) {
            Header(
                tab,
                onSearch = { path.push(Route.Search) },
                onSettings = onOpenSettings,
                onChatRequest = { chatRequest = it },
                onDevice = onOpenDevice,
            )
            Switcher(tab, onSelect = ::select)
            HorizontalPager(pager, Modifier.weight(1f), beyondViewportPageCount = 1, key = { it }) { page ->
                val inset = OmiBottomBarHeight + with(LocalDensity.current) { 0.dp }
                val openConversation: (String) -> Unit = { path.push(Route.Conversation(it)) }
                when (Tab.entries[page]) {
                    Tab.Home -> TodayScreen(
                        onOpenConversation = openConversation,
                        onOpenAllTasks = { path.push(Route.AllTasks) },
                        onOpenSearch = { path.push(Route.Search) },
                        onOpenRecap = { path.push(Route.Recap(it)) },
                        onAskOmi = { select(Tab.Chat) },
                        bottomInset = inset,
                        onOpenTask = { detailTask = it },
                        onHandOver = { handOverTask = it },
                        onOpenRun = { id -> handOverTask = tasks.tasks.firstOrNull { it.id == id } },
                        laterUndo = laterUndo,
                    )
                    Tab.Chat -> ChatScreen(onOpenConversation = openConversation, request = chatRequest, onUpgrade = onOpenSettings)
                    Tab.Memory -> MemoryScreen(onOpenConversation = openConversation, bottomInset = inset, onOpenGraph = { path.push(Route.MemoryGraph) })
                }
            }
        }
        // Over the pages, not beside them: lists scroll on under the bar and fade out there.
        AnimatedVisibility(tab != Tab.Chat, Modifier.align(Alignment.BottomCenter), enter = fadeIn(DS.Motion.standard<Float>()), exit = fadeOut(DS.Motion.standard<Float>())) {
            BottomBar(
                onAsk = { select(Tab.Chat) },
                onDictate = {
                    chatRequest = ChatScreenRequest.dictate()
                    select(Tab.Chat)
                },
                onRecordWith = { showsRecordWith = true }, // Capture (and-capture)
            )
        }
        // A card swiped to Later: "Moved to Later" with Undo, just above the Omi bar.
        if (tab == Tab.Home) {
            TaskLaterUndoToast(
                laterUndo,
                Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = OmiBottomBarHeight + DS.Spacing.sm),
            )
        }
    }
    detailTask?.let { task ->
        TaskDetailSheet(
            task, onDismiss = { detailTask = null },
            onOpenConversation = { path.push(Route.Conversation(it)) },
            onHandOver = { handOverTask = it },
        )
    }
    handOverTask?.let { task ->
        OmiSheet(onDismiss = { handOverTask = null }) { HandOverSheet(task, conversationTitle(task), onDismiss = { handOverTask = null }) }
    }
    if (showsRecordWith) RecordWithSheet(onDismiss = { showsRecordWith = false }) // Capture (and-capture)
}

@Composable
private fun BottomBar(onAsk: () -> Unit, onDictate: () -> Unit, onRecordWith: () -> Unit) {
    val page = DS.Palette.background
    Box(
        Modifier.fillMaxWidth().drawBehind {
            // Content fades out under the bar instead of colliding with it (56 pt above the bar).
            val top = -56.dp.toPx()
            drawRect(
                Brush.verticalGradient(
                    0f to page.copy(alpha = 0f), 0.35f to page.copy(alpha = 0.75f), 0.62f to page,
                    startY = top, endY = size.height,
                ),
                topLeft = Offset(0f, top),
                size = size.copy(height = size.height - top),
            )
        },
    ) {
        OmiBottomBar(onAsk = onAsk, onDictate = onDictate, onRecordWith = onRecordWith, modifier = Modifier.navigationBarsPadding())
    }
}

@Composable
private fun Header(tab: Tab, onSearch: () -> Unit, onSettings: () -> Unit, onChatRequest: (ChatScreenRequest) -> Unit, onDevice: () -> Unit) {
    HStack(Modifier.padding(horizontal = DS.Spacing.gutter).padding(top = DS.Spacing.xs), spacing = DS.Spacing.sm) {
        DevicePill(Modifier.plainButton(onClick = onDevice))
        Spacer(Modifier.weight(1f))
        // One header for every tab: on Chat its search looks through the thread, and the chat's "..." joins it.
        if (tab == Tab.Chat) {
            ChatHeaderActions(onSearch = { onChatRequest(ChatScreenRequest.search()) }, onFilter = { onChatRequest(ChatScreenRequest.filter(it)) })
        } else {
            CircleIconButton("magnifyingglass", contentDescription = L("search"), onClick = onSearch)
        }
        CircleIconButton("gearshape", contentDescription = L("settings"), onClick = onSettings)
    }
}

/**
 * Omi's word tabs. Long words (German "Erinnerungen") first get a smaller size; at large text
 * sizes the row scrolls sideways instead of breaking words (`ViewThatFits`). The words keep their
 * size on every page, also while the chat's thread is scrolled.
 */
@Composable
private fun Switcher(tab: Tab, onSelect: (Tab) -> Unit) {
    val measurer = rememberTextMeasurer()
    val titles = Tab.entries.map { it.title() }
    BoxWithConstraints(Modifier.fillMaxWidth().padding(top = DS.Spacing.xl, bottom = DS.Spacing.lg)) {
        val density = LocalDensity.current
        val available = with(density) { (maxWidth - DS.Spacing.gutter * 2).toPx() }
        fun width(style: TextStyle) = titles.sumOf { measurer.measure(it, style).size.width } + with(density) { (DS.Spacing.lg * (titles.size - 1)).toPx() }
        val style = when {
            width(DS.Typography.switcher) <= available -> DS.Typography.switcher
            width(TextStyles.title2.bold()) <= available -> TextStyles.title2.bold()
            else -> DS.Typography.switcher
        }
        HStack(
            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = DS.Spacing.gutter),
            spacing = DS.Spacing.lg,
        ) {
            Tab.entries.forEachIndexed { index, item ->
                Text(
                    titles[index],
                    style = style,
                    color = if (tab == item) DS.Palette.ink else DS.Palette.inkTertiary,
                    maxLines = 1,
                    modifier = Modifier.plainButton { onSelect(item) },
                )
            }
        }
    }
}
