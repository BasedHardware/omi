package com.friend.ios.features.components

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.core.DeepLink
import com.friend.ios.features.conversations.openURL

/**
 * Port of `OpenUpgradeAction.swift`: opens the plans from anywhere (a locked conversation). The
 * shell may provide its own (iOS opens Settings at Plan & usage); without one, the app's own
 * `omi://settings/account` link opens Settings > Account, where the plans are.
 */
val LocalOpenUpgrade = staticCompositionLocalOf<(() -> Unit)?> { null }

@Composable
fun rememberOpenUpgrade(): () -> Unit {
    LocalOpenUpgrade.current?.let { return it }
    val context = LocalContext.current
    return { openURL(context, DeepLink.Account.url) }
}
