package com.friend.ios.features.settings

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.runtime.Composable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.unit.IntOffset

/**
 * `NavigationLink { Destination() }` inside one settings screen: a page pushed over [base] that is
 * not a deep-linkable `SettingsTopic` (Clean up, Ignored voices, the language list, ...). Slides
 * like `OmiNavigationStack`; the system back gesture closes it.
 */
@Composable
fun <T : Any> SettingsSubPageHost(page: T?, onClose: () -> Unit, base: @Composable () -> Unit, content: @Composable (T) -> Unit) {
    val holder = rememberSaveableStateHolder()
    BackHandler(enabled = page != null, onBack = onClose)
    AnimatedContent(
        targetState = page,
        transitionSpec = {
            val spec = tween<IntOffset>(350, easing = CubicBezierEasing(0.2f, 0.9f, 0.1f, 1f))
            if (targetState != null) slideInHorizontally(spec) { it } togetherWith slideOutHorizontally(spec) { -it / 3 }
            else slideInHorizontally(spec) { -it / 3 } togetherWith slideOutHorizontally(spec) { it }
        },
        label = "settings-subpage",
    ) { current ->
        if (current == null) holder.SaveableStateProvider("base") { base() } else content(current)
    }
}
