package com.friend.ios.features.device

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.OmiPendantThumbnail
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.R
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberNavPath
import com.friend.ios.design.OmiNavigationStack
import com.friend.ios.design.semibold
import com.friend.ios.device.OmiDeviceManager
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiRowGlyph
import com.friend.ios.features.components.OmiSectionLabel
import com.friend.ios.features.settings.OmiStatusDot
import com.friend.ios.features.settings.SettingsPage
import com.friend.ios.features.settings.SettingsMetrics
import com.friend.ios.features.components.OmiFlatList
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.LocalFirmwareStore
import com.friend.ios.service.LocalSyncStore
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.stores.LowBatteryAlert
import com.friend.ios.service.stores.SettingsHub
import com.friend.ios.service.stores.SyncStore
import kotlin.time.Duration.Companion.seconds

/** The pages My Omi pushes (`NavigationLink`s of `DeviceScreen.swift`). */
enum class DeviceRoute { Info, Help, Diagnostics, Recordings }

/**
 * Port of `DeviceScreen.swift`: My Omi, laid out like AirPods in iOS Settings: the pendant itself
 * large in the middle with its name and one status line (dot, listening or paused, battery), three
 * round quick buttons (pause, find, light), the few settings people change as flat rows,
 * recordings waiting on the Omi as one row, then this Omi's software, About this Omi and help.
 * Away: the same page with the pendant faded, a Connect button and the quick buttons dimmed. Never
 * paired: the Omis nearby as rows and "Get an Omi" as one quiet row.
 *
 * [onBack] is Settings' back; [onDone] the Done of the sheet the header pill opens. [tutorial] is
 * My Devices › How to use your Omi (the onboarding lessons unless a caller hands in others).
 */
@Composable
fun DeviceScreen(
    onBack: (() -> Unit)? = null,
    onDone: (() -> Unit)? = null,
    tutorial: (@Composable (onClose: () -> Unit) -> Unit)? = buttonTutorial,
) {
    val path = rememberNavPath<DeviceRoute>()
    // `-omiDevicePage help|diagnostics|light` (debug): opens that page for emulator QA.
    LaunchedEffect(Unit) {
        when (DeviceDebug.page) {
            "help" -> path.push(DeviceRoute.Help)
            "diagnostics" -> path.push(DeviceRoute.Diagnostics)
            "info" -> path.push(DeviceRoute.Info)
            "recordings" -> path.push(DeviceRoute.Recordings)
        }
    }
    OmiNavigationStack(path, root = { DeviceRoot(onBack, onDone) { path.push(it) } }) { route ->
        when (route) {
            DeviceRoute.Info -> DeviceInfoScreen(onBack = { path.pop() }, onOpen = { path.push(it) }, onForgotten = { path.pop() })
            DeviceRoute.Help -> OmiHelpScreen(onBack = { path.pop() }, tutorial = tutorial)
            DeviceRoute.Diagnostics -> DeviceDiagnosticsScreen(onBack = { path.pop() })
            DeviceRoute.Recordings -> DeviceRecordingsScreen(onBack = { path.pop() })
        }
    }
}

@Composable
private fun DeviceRoot(onBack: (() -> Unit)?, onDone: (() -> Unit)?, onOpen: (DeviceRoute) -> Unit) {
    val devices = LocalDeviceStore.current
    val firmware = LocalFirmwareStore.current
    val sync = LocalSyncStore.current
    val uriHandler = LocalUriHandler.current
    BluetoothPermissions(devices)
    LaunchedEffect(Unit) {
        // Opening the page counts as "Try again" for a paired Omi that is not connected.
        if (devices.paired == null) devices.scan() else if (devices.connection == DeviceStore.Connection.Disconnected) devices.start()
        firmware.checkIfDue()
    }
    DisposableEffect(Unit) { onDispose { devices.stopScan() } }
    SettingsPage(L("nativeQuickActionMyOmi"), onBack, trailing = { if (onDone != null) DoneCapsule(onDone) }, scrollsUnderBar = true) {
      OmiFlatList(contentPadding = SettingsMetrics.listPaddingUnderBar) {
        val paired = devices.paired
        if (paired != null) {
            section {
                plainRow { Hero(paired.name) }
                plainRow { DeviceQuickButtons() }
            }
            if (devices.connection == DeviceStore.Connection.Connected) deviceControlsSection()
            if (sync.status != SyncStore.Status.Hidden) deviceRecordingsRow { onOpen(DeviceRoute.Recordings) }
            section(footerContent = {
                Column(Modifier.padding(top = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    val notes = firmware.available?.notes
                    if (firmware.phase == com.friend.ios.service.stores.FirmwareStore.Phase.Idle && notes != null) {
                        Text(notes, style = TextStyles.footnote, color = DS.Palette.inkSecondary, maxLines = 3)
                    }
                    // Already has one: where to get another stays a quiet link at the very end.
                    Text(
                        L("nativeGetAnotherOmi"),
                        style = DS.Typography.caption.semibold(),
                        color = DS.Palette.inkSecondary,
                        modifier = Modifier.plainButton { uriHandler.openUri(SHOP_URL) },
                    )
                }
            }) {
                softwareRow()
                row(onClick = { onOpen(DeviceRoute.Info) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                    DeviceRow(L("nativeAboutThisOmi"), "info.circle")
                }
                row(onClick = { onOpen(DeviceRoute.Help) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                    DeviceRow(L("nativeHelpWithYourOmi"), "questionmark.circle")
                }
            }
        } else {
            section { plainRow { NeverPairedHero() } }
            nearby(devices)
            section(footer = L("nativeNoOmiFooter")) {
                row(onClick = { uriHandler.openUri(SHOP_URL) }, separatorInset = OmiListMetrics.iconSeparatorInset) {
                    DeviceRow(L("nativeGetAnOmi"), "bag")
                    Spacer(Modifier.weight(1f))
                    SFImage("arrow.up.right", size = 13.sp, tint = DS.Palette.inkTertiary)
                }
            }
        }
      }
    }
}

/**
 * `MainTabView+Sheets.buttonTutorial`: the three button lessons, reopened from My Omi's help. iOS
 * passes it wherever My Omi opens (Settings, the header pill), so it is the default here.
 */
private val buttonTutorial: @Composable (onClose: () -> Unit) -> Unit = { onClose ->
    val voice = com.friend.ios.service.LocalVoicePlaybackStore.current
    if (voice != null) com.friend.ios.features.onboarding.OmiButtonTutorialScreen(com.friend.ios.service.LocalButtonTutorialStore.current, voice, onClose)
}

/** The state shown on My Omi (`SettingsHub.omiState`). */
@Composable
internal fun omiState(): SettingsHub.OmiState {
    val devices = LocalDeviceStore.current
    val capture = LocalCaptureStore.current
    return SettingsHub.omiState(
        isPaired = devices.paired != null, connection = devices.connection, battery = devices.battery,
        isMuted = capture.isDeviceMuted, isListening = capture.source == com.friend.ios.service.stores.CaptureStore.Source.Device && capture.isLive,
    )
}

/** The pendant large in the middle, its name, the status line; away, a Connect button. */
@Composable
private fun Hero(title: String) {
    val devices = LocalDeviceStore.current
    val state = omiState()
    Column(
        Modifier.fillMaxWidth().padding(top = DS.Spacing.sm, bottom = DS.Spacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        OmiPendantPhoto(150.dp, isFaded = !state.isConnected, modifier = Modifier.padding(bottom = DS.Spacing.sm))
        Text(title, style = DS.Typography.title, color = DS.Palette.ink, maxLines = 1)
        StatusLine(state)
        if (!state.isConnected && !devices.isUpdatingFirmware) Connect()
    }
}

/** ● Listening · 76% ▮▮▮▯ (red while listening, green connected, gray away). */
@Composable
private fun StatusLine(state: SettingsHub.OmiState) {
    val devices = LocalDeviceStore.current
    val text = when {
        state is SettingsHub.OmiState.Connected && state.activity == SettingsHub.OmiState.Activity.Listening -> L("nativeOmiListening")
        state is SettingsHub.OmiState.Connected && state.activity == SettingsHub.OmiState.Activity.Paused -> L("nativePaused")
        state is SettingsHub.OmiState.Connected -> L("nativeConnected")
        state == SettingsHub.OmiState.Connecting -> L("nativeConnecting")
        else -> L("nativeNotConnected")
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        OmiStatusDot(state.dot, size = 8.dp, ring = Color.Transparent, showsOff = true)
        Text(text, style = DS.Typography.callout, color = DS.Palette.inkSecondary, maxLines = 1)
        val battery = (state as? SettingsHub.OmiState.Connected)?.battery
        if (battery != null) {
            Text("·", style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            BatteryBadge(battery)
            if (devices.isCharging == true) SFImage("bolt.fill", size = 15.sp, tint = DS.Palette.inkSecondary, contentDescription = L("charging"))
        }
    }
}

/**
 * Away: one Connect button (tries right away; the app keeps waiting in the background either
 * way) and what to check, in one line.
 */
@Composable
private fun Connect() {
    val devices = LocalDeviceStore.current
    val connecting = devices.connection == DeviceStore.Connection.Connecting
    Column(Modifier.padding(top = DS.Spacing.sm), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Row(
            Modifier
                .background(DS.Palette.accent, CircleShape)
                .plainButton(enabled = !connecting) { devices.start() }
                .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
        ) {
            if (connecting) OmiProgress(Modifier.size(16.dp), tint = DS.Palette.onAccent)
            Text(L("connect"), style = TextStyles.subheadline.semibold(), color = DS.Palette.onAccent)
        }
        if (devices.bluetooth.isOff) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                SFImage("exclamationmark.triangle", size = 13.sp, tint = DS.Palette.warning)
                Text(L("nativeBluetoothOff"), style = DS.Typography.caption, color = DS.Palette.warning, maxLines = 2)
            }
        } else {
            Text(L("nativeOmiOnAndNearby"), style = DS.Typography.caption, color = DS.Palette.inkTertiary, textAlign = TextAlign.Center, maxLines = 2)
        }
    }
}

/** Never paired: the pendant faded, "Connect your Omi" and how. */
@Composable
private fun NeverPairedHero() {
    Column(
        Modifier.fillMaxWidth().padding(vertical = DS.Spacing.lg, horizontal = DS.Spacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        OmiPendantPhoto(130.dp, isFaded = true, modifier = Modifier.padding(bottom = DS.Spacing.sm))
        Text(L("nativeConnectYourOmi"), style = DS.Typography.title, color = DS.Palette.ink, textAlign = TextAlign.Center)
        Text(L("nativePairingHint"), style = DS.Typography.callout, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
    }
}

/** The Omis nearby, one row each; a tap pairs. */
@Composable
private fun OmiListBuilder.nearby(devices: DeviceStore) {
    section(headerContent = { OmiSectionLabel(L("nativeNearbyDevices")) }) {
        if (devices.bluetooth.isOff) {
            row(separatorInset = OmiListMetrics.iconSeparatorInset) { DeviceRow(L("nativeBluetoothOff"), "exclamationmark.triangle", tint = DS.Palette.warning) }
        }
        devices.discovered.forEach { discovery ->
            row(key = discovery.id, onClick = { devices.pair(discovery) }, separatorInset = OmiListMetrics.iconSeparatorInset) {
                // `.accessibilityHint(L("nativeTapToConnect"))`: Compose's nearest is the click's label.
                val hint = L("nativeTapToConnect")
                Row(Modifier.semantics { onClick(label = hint, action = null) }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) { OmiPendantThumbnail(28.dp) }
                    Text(discovery.name, style = DS.Typography.body, color = DS.Palette.ink)
                    // `wifi` with a variable value: the signal, dimmed by how weak it is.
                    SFImage("wifi", size = 13.sp, tint = DS.Palette.inkTertiary.copy(alpha = 0.4f + 0.6f * signal(discovery.rssi)))
                }
                Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
                Text(L("connect"), style = TextStyles.subheadline.semibold(), color = DS.Palette.ink)
            }
        }
        if (devices.isScanning || devices.discovered.isEmpty()) {
            row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) { OmiProgress(Modifier.size(18.dp)) }
                    Text(L("nativeLookingForOmi"), style = DS.Typography.body, color = DS.Palette.inkSecondary)
                }
            }
        }
    }
}

/** "Software: up to date", or the update on offer / under way (`FirmwareUpdateRow`). */
@Composable
private fun com.friend.ios.features.components.OmiSectionBuilder.softwareRow() {
    val firmware = LocalFirmwareStore.current
    if (firmware.phase == com.friend.ios.service.stores.FirmwareStore.Phase.Idle && firmware.available == null) {
        row(separatorInset = OmiListMetrics.iconSeparatorInset) {
            DeviceRow(L("nativeSoftware"), "checkmark.seal")
            Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
            Text(L("nativeUpToDate"), style = DS.Typography.body, color = DS.Palette.inkSecondary)
        }
    } else {
        row(separatorInset = OmiListMetrics.iconSeparatorInset) { FirmwareUpdateRow() }
    }
}

/** Asks for the Bluetooth permissions once (iOS shows its prompt when the driver starts). */
@Composable
private fun BluetoothPermissions(devices: DeviceStore) {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { devices.permissionsChanged() }
    LaunchedEffect(Unit) {
        val missing = OmiDeviceManager.requiredPermissions.filter {
            ContextCompat.checkSelfPermission(context, it) != android.content.pm.PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty() && !DeviceDebug.isFake) launcher.launch(missing.toTypedArray())
    }
}

/** The sheet's Done (`ToolbarItem(placement: .confirmationAction)`): a glass capsule. */
@Composable
private fun DoneCapsule(onDone: () -> Unit) {
    val dark = LocalOmiDark.current
    Box(
        Modifier
            .height(44.dp)
            .background(if (dark) hex(0x282828) else hex(0xF5F5F5), CircleShape)
            .border(1.dp, if (dark) hex(0x363636) else hex(0xE4E4E4), CircleShape)
            .plainButton(onClick = onDone)
            .padding(horizontal = DS.Spacing.lg),
        contentAlignment = Alignment.Center,
    ) {
        Text(L("done"), style = TextStyles.headline, color = DS.Palette.ink)
    }
}

private val OmiDeviceManager.BluetoothState.isOff: Boolean
    get() = this == OmiDeviceManager.BluetoothState.PoweredOff || this == OmiDeviceManager.BluetoothState.Unauthorized

private fun signal(rssi: Int): Float = ((rssi + 100) / 50f).coerceIn(0f, 1f)

internal const val SHOP_URL = "https://www.omi.me/?_ref=omi_connect_device"

internal fun chargingHelpURL(deviceName: String): String {
    val page = when (deviceName) {
        "Omi DevKit 2" -> "charging-devkit2"
        "Omi" -> "charging-omi"
        else -> "charging"
    }
    return "https://www.omi.me/pages/$page"
}

/** "3 min", "1 hr, 5 min"; under a minute reads as a minute (`Duration.formatted(.units)`). */
internal fun deviceDuration(seconds: Int): String {
    val minutes = maxOf(1, (seconds + 59) / 60)
    val hours = minutes / 60
    val rest = minutes % 60
    return when {
        hours == 0 -> "$rest min"
        rest == 0 -> "$hours hr"
        else -> "$hours hr, $rest min"
    }
}

/** Battery percentage with a matching symbol. */
@Composable
fun BatteryBadge(level: Int) {
    val symbol = when {
        level < 13 -> "battery.0percent"
        level < 38 -> "battery.25percent"
        level < 63 -> "battery.50percent"
        level < 88 -> "battery.75percent"
        else -> "battery.100percent"
    }
    val tint = if (LowBatteryAlert.isLow(level)) DS.Palette.warning else DS.Palette.inkSecondary
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Text("$level%", style = DS.Typography.callout.copy(fontFeatureSettings = "tnum"), color = tint)
        SFImage(symbol, size = 15.sp, tint = tint)
    }
}

/** A My Omi row: a thin line glyph in a fixed column, then the title (Settings' row look). */
@Composable
internal fun DeviceRow(title: String, systemImage: String, tint: Color = DS.Palette.ink) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        OmiRowGlyph(systemImage, tint = DS.Palette.ink)
        Text(title, style = DS.Typography.body, color = tint)
    }
}

/**
 * `OmiPendantPhoto`: the Omi itself, large (My Omi's headline, as AirPods in iOS Settings): the
 * photo with a soft shadow under it; gray and faded while the Omi is away.
 */
@Composable
fun OmiPendantPhoto(size: Dp = 150.dp, isFaded: Boolean = false, modifier: Modifier = Modifier) {
    val alpha by animateFloatAsState(if (isFaded) 0.45f else 1f, label = "faded")
    val gray = ColorMatrix().apply { setToSaturation(0f) }
    Image(
        painterResource(R.drawable.omi_device),
        contentDescription = null,
        contentScale = ContentScale.Fit,
        colorFilter = if (isFaded) ColorFilter.colorMatrix(gray) else null,
        modifier = modifier
            .size(size)
            .shadow(size / 12, CircleShape, clip = false, ambientColor = Color.Black.copy(alpha = if (isFaded) 0.06f else 0.18f))
            .alpha(alpha),
    )
}

/** Emulator QA without tapping (debug builds only; the extras are empty otherwise). */
object DeviceDebug {
    val page: String? get() = DebugLaunch.string("omiDevicePage")
    val isFake: Boolean get() = DebugLaunch.string("omiFakeDevice") != null
}
