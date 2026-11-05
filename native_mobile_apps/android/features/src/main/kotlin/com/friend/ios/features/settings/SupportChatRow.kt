package com.friend.ios.features.settings

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import com.friend.ios.design.L
import com.friend.ios.features.components.OmiSectionBuilder

/**
 * Port of `SupportChatRow.swift`. Opens the support chat (Intercom, set by the app when the build
 * has its keys); `@Environment(\.supportChat)`. Null when the build has no support chat.
 */
val LocalSupportChat = staticCompositionLocalOf<(() -> Unit)?> { null }

/**
 * "Need help? Chat with us" (Flutter's Help and feedback sheet), only when the support chat is
 * configured; otherwise nothing, and the help center and feedback links stand alone.
 */
@Composable
fun OmiSectionBuilder.supportChatRow() {
    val supportChat = LocalSupportChat.current ?: return
    val title = L("needHelpChatWithUs")
    // `Button(L("needHelpChatWithUs"))`: a plain button row, no glyph.
    row(onClick = supportChat) { SettingsButtonText(title) }
}
