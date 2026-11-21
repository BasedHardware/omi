package com.friend.ios.features.onboarding

import com.friend.ios.device.OmiDeviceManager
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.LocalDeviceStore
import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.R
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.stores.OnboardingStore

/** "Do you have an Omi?" Two big cards side by side, a picture and one line each; a tap moves on. */
@Composable
internal fun HasOmiStep(store: OnboardingStore) {
    val uri = LocalUriHandler.current
    OnboardingLayout(kicker = L("nativeKickerYourOmi"), title = L("nativeDoYouHaveOmi"), subtitle = L("nativeDoYouHaveOmiShort")) {
        Row(Modifier.padding(horizontal = DS.Spacing.gutter), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            OmiChoiceCard(L("nativeYesIHaveOmi"), store.hasOmi == true, Modifier.weight(1f), action = { store.chooseOmi(true) }) {
                Image(painterResource(R.drawable.omi_device), null, contentScale = ContentScale.Fit, modifier = Modifier.size(92.dp))
            }
            OmiChoiceCard(L("nativeNoUseIphone"), store.hasOmi == false, Modifier.weight(1f), action = { store.chooseOmi(false) }) {
                Box(Modifier.size(92.dp), contentAlignment = Alignment.Center) {
                    SFImage("iphone", size = 54.sp, weight = FontWeight.ExtraLight, tint = DS.Palette.ink)
                }
            }
        }
        // `TrailingIconLabelStyle`: the title, then the arrow.
        HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.gutter), spacing = DS.Spacing.xs) {
            Box(Modifier.weight(1f))
            HStack(Modifier.plainButton { uri.openUri("https://www.omi.me") }, spacing = DS.Spacing.xs) {
                Text(L("nativeGetAnOmi"), style = TextStyles.subheadline.semibold(), color = DS.Palette.inkSecondary)
                SFImage("arrow.up.right", size = 15.sp, tint = DS.Palette.inkSecondary)
            }
            Box(Modifier.weight(1f))
        }
    }
}

/** A large tappable card: a picture on top, one line under it. */
@Composable
private fun OmiChoiceCard(title: String, selected: Boolean, modifier: Modifier = Modifier, action: () -> Unit, picture: @Composable () -> Unit) {
    val haptics = rememberHaptics()
    val shape = ContinuousRoundedShape(DS.Radius.hero)
    // `PressableCardStyle`: dims a little while pressed, nothing more.
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    Column(
        modifier.alpha(if (pressed) 0.7f else 1f)
            .clickable(source, indication = null) { haptics.selection(); action() }
            .heightIn(min = 196.dp)
            .background(DS.Palette.ink.copy(alpha = if (selected) 0.12f else 0.05f), shape)
            .border(if (selected) 1.5.dp else 1.dp, DS.Palette.ink.copy(alpha = if (selected) 0.5f else 0.08f), shape)
            .padding(horizontal = DS.Spacing.md),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        picture()
        Text(title, style = TextStyles.body.semibold(), color = DS.Palette.ink, textAlign = TextAlign.Center)
    }
}

/**
 * Finds the Omi and connects. Connected: the pendant with a calm check, its name and battery,
 * and Continue. Nothing blinks or pulses.
 */
@Composable
internal fun PairStep(store: OnboardingStore) {
    val devices = LocalDeviceStore.current
    val haptics = rememberHaptics()
    val connected = devices.connection == DeviceStore.Connection.Connected
    val bluetooth = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        devices.permissionsChanged()
        devices.scan()
    }
    OnboardingLayout(
        kicker = L("nativeKickerYourOmi"),
        title = if (connected) L("nativeConnectedToOmi") else L("nativeConnectYourOmi"),
        subtitle = if (connected) batteryLine(devices) else L("nativePairingHint"),
        button = StepButton(L("continueButton"), isEnabled = connected, action = store::next),
        secondary = if (connected) null else StepButton(L("nativeContinueWithIphone"), action = store::continueWithoutOmi),
        centered = true,
    ) {
        PendantImage(150.dp) {
            AnimatedVisibility(connected, enter = scaleIn(initialScale = 0.6f) + fadeIn(), exit = fadeOut()) {
                Box(Modifier.size(38.dp).background(DS.Palette.background, CircleShape), contentAlignment = Alignment.Center) {
                    SFImage("checkmark.circle.fill", size = 34.sp, tint = DS.Palette.success)
                }
            }
        }
        if (!connected) Nearby(devices)
    }
    LaunchedEffect(devices) {
        // Scanning needs the nearby-devices permission on Android 12 and later.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            bluetooth.launch(arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT))
        }
        devices.start()
        if (devices.paired == null || devices.connection == DeviceStore.Connection.Disconnected) devices.scan()
    }
    DisposableEffect(devices) { onDispose { devices.stopScan() } }
    LaunchedEffect(connected) { if (connected) haptics.success() }
}

@Composable
private fun batteryLine(devices: DeviceStore): String {
    val name = devices.paired?.name ?: "Omi"
    val battery = devices.battery ?: return name
    return L("nativeOmiBatteryLine", name, "$battery")
}

@Composable
private fun Nearby(devices: DeviceStore) {
    val haptics = rememberHaptics()
    val discovered = devices.discovered
    when {
        devices.bluetooth == OmiDeviceManager.BluetoothState.PoweredOff || devices.bluetooth == OmiDeviceManager.BluetoothState.Unauthorized ->
            StatusLine(L("nativeBluetoothOff"), "exclamationmark.triangle.fill", DS.Palette.warning).View(Modifier.padding(horizontal = DS.Spacing.gutter))
        discovered.isEmpty() -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            OmiProgress()
            Text(
                if (devices.connection == DeviceStore.Connection.Connecting) L("nativeConnecting") else L("searchingForDevices"),
                style = TextStyles.subheadline, color = DS.Palette.inkSecondary, modifier = Modifier.padding(start = DS.Spacing.sm),
            )
        }
        else -> RowList(
            discovered.take(3).map { discovery ->
                @Composable {
                    HStack(
                        Modifier.fillMaxWidth().height(60.dp).plainButton { haptics.selection(); devices.pair(discovery) }.padding(horizontal = DS.Spacing.lg),
                        spacing = DS.Spacing.md,
                    ) {
                        Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) { SFImage("circle.circle", size = 20.sp, tint = DS.Palette.inkSecondary) }
                        Text(discovery.name, style = TextStyles.body.medium(), color = DS.Palette.ink, modifier = Modifier.weight(1f))
                        if (devices.connection == DeviceStore.Connection.Connecting) {
                            OmiProgress()
                        } else {
                            Box(Modifier.height(32.dp).background(DS.Palette.ink, CircleShape).padding(horizontal = DS.Spacing.md), contentAlignment = Alignment.Center) {
                                Text(L("nativeConnect"), style = TextStyles.subheadline.semibold(), color = DS.Palette.onAccent)
                            }
                        }
                    }
                }
            },
        )
    }
}

/**
 * The light, in two boxes: "Omi is recording" (blue live, red saved on the Omi) and charging
 * (green); the rare ones in one quiet line. Still dots, no blinking.
 */
@Composable
internal fun LightsStep(onContinue: () -> Unit) {
    OnboardingLayout(
        kicker = L("nativeKickerYourOmi"), title = L("nativeWhatTheLightMeans"),
        button = StepButton(L("continueButton"), action = onContinue),
    ) {
        Column(Modifier.padding(horizontal = DS.Spacing.gutter), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            Column(Modifier.onboardingCard(padding = DS.Spacing.xl), verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
                Text(L("nativeLightRecordingTitle"), style = TextStyles.headline, color = DS.Palette.ink)
                // Firmware `set_led_state`: blue while connected, red while it records to its
                // own storage (transport.c `pusher`), green while charging.
                Light(DS.Palette.agent, L("nativeLightLiveTitle"), L("nativeLightLiveShort"))
                Light(DS.Palette.live, L("nativeLightSavedTitle"), L("nativeLightSavedShort"))
            }
            Box(Modifier.onboardingCard(padding = DS.Spacing.xl)) {
                Light(DS.Palette.success, L("nativeLightChargingTitle"), L("nativeLightGreenBody"))
            }
        }
        // Red blinking until the app set the clock, nothing when off: rare, so one line.
        Text(L("nativeLightRare"), style = TextStyles.footnote, color = DS.Palette.inkTertiary, modifier = Modifier.padding(horizontal = DS.Spacing.gutter))
    }
    ConnectsPairedOmi()
}

@Composable
private fun Light(color: androidx.compose.ui.graphics.Color, title: String, detail: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Box(
            Modifier.padding(top = 5.dp).size(12.dp)
                .shadow(4.dp, CircleShape, ambientColor = color.copy(alpha = 0.6f), spotColor = color.copy(alpha = 0.6f))
                .background(color, CircleShape),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = TextStyles.body.semibold(), color = DS.Palette.ink)
            Text(detail, style = TextStyles.subheadline, color = DS.Palette.inkSecondary)
        }
    }
}

// Permissions

private fun Context.granted(permission: String): Boolean = checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED

/** Notifications, microphone and location: one row each, an Allow button or a check. */
@Composable
internal fun PermissionsStep(onContinue: () -> Unit) {
    val context = LocalContext.current
    fun notificationsGranted() = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || context.granted(Manifest.permission.POST_NOTIFICATIONS)
    fun locationGranted() = context.granted(Manifest.permission.ACCESS_COARSE_LOCATION) || context.granted(Manifest.permission.ACCESS_FINE_LOCATION)
    var notifications by remember { mutableStateOf(notificationsGranted()) }
    var microphone by remember { mutableStateOf(context.granted(Manifest.permission.RECORD_AUDIO)) }
    var location by remember { mutableStateOf(locationGranted()) }
    var locationAsked by remember { mutableStateOf(false) }
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { notifications = notificationsGranted() }
    val askMicrophone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { microphone = it }
    val askLocation = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { location = locationGranted() }
    OnboardingLayout(
        kicker = L("nativeKickerAlmostDone"), title = L("nativeStayInTheLoop"), subtitle = L("nativePermissionsShort"),
        button = StepButton(L("continueButton"), action = onContinue),
    ) {
        RowList(
            listOf(
                {
                    PermissionRow("bell.badge", L("notifications"), notifications) {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                },
                { PermissionRow("mic", L("nativeMicrophone"), microphone) { askMicrophone.launch(Manifest.permission.RECORD_AUDIO) } },
                // While in use only, as Flutter asks here; "Always" is never needed.
                {
                    PermissionRow("location", L("locationAccess"), location) {
                        if (locationAsked) {
                            // Refused before: Android asks no more, the app's settings page can.
                            context.startActivity(
                                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                            )
                        } else {
                            locationAsked = true
                            askLocation.launch(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION))
                        }
                    }
                },
            ),
        )
    }
}

@Composable
private fun PermissionRow(icon: String, title: String, granted: Boolean, request: () -> Unit) {
    HStack(Modifier.fillMaxWidth().height(64.dp).padding(horizontal = DS.Spacing.lg), spacing = DS.Spacing.md) {
        Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) { SFImage(icon, size = 20.sp, tint = DS.Palette.inkSecondary) }
        Text(title, style = TextStyles.body.medium(), color = DS.Palette.ink, modifier = Modifier.weight(1f))
        if (granted) {
            SFImage("checkmark.circle.fill", size = 20.sp, tint = DS.Palette.success)
        } else {
            OmiPillButton(L("allow"), onClick = request)
        }
    }
}
