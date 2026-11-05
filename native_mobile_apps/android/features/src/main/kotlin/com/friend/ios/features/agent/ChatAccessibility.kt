package com.friend.ios.features.agent

import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription

/**
 * iOS `.accessibilityHint`: what a control does, read after its label. Compose has no hint, so
 * TalkBack gets it as the state description, which it reads right after the label and role.
 */
internal fun Modifier.accessibilityHint(hint: String): Modifier = semantics { stateDescription = hint }
