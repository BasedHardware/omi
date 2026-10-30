package com.friend.ios.features.device

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.settings.OmiMeterBar
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.LocalFirmwareStore
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.stores.FirmwareStore
import kotlinx.coroutines.launch

/**
 * Port of `FirmwareUpdateRow.swift`: the firmware update in My Devices, one row, only when there
 * is something to say (an update on offer, one running, or how the last one ended). The update
 * starts only from the confirmation; below 20 % battery it is refused before asking.
 */
@Composable
fun FirmwareUpdateRow() {
    val devices = LocalDeviceStore.current
    val firmware = LocalFirmwareStore.current
    val scope = rememberCoroutineScope()
    var confirming by remember { mutableStateOf(false) }
    var refusedForBattery by remember { mutableStateOf(false) }
    val connected = devices.connection == DeviceStore.Connection.Connected
    val requestUpdate = {
        val battery = devices.battery
        if (battery == null || battery < FirmwareStore.MINIMUM_BATTERY) refusedForBattery = true else confirming = true
    }
    when (val phase = firmware.phase) {
        FirmwareStore.Phase.Idle -> firmware.available?.let { release ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(L("nativeFirmwareUpdateAvailable", release.version), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                OmiPillButton(L("update"), Modifier.alpha(if (connected) 1f else 0.4f), onClick = { if (connected) requestUpdate() })
            }
        }
        FirmwareStore.Phase.Downloading -> Progress(L("downloadingFirmware"), null, keepOpen = true)
        is FirmwareStore.Phase.Installing -> Progress(L("installingFirmware"), phase.progress, keepOpen = true)
        FirmwareStore.Phase.Restarting -> Progress(L("otaRebooting", devices.paired?.name ?: "Omi"), null, keepOpen = false)
        is FirmwareStore.Phase.Finished -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            SFImage("checkmark.circle.fill", size = 17.sp, tint = DS.Palette.success)
            Text(L("nativeFirmwareUpdated", phase.version), style = DS.Typography.body, color = DS.Palette.success)
        }
        is FirmwareStore.Phase.Failed -> Failed(phase.failure, canRetry = firmware.available != null && connected, retry = requestUpdate) { firmware.dismissResult() }
    }
    if (confirming) {
        OmiAlert(
            L("nativeFirmwareUpdateConfirmTitle"),
            buttons = listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("nativeFirmwareUpdateStart")) { scope.launch { firmware.install() } },
            ),
            onDismiss = { confirming = false },
            message = L("nativeFirmwareUpdateConfirmBody"),
        )
    }
    if (refusedForBattery) {
        OmiAlert(
            L("nativeFirmwareBatteryTooLow"),
            buttons = listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)),
            onDismiss = { refusedForBattery = false },
            message = L("nativeFirmwareBatteryTooLowBody"),
        )
    }
    // The phone must not lock mid-transfer: a sleeping phone can drop the Bluetooth upload.
    val transferring = firmware.phase == FirmwareStore.Phase.Downloading || firmware.phase is FirmwareStore.Phase.Installing
    val view = LocalView.current
    DisposableEffect(transferring) {
        view.keepScreenOn = transferring
        onDispose { view.keepScreenOn = false }
    }
}

@Composable
private fun Progress(title: String, value: Double?, keepOpen: Boolean) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
            if (value != null) {
                Text("${(value * 100).toInt()}%", style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
            } else {
                OmiProgress(Modifier.size(18.dp))
            }
        }
        if (value != null) OmiMeterBar(value, DS.Palette.ink, Modifier.fillMaxWidth())
        if (keepOpen) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                SFImage("exclamationmark.triangle", size = 13.sp, tint = DS.Palette.warning)
                Text(L("nativeFirmwareKeepAppOpen"), style = DS.Typography.caption, color = DS.Palette.warning)
            }
        }
    }
}

@Composable
private fun Failed(failure: FirmwareStore.Failure, canRetry: Boolean, retry: () -> Unit, dismiss: () -> Unit) {
    val title = when (failure) {
        FirmwareStore.Failure.LowBattery -> L("nativeFirmwareBatteryTooLow")
        FirmwareStore.Failure.NotConnected -> L("nativeFirmwareConnectFirst")
        FirmwareStore.Failure.Download, FirmwareStore.Failure.Install -> L("firmwareUpdateFailedTitle")
    }
    val body = when (failure) {
        FirmwareStore.Failure.LowBattery -> L("nativeFirmwareBatteryTooLowBody")
        FirmwareStore.Failure.NotConnected -> L("nativeOmiOnAndNearby")
        FirmwareStore.Failure.Download -> L("firmwareDownloadFailedMessage")
        FirmwareStore.Failure.Install -> L("firmwareUpdateFailedMessage")
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            SFImage("exclamationmark.triangle", size = 17.sp, tint = DS.Palette.warning)
            Text(title, style = DS.Typography.body, color = DS.Palette.warning)
        }
        Text(body, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
        Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            if (canRetry && (failure == FirmwareStore.Failure.Download || failure == FirmwareStore.Failure.Install)) {
                OmiPillButton(L("tryAgain"), prominent = false, onClick = retry)
            }
            OmiPillButton(L("ok"), prominent = false, onClick = dismiss)
            Spacer(Modifier.weight(1f))
        }
    }
}
