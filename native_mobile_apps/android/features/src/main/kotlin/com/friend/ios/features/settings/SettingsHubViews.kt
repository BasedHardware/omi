package com.friend.ios.features.settings

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import com.friend.ios.core.models.Subscription
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPendantThumbnail
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.pressable
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.PlanCatalog
import com.friend.ios.service.stores.SettingsHub
import com.friend.ios.service.stores.UsageMeter

/** `PlanUsageScreen.planName`: the plan's name, "Free" on the free plan. */
@Composable
fun planName(subscription: Subscription): String = PlanCatalog.paidPlanName(subscription) ?: L("nativePlanFree")

/**
 * Port of `SettingsHubViews.swift`. The top of Settings: who is signed in, large, with email and
 * plan on one quiet line (and Upgrade on the free plan). Tapping it opens Account.
 */
@Composable
fun SettingsProfileHeader(onOpenAccount: () -> Unit, onUpgrade: () -> Unit) {
    val settings = LocalSettingsStore.current
    val session = LocalSessionStore.current
    val rawName = settings.displayName ?: session.displayName
    val email = settings.email
    val name = SettingsHub.headline(rawName, email) ?: L("account")
    val subscription = settings.subscription
    Row(
        Modifier.fillMaxWidth().padding(top = DS.Spacing.xs, bottom = DS.Spacing.lg),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
    ) {
        Row(
            Modifier.weight(1f).pressable(pressedScale = 1f, pressedAlpha = 0.7f, haptic = false, onClick = onOpenAccount),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        ) {
            Box(Modifier.size(52.dp).background(DS.Palette.card, CircleShape), contentAlignment = Alignment.Center) {
                Text(SettingsHub.initials(rawName, email), style = DS.Typography.sectionTitle, color = DS.Palette.ink)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                Text(name, style = DS.Typography.largeTitle, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    if (email != null) {
                        Text(
                            middleTruncated(email, if (subscription != null) 18 else 32),
                            style = DS.Typography.callout,
                            color = DS.Palette.inkSecondary,
                            maxLines = 1,
                            modifier = Modifier.weight(1f, fill = false),
                        )
                    }
                    if (subscription != null) {
                        Text(
                            planName(subscription),
                            style = DS.Typography.micro,
                            color = DS.Palette.inkSecondary,
                            maxLines = 1,
                            modifier = Modifier.background(DS.Palette.fill, CircleShape).padding(horizontal = DS.Spacing.sm, vertical = 3.dp),
                        )
                    }
                }
            }
        }
        if (subscription != null && SettingsHub.isFree(subscription) && subscription.showSubscriptionUI) {
            OmiPillButton(L("upgrade"), onClick = onUpgrade)
        }
    }
}

/** `.truncationMode(.middle)` for one line of known-short text (an email). */
internal fun middleTruncated(text: String, max: Int): String {
    if (text.length <= max) return text
    val head = (max - 1) / 2 + 1
    val tail = max - 1 - head
    return text.take(head) + "…" + text.takeLast(tail)
}

/** Four live tiles under the header: the Omi, the plan, apps, voices. Each opens its screen. */
@Composable
fun SettingsHubTiles(onOpen: (SettingsTopic) -> Unit) {
    val settings = LocalSettingsStore.current
    // The Omi tile's state (and-device): `omiState()` reads DeviceStore and capture.
    val state = com.friend.ios.features.device.omiState()
    Column(Modifier.fillMaxWidth().padding(bottom = DS.Spacing.sm), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Max), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            val omiValue = omiStatusShort(state)
            HubTile(com.friend.ios.service.LocalDeviceStore.current.paired?.name ?: "Omi", SettingsTopic.Devices, onOpen, Modifier.weight(1f), spokenValue = omiValue, glyph = {
                Box {
                    OmiPendantThumbnail(30.dp, Modifier.alpha(if (state.isConnected) 1f else 0.45f))
                    OmiStatusDot(state.dot, Modifier.align(Alignment.BottomEnd))
                }
            }) { Text(omiValue) }
            val subscription = settings.subscription
            val meter = subscription?.let { SettingsHub.busiestMeter(PlanCatalog.meters(it)) }
            val fraction = meter?.fraction
            val spoken = fraction?.let { L("nativeHubPercentUsed", "${SettingsHub.percent(it)}%") } ?: ""
            HubTile(subscription?.let { planName(it) } ?: L("nativePlan"), SettingsTopic.PlanUsage, onOpen, Modifier.weight(1f), spokenValue = spoken, glyph = { HubGlyph("chart.bar") }) {
                if (meter != null && fraction != null) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                        OmiMeterBar(fraction, meterTint(meter), Modifier.widthIn(max = 72.dp).weight(1f, fill = false).width(72.dp))
                        Text("${SettingsHub.percent(fraction)}%", style = DS.Typography.callout.copy(fontFeatureSettings = "tnum"))
                    }
                } else {
                    Text(L("nativeSettingsPlanUsage"))
                }
            }
        }
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Max), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            // Reminders has no Android counterpart.
            val health = com.friend.ios.service.LocalAppleHealthStore.current
            val count = SettingsHub.connectedApps(com.friend.ios.service.LocalCapabilitiesStore.current.connectedCount, health = health.isConnected, reminders = false)
            val apps = if (count == 0) L("nativeHubConnectApps") else L("nativeHubConnectedCount", "$count")
            HubTile(L("nativeHubApps"), SettingsTopic.Apps, onOpen, Modifier.weight(1f), spokenValue = apps, glyph = { HubGlyph("square.grid.2x2") }) { Text(apps) }
            val people = settings.people.size
            val voices = when (people) {
                0 -> L("nativeHubNoPeople")
                1 -> L("nativeHubOnePerson")
                else -> L("nativeHubPeopleCount", "$people")
            }
            HubTile(L("nativeHubVoices"), SettingsTopic.Voices, onOpen, Modifier.weight(1f), spokenValue = voices, glyph = { HubGlyph("person.2") }) { Text(voices) }
        }
    }
}

/** Ink, amber near the limit, red at it (as on Plan & usage). */
@Composable
private fun meterTint(meter: UsageMeter): Color = when {
    meter.isAtLimit -> DS.Palette.live
    meter.isNearLimit -> DS.Palette.warning
    else -> DS.Palette.ink
}

/** One tile: a thin glyph on top, the title, one live line under it, on the raised card color. Sinks a little under the finger. */
@Composable
private fun HubTile(
    title: String,
    topic: SettingsTopic,
    onOpen: (SettingsTopic) -> Unit,
    modifier: Modifier,
    /** `.accessibilityValue`: the tile reads as its title and this, as one button. */
    spokenValue: String,
    glyph: @Composable () -> Unit,
    value: @Composable () -> Unit,
) {
    val shape = ContinuousRoundedShape(DS.Radius.card)
    Column(
        modifier
            .fillMaxHeight()
            .heightIn(min = 112.dp)
            .pressable(pressedScale = 0.97f, pressedAlpha = 0.85f, haptic = false) { onOpen(topic) }
            // The press above stays the button; what is inside reads as its title and value.
            .clearAndSetSemantics {
                contentDescription = title
                stateDescription = spokenValue
            }
            .background(DS.Palette.card, shape)
            .padding(DS.Spacing.lg),
    ) {
        Box(Modifier.height(30.dp), contentAlignment = Alignment.CenterStart) { glyph() }
        Spacer(Modifier.weight(1f).heightIn(min = DS.Spacing.md))
        Text(title, style = DS.Typography.body.semibold(), color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Box(Modifier.padding(top = DS.Spacing.xxs).height(20.dp), contentAlignment = Alignment.CenterStart) {
            androidx.compose.runtime.CompositionLocalProvider(
                androidx.compose.material3.LocalTextStyle provides DS.Typography.callout.copy(color = DS.Palette.inkSecondary),
                androidx.compose.material3.LocalContentColor provides DS.Palette.inkSecondary,
            ) { value() }
        }
    }
}

/** A tile's thin line glyph. */
@Composable
private fun HubGlyph(systemImage: String) {
    SFImage(systemImage, size = 21.sp, weight = FontWeight.Light, tint = DS.Palette.ink)
}

/** `OmiStatusDot`: red while listening, green while connected, none while away. */
@Composable
fun OmiStatusDot(dot: SettingsHub.OmiState.Dot, modifier: Modifier = Modifier, size: Dp = 9.dp, ring: Color = DS.Palette.card, showsOff: Boolean = false) {
    val color = when (dot) {
        SettingsHub.OmiState.Dot.Live -> DS.Palette.live
        SettingsHub.OmiState.Dot.Connected -> DS.Palette.success
        SettingsHub.OmiState.Dot.Off -> if (showsOff) DS.Palette.inkTertiary else null
    } ?: return
    Box(modifier.size(size).background(ring, CircleShape).padding(size / 6).background(color, CircleShape))
}

/** `OmiStatusText.short`: the Omi's state in words ("76% · Listening", "Not connected", "Get an Omi"). */
@Composable
fun omiStatusShort(state: SettingsHub.OmiState): String = when (state) {
    SettingsHub.OmiState.None -> L("nativeGetAnOmi")
    SettingsHub.OmiState.NotConnected -> L("nativeNotConnected")
    SettingsHub.OmiState.Connecting -> L("nativeConnecting")
    is SettingsHub.OmiState.Connected -> {
        val doing = when (state.activity) {
            SettingsHub.OmiState.Activity.Listening -> L("nativeOmiListening")
            SettingsHub.OmiState.Activity.Paused -> L("nativePaused")
            SettingsHub.OmiState.Activity.Idle -> L("nativeConnected")
        }
        listOfNotNull(state.battery?.let { "$it%" }, doing).joinToString(" · ")
    }
}

/** `OmiMeterBar`: a thin rounded meter, the used share in [tint] on the quiet fill. */
@Composable
fun OmiMeterBar(fraction: Double, tint: Color = DS.Palette.ink, modifier: Modifier = Modifier) {
    BoxWithConstraints(modifier.height(4.dp).background(DS.Palette.fill, CircleShape)) {
        val share = fraction.coerceIn(0.0, 1.0).toFloat()
        val width = if (share > 0) maxOf(4.dp, maxWidth * share) else 0.dp
        Box(Modifier.width(width).height(4.dp).background(tint, CircleShape))
    }
}
