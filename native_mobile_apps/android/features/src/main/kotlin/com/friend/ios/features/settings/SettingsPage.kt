package com.friend.ios.features.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.OmiFlatList
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiListBuilder

/**
 * `.omiPage(title)` inside the Settings sheet: the inline navigation bar of a pushed screen (the
 * iOS 26 glass back button, the centered title), the page color, and the screen's list. The shell's
 * `OmiPushedScreen` pads for the status bar; inside the sheet the bar sits at the sheet's top edge.
 */
@Composable
fun SettingsPage(
    title: String?,
    onBack: (() -> Unit)?,
    modifier: Modifier = Modifier,
    leadingSymbol: String = "chevron.left",
    trailing: @Composable RowScope.() -> Unit = {},
    /**
     * The content scrolls on under the bar, as under iOS 26's transparent toolbar (soft edge fade);
     * it must then pad its own top by [SettingsMetrics.navBarHeight].
     */
    scrollsUnderBar: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    if (!scrollsUnderBar) {
        Column(modifier.fillMaxSize().background(DS.Palette.background)) {
            SettingsNavBar(title, onBack, leadingSymbol, trailing)
            content()
        }
        return
    }
    val page = DS.Palette.background
    Box(modifier.fillMaxSize().background(page)) {
        Column(Modifier.fillMaxSize(), content = content)
        Box(
            Modifier.fillMaxWidth().height(SettingsMetrics.navBarHeight).background(
                Brush.verticalGradient(0f to page, 0.55f to page.copy(alpha = 0.85f), 1f to page.copy(alpha = 0f)),
            ),
        ) { SettingsNavBar(title, onBack, leadingSymbol, trailing) }
    }
}

/** A pushed settings screen whose body is one `SettingsList` (`OmiGroupedList`). */
@Composable
fun SettingsListPage(
    title: String?,
    onBack: () -> Unit,
    trailing: @Composable RowScope.() -> Unit = {},
    content: @Composable OmiListBuilder.() -> Unit,
) {
    SettingsPage(title, onBack, trailing = trailing, scrollsUnderBar = true) {
        OmiGroupedList(contentPadding = SettingsMetrics.listPaddingUnderBar, content = content)
    }
}

/** A pushed screen whose body is an `OmiFlatList` (My Omi). */
@Composable
fun SettingsFlatListPage(title: String, onBack: () -> Unit, content: @Composable OmiListBuilder.() -> Unit) {
    SettingsPage(title, onBack, scrollsUnderBar = true) { OmiFlatList(contentPadding = SettingsMetrics.listPaddingUnderBar, content = content) }
}

/** Measured on the simulator: the bar is 76 pt from the sheet's top, the first group 29 pt under it. */
object SettingsMetrics {
    val navBarHeight = 76.dp
    val listPadding = PaddingValues(top = 29.dp, bottom = DS.Spacing.section)
    /** [listPadding] for a list that scrolls on under the bar. */
    val listPaddingUnderBar = PaddingValues(top = navBarHeight + 29.dp, bottom = DS.Spacing.section)
}

/** The inline bar: glass circle buttons on both sides, the 17 pt semibold title in the middle. */
@Composable
fun SettingsNavBar(title: String?, onBack: (() -> Unit)?, leadingSymbol: String = "chevron.left", trailing: @Composable RowScope.() -> Unit = {}) {
    Box(Modifier.fillMaxWidth().height(SettingsMetrics.navBarHeight).padding(horizontal = DS.Spacing.lg)) {
        if (onBack != null) {
            // The system back button reads "Back"; the root's xmark is labeled Close on iOS.
            val label = if (leadingSymbol == "xmark") L("close") else L("back")
            GlassCircleButton(leadingSymbol, Modifier.align(Alignment.CenterStart), contentDescription = label, onClick = onBack)
        }
        if (title != null) {
            Text(
                title,
                style = TextStyles.headline,
                color = DS.Palette.ink,
                textAlign = TextAlign.Center,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.align(Alignment.Center).padding(horizontal = 56.dp),
            )
        }
        Row(Modifier.align(Alignment.CenterEnd), verticalAlignment = Alignment.CenterVertically, content = trailing)
    }
}

/**
 * An iOS 26 toolbar button: a 44 pt glass circle with a hairline edge around one glyph.
 * [contentDescription] is the button's `.accessibilityLabel`.
 */
@Composable
fun GlassCircleButton(systemImage: String, modifier: Modifier = Modifier, contentDescription: String? = null, onClick: () -> Unit) {
    val dark = LocalOmiDark.current
    Box(
        modifier
            .size(44.dp)
            .background(if (dark) hex(0x282828) else hex(0xF5F5F5), CircleShape)
            .border(1.dp, if (dark) hex(0x363636) else hex(0xE4E4E4), CircleShape)
            .plainButton(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        SFImage(systemImage, size = 21.sp, weight = androidx.compose.ui.text.font.FontWeight.Medium, tint = DS.Palette.ink, contentDescription = contentDescription)
    }
}
