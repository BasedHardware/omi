package com.friend.ios.features.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.FairUseStatus
import com.friend.ios.core.models.UsageStats
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.service.stores.UsageStore
import kotlinx.coroutines.launch
import java.text.NumberFormat

/** Port of `UsageScreens.swift`. What Omi heard in a period: minutes, words, insights, memories, and words per day. */
@Composable
@androidx.compose.runtime.NonRestartableComposable
fun OmiListBuilder.activitySection(store: UsageStore) {
    val scope = rememberCoroutineScope()
    LaunchedEffect(store.period) { store.load() }
    val periods = listOf(UsageStats.Period.Today, UsageStats.Period.Monthly, UsageStats.Period.Yearly, UsageStats.Period.AllTime)
    val titles = periods.map { periodTitle(it) }
    val stats = store.current
    val couldNotLoad = L("nativeCouldNotLoad")
    val empty = L("nativeUsageEmpty")
    section(header = L("nativeSettingsActivity")) {
        // `Picker(L("nativeUsagePeriod"))` with its label hidden: TalkBack still names it.
        val periodLabel = L("nativeUsagePeriod")
        row { Box(Modifier.semantics { contentDescription = periodLabel }) { OmiSegmentedPicker(titles, periods.indexOf(store.period)) { store.period = periods[it] } } }
        when {
            stats != null && stats.totals.isEmpty -> row { Text(empty, style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
            stats != null -> {
                row { Totals(stats.totals) }
                if (stats.history.size > 3) row { Chart(stats) }
            }
            store.period in store.failedPeriods -> row { RetryRow(couldNotLoad) { scope.launch { store.load() } } }
            else -> row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
        }
    }
}

@Composable
private fun periodTitle(period: UsageStats.Period): String = when (period) {
    UsageStats.Period.Today -> L("today")
    UsageStats.Period.Monthly -> L("usageMonth")
    UsageStats.Period.Yearly -> L("usageYear")
    UsageStats.Period.AllTime -> L("usageAll")
}

@Composable
private fun Totals(totals: UsageStats.Totals) {
    val number = NumberFormat.getIntegerInstance()
    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
            Number(L("nativeMinutesValue", "${totals.transcriptionSeconds / 60}"), L("nativeUsageListened"), Modifier.weight(1f))
            Number(number.format(totals.words), L("nativeUsageWords"), Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
            Number(number.format(totals.insights), L("nativeUsageInsights"), Modifier.weight(1f))
            Number(number.format(totals.memories), L("memories"), Modifier.weight(1f))
        }
    }
}

@Composable
private fun Number(value: String, label: String, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
        Text(value, style = DS.Typography.sectionTitle.copy(fontFeatureSettings = "tnum"), color = DS.Palette.ink)
        Text(label, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
    }
}

/** Words per bucket as ink bars, no axes (`Chart { BarMark }`). */
@Composable
private fun Chart(stats: UsageStats) {
    val ink = DS.Palette.ink
    val values = stats.history.map { it.second.words }
    val max = (values.maxOrNull() ?: 0).coerceAtLeast(1)
    Canvas(Modifier.fillMaxWidth().height(110.dp).padding(vertical = DS.Spacing.xs)) {
        val slot = size.width / values.size
        val barWidth = slot * 0.7f
        values.forEachIndexed { i, value ->
            val h = size.height * value / max
            drawRoundRect(ink, Offset(i * slot + (slot - barWidth) / 2, size.height - h), Size(barWidth, h), CornerRadius(3.dp.toPx()))
        }
    }
}

/** `ActivitySection.shareText`: the period's totals as a short note with omi.me. */
@Composable
fun activityShareText(totals: UsageStats.Totals, period: UsageStats.Period): String {
    val number = NumberFormat.getIntegerInstance()
    val lines = mutableListOf(L("nativeUsageShareTitle", periodTitle(period)))
    if (totals.transcriptionSeconds >= 60) lines += "🎧 " + L("nativeUsageShareMinutes", "${totals.transcriptionSeconds / 60}")
    if (totals.words > 0) lines += "💬 " + L("nativeUsageShareWords", number.format(totals.words))
    if (totals.insights > 0) lines += "💡 " + L("nativeUsageShareInsights", number.format(totals.insights))
    if (totals.memories > 0) lines += "🧠 " + L("nativeUsageShareMemories", number.format(totals.memories))
    return (lines + "omi.me").joinToString("\n")
}

/** Speech hours against today's, three days' and the week's fair-use limits, and the server's note. */
@Composable
@androidx.compose.runtime.NonRestartableComposable
fun OmiListBuilder.fairUseSection(store: UsageStore) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val status = store.fairUse
    val loadError = L("nativeFairUseLoadError")
    section(header = L("nativeFairUseTitle"), footer = L("fairUseAboutBody")) {
        when {
            status != null -> {
                if (status.stage != "none") {
                    row {
                        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
                            SFImage("exclamationmark.triangle.fill", tint = DS.Palette.warning)
                            Text(stageTitle(status.stage), style = DS.Typography.body, color = DS.Palette.warning)
                        }
                    }
                    status.caseReference?.let { reference ->
                        row(onClick = {
                            (context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText(null, reference))
                            haptics.success()
                        }) { SettingsLabeledContent(L("nativeCaseReference"), reference) }
                    }
                }
                row { FairUseMeter(L("fairUseToday"), status.today) }
                row { FairUseMeter(L("nativeFairUseThreeDays"), status.threeDays) }
                row { FairUseMeter(L("nativeFairUseWeek"), status.week) }
                if (status.message.isNotEmpty()) row { Text(status.message, style = DS.Typography.callout, color = DS.Palette.ink) }
            }
            store.fairUseFailed -> row { RetryRow(loadError) { scope.launch { store.loadFairUse() } } }
            else -> row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
        }
    }
}

@Composable
private fun stageTitle(stage: String): String = when (stage) {
    "throttle" -> L("fairUseStageThrottle")
    "restrict" -> L("fairUseStageRestrict")
    else -> L("fairUseStageWarning")
}

@Composable
private fun FairUseMeter(title: String, window: FairUseStatus.Window) {
    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        SettingsLabeledContent(title, L("nativeHoursOfHours", fairUseHours(window.usedHours), fairUseHours(window.limitHours)))
        val tint = when {
            window.percent >= 100 -> DS.Palette.live
            window.percent >= 80 -> DS.Palette.warning
            else -> DS.Palette.ink
        }
        OmiMeterBar(minOf(window.percent, 100.0) / 100, tint, Modifier.fillMaxWidth())
    }
}

/** `FairUseSection.hours`: at most one decimal. */
fun fairUseHours(value: Double): String = NumberFormat.getNumberInstance().apply { maximumFractionDigits = 1; minimumFractionDigits = 0 }.format(value)

/** A row saying what failed, with Try again (never an endless spinner). */
@Composable
fun RetryRow(message: String, action: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically) {
            SFImage("wifi.exclamationmark", tint = DS.Palette.inkSecondary)
            Text(message, style = DS.Typography.body, color = DS.Palette.inkSecondary)
        }
        // `.buttonStyle(.bordered)` capsule in ink.
        Text(
            L("tryAgain"),
            style = TextStyles.subheadline.semibold(),
            color = DS.Palette.ink,
            modifier = Modifier.plainButton(onClick = action).background(DS.Palette.fill, CircleShape).padding(horizontal = DS.Spacing.md, vertical = 6.dp),
        )
    }
}

/**
 * `Picker(...).pickerStyle(.segmented)` in the iOS 26 look (measured): a capsule track in the
 * fill color, the chosen segment a lighter capsule that slides.
 */
@Composable
fun OmiSegmentedPicker(titles: List<String>, selected: Int, textStyle: androidx.compose.ui.text.TextStyle = DS.Typography.body, onSelect: (Int) -> Unit) {
    val haptics = rememberHaptics()
    val dark = LocalOmiDark.current
    val track = if (dark) hex(0x3A3A3C) else hex(0xEEEEEF)
    val thumb = if (dark) hex(0x636366) else hex(0xFFFFFF)
    BoxWithConstraints(Modifier.fillMaxWidth().height(32.dp).background(track, CircleShape).padding(2.dp)) {
        val segment = maxWidth / titles.size.coerceAtLeast(1)
        val offset by animateDpAsState(segment * selected, label = "segment")
        Box(Modifier.offset(x = offset).width(segment).fillMaxHeight().background(thumb, CircleShape))
        Row(Modifier.fillMaxWidth().fillMaxHeight()) {
            titles.forEachIndexed { index, title ->
                Box(
                    Modifier.weight(1f).fillMaxHeight().plainButton {
                        haptics.selection()
                        onSelect(index)
                    },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(title, style = if (index == selected) textStyle.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium) else textStyle, color = DS.Palette.ink, textAlign = TextAlign.Center, maxLines = 1)
                }
            }
        }
    }
}
