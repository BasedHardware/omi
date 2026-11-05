package com.friend.ios.design

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer

/**
 * `.contextMenu { }` + `.onTapGesture { }`: a tap runs [onTap]; a long press lifts the content a
 * little (the system "lift"), ticks, and opens the menu anchored to it.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ContextMenuBox(
    sections: () -> List<MenuSection>,
    modifier: Modifier = Modifier,
    onTap: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    val haptics = rememberHaptics()
    val lift by animateFloatAsState(if (open) 1.03f else 1f, DS.Motion.snappy(), label = "lift")
    Box(
        modifier
            .graphicsLayer { scaleX = lift; scaleY = lift }
            .combinedClickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = { onTap?.invoke() },
                onLongClick = {
                    haptics.tap(DSHaptics.Style.Medium)
                    open = true
                },
            ),
    ) {
        content()
        if (open) MenuPopup(sections()) { open = false }
    }
}
