package com.friend.ios.system.widgets

import android.content.Context
import android.content.Intent
import android.icu.text.MeasureFormat
import android.icu.util.Measure
import android.icu.util.MeasureUnit
import android.text.format.DateFormat
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.ColorFilter
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.text.FontFamily
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.friend.ios.MainActivity
import com.friend.ios.R
import com.friend.ios.core.DeepLink
import com.friend.ios.system.PushNotifications
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle as JavaTextStyle
import java.util.Locale

/**
 * Port of `Extensions/OmiWidgets` (`BatteryWidget.swift`, `HomeWidgets.swift`, `WidgetStyle.swift`)
 * as Glance widgets: Battery, Up next and Latest, dark like the iOS widgets in dark mode. They read
 * the snapshots the app writes ([WidgetPublisher]); a tap opens the app at the matching link.
 */
internal object WidgetPalette {
    val ink = Color(0xFFFFFFFF)
    val inkSecondary = Color(0xFFAEAEB2)
    val inkTertiary = Color(0xFF8E8E93)
    val card = Color(0xFF1C1C1E)
    val live = Color(0xFFFF453A)
}

private fun style(color: Color, size: Float, weight: FontWeight = FontWeight.Normal, family: FontFamily? = null) =
    TextStyle(color = ColorProvider(color), fontSize = size.sp, fontWeight = weight, fontFamily = family)

/** Links into the app (`WidgetLink`): `DeepLink.fromUrl` in the app reads them. */
private fun open(context: Context, link: DeepLink) =
    actionStartActivity(
        Intent(context, MainActivity::class.java)
            .setAction("omi.widget." + link.url)
            .putExtra(PushNotifications.EXTRA_LINK, link.url)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
    )

@Composable
private fun WidgetCard(content: @Composable () -> Unit) {
    Box(
        GlanceModifier.fillMaxSize().background(WidgetPalette.card).cornerRadius(22.dp).padding(16.dp),
        contentAlignment = Alignment.TopStart,
    ) { content() }
}

@Composable
private fun RingMark(size: Int, color: Color = WidgetPalette.ink) {
    Image(
        ImageProvider(R.drawable.ic_omi_ring), contentDescription = null,
        modifier = GlanceModifier.size(size.dp), colorFilter = ColorFilter.tint(ColorProvider(color)),
    )
}

// MARK: - Battery

class OmiBatteryWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val device = WidgetStore(context).device()
        provideContent { BatteryView(context, device) }
    }
}

class OmiBatteryWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = OmiBatteryWidget()
}

/** The Omi, "Battery", the level large, and its name with the connection under it. */
@Composable
private fun BatteryView(context: Context, device: DeviceSnapshot?) {
    val level = device?.takeIf { it.connected }?.battery
    fun s(key: String) = WidgetStrings.get(context, key)
    WidgetCard {
        Column(GlanceModifier.fillMaxSize().clickable(open(context, DeepLink.Device))) {
            Row(GlanceModifier.fillMaxWidth()) {
                Image(
                    ImageProvider(com.friend.ios.design.R.drawable.omi_device), contentDescription = null,
                    modifier = GlanceModifier.size(46.dp),
                )
                Spacer(GlanceModifier.defaultWeight())
                Text(s("Battery"), style = style(WidgetPalette.inkSecondary, 12f, FontWeight.Medium))
            }
            Spacer(GlanceModifier.defaultWeight())
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    level?.let { percent(it) } ?: "—",
                    style = style(if (level == null) WidgetPalette.inkTertiary else WidgetPalette.ink, 34f, FontWeight.Medium),
                    maxLines = 1,
                )
                if (level != null && level <= DeviceSnapshot.LOW_MARK) {
                    Spacer(GlanceModifier.width(4.dp))
                    Box(GlanceModifier.size(10.dp).background(WidgetPalette.live).cornerRadius(5.dp)) {}
                }
            }
            val status = when {
                device == null -> s("No Omi paired")
                device.connected -> device.name
                else -> device.name + " · " + s("Not connected")
            }
            Text(status, style = style(WidgetPalette.inkSecondary, 13f), maxLines = 1)
        }
    }
}

/** "82%", "82 %" in German. */
private fun percent(level: Int): String = java.text.NumberFormat.getPercentInstance().format(level / 100.0)

// MARK: - Up next

class OmiUpNextWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val data = WidgetStore(context).upNext()
        provideContent { UpNextView(context, data, Instant.now()) }
    }
}

class OmiUpNextWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = OmiUpNextWidget()
}

/** The Omi mark, Up next and how many are open, then three tasks with when they are due. */
@Composable
private fun UpNextView(context: Context, data: UpNextSnapshot?, now: Instant) {
    fun s(key: String, vararg arguments: Any) = WidgetStrings.get(context, key, *arguments)
    WidgetCard {
        Column(GlanceModifier.fillMaxSize().clickable(open(context, DeepLink.Tasks))) {
            Row(GlanceModifier.fillMaxWidth().padding(bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                RingMark(16)
                Spacer(GlanceModifier.width(6.dp))
                Text(s("Up next"), style = style(WidgetPalette.inkSecondary, 13f, FontWeight.Medium), maxLines = 1)
                Spacer(GlanceModifier.defaultWeight())
                if (data != null && data.open > 0) {
                    Text(s("%lld open", data.open), style = style(WidgetPalette.inkTertiary, 13f, FontWeight.Medium), maxLines = 1)
                }
            }
            if (data != null && data.tasks.isNotEmpty()) {
                data.tasks.take(3).forEach { task -> TaskRow(context, task, now) }
                Spacer(GlanceModifier.defaultWeight())
            } else {
                Spacer(GlanceModifier.defaultWeight())
                Text(
                    s(if (data == null) "Open Omi to continue" else "All caught up"),
                    style = style(WidgetPalette.inkSecondary, 15f).copy(textAlign = androidx.glance.text.TextAlign.Center),
                    modifier = GlanceModifier.fillMaxWidth(),
                )
                Spacer(GlanceModifier.defaultWeight())
            }
        }
    }
}

@Composable
private fun TaskRow(context: Context, task: UpNextSnapshot.Task, now: Instant) {
    val overdue = task.due?.isBefore(now) == true
    Row(
        GlanceModifier.fillMaxWidth().height(34.dp).clickable(open(context, DeepLink.Task(task.id))),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // The open circle (`Circle().strokeBorder`): a ring drawn as two discs.
        Box(GlanceModifier.size(18.dp).background(WidgetPalette.inkTertiary).cornerRadius(9.dp), contentAlignment = Alignment.Center) {
            Box(GlanceModifier.size(15.dp).background(WidgetPalette.card).cornerRadius(7.5.dp)) {}
        }
        Spacer(GlanceModifier.width(10.dp))
        Text(task.title, style = style(WidgetPalette.ink, 15f), maxLines = 1, modifier = GlanceModifier.defaultWeight())
        dueText(context, task.due, now)?.let {
            Spacer(GlanceModifier.width(4.dp))
            Text(it, style = style(if (overdue) WidgetPalette.live else WidgetPalette.inkSecondary, 13f), maxLines = 1)
        }
    }
}

/**
 * When a task is due, as the widget says it at [now]: Overdue, today's time, Tomorrow, the weekday
 * this week, else the date. Null for a task without a date.
 */
internal fun dueText(context: Context, due: Instant?, now: Instant, zone: ZoneId = ZoneId.systemDefault()): String? {
    due ?: return null
    if (due.isBefore(now)) return WidgetStrings.get(context, "Overdue")
    val locale = context.resources.configuration.locales[0]
    val day = due.atZone(zone).toLocalDate()
    val today = now.atZone(zone).toLocalDate()
    return when {
        day == today -> DateFormat.getTimeFormat(context).format(java.util.Date.from(due))
        day == today.plusDays(1) -> WidgetStrings.get(context, "Tomorrow")
        day.isBefore(today.plusDays(6)) -> day.dayOfWeek.getDisplayName(JavaTextStyle.SHORT, locale)
        else -> monthDay(day, locale)
    }
}

private fun monthDay(day: LocalDate, locale: Locale): String =
    DateTimeFormatter.ofPattern(android.text.format.DateFormat.getBestDateTimePattern(locale, "MMMd"), locale).format(day)

// MARK: - Latest conversation

class OmiLatestWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val store = WidgetStore(context)
        val conversation = store.latest()
        val known = store.isKnown(WidgetStore.Key.Latest)
        provideContent { LatestView(context, conversation, known, Instant.now()) }
    }
}

class OmiLatestWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = OmiLatestWidget()
}

/** When it happened, its title in the serif, and its tasks and length. */
@Composable
private fun LatestView(context: Context, conversation: LatestSnapshot?, known: Boolean, now: Instant) {
    fun s(key: String, vararg arguments: Any) = WidgetStrings.get(context, key, *arguments)
    val link = conversation?.let { DeepLink.Conversation(it.id) } ?: DeepLink.Home
    WidgetCard {
        Column(GlanceModifier.fillMaxSize().clickable(open(context, link))) {
            val header = when (val at = conversation?.at) {
                null -> s("Latest")
                else -> s("Latest") + " · " + whenText(context, at, now)
            }
            Text(header, style = style(WidgetPalette.inkSecondary, 12f, FontWeight.Medium), maxLines = 1)
            Spacer(GlanceModifier.height(6.dp))
            if (conversation != null) {
                Text(
                    conversation.title.ifEmpty { s("Untitled conversation") },
                    style = style(WidgetPalette.ink, 19f, family = FontFamily.Serif), maxLines = 3,
                )
                Spacer(GlanceModifier.defaultWeight())
                detail(context, conversation)?.let { Text(it, style = style(WidgetPalette.inkSecondary, 13f), maxLines = 1) }
            } else {
                Text(s(if (known) "No conversations yet" else "Open Omi to continue"), style = style(WidgetPalette.inkSecondary, 15f))
                Spacer(GlanceModifier.defaultWeight())
            }
        }
    }
}

private fun whenText(context: Context, at: Instant, now: Instant, zone: ZoneId = ZoneId.systemDefault()): String {
    val day = at.atZone(zone).toLocalDate()
    val today = now.atZone(zone).toLocalDate()
    return when (day) {
        today -> DateFormat.getTimeFormat(context).format(java.util.Date.from(at))
        today.minusDays(1) -> WidgetStrings.get(context, "Yesterday")
        else -> monthDay(day, context.resources.configuration.locales[0])
    }
}

/** "2 tasks · 14 min". */
private fun detail(context: Context, conversation: LatestSnapshot): String? {
    val locale = context.resources.configuration.locales[0]
    val parts = mutableListOf<String>()
    if (conversation.taskCount > 0) parts += WidgetStrings.get(context, "%lld tasks", conversation.taskCount)
    conversation.duration?.takeIf { it >= 1 }?.let { seconds ->
        val format = MeasureFormat.getInstance(locale, MeasureFormat.FormatWidth.SHORT)
        val total = seconds.toLong()
        parts += when {
            total >= 3600 -> format.formatMeasures(Measure(total / 3600, MeasureUnit.HOUR), Measure((total % 3600) / 60, MeasureUnit.MINUTE))
            total >= 60 -> format.format(Measure(total / 60, MeasureUnit.MINUTE))
            else -> format.format(Measure(total, MeasureUnit.SECOND))
        }
    }
    return parts.takeIf { it.isNotEmpty() }?.joinToString(" · ")
}
