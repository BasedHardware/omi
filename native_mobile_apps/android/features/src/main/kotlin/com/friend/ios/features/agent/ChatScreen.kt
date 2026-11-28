package com.friend.ios.features.agent

import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalContext
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.Manifest
import android.content.pm.PackageManager
import com.friend.ios.design.DSHaptics
import com.friend.ios.service.LocalDictation
import com.friend.ios.service.stores.VoiceIntroStore
import java.util.Locale
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.ChatBottomTracker
import com.friend.ios.service.stores.asChatTasks
import com.friend.ios.service.stores.ChatThreadFilter
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Something the shell hands the chat tab: start listening, a question waiting in the composer, or
 * searching the thread (the app header's search and "…" filters on the tab). Each new [id] is
 * handled once. Port of `ChatScreen.Request`.
 */
data class ChatScreenRequest(
    val draft: String = "",
    val dictate: Boolean = false,
    val search: Boolean = false,
    val filter: ChatThreadFilter? = null,
    val id: String = UUID.randomUUID().toString(),
) {
    companion object {
        /** The header's search on the Chat tab: the field opens, the keyboard comes up. */
        fun search() = ChatScreenRequest(search = true)

        /** A filter from the header's "…": the thread shows only those. */
        fun filter(filter: ChatThreadFilter) = ChatScreenRequest(search = true, filter = filter)

        /** The Ask bar's mic: the chat opens listening. */
        fun dictate() = ChatScreenRequest(dictate = true)

        /** A question in the composer, not sent yet (one the assistant could not answer). */
        fun draft(text: String) = ChatScreenRequest(draft = text)
    }
}

/**
 * Port of `ChatScreen.swift` in `.tab` mode (+ `ChatScreen+Tab.swift`, `ChatScreen+Empty.swift`).
 * Chat with Omi: one long thread (the pinned main chat) with greeting and starters when empty,
 * streamed answers with the agent's tool steps, and the cards the app draws for what Omi did.
 * As a tab it also shows what Omi is working on right now ("Running now") and can be searched.
 *
 * [request]: what the shell asks for on switching to the tab (search, a filter, dictate, a draft).
 * [onUpgrade]: "Upgrade" on a quota answer (the shell opens Account).
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ChatScreen(
    onOpenConversation: (String) -> Unit,
    modifier: Modifier = Modifier,
    request: ChatScreenRequest? = null,
    onUpgrade: (() -> Unit)? = null,
) {
    val chat = LocalChatStore.current
    val agent = LocalAgentStore.current
    val conversations = LocalConversationsStore.current
    val tasks = LocalTasksStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val keyboard = LocalSoftwareKeyboardController.current
    val density = LocalDensity.current
    val state = ChatScreenState.remember()
    val list = rememberLazyListState()
    val composerFocus = remember { FocusRequester() }
    var composerFocused by remember { mutableStateOf(false) }
    var composerHeight by remember { mutableStateOf(0.dp) }
    var historySettled by remember { mutableStateOf(false) }
    /** Whether the thread rests at its end (follows new words, hides the jump button). */
    val bottom = remember { ChatBottomTracker() }
    val offline = rememberIsOffline()

    // Dictation: the phone microphone, words on the phone (`AppEnvironment.dictation`).
    val dictation = LocalDictation.current
    val context = LocalContext.current
    /** The draft before dictation began; dictated words are added after it. */
    var draftBeforeDictation by remember { mutableStateOf("") }
    /** Dictation started from the filled circle: the question goes out when it stops. */
    var sendsAfterDictation by remember { mutableStateOf(false) }
    val isDictating = dictation != null && (dictation.phase == VoiceIntroStore.Phase.Listening || dictation.phase == VoiceIntroStore.Phase.Starting)
    // The phone microphone is busy while the phone itself records.
    val capture = com.friend.ios.service.LocalCaptureStore.current
    val canDictate = dictation != null && !(capture.isLive && capture.source == com.friend.ios.service.stores.CaptureStore.Source.Phone)
    val voice = com.friend.ios.service.LocalVoicePlaybackStore.current
    fun beginDictation() {
        val store = dictation ?: return
        voice?.stop()
        haptics.tap(DSHaptics.Style.Medium)
        draftBeforeDictation = state.draft
        scope.launch { store.start(VoiceIntroStore.Source.Phone, Locale.getDefault().language.ifEmpty { "en" }) }
    }
    // The microphone permission is asked for the first time dictation starts.
    val askMicrophone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) beginDictation() else sendsAfterDictation = false
    }
    fun startDictation() {
        if (!canDictate) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) beginDictation()
        else askMicrophone.launch(Manifest.permission.RECORD_AUDIO)
    }
    fun stopDictation() {
        dictation?.stop()
        haptics.tap(DSHaptics.Style.Light)
    }

    val canSend = state.draft.isNotBlank() && !chat.isUploading
    fun send(text: String) {
        haptics.tap()
        voice?.stop()
        chat.send(text)
    }
    fun sendDraft() {
        if (chat.isStreaming) {
            chat.cancel()
            return
        }
        if (!canSend) return
        send(state.draft)
        state.draft = ""
    }
    fun focusComposer() {
        composerFocus.requestFocus()
        keyboard?.show()
    }

    LaunchedEffect(Unit) {
        // What the agent does to tasks shows as cards under its answers.
        chat.tasks = tasks.asChatTasks()
        chat.loadHistory()
    }
    LaunchedEffect(offline) { chat.networkUnavailable = offline }
    LaunchedEffect(isDictating) {
        // Talking from the filled circle: the question goes out once listening ends.
        if (isDictating || !sendsAfterDictation) return@LaunchedEffect
        sendsAfterDictation = false
        sendDraft()
    }
    LaunchedEffect(dictation?.transcript) {
        val words = dictation?.transcript.orEmpty()
        if (!isDictating || words.isEmpty()) return@LaunchedEffect
        state.draft = if (draftBeforeDictation.isEmpty()) words else "$draftBeforeDictation $words"
    }
    DisposableEffect(Unit) {
        // Finished answers are read aloud while the chat is on screen (as the reply mode allows).
        chat.onAnswer = { voice?.answerArrived(it) }
        onDispose {
            dictation?.stop()
            chat.onAnswer = null
            voice?.stop()
        }
    }
    // Leaving the app stops reading (`scenePhase != .active`).
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current
    DisposableEffect(lifecycle) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            if (event == androidx.lifecycle.Lifecycle.Event.ON_PAUSE) voice?.stop()
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(request?.id) {
        val wanted = request ?: return@LaunchedEffect
        if (state.handledRequest == wanted.id) return@LaunchedEffect
        state.handledRequest = wanted.id
        if (wanted.search) {
            if (wanted.filter != null) {
                // A filter from the header's "…": the matches, without the keyboard in the way.
                keyboard?.hide()
                state.isSearching = true
                state.filter = wanted.filter
            } else {
                haptics.selection()
                state.isSearching = true
                state.focusSearch = true
            }
            return@LaunchedEffect
        }
        state.stopSearching()
        if (wanted.draft.isNotEmpty()) state.draft = wanted.draft
        if (wanted.dictate) startDictation()
    }
    // Where the thread rests: at its end (the jump button, following new words). At the end while
    // the newest row is within the threshold of the composer (the list is laid out from the bottom).
    LaunchedEffect(list) {
        val threshold = with(density) { ChatBottomTracker.THRESHOLD.dp.toPx() }
        snapshotFlow { list.firstVisibleItemIndex == 0 && list.firstVisibleItemScrollOffset <= threshold }
            // Only the user's own scrolling leaves the bottom: a growing answer or the keyboard
            // never stops the list from following.
            .collect { bottom.geometryChanged(atBottom = it) }
    }
    LaunchedEffect(list) {
        // Scrolling ended (also after a fling that bounced at the end): believe where it rests.
        snapshotFlow { list.isScrollInProgress }.collect { bottom.phaseChanged(isIdle = !it) }
    }
    val lastID = chat.messages.lastOrNull()?.id ?: ""
    val cardsOnLast = chat.cards(lastID).size + (if (chat.pendingDeviceToolMessageID == lastID) 1 else 0)
    val followKey = followKey(chat.messages.lastOrNull(), chat.isStreaming, cardsOnLast, finishedRuns(agent).size)
    LaunchedEffect(followKey) { if (bottom.isAtBottom && list.firstVisibleItemIndex <= 1) list.scrollToItem(0) }
    LaunchedEffect(chat.messages.lastOrNull()?.id) {
        // A question the user just sent always comes into view (older pages land at the top and
        // leave the last message as it is).
        if (chat.messages.lastOrNull()?.sender == ChatMessage.Sender.Omi) {
            bottom.jumpedToBottom()
            list.animateScrollToItem(0)
        }
    }
    LaunchedEffect(chat.hasLoaded) {
        // Once the history is laid out, settle at the end; only then may the top load older pages.
        if (!chat.hasLoaded) return@LaunchedEffect
        list.scrollToItem(0)
        delay(240)
        historySettled = true
    }
    LaunchedEffect(composerFocused) {
        // Typing starts at the newest message: once the keyboard has come up, bring the end into view.
        if (!composerFocused) return@LaunchedEffect
        delay(350)
        bottom.jumpedToBottom()
        list.animateScrollToItem(0)
    }

    val rows = ChatRow.stacked(ChatRow.merge(chat.messages, if (chat.chatApp == null) finishedRuns(agent) else emptyList()))
    fun open(run: AgentStore.Run) {
        haptics.selection()
        keyboard?.hide()
        state.openRun = handOverTask(run, tasks)
    }
    LaunchedEffect(state.jumpTarget) {
        val target = state.jumpTarget ?: return@LaunchedEffect
        // Back in the full thread: the tapped match comes into view once it is laid out.
        delay(120)
        val index = rows.asReversed().indexOfFirst { it.id == target }
        if (index >= 0) list.animateScrollToItem(index + 1, -with(density) { 200.dp.toPx() }.toInt())
        state.jumpTarget = null
    }

    // Debug builds: the launch arguments for screenshots (inert otherwise).
    ChatDebugDemos(state)

    Column(modifier.fillMaxSize()) {
        ChatTabHeader(state, offline, onOpenRun = ::open)
        Box(Modifier.weight(1f).fillMaxWidth()) {
            ChatList(
                list = list,
                rows = rows,
                state = state,
                historySettled = historySettled,
                bottomPadding = composerHeight,
                onReply = { message ->
                    haptics.selection()
                    chat.replyingTo = message
                    focusComposer()
                },
                onSend = ::send,
                onOpenConversation = onOpenConversation,
                onUpgrade = onUpgrade,
                onJump = { id ->
                    state.stopSearching()
                    state.jumpTarget = id
                },
                onAskAboutFile = { draft ->
                    state.draft = draft
                    focusComposer()
                },
                onOpenRun = ::open,
                modifier = Modifier.fillMaxSize().fadingTop(),
            )
            if (!chat.hasLoaded) LoadingOrFailed(Modifier.align(Alignment.Center))
            // Above the composer, only while the end is out of view by more than the threshold, so
            // it never sits on the last bubble.
            androidx.compose.animation.AnimatedVisibility(
                !bottom.isAtBottom && chat.hasLoaded && chat.messages.isNotEmpty() && !state.isFiltering,
                Modifier.align(Alignment.BottomCenter).padding(bottom = composerHeight + DS.Spacing.sm),
                enter = scaleIn() + fadeIn(),
                exit = scaleOut() + fadeOut(),
            ) {
                androidx.compose.foundation.layout.Box(
                    Modifier
                        .size(40.dp)
                        .plainButton {
                            haptics.selection()
                            scope.launch { list.animateScrollToItem(0) }
                            bottom.jumpedToBottom()
                        }
                        .omiSurface(CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    SFImage("arrow.down", size = 17.sp, weight = FontWeight.SemiBold, tint = DS.Palette.ink, contentDescription = L("nativeJumpToLatest"))
                }
            }
            BottomInset(
                showsStarters = chat.messages.isEmpty() && chat.hasLoaded && !state.isFiltering,
                startersVisible = state.draft.isEmpty(),
                hasConversations = conversations.conversations.isNotEmpty(),
                onStarter = ::send,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .onSizeChanged { composerHeight = with(density) { it.height.toDp() } },
            ) {
                ChatComposer(
                    draft = state.draft,
                    onDraftChange = { state.draft = it },
                    focusRequester = composerFocus,
                    onFocusChange = { composerFocused = it },
                    isDictating = isDictating,
                    canDictate = canDictate,
                    canSend = canSend,
                    level = dictation?.level ?: 0f,
                    sendsAfterDictation = sendsAfterDictation,
                    onSend = ::sendDraft,
                    onDictate = { thenSend ->
                        sendsAfterDictation = thenSend
                        startDictation()
                    },
                    onStopDictation = ::stopDictation,
                )
            }
        }
    }
    state.openRun?.let { task ->
        val title = task.conversationID?.let { id -> conversations.conversations.firstOrNull { it.id == id }?.title }
        OmiSheet(onDismiss = { state.openRun = null }) { HandOverSheet(task, title, onDismiss = { state.openRun = null }) }
    }
}

/**
 * The starters (while the thread is empty) and the composer, pinned at the bottom over the thread,
 * which scrolls on under them ([composerBackdrop]). Sits on the keyboard.
 */
@Composable
private fun BottomInset(
    showsStarters: Boolean,
    startersVisible: Boolean,
    hasConversations: Boolean,
    onStarter: (String) -> Unit,
    modifier: Modifier,
    composer: @Composable () -> Unit,
) {
    // Fades instead of collapsing while typing, so the composer does not jump.
    val starters by animateFloatAsState(if (startersVisible) 1f else 0f, DS.Motion.standard(), label = "starters")
    Column(
        modifier
            .fillMaxWidth()
            .composerBackdrop()
            .windowInsetsPadding(WindowInsets.ime.union(WindowInsets.navigationBars)),
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        if (showsStarters) {
            Box(Modifier.graphicsLayer { alpha = starters }) {
                Starters(hasConversations, enabled = startersVisible, onSend = onStarter)
            }
        }
        composer()
    }
}

/**
 * Port of `ComposerBackdrop`: behind the composer the page color, down to the screen's edge (and
 * the keyboard's top while it is up), with a short fade at its top edge instead of a line. iOS lays
 * it over a blur (`.ultraThinMaterial` under the page color at 86 %); Compose cannot blur what lies
 * behind a view, so here the page color is solid.
 */
@Composable
private fun Modifier.composerBackdrop(): Modifier {
    val page = DS.Palette.background
    val fade = with(LocalDensity.current) { COMPOSER_FADE.toPx() }
    return drawBehind {
        drawRect(
            Brush.verticalGradient(0f to page.copy(alpha = 0f), 1f to page, startY = -fade, endY = 0f),
            topLeft = Offset(0f, -fade),
            size = size.copy(height = fade),
        )
        drawRect(page)
    }
}

private val COMPOSER_FADE = 14.dp

/** The thread fades out at its top edge, so messages leave softly instead of being cut off. */
private fun Modifier.fadingTop(height: Dp = 28.dp): Modifier = this
    .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
    .drawWithContent {
        drawContent()
        drawRect(Brush.verticalGradient(listOf(Color.Transparent, Color.Black), startY = 0f, endY = height.toPx()), blendMode = BlendMode.DstIn)
    }

/** Changes whenever the last answer grows: new text, a new step, a card, or a finished state. */
private fun followKey(last: ChatMessage?, streaming: Boolean, cards: Int, runs: Int): String {
    last ?: return ""
    return "${last.id}|${last.text.length}|${last.steps.size}|${last.failure?.rawValue ?: ""}|$streaming|$cards|$runs"
}

/** Keeps the thread's screen state (iOS `@State`) together. */
internal class ChatScreenState {
    var draft by mutableStateOf("")
    var handledRequest: String? = null
    /** Searching the thread: the field and the filter chips show, the thread shows matches only. */
    var isSearching by mutableStateOf(false)
    var query by mutableStateOf("")
    var filter by mutableStateOf<ChatThreadFilter?>(null)
    /** The search field should take the keyboard (once). */
    var focusSearch by mutableStateOf(false)
    /** A match the user tapped: the full thread comes back scrolled to it. */
    var jumpTarget by mutableStateOf<String?>(null)
    /** The hand-over whose sheet is open (from Running now or a finished run's row). */
    var openRun by mutableStateOf<ActionItem?>(null)

    val isFiltering: Boolean get() = isSearching && (query.isNotBlank() || filter != null)

    fun stopSearching() {
        isSearching = false
        query = ""
        filter = null
        focusSearch = false
    }

    companion object {
        @Composable
        fun remember(): ChatScreenState {
            val state = androidx.compose.runtime.remember { ChatScreenState() }
            // The draft survives a configuration change, as `@State` survives on iOS.
            var saved by rememberSaveable { mutableStateOf("") }
            LaunchedEffect(Unit) { if (state.draft.isEmpty()) state.draft = saved }
            LaunchedEffect(state.draft) { saved = state.draft }
            return state
        }
    }
}
