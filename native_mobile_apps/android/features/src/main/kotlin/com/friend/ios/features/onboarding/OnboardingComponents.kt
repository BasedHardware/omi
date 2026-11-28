package com.friend.ios.features.onboarding

import android.content.Context
import android.content.res.Configuration
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiStatusLine
import com.friend.ios.design.R
import com.friend.ios.design.SFImage
import com.friend.ios.design.Strings
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import java.util.Locale

/** One continuous line, no segments: a count of steps reads as "this will take a while". */
@Composable
internal fun OnboardingProgress(value: Double, modifier: Modifier = Modifier) {
    val fraction by animateFloatAsState(value.toFloat(), OnboardingScreenDefaults.stepAnimation(), label = "onboarding-progress")
    val label = L("nativeOnboardingProgress", "${(value * 100).toInt()}")
    BoxWithConstraints(
        modifier
            .fillMaxWidth()
            .height(3.dp)
            .background(DS.Palette.ink.copy(alpha = 0.12f), CircleShape)
            .clearAndSetSemantics { contentDescription = label },
    ) {
        Box(Modifier.width(maxOf(6.dp, maxWidth * fraction)).height(3.dp).background(DS.Palette.ink, CircleShape))
    }
}

/**
 * A quiet label naming the part of the setup, a large headline, at most one muted line under it.
 * [centered] for the hero steps (an image below), leading for the others.
 */
@Composable
internal fun OnboardingHeader(kicker: String, title: String, subtitle: String? = null, centered: Boolean = false, modifier: Modifier = Modifier) {
    val align = if (centered) TextAlign.Center else TextAlign.Start
    Column(
        modifier.fillMaxWidth().padding(horizontal = DS.Spacing.gutter),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
        horizontalAlignment = if (centered) Alignment.CenterHorizontally else Alignment.Start,
    ) {
        Text(kicker, style = TextStyles.footnote.semibold(), color = DS.Palette.inkTertiary, textAlign = align)
        Text(title, style = DS.Typography.display, color = DS.Palette.ink, textAlign = align)
        if (subtitle != null) {
            Text(subtitle, style = TextStyles.body, color = DS.Palette.inkSecondary, textAlign = align, modifier = Modifier.padding(top = DS.Spacing.xxs))
        }
    }
}

/** The onboarding's one surface: a softly filled rounded box with a hairline edge. */
@Composable
internal fun Modifier.onboardingCard(padding: Dp = DS.Spacing.lg): Modifier {
    val shape = ContinuousRoundedShape(DS.Radius.card)
    return this.fillMaxWidth()
        .background(DS.Palette.ink.copy(alpha = 0.05f), shape)
        .border(1.dp, DS.Palette.ink.copy(alpha = 0.08f), shape)
        .padding(padding)
}

/** A button of the step. */
internal class StepButton(
    val title: String,
    val isEnabled: Boolean = true,
    /** A way out (skip) rather than the step's goal: drawn quieter, without the arrow. */
    val isSecondary: Boolean = false,
    val action: () -> Unit,
)

internal object OnboardingLayoutDefaults {
    val secondaryHeight = 44.dp
}

/**
 * Header, content, and the buttons pinned to the bottom: one primary button, and under it the
 * slot of the quiet way out, kept even when empty so the button never moves between steps.
 * Content only scrolls where large text makes it taller than the screen.
 */
@Composable
internal fun OnboardingLayout(
    kicker: String,
    title: String,
    subtitle: String? = null,
    button: StepButton? = null,
    secondary: StepButton? = null,
    scrolls: Boolean = true,
    /** Headline centered over a hero image instead of leading. */
    centered: Boolean = false,
    /** A quiet line over the buttons while something happens on its own. */
    status: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(Modifier.fillMaxSize()) {
        val stack: @Composable (Modifier) -> Unit = { modifier ->
            Column(modifier, verticalArrangement = Arrangement.spacedBy(DS.Spacing.section)) {
                OnboardingHeader(kicker, title, subtitle, centered, Modifier.padding(top = DS.Spacing.lg))
                content()
            }
        }
        if (scrolls) {
            Box(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
                stack(Modifier.padding(bottom = DS.Spacing.lg))
            }
        } else {
            Box(Modifier.weight(1f).fillMaxWidth()) { stack(Modifier.fillMaxSize()) }
        }
        if (button != null || secondary != null || status != null) {
            Column(
                Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.gutter).padding(top = DS.Spacing.sm, bottom = DS.Spacing.sm),
                verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                AnimatedVisibility(status != null, enter = fadeIn(), exit = fadeOut()) {
                    OmiStatusLine(status.orEmpty(), Modifier.padding(bottom = DS.Spacing.md))
                }
                if (button != null) OnboardingButton(button)
                Box(Modifier.fillMaxWidth().height(OnboardingLayoutDefaults.secondaryHeight), contentAlignment = Alignment.Center) {
                    if (secondary != null) {
                        Text(
                            secondary.title,
                            style = TextStyles.callout.semibold(),
                            color = DS.Palette.inkSecondary,
                            modifier = Modifier.plainButton(enabled = secondary.isEnabled, onClick = secondary.action)
                                .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
                        )
                    }
                }
            }
        }
    }
}

/** White pill with a trailing arrow; quieter when it is a way out. */
@Composable
internal fun OnboardingButton(model: StepButton, modifier: Modifier = Modifier) {
    if (model.isSecondary) {
        Box(
            modifier.fillMaxWidth().heightIn(min = DS.Size.primaryButtonHeight)
                .pressable(enabled = model.isEnabled, pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = model.action)
                .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.md)),
            contentAlignment = Alignment.Center,
        ) {
            Text(model.title, style = DS.Typography.button, color = if (model.isEnabled) DS.Palette.ink else DS.Palette.inkDisabled)
        }
    } else {
        val enabled = model.isEnabled
        val ink = if (enabled) DS.Palette.onAccent else DS.Palette.inkDisabled
        Box(
            modifier.fillMaxWidth().heightIn(min = DS.Size.primaryButtonHeight)
                .pressable(enabled = enabled, pressedScale = 0.98f, pressedAlpha = 0.85f, onClick = model.action)
                .background(if (enabled) DS.Palette.accent else DS.Palette.fill, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            HStack(spacing = DS.Spacing.sm) {
                Text(model.title, style = DS.Typography.button, color = ink)
                SFImage("arrow.right", size = 17.sp, weight = FontWeight.SemiBold, tint = ink)
            }
        }
    }
}

/**
 * One line of a choice list: icon, title, and a check when chosen. No detail lines: the step's
 * one subtitle explains, the rows only name.
 */
@Composable
internal fun ChoiceRow(symbol: String, title: String, selected: Boolean = false, modifier: Modifier = Modifier, action: () -> Unit) {
    val haptics = rememberHaptics()
    HStack(
        modifier.fillMaxWidth().heightIn(min = 56.dp)
            .plainButton { haptics.selection(); action() }
            .padding(horizontal = DS.Spacing.lg),
        spacing = DS.Spacing.md,
    ) {
        Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) {
            SFImage(symbol, size = 20.sp, tint = if (selected) DS.Palette.ink else DS.Palette.inkSecondary)
        }
        Text(
            title,
            style = if (selected) TextStyles.body.semibold() else TextStyles.body,
            color = DS.Palette.ink,
            modifier = Modifier.weight(1f),
        )
        SFImage(
            if (selected) "checkmark.circle.fill" else "circle",
            size = 20.sp,
            tint = if (selected) DS.Palette.agent else DS.Palette.ink.copy(alpha = 0.25f),
        )
    }
}

/** Rows in one card, with hairlines between them. */
@Composable
internal fun RowList(rows: List<@Composable () -> Unit>, modifier: Modifier = Modifier) {
    Column(modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard(padding = 0.dp)) {
        rows.forEachIndexed { index, row ->
            row()
            if (index < rows.size - 1) {
                Box(
                    Modifier.fillMaxWidth().padding(start = DS.Spacing.lg + 28.dp + DS.Spacing.md)
                        .height(0.5.dp).background(DS.Palette.ink.copy(alpha = 0.08f)),
                )
            }
        }
    }
}

/** One line of status under a step: what it says, its symbol and colour. */
internal class StatusLine(val text: String, val symbol: String, val tint: Color)

@Composable
internal fun StatusLine.View(modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
        SFImage(symbol, size = 15.sp, tint = tint)
        Spacer(Modifier.width(DS.Spacing.sm))
        Text(text, style = TextStyles.subheadline.medium(), color = tint, textAlign = TextAlign.Center)
    }
}

/** The pendant, still: no rings, no pulse. A small badge can sit on it (a check, "1x"). */
@Composable
internal fun PendantImage(size: Dp = 140.dp, modifier: Modifier = Modifier, badge: @Composable () -> Unit = {}) {
    Box(modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Box(Modifier.size(size)) {
            Image(painterResource(R.drawable.omi_device), contentDescription = null, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
            Box(Modifier.align(Alignment.TopEnd).offset(x = -size * 0.04f, y = size * 0.04f)) { badge() }
        }
    }
}

/** `FlowLayout`: wraps chips onto as many lines as needed. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun FlowLayout(spacing: Dp, modifier: Modifier = Modifier, centered: Boolean = false, content: @Composable () -> Unit) {
    FlowRow(
        modifier,
        horizontalArrangement = if (centered) Arrangement.spacedBy(spacing, Alignment.CenterHorizontally) else Arrangement.spacedBy(spacing),
        verticalArrangement = Arrangement.spacedBy(spacing),
    ) { content() }
}

/**
 * `L(_:inLanguage:)`: the string in [language] (the language the user speaks, not the phone's),
 * or null when the catalog has no translation into it.
 */
internal fun localized(context: Context, key: String, language: String): String? {
    val base = language.replace('_', '-').substringBefore('-')
    fun inLocale(locale: Locale): String {
        val configuration = Configuration(context.resources.configuration).apply { setLocale(locale) }
        return Strings.get(context.createConfigurationContext(configuration), key)
    }
    val value = inLocale(Locale.forLanguageTag(base))
    if (value == key) return null
    // Android falls back to English silently: an English string for another language is no translation.
    if (base != "en" && value == inLocale(Locale.ENGLISH)) return null
    return value
}
