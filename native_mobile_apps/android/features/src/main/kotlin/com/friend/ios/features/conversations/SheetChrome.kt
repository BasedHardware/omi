package com.friend.ios.features.conversations

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton

/**
 * A sheet's `NavigationStack` bar with `.navigationBarTitleDisplayMode(.inline)`: the
 * `.cancellationAction` on the left, the 17 pt semibold title, the `.confirmationAction` on the
 * right. iOS 26 draws toolbar buttons as glass capsules (text) or circles (a glyph).
 */
@Composable
fun SheetBar(
    title: String,
    modifier: Modifier = Modifier,
    leading: (@Composable RowScope.() -> Unit)? = null,
    trailing: (@Composable RowScope.() -> Unit)? = null,
) {
    Box(modifier.fillMaxWidth().height(56.dp).padding(horizontal = DS.Spacing.lg)) {
        leading?.let { Row(Modifier.align(Alignment.CenterStart), verticalAlignment = Alignment.CenterVertically, content = it) }
        Text(
            title,
            style = TextStyles.headline,
            color = DS.Palette.ink,
            textAlign = TextAlign.Center,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.align(Alignment.Center).padding(horizontal = 96.dp),
        )
        trailing?.let { Row(Modifier.align(Alignment.CenterEnd), verticalAlignment = Alignment.CenterVertically, content = it) }
    }
}

/** A toolbar text button ("Cancel", "Done", "Save") as an iOS 26 glass capsule. */
@Composable
fun SheetBarButton(title: String, enabled: Boolean = true, prominent: Boolean = false, onClick: () -> Unit) {
    Box(
        Modifier
            .heightIn(min = 44.dp)
            .glassCapsule()
            .plainButton(enabled = enabled, onClick = onClick)
            .padding(horizontal = DS.Spacing.lg),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            title,
            style = TextStyles.body.copy(fontWeight = if (prominent) FontWeight.SemiBold else FontWeight.Normal),
            color = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled,
        )
    }
}

/** A toolbar glyph button (`xmark`, `paperplane.fill`) as an iOS 26 glass circle. */
@Composable
fun SheetBarIcon(systemImage: String, enabled: Boolean = true, onClick: () -> Unit) {
    Box(
        Modifier.height(44.dp).padding(0.dp).glassCapsule().plainButton(enabled = enabled, onClick = onClick).padding(horizontal = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        SFImage(systemImage, size = 19.sp, weight = FontWeight.Medium, tint = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
    }
}

@Composable
internal fun Modifier.glassCapsule(): Modifier {
    val dark = LocalOmiDark.current
    return this
        .background(if (dark) hex(0x282828) else hex(0xF5F5F5), CircleShape)
        .border(1.dp, if (dark) hex(0x363636) else hex(0xE4E4E4), CircleShape)
}
