package com.friend.ios.design

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** `OmiPrimaryButtonStyle`: full width, ink capsule, background-colored label. */
@Composable
fun OmiPrimaryButton(title: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Box(
        modifier
            .fillMaxWidth()
            .heightIn(min = DS.Size.primaryButtonHeight)
            .pressable(enabled = enabled, pressedScale = 0.98f, pressedAlpha = 0.85f, onClick = onClick)
            .background(if (enabled) DS.Palette.accent else DS.Palette.fill, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(title, style = DS.Typography.button, color = if (enabled) DS.Palette.onAccent else DS.Palette.inkDisabled)
    }
}

/** `OmiSecondaryButtonStyle`: secondary action on a card surface. */
@Composable
fun OmiSecondaryButton(title: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier
            .fillMaxWidth()
            .heightIn(min = DS.Size.primaryButtonHeight)
            .pressable(pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onClick)
            .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.md)),
        contentAlignment = Alignment.Center,
    ) {
        Text(title, style = DS.Typography.button, color = DS.Palette.ink)
    }
}

/** `OmiPillButtonStyle`: small pill action ("Allow", "Connect", "Get"); `omiPillSubtle` when not prominent. */
@Composable
fun OmiPillButton(title: String, modifier: Modifier = Modifier, prominent: Boolean = true, onClick: () -> Unit) {
    Box(
        modifier
            .pressable(pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onClick)
            .background(if (prominent) DS.Palette.accent else DS.Palette.cardRaised, CircleShape)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
    ) {
        Text(title, style = TextStyles.subheadline.semibold(), color = if (prominent) DS.Palette.onAccent else DS.Palette.ink)
    }
}

/** `CircleIconButton`: the round header buttons (search, settings, back, share). */
@Composable
fun CircleIconButton(systemImage: String, modifier: Modifier = Modifier, contentDescription: String? = null, onClick: () -> Unit) {
    OmiCircleIcon(systemImage, modifier.plainButton(onClick = onClick), contentDescription)
}

/** `OmiCircleIcon`: a plain line glyph in a 40 pt hit area, as in the ChatGPT app: no circle behind it. */
@Composable
fun OmiCircleIcon(systemImage: String, modifier: Modifier = Modifier, contentDescription: String? = null) {
    Box(modifier.size(DS.Size.headerButton), contentAlignment = Alignment.Center) {
        SFImage(systemImage, size = 19.sp, tint = DS.Palette.ink, contentDescription = contentDescription)
    }
}

/** `OmiSearchField`: the search capsule at the top of Tasks and Memories. [clearLabel] is the clear button's accessibility label. */
@Composable
fun OmiSearchField(prompt: String, text: String, onTextChange: (String) -> Unit, clearLabel: String, modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = DS.Size.searchField)
            .omiSurface(CircleShape)
            .padding(horizontal = DS.Spacing.lg),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        SFImage("magnifyingglass", size = 15.sp, tint = DS.Palette.inkTertiary)
        Box(Modifier.weight(1f)) {
            if (text.isEmpty()) Text(prompt, style = DS.Typography.callout, color = DS.Palette.inkTertiary, maxLines = 1)
            BasicTextField(
                value = text,
                onValueChange = onTextChange,
                singleLine = true,
                textStyle = DS.Typography.callout.copy(color = DS.Palette.ink),
                cursorBrush = SolidColor(DS.Palette.agent),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (text.isNotEmpty()) {
            SFImage("xmark.circle.fill", size = 15.sp, tint = DS.Palette.inkTertiary, modifier = Modifier.plainButton { onTextChange("") }, contentDescription = clearLabel)
        }
    }
}

/** `OmiEmptyState`: a soft round icon, a title, a line of help, an optional action. */
@Composable
fun OmiEmptyState(
    title: String,
    systemImage: String,
    modifier: Modifier = Modifier,
    message: String? = null,
    actionTitle: String? = null,
    action: (() -> Unit)? = null,
) {
    Box(modifier.fillMaxWidth().padding(horizontal = DS.Spacing.xl), contentAlignment = Alignment.Center) {
        Column(
            Modifier.widthIn(max = 320.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        ) {
            Box(
                Modifier.padding(bottom = DS.Spacing.xs).size(60.dp).background(DS.Palette.agentSoft, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                SFImage(systemImage, size = 24.sp, weight = androidx.compose.ui.text.font.FontWeight.SemiBold, tint = DS.Palette.agent)
            }
            Text(title, style = DS.Typography.sectionTitle, color = DS.Palette.ink, textAlign = TextAlign.Center)
            if (message != null) {
                Text(message, style = DS.Typography.callout, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
            }
            if (actionTitle != null && action != null) {
                OmiPillButton(actionTitle, Modifier.padding(top = DS.Spacing.xs), prominent = false, onClick = action)
            }
        }
    }
}

/** `omiField()`: Omi's input field, a card-colored rounded box with a hairline border. */
@Composable
fun Modifier.omiField(): Modifier = this
    .heightIn(min = 56.dp)
    .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.md))
    .border(1.dp, DS.Palette.hairline, ContinuousRoundedShape(DS.Radius.md))
    .padding(horizontal = DS.Spacing.lg)

/** `omiSurface(_:)`: the quiet card color edged by a hairline. Solid on purpose. */
@Composable
fun Modifier.omiSurface(shape: Shape): Modifier = this
    .background(DS.Palette.card, shape)
    .border(DS.Stroke.regular, DS.Palette.cardStroke, shape)

/** `CalmBackground`: the page color with at most a breath of light at the top. */
@Composable
fun CalmBackground(modifier: Modifier = Modifier) {
    val glow = Color.White.copy(alpha = if (LocalOmiDark.current) 0.035f else 0.45f)
    val page = DS.Palette.background
    Box(
        modifier.fillMaxSize().drawBehind {
            drawRect(page)
            val radius = 420.dp.toPx()
            val height = 460.dp.toPx()
            drawRect(
                Brush.radialGradient(listOf(glow, Color.Transparent), center = Offset(size.width / 2, 0f), radius = radius),
                size = androidx.compose.ui.geometry.Size(size.width, height),
            )
        },
    )
}

/** `HStack(spacing:)` with centered children, the most common row in the iOS code. */
@Composable
fun HStack(
    modifier: Modifier = Modifier,
    spacing: androidx.compose.ui.unit.Dp = DS.Spacing.sm,
    alignment: Alignment.Vertical = Alignment.CenterVertically,
    content: @Composable RowScope.() -> Unit,
) = Row(modifier, horizontalArrangement = Arrangement.spacedBy(spacing), verticalAlignment = alignment, content = content)
