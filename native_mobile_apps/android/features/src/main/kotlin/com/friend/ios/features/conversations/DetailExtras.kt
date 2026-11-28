package com.friend.ios.features.conversations

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.L
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.ConversationScreenshotsStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.SummaryFeedbackStore
import com.friend.ios.service.stores.SummaryTemplatesStore
import com.friend.ios.service.stores.isCalendarConnected
import com.friend.ios.service.stores.makeTemplatesStore
import com.friend.ios.service.stores.markEventAdded
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `DetailExtras.swift`: what the detail page's newer actions have open: summary template,
 * calendar link, recordings, SMS sharing, the developer test prompt. One object, so the screen
 * holds one piece of state.
 */
@Stable
class DetailExtras {
    var showsTemplates by mutableStateOf(false)
    var linksEvent by mutableStateOf(false)
    var showsEvent by mutableStateOf(false)
    var showsRecordings by mutableStateOf(false)
    var sharesBySMS by mutableStateOf(false)
    var testsPrompt by mutableStateOf(false)
    /** "Google Calendar Not Connected · Connect". */
    var asksToConnectCalendar by mutableStateOf(false)
    /** Another device's recording, opened from the recordings sheet. */
    var openRecording: Conversation? by mutableStateOf(null)
    /** Event Omi found, being added to the phone's calendar (index into `events`). */
    var addingEvent: Int? by mutableStateOf(null)
    /** A short confirmation or failure, shown for a moment by the screen's toast. */
    var notice: String? by mutableStateOf(null)
    /** Debug: the templates sheet opens on "Create custom template". */
    var debugCreatesTemplate by mutableStateOf(false)

    /** Created on first use (they load from the backend). */
    var templates: SummaryTemplatesStore? by mutableStateOf(null)
    var feedback: SummaryFeedbackStore? by mutableStateOf(null)
    var screenshots: ConversationScreenshotsStore? by mutableStateOf(null)

    fun templates(list: ConversationsStore): SummaryTemplatesStore {
        templates?.let { return it }
        val store = list.makeTemplatesStore()
        templates = store
        return store
    }

    fun say(message: String, scope: CoroutineScope) {
        notice = message
        scope.launch {
            delay(2_500)
            if (notice == message) notice = null
        }
    }

    /** Starts linking: the picker when Google Calendar is connected, else the offer to connect. */
    fun linkEvent(store: ConversationDetailStore, scope: CoroutineScope) {
        scope.launch {
            if (store.isCalendarConnected()) linksEvent = true else asksToConnectCalendar = true
        }
    }
}

/**
 * `DetailExtrasPresenter`: every sheet and dialog the extras open, attached once to the detail
 * screen. Another device's recording goes to [onOpenConversation] (the shell pushes it).
 */
@Composable
fun DetailExtrasPresenter(extras: DetailExtras, store: ConversationDetailStore, conversation: Conversation, onOpenConversation: (Conversation) -> Unit) {
    val conversations = LocalConversationsStore.current
    val capabilities = LocalCapabilitiesStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val linkedTo = L("linkedToEvent", "%s")
    val openFailed = L("captureRecordingOpenFailed")

    if (extras.showsTemplates) {
        SummaryTemplateSheet(extras.templates(conversations), store, creating = extras.debugCreatesTemplate, onDismiss = { extras.showsTemplates = false })
    }
    if (extras.linksEvent) {
        LinkEventSheet(store, onLinked = { title -> extras.say(linkedTo.replace("%s", title), scope) }, onDismiss = { extras.linksEvent = false })
    }
    if (extras.showsEvent) {
        val event = store.detail?.calendarEvent
        if (event != null) CalendarEventSheet(event, store, onDismiss = { extras.showsEvent = false })
    }
    if (extras.showsRecordings) {
        CaptureRecordingsSheet(
            store,
            onOpen = { recording ->
                scope.launch {
                    val opened = conversations.conversation(recording.id)
                    if (opened != null) {
                        extras.showsRecordings = false
                        extras.openRecording = opened
                    } else {
                        extras.say(openFailed, scope)
                    }
                }
            },
            onDismiss = { extras.showsRecordings = false },
        )
    }
    if (extras.testsPrompt) TestPromptSheet(store, onDismiss = { extras.testsPrompt = false })

    // A found event on its way into the phone's calendar (the system editor).
    val addToCalendar = rememberAddToCalendar { added ->
        val index = extras.addingEvent
        extras.addingEvent = null
        if (added && index != null) scope.launch { store.markEventAdded(index) }
    }
    LaunchedEffect(extras.addingEvent) {
        val index = extras.addingEvent ?: return@LaunchedEffect
        val event = store.detail?.events?.getOrNull(index)
        if (event == null) extras.addingEvent = null else addToCalendar(event)
    }

    ShareBySMS(extras.sharesBySMS, { extras.sharesBySMS = it }, conversation) { extras.say(it, scope) }

    if (extras.asksToConnectCalendar) {
        OmiAlert(
            L("googleCalendarNotConnected"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("connect")) {
                    scope.launch {
                        val integration = capabilities.integrations.firstOrNull { it.id == "google_calendar" } ?: return@launch
                        capabilities.authorizationURL(integration)?.let { openURL(context, it) }
                    }
                },
            ),
            onDismiss = { extras.asksToConnectCalendar = false },
            message = L("googleCalendarConnectPrompt"),
        )
    }

    LaunchedEffect(extras.openRecording) {
        val other = extras.openRecording ?: return@LaunchedEffect
        extras.openRecording = null
        onOpenConversation(other)
    }

    // `--es omiConversationSheet templates|createTemplate|linkEvent|event|recordings|testPrompt|sms|addEvent`
    // opens that sheet once the page has loaded (scripted screenshots; debug builds only).
    LaunchedEffect(Unit) {
        val sheet = DebugLaunch.string("omiConversationSheet") ?: return@LaunchedEffect
        delay(1_500)
        when (sheet) {
            "templates" -> extras.showsTemplates = true
            "createTemplate" -> {
                extras.debugCreatesTemplate = true
                extras.showsTemplates = true
            }
            "linkEvent" -> extras.linkEvent(store, scope)
            "event" -> extras.showsEvent = true
            "recordings" -> extras.showsRecordings = true
            "testPrompt" -> extras.testsPrompt = true
            "sms" -> extras.sharesBySMS = true
            "addEvent" -> extras.addingEvent = store.detail?.events?.indexOfFirst { !it.isCreated }?.takeIf { it >= 0 }
        }
    }
}
