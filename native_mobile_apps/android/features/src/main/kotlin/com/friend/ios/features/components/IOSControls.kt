package com.friend.ios.features.components

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold

/**
 * SwiftUI `Toggle` in the iOS 26 switch look (measured on the simulator): a 63 x 28 pt track,
 * a 37 x 24 pt capsule knob; system green when on (UISwitch ignores the app's accent), the
 * quiet system fill when off.
 */
@Composable
fun OmiToggle(checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    val dark = LocalOmiDark.current
    val haptics = rememberHaptics()
    val on = if (dark) hex(0x30D158) else hex(0x34C759)
    val off = if (dark) hex(0x67676A) else hex(0xE9E9EA)
    val track by animateColorAsState(if (checked) on else off, label = "toggle-track")
    val offset by animateDpAsState(if (checked) 24.dp else 0.dp, spring(dampingRatio = 0.75f, stiffness = DS.Motion.stiffness(0.3f)), label = "toggle-knob")
    Box(
        modifier
            .size(63.dp, 28.dp)
            .background(track, CircleShape)
            .clickable(remember { MutableInteractionSource() }, indication = null, enabled = enabled) {
                haptics.selection()
                onCheckedChange(!checked)
            }
            .semantics { role = Role.Switch; stateDescription = if (checked) "On" else "Off" }
            .padding(2.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Box(
            Modifier
                .offset(x = offset)
                .size(37.dp, 24.dp)
                .shadow(2.dp, CircleShape)
                .background(Color.White, CircleShape),
        )
    }
}

/** A `Toggle(isOn:) { label }` row's content: the label, then the switch on the right. */
@Composable
fun OmiToggleRow(checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, label: @Composable () -> Unit) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) { label() }
        OmiToggle(checked, onCheckedChange, enabled = enabled)
    }
}

/**
 * `Picker(selection:) { }` in a List (`.menu` style): the title, the chosen value and the up-down
 * chevron on the right; tapping opens Omi's pull-down menu with a check on the chosen one.
 */
@Composable
fun <T> OmiPickerRow(
    options: List<T>,
    selected: T,
    title: (T) -> String,
    onSelect: (T) -> Unit,
    modifier: Modifier = Modifier,
    label: @Composable () -> Unit,
) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) { label() }
        OmiMenu(listOf(MenuSection(items = options.map { option -> MenuItem(title(option), if (option == selected) "checkmark" else null) { onSelect(option) } }))) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                // A menu picker's value reads in the primary ink on iOS 26 (unlike a row's plain value).
                Text(title(selected), style = DS.Typography.body, color = DS.Palette.ink, maxLines = 1)
                SFImage("chevron.up.chevron.down", size = 14.sp, weight = FontWeight.SemiBold, tint = DS.Palette.ink)
            }
        }
    }
}

/** One button of a confirmation dialog or alert. */
data class DialogButton(val title: String, val role: Role = Role.Default, val enabled: Boolean = true, val action: () -> Unit = {}) {
    enum class Role { Default, Destructive, Cancel }
}

/**
 * `.confirmationDialog(title, isPresented:, titleVisibility: .visible) { } message: { }`: the iOS
 * action sheet at the bottom, the title and message small and gray on top, the actions, and Cancel
 * in its own group.
 */
@Composable
fun OmiConfirmationDialog(
    title: String?,
    buttons: List<DialogButton>,
    onDismiss: () -> Unit,
    message: String? = null,
) {
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().clickable(remember { MutableInteractionSource() }, indication = null, onClick = onDismiss), contentAlignment = Alignment.BottomCenter) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp).navigationBarsPadding().padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val sheet = sheetColor()
                val shape = ContinuousRoundedShape(14.dp)
                Column(Modifier.fillMaxWidth().background(sheet, shape)) {
                    if (title != null || message != null) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            title?.let { Text(it, style = TextStyles.footnote.semibold(), color = DS.Palette.inkSecondary, textAlign = TextAlign.Center) }
                            message?.let { Text(it, style = TextStyles.footnote, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center) }
                        }
                        SheetDivider()
                    }
                    buttons.filter { it.role != DialogButton.Role.Cancel }.forEachIndexed { index, button ->
                        if (index > 0) SheetDivider()
                        SheetButton(button.title, if (button.role == DialogButton.Role.Destructive) DS.Palette.live else DS.Palette.agent, bold = false, enabled = button.enabled) {
                            onDismiss()
                            button.action()
                        }
                    }
                }
                val cancel = buttons.firstOrNull { it.role == DialogButton.Role.Cancel }
                Box(Modifier.fillMaxWidth().background(sheet, shape)) {
                    SheetButton(cancel?.title ?: com.friend.ios.design.L("cancel"), DS.Palette.agent, bold = true, enabled = true) {
                        onDismiss()
                        cancel?.action?.invoke()
                    }
                }
            }
        }
    }
}

@Composable
private fun sheetColor(): Color = if (LocalOmiDark.current) hex(0x2C2C2E) else hex(0xF9F9F9)

@Composable
private fun SheetDivider() = Box(Modifier.fillMaxWidth().height(0.5.dp).background(DS.Palette.hairline))

@Composable
private fun SheetButton(title: String, color: Color, bold: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    Box(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 57.dp)
            .background(if (pressed) DS.Palette.fill else Color.Transparent)
            .clickable(source, indication = null, enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(title, style = TextStyles.system(20, if (bold) FontWeight.SemiBold else FontWeight.Normal), color = if (enabled) color else DS.Palette.inkDisabled)
    }
}

/**
 * `.alert(title, isPresented:) { TextField; Cancel; Save } message: { }`: the centered iOS alert
 * card, with an optional text field, the buttons side by side.
 */
@Composable
fun OmiAlert(
    title: String,
    buttons: List<DialogButton>,
    onDismiss: () -> Unit,
    message: String? = null,
    textField: Pair<String, String>? = null,
    onTextChange: (String) -> Unit = {},
) {
    Dialog(onDismissRequest = onDismiss) {
        val shape = ContinuousRoundedShape(28.dp)
        Column(
            Modifier.width(300.dp).background(sheetColor(), shape).padding(horizontal = 20.dp, vertical = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = TextStyles.headline, color = DS.Palette.ink, textAlign = TextAlign.Center)
            message?.let { Text(it, style = TextStyles.footnote, color = DS.Palette.ink, textAlign = TextAlign.Center) }
            textField?.let { (placeholder, text) ->
                val focus = remember { FocusRequester() }
                LaunchedEffect(Unit) { focus.requestFocus() }
                Box(
                    Modifier.fillMaxWidth().padding(top = 4.dp).background(DS.Palette.fill, ContinuousRoundedShape(10.dp)).padding(horizontal = 10.dp, vertical = 9.dp),
                ) {
                    if (text.isEmpty()) Text(placeholder, style = DS.Typography.callout, color = DS.Palette.inkTertiary)
                    BasicTextField(
                        value = text,
                        onValueChange = onTextChange,
                        singleLine = true,
                        textStyle = DS.Typography.callout.copy(color = DS.Palette.ink),
                        cursorBrush = SolidColor(DS.Palette.agent),
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words),
                        modifier = Modifier.fillMaxWidth().focusRequester(focus),
                    )
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                buttons.forEach { button ->
                    val prominent = button.role != DialogButton.Role.Cancel && button == buttons.last()
                    Box(
                        Modifier
                            .weight(1f)
                            .heightIn(min = 48.dp)
                            .background(if (prominent) DS.Palette.agent else DS.Palette.fill, CircleShape)
                            .plainButton(enabled = button.enabled) {
                                onDismiss()
                                button.action()
                            },
                        contentAlignment = Alignment.Center,
                    ) {
                        val color = when {
                            !button.enabled -> DS.Palette.inkDisabled
                            prominent -> Color.White
                            button.role == DialogButton.Role.Destructive -> DS.Palette.live
                            else -> DS.Palette.ink
                        }
                        Text(button.title, style = DS.Typography.body.copy(fontWeight = if (prominent) FontWeight.SemiBold else FontWeight.Normal), color = color)
                    }
                }
            }
        }
    }
}

/** `.buttonStyle(.omiPill)` used as a trailing row control ("Allow", "Open Settings"). */
@Composable
fun OmiRowPill(title: String, onClick: () -> Unit) {
    com.friend.ios.design.OmiPillButton(title, onClick = onClick)
}
