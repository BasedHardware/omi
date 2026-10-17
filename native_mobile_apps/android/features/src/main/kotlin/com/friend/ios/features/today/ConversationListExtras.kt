package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold
import com.friend.ios.features.components.rememberOpenUpgrade
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationsStore
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * Port of `LockedRowCover` (`ConversationListExtras.swift`): a locked conversation's row (behind
 * the paywall): frosted, with "Upgrade to Unlimited" (Flutter `OmiLockedPreview`). Tapping
 * anywhere opens the plans (`openUpgrade`).
 */
@Composable
fun LockedRowCover(modifier: Modifier = Modifier) {
    val openUpgrade = rememberOpenUpgrade()
    Box(
        modifier
            .background(DS.Palette.background.copy(alpha = 0.85f), ContinuousRoundedShape(DS.Radius.card))
            .plainButton(onClick = openUpgrade),
        contentAlignment = Alignment.Center,
    ) {
        HStack(
            Modifier.omiSurface(androidx.compose.foundation.shape.CircleShape).padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.sm),
            spacing = DS.Spacing.xs,
        ) {
            SFImage("lock", size = 15.sp, tint = DS.Palette.ink)
            Text(L("upgradeToUnlimited"), style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
        }
    }
}

/**
 * Port of `DisplayOptionsMenu`: Home's filter menu section: discarded conversations on or off,
 * and how short a conversation may be. The iOS submenu for the threshold is a second section here
 * (the popup menu has no nested menus).
 */
@Composable
fun displayOptionsMenu(): List<MenuSection> {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val display = conversations.display
    fun choice(title: String, selected: Boolean, action: () -> Unit) = MenuItem(title, if (selected) "checkmark" else null, action = action)
    return listOf(
        MenuSection(
            header = L("conversationDisplay"),
            items = listOf(
                MenuItem(L("showDiscardedConversations"), if (display.showsDiscarded) "checkmark" else "trash.slash") {
                    scope.launch { conversations.setShowsDiscarded(!display.showsDiscarded) }
                },
            ),
        ),
        MenuSection(
            header = L("shortConversationThreshold"),
            items = listOf(choice(L("showShortConversations"), display.hidesShorterThan == null) { conversations.hideShorter(null) }) +
                ConversationsStore.shortThresholds.map { seconds ->
                    choice(L("nativeHideUnderMinutes", "${seconds / 60}"), display.hidesShorterThan == seconds) { conversations.hideShorter(seconds) }
                },
        ),
    )
}

/** The day the one-day page opens at; [picksDay] opens its calendar first. */
data class DayRequest(val day: LocalDate, val picksDay: Boolean) {
    val id: LocalDate get() = day
}

// DayPickerSheet and DayConversationsScreen are in DayConversationsScreen.kt.
