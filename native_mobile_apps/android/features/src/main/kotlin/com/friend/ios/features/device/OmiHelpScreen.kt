package com.friend.ios.features.device

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiSectionBuilder
import com.friend.ios.features.settings.SettingsListPage
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.stores.DeviceStore

/**
 * Port of `OmiHelpScreen.swift`: My Omi › Help with your Omi, learning the button again and
 * charging help (Flutter device settings: Device Tutorial, Charging Issues; Diagnostics lives in
 * About this Omi). One row on the device screen leads here, so the device screen stays about the
 * device.
 */
@Composable
fun OmiHelpScreen(onBack: () -> Unit, tutorial: (@Composable (onClose: () -> Unit) -> Unit)?) {
    val devices = LocalDeviceStore.current
    val uriHandler = LocalUriHandler.current
    var showsTutorial by remember { mutableStateOf(false) }
    val connected = devices.connection == DeviceStore.Connection.Connected
    val deviceName = devices.paired?.name ?: "Omi"
    if (showsTutorial && tutorial != null) {
        tutorial { showsTutorial = false }
        return
    }
    SettingsListPage(L("nativeHelpWithYourOmi"), onBack) {
        section(footerContent = {
            // What each row is, said once (rows stay one line).
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                if (tutorial != null && !connected) Text(L("nativeOmiOnAndNearby"), style = TextStyles.footnote, color = DS.Palette.inkSecondary)
                Text(L("nativeHelpFooter"), style = TextStyles.footnote, color = DS.Palette.inkSecondary)
            }
        }) {
            if (tutorial != null) {
                helpRow(L("nativeLearnTheButton"), "hand.tap", "chevron.right", enabled = connected) { showsTutorial = true }
            }
            helpRow(L("nativeChargingHelp"), "bolt", "arrow.up.right") { uriHandler.openUri(chargingHelpURL(deviceName)) }
        }
    }
}

/** A one-line row that opens something: the glyph, the title, where it goes on the right. */
private fun OmiSectionBuilder.helpRow(title: String, symbol: String, trailing: String, enabled: Boolean = true, onClick: () -> Unit) {
    row(onClick = onClick, enabled = enabled, separatorInset = OmiListMetrics.iconSeparatorInset) {
        DeviceRow(title, symbol, tint = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
        Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
        SFImage(trailing, size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
    }
}
