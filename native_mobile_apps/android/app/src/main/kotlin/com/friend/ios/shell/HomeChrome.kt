package com.friend.ios.shell

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.service.LocalCaptureStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPendantThumbnail
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.design.DSHaptics

/**
 * Port of `DevicePill` (`HomeChrome.swift`): "Connect" without a device, name and battery while
 * connected, otherwise the connection state (tap: My Omi); a red dot while live, a small accent dot
 * while offline recordings wait to sync.
 */
@Composable
fun DevicePill(modifier: Modifier = Modifier) {
    val devices = com.friend.ios.service.LocalDeviceStore.current
    val capture = LocalCaptureStore.current
    val sync = com.friend.ios.service.LocalSyncStore.current
    val connected = devices.connection == com.friend.ios.service.stores.DeviceStore.Connection.Connected
    val paired = devices.paired
    val label = when {
        paired == null -> L("connect")
        connected -> paired.name
        // Tapping opens My Omi, which explains what to check and can try again.
        devices.connection == com.friend.ios.service.stores.DeviceStore.Connection.Connecting -> L("nativeConnecting")
        else -> L("nativeNotConnected")
    }
    // The pendant itself, with a small status dot: red while recording, green when connected, none when away.
    val statusColor = when {
        capture.isLive -> DS.Palette.live
        connected -> DS.Palette.success
        else -> null
    }
    val battery = if (connected) devices.battery?.let { "$it%" } else null
    val background = DS.Palette.background
    Box(modifier) {
        HStack(Modifier.heightIn(min = DS.Size.headerButton), spacing = DS.Spacing.sm) {
            Box {
                OmiPendantThumbnail(26.dp, Modifier.alpha(if (connected) 1f else 0.45f))
                if (statusColor != null) {
                    Box(
                        Modifier.align(Alignment.BottomEnd).size(8.dp)
                            .background(statusColor, CircleShape)
                            .border(1.5.dp, background, CircleShape),
                    )
                }
            }
            Text(label, style = TextStyles.body.semibold(), color = DS.Palette.ink, maxLines = 1)
            if (battery != null) Text(battery, style = TextStyles.subheadline.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
            SFImage("chevron.down", size = 11.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
        }
        // A small accent dot while offline recordings wait to sync.
        if (sync.hasPending) {
            Box(Modifier.align(Alignment.TopEnd).offset(x = 6.dp).size(7.dp).background(DS.Palette.agent, CircleShape))
        }
    }
}

/** Port of `OmiBottomBar`: "Ask Omi" with a mic, and the round record button beside it. */
@Composable
fun OmiBottomBar(onAsk: () -> Unit, onDictate: () -> Unit, onRecordWith: () -> Unit, modifier: Modifier = Modifier) {
    val shape = ContinuousRoundedShape(28.dp)
    // One rounded composer, as in the ChatGPT app: the prompt, the mic, and the record button as
    // the filled circle at the end.
    HStack(
        modifier
            .padding(horizontal = DS.Spacing.gutter)
            .padding(top = DS.Spacing.sm, bottom = DS.Spacing.xs)
            .fillMaxWidth()
            .heightIn(min = DS.Size.omiBarHeight)
            .background(DS.Palette.cardRaised, shape)
            .border(1.dp, DS.Palette.cardStroke, shape)
            .padding(start = DS.Spacing.lg + 2.dp, end = DS.Spacing.sm),
        spacing = DS.Spacing.xs,
    ) {
        Box(Modifier.weight(1f).heightIn(min = DS.Size.omiBarHeight).plainButton(onClick = onAsk), contentAlignment = Alignment.CenterStart) {
            Text(L("askOmi"), style = DS.Typography.body, color = DS.Palette.inkTertiary)
        }
        Box(Modifier.size(40.dp).pressable(onClick = onDictate), contentAlignment = Alignment.Center) {
            SFImage("mic", size = 18.sp, tint = DS.Palette.ink, contentDescription = L("nativeAskByVoice"))
        }
        RecordButton(onRecordWith)
    }
    CaptureDebugHooks()
}

/** Tap: record with the phone (or stop); long press: choose the phone or the Omi. */
@Composable
private fun RecordButton(onRecordWith: () -> Unit) {
    val capture = LocalCaptureStore.current
    val haptics = rememberHaptics()
    val isLive = capture.isLive
    val stopLabel = L("nativeStopRecording")
    val recordLabel = L("nativeRecordWithPhone")
    val recordWith = L("nativeRecordWith")
    Box(
        Modifier.size(40.dp)
            // A button for TalkBack too: a double tap records (or stops), "Record with" as an action.
            .semantics {
                role = Role.Button
                contentDescription = if (isLive) stopLabel else recordLabel
                onClick {
                    capture.perform { if (isLive) stop() else startPhone() }
                    true
                }
                customActions = listOf(
                    CustomAccessibilityAction(recordWith) {
                        if (!capture.isLive) onRecordWith()
                        true
                    },
                )
            }
            .pointerInput(Unit) {
                detectTapGestures(
                    onTap = {
                        haptics.tap(DSHaptics.Style.Medium)
                        capture.perform { if (isLive) stop() else startPhone() }
                    },
                    onLongPress = {
                        if (!capture.isLive) {
                            haptics.tap(DSHaptics.Style.Medium)
                            onRecordWith()
                        }
                    },
                )
            }
            .background(DS.Palette.ink, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        if (isLive) Box(Modifier.size(13.dp).background(DS.Palette.onAccent, RoundedCornerShape(3.dp)))
        else Box(Modifier.size(14.dp).background(DS.Palette.live, CircleShape))
    }
}

/**
 * `-omiStartCapture YES` (`DebugHooks.swift`): starts a phone recording once the shell is up, and
 * `-omiCaptureSeconds n` stops it after n seconds.
 */
@Composable
private fun CaptureDebugHooks() {
    val capture = LocalCaptureStore.current
    val session = com.friend.ios.service.LocalSessionStore.current
    LaunchedEffect(Unit) {
        if (!DebugLaunch.flag("omiStartCapture") || debugCaptureStarted) return@LaunchedEffect
        debugCaptureStarted = true
        // Once signed in (the shell can show before the session has its user).
        androidx.compose.runtime.snapshotFlow { session.userID }.first { it != null }
        capture.startPhone()
        DebugLaunch.string("omiCaptureSeconds")?.toLongOrNull()?.takeIf { it > 0 }?.let {
            delay(it * 1000)
            capture.stop()
        }
    }
}

/** Once per process: the bar recomposes (and its effect restarts) when it fades out and back in. */
private var debugCaptureStarted = false

/** `OmiBottomBar.height`: what the bar covers above the bottom safe area. */
val OmiBottomBarHeight: Dp = DS.Size.omiBarHeight + DS.Spacing.sm + DS.Spacing.xs
