package com.friend.ios.design

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.Role

/**
 * SwiftUI `ButtonStyle` press feedback without Android's ripple: scale and dim while pressed
 * (`.snappy(duration: 0.2)`), and a light haptic on press down. `.hapticTap` is 0.97 / 0.9.
 */
fun Modifier.pressable(
    enabled: Boolean = true,
    pressedScale: Float = 0.97f,
    pressedAlpha: Float = 0.9f,
    haptic: Boolean = true,
    role: Role = Role.Button,
    onClick: () -> Unit,
): Modifier = composed {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val haptics = rememberHaptics()
    LaunchedEffect(pressed) { if (pressed && haptic) haptics.tap() }
    val spec = spring<Float>(dampingRatio = 0.85f, stiffness = DS.Motion.stiffness(0.2f))
    val scale by animateFloatAsState(if (pressed) pressedScale else 1f, spec, label = "press-scale")
    val alpha by animateFloatAsState(if (pressed) pressedAlpha else 1f, spec, label = "press-alpha")
    this
        .graphicsLayer { scaleX = scale; scaleY = scale; this.alpha = alpha }
        .clickable(interactionSource = source, indication = null, enabled = enabled, role = role, onClick = onClick)
}

/** `.buttonStyle(.plain)`: tappable with no visual feedback (the system dims briefly; we don't). */
fun Modifier.plainButton(enabled: Boolean = true, onClick: () -> Unit): Modifier =
    pressable(enabled = enabled, pressedScale = 1f, pressedAlpha = 0.7f, haptic = false, onClick = onClick)
