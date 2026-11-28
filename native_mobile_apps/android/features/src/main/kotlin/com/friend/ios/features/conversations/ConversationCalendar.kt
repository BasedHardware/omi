package com.friend.ios.features.conversations

import android.Manifest
import android.app.Activity
import android.content.ContentUris
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.CalendarContract
import android.text.format.DateFormat
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.CalendarEventCandidate
import com.friend.ios.core.models.CalendarEventLink
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.Formatted
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiRowGlyph
import com.friend.ios.service.stores.ConversationDetailStore
import com.friend.ios.service.stores.calendarCandidates
import com.friend.ios.service.stores.linkCalendarEvent
import com.friend.ios.service.stores.unlinkCalendarEvent
import com.friend.ios.service.stores.window
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** The Google Calendar event the conversation is linked to, as a card on the summary tab. */
@Composable
fun LinkedEventCard(event: CalendarEventLink, onOpen: () -> Unit) {
    HStack(Modifier.fillMaxWidth().plainButton(onClick = onOpen), spacing = DS.Spacing.md) {
        Box(Modifier.width(22.dp), contentAlignment = Alignment.Center) {
            SFImage("calendar.badge.checkmark", tint = DS.Palette.inkSecondary)
        }
        Column(Modifier.weight(1f)) {
            Text(event.title, style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 2)
            Text(
                CalendarEventSheet.timeRange(event.start, event.end),
                style = DS.Typography.caption,
                color = DS.Palette.inkSecondary,
                modifier = Modifier.padding(top = DS.Spacing.xxs),
            )
        }
    }
}

/** A linked event: when, who, open it in Google Calendar, write to the attendees, unlink. */
@Composable
fun CalendarEventSheet(event: CalendarEventLink, store: ConversationDetailStore, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val openInGoogle = L("openInGoogleCalendar")
    val share = L("shareWithAttendees")
    val unlink = L("unlinkCalendarEvent")
    val subject = L("meetingNotesSubject", event.title)
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium)) {
        SheetBar(event.title, trailing = { SheetBarButton(L("done"), prominent = true, onClick = onDismiss) })
        OmiGroupedList {
            section {
                row {
                    OmiRowGlyph("clock")
                    Spacer(Modifier.width(DS.Spacing.md))
                    Text(CalendarEventSheet.timeRange(event.start, event.end), style = DS.Typography.body, color = DS.Palette.ink)
                }
                if (event.attendees.isNotEmpty()) {
                    row {
                        OmiRowGlyph("person.2")
                        Spacer(Modifier.width(DS.Spacing.md))
                        Text(event.attendees.joinToString(", ", transform = CalendarEventSheet::attendee), style = DS.Typography.body, color = DS.Palette.ink)
                    }
                }
            }
            val mail = event.shareURL(subject)
            if (event.htmlLink != null || mail != null) {
                section {
                    event.htmlLink?.let { link ->
                        row(onClick = { openURL(context, link) }) { ActionLabel(openInGoogle, "arrow.up.right.square") }
                    }
                    mail?.let { url -> row(onClick = { openURL(context, url) }) { ActionLabel(share, "envelope") } }
                }
            }
            section {
                row(onClick = {
                    scope.launch {
                        store.unlinkCalendarEvent()
                        onDismiss()
                    }
                }) { ActionLabel(unlink, "calendar.badge.minus", destructive = true) }
            }
        }
    }
}

/** A `Label` button row in a grouped list: the glyph in the tint, the title. */
@Composable
internal fun ActionLabel(title: String, systemImage: String, destructive: Boolean = false) {
    val tint = if (destructive) DS.Palette.live else DS.Palette.agent
    OmiRowGlyph(systemImage, tint = tint)
    Spacer(Modifier.width(DS.Spacing.md))
    Text(title, style = DS.Typography.body, color = tint)
}

object CalendarEventSheet {
    /** "Wed 7 Oct, 15:00 – 16:00". */
    fun timeRange(start: Instant, end: Instant): String = "${dateTime(start)} – ${Formatted.shortTime(end)}"

    /** `.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute()`. */
    fun dateTime(instant: Instant, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
        DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, "EEEMMMdjmm"), locale).format(instant.atZone(zone))

    /** An email shows as its local part (Flutter `formatAttendeeName`). */
    fun attendee(value: String): String = if ("@" in value) value.substringBefore("@") else value
}

/**
 * "Link Event": events around the conversation from Google Calendar, the best overlap marked
 * "Suggested" and first.
 */
@Composable
fun LinkEventSheet(store: ConversationDetailStore, onLinked: (String) -> Unit, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var events by remember { mutableStateOf<List<CalendarEventCandidate>?>(null) }
    var linking by remember { mutableStateOf<String?>(null) }
    var failed by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        val loaded = store.calendarCandidates() ?: emptyList()
        val (start, end) = store.window
        val best = CalendarEventCandidate.suggested(loaded, start, end)
        events = loaded.sortedWith { lhs, rhs ->
            when {
                lhs.id == best?.id -> -1
                rhs.id == best?.id -> 1
                else -> lhs.start.compareTo(rhs.start)
            }
        }
    }
    val (start, end) = store.window
    val suggested = CalendarEventCandidate.suggested(events.orEmpty(), start, end)
    val untitled = L("untitledConversation")
    val suggestedLabel = L("suggestedEvent")
    val nothing = L("noCalendarEventsNearby")
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(L("linkEvent"), leading = { SheetBarButton(L("cancel"), onClick = onDismiss) })
        OmiGroupedList {
            section {
                val list = events
                if (list == null) {
                    row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
                } else {
                    if (list.isEmpty()) row { Text(nothing, style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
                    list.forEach { event ->
                        row(key = event.id, enabled = linking == null, onClick = {
                            linking = event.id
                            scope.launch {
                                if (store.linkCalendarEvent(event.id) != null) {
                                    onLinked(event.title)
                                    onDismiss()
                                } else {
                                    failed = true
                                }
                                linking = null
                            }
                        }) {
                            Column(Modifier.weight(1f)) {
                                HStack(spacing = DS.Spacing.xs) {
                                    Text(event.title.ifEmpty { untitled }, style = DS.Typography.cardTitle, color = DS.Palette.ink)
                                    if (event.id == suggested?.id) {
                                        Text(
                                            suggestedLabel,
                                            style = DS.Typography.micro,
                                            color = DS.Palette.agent,
                                            modifier = Modifier
                                                .background(DS.Palette.agentSoft, CircleShape)
                                                .padding(horizontal = DS.Spacing.xs + 2.dp, vertical = 2.dp),
                                        )
                                    }
                                }
                                Text(
                                    CalendarEventSheet.timeRange(event.start, event.end),
                                    style = DS.Typography.caption,
                                    color = DS.Palette.inkSecondary,
                                    modifier = Modifier.padding(top = DS.Spacing.xxs),
                                )
                            }
                            if (linking == event.id) OmiProgress()
                        }
                    }
                }
            }
        }
    }
    if (failed) {
        OmiAlert(L("failedToLinkCalendarEvent"), listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { failed = false })
    }
}

/**
 * `AddToCalendarView`: the system "New Event" editor (Calendar provider insert), filled with an
 * event Omi found; no calendar permission needed (the editor runs outside the app). Returns the
 * function that opens it; [onFinish] says whether the event is now in the calendar.
 *
 * iOS hears "saved" from the editor. Most Android calendar apps never report a save (they return
 * `RESULT_CANCELED` either way), so a return counts as added: the row then shows its check and
 * the event is not added twice. Where the app may read the calendar, the calendar itself answers
 * instead ([CalendarCheck]). Only a launch that failed (no calendar app) is "not added".
 */
@Composable
fun rememberAddToCalendar(onFinish: (Boolean) -> Unit): (ConversationDetail.Event) -> Unit {
    val context = LocalContext.current
    var pending by remember { mutableStateOf<ConversationDetail.Event?>(null) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val event = pending
        pending = null
        onFinish(result.resultCode == Activity.RESULT_OK || event == null || CalendarCheck.contains(context, event) != false)
    }
    return remember(launcher) {
        { event: ConversationDetail.Event ->
            val (begin, end) = CalendarCheck.window(event)
            val intent = Intent(Intent.ACTION_INSERT, CalendarContract.Events.CONTENT_URI)
                .putExtra(CalendarContract.Events.TITLE, event.title)
                .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, begin.toEpochMilli())
                .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, end.toEpochMilli())
            if (event.description.isNotEmpty()) intent.putExtra(CalendarContract.Events.DESCRIPTION, event.description)
            pending = event
            runCatching { launcher.launch(intent) }.onFailure {
                pending = null
                onFinish(false)
            }
        }
    }
}

/** Whether a found event is in the phone's calendar, where the app may read it. */
object CalendarCheck {
    /** The event's start and end as the editor gets them (now when it has no start, at least a minute). */
    fun window(event: ConversationDetail.Event, now: Instant = Instant.now()): Pair<Instant, Instant> {
        val start = event.start ?: now
        return start to start.plusSeconds(maxOf(event.duration, 1) * 60L)
    }

    /**
     * True when an event with the same title starts within a minute of [event]'s start, false when
     * none does, null when the calendar cannot be read (no permission, no provider).
     */
    fun contains(context: Context, event: ConversationDetail.Event): Boolean? {
        if (context.checkSelfPermission(Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) return null
        val (begin, _) = window(event)
        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon().also {
            ContentUris.appendId(it, begin.toEpochMilli() - 60_000)
            ContentUris.appendId(it, begin.toEpochMilli() + 60_000)
        }.build()
        return runCatching {
            context.contentResolver.query(uri, arrayOf(CalendarContract.Instances.TITLE), null, null, null)?.use { cursor ->
                var found = false
                while (!found && cursor.moveToNext()) found = cursor.getString(0) == event.title
                found
            }
        }.getOrNull()
    }
}
