package com.friend.ios.features.device

import android.text.format.Formatter
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.settings.OmiMeterBar
import com.friend.ios.features.settings.SettingsLabeledContent
import com.friend.ios.features.settings.SettingsListPage
import com.friend.ios.service.LocalSyncStore
import com.friend.ios.service.stores.SyncStore
import com.friend.ios.service.stores.deviceRecordings
import kotlin.math.roundToInt

/**
 * Port of `DeviceRecordingsRow.swift`: My Omi › Recordings on your Omi, one row with how many
 * wait (or how the sync is going); it opens the page with how full the Omi's storage is and the
 * recordings themselves. Syncing itself stays automatic.
 */
@Composable
fun OmiListBuilder.deviceRecordingsRow(onOpen: () -> Unit) {
    val sync = LocalSyncStore.current
    section {
        row(onClick = onOpen, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
            DeviceRow(L("nativeRecordingsOnOmi"), "waveform")
            Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
            // The count waiting on the Omi; while syncing, how far along it is.
            val status = sync.status
            val value = if (status is SyncStore.Status.Syncing) "${(status.progress * 100).toInt()}%" else "${sync.deviceRecordings.size}"
            Text(value, style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
        }
    }
}

/** The recordings on the Omi: the sync line, storage, then each recording. */
@Composable
fun DeviceRecordingsScreen(onBack: () -> Unit) {
    val sync = LocalSyncStore.current
    val context = LocalContext.current
    // One player for the page: a new recording stops the one playing; leaving stops it.
    val player = com.friend.ios.features.components.rememberAudioClipPlayer()
    androidx.compose.runtime.DisposableEffect(Unit) { onDispose { player.stop() } }
    SettingsListPage(L("nativeRecordingsOnOmi"), onBack) {
        section {
            row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                val (text, icon) = when (val status = sync.status) {
                    is SyncStore.Status.Waiting -> L("nativeOfflineSyncWaiting", deviceDuration(status.seconds)) to "clock.arrow.circlepath"
                    is SyncStore.Status.Syncing -> L("nativeOfflineSyncing", "${(status.progress * 100).toInt()}") to "arrow.triangle.2.circlepath"
                    SyncStore.Status.Synced, SyncStore.Status.Hidden -> L("nativeOfflineSynced") to "checkmark.icloud"
                }
                DeviceRow(text, icon)
            }
            sync.deviceStorage?.let { storage ->
                row {
                    // Used share of the Omi's storage; amber from 80 %, red from 95 % (`device_storage_card`).
                    val used = storage.usedBytes.toDouble()
                    val total = used + storage.freeBytes
                    val fraction = if (total > 0) minOf(1.0, used / total) else 0.0
                    val tint = when {
                        fraction >= 0.95 -> DS.Palette.live
                        fraction >= 0.8 -> DS.Palette.warning
                        else -> DS.Palette.ink
                    }
                    fun bytes(count: Double) = Formatter.formatFileSize(context, count.toLong())
                    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                        SettingsLabeledContent(L("nativeDeviceStorage"), L("deviceStoragePercentFull", "${(fraction * 100).roundToInt()}"))
                        OmiMeterBar(fraction, tint, Modifier.fillMaxWidth())
                        Text(
                            L("deviceStorageUsedOfTotal", bytes(used), bytes(total)) + " · " + L("deviceStorageFree", bytes(storage.freeBytes.toDouble())),
                            style = DS.Typography.caption,
                            color = DS.Palette.inkSecondary,
                        )
                        if (fraction >= 0.95) Text(L("deviceStorageNearlyFull"), style = DS.Typography.caption, color = DS.Palette.live)
                    }
                }
            }
        }
        section {
            val recordings = sync.deviceRecordings
            if (recordings.isEmpty()) {
                row { Text(L("nativeNoRecordingsWaiting"), style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
            } else {
                recordings.forEach { recording -> row(key = recording.filename) { com.friend.ios.features.components.PendingRecordingRow(recording, player) } }
            }
        }
    }
}
