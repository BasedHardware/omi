package com.friend.ios.features.agent

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ChatFile
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarButton

/**
 * `FilePreviewSheet` of `ChatMedia.swift`: a sent photo, large; or a sent file's name and type,
 * with "Ask about it" (a question about the file into the composer).
 */
@Composable
fun FilePreviewSheet(file: ChatFile, onDismiss: () -> Unit, onAsk: () -> Unit) {
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(
            if (file.isImage) "" else file.name,
            leading = { SheetBarButton(L("close"), onClick = onDismiss) },
            trailing = {
                SheetBarButton(L("nativeChatAskAboutFile"), prominent = true) {
                    onDismiss()
                    onAsk()
                }
            },
        )
        Box(Modifier.fillMaxWidth().weight(1f).background(DS.Palette.background), contentAlignment = Alignment.Center) {
            if (file.isImage) {
                AttachmentThumbnail(
                    file.localPreview, file.thumbnailURL,
                    Modifier.padding(DS.Spacing.gutter).fillMaxSize().clip(ContinuousRoundedShape(DS.Radius.md)),
                    fit = true,
                )
            } else {
                Column(
                    Modifier.padding(DS.Spacing.gutter),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
                ) {
                    SFImage("doc.text", size = 44.sp, weight = FontWeight.Light, tint = DS.Palette.inkSecondary)
                    Text(file.name, style = DS.Typography.body.copy(fontWeight = FontWeight.Medium), color = DS.Palette.ink, textAlign = TextAlign.Center)
                    Text(L("nativeChatFileSent"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                }
            }
        }
    }
}
