package com.friend.ios.design

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntRect
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupPositionProvider
import androidx.compose.ui.window.PopupProperties

/** One row of an iOS `Menu` / `contextMenu`: title left, SF Symbol right, red when destructive. */
data class MenuItem(
    val title: String,
    val systemImage: String? = null,
    val destructive: Boolean = false,
    val action: () -> Unit,
)

/** A `Section` inside a menu: an optional small gray header, rows, a thick separator between sections. */
data class MenuSection(val header: String? = null, val items: List<MenuItem>)

/**
 * SwiftUI `Menu { } label: { }`: tapping [label] opens a rounded popup anchored to it, like the
 * iOS 26 pull-down menu (no Material ripple or elevation look). [contentDescription] is the
 * `.accessibilityLabel` of an icon-only label (e.g. `moreOptions` on an ellipsis).
 */
@Composable
fun OmiMenu(
    sections: List<MenuSection>,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
    label: @Composable () -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    val labelled = if (contentDescription != null) Modifier.semantics { this.contentDescription = contentDescription } else Modifier
    Box(modifier.plainButton { open = true }.then(labelled)) {
        label()
        if (open) MenuPopup(sections) { open = false }
    }
}

@Composable
fun MenuPopup(sections: List<MenuSection>, onDismiss: () -> Unit) {
    val haptics = rememberHaptics()
    val scale by animateFloatAsState(1f, spring(dampingRatio = 0.8f, stiffness = DS.Motion.stiffness(0.3f)), label = "menu")
    Popup(popupPositionProvider = AnchorBelow, onDismissRequest = onDismiss, properties = PopupProperties(focusable = true)) {
        OmiColorScheme(LocalOmiDark.current) {
            Column(
                Modifier
                    .graphicsLayer { scaleX = scale; scaleY = scale; transformOrigin = TransformOrigin(1f, 0f) }
                    .widthIn(min = 250.dp, max = 280.dp)
                    .width(IntrinsicSize.Max)
                    .shadow(24.dp, MenuShape, ambientColor = Color.Black.copy(alpha = 0.3f), spotColor = Color.Black.copy(alpha = 0.3f))
                    .background(menuBackground(), MenuShape)
                    .padding(vertical = DS.Spacing.sm),
            ) {
                sections.forEachIndexed { index, section ->
                    if (index > 0) Box(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs + 2.dp).heightIn(min = 8.dp).background(DS.Palette.hairline.copy(alpha = 0.5f)))
                    section.header?.let {
                        Text(it, style = DS.Typography.caption, color = DS.Palette.inkTertiary, modifier = Modifier.padding(horizontal = DS.Spacing.lg + 2.dp, vertical = DS.Spacing.xs))
                    }
                    section.items.forEach { item ->
                        val tint = if (item.destructive) DS.Palette.live else DS.Palette.ink
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .heightIn(min = 44.dp)
                                .pressable(pressedScale = 1f, pressedAlpha = 0.6f, haptic = false) {
                                    haptics.selection()
                                    onDismiss()
                                    item.action()
                                }
                                .padding(horizontal = DS.Spacing.lg + 2.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(item.title, style = DS.Typography.body, color = tint, modifier = Modifier.weight(1f))
                            if (item.systemImage != null) {
                                Spacer(Modifier.width(DS.Spacing.md))
                                SFImage(item.systemImage, size = 17.sp, tint = tint)
                            }
                        }
                    }
                }
            }
        }
    }
}

private val MenuShape = RoundedCornerShape(22.dp)

@Composable
private fun menuBackground(): Color = if (LocalOmiDark.current) hex(0x2C2C2E) else hex(0xF9F9F9)

/** Below the anchor, right edges aligned, flipped above when there is no room (iOS pull-down). */
private object AnchorBelow : PopupPositionProvider {
    override fun calculatePosition(anchorBounds: IntRect, windowSize: IntSize, layoutDirection: LayoutDirection, popupContentSize: IntSize): IntOffset {
        val margin = 16
        val x = (anchorBounds.right - popupContentSize.width).coerceIn(margin, maxOf(margin, windowSize.width - popupContentSize.width - margin))
        val below = anchorBounds.bottom + 8
        val y = if (below + popupContentSize.height <= windowSize.height - margin) below else maxOf(margin, anchorBounds.top - popupContentSize.height - 8)
        return IntOffset(x, y)
    }
}
