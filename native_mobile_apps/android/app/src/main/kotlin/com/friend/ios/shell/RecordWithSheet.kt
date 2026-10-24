package com.friend.ios.shell

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiRowGlyph
import com.friend.ios.features.components.OmiSectionBuilder
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.watch.isAvailable
import com.friend.ios.service.watch.ping
import com.friend.ios.service.watch.startFromPhone

/**
 * Port of `RecordWithSheet.swift`: "Record with..." (Flutter `battery_info_widget`, long press on
 * the record button): one source at a time, the phone's microphone, the Omi, or the watch (a Wear
 * OS watch running the Omi watch app, `:wear`; titled with its own name once it reported in).
 */
@Composable
fun RecordWithSheet(onDismiss: () -> Unit) {
    val capture = LocalCaptureStore.current
    val watch = com.friend.ios.service.LocalWatchStore.current
    androidx.compose.runtime.LaunchedEffect(watch) { watch?.ping() }
    val haptics = rememberHaptics()
    val devices = com.friend.ios.service.LocalDeviceStore.current
    val omiReady = devices.connection == com.friend.ios.service.stores.DeviceStore.Connection.Connected && devices.codec != null

    fun OmiSectionBuilder.source(title: String, detail: String, icon: String, enabled: Boolean, start: () -> Unit) {
        val active = enabled && !capture.isLive
        row(
            key = icon,
            enabled = active,
            separatorInset = OmiListMetrics.iconSeparatorInset,
            onClick = {
                haptics.tap(DSHaptics.Style.Medium)
                onDismiss()
                start()
            },
        ) {
            HStack(spacing = 12.dp) {
                OmiRowGlyph(icon, tint = if (enabled) DS.Palette.inkSecondary else DS.Palette.inkDisabled)
                Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                    Text(title, style = DS.Typography.body, color = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
                    Text(detail, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                }
            }
        }
    }

    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium), showsGrabber = false) {
        // The inline navigation bar: Cancel on the left, the title in the middle.
        Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
            Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onDismiss))
            Text(L("nativeRecordWith"), style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
        }
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                source(L("phone"), detail = L("recordWithPhoneMic"), icon = "iphone", enabled = true) {
                    capture.perform { startPhone() }
                }
                source(
                    devices.paired?.name ?: "Omi",
                    detail = if (omiReady) L("nativeRecordWithOmiDetail") else L("nativeRecordWithOmiUnavailable"),
                    icon = "circle.circle",
                    enabled = omiReady,
                ) {
                    val codec = devices.codec ?: return@source
                    val listen = com.friend.ios.network.listen.ListenSocket.Options.Codec.from(codec.listenValue) ?: return@source
                    capture.perform { startDevice(listen, codec.sampleRate) }
                }
                val watchAvailable = watch?.isAvailable == true
                source(
                    watch?.info?.name ?: L("nativeRecordWithWatch"),
                    detail = if (watchAvailable) L("nativeRecordWithWatchDetail") else L("nativeRecordWithWatchUnavailable"),
                    icon = "applewatch",
                    enabled = watchAvailable,
                ) {
                    watch?.startFromPhone()
                }
            }
        }
    }
}
