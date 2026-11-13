package com.friend.ios.design

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/** `.presentationDetents`: medium (half height) and/or large. */
enum class Detent { Medium, Large }

/**
 * `.sheet` in the iOS look: the page color, large continuous top corners, a small grabber, no
 * Material tint or elevation overlay. `[Medium, Large]` opens at half height and drags to full;
 * `[Large]` opens full.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OmiSheet(
    onDismiss: () -> Unit,
    detents: Set<Detent> = setOf(Detent.Large),
    showsGrabber: Boolean = Detent.Medium in detents,
    content: @Composable ColumnScope.() -> Unit,
) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = Detent.Medium !in detents)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        // Like an iOS sheet, it stops below the status bar with a sliver of the screen behind showing.
        modifier = Modifier.windowInsetsPadding(WindowInsets.statusBars).padding(top = 10.dp),
        sheetState = state,
        shape = RoundedCornerShape(topStart = 38.dp, topEnd = 38.dp),
        containerColor = DS.Palette.background,
        contentColor = DS.Palette.ink,
        scrimColor = Color.Black.copy(alpha = 0.4f),
        tonalElevation = 0.dp,
        dragHandle = if (showsGrabber) {
            { Box(Modifier.padding(top = 5.dp, bottom = 8.dp).size(36.dp, 5.dp).background(DS.Palette.inkTertiary.copy(alpha = 0.5f), CircleShape)) }
        } else null,
        content = content,
    )
}
