package com.friend.ios.features.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiCardSurface
import com.friend.ios.design.plainButton
import androidx.compose.runtime.rememberCoroutineScope
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.LocalSyncStore
import com.friend.ios.service.stores.SyncStore
import kotlinx.coroutines.launch
import com.friend.ios.service.stores.CaptureNotice
import com.friend.ios.service.stores.CaptureRecovery
import com.friend.ios.service.stores.dismissNotice
import com.friend.ios.service.stores.dismissRecovery
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Port of `CaptureRecoveryBanner.swift`: Home's notice when a recording did not end as meant
 * (Flutter `capture_recovery_banner`): the app was closed while recording, the connection dropped
 * and the phone kept the audio, or the system took the microphone away while the recording is
 * still running.
 */
@Composable
fun CaptureRecoveryBanner(modifier: Modifier = Modifier) {
    val capture = LocalCaptureStore.current
    val recovery = capture.recovery
    val notice = capture.notice
    if (recovery == null && notice == null) return
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        if (recovery != null) RecoveryCard(recovery)
        if (notice != null) NoticeCard(notice)
    }
}

/** A recording that did not end the way it was meant to: what happened, and what can be done. */
@Composable
private fun RecoveryCard(recovery: CaptureRecovery) {
    val capture = LocalCaptureStore.current
    val sync = LocalSyncStore.current
    val scope = rememberCoroutineScope()
    CardShell(
        icon = icon(recovery),
        title = title(recovery, capture.isLive),
        message = message(recovery, capture.isLive),
        onDismiss = { capture.dismissRecovery() },
    ) {
        if (recovery is CaptureRecovery.Interrupted && !capture.isLive) {
            OmiPillButton(L("nativeRecoveryRecordAgain")) {
                capture.dismissRecovery()
                capture.perform { startPhone() }
            }
        }
        if (sync.status != SyncStore.Status.Synced && !capture.isLive && sync.hasPending) {
            OmiPillButton(L("nativeRecoveryUploadNow"), prominent = false) { scope.launch { sync.uploadPending() } }
        }
    }
}

/**
 * The recording is still running: the system has the microphone and the app is asking for it back
 * every few seconds, so this only says why it is quiet.
 */
@Composable
private fun NoticeCard(notice: CaptureNotice) {
    val capture = LocalCaptureStore.current
    CardShell(
        icon = "mic.slash",
        title = L("nativeNoticeCapturePaused"),
        message = if (notice is CaptureNotice.InputGone) {
            L("nativeNoticeInputGoneMessage")
        } else {
            L("nativeNoticeMicrophoneTakenMessage")
        },
        onDismiss = { capture.dismissNotice() },
        buttons = {},
    )
}

/** The words and the identity of one notice card; [CardShell] only lays them out. */
@Composable
private fun CardShell(
    icon: String,
    title: String,
    message: String,
    onDismiss: () -> Unit,
    buttons: @Composable () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().omiCardSurface().padding(DS.Spacing.lg),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        verticalAlignment = Alignment.Top,
    ) {
        Box(Modifier.width(24.dp), contentAlignment = Alignment.Center) {
            SFImage(icon, size = 17.sp, weight = FontWeight.SemiBold, tint = DS.Palette.warning)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
            Text(title, style = DS.Typography.cardTitle, color = DS.Palette.ink)
            Text(message, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            Row(Modifier.padding(top = DS.Spacing.xxs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                buttons()
            }
        }
        Spacer(Modifier.width(0.dp))
        Box(Modifier.plainButton { onDismiss() }) {
            SFImage("xmark", size = 12.sp, weight = FontWeight.Bold, tint = DS.Palette.inkTertiary, contentDescription = L("close"))
        }
    }
}

private fun icon(recovery: CaptureRecovery): String = when (recovery) {
    is CaptureRecovery.Interrupted -> "exclamationmark.triangle.fill"
    CaptureRecovery.ConnectionLost -> "wifi.exclamationmark"
}

@Composable
private fun title(recovery: CaptureRecovery, isLive: Boolean): String = when (recovery) {
    is CaptureRecovery.Interrupted -> L("nativeRecoveryInterruptedTitle")
    CaptureRecovery.ConnectionLost -> L(if (isLive) "nativeRecoveryOfflineTitle" else "nativeRecoveryOfflineSavedTitle")
}

@Composable
private fun message(recovery: CaptureRecovery, isLive: Boolean): String = when (recovery) {
    is CaptureRecovery.Interrupted -> L(
        "nativeRecoveryInterruptedMessage",
        DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).format(Instant.ofEpochMilli(recovery.sinceMillis).atZone(ZoneId.systemDefault())),
    )
    CaptureRecovery.ConnectionLost -> L(if (isLive) "nativeRecoveryOfflineMessage" else "nativeRecoveryOfflineSavedMessage")
}
