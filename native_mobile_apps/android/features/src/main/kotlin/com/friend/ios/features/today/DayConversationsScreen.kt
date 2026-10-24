package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.SkeletonBlock
import com.friend.ios.design.TextStyles
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.semibold
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.ConversationRowStyle
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarButton
import com.friend.ios.core.models.Conversation
import com.friend.ios.service.stores.DayConversationsStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle as JavaTextStyle
import java.time.temporal.WeekFields
import java.util.Locale

/**
 * Port of `DayConversationsScreen` (`ConversationListExtras.swift`): one day's conversations
 * (Flutter `day_conversations_page`): the previous and next day, a calendar to jump, pull to
 * refresh, "show more". Shown full screen (`.fullScreenCover`).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DayConversationsScreen(
    store: DayConversationsStore,
    picking: Boolean,
    onOpenConversation: (Conversation) -> Unit,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    /** Opens on the calendar, so the day is picked first. */
    var pickingDay by remember { mutableStateOf(picking) }
    var refreshing by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { if (store.conversations.isEmpty()) store.load() }

    fun open(conversation: Conversation) {
        onDismiss()
        onOpenConversation(conversation)
    }

    FullScreenCover(onDismiss) {
        SheetBar(
            Formatting.dayTitle(store.day),
            leading = { SheetBarButton(L("done"), onClick = onDismiss) },
            trailing = {
                ToolbarGroup {
                    ToolbarGlyph("chevron.left", L("previousDay")) { scope.launch { store.go(-1L) } }
                    ToolbarGlyph("chevron.right", L("nextDay"), enabled = store.canGoForward()) { scope.launch { store.go(1L) } }
                    ToolbarGlyph("calendar", L("filterByDate")) { pickingDay = true }
                }
            },
        )
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = {
                scope.launch {
                    refreshing = true
                    store.load()
                    refreshing = false
                }
            },
            modifier = Modifier.weight(1f),
        ) {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = DS.Spacing.gutter, end = DS.Spacing.gutter, bottom = DS.Spacing.section),
                verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
            ) {
                when (store.phase) {
                    DayConversationsStore.Phase.Loading -> items(4) { SkeletonBlock(height = 68.dp) }
                    DayConversationsStore.Phase.Failed -> item(key = "failed") {
                        Column(
                            Modifier.fillMaxWidth().padding(top = 80.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
                        ) {
                            Text(L("somethingWentWrong"), style = DS.Typography.cardTitle, color = DS.Palette.ink)
                            OmiPillButton(L("tryAgain"), prominent = false) { scope.launch { store.load() } }
                        }
                    }
                    DayConversationsStore.Phase.Loaded -> {
                        if (store.conversations.isEmpty()) {
                            item(key = "empty") {
                                Text(
                                    L("noConversationsOnDate", Formatting.dayTitle(store.day)),
                                    style = DS.Typography.callout,
                                    color = DS.Palette.inkSecondary,
                                    textAlign = TextAlign.Center,
                                    modifier = Modifier.fillMaxWidth().padding(top = 80.dp),
                                )
                            }
                        }
                        items(store.conversations, key = { it.id }) { conversation ->
                            Box {
                                ConversationRow(
                                    conversation,
                                    Modifier.pressable { open(conversation) },
                                    style = ConversationRowStyle.Plain,
                                )
                                if (conversation.isLocked) LockedRowCover(Modifier.matchParentSize())
                            }
                        }
                        if (store.hasMore) {
                            item(key = "more") {
                                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                                    if (store.isLoadingMore) {
                                        OmiProgress()
                                    } else {
                                        HStack(
                                            Modifier
                                                .plainButton { scope.launch { store.loadMore() } }
                                                .background(DS.Palette.cardRaised, CircleShape)
                                                .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
                                            spacing = DS.Spacing.xs,
                                        ) {
                                            SFImage("chevron.down", size = 13.sp, tint = DS.Palette.ink)
                                            Text(L("showMore"), style = TextStyles.subheadline.semibold(), color = DS.Palette.ink)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if (pickingDay) {
        DayPickerSheet(store.day, onDismiss = { pickingDay = false }) { day -> scope.launch { store.show(day) } }
    }
}

/** `DayConversationsScreen.requestForDebugging`. */
object DayConversationsScreen {
    /**
     * `--es omiOpenDay YES` (the calendar first) or `--es omiOpenDay 2026-10-04` opens this page once
     * Home has settled (scripted screenshots; debug builds only, the extras are empty otherwise).
     */
    suspend fun requestForDebugging(): DayRequest? {
        val value = DebugLaunch.string("omiOpenDay") ?: return null
        delay(1_500)
        val day = runCatching { LocalDate.parse(value) }.getOrNull()
        return if (day != null) DayRequest(day, picksDay = false) else DayRequest(LocalDate.now(), picksDay = true)
    }
}

/** An iOS 26 `ToolbarItemGroup`: several glyphs in one glass capsule. */
@Composable
private fun ToolbarGroup(content: @Composable () -> Unit) {
    val dark = LocalOmiDark.current
    Row(
        Modifier
            .height(44.dp)
            .background(if (dark) hex(0x282828) else hex(0xF5F5F5), CircleShape)
            .border(1.dp, if (dark) hex(0x363636) else hex(0xE4E4E4), CircleShape)
            .padding(horizontal = DS.Spacing.xs),
        verticalAlignment = Alignment.CenterVertically,
    ) { content() }
}

@Composable
private fun ToolbarGlyph(systemImage: String, label: String, enabled: Boolean = true, onClick: () -> Unit) {
    Box(
        Modifier.size(40.dp).plainButton(enabled = enabled, onClick = onClick).semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        SFImage(systemImage, size = 17.sp, weight = FontWeight.Medium, tint = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
    }
}

/**
 * Port of `DayPickerSheet` (`ConversationListExtras.swift`): "Go to a day": a calendar to pick one
 * day (never after today), drawn like iOS's `.graphical` date picker.
 */
@Composable
fun DayPickerSheet(day: LocalDate, onDismiss: () -> Unit, onPick: (LocalDate) -> Unit) {
    var selected by remember { mutableStateOf(day) }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(
            L("filterByDate"),
            leading = { SheetBarButton(L("cancel"), onClick = onDismiss) },
            trailing = {
                SheetBarButton(L("nativeShowDay"), prominent = true) {
                    onDismiss()
                    onPick(selected)
                }
            },
        )
        GraphicalCalendar(selected, Modifier.padding(horizontal = DS.Spacing.gutter), latest = LocalDate.now()) { selected = it }
        Spacer(Modifier.height(DS.Spacing.xl))
    }
}

/**
 * `DatePicker(...).datePickerStyle(.graphical)`: "October 2026 >" with the month arrows on the
 * right, the weekday letters, then the days; the chosen day on a soft tint circle, today in the
 * tint, days after [latest] gray.
 */
@Composable
fun GraphicalCalendar(selected: LocalDate, modifier: Modifier = Modifier, latest: LocalDate? = null, earliest: LocalDate? = null, onSelect: (LocalDate) -> Unit) {
    var month by remember { mutableStateOf(YearMonth.from(selected)) }
    val locale = Locale.getDefault()
    val firstDay: DayOfWeek = WeekFields.of(locale).firstDayOfWeek
    val today = LocalDate.now()
    val tint = DS.Palette.agent
    Column(modifier.fillMaxWidth()) {
        HStack(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.sm)) {
            Text(
                month.format(DateTimeFormatter.ofPattern("LLLL yyyy", locale)),
                style = TextStyles.headline,
                color = DS.Palette.ink,
            )
            SFImage("chevron.right", size = 14.sp, weight = FontWeight.SemiBold, tint = tint)
            Spacer(Modifier.weight(1f))
            val canGoBack = earliest == null || month > YearMonth.from(earliest)
            val canGoForward = latest == null || month < YearMonth.from(latest)
            Box(Modifier.size(40.dp).plainButton(enabled = canGoBack) { month = month.minusMonths(1) }, contentAlignment = Alignment.Center) {
                // Named by the month it goes to (no "previous month" string in the catalog).
                SFImage(
                    "chevron.left", size = 20.sp, weight = FontWeight.Medium, tint = if (canGoBack) tint else DS.Palette.inkDisabled,
                    contentDescription = month.minusMonths(1).format(DateTimeFormatter.ofPattern("LLLL yyyy", locale)),
                )
            }
            Box(Modifier.size(40.dp).plainButton(enabled = canGoForward) { month = month.plusMonths(1) }, contentAlignment = Alignment.Center) {
                SFImage(
                    "chevron.right", size = 20.sp, weight = FontWeight.Medium, tint = if (canGoForward) tint else DS.Palette.inkDisabled,
                    contentDescription = month.plusMonths(1).format(DateTimeFormatter.ofPattern("LLLL yyyy", locale)),
                )
            }
        }
        Row(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs)) {
            (0 until 7).forEach { offset ->
                val weekday = firstDay.plus(offset.toLong())
                Text(
                    weekday.getDisplayName(JavaTextStyle.SHORT, locale).uppercase(locale).trimEnd('.'),
                    style = TextStyles.footnote.semibold(),
                    color = DS.Palette.inkTertiary,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.weight(1f),
                )
            }
        }
        val first = month.atDay(1)
        val lead = (first.dayOfWeek.value - firstDay.value + 7) % 7
        val cells = lead + month.lengthOfMonth()
        val rows = (cells + 6) / 7
        (0 until rows).forEach { rowIndex ->
            Row(Modifier.fillMaxWidth()) {
                (0 until 7).forEach { column ->
                    val index = rowIndex * 7 + column - lead
                    Box(Modifier.weight(1f).aspectRatio(1f), contentAlignment = Alignment.Center) {
                        if (index in 0 until month.lengthOfMonth()) {
                            val date = month.atDay(index + 1)
                            val enabled = (latest == null || date <= latest) && (earliest == null || date >= earliest)
                            val isSelected = date == selected
                            val isToday = date == today
                            val fill = when {
                                isSelected && isToday -> tint
                                isSelected -> tint.copy(alpha = 0.12f)
                                else -> androidx.compose.ui.graphics.Color.Transparent
                            }
                            val color = when {
                                isSelected && isToday -> androidx.compose.ui.graphics.Color.White
                                isSelected || isToday -> tint
                                !enabled -> DS.Palette.inkDisabled
                                else -> DS.Palette.ink
                            }
                            Box(
                                Modifier
                                    .size(44.dp)
                                    .background(fill, CircleShape)
                                    .plainButton(enabled = enabled) { onSelect(date) },
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    "${date.dayOfMonth}",
                                    style = TextStyles.system(20, if (isSelected || isToday) FontWeight.SemiBold else FontWeight.Normal),
                                    color = color,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
