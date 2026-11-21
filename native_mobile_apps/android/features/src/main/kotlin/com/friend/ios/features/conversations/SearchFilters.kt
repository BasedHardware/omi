package com.friend.ios.features.conversations

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.today.GraphicalCalendar
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.SearchStore
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Port of `SearchFilterMenu` (`SearchFilters.swift`): the search's filter menu: starred, one
 * person, a date range (Flutter's starred and people tiles and date filter). The iOS "People"
 * submenu is a section here (the popup menu has no nested menus).
 */
@Composable
fun SearchFilterMenu(search: SearchStore, onPickDates: () -> Unit) {
    val settings = LocalSettingsStore.current
    val filter = search.filter
    val people = settings.people
    val sections = buildList {
        add(
            MenuSection(
                items = listOf(
                    MenuItem(L("starred"), if (filter.starred) "checkmark" else "star") { search.filter = search.filter.copy(starred = !filter.starred) },
                ),
            ),
        )
        if (people.isNotEmpty()) {
            add(
                MenuSection(
                    header = L("people"),
                    items = people.map { person ->
                        MenuItem(person.name, if (filter.person?.id == person.id) "checkmark" else null) {
                            search.filter = search.filter.copy(person = if (search.filter.person?.id == person.id) null else person)
                        }
                    },
                ),
            )
        }
        add(
            MenuSection(
                header = L("filterByDate"),
                items = listOf(
                    MenuItem(L("today")) { setDays(search, 1) },
                    MenuItem(L("nativeLast7Days")) { setDays(search, 7) },
                    MenuItem(L("nativeLast30Days")) { setDays(search, 30) },
                    MenuItem(L("nativeChooseDates"), "calendar", action = onPickDates),
                ),
            ),
        )
        if (filter.isActive) {
            add(MenuSection(items = listOf(MenuItem(L("nativeClearFilters"), "xmark", destructive = true) { search.filter = SearchStore.Filter() })))
        }
    }
    val label = L("filters")
    OmiMenu(sections) {
        Box(Modifier.size(DS.Size.headerButton).semantics { contentDescription = label }, contentAlignment = Alignment.Center) {
            SFImage(
                if (filter.isActive) "line.3.horizontal.decrease.circle.fill" else "line.3.horizontal.decrease.circle",
                size = 21.sp,
                tint = DS.Palette.ink,
            )
        }
    }
}

/** Today counts from midnight; longer ranges end now. */
private fun setDays(search: SearchStore, days: Int, zone: ZoneId = ZoneId.systemDefault()) {
    val today = LocalDate.now(zone)
    search.filter = search.filter.copy(start = today.minusDays((days - 1).toLong()).atStartOfDay(zone).toInstant(), end = null)
}

/** Port of `FilterChip`: a removable filter capsule above the results. */
@Composable
fun FilterChip(title: String, symbol: String, onRemove: () -> Unit) {
    val label = L("nativeRemoveFilter", title)
    HStack(
        Modifier
            .plainButton(onClick = onRemove)
            .heightIn(min = 32.dp)
            .background(DS.Palette.accent, CircleShape)
            .padding(horizontal = DS.Spacing.md)
            .semantics { contentDescription = label },
        spacing = DS.Spacing.xs,
    ) {
        SFImage(symbol, size = 13.sp, tint = DS.Palette.onAccent)
        Text(title, style = TextStyles.footnote.semibold(), color = DS.Palette.onAccent, maxLines = 1)
        SFImage("xmark", size = 9.sp, weight = FontWeight.Bold, tint = DS.Palette.onAccent)
    }
}

/** Port of `DateRangeSheet`: pick a from-to range of days. The compact date pickers open a calendar inline. */
@Composable
fun DateRangeSheet(search: SearchStore, onDismiss: () -> Unit, zone: ZoneId = ZoneId.systemDefault()) {
    val today = LocalDate.now(zone)
    var start by remember { mutableStateOf(search.filter.start?.atZone(zone)?.toLocalDate() ?: today.minusDays(7)) }
    var end by remember { mutableStateOf(search.filter.end?.atZone(zone)?.toLocalDate() ?: today) }
    /** Which row's calendar is open: 0 from, 1 to. */
    var editing by remember { mutableStateOf<Int?>(null) }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(
            L("filterByDate"),
            leading = { SheetBarButton(L("cancel"), onClick = onDismiss) },
            trailing = {
                SheetBarButton(L("nativeApply"), prominent = true) {
                    search.filter = search.filter.copy(
                        start = start.atStartOfDay(zone).toInstant(),
                        end = end.plusDays(1).atStartOfDay(zone).toInstant().minusSeconds(1),
                    )
                    onDismiss()
                }
            },
        )
        val from = L("nativeFrom")
        val to = L("nativeTo")
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            section {
                row(key = "from", onClick = { editing = if (editing == 0) null else 0 }) {
                    Text(from, style = DS.Typography.body, color = DS.Palette.ink)
                    Spacer(Modifier.weight(1f))
                    DateCapsule(start, editing == 0)
                }
                if (editing == 0) {
                    plainRow(key = "from.calendar") {
                        GraphicalCalendar(start, Modifier.weight(1f).padding(vertical = DS.Spacing.sm), latest = end) { start = it }
                    }
                }
                row(key = "to", onClick = { editing = if (editing == 1) null else 1 }) {
                    Text(to, style = DS.Typography.body, color = DS.Palette.ink)
                    Spacer(Modifier.weight(1f))
                    DateCapsule(end, editing == 1)
                }
                if (editing == 1) {
                    plainRow(key = "to.calendar") {
                        GraphicalCalendar(end, Modifier.weight(1f).padding(vertical = DS.Spacing.sm), earliest = start, latest = today) { end = it }
                    }
                }
            }
        }
    }
}

/** The compact `DatePicker`'s value: the date in a gray capsule, tinted while its calendar is open. */
@Composable
private fun DateCapsule(date: LocalDate, active: Boolean) {
    Text(
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).format(date),
        style = DS.Typography.body,
        color = if (active) DS.Palette.agent else DS.Palette.ink,
        modifier = Modifier.background(DS.Palette.fill, CircleShape).padding(horizontal = DS.Spacing.md, vertical = 6.dp),
    )
}

/** `DateRangeSheet.title(_:)`. */
object DateRangeSheet {
    /** "Oct 1, 2026 – Oct 7, 2026", "Since Oct 1, 2026", or null without a range. */
    @Composable
    fun title(filter: SearchStore.Filter, zone: ZoneId = ZoneId.systemDefault()): String? {
        fun format(date: Instant) = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).format(date.atZone(zone))
        val start = filter.start
        val end = filter.end
        return when {
            start != null && end != null -> "${format(start)} – ${format(end)}"
            start != null -> L("nativeSinceDate", format(start))
            end != null -> L("nativeUntilDate", format(end))
            else -> null
        }
    }
}
