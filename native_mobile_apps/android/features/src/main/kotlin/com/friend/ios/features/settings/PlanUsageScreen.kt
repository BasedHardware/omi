package com.friend.ios.features.settings

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.friend.ios.core.models.Subscription
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.PlanStore
import com.friend.ios.service.stores.UsageMeter
import com.friend.ios.service.stores.makePlanStore
import com.friend.ios.service.stores.makeProfileStore
import com.friend.ios.service.stores.makeUsageStore
import kotlinx.coroutines.launch
import java.text.NumberFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * Port of `PlanUsageScreen.swift`. Account > Plan & usage, one screen for Flutter's `usage_page`,
 * plans sheet and `fair_use_page`: the plan (renews or ends when), this month's meters against its
 * limits, the plans to choose from with Monthly or Yearly and the one button that upgrades (paid on
 * Stripe's page, opened in the browser), payment method and cancelling, then what Omi heard and
 * the fair-use limits.
 */
@Composable
fun PlanUsageScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val store = remember { settings.makePlanStore() }
    val usage = remember { settings.makeUsageStore() }
    /** The open page is Stripe's (checkout or portal): coming back reads the plan again. */
    var browsing by remember { mutableStateOf<Boolean?>(null) }
    var showsCancel by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        store.load()
        usage.loadFairUse()
    }
    // Back from Stripe (checkout or portal): the plan may have changed (`SafariView` onDismiss).
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            val wasCheckout = browsing
            if (event == Lifecycle.Event.ON_RESUME && wasCheckout != null) {
                browsing = null
                scope.launch {
                    if (wasCheckout) store.returnedFromCheckout() else store.load()
                    settings.loadSubscription()
                }
            }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    fun open(url: String, checkout: Boolean) {
        browsing = checkout
        runCatching { uriHandler.openUri(url) }
    }

    val stats = usage.current
    val shareText = stats?.takeIf { !it.totals.isEmpty }?.let { activityShareText(it.totals, usage.period) }
    SettingsListPage(
        L("nativeSettingsPlanUsage"),
        onBack,
        trailing = { if (shareText != null) GlassCircleButton("square.and.arrow.up", contentDescription = L("share")) { shareText(context, shareText) } },
    ) {
        planSummarySection(store)
        val subscription = store.subscription
        if (subscription != null) {
            if (store.meters.isNotEmpty()) metersSection(store, subscription)
            if (subscription.showSubscriptionUI) planPickerSection(store) { open(it, checkout = true) }
            manageSection(store, subscription, onPortal = { open(it, checkout = false) }, onCancel = { showsCancel = true })
        } else if (store.failed) {
            section { row { RetryRow(L("nativeCouldNotLoad")) { scope.launch { store.load() } } } }
        } else {
            section { row { Box(Modifier.fillMaxWidth().heightIn(min = 80.dp), contentAlignment = Alignment.Center) { OmiProgress() } } }
        }
        activitySection(usage)
        fairUseSection(usage)
    }
    if (showsCancel) {
        CancelSubscriptionSheet(remember { settings.makeProfileStore() }) {
            showsCancel = false
            scope.launch {
                store.load()
                settings.loadSubscription()
            }
        }
    }
}

/** Payment method and invoices (Stripe's portal), and cancelling a running plan. */
@Composable
@androidx.compose.runtime.NonRestartableComposable
private fun OmiListBuilder.manageSection(store: PlanStore, subscription: Subscription, onPortal: (String) -> Unit, onCancel: () -> Unit) {
    if (!(subscription.isPaid || subscription.hasStripeSubscription)) return
    val scope = rememberCoroutineScope()
    val manage = L("nativePlanManage")
    val cancel = L("nativeCancelSubscription")
    section {
        row(onClick = { scope.launch { store.portalURL()?.let(onPortal) } }, separatorInset = OmiListMetrics.iconSeparatorInset) {
            SettingsRowLabel(manage, "creditcard", Modifier.weight(1f))
            SettingsExternalArrow()
        }
        if (subscription.isPaid && !subscription.cancelAtPeriodEnd) {
            row(onClick = onCancel, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(cancel, "xmark.circle", tint = DS.Palette.live, titleColor = DS.Palette.live)
            }
        }
    }
}

/**
 * The plan as the page's headline, as Home shows its title: the name big, one gray line under it
 * (renews, ends, or what the free plan includes), and what the last action did.
 */
@Composable
@androidx.compose.runtime.NonRestartableComposable
private fun OmiListBuilder.planSummarySection(store: PlanStore) {
    val name = store.subscription?.let { planName(it) } ?: " "
    val line = statusLine(store)
    section {
        plainRow {
            Column(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.lg).padding(bottom = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                Text(L("nativePlanYourPlan"), style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary)
                Text(name, style = DS.Typography.display, color = DS.Palette.ink)
                if (line != null) Text(line.first, style = DS.Typography.callout, color = if (line.second) DS.Palette.warning else DS.Palette.inkSecondary)
            }
        }
        store.notice?.let { notice -> row { NoticeRow(notice) { store.dismissNotice() } } }
    }
}

@Composable
private fun statusLine(store: PlanStore): Pair<String, Boolean>? {
    val subscription = store.subscription ?: return null
    if (!subscription.isPaid) return L("nativePlanFreeLine") to false
    val price = store.tiers.firstOrNull { it.isCurrent }?.let { tier -> listOfNotNull(tier.monthly, tier.annual).firstOrNull { it.isActive } }
    val end = subscription.currentPeriodEnd ?: return price?.let { it.priceString to false }
    val date = longDate(end)
    if (subscription.cancelAtPeriodEnd) {
        return (if (end.isBefore(Instant.now())) L("nativePlanEndedOn", date) else L("nativePlanEndsOn", date)) to true
    }
    val renews = L("nativePlanRenewsOn", date)
    return (price?.let { "${it.priceString} · $renews" } ?: renews) to false
}

/** `.formatted(date: .long, time: .omitted)`. */
internal fun longDate(instant: Instant): String =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(Locale.getDefault()).format(instant.atZone(ZoneId.systemDefault()))

/** `.formatted(.dateTime.month(.wide).day())`. */
internal fun monthDay(instant: Instant): String {
    val pattern = android.text.format.DateFormat.getBestDateTimePattern(Locale.getDefault(), "MMMMd")
    return DateTimeFormatter.ofPattern(pattern, Locale.getDefault()).format(instant.atZone(ZoneId.systemDefault()))
}

/** One line saying what the last action did: green when it worked, red when it did not. */
@Composable
private fun NoticeRow(notice: PlanStore.Notice, onDismiss: () -> Unit) {
    val isError = notice is PlanStore.Notice.Refused || notice is PlanStore.Notice.Unreachable
    val text = when (notice) {
        is PlanStore.Notice.Upgraded -> L("nativePlanNoticeUpgraded", notice.plan)
        is PlanStore.Notice.Reactivated -> notice.message ?: L("nativePlanNoticeReactivated")
        is PlanStore.Notice.Changed -> notice.message ?: L("nativePlanNoticeChanged")
        is PlanStore.Notice.Refused -> notice.reason
        PlanStore.Notice.Unreachable -> L("nativePlanNoticeUnreachable")
    }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        SFImage(if (isError) "exclamationmark.circle" else "checkmark.circle", tint = if (isError) DS.Palette.live else DS.Palette.success)
        Text(text, style = DS.Typography.callout, color = DS.Palette.ink, modifier = Modifier.weight(1f))
        SFImage("xmark", size = 13.sp, tint = DS.Palette.inkTertiary, modifier = Modifier.plainButton(onClick = onDismiss), contentDescription = L("close"))
    }
}

/**
 * This month against the plan's limits: listening minutes, chat questions, and words or insights
 * where the plan limits them. A thin bar under each, amber from 80 %, red at the limit.
 */
@Composable
@androidx.compose.runtime.NonRestartableComposable
private fun OmiListBuilder.metersSection(store: PlanStore, subscription: Subscription) {
    val resets = subscription.usage.resetsAt?.let(::monthDay)
    val footer = when {
        subscription.isOutOfMinutes && resets != null -> L("nativeMeterMinutesUsedUp", resets)
        resets != null -> L("nativePlanResetsOn", resets)
        else -> null
    }
    section(header = L("nativePlanThisMonth"), footer = footer) {
        store.meters.forEach { meter ->
            row(key = meter.kind) {
                Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(meterTitle(meter.kind), style = DS.Typography.body, color = DS.Palette.ink)
                        Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
                        Text(meterValue(meter), style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
                    }
                    meter.fraction?.let { OmiMeterBar(it, usageMeterTint(meter), Modifier.fillMaxWidth()) }
                }
            }
        }
    }
}

@Composable
private fun usageMeterTint(meter: UsageMeter): Color = when {
    meter.isAtLimit -> DS.Palette.live
    meter.isNearLimit -> DS.Palette.warning
    else -> DS.Palette.ink
}

@Composable
private fun meterTitle(kind: UsageMeter.Kind): String = when (kind) {
    UsageMeter.Kind.Listening -> L("nativeMeterListening")
    UsageMeter.Kind.Chat -> L("nativeMeterChat")
    UsageMeter.Kind.ChatSpend -> L("nativeMeterChatSpend")
    UsageMeter.Kind.Words -> L("nativeMeterWords")
    UsageMeter.Kind.Insights -> L("nativeMeterInsights")
}

@Composable
private fun meterValue(meter: UsageMeter): String {
    val used = formatMeter(meter.used, meter.kind)
    val limit = meter.limit ?: return L("nativeMeterNoLimit", used)
    return if (meter.kind == UsageMeter.Kind.Listening) L("nativeMeterOfMinutes", used, formatMeter(limit, meter.kind))
    else L("nativeMeterOf", used, formatMeter(limit, meter.kind))
}

private fun formatMeter(value: Double, kind: UsageMeter.Kind): String =
    if (kind == UsageMeter.Kind.ChatSpend) usd(value, maxFraction = 2) else NumberFormat.getIntegerInstance().format(Math.round(value))

/** Prices are US dollars written the backend's way ("$161.91"), whatever the region (`PlanCard.usd`). */
internal fun usd(value: Double, maxFraction: Int = 2): String =
    NumberFormat.getCurrencyInstance(Locale.US).apply {
        minimumFractionDigits = 0
        maximumFractionDigits = maxFraction
    }.format(value)

/** `ShareLink(item: text)`: the system share sheet. */
internal fun shareText(context: Context, text: String) {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text)
    runCatching { context.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}
