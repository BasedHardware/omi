package com.friend.ios.features.device

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiSectionLabel
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.hex
import androidx.compose.foundation.border
import com.friend.ios.features.settings.SettingsLabeledContent
import com.friend.ios.features.settings.SettingsListPage
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.LocalDiagnosticsReportStore
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.stores.DiagnosticsEvent
import com.friend.ios.service.stores.DiagnosticsReportStore
import com.friend.ios.service.stores.DiagnosticsSummary
import com.friend.ios.service.stores.SignalQuality
import com.friend.ios.service.stores.readSignal
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.roundToLong

/**
 * Port of `DeviceDiagnosticsScreen.swift`: My Devices › About this Omi › Connection health
 * (Flutter `device_diagnostics.dart`): right now, the last 7 days with a verdict, signal and
 * battery over time, and the link's history. Share and Send to support sit in the one "..." menu.
 * Signal is read every 2 s while the page is open.
 */
@Composable
fun DeviceDiagnosticsScreen(onBack: () -> Unit) {
    val devices = LocalDeviceStore.current
    val report = LocalDiagnosticsReportStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var confirmSend by remember { mutableStateOf(false) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    val log = devices.diagnostics
    val connected = devices.connection == DeviceStore.Connection.Connected
    LaunchedEffect(Unit) {
        while (true) {
            devices.readSignal()
            now = System.currentTimeMillis()
            delay(2_000)
        }
    }
    val exportTitle = L("diagnosticsExportTitle")
    SettingsListPage(L("nativeConnectionHealth"), onBack, trailing = {
        val menu = listOf(
            MenuSection(
                items = listOf(
                    MenuItem(L("share"), "square.and.arrow.up") { share(context, report.bundle(), exportTitle) },
                    MenuItem(L("sendToSupport"), "lifepreserver") { if (report.phase != DiagnosticsReportStore.Phase.Sending) confirmSend = true },
                ),
            ),
        )
        // iOS reads the system "ellipsis" glyph as "More".
        OmiMenu(menu, contentDescription = L("moreOptions")) {
            if (report.phase == DiagnosticsReportStore.Phase.Sending) Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) { OmiProgress() }
            else GlassCircleLabel("ellipsis")
        }
    }) {
        section(headerContent = { OmiSectionLabel(L("nativeDiagnosticsNow")) }) {
            row {
                val since = log.connectedAt
                SettingsLabeledContent(
                    L("diagnosticsConnectedFor"),
                    if (since != null && connected) compact((now - since) / 1000.0) else L("nativeNotConnected"),
                )
            }
            row { SettingsLabeledContent(L("battery"), if (connected) devices.battery?.let { "$it%" } ?: "–" else "–") }
            row {
                Text(L("signal"), style = DS.Typography.body, color = DS.Palette.ink)
                Spacer(Modifier.weight(1f).width(DS.Spacing.md))
                val rssi = log.latestSignal
                if (rssi != null && connected) {
                    val quality = SignalQuality.of(rssi)
                    Box(Modifier.size(8.dp).background(color(quality), CircleShape))
                    Spacer(Modifier.width(DS.Spacing.sm))
                    Text(label(quality), style = DS.Typography.body, color = DS.Palette.inkSecondary)
                } else {
                    Text("–", style = DS.Typography.body, color = DS.Palette.inkSecondary)
                }
            }
        }
        val summary = log.summary
        section(headerContent = { OmiSectionLabel(L("nativeDiagnosticsWeek")) }) {
            row { Verdict(summary) }
            row {
                Text(L("diagnosticsDrops"), style = DS.Typography.body, color = DS.Palette.ink)
                Spacer(Modifier.weight(1f).width(DS.Spacing.md))
                Text("${summary.drops}", style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
                summary.dropsPerHour?.let {
                    Spacer(Modifier.width(DS.Spacing.xs))
                    Text(L("diagnosticsDropsPerHour", "$it"), style = DS.Typography.body, color = DS.Palette.inkTertiary)
                }
            }
            row { SettingsLabeledContent(L("failedConnections"), "${summary.failed}") }
            summary.longestGap?.let { gap -> row { SettingsLabeledContent(L("diagnosticsLongestGap"), compact(gap)) } }
        }
        section {
            row {
                Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    Text(L("nativeSignalStrength"), style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
                    if (log.signal.size < 2) {
                        Empty(L("collectingData"))
                    } else {
                        LineChart(log.signal.map { it.rssi.toFloat() }, min = -100f, max = -30f, line = DS.Palette.agent, area = null)
                    }
                }
            }
            row {
                Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    Text(L("batteryHistory"), style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
                    if (log.battery.size < 2) {
                        Empty(L("noBatteryDataYet"))
                    } else {
                        LineChart(log.battery.map { it.level.toFloat() }, min = 0f, max = 100f, line = DS.Palette.success, area = DS.Palette.success.copy(alpha = 0.18f))
                    }
                }
            }
        }
        val recent = log.recent
        section(
            headerContent = { OmiSectionLabel(L("nativeDisconnectHistory")) },
            footer = if (recent.isNotEmpty()) L("lastNEvents", "${recent.size}") else null,
        ) {
            if (recent.isEmpty()) row { Text(L("noDisconnectsRecorded"), style = DS.Typography.body, color = DS.Palette.inkSecondary) }
            recent.forEachIndexed { index, event ->
                row(key = index) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text(title(event), style = DS.Typography.body, color = DS.Palette.ink)
                        Text(detail(event, now), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                    if (event.kind == DiagnosticsEvent.Kind.FailedConnect) {
                        Text(
                            L("diagnosticsFailBadge"),
                            style = DS.Typography.micro,
                            color = DS.Palette.warning,
                            modifier = Modifier.background(DS.Palette.warning.copy(alpha = 0.14f), CircleShape).padding(horizontal = DS.Spacing.sm, vertical = DS.Spacing.xxs),
                        )
                    }
                }
            }
        }
    }
    if (confirmSend) {
        OmiAlert(
            L("sendToSupport"),
            buttons = listOf(DialogButton(L("cancel"), DialogButton.Role.Cancel), DialogButton(L("send")) { scope.launch { report.send() } }),
            onDismiss = { confirmSend = false },
            message = L("nativeDiagnosticsSendBody"),
        )
    }
    (report.phase as? DiagnosticsReportStore.Phase.Sent)?.let { sent ->
        OmiAlert(
            L("deviceDiagnosticsTicket"),
            buttons = listOf(
                DialogButton(L("copy")) {
                    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("ticket", sent.ticket))
                    report.dismiss()
                },
                DialogButton(L("ok"), DialogButton.Role.Cancel) { report.dismiss() },
            ),
            onDismiss = { report.dismiss() },
            message = sent.ticket,
        )
    }
    if (report.phase == DiagnosticsReportStore.Phase.Failed) {
        OmiAlert(L("deviceDiagnosticsUploadFailed"), listOf(DialogButton(L("ok"), DialogButton.Role.Cancel) { report.dismiss() }), onDismiss = { report.dismiss() })
    }
}

/** The week's verdict line. */
@Composable
private fun Verdict(summary: DiagnosticsSummary) {
    val median = summary.medianReconnect
    val (title, detail) = when {
        summary.hasTrouble -> L("diagnosticsVerdictTrouble") to L("diagnosticsVerdictTroubleDetail", "${summary.failedLast24h}")
        median != null -> L("diagnosticsVerdictReconnects") to L("diagnosticsVerdictReconnectsDetail", compact(median))
        else -> L("diagnosticsVerdictNoDrops") to null
    }
    val symbol = when {
        summary.hasTrouble -> "exclamationmark.triangle.fill"
        median != null -> "arrow.triangle.2.circlepath"
        else -> "checkmark.circle.fill"
    }
    val tint = if (summary.hasTrouble) DS.Palette.warning else DS.Palette.success
    Row(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        SFImage(symbol, size = 20.sp, tint = tint)
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
            Text(title, style = DS.Typography.cardTitle, color = DS.Palette.ink)
            detail?.let { Text(it, style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
        }
    }
}

@Composable
private fun Empty(text: String) {
    Box(Modifier.fillMaxWidth().heightIn(min = 80.dp), contentAlignment = Alignment.Center) {
        Text(text, style = DS.Typography.callout, color = DS.Palette.inkTertiary)
    }
}

/** A Swift Charts `LineMark` (+ `AreaMark`) over evenly spaced readings, 110 pt tall. */
@Composable
private fun LineChart(values: List<Float>, min: Float, max: Float, line: Color, area: Color?) {
    Canvas(Modifier.fillMaxWidth().height(110.dp)) {
        val step = size.width / (values.size - 1).coerceAtLeast(1)
        fun y(value: Float) = size.height * (1 - ((value - min) / (max - min)).coerceIn(0f, 1f))
        val points = values.mapIndexed { i, v -> Offset(i * step, y(v)) }
        val path = Path().apply {
            moveTo(points.first().x, points.first().y)
            points.drop(1).forEach { lineTo(it.x, it.y) }
        }
        if (area != null) {
            val fill = Path().apply {
                addPath(path)
                lineTo(points.last().x, size.height)
                lineTo(points.first().x, size.height)
                close()
            }
            drawPath(fill, area)
        }
        drawPath(path, line, style = Stroke(width = 2.dp.toPx()))
    }
}

@Composable
private fun title(event: DiagnosticsEvent): String = when {
    event.kind == DiagnosticsEvent.Kind.FailedConnect -> L("connectionFailed")
    event.manual -> L("manualDisconnect")
    else -> event.reason ?: L("nativeConnectionDropped")
}

@Composable
private fun detail(event: DiagnosticsEvent, now: Long): String {
    val ago = L("durationAgo", compact((now - event.at) / 1000.0))
    val back = event.reconnectedAfter ?: return ago
    return ago + " · " + L("diagnosticsReconnectedIn", compact(back))
}

/** "45s", "3m 10s", "2h 5m", "3d" (Flutter `OmiDuration.compact`). */
@Composable
internal fun compact(interval: Double): String {
    val seconds = maxOf(0L, interval.roundToLong()).toInt()
    return when {
        seconds < 60 -> L("timeCompactSecs", "$seconds")
        seconds < 3600 -> {
            val (mins, secs) = seconds / 60 to seconds % 60
            if (secs == 0) L("timeCompactMins", "$mins") else L("timeCompactMinsAndSecs", "$mins", "$secs")
        }
        seconds < 86400 -> {
            val (hours, mins) = seconds / 3600 to seconds % 3600 / 60
            if (mins == 0) L("timeCompactHours", "$hours") else L("timeCompactHoursAndMins", "$hours", "$mins")
        }
        else -> L("timeCompactDays", "${seconds / 86400}")
    }
}

@Composable
private fun label(quality: SignalQuality): String = when (quality) {
    SignalQuality.Excellent -> L("excellent")
    SignalQuality.Good -> L("good")
    SignalQuality.Fair -> L("fair")
    SignalQuality.Weak -> L("weak")
}

/** Excellent and good read as fine, fair as a warning, weak as trouble. */
@Composable
private fun color(quality: SignalQuality): Color = when (quality) {
    SignalQuality.Excellent, SignalQuality.Good -> DS.Palette.success
    SignalQuality.Fair -> DS.Palette.warning
    SignalQuality.Weak -> DS.Palette.live
}

/** `GlassCircleButton`'s look as a menu's label (the menu handles the tap). */
@Composable
private fun GlassCircleLabel(systemImage: String) {
    val dark = LocalOmiDark.current
    Box(
        Modifier
            .size(44.dp)
            .background(if (dark) hex(0x282828) else hex(0xF5F5F5), CircleShape)
            .border(1.dp, if (dark) hex(0x363636) else hex(0xE4E4E4), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        SFImage(systemImage, size = 21.sp, weight = FontWeight.Medium, tint = DS.Palette.ink)
    }
}

/**
 * `ShareLink(item: DiagnosticsJSON, preview: SharePreview(L("diagnosticsExportTitle")))`: the bundle
 * as an `omi_diagnostics.json` attachment (the features module's FileProvider, the cache dir).
 */
private fun share(context: Context, bundle: ByteArray, title: String) {
    runCatching {
        val file = java.io.File(context.cacheDir, "omi_diagnostics.json").apply { writeBytes(bundle) }
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(Intent.EXTRA_STREAM, com.friend.ios.features.conversations.fileUri(context, file))
            putExtra(Intent.EXTRA_TITLE, title)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(send, title).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
