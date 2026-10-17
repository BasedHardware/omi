package com.friend.ios.features.device

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.R

/**
 * Port of `DeviceHero` (`OmiComponents/DeviceLive.swift`): the Omi itself, a calm ring while
 * searching, a blue glow that breathes while it streams. (`LiveTryCard` in the same Swift file is
 * not used by any iOS screen, so it has no port.)
 */
@Composable
fun DeviceHero(state: DeviceHeroState) {
    val streaming = state == DeviceHeroState.Streaming
    val transition = rememberInfiniteTransition(label = "hero")
    val pulse by transition.animateFloat(
        0f, 1f,
        infiniteRepeatable(tween(if (streaming) 1400 else 2000, easing = LinearEasing), if (streaming) RepeatMode.Reverse else RepeatMode.Restart),
        label = "pulse",
    )
    Box(Modifier.fillMaxWidth().height(210.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(200.dp)
                .scale(0.92f + 0.2f * pulse)
                .alpha(1f - pulse)
                .border(2.dp, if (streaming) BLUE.copy(alpha = 0.5f) else DS.Palette.ink.copy(alpha = 0.15f), CircleShape),
        )
        if (streaming) {
            Box(Modifier.size(150.dp).scale(0.85f + 0.3f * pulse).blur(30.dp).background(BLUE.copy(alpha = 0.35f), CircleShape))
        }
        Box(contentAlignment = Alignment.Center) {
            Image(painterResource(R.drawable.omi_device), null, Modifier.size(128.dp), contentScale = ContentScale.Fit)
            if (streaming) Box(Modifier.size(14.dp).blur(3.dp).alpha(0.55f + 0.45f * pulse).background(BLUE, CircleShape))
        }
    }
}

enum class DeviceHeroState { Searching, Connecting, Streaming }

private val BLUE = Color(0.25f, 0.55f, 1.0f)
