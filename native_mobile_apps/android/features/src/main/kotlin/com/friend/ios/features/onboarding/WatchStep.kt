package com.friend.ios.features.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.service.watch.WatchStore
import com.friend.ios.service.watch.isAvailable
import com.friend.ios.service.watch.isWatchAppInstalled
import com.friend.ios.service.watch.ping

/**
 * Port of `WatchStep.swift`: the paired watch as a recording source (Flutter's Apple Watch device
 * and `apple_watch_permission_page`): is the Omi watch app there, and may it use the microphone.
 * The watch asks for the microphone itself and answers back; recordings then start on the wrist.
 * Only on the path when a watch is paired (on Android a Wear OS watch connected to the phone).
 */
@Composable
internal fun WatchStep(watch: WatchStore?, onContinue: () -> Unit) {
    var showsHelp by remember { mutableStateOf(false) }
    val installed = watch?.isWatchAppInstalled == true || watch?.isAvailable == true
    LaunchedEffect(Unit) { watch?.ping() }

    OnboardingLayout(
        kicker = L("nativeKickerAppleWatch"), title = L("nativeWatchStepTitle"), subtitle = L("nativeWatchStepShort"),
        button = StepButton(L("continueButton"), action = onContinue),
    ) {
        Box(Modifier.fillMaxWidth().height(110.dp), contentAlignment = Alignment.Center) {
            SFImage("applewatch", size = 72.sp, weight = FontWeight.ExtraLight, tint = DS.Palette.ink)
        }
        RowList(
            listOf(
                {
                    WatchRow(
                        "applewatch", L("nativeWatchAppRow"),
                        if (installed) L("nativeWatchAppInstalled") else L("nativeWatchAppMissing"),
                    ) {
                        if (installed) {
                            SFImage("checkmark.circle.fill", size = 20.sp, tint = DS.Palette.success)
                        } else {
                            SFImage("arrow.down.circle", size = 20.sp, tint = DS.Palette.inkTertiary)
                        }
                    }
                },
                { MicrophoneRow(watch, installed) },
            ),
        )
        Text(
            L("nativeWatchNeedHelp"),
            style = TextStyles.subheadline.copy(fontWeight = FontWeight.SemiBold),
            color = DS.Palette.inkSecondary,
            modifier = Modifier.align(Alignment.CenterHorizontally).plainButton { showsHelp = true }
                .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
        )
    }
    if (showsHelp) {
        OmiAlert(
            title = L("nativeWatchNeedHelp"),
            message = L("nativeWatchTroubleshooting"),
            buttons = listOf(DialogButton(L("gotIt"), DialogButton.Role.Cancel)),
            onDismiss = { showsHelp = false },
        )
    }
}

@Composable
private fun MicrophoneRow(watch: WatchStore?, installed: Boolean) {
    val granted = watch?.microphoneGranted
    val requesting = watch?.isRequestingMicrophone == true
    val detail = when {
        granted == true -> L("nativeWatchMicAllowed")
        granted == false -> L("nativeWatchMicDenied")
        requesting -> L("nativeWatchMicLookAtWatch")
        else -> L("nativeWatchMicReason")
    }
    WatchRow("mic", L("microphonePermission"), detail) {
        val state = when {
            granted == true -> 0
            requesting -> 1
            else -> 2
        }
        AnimatedContent(
            targetState = state,
            transitionSpec = { (fadeIn(DS.Motion.snappy()) + scaleIn(DS.Motion.snappy())) togetherWith fadeOut(DS.Motion.snappy()) },
            label = "watchMicrophone",
        ) { shown ->
            when (shown) {
                0 -> SFImage("checkmark.circle.fill", size = 20.sp, tint = DS.Palette.success)
                1 -> OmiProgress(Modifier.size(20.dp))
                // `.disabled(!installed)`: dimmed and inert until the watch app is there.
                else -> OmiPillButton(
                    L("allow"),
                    modifier = Modifier.alpha(if (installed) 1f else 0.4f),
                    onClick = { if (installed) watch?.requestMicrophone() },
                )
            }
        }
    }
}

@Composable
private fun WatchRow(icon: String, title: String, detail: String, trailing: @Composable () -> Unit) {
    HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.md), spacing = DS.Spacing.md) {
        Box(Modifier.width(28.dp), contentAlignment = Alignment.CenterStart) { SFImage(icon, size = 20.sp, tint = DS.Palette.ink) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, style = TextStyles.body.copy(fontWeight = FontWeight.Medium), color = DS.Palette.ink)
            Text(detail, style = TextStyles.subheadline, color = DS.Palette.inkSecondary)
        }
        trailing()
    }
}
