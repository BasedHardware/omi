package com.friend.ios.design

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.text.selection.LocalTextSelectionColors
import androidx.compose.foundation.text.selection.TextSelectionColors
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf

/** True when Omi renders its dark palette (the `\.colorScheme` of the iOS app). */
val LocalOmiDark = staticCompositionLocalOf { true }

/** `flutter.appearanceMode`: light, dark or system. Dark is the default, as on iOS. */
enum class AppearanceMode(val raw: String) {
    Light("light"), Dark("dark"), System("system");

    companion object {
        fun from(raw: String?): AppearanceMode = entries.firstOrNull { it.raw == raw } ?: Dark
    }
}

@Composable
fun OmiTheme(appearance: AppearanceMode = AppearanceMode.Dark, content: @Composable () -> Unit) {
    val dark = when (appearance) {
        AppearanceMode.Light -> false
        AppearanceMode.Dark -> true
        AppearanceMode.System -> isSystemInDarkTheme()
    }
    OmiColorScheme(dark, content)
}

/** Forces one scheme for a subtree (onboarding is always dark). */
@Composable
fun OmiColorScheme(dark: Boolean, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalOmiDark provides dark) {
        CompositionLocalProvider(
            LocalContentColor provides DS.Palette.ink,
            LocalTextStyle provides DS.Typography.body,
            LocalTextSelectionColors provides TextSelectionColors(DS.Palette.agent, DS.Palette.agent.copy(alpha = 0.3f)),
            content = content,
        )
    }
}
