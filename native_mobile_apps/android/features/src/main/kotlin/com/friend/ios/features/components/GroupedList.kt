package com.friend.ios.features.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.calculateEndPadding
import androidx.compose.foundation.layout.calculateStartPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.ScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.NonRestartableComposable
import androidx.compose.runtime.RecomposeScope
import androidx.compose.runtime.currentRecomposeScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles

/**
 * Port of `OmiComponents/GroupedList.swift`. SwiftUI's `List` with `Section`s becomes a builder:
 * `OmiGroupedList { section(header = ...) { row { ... } } }`. The builder runs during composition,
 * so plain `if`s and state reads inside it work like a `@ViewBuilder`.
 *
 * Geometry of the iOS 26 `.insetGrouped` list (measured on the simulator): groups 16 pt from the
 * screen edge, 26 pt continuous corners, rows at least 50 pt with 16 pt insets, hairlines from the
 * row's title to 16 pt short of the trailing edge.
 */
object OmiListMetrics {
    val margin: Dp = 16.dp
    val rowInset: Dp = 16.dp
    val minRowHeight: Dp = 50.dp
    val rowVerticalPadding: Dp = 11.dp
    val cornerRadius: Dp = 26.dp
    /** A row with a leading glyph: the hairline starts at the title (16 + 28 + 12). */
    val iconSeparatorInset: Dp = 56.dp
    /** A section label sits 10 pt further from the group above than the plain section spacing. */
    val headerTopPadding: Dp = 10.dp
    val headerBottomPadding: Dp = 10.dp
    /** How much of the list's top margin a first-section label takes up. */
    val firstHeaderLift: Dp = 23.dp
}

/** One row of a section. */
class OmiListRow internal constructor(
    val key: Any?,
    val plain: Boolean,
    val plainInset: Dp,
    val separatorInset: Dp,
    val showsChevron: Boolean,
    val onClick: (() -> Unit)?,
    val enabled: Boolean,
    val content: @Composable RowScope.() -> Unit,
)

/** A `Section { } header: { } footer: { }`. */
class OmiListSection internal constructor(
    val key: Any?,
    val header: (@Composable () -> Unit)?,
    val footer: (@Composable () -> Unit)?,
    val rows: List<OmiListRow>,
)

/**
 * The rows of one section. The builders run inside composition (like a `@ViewBuilder`), so they
 * may read state and call `L(...)`; the rows they collect render right after.
 */
class OmiSectionBuilder internal constructor(private val list: OmiListBuilder) {
    internal val rows = mutableListOf<OmiListRow>()

    /**
     * A row on the group's card. [onClick] makes it a button (the system highlight while pressed);
     * [chevron] adds the `NavigationLink` disclosure chevron. [separatorInset] is where the hairline
     * under it starts (16 for a text row, [OmiListMetrics.iconSeparatorInset] behind a glyph).
     */
    fun row(
        key: Any? = null,
        onClick: (() -> Unit)? = null,
        chevron: Boolean = false,
        enabled: Boolean = true,
        separatorInset: Dp = OmiListMetrics.rowInset,
        content: @Composable RowScope.() -> Unit,
    ) {
        list.touched()
        rows += OmiListRow(key, false, 0.dp, separatorInset, chevron, onClick, enabled, content)
    }

    /**
     * `omiPlainRow(inset:)`: a row that sits on the page instead of a group (a hero, a big button,
     * the page title): no card behind it, no hairline. `inset` 0 lines it up with the groups' edges.
     */
    fun plainRow(key: Any? = null, inset: Dp = 0.dp, content: @Composable RowScope.() -> Unit) {
        list.touched()
        rows += OmiListRow(key, true, inset, 0.dp, false, null, true, content)
    }
}

/** The sections of a list. */
class OmiListBuilder internal constructor(private val scope: RecomposeScope) {
    internal val sections = mutableListOf<OmiListSection>()

    /** True while [OmiList] runs the builder; rows added outside that pass come from a restarted inner scope. */
    internal var inPass = false

    /**
     * Builder lambdas and `@Composable` builder extensions are restartable: when a state they read
     * changes, Compose re-runs only that scope, which would add rows to this old builder and never
     * re-render the list. Any call outside the list's own pass therefore invalidates the whole list,
     * which then rebuilds from scratch.
     */
    internal fun touched() {
        if (!inPass) scope.invalidate()
    }

    @Composable
    @NonRestartableComposable
    fun section(
        header: String? = null,
        footer: String? = null,
        key: Any? = null,
        headerContent: (@Composable () -> Unit)? = null,
        footerContent: (@Composable () -> Unit)? = null,
        rows: @Composable OmiSectionBuilder.() -> Unit,
    ) {
        touched()
        val builder = OmiSectionBuilder(this)
        builder.rows()
        val head: (@Composable () -> Unit)? = headerContent ?: header?.let { { OmiSectionLabel(it) } }
        val foot: (@Composable () -> Unit)? = footerContent ?: footer?.let { { OmiSectionFooter(it) } }
        sections += OmiListSection(key, head, foot, builder.rows)
    }
}

/**
 * A list of rounded groups on the plain page, as in the ChatGPT app's settings: each section is
 * one raised card (`DS.Palette.card`) with hairlines between its rows; quiet gray section labels.
 */
@Composable
fun OmiGroupedList(
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = OmiListDefaults.contentPadding,
    scrollState: ScrollState = rememberScrollState(),
    content: @Composable OmiListBuilder.() -> Unit,
) = OmiList(modifier, contentPadding, scrollState, cardColor = DS.Palette.card, sectionSpacing = DS.Spacing.xl, content)

/**
 * A flat list as in the ChatGPT app's settings root: rows sit directly on the page (no card behind
 * them), divided by hairlines that start at the title, with quiet gray section labels.
 */
@Composable
fun OmiFlatList(
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = OmiListDefaults.contentPadding,
    scrollState: ScrollState = rememberScrollState(),
    content: @Composable OmiListBuilder.() -> Unit,
) = OmiList(modifier, contentPadding, scrollState, cardColor = Color.Transparent, sectionSpacing = DS.Spacing.lg, content)

object OmiListDefaults {
    /** The first group sits this far under the navigation bar (iOS: 35 pt under the 52 pt bar). */
    val contentPadding = PaddingValues(top = 35.dp, bottom = DS.Spacing.section)
}

@Composable
private fun OmiList(
    modifier: Modifier,
    contentPadding: PaddingValues,
    scrollState: ScrollState,
    cardColor: Color,
    sectionSpacing: Dp,
    content: @Composable OmiListBuilder.() -> Unit,
) {
    val builder = OmiListBuilder(currentRecomposeScope)
    builder.inPass = true
    builder.content()
    builder.inPass = false
    val sections = builder.sections
    val direction = LocalLayoutDirection.current
    Column(
        modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(
                start = OmiListMetrics.margin + contentPadding.calculateStartPadding(direction),
                end = OmiListMetrics.margin + contentPadding.calculateEndPadding(direction),
                // A header on the first section takes the place of part of the top margin (iOS).
                top = if (sections.firstOrNull()?.header != null) (contentPadding.calculateTopPadding() - OmiListMetrics.firstHeaderLift).coerceAtLeast(0.dp) else contentPadding.calculateTopPadding(),
                bottom = contentPadding.calculateBottomPadding(),
            )
            .navigationBarsPadding(),
    ) {
        sections.forEachIndexed { index, section ->
            if (index > 0) Spacer(Modifier.height(sectionSpacing))
            SectionView(section, cardColor, isFirst = index == 0)
        }
    }
}

@Composable
private fun SectionView(section: OmiListSection, cardColor: Color, isFirst: Boolean) {
    Column(Modifier.fillMaxWidth()) {
        section.header?.let {
            val top = if (isFirst) 0.dp else OmiListMetrics.headerTopPadding
            Box(Modifier.padding(start = OmiListMetrics.rowInset, end = OmiListMetrics.rowInset, top = top, bottom = OmiListMetrics.headerBottomPadding)) { it() }
        }
        // Consecutive card rows share one rounded card; plain rows sit between them on the page.
        val groups = mutableListOf<MutableList<OmiListRow>>()
        section.rows.forEach { row ->
            if (row.plain || groups.isEmpty() || groups.last().first().plain) groups += mutableListOf(row) else groups.last() += row
        }
        groups.forEach { group ->
            if (group.first().plain) {
                group.forEach { row ->
                    Row(Modifier.fillMaxWidth().padding(horizontal = row.plainInset), verticalAlignment = Alignment.CenterVertically, content = row.content)
                }
            } else {
                val shape = ContinuousRoundedShape(OmiListMetrics.cornerRadius)
                Column(Modifier.fillMaxWidth().clip(shape).background(cardColor, shape)) {
                    group.forEachIndexed { i, row -> CardRow(row, showsSeparator = i < group.lastIndex) }
                }
            }
        }
        section.footer?.let {
            Box(Modifier.padding(start = OmiListMetrics.rowInset, end = OmiListMetrics.rowInset, top = DS.Spacing.sm)) { it() }
        }
    }
}

@Composable
private fun CardRow(row: OmiListRow, showsSeparator: Boolean) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val highlight = DS.Palette.fill
    val hairline = DS.Palette.hairline
    val clickable = row.onClick?.let { onClick ->
        Modifier.clickable(interactionSource = source, indication = null, enabled = row.enabled, onClick = onClick)
    } ?: Modifier
    Row(
        Modifier
            .fillMaxWidth()
            .then(clickable)
            .background(if (pressed) highlight else Color.Transparent)
            .drawBehind {
                if (showsSeparator) {
                    val y = size.height - 0.5.dp.toPx()
                    drawLine(hairline, Offset(row.separatorInset.toPx(), y), Offset(size.width - OmiListMetrics.rowInset.toPx(), y), strokeWidth = 1.dp.toPx())
                }
            }
            .heightIn(min = OmiListMetrics.minRowHeight)
            .padding(horizontal = OmiListMetrics.rowInset, vertical = OmiListMetrics.rowVerticalPadding),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, content = row.content)
        if (row.showsChevron) {
            Spacer(Modifier.width(DS.Spacing.sm))
            OmiDisclosureChevron()
        }
    }
}

/** The `NavigationLink` chevron: small, semibold, tertiary. */
@Composable
fun OmiDisclosureChevron(modifier: Modifier = Modifier) {
    SFImage("chevron.right", modifier, size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary)
}

/** A section label over a group: small, gray, sentence case (as "For you" on Home). */
@Composable
fun OmiSectionLabel(title: String, modifier: Modifier = Modifier) {
    Text(title, style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary, modifier = modifier.semantics { heading() })
}

/** A section footer: the explanation under a group, once (`Section { } footer: { Text(...) }`). */
@Composable
fun OmiSectionFooter(text: String, modifier: Modifier = Modifier) {
    Text(text, style = TextStyles.footnote, color = DS.Palette.inkSecondary, modifier = modifier)
}

/** `omiRowGlyph()`: a row's leading glyph in a grouped list, thin, monochrome, in a fixed 28 pt column. */
@Composable
fun OmiRowGlyph(systemImage: String, modifier: Modifier = Modifier, tint: Color = DS.Palette.inkSecondary) {
    Box(modifier.width(28.dp), contentAlignment = Alignment.Center) { SFImage(systemImage, size = 17.sp, tint = tint) }
}
