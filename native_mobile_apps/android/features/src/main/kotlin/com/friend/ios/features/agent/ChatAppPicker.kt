package com.friend.ios.features.agent

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.core.models.OmiApp
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.service.LocalChatStore
import kotlinx.coroutines.launch

/**
 * Port of `ChatAppPicker.swift`: the chat header's "Talk to..." menu (Flutter `chat_apps_drawer`):
 * Omi, or one of the enabled apps that can chat. Each keeps its own history; switching waits until
 * an answer has finished.
 */
@Composable
fun ChatAppPicker(modifier: Modifier = Modifier) {
    val chat = LocalChatStore.current
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { chat.loadChatApps() }
    val noApps = L("nativeNoChatApps")
    val rows = listOf(MenuItem("Omi", if (chat.chatApp == null) "checkmark" else null) { scope.launch { chat.talk(null) } }) +
        chat.chatApps.map { app -> MenuItem(app.name, if (chat.chatApp?.id == app.id) "checkmark" else null) { scope.launch { chat.talk(app) } } }
    val sections = buildList {
        add(MenuSection(header = L("nativeTalkTo"), items = rows))
        if (chat.chatApps.isEmpty()) add(MenuSection(items = listOf(MenuItem(noApps) {})))
    }
    val label: @Composable () -> Unit = {
        HStack(
            Modifier.padding(horizontal = DS.Spacing.sm).heightIn(min = DS.Size.headerButton),
            spacing = DS.Spacing.xs,
        ) {
            chat.chatApp?.let { ChatAppPicture(it, 22.dp) }
            // As the device pill on Home: the name and a small chevron, no capsule.
            Text(chat.chatApp?.name ?: "Omi", style = TextStyles.body.medium(), color = DS.Palette.ink, maxLines = 1)
            SFImage("chevron.down", size = 11.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
        }
    }
    // Its value says who the chat talks to (iOS `.accessibilityValue`).
    val talkTo = L("nativeTalkTo")
    val value = chat.chatApp?.name ?: "Omi"
    if (chat.isStreaming) {
        Box(
            modifier.alpha(0.5f).clearAndSetSemantics {
                contentDescription = talkTo
                stateDescription = value
                disabled()
            },
        ) { label() }
    } else {
        OmiMenu(sections, modifier.semantics { stateDescription = value }, contentDescription = talkTo, label = label)
    }
}

/** The app's round picture (`AsyncImage` with the fill as placeholder). */
@Composable
internal fun ChatAppPicture(app: OmiApp, size: Dp) {
    AsyncImage(
        model = app.imageURL,
        contentDescription = null,
        contentScale = ContentScale.Crop,
        modifier = Modifier.size(size).clip(CircleShape).background(DS.Palette.fill),
    )
}
