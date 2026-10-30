package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.style.TextAlign
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.plainButton
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.Announcement
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.TextStyles
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.makeAnnouncementsStore
import kotlinx.coroutines.launch

/**
 * Port of `WhatsNew.swift`. `WhatsNewPresenter` and `AnnouncementSheet` run in the app shell after
 * an update (end of this file); the Settings half is `WhatsNewScreen`.
 */

/** One version's changes: emoji, title and description per row (`ChangesSection`). */
@Composable
fun OmiListBuilder.changesSection(version: String, changes: List<Announcement.Change>, key: Any? = null) {
    section(key = key, footerContent = { com.friend.ios.features.components.OmiSectionFooter(L("versionLabel", version)) }) {
        changes.forEach { change ->
            row(key = change.id) {
                Row(Modifier.padding(vertical = DS.Spacing.xxs), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    Text(change.emoji ?: "✨", style = TextStyles.title3)
                    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text(change.title, style = DS.Typography.cardTitle, color = DS.Palette.ink)
                        Text(change.text, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                }
            }
        }
    }
}

/** Settings > Help > What's new: the latest versions' changes. */
@Composable
fun WhatsNewScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val store = remember { settings.makeAnnouncementsStore() }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { store.loadRecent() }
    val nothingNew = L("nativeNothingNewYet")
    SettingsListPage(L("whatsNew"), onBack) {
        if (store.recentFailed && store.recent.isEmpty()) {
            section {
                plainRow {
                    OmiEmptyState(
                        L("couldNotLoadWhatsNew"), "sparkles", Modifier.padding(top = 72.dp),
                        actionTitle = L("tryAgain"), action = { scope.launch { store.loadRecent() } },
                    )
                }
            }
        } else if (store.recent.isEmpty()) {
            section { row { Text(nothingNew, style = DS.Typography.body, color = DS.Palette.inkSecondary, modifier = Modifier.fillMaxWidth()) } }
        }
        store.recent.forEach { item ->
            val kind = item.kind
            if (kind is Announcement.Kind.Changelog) changesSection(kind.version ?: item.title, kind.changes, key = item.id)
        }
    }
}

// --- What's new after an update (and-onboarding system) ---

/**
 * After an update: the changes since the last version, then pending feature tours and messages,
 * one sheet at a time (Flutter's announcement flow), never while recording. The app shell adds it
 * once, over Home.
 */
@Composable
fun WhatsNewPresenter(appVersion: String) {
    val settings = LocalSettingsStore.current
    val store = remember { settings.makeAnnouncementsStore() }
    val scope = rememberCoroutineScope()
    val uriHandler = androidx.compose.ui.platform.LocalUriHandler.current
    val capture = com.friend.ios.service.LocalCaptureStore.current
    LaunchedEffect(appVersion) { store.checkAfterLaunch(appVersion) }
    // Waits until the recording ends (`capture.isLive ? nil : store?.current`).
    if (capture.isLive) return
    val item = store.current ?: return
    com.friend.ios.design.OmiSheet(
        onDismiss = { if (store.current != null) store.later() },
        detents = setOf(com.friend.ios.design.Detent.Medium, com.friend.ios.design.Detent.Large),
    ) {
        AnnouncementSheet(
            item,
            onDone = { scope.launch { store.dismiss() } },
            onButton = { url ->
                scope.launch { store.dismiss(buttonTapped = true) }
                runCatching { uriHandler.openUri(url) }
            },
            onLater = { store.later() },
        )
    }
}

/** One announcement: a version's changes, a feature tour (one page per step) or a message. */
@Composable
private fun AnnouncementSheet(announcement: Announcement, onDone: () -> Unit, onButton: (String) -> Unit, onLater: () -> Unit) {
    val kind = announcement.kind
    val title = if (kind is Announcement.Kind.Changelog) L("whatsNewInVersion", kind.version ?: announcement.title) else announcement.title
    val notNow = L("notNow")
    val gotIt = L("gotIt")
    Column(Modifier.fillMaxWidth()) {
        Box(Modifier.fillMaxWidth().padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.md)) {
            if (kind is Announcement.Kind.Message) {
                Text(notNow, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onLater))
            }
            Text(title, style = TextStyles.headline, color = DS.Palette.ink, maxLines = 1, modifier = Modifier.align(Alignment.Center).padding(horizontal = 72.dp))
            Text(gotIt, style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterEnd).plainButton(onClick = onDone))
        }
        when (kind) {
            is Announcement.Kind.Changelog -> com.friend.ios.features.components.OmiGroupedList {
                changesSection(kind.version ?: announcement.title, kind.changes)
            }
            is Announcement.Kind.Feature -> {
                val pager = rememberPagerState { kind.steps.size }
                HorizontalPager(pager, Modifier.fillMaxWidth()) { page ->
                    val step = kind.steps[page]
                    Column(
                        Modifier.fillMaxWidth().padding(DS.Spacing.xl),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
                    ) {
                        step.imageURL?.let { url -> AnnouncementImage(url, maxHeight = 220.dp) }
                        Text(step.title, style = DS.Typography.title, color = DS.Palette.ink, textAlign = TextAlign.Center)
                        Text(step.text, style = DS.Typography.callout, color = DS.Palette.inkSecondary, textAlign = TextAlign.Center)
                    }
                }
            }
            is Announcement.Kind.Message -> Column(
                Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(DS.Spacing.xl),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
            ) {
                kind.imageURL?.let { url -> AnnouncementImage(url, maxHeight = 180.dp) }
                Text(kind.body, style = DS.Typography.body, color = DS.Palette.ink)
                val buttonTitle = kind.buttonTitle
                val buttonURL = kind.buttonURL
                if (buttonTitle != null && buttonURL != null) OmiPrimaryButton(buttonTitle) { onButton(buttonURL) }
            }
        }
    }
}

/** `AsyncImage(url:) { $0.resizable().scaledToFit() }.frame(maxHeight:)`: the whole picture, at most [maxHeight] tall. */
@Composable
private fun AnnouncementImage(url: String, maxHeight: androidx.compose.ui.unit.Dp) {
    com.friend.ios.features.conversations.RemoteImage(
        load = { com.friend.ios.features.conversations.ScreenshotsStrip.load(url) },
        modifier = Modifier.fillMaxWidth().height(maxHeight),
        fits = true,
    )
}
