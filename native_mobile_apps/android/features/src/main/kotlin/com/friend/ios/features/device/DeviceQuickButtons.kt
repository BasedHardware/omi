package com.friend.ios.features.device

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.stores.canDimLED
import com.friend.ios.service.stores.canFind
import kotlinx.coroutines.launch

/**
 * Port of `DeviceQuickButtons.swift`: My Omi's three round quick buttons under the pendant, as
 * AirPods' noise control: pause or resume listening, find the Omi (it plays its sound), and the
 * light's brightness (a small sheet). Dimmed while the Omi is away.
 */
@Composable
fun DeviceQuickButtons() {
    val devices = LocalDeviceStore.current
    val capture = LocalCaptureStore.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    var showsLight by remember { mutableStateOf(DeviceDebug.page == "light") }
    val connected = devices.connection == DeviceStore.Connection.Connected
    val paused = capture.isDeviceMuted
    val lightCaption = if (devices.canDimLED) devices.ledBrightness?.let { if (it < 1) L("off") else "$it%" } else null
    Row(Modifier.fillMaxWidth().padding(bottom = DS.Spacing.lg), verticalAlignment = Alignment.Top) {
        QuickButton(
            title = if (paused) L("nativeQuickResume") else L("nativeQuickPause"),
            systemImage = if (paused) "play.fill" else "pause",
            isOn = paused,
            enabled = connected,
            modifier = Modifier.weight(1f),
            spokenValue = if (paused) L("nativePaused") else null,
        ) {
            haptics.selection()
            capture.isDeviceMuted = !capture.isDeviceMuted
        }
        QuickButton(
            title = if (devices.isFinding) L("nativeQuickPlayingSound") else L("nativeQuickFind"),
            systemImage = if (devices.isFinding) "speaker.wave.2" else "dot.radiowaves.left.and.right",
            isOn = devices.isFinding,
            enabled = devices.canFind && !devices.isFinding,
            modifier = Modifier.weight(1f),
            spokenTitle = L("nativeFindMyOmi"),
        ) {
            haptics.selection()
            scope.launch { devices.findDevice() }
        }
        QuickButton(
            title = L("nativeQuickLight"),
            caption = lightCaption,
            systemImage = "sun.max",
            isOn = false,
            enabled = devices.canDimLED,
            modifier = Modifier.weight(1f),
            spokenTitle = L("nativeLightBrightness"),
            spokenValue = lightCaption,
        ) { showsLight = true }
    }
    if (showsLight) OmiSheet(onDismiss = { showsLight = false }, detents = setOf(Detent.Medium)) { LightSheet { showsLight = false } }
}

/**
 * One round quick button: a 58 pt circle with a thin glyph (filled ink while on), the label under
 * it and, for the light, its current value.
 */
@Composable
private fun QuickButton(
    title: String,
    systemImage: String,
    isOn: Boolean,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    caption: String? = null,
    /** What TalkBack reads instead of [title] (and as its value), as iOS's `spokenTitle` / `spokenValue`. */
    spokenTitle: String? = null,
    spokenValue: String? = null,
    action: () -> Unit,
) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.94f else 1f, label = "press")
    Column(
        modifier
            .alpha(if (enabled) 1f else 0.4f)
            .clickable(source, indication = null, enabled = enabled, onClick = action)
            .clearAndSetSemantics {
                contentDescription = spokenTitle ?: title
                spokenValue?.let { stateDescription = it }
            }
            .scale(scale),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        Box(Modifier.size(58.dp).background(if (isOn) DS.Palette.ink else DS.Palette.card, CircleShape), contentAlignment = Alignment.Center) {
            SFImage(systemImage, size = 21.sp, weight = FontWeight.Light, tint = if (isOn) DS.Palette.onAccent else DS.Palette.ink)
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(title, style = DS.Typography.label, color = DS.Palette.ink, maxLines = 1)
            if (caption != null) Text(caption, style = DS.Typography.caption.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
        }
    }
}

/** The light's brightness, from the Light quick button: one slider, the value, Done. */
@Composable
fun LightSheet(onDone: () -> Unit) {
    val devices = LocalDeviceStore.current
    var brightness by remember { mutableFloatStateOf(devices.ledBrightness?.toFloat() ?: 100f) }
    var lastWrite by remember { mutableLongStateOf(0L) }
    LaunchedEffect(devices.ledBrightness) { devices.ledBrightness?.let { brightness = it.toFloat() } }
    Column(
        Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.gutter).padding(top = DS.Spacing.xl, bottom = DS.Spacing.lg).navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(L("nativeLightBrightness"), style = DS.Typography.sectionTitle, color = DS.Palette.ink)
            Spacer(Modifier.weight(1f))
            Text(if (brightness < 1) L("off") else "${brightness.toInt()}%", style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            SFImage("sun.min", size = 17.sp, tint = DS.Palette.inkSecondary)
            IOSSlider(
                value = brightness / 100f,
                onChange = { fraction ->
                    brightness = fraction * 100f
                    // The light follows the slider while dragging, at most every 0.3 s (Flutter's debounce).
                    val now = System.currentTimeMillis()
                    if (brightness.toInt() != devices.ledBrightness && now - lastWrite > 300) {
                        lastWrite = now
                        devices.setLEDBrightness(brightness.toInt())
                    }
                },
                onChangeFinished = { if (brightness.toInt() != devices.ledBrightness) devices.setLEDBrightness(brightness.toInt()) },
                modifier = Modifier.weight(1f),
            )
            SFImage("sun.max", size = 17.sp, tint = DS.Palette.inkSecondary)
        }
        OmiPrimaryButton(L("done"), Modifier.fillMaxWidth(), onClick = onDone)
    }
}

/** `Slider` in the iOS look: a thin track filled in ink up to a round white knob with a soft shadow. */
@Composable
private fun IOSSlider(value: Float, onChange: (Float) -> Unit, onChangeFinished: () -> Unit, modifier: Modifier = Modifier) {
    val knob = 27.dp
    val density = LocalDensity.current
    BoxWithConstraints(modifier.height(knob)) {
        val track = maxWidth - knob
        val width = with(density) { track.toPx() }.coerceAtLeast(1f)
        fun fraction(x: Float) = ((x - with(density) { knob.toPx() } / 2) / width).coerceIn(0f, 1f)
        Box(
            Modifier
                .fillMaxWidth()
                .height(knob)
                .pointerInput(width) {
                    detectTapGestures { onChange(fraction(it.x)); onChangeFinished() }
                }
                .pointerInput(width) {
                    detectDragGestures(onDragEnd = onChangeFinished) { change, _ -> onChange(fraction(change.position.x)) }
                },
            contentAlignment = Alignment.CenterStart,
        ) {
            Box(Modifier.padding(horizontal = knob / 2).fillMaxWidth().height(4.dp).background(DS.Palette.fill, CircleShape))
            Box(Modifier.padding(start = knob / 2).width(track * value).height(4.dp).background(DS.Palette.ink, CircleShape))
            Box(
                Modifier
                    .offset(x = track * value)
                    .size(knob)
                    .shadow(3.dp, CircleShape)
                    .background(Color.White, CircleShape),
            )
        }
    }
}
