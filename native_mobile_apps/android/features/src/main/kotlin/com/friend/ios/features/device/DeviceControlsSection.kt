package com.friend.ios.features.device

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiToggle
import com.friend.ios.features.settings.OmiSegmentedPicker
import com.friend.ios.service.LocalDeviceStore
import com.friend.ios.service.stores.DoubleTapAction
import com.friend.ios.service.stores.canSetMicGain
import kotlin.math.abs

/**
 * Microphone presets over the firmware's gain levels 1...8 (-20 dB ... +40 dB): a quiet room needs
 * more gain to catch soft voices, a loud place less.
 */
enum class Sensitivity(val rawValue: Int) {
    Loud(3), Normal(5), Quiet(7);

    @Composable
    fun title(): String = when (this) {
        Quiet -> L("nativeMicQuiet")
        Normal -> L("nativeMicNormal")
        Loud -> L("nativeMicLoud")
    }

    companion object {
        /** The preset closest to a level read from the Omi (0, muted, reads as a loud place). */
        fun of(level: Int): Sensitivity = entries.minByOrNull { abs(it.rawValue - level) } ?: Normal
    }
}

@Composable
private fun doubleTapChoices(): List<Pair<DoubleTapAction, String>> = listOf(
    DoubleTapAction.EndConversation to L("nativePressTwiceEnd"),
    DoubleTapAction.ToggleMute to L("nativePressTwicePause"),
    DoubleTapAction.Star to L("nativePressTwiceStar"),
)

/**
 * Port of `DeviceControlsSection.swift`: the few settings people change, one flat line each: how
 * sensitive the microphone is, what pressing twice does, and whether the button does anything.
 * Pause, find and the light are the quick buttons above. Only what the connected firmware
 * supports is shown (Flutter `device_settings.dart` customization group).
 */
@Composable
fun OmiListBuilder.deviceControlsSection() {
    val devices = LocalDeviceStore.current
    section(footerContent = { Text(L("nativeUseTheButtonCaption"), style = TextStyles.footnote, color = DS.Palette.inkSecondary, maxLines = 1) }) {
        if (devices.canSetMicGain) {
            // Microphone · Quiet | Normal | Loud, on one line.
            row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                DeviceRow(L("nativeMicrophone"), "mic")
                Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
                val options = Sensitivity.entries.reversed()
                val selected = Sensitivity.of(devices.micGain ?: Sensitivity.Normal.rawValue)
                val sensitivity = L("nativeMicSensitivity")
                // `Picker(L("nativeMicSensitivity"))` with its label hidden: TalkBack still names it.
                Box(Modifier.widthIn(max = 220.dp).width(220.dp).semantics { contentDescription = sensitivity }) {
                    OmiSegmentedPicker(options.map { it.title() }, options.indexOf(selected), textStyle = TextStyles.footnote) { devices.setMicGain(options[it].rawValue) }
                }
            }
        }
        // Press twice · the chosen action as a menu (dimmed while the button is off).
        row(separatorInset = OmiListMetrics.iconSeparatorInset, enabled = devices.buttonActionsEnabled) {
            val choices = doubleTapChoices()
            Row(Modifier.alpha(if (devices.buttonActionsEnabled) 1f else 0.45f), verticalAlignment = Alignment.CenterVertically) {
                DeviceRow(L("nativePressTwice"), "hand.tap")
                Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
                val menu = listOf(
                    MenuSection(
                        items = choices.map { (action, title) ->
                            MenuItem(title, if (action == devices.doubleTapAction) "checkmark" else null) {
                                if (devices.buttonActionsEnabled) devices.doubleTapAction = action
                            }
                        },
                    ),
                )
                OmiMenu(menu, contentDescription = L("nativePressTwiceTo")) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                        Text(
                            choices.firstOrNull { it.first == devices.doubleTapAction }?.second.orEmpty(),
                            style = DS.Typography.body,
                            color = DS.Palette.inkSecondary,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        SFImage("chevron.up.chevron.down", size = 13.sp, tint = DS.Palette.inkSecondary)
                    }
                }
            }
        }
        row(separatorInset = OmiListMetrics.iconSeparatorInset) {
            DeviceRow(L("nativeUseTheButton"), "circle.circle")
            Spacer(Modifier.weight(1f))
            OmiToggle(devices.buttonActionsEnabled, { devices.buttonActionsEnabled = it })
        }
    }
}
