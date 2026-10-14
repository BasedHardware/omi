package com.friend.ios.features.onboarding

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first

private class SetupItem(val key: String, val symbol: String, /** How long this one takes, so the list does not tick like a metronome. */ val seconds: Double)

private val items = listOf(
    SetupItem("nativeSetupProfile", "person.crop.circle", 1.3),
    SetupItem("nativeSetupVoice", "waveform", 1.8),
    SetupItem("nativeSetupLanguage", "character.bubble", 1.4),
    SetupItem("nativeSetupMemory", "brain", 1.9),
    SetupItem("nativeSetupSummaries", "text.alignleft", 1.5),
    SetupItem("nativeSetupFinal", "checkmark.seal", 1.4),
)
private const val REVIEW_AFTER_STEP = 1

/**
 * Port of `SetupStep.swift`. "Setting up your Omi": steps arrive one by one, each with a
 * barely-there tick, and are checked off with a light one, about ten seconds in all. The rating
 * ask comes right after the first step, while there is plenty of time left, as an alert; the
 * steps keep running underneath and the flow never finishes while it is open.
 */
@Composable
internal fun SetupStep(onFinished: () -> Unit) {
    val context = LocalContext.current
    val haptics = rememberHaptics()
    var shown by remember { mutableIntStateOf(0) }
    var completed by remember { mutableIntStateOf(0) }
    var asksForReview by remember { mutableStateOf(false) }
    val list = rememberLazyListState()
    Column(Modifier.fillMaxSize()) {
        OnboardingHeader(
            L("nativeKickerAlmostDone"), L("nativeSetupTitle"), L("nativeSetupSubtitle"),
            modifier = Modifier.padding(top = DS.Spacing.section + 44.dp).padding(bottom = DS.Spacing.xl),
        )
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = list,
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(start = DS.Spacing.gutter, end = DS.Spacing.gutter, bottom = DS.Spacing.section),
        ) {
            itemsIndexed(items.take(shown)) { index, item ->
                var appeared by remember { mutableStateOf(false) }
                LaunchedEffect(Unit) { appeared = true }
                AnimatedVisibility(appeared, enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard())) {
                    SetupRow(item, done = index < completed)
                }
            }
        }
        // The progress line.
        val fraction by animateFloatAsState(completed.toFloat() / items.size, tween(600), label = "setup-progress")
        BoxWithConstraints(
            Modifier.padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.xl).fillMaxWidth().height(3.dp)
                .background(DS.Palette.ink.copy(alpha = 0.1f), CircleShape),
        ) {
            Box(Modifier.width(maxWidth * fraction).height(3.dp).background(DS.Palette.agent, CircleShape))
        }
    }
    if (asksForReview) {
        OmiAlert(
            title = L("nativeReviewTitle"),
            message = L("nativeReviewBody"),
            buttons = listOf(
                DialogButton(L("nativeReviewNo"), DialogButton.Role.Cancel) { asksForReview = false },
                DialogButton(L("nativeReviewYes")) {
                    asksForReview = false
                    // `requestReview`: the store listing (no in-app review library in this build).
                    runCatching {
                        context.startActivity(
                            Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.friend.ios")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                        )
                    }
                },
            ),
            onDismiss = { asksForReview = false },
        )
    }
    LaunchedEffect(Unit) {
        var askedForReview = false
        for ((index, item) in items.withIndex()) {
            shown = index + 1
            runCatching { list.animateScrollToItem(index) }
            haptics.soft()
            delay((item.seconds * 1000).toLong())
            completed = index + 1
            haptics.tap()
            if (completed == REVIEW_AFTER_STEP && !askedForReview) {
                askedForReview = true
                delay(400)
                asksForReview = true
            }
            delay(250)
        }
        // Never finish while the rating ask is open.
        snapshotFlow { asksForReview }.first { !it }
        haptics.success()
        delay(900)
        onFinished()
    }
}

@Composable
private fun SetupRow(item: SetupItem, done: Boolean) {
    HStack(Modifier.fillMaxWidth(), spacing = DS.Spacing.md) {
        Box(Modifier.size(28.dp), contentAlignment = Alignment.Center) {
            if (done) {
                SFImage("checkmark.circle.fill", size = 22.sp, tint = DS.Palette.agent)
            } else {
                OmiProgress(tint = DS.Palette.agent)
            }
        }
        Box(Modifier.width(24.dp), contentAlignment = Alignment.Center) {
            SFImage(item.symbol, size = 17.sp, tint = if (done) DS.Palette.inkSecondary else DS.Palette.ink)
        }
        Text(L(item.key), style = TextStyles.body.medium(), color = if (done) DS.Palette.inkSecondary else DS.Palette.ink, modifier = Modifier.weight(1f))
    }
}
