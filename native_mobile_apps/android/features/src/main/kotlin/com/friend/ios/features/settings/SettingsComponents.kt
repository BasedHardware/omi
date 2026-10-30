package com.friend.ios.features.settings

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles

/**
 * Port of `SettingsComponents.swift`. The glyph in front of a settings row: one quiet symbol in a
 * fixed-width column, no tile and no per-row colors, so the list reads calm and the titles line up.
 */
@Composable
fun SettingsIcon(systemImage: String, modifier: Modifier = Modifier, tint: Color = DS.Palette.inkSecondary) {
    Box(modifier.width(28.dp), contentAlignment = Alignment.Center) { SFImage(systemImage, size = 17.sp, tint = tint) }
}

/** One settings row: icon, title, and an optional short value on the right (the current choice). */
@Composable
fun SettingsRowLabel(
    title: String,
    systemImage: String,
    modifier: Modifier = Modifier,
    value: String? = null,
    tint: Color = DS.Palette.inkSecondary,
    titleColor: Color = DS.Palette.ink,
) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        SettingsIcon(systemImage, tint = tint)
        Text(title, style = DS.Typography.body, color = titleColor, modifier = if (value == null) Modifier.weight(1f) else Modifier)
        if (value != null) {
            Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
            Text(value, style = DS.Typography.body, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** `LabeledContent(title) { value }`: the title left, the value right in secondary ink. */
@Composable
fun SettingsLabeledContent(title: String, value: String, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = DS.Typography.body, color = DS.Palette.ink)
        Spacer(Modifier.weight(1f).width(DS.Spacing.md))
        Text(value, style = DS.Typography.body, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** The trailing "opens elsewhere" arrow of a `Link` row. */
@Composable
fun SettingsExternalArrow() {
    SFImage("arrow.up.right", size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
}

/**
 * A round monogram from a name ("Alice Moore" -> "AM"): the profile header, people, apps without
 * an icon. A hairline ring, no fill.
 */
@Composable
fun Monogram(name: String, modifier: Modifier = Modifier, size: Dp = 56.dp) {
    Box(modifier.size(size).border(1.dp, DS.Palette.hairline, CircleShape), contentAlignment = Alignment.Center) {
        Text(initials(name), style = if (size >= 44.dp) DS.Typography.sectionTitle else DS.Typography.micro, color = DS.Palette.ink)
    }
}

/** `Monogram.initials`. */
fun initials(name: String): String {
    val words = name.split(' ', '@', '.').filter { it.isNotEmpty() }.take(2)
    return words.map { it.first().uppercase() }.joinToString("").ifEmpty { "?" }
}

/**
 * The calm hero on top of a few screens (referral, phone calls locked, connect your AI): one thin
 * line glyph, one title line, one short line under it.
 */
@Composable
fun SettingsHero(systemImage: String, title: String, message: String, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().padding(vertical = DS.Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
    ) {
        Box(Modifier.height(44.dp), contentAlignment = Alignment.Center) {
            SFImage(systemImage, size = 34.sp, weight = FontWeight.Light, tint = DS.Palette.inkSecondary)
        }
        Text(title, style = DS.Typography.title, color = DS.Palette.ink, textAlign = TextAlign.Center)
        Text(message, style = DS.Typography.callout, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
    }
}

/** The row text of a plain `Button(title)` in a list (Sign out, Delete account). */
@Composable
fun SettingsButtonText(title: String, color: Color = DS.Palette.ink) {
    Text(title, style = DS.Typography.body, color = color)
}

/** A secondary line under a row title (captions in rows). */
@Composable
fun SettingsCaption(text: String, color: Color = DS.Palette.inkSecondary) {
    Text(text, style = TextStyles.footnote, color = color)
}
