package com.friend.ios.features.components

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold

/** Port of `OmiToast` (`OmiComponents/ConversationToasts.swift`). */
@Composable
fun OmiToast(text: String, systemImage: String, modifier: Modifier = Modifier, actionTitle: String? = null, action: (() -> Unit)? = null) {
    HStack(
        modifier
            .padding(horizontal = DS.Spacing.lg)
            .fillMaxWidth()
            .shadow(12.dp, CircleShape, ambientColor = Color.Black.copy(alpha = 0.12f), spotColor = Color.Black.copy(alpha = 0.12f))
            .omiSurface(CircleShape)
            .heightIn(min = 48.dp)
            .padding(horizontal = DS.Spacing.lg),
        spacing = DS.Spacing.md,
    ) {
        SFImage(systemImage, tint = DS.Palette.inkSecondary)
        Text(text, style = DS.Typography.callout.medium(), color = DS.Palette.ink, maxLines = 2, modifier = Modifier.weight(1f))
        if (actionTitle != null && action != null) {
            Text(actionTitle, style = DS.Typography.callout.semibold(), color = DS.Palette.agent, modifier = Modifier.plainButton(onClick = action))
        }
    }
}
