package com.friend.ios.features.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.service.LocalAppleHealthStore
import com.friend.ios.service.stores.AppleHealthStore
import kotlinx.coroutines.launch

/**
 * Port of `AppleHealthScreen.swift`, as Health Connect (Android's Apple Health). Settings >
 * Capabilities > Health Connect (Flutter `apple_health_detail_page`): what Omi reads, whether it is
 * connected, the last sync, connect / disconnect.
 */
@Composable
fun AppleHealthScreen(onBack: () -> Unit) {
    val health = LocalAppleHealthStore.current
    val scope = rememberCoroutineScope()
    var confirmsDisconnect by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) { health.load() }
    val title = HEALTH_CONNECT
    val features = listOf(
        Triple("bubble.left", L("appleHealthFeatureChatTitle"), L("appleHealthFeatureChatDesc")),
        Triple("lock", L("appleHealthFeatureReadOnlyTitle"), L("appleHealthFeatureReadOnlyDesc")),
        Triple("arrow.triangle.2.circlepath.icloud", L("appleHealthFeatureSecureTitle"), L("appleHealthFeatureSecureDesc")),
    )
    val syncNow = L("syncNow")
    val disconnect = L("appleHealthDisconnectCta")
    val connect = L("appleHealthConnectCta")
    val idle = health.phase == AppleHealthStore.Phase.Idle
    SettingsListPage(title, onBack) {
        section {
            row {
                Row(Modifier.padding(vertical = DS.Spacing.xs), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    AppleHealthIcon(44.dp)
                    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text(title, style = DS.Typography.cardTitle, color = DS.Palette.ink)
                        HealthStatus(health)
                    }
                }
            }
        }
        section {
            features.forEach { (icon, heading, detail) ->
                // A thin gray glyph as on every settings row; Health's pink stays on its own icon only.
                row {
                    Row(Modifier.padding(vertical = DS.Spacing.xxs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                        SettingsIcon(icon)
                        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                            Text(heading, style = DS.Typography.cardTitle, color = DS.Palette.ink)
                            Text(detail, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                        }
                    }
                }
            }
        }
        section(footer = L("appleHealthManageNote")) {
            if (health.isConnected) {
                row(onClick = { if (idle) scope.launch { health.sync() } }) {
                    Text(syncNow, style = DS.Typography.body, color = DS.Palette.agent, modifier = Modifier.alpha(if (idle) 1f else 0.4f))
                }
                row(onClick = { if (idle) confirmsDisconnect = true }) {
                    Text(disconnect, style = DS.Typography.body, color = DS.Palette.live, modifier = Modifier.alpha(if (idle) 1f else 0.4f))
                }
            } else {
                row(onClick = { if (idle) scope.launch { health.connect() } }) {
                    Text(connect, style = DS.Typography.body, color = DS.Palette.agent, modifier = Modifier.alpha(if (idle) 1f else 0.4f))
                    if (health.phase == AppleHealthStore.Phase.Connecting) {
                        Spacer(Modifier.weight(1f))
                        OmiProgress()
                    }
                }
            }
        }
    }
    if (confirmsDisconnect) {
        OmiConfirmationDialog(
            title = L("disconnectAppTitle", title),
            message = L("nativeAppleHealthReconnectAnytime"),
            buttons = listOf(DialogButton(disconnect, DialogButton.Role.Destructive) { scope.launch { health.disconnect() } }),
            onDismiss = { confirmsDisconnect = false },
        )
    }
    // Failures only; a successful connect or disconnect shows in the status line.
    val alertTitle = when (health.notice) {
        AppleHealthStore.Notice.Denied -> L("appleHealthDeniedTitle")
        AppleHealthStore.Notice.Unavailable -> L("appleHealthNotAvailable")
        AppleHealthStore.Notice.Failed -> L("nativeAppleHealthConnectFailed")
        AppleHealthStore.Notice.DisconnectFailed -> L("failedToDisconnect")
        else -> null
    }
    if (alertTitle != null) {
        OmiAlert(
            alertTitle,
            listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)),
            onDismiss = { health.notice = null },
            message = if (health.notice == AppleHealthStore.Notice.Denied) L("appleHealthDeniedBody") else null,
        )
    }
}

/** Connected (green dot, last sync) or what connecting does. */
@Composable
private fun HealthStatus(health: AppleHealthStore) {
    if (health.isConnected) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
            Box(Modifier.size(7.dp).background(DS.Palette.success, CircleShape))
            Text(L("appleHealthConnectedBadge"), style = DS.Typography.caption, color = DS.Palette.success)
            Text("·", style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            val synced = health.lastSync?.let { L("nativeAppleHealthLastSync", relative(it)) } ?: L("nativeAppleHealthNotSynced")
            Text(synced, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
    } else {
        Text(L("nativeCapabilityHealth"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
    }
}

/** Android's name for the health store iOS calls Apple Health (a product name, not translated). */
const val HEALTH_CONNECT = "Health Connect"

/** Apple Health's own pink, only for its icons (as Flutter). */
val AppleHealthPink = Color(red = 1f, green = 0.176f, blue = 0.333f)

/** The heart on white, as Health's own icon. */
@Composable
fun AppleHealthIcon(size: Dp) {
    Box(Modifier.size(size).background(Color.White, ContinuousRoundedShape(size * 0.28f)), contentAlignment = Alignment.Center) {
        SFImage("heart.fill", size = (size.value * 0.5f).sp, weight = FontWeight.SemiBold, tint = AppleHealthPink)
    }
}
