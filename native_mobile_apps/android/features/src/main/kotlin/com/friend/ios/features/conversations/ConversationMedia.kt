package com.friend.ios.features.conversations

import android.graphics.BitmapFactory
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationPhoto
import com.friend.ios.core.models.ConversationScreenshot
import com.friend.ios.core.models.Participants
import com.friend.ios.core.models.participants
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.Detent
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.ConversationScreenshotsStore
import com.friend.ios.service.stores.followProcessing
import com.friend.ios.service.stores.image
import com.friend.ios.service.stores.makeFeedbackStore
import com.friend.ios.service.stores.makeScreenshotsStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URL

/**
 * Port of `ConversationMedia.swift`: the summary's extras inside "More details": which app wrote
 * it, the linked calendar event, "Was this helpful?" and what was on screen.
 */
@Composable
fun SummaryExtrasSection(store: ConversationDetailStore, extras: DetailExtras) {
    store.detail?.summaryAppID?.let { appID -> Attribution(appID, extras) }
    store.detail?.calendarEvent?.let { event -> LinkedEventCard(event) { extras.showsEvent = true } }
    extras.feedback?.let { SummaryFeedbackRow(it) }
    extras.screenshots?.let { screenshots -> if (screenshots.screenshots.isNotEmpty()) ScreenshotsStrip(screenshots) }
}

/** "Summarized by <app>"; tapping it opens the summary templates. */
@Composable
private fun Attribution(appID: String, extras: DetailExtras) {
    val name = extras.templates?.app(appID)?.name ?: L("unknownApp")
    HStack(Modifier.plainButton { extras.showsTemplates = true }, spacing = DS.Spacing.sm) {
        SFImage("square.grid.2x2", size = 13.sp, tint = DS.Palette.inkSecondary)
        Text(L("nativeSummarizedBy", name), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
    }
}

/**
 * Creates and loads what the extras need (summary feedback, screenshots, the summarizing app's
 * name) once the conversation has loaded, whether or not "More details" is open.
 */
@Composable
fun SummaryExtrasLoader(store: ConversationDetailStore, extras: DetailExtras) {
    val conversations = LocalConversationsStore.current
    LaunchedEffect(store.phase) {
        val detail = store.detail
        if (store.phase != ConversationDetailStore.Phase.Loaded || detail == null) return@LaunchedEffect
        if (extras.feedback == null) {
            val feedback = conversations.makeFeedbackStore(detail.conversation.id)
            extras.feedback = feedback
            // Only Omi's own summary asks about a summary, a finished recording with audio about
            // the recording; a discarded conversation never asks.
            val kept = !detail.conversation.isDiscarded
            feedback.start(
                hasOwnSummary = kept && detail.summaryAppID == null && detail.summary.isNotEmpty(),
                hasRecording = kept && detail.conversation.status == Conversation.Status.Completed && detail.hasAudio,
            )
        }
        if (extras.screenshots == null && detail.conversation.status == Conversation.Status.Completed && !detail.conversation.isDiscarded) {
            val screenshots = conversations.makeScreenshotsStore(detail.conversation.id)
            extras.screenshots = screenshots
            screenshots.load()
        }
    }
    LaunchedEffect(store.detail?.summaryAppID) {
        // The app's name for the attribution line.
        if (store.detail?.summaryAppID != null) extras.templates(conversations).load(store.conversation.id)
    }
}

/** "You + 2 others": who took part. Opens the linked calendar event, if any. */
@Composable
fun ParticipantsRow(store: ConversationDetailStore, onOpenEvent: () -> Unit) {
    val detail = store.detail ?: return
    val settings = LocalSettingsStore.current
    val you = L("you")
    val people = detail.participants(you) { id -> settings.people.firstOrNull { it.id == id }?.name }
    if (people.isEmpty) return
    val label = ParticipantsRow.label(people)
    val symbol = if (people.names.size > 1 || people.others > 0) "person.2" else "person"
    val modifier = if (detail.calendarEvent != null) Modifier.plainButton(onClick = onOpenEvent) else Modifier
    HStack(modifier, spacing = DS.Spacing.sm) {
        SFImage(symbol, size = 15.sp, tint = DS.Palette.inkSecondary)
        Text(label, style = DS.Typography.callout, color = DS.Palette.inkSecondary, maxLines = 1)
    }
}

object ParticipantsRow {
    /** One name; "Anna + 2 others"; "Anna + others" when Omi could not count. */
    @Composable
    fun label(people: Participants): String {
        val first = people.names.firstOrNull() ?: return ""
        if (people.uncounted) return L("participantsSummaryUncounted", first)
        return when {
            people.others < 1 -> first
            people.others == 1 -> L("nativeParticipantsOneOther", first)
            else -> L("nativeParticipantsOthers", first, "${people.others}")
        }
    }
}

/**
 * A thin running bar and "Processing conversation..." under the title while Omi works on it; the
 * page reloads every few seconds until it is done (Flutter `conversation_activity_strip`).
 */
@Composable
fun ProcessingStrip(store: ConversationDetailStore, conversation: Conversation) {
    val conversations = LocalConversationsStore.current
    val processing = conversation.status == Conversation.Status.Processing
    AnimatedVisibility(store.isReprocessing || processing, enter = fadeIn(DS.Motion.standard()), exit = fadeOut(DS.Motion.standard())) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
            LinearActivityBar(Modifier.fillMaxWidth())
            Text(
                if (store.isReprocessing) L("reprocessingConversationProgress") else L("processingConversationProgress"),
                style = DS.Typography.caption,
                color = DS.Palette.inkSecondary,
            )
        }
    }
    LaunchedEffect(conversation.status) {
        if (processing && !store.isReprocessing) store.followProcessing(conversations)
    }
}

/** `ProgressView().progressViewStyle(.linear)` without a value: a 4 pt track, a segment running across in the tint. */
@Composable
private fun LinearActivityBar(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "activity")
    val phase by transition.animateFloat(0f, 1f, infiniteRepeatable(tween(1_400, easing = LinearEasing), RepeatMode.Restart), label = "phase")
    val tint = DS.Palette.agent
    BoxWithConstraints(modifier.height(4.dp).clip(CircleShape).background(DS.Palette.fill)) {
        val segment = maxWidth * 0.35f
        Box(
            Modifier
                .offset(x = (maxWidth + segment) * phase - segment)
                .width(segment)
                .fillMaxSize()
                .background(tint, CircleShape),
        )
    }
}

/**
 * Photos taken during the conversation, three across; Omi is still describing the ones with a
 * spinner, discarded ones are dimmed. Tap for the full picture and its description.
 */
@Composable
fun ConversationPhotosGrid(store: ConversationDetailStore) {
    val photos = store.detail?.photos.orEmpty()
    if (photos.isEmpty()) return
    var opened by remember { mutableStateOf<ConversationPhoto?>(null) }
    val shape = ContinuousRoundedShape(DS.Radius.sm)
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        photos.chunked(3).forEach { rowPhotos ->
            Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                rowPhotos.forEach { photo ->
                    Box(
                        Modifier.weight(1f).aspectRatio(4f / 3f).clip(shape).plainButton { opened = photo },
                        contentAlignment = Alignment.Center,
                    ) {
                        RemoteImage(
                            { store.image(photo) }, Modifier.fillMaxSize().alpha(if (photo.isDiscarded) 0.4f else 1f),
                            contentDescription = photo.description ?: L("nativePhoto"),
                        )
                        if (photo.isDescribing) OmiProgress()
                        if (photo.isDiscarded) SFImage("eye.slash", tint = DS.Palette.inkSecondary)
                    }
                }
                repeat(3 - rowPhotos.size) { Box(Modifier.weight(1f)) }
            }
        }
    }
    opened?.let { photo -> ImageViewer(photo.description, { store.image(photo) }, onDismiss = { opened = null }) }
}

/** "What was on screen": a meeting's screenshots in a row with their captions. Tap to open, long-press to delete. */
@Composable
fun ScreenshotsStrip(screenshots: ConversationScreenshotsStore) {
    val scope = rememberCoroutineScope()
    var opened by remember { mutableStateOf<ConversationScreenshot?>(null) }
    var deleting by remember { mutableStateOf<ConversationScreenshot?>(null) }
    val fallback = L("meetingScreenshotFallbackCaption")
    val openTitle = L("open")
    val deleteTitle = L("delete")
    fun caption(shot: ConversationScreenshot) = shot.caption.ifEmpty { fallback }
    val shape = ContinuousRoundedShape(DS.Radius.sm)
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Text(L("meetingScreenshotsTitle"), style = DS.Typography.sectionTitle, color = DS.Palette.ink)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            screenshots.screenshots.forEach { shot ->
                ContextMenuBox(
                    sections = {
                        listOf(
                            MenuSection(
                                items = listOf(
                                    MenuItem(openTitle, "arrow.up.left.and.arrow.down.right") { opened = shot },
                                    MenuItem(deleteTitle, "trash", destructive = true) { deleting = shot },
                                ),
                            ),
                        )
                    },
                    onTap = { opened = shot },
                ) {
                    Column(Modifier.width(144.dp), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                        RemoteImage({ ScreenshotsStrip.load(shot.thumbnailURL ?: shot.imageURL) }, Modifier.size(144.dp, 90.dp).clip(shape))
                        Text(caption(shot), style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 2)
                    }
                }
            }
        }
    }
    opened?.let { shot -> ImageViewer(caption(shot), { ScreenshotsStrip.load(shot.imageURL ?: shot.thumbnailURL) }, onDismiss = { opened = null }) }
    deleting?.let { shot ->
        OmiAlert(
            L("deleteMeetingScreenshotTitle"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("delete"), DialogButton.Role.Destructive) { scope.launch { screenshots.delete(shot) } },
            ),
            onDismiss = { deleting = null },
            message = L("deleteMeetingScreenshotMessage"),
        )
    }
}

object ScreenshotsStrip {
    /** Signed URLs load without auth headers. */
    suspend fun load(url: String?): ByteArray? {
        url ?: return null
        return withContext(Dispatchers.IO) { runCatching { URL(url).openStream().use { it.readBytes() } }.getOrNull() }
    }
}

/** An image from bytes loaded on demand, a quiet tile meanwhile. [fits] shows the whole picture instead of filling the frame. */
@Composable
fun RemoteImage(load: suspend () -> ByteArray?, modifier: Modifier = Modifier, fits: Boolean = false, contentDescription: String? = null) {
    val state by produceState<Pair<ImageBitmap?, Boolean>>(null to false) {
        val data = load()
        val bitmap = data?.let { bytes ->
            withContext(Dispatchers.Default) { runCatching { BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap() }.getOrNull() }
        }
        value = bitmap to true
    }
    Box(modifier.background(DS.Palette.cardRaised), contentAlignment = Alignment.Center) {
        val (image, loaded) = state
        if (image != null) {
            Image(image, contentDescription, Modifier.fillMaxSize(), contentScale = if (fits) ContentScale.Fit else ContentScale.Crop)
        } else if (loaded) {
            SFImage("photo", tint = DS.Palette.inkTertiary, contentDescription = contentDescription)
        }
    }
}

/** One picture, full width, with its caption. */
@Composable
fun ImageViewer(caption: String?, load: suspend () -> ByteArray?, onDismiss: () -> Unit) {
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar("", trailing = { SheetBarButton(L("done"), prominent = true, onClick = onDismiss) })
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(DS.Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        ) {
            RemoteImage(load, Modifier.fillMaxWidth().aspectRatio(4f / 3f).clip(ContinuousRoundedShape(DS.Radius.md)), fits = true)
            if (!caption.isNullOrEmpty()) Text(caption, style = DS.Typography.body, color = DS.Palette.inkSecondary)
        }
    }
}
