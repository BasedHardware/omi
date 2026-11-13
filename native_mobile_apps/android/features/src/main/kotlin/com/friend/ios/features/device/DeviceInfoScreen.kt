package com.friend.ios.features.device

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.settings.SettingsLabeledContent
import com.friend.ios.features.settings.SettingsListPage
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.LocalFirmwareStore

/**
 * Port of `DeviceInfoScreen.swift`: My Omi › About this Omi, everything the Omi reports about
 * itself, how well the connection holds up, and forgetting it.
 */
@Composable
fun DeviceInfoScreen(onBack: () -> Unit, onOpen: (DeviceRoute) -> Unit, onForgotten: () -> Unit) {
    val devices = LocalDeviceStore.current
    val firmware = LocalFirmwareStore.current
    var confirmForget by remember { mutableStateOf(false) }
    val device = devices.paired
    SettingsListPage(L("nativeAboutThisOmi"), onBack) {
        section {
            row { SettingsLabeledContent(L("nativeModel"), device?.modelNumber ?: "–") }
            row { SettingsLabeledContent(L("nativeFirmware"), device?.firmwareRevision ?: "–") }
            row { SettingsLabeledContent(L("nativeAudioCodec"), devices.codec?.listenValue ?: "–") }
            device?.hardwareRevision?.let { row { SettingsLabeledContent(L("nativeHardwareRevision"), it) } }
            device?.manufacturerName?.let { row { SettingsLabeledContent(L("manufacturer"), it) } }
            device?.serialNumber?.let { row { SettingsLabeledContent(L("nativeSerialNumber"), it) } }
        }
        section {
            row(onClick = { onOpen(DeviceRoute.Diagnostics) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                DeviceRow(L("nativeConnectionHealth"), "waveform.path.ecg")
            }
        }
        section {
            row(onClick = { confirmForget = true }, enabled = !firmware.isBusy) {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterStart) {
                    Text(L("nativeForgetDevice"), style = DS.Typography.body, color = if (firmware.isBusy) DS.Palette.inkDisabled else DS.Palette.live)
                }
            }
        }
    }
    if (confirmForget) {
        OmiConfirmationDialog(
            L("nativeForgetDevice"),
            buttons = listOf(
                DialogButton(L("nativeForgetDevice"), DialogButton.Role.Destructive) {
                    devices.forget()
                    onForgotten()
                },
            ),
            onDismiss = { confirmForget = false },
            message = L("forgetDeviceConfirmMessage"),
        )
    }
}
