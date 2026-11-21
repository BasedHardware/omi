package com.friend.ios.features.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.CalmBackground
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiChip
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DebugLaunch
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * After "Setting up your Omi": the "You're ready" moment, then (if wanted) the short introduction.
 * [onFinished] lands on Home; its argument is a Settings section to open there (the For you
 * card's "Choose how often"), or null.
 */
@Composable
internal fun ReadyFlow(name: String, hasOmi: Boolean, onFinished: (String?) -> Unit) {
    var showsTour by remember { mutableStateOf(false) }
    AnimatedContent(
        targetState = showsTour,
        transitionSpec = {
            if (targetState) (slideInHorizontally(DS.Motion.standard()) { it } + fadeIn()).togetherWith(fadeOut())
            else fadeIn().togetherWith(fadeOut())
        },
        label = "ready-flow",
    ) { tour ->
        if (tour) {
            IntroTourScreen(onFinished)
        } else {
            ReadyStep(name, hasOmi, onTour = { showsTour = true }, onSkip = { onFinished(null) })
        }
    }
}

/**
 * "You're ready, Ada." A ring draws itself around a check, a soft tap, one line on what
 * happens now. Centered, with air: the calm end of setup.
 */
@Composable
internal fun ReadyStep(name: String, hasOmi: Boolean, onTour: () -> Unit, onSkip: () -> Unit) {
    val haptics = rememberHaptics()
    var drawn by remember { mutableStateOf(false) }
    val reveal by animateFloatAsState(if (drawn) 1f else 0f, tween(900), label = "ready-reveal")
    val firstName = name.split(" ").firstOrNull().orEmpty()
    Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.heightIn(min = DS.Spacing.section).weight(1f))
        ReadyMark(reveal, Modifier.padding(bottom = DS.Spacing.section + DS.Spacing.lg))
        Column(
            Modifier.padding(horizontal = DS.Spacing.section).alpha(reveal).offset(y = (8 * (1 - reveal)).dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        ) {
            Text(
                if (firstName.isEmpty()) L("nativeReadyTitleNoName") else L("nativeReadyTitle", firstName),
                style = DS.Typography.display, color = DS.Palette.ink, textAlign = TextAlign.Center,
            )
            Text(if (hasOmi) L("nativeReadyBody") else L("nativeReadyBodyPhone"), style = DS.Typography.body, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
        }
        if (hasOmi) {
            OmiChip(L("nativeReadyListening"), Modifier.padding(top = DS.Spacing.xl).alpha(reveal), systemImage = "waveform", tint = DS.Palette.agent)
        }
        Spacer(Modifier.heightIn(min = DS.Spacing.section).weight(1f))
        Column(
            Modifier.padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.md).alpha(reveal),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
        ) {
            OnboardingButton(StepButton(L("nativeReadyTour"), action = onTour))
            Box(Modifier.fillMaxWidth().heightIn(min = 44.dp), contentAlignment = Alignment.Center) {
                Text(
                    L("nativeReadySkip"), style = TextStyles.callout.semibold(), color = DS.Palette.inkSecondary,
                    modifier = Modifier.plainButton(onClick = onSkip).padding(DS.Spacing.sm),
                )
            }
        }
    }
    LaunchedEffect(Unit) {
        delay(250)
        drawn = true
        delay(650)
        haptics.success()
    }
}

/**
 * A thin ring that draws itself (hairline gray warming into Omi blue) around a check, with a
 * soft blue glow behind it.
 */
@Composable
private fun ReadyMark(drawn: Float, modifier: Modifier = Modifier) {
    val hairline = DS.Palette.hairline
    val start = DS.Palette.inkTertiary.copy(alpha = 0.4f)
    val agent = DS.Palette.agent
    Box(modifier.size(180.dp), contentAlignment = Alignment.Center) {
        // The blurred 150 pt glow: a radial fade (a blur would be clipped to its square on Android).
        val glow = DS.Glow.live
        Canvas(Modifier.requiredSize(240.dp)) {
            drawCircle(
                Brush.radialGradient(
                    0f to glow.copy(alpha = glow.alpha * 0.8f * drawn),
                    0.45f to glow.copy(alpha = glow.alpha * 0.55f * drawn),
                    1f to glow.copy(alpha = 0f),
                ),
            )
        }
        Canvas(Modifier.size(128.dp)) {
            val width = DS.Stroke.hero.toPx()
            drawCircle(hairline, style = Stroke(width))
            rotate(-90f) {
                drawArc(
                    Brush.sweepGradient(listOf(start, agent)), 0f, 360f * drawn, useCenter = false,
                    style = Stroke(width * 1.5f, cap = StrokeCap.Round),
                )
            }
        }
        SFImage(
            "checkmark", Modifier.scale(0.6f + 0.4f * drawn).alpha(drawn),
            size = 40.sp, weight = FontWeight.Light, tint = DS.Palette.ink,
        )
    }
}

// The introduction

/**
 * Five short pages on how Omi works, each with a small live demo built from the app's own rows.
 * Skippable, swipeable. Also replayed on its own from Help. [onFinished] gets a Settings section
 * to open afterwards, or null.
 */
@Composable
fun IntroTourScreen(onFinished: (String?) -> Unit) {
    val pages = IntroPage.entries
    // --es omiIntroPage <n>: open on a page (QA).
    val initial = (DebugLaunch.string("omiIntroPage")?.toIntOrNull() ?: 0).coerceIn(0, pages.size - 1)
    val pager = rememberPagerState(initialPage = initial) { pages.size }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    Box(Modifier.fillMaxSize()) {
        CalmBackground()
        Column(Modifier.fillMaxSize().systemBarsPadding()) {
            HStack(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.gutter).padding(top = DS.Spacing.sm)) {
                Text(
                    L("nativeIntroKicker").uppercase(),
                    style = DS.Typography.label.copy(letterSpacing = DS.Tracking.label.sp),
                    color = DS.Palette.inkTertiary,
                    modifier = Modifier.weight(1f),
                )
                Box(Modifier.heightIn(min = 44.dp).plainButton { onFinished(null) }, contentAlignment = Alignment.Center) {
                    Text(L("skip"), style = TextStyles.callout.semibold(), color = DS.Palette.inkSecondary)
                }
            }
            HorizontalPager(pager, Modifier.weight(1f).fillMaxWidth()) { index ->
                IntroCard(pages[index], isActive = pager.currentPage == index, onSetting = { onFinished("assistant") })
            }
            PageDots(pages.size, pager.currentPage, Modifier.align(Alignment.CenterHorizontally).padding(bottom = DS.Spacing.lg))
            OnboardingButton(
                StepButton(if (pager.currentPage == pages.size - 1) L("nativeIntroDone") else L("nativeIntroNext"), action = {
                    if (pager.currentPage < pages.size - 1) scope.launch { pager.animateScrollToPage(pager.currentPage + 1) } else onFinished(null)
                }),
                Modifier.padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.md),
            )
        }
    }
    var firstPage by remember { mutableStateOf(true) }
    LaunchedEffect(pager.currentPage) { if (firstPage) firstPage = false else haptics.selection() }
}

internal enum class IntroPage {
    Listen, Learn, Voices, ForYou, HandOver;

    val titleKey: String
        get() = when (this) {
            Listen -> "nativeIntroListenTitle"
            Learn -> "nativeIntroLearnTitle"
            Voices -> "nativeIntroVoicesTitle"
            ForYou -> "nativeIntroForYouTitle"
            HandOver -> "nativeIntroHandOverTitle"
        }

    val bodyKey: String
        get() = when (this) {
            Listen -> "nativeIntroListenBody"
            Learn -> "nativeIntroLearnBody"
            Voices -> "nativeIntroVoicesBody"
            ForYou -> "nativeIntroForYouBody"
            HandOver -> "nativeIntroHandOverBody"
        }
}

/** One page: the live demo on top, a title and a quiet line under it. */
@Composable
private fun IntroCard(page: IntroPage, isActive: Boolean, onSetting: () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.fillMaxWidth().heightIn(min = 230.dp).padding(top = DS.Spacing.lg), contentAlignment = Alignment.TopCenter) {
            when (page) {
                IntroPage.Listen -> ListenDemo(isActive)
                IntroPage.Learn -> MemoryDemo(isActive)
                IntroPage.Voices -> VoicesDemo(isActive)
                IntroPage.ForYou -> ForYouDemo(isActive)
                IntroPage.HandOver -> HandOverDemo(isActive)
            }
        }
        Column(Modifier.padding(horizontal = DS.Spacing.sm), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(L(page.titleKey), style = DS.Typography.largeTitle, color = DS.Palette.ink, textAlign = TextAlign.Center)
            Text(L(page.bodyKey), style = DS.Typography.body, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
        }
        when (page) {
            IntroPage.ForYou -> OmiChip(
                L("nativeIntroForYouSetting"), Modifier.plainButton(onClick = onSetting),
                systemImage = "slider.horizontal.3", tint = DS.Palette.agent,
            )
            IntroPage.HandOver -> Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                HStack(spacing = DS.Spacing.sm) {
                    SFImage("checkmark.circle", size = 16.sp, tint = DS.Palette.ink)
                    Text(L("nativeIntroOnItsOwn"), style = DS.Typography.callout, color = DS.Palette.ink)
                }
                HStack(spacing = DS.Spacing.sm) {
                    SFImage("hand.raised", size = 16.sp, tint = DS.Palette.ink)
                    Text(L("nativeIntroAsksFirst"), style = DS.Typography.callout, color = DS.Palette.ink)
                }
            }
            else -> Unit
        }
    }
}

/** Small dots under the pages; the current one is a short bar. */
@Composable
private fun PageDots(count: Int, current: Int, modifier: Modifier = Modifier) {
    val label = L("nativeIntroPage", "${current + 1}", "$count")
    Row(modifier.clearAndSetSemantics { contentDescription = label }, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        for (index in 0 until count) {
            val width by animateDpAsState(if (index == current) 18.dp else 6.dp, DS.Motion.snappy(), label = "page-dot")
            Box(
                Modifier.width(width).size(width = width, height = 6.dp)
                    .background(if (index == current) DS.Palette.ink else DS.Palette.ink.copy(alpha = 0.18f), CircleShape),
            )
        }
    }
}
