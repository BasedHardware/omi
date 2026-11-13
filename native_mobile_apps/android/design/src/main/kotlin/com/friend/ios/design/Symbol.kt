package com.friend.ios.design

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

/**
 * `Image(systemName:)`: an SF Symbol name from the iOS code, drawn with the matching Material
 * Symbols Rounded glyph (map in [SF_SYMBOLS]). [size] is the SF point size (`.font(.system(size:))`)
 * and scales with the font scale like Dynamic Type.
 * [contentDescription] is `.accessibilityLabel`; without one the glyph is hidden from TalkBack
 * (`.accessibilityHidden(true)`), since its private-use codepoint would be read as noise.
 */
@Composable
fun SFImage(
    systemName: String,
    modifier: Modifier = Modifier,
    size: TextUnit = 17.sp,
    weight: FontWeight = FontWeight.Normal,
    tint: Color = LocalContentColor.current,
    contentDescription: String? = null,
) {
    val glyph = SF_SYMBOLS[systemName] ?: SymbolGlyph("help", false)
    val box = with(LocalDensity.current) { (size * SYMBOL_SCALE).toDp() }
    val labelled = if (contentDescription != null) Modifier.semantics { this.contentDescription = contentDescription } else Modifier
    Box(modifier.then(labelled).size(box), contentAlignment = Alignment.Center) {
        Text(
            modifier = Modifier.clearAndSetSemantics {},
            // By codepoint: the bundled font is a subset without ligatures (Tools/icons/subset_font.py).
            text = String(Character.toChars(MATERIAL_CODEPOINTS[glyph.name] ?: MATERIAL_CODEPOINTS.getValue("help"))),
            style = TextStyle(
                fontFamily = symbolFamily(glyph.filled, weight),
                fontSize = size * SYMBOL_SCALE,
                lineHeight = 1.em,
                lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both),
                color = tint,
            ),
            softWrap = false,
            maxLines = 1,
        )
    }
}

/** Material glyphs sit in a 24-unit box with padding; SF glyphs fill their point size more. */
private const val SYMBOL_SCALE = 1.35f

/** SF weight -> Material `wght`: SF strokes are thinner than Material's at the same name. */
private fun symbolWeight(weight: FontWeight): Int = when {
    weight.weight <= 300 -> 200
    weight.weight <= 400 -> 250
    weight.weight <= 500 -> 350
    weight.weight <= 600 -> 450
    else -> 550
}

private val families = HashMap<Pair<Boolean, Int>, FontFamily>()

@OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)
private fun symbolFamily(filled: Boolean, weight: FontWeight): FontFamily {
    val wght = symbolWeight(weight)
    return families.getOrPut(filled to wght) {
        FontFamily(
            Font(
                R.font.material_symbols_rounded,
                variationSettings = FontVariation.Settings(
                    FontVariation.weight(wght),
                    FontVariation.Setting("FILL", if (filled) 1f else 0f),
                    FontVariation.Setting("opsz", 24f),
                ),
            ),
        )
    }
}
