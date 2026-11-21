package com.friend.ios.features.settings

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.AppQuery
import com.friend.ios.core.models.OmiApp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalAppCatalogStore
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.stores.AppCatalogStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URL
import java.text.NumberFormat

/**
 * Port of `AppsBrowserScreen.swift`. The app store: kinds as chips, search, category and sort in
 * the filter menu; tap an app for its page. Loading, nothing found and failure each have their own
 * state (failure offers Try again).
 */
@Composable
fun AppsBrowserScreen(onBack: () -> Unit) {
    val catalog = LocalAppCatalogStore.current
    val scope = rememberCoroutineScope()
    var text by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { catalog.loadCategories() }
    val query = catalog.query
    LaunchedEffect(text, query.category, query.capability, query.sort) {
        if (text.isNotEmpty()) delay(300)
        catalog.query = catalog.query.copy(text = text)
        catalog.search()
    }
    val isFiltered = text.isNotEmpty() || query.category != null || query.capability != null
    SettingsPage(L("nativeBrowseApps"), onBack, trailing = { FilterMenu(catalog) }) {
        // `.searchable(placement: .navigationBarDrawer(displayMode: .always))`.
        OmiSearchField(L("nativeSearchApps"), text, { text = it }, L("nativeClearSearch"), Modifier.padding(horizontal = DS.Spacing.lg).padding(bottom = DS.Spacing.sm))
        Box(Modifier.weight(1f)) {
            SettingsListBody {
                section { plainRow { KindChips(query.capability) { catalog.query = catalog.query.copy(capability = it) } } }
                if (catalog.results.isNotEmpty()) {
                    section {
                        catalog.results.forEach { app ->
                            row(key = app.id, separatorInset = 76.dp) {
                                AppRow(app)
                                if (app.id == catalog.results.lastOrNull()?.id) LaunchedEffect(app.id) { catalog.loadMore() }
                            }
                        }
                        if (catalog.isLoading) row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
                    }
                }
            }
            if (catalog.results.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    when {
                        catalog.isLoading -> OmiProgress(Modifier.size(32.dp))
                        catalog.searchFailed -> OmiEmptyState(
                            L("nativeSettingsAppsFailed"), "wifi.exclamationmark", message = L("nativeSettingsAppsFailedBody"),
                            actionTitle = L("tryAgain"), action = { scope.launch { catalog.search() } },
                        )
                        else -> OmiEmptyState(
                            L("nativeNoApps"), "square.grid.2x2",
                            message = if (isFiltered) L("nativeSettingsAppsNoMatch") else null,
                            actionTitle = if (isFiltered) L("nativeSettingsClearFilters") else null,
                            action = if (isFiltered) {
                                {
                                    text = ""
                                    catalog.query = catalog.query.copy(category = null, capability = null)
                                }
                            } else null,
                        )
                    }
                }
            }
        }
    }
}

/** `OmiGroupedList` with the settings page's padding, under a header of the screen's own. */
@Composable
private fun SettingsListBody(content: @Composable com.friend.ios.features.components.OmiListBuilder.() -> Unit) {
    com.friend.ios.features.components.OmiGroupedList(contentPadding = androidx.compose.foundation.layout.PaddingValues(top = DS.Spacing.sm, bottom = DS.Spacing.section), content = content)
}

@Composable
private fun FilterMenu(catalog: AppCatalogStore) {
    val query = catalog.query
    val sorts = listOf(AppQuery.Sort.Installs to L("nativeAppsSortPopular"), AppQuery.Sort.Rating to L("nativeAppsSortRating"), AppQuery.Sort.Name to L("nativeAppsSortName"))
    val categories = listOf<Pair<String?, String>>(null to L("nativeAppsAllCategories")) + catalog.categories.map { it.id to it.title }
    OmiMenu(
        listOf(
            MenuSection(L("nativeAppsSort"), sorts.map { (sort, title) -> MenuItem(title, if (query.sort == sort) "checkmark" else null) { catalog.query = catalog.query.copy(sort = sort) } }),
            MenuSection(L("nativeAppsCategory"), categories.map { (id, title) -> MenuItem(title, if (query.category == id) "checkmark" else null) { catalog.query = catalog.query.copy(category = id) } }),
        ),
        contentDescription = L("nativeAppsFilter"),
    ) {
        Box(Modifier.size(44.dp).background(DS.Palette.card, CircleShape), contentAlignment = Alignment.Center) {
            SFImage(if (query.category != null) "line.3.horizontal.decrease.circle.fill" else "line.3.horizontal.decrease", size = 19.sp, tint = DS.Palette.ink)
        }
    }
}

@Composable
fun appKindTitle(capability: String): String = when (capability) {
    "chat" -> L("nativeAppsKindChat")
    "memories" -> L("nativeAppsKindSummaries")
    "external_integration" -> L("nativeAppsKindIntegrations")
    "proactive_notification" -> L("nativeAppsKindNotifications")
    "tasks" -> L("nativeAppsKindTasks")
    else -> capability
}

/** All, Chat, Summaries ... as one scrolling row of chips. */
@Composable
private fun KindChips(selection: String?, onSelect: (String?) -> Unit) {
    val haptics = rememberHaptics()
    Row(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = DS.Spacing.xs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        (listOf<String?>(null) + AppCatalogStore.capabilityKinds).forEach { value ->
            val selected = selection == value
            Text(
                if (value == null) L("nativeAppsAllKinds") else appKindTitle(value),
                style = DS.Typography.callout.medium(),
                color = if (selected) DS.Palette.onAccent else DS.Palette.ink,
                modifier = Modifier
                    .plainButton {
                        haptics.selection()
                        onSelect(value)
                    }
                    .semantics { this.selected = selected }
                    .background(if (selected) DS.Palette.accent else androidx.compose.ui.graphics.Color.Transparent, CircleShape)
                    .border(1.dp, if (selected) androidx.compose.ui.graphics.Color.Transparent else DS.Palette.hairline, CircleShape)
                    .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.sm),
            )
        }
    }
}

/** One app in a list: icon, name, one line of what it does, rating; Get or Remove on the right. */
@Composable
fun AppRow(app: OmiApp) {
    val store = LocalCapabilitiesStore.current
    val navigator = LocalSettingsNavigator.current
    val scope = rememberCoroutineScope()
    Row(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xxs), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        Row(
            Modifier.weight(1f).plainButton { navigator.push(SettingsRoute.App(app.id)) },
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        ) {
            AppIcon(app.imageURL, app.name, 48.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                Text(app.name, style = DS.Typography.cardTitle, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(app.description, style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                val rating = app.rating
                if (rating != null && app.ratingCount > 0) {
                    val average = NumberFormat.getNumberInstance().apply { minimumFractionDigits = 1; maximumFractionDigits = 1 }.format(rating)
                    Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xxs), verticalAlignment = Alignment.CenterVertically) {
                        SFImage("star.fill", size = 11.sp, tint = DS.Palette.inkTertiary)
                        Text("$average (${app.ratingCount})", style = DS.Typography.micro, color = DS.Palette.inkTertiary)
                    }
                }
            }
        }
        if (!app.isPaid || app.isEnabled) {
            OmiPillButton(if (app.isEnabled) L("nativeRemove") else L("nativeGet"), prominent = !app.isEnabled) {
                scope.launch { store.setApp(app, !app.isEnabled) }
            }
        }
    }
}

/** An app's icon, or its initials while the image loads or when there is none. */
@Composable
fun AppIcon(url: String?, name: String, size: Dp) {
    val shape = ContinuousRoundedShape(size * 0.24f)
    val bitmap by produceState<Bitmap?>(RemoteImages.cached(url), url) { value = RemoteImages.load(url) }
    Box(Modifier.size(size).clip(shape).border(1.dp, DS.Palette.hairline, shape), contentAlignment = Alignment.Center) {
        val image = bitmap
        if (image != null) {
            Image(image.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        } else {
            Text(initials(name), style = if (size >= 44.dp) DS.Typography.sectionTitle else DS.Typography.callout, color = DS.Palette.ink)
        }
    }
}

/**
 * `AsyncImage` for small remote icons: one plain download, decoded off the main thread and kept
 * in a small memory cache, so a scrolled list does not fetch every icon again. Not the shared
 * `RemoteImage` (`ConversationMedia.kt`): that one shows a photo glyph on a tile while loading,
 * where an app icon shows its initials, as on iOS.
 */
internal object RemoteImages {
    private val cache = LruCache<String, Bitmap>(64)

    fun cached(url: String?): Bitmap? = url?.let { cache.get(it) }

    suspend fun load(url: String?): Bitmap? {
        if (url.isNullOrEmpty() || !url.startsWith("http")) return null
        cache.get(url)?.let { return it }
        return withContext(Dispatchers.IO) {
            runCatching { URL(url).openStream().use { BitmapFactory.decodeStream(it) } }.getOrNull()
        }?.also { cache.put(url, it) }
    }
}
