package com.friend.ios.features.conversations

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.boundsInParent
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiNavBar
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.AgentTaskStatus
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.FolderLabel
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.components.MoveToFolderSheet
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiToast
import com.friend.ios.features.components.TaskRow
import com.friend.ios.features.components.displayTitle
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.TasksStore
import com.friend.ios.service.stores.canTakeOver
import com.friend.ios.service.stores.loadWorkstreams
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The screen's `@State` (`ConversationDetailScreen.swift`), shared by the page, its menus
 * (`ConversationDetailMenu.kt`) and its sheets.
 */
@Stable
class ConversationDetailState internal constructor(
    val store: ConversationDetailStore,
    internal val conversations: ConversationsStore,
    val scope: CoroutineScope,
    val onBack: () -> Unit,
) {
    enum class Page { Summary, Transcript }

    var page by mutableStateOf(if (DebugLaunch.string("omiConversationPage") == "transcript") Page.Transcript else Page.Summary)
    var renaming by mutableStateOf(false)
    var newTitle by mutableStateOf("")
    var moving by mutableStateOf(false)
    var confirmsShareLink by mutableStateOf(false)
    /** A short confirmation ("Summary copied"), shown for a moment. */
    var notice: String? by mutableStateOf(null)
    var query by mutableStateOf("")
    var cursor by mutableStateOf(0)
    /** The transcript's search field is open (magnifier above the page, or the "..." menu). */
    var searchesTranscript by mutableStateOf(DebugLaunch.flag("omiTranscriptSearch"))
    /** Summary template, calendar, recordings, SMS, test prompt (`DetailExtras.kt`). */
    val extras = DetailExtras()

    internal var share: (ShareRequest) -> Unit = {}
    internal var haptics: DSHaptics? = null
    internal var askOmi: () -> Unit = {}
    internal var strings = Strings("", "", "")

    internal data class Strings(val urlNotShared: String, val preparingAudio: String, val audioDownloadFailed: String)

    /** The list's copy wins, so a rename or a star shows here at once. */
    val conversation: Conversation get() = conversations.current(store.conversation)

    fun show(message: String) {
        notice = message
        scope.launch {
            delay(2_000)
            if (notice == message) notice = null
        }
    }
}

/**
 * Port of `ConversationDetailScreen.swift`: Omi's conversation page: title and date, then Summary |
 * Transcript side by side (swipe or tap the labels). The summary page leads with what came out of
 * it: the summary in a few sentences, the action items, and Ask / Check / Send to my AI; everything
 * else waits behind "More details". The share button and the "..." menu hold every action
 * (`ConversationDetailMenu.kt`). `onAskOmi` opens the chat; the screen has already pointed it at
 * this conversation. `EdgeSwipeBack.swift` has no counterpart: Android's back gesture is the
 * system's and never competes with the pager.
 */
@Composable
fun ConversationDetailScreen(
    store: ConversationDetailStore,
    onBack: () -> Unit,
    onHandOver: (ActionItem) -> Unit,
    onAskOmi: () -> Unit = {},
    onOpenConversation: (Conversation) -> Unit = {},
) {
    val conversations = LocalConversationsStore.current
    val tasks = LocalTasksStore.current
    val agent = LocalAgentStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val state = remember(store) { ConversationDetailState(store, conversations, scope, onBack) }
    state.share = rememberShareSheet()
    state.haptics = haptics
    state.askOmi = rememberAskOmi(state, onAskOmi)
    state.strings = ConversationDetailState.Strings(L("conversationUrlNotShared"), L("preparingAudio"), L("audioDownloadFailed"))
    val sendToMyAI = rememberSendToMyAI(state)
    val conversation = state.conversation
    val pager = rememberPagerState(initialPage = state.page.ordinal) { 2 }
    val anchors = remember { TranscriptAnchors() }

    LaunchedEffect(store) {
        store.load()
        conversations.remember(store.conversation)
    }
    // The folder name needs the folders (the screen can open straight from search or a link).
    LaunchedEffect(Unit) { if (conversations.folders.isEmpty()) conversations.loadFolders() }
    LaunchedEffect(Unit) { if (tasks.phase == TasksStore.Phase.Idle) tasks.load() }
    LaunchedEffect(tasks.tasks.size) { agent.loadWorkstreams(tasks.tasks) }
    LaunchedEffect(state.page) { if (pager.currentPage != state.page.ordinal) pager.animateScrollToPage(state.page.ordinal, animationSpec = DS.Motion.standard()) }
    LaunchedEffect(pager) { snapshotFlow { pager.settledPage }.collect { state.page = ConversationDetailState.Page.entries[it] } }
    LaunchedEffect(state.extras.notice) { state.extras.notice?.let(state::show) }
    LaunchedEffect(Unit) { swipeForDebugging(state) }

    Box(Modifier.fillMaxSize().background(DS.Palette.background)) {
        Column(Modifier.fillMaxSize().statusBarsPadding()) {
            // The system bar of iOS 26: back in a glass circle, Share and "..." in one glass capsule.
            Box(Modifier.fillMaxWidth().height(56.dp).padding(horizontal = DS.Spacing.lg)) {
                val back = L("back")
                com.friend.ios.features.settings.GlassCircleButton("chevron.left", Modifier.align(Alignment.CenterStart).semantics { contentDescription = back }, onClick = onBack)
                Row(Modifier.align(Alignment.CenterEnd).glassCapsule().padding(horizontal = DS.Spacing.xs), verticalAlignment = Alignment.CenterVertically) {
                    OmiMenu(shareMenu(state), contentDescription = L("share")) { Toolbar("square.and.arrow.up") }
                    OmiMenu(detailMenu(state), contentDescription = L("moreOptions")) { Toolbar("ellipsis") }
                }
            }
            Column(Modifier.padding(horizontal = DS.Spacing.gutter), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                Header(state)
                ProcessingStrip(store, conversation)
                Tabs(state, pager.currentPage + pager.currentPageOffsetFraction)
            }
            // Summary and Transcript side by side in one pager: swipe between them and the
            // underline follows the finger; each page scrolls vertically on its own.
            HorizontalPager(pager, Modifier.weight(1f), beyondViewportPageCount = 1) { page ->
                if (page == 0) SummaryPage(state, onHandOver, sendToMyAI) else TranscriptPage(state, anchors)
            }
        }
        AnimatedVisibility(
            state.notice != null,
            Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = DS.Spacing.lg),
            enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard()),
            exit = slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()),
        ) {
            OmiToast(state.notice ?: "", "checkmark")
        }
    }

    if (state.renaming) {
        OmiAlert(
            L("renameConversation"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("save")) { scope.launch { conversations.rename(conversation.id, state.newTitle) } },
            ),
            onDismiss = { state.renaming = false },
            textField = L("conversationTitle") to state.newTitle,
            onTextChange = { state.newTitle = it },
        )
    }
    if (state.confirmsShareLink) {
        OmiConfirmationDialog(
            L("shareConversationQuestion"),
            listOf(DialogButton(L("share")) { scope.launch { state.shareLink() } }, DialogButton(L("cancel"), DialogButton.Role.Cancel)),
            onDismiss = { state.confirmsShareLink = false },
            message = L("anyoneWithLinkCanView"),
        )
    }
    if (state.moving) MoveToFolderSheet(listOf(conversation.id), onDismiss = { state.moving = false })
    DetailExtrasPresenter(state.extras, store, conversation, onOpenConversation)
}

@Composable
private fun Toolbar(systemImage: String) {
    Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
        SFImage(systemImage, size = 19.sp, weight = FontWeight.Medium, tint = DS.Palette.ink)
    }
}

/** The emoji on its own, the title, and one quiet line: when, how long, folder, starred, shared. */
@Composable
private fun Header(state: ConversationDetailState) {
    val conversations = LocalConversationsStore.current
    val conversation = state.conversation
    Column(Modifier.padding(top = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            conversation.emoji?.let { Text(it, style = TextStyles.system(22)) }
            Text(conversation.displayTitle(), style = DS.Typography.title, color = DS.Palette.ink, maxLines = 3)
        }
        HStack(spacing = DS.Spacing.sm) {
            Text(`when`(conversation), style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1)
            conversations.folder(conversation.folderID)?.let { FolderLabel(it) }
            if (conversation.isStarred) SFImage("star.fill", size = 13.sp, tint = DS.Palette.inkSecondary, contentDescription = L("starred"))
            if (conversation.visibility != Conversation.Visibility.Private) {
                SFImage("globe", size = 13.sp, tint = DS.Palette.inkSecondary, contentDescription = L("nativeShared"))
            }
        }
    }
}

/** "Wed, Oct 7, 3:18 PM · 38m". */
private fun `when`(conversation: Conversation): String {
    val date = DetailDates.weekdayDateTime(conversation.date)
    return conversation.duration?.let { "$date · ${Formatting.length(it)}" } ?: date
}

@Composable
private fun Tabs(state: ConversationDetailState, progress: Float) {
    val haptics = rememberHaptics()
    val frames = remember { mutableStateMapOf<ConversationDetailState.Page, Pair<Float, Float>>() }
    val hairline = DS.Palette.hairline
    val ink = DS.Palette.ink
    val density = LocalDensity.current
    Box(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xl)) {
            listOf(ConversationDetailState.Page.Summary to L("summary"), ConversationDetailState.Page.Transcript to L("transcript")).forEach { (page, title) ->
                // How selected this label is right now (follows the swipe).
                val weight = if (page == ConversationDetailState.Page.Summary) 1 - progress else progress
                Box(
                    Modifier
                        .onGloballyPositioned { frames[page] = it.boundsInParent().left to it.boundsInParent().width }
                        .plainButton {
                            haptics.selection()
                            state.page = page
                        }
                        .padding(bottom = DS.Spacing.sm),
                ) {
                    Text(title, style = TextStyles.subheadline.semibold(), color = DS.Palette.inkTertiary)
                    Text(title, style = TextStyles.subheadline.semibold(), color = DS.Palette.ink, modifier = Modifier.graphicsLayer { alpha = weight.coerceIn(0f, 1f) })
                }
            }
            Spacer(Modifier.weight(1f))
            // Search lives with the transcript: a small magnifier, the field only when asked for.
            AnimatedVisibility(
                state.page == ConversationDetailState.Page.Transcript && state.store.detail?.transcript?.isNotEmpty() == true,
                enter = fadeIn(DS.Motion.standard()),
                exit = fadeOut(DS.Motion.standard()),
            ) {
                Box(
                    Modifier
                        .size(32.dp, 24.dp)
                        .plainButton {
                            haptics.selection()
                            state.searchesTranscript = !state.searchesTranscript
                        }
                        .padding(bottom = 0.dp),
                    contentAlignment = Alignment.TopCenter,
                ) {
                    SFImage(
                        "magnifyingglass", size = 15.sp, tint = if (state.searchesTranscript) DS.Palette.ink else DS.Palette.inkSecondary,
                        contentDescription = L("searchTranscriptOrSummary"),
                    )
                }
            }
        }
        Box(Modifier.align(Alignment.BottomStart).fillMaxWidth().height(DS.Stroke.hairline).background(hairline))
        // The underline slides with the pages: between the two labels in step with the swipe.
        val summary = frames[ConversationDetailState.Page.Summary]
        val transcript = frames[ConversationDetailState.Page.Transcript]
        if (summary != null && transcript != null) {
            val p = progress.coerceIn(0f, 1f)
            val x = summary.first + (transcript.first - summary.first) * p
            val width = summary.second + (transcript.second - summary.second) * p
            with(density) {
                Box(Modifier.align(Alignment.BottomStart).offset(x = x.toDp()).width(width.toDp()).height(2.dp).background(ink))
            }
        }
    }
}

/**
 * What came out of it: the summary in a few sentences, the action items, three ways to use it, and
 * everything else behind "More details".
 */
@Composable
private fun SummaryPage(state: ConversationDetailState, onHandOver: (ActionItem) -> Unit, sendToMyAI: () -> Unit) {
    val scroll = rememberScrollState()
    var moreDetailsY by remember { mutableFloatStateOf(-1f) }
    // Read here, not in the callback: `L` is composable (iOS's `L` is a plain function).
    val savedMessage = L("nativeSummarySaved")
    LaunchedEffect(Unit) {
        // `-omiMoreDetails YES` opens "More details" and scrolls to it (scripted screenshots).
        if (!DebugLaunch.flag("omiMoreDetails")) return@LaunchedEffect
        delay(2_500)
        if (moreDetailsY >= 0) scroll.animateScrollTo(moreDetailsY.toInt())
    }
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(horizontal = DS.Spacing.gutter)
            .padding(top = DS.Spacing.lg, bottom = DS.Spacing.section)
            .navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl),
    ) {
        ConversationSummaryView(
            state.store,
            state.conversation,
            onRetry = { state.reprocess() },
            onSaved = { state.show(savedMessage) },
        )
        ActionItems(state, onHandOver)
        DetailActions(
            onAsk = { state.askOmi() },
            onCheck = { state.page = ConversationDetailState.Page.Transcript },
            onSend = sendToMyAI,
        )
        MoreDetailsSection(state.store, state.extras, state.conversation, Modifier.onGloballyPositioned { moreDetailsY = it.boundsInParent().top })
    }
}

@Composable
private fun TranscriptPage(state: ConversationDetailState, anchors: TranscriptAnchors) {
    val scroll = rememberScrollState()
    var viewport by remember { mutableStateOf(0f to 0f) }
    val detail = state.store.detail
    // The transcript paragraph holding the current search match.
    val matchLine: Int? = run {
        if (state.page != ConversationDetailState.Page.Transcript || detail == null) return@run null
        val matches = detail.lines(state.query)
        if (matches.isEmpty()) return@run null
        TranscriptView.paragraphID(matches[minOf(state.cursor, matches.size - 1)], detail.transcript)
    }
    LaunchedEffect(matchLine) {
        val line = matchLine ?: return@LaunchedEffect
        delay(50)
        val y = anchors.positions[line] ?: return@LaunchedEffect
        val (top, height) = viewport
        scroll.animateScrollTo((scroll.value + y - top - height / 2).toInt().coerceAtLeast(0), DS.Motion.standard())
    }
    Column(
        Modifier
            .fillMaxSize()
            .onGloballyPositioned { viewport = it.positionInRoot().y to it.size.height.toFloat() }
            .verticalScroll(scroll)
            .padding(horizontal = DS.Spacing.gutter)
            .padding(top = DS.Spacing.lg, bottom = DS.Spacing.section)
            .navigationBarsPadding(),
    ) {
        TranscriptView(
            state.store,
            query = state.query,
            onQueryChange = { state.query = it },
            cursor = state.cursor,
            onCursorChange = { state.cursor = it },
            showsSearch = state.searchesTranscript,
            onShowsSearchChange = { state.searchesTranscript = it },
            onShareAudio = { state.shareAudio() },
            anchors = anchors,
        )
    }
}

/** The action items as plain rows under the summary: check them off, or hand one to Omi. */
@Composable
private fun ActionItems(state: ConversationDetailState, onHandOver: (ActionItem) -> Unit) {
    val tasks = LocalTasksStore.current
    val agent = LocalAgentStore.current
    val scope = rememberCoroutineScope()
    val canonical = tasks.tasks(state.conversation.id)
    val fallback = state.store.detail?.summaryActionItems.orEmpty()
    if (canonical.isEmpty() && fallback.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Text(L("nativeActionItems"), style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary, modifier = Modifier.semantics { heading() })
        if (canonical.isEmpty()) {
            fallback.forEach { text ->
                Row(Modifier.padding(vertical = DS.Spacing.xs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    SFImage("circle", Modifier.padding(top = 1.dp), size = 20.sp, tint = DS.Palette.inkTertiary)
                    Text(text, style = DS.Typography.body, color = DS.Palette.ink)
                }
            }
        } else {
            canonical.forEach { task ->
                val status = AgentTaskStatus.of(task, agent)
                TaskRow(
                    task,
                    agentStatus = status,
                    onToggle = { scope.launch { tasks.setCompleted(task.id, !task.isCompleted) } },
                    // Omi's work opens where it has some; a new hand-over only for what Omi can do digitally.
                    onHandOver = if (status != null || agent.canTakeOver(task)) ({ onHandOver(task) }) else null,
                )
            }
        }
    }
}

/**
 * `-omiSwipeDemo YES` pages to the transcript and back once the page has settled (a scripted check
 * that the pager moves smoothly; debug builds only).
 */
private suspend fun swipeForDebugging(state: ConversationDetailState) {
    if (!DebugLaunch.flag("omiSwipeDemo")) return
    repeat(6) {
        delay(2_500)
        state.page = if (state.page == ConversationDetailState.Page.Summary) ConversationDetailState.Page.Transcript else ConversationDetailState.Page.Summary
    }
}
