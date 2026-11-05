package com.friend.ios.design

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp

/**
 * Port of `Glass.swift`. The iOS app is deliberately solid (glass "read as a gray smudge"), so
 * these are flat card surfaces; Liquid Glass only ever shows through iOS system chrome.
 */

/** `omiCard(padding:)`: standard content card, continuous corners, thin outline. */
@Composable
fun Modifier.omiCard(padding: Dp = DS.Spacing.lg): Modifier = this.fillMaxWidth().omiCardSurface().padding(padding)

/** `omiGroup()`: rows grouped on one card; side padding only, rows bring their own height. */
@Composable
fun Modifier.omiGroup(): Modifier = this.fillMaxWidth().omiCardSurface().padding(horizontal = DS.Spacing.md)

/** `omiCardSurface(radius:)`: just the card fill and outline. */
@Composable
fun Modifier.omiCardSurface(radius: Dp = DS.Radius.card): Modifier {
    val shape = ContinuousRoundedShape(radius)
    return this.background(DS.Palette.card, shape).border(DS.Stroke.regular, DS.Palette.cardStroke, shape)
}
