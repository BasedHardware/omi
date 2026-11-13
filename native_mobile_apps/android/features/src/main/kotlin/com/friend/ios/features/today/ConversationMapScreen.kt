package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationPlace
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.bold
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.ConversationRowStyle
import com.friend.ios.features.components.OSMMap
import com.friend.ios.features.components.OSMTiles
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.features.conversations.SheetBarIcon

/**
 * Port of `ConversationMapScreen.swift`: the loaded conversations by place (Flutter
 * `conversation_map_page`): one pin per place (~100 m), a single conversation opens directly, a
 * place with several lists them first. The map is OpenStreetMap ([OSMMap]): Google Maps needs an
 * API key, MapKit has no Android counterpart.
 */
@Composable
fun ConversationMapScreen(conversations: List<Conversation>, onOpenConversation: (Conversation) -> Unit, onDismiss: () -> Unit) {
    val places = remember(conversations) { ConversationPlace.group(conversations) }
    var selected by remember { mutableStateOf<ConversationPlace?>(null) }
    val haptics = rememberHaptics()
    FullScreenCover(onDismiss) {
        SheetBar(L("conversationMap"), leading = { SheetBarIcon("xmark", onClick = onDismiss) })
        if (places.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                OmiEmptyState(if (conversations.isEmpty()) L("noConversationsYet") else L("unknownLocation"), "map")
            }
        } else {
            BoxWithConstraints(Modifier.fillMaxSize()) {
                val (center, zoom) = position(places, maxWidth.value, maxHeight.value)
                OSMMap(center.first, center.second, zoom, Modifier.fillMaxSize()) { project ->
                    places.forEach { place ->
                        val point = project(place.location.latitude, place.location.longitude)
                        Pin(place, Modifier.offset(point.x - 17.dp, point.y - 17.dp)) {
                            haptics.selection()
                            val only = place.conversations.firstOrNull()
                            if (only != null && place.conversations.size == 1) onOpenConversation(only) else selected = place
                        }
                    }
                }
            }
        }
    }
    selected?.let { place -> PlaceSheet(place, onDismiss = { selected = null }) { conversation ->
        selected = null
        onOpenConversation(conversation)
    } }
}

@Composable
private fun Pin(place: ConversationPlace, modifier: Modifier, onTap: () -> Unit) {
    val label = title(place)
    Box(
        modifier
            .size(34.dp)
            .background(DS.Palette.agent, CircleShape)
            .border(2.dp, DS.Palette.card, CircleShape)
            .plainButton(onClick = onTap)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        if (place.conversations.size == 1) {
            SFImage("mappin", size = 15.sp, weight = FontWeight.Bold, tint = DS.Palette.onAccent)
        } else {
            Text("${place.conversations.size}", style = DS.Typography.callout.bold().copy(fontFeatureSettings = "tnum"), color = DS.Palette.onAccent)
        }
    }
}

/**
 * Every place in view; one place (or places close together) at neighborhood scale, not the
 * street-level zoom a single pin would get. Returns the center and the tile zoom.
 */
private fun position(places: List<ConversationPlace>, width: Float, height: Float): Pair<Pair<Double, Double>, Int> {
    val latitudes = places.map { it.location.latitude }
    val longitudes = places.map { it.location.longitude }
    val south = latitudes.min()
    val north = latitudes.max()
    val west = longitudes.min()
    val east = longitudes.max()
    val center = (south + north) / 2 to (west + east) / 2
    val latSpan = maxOf(0.02, (north - south) * 1.5)
    val lonSpan = maxOf(0.02, (east - west) * 1.5)
    val zoom = OSMTiles.fittingZoom(
        center.first - latSpan / 2, center.first + latSpan / 2, center.second - lonSpan / 2, center.second + lonSpan / 2,
        width.dp, height.dp,
    )
    return center to zoom
}

/** A single conversation's title, else "<n> conversations". */
@Composable
private fun title(place: ConversationPlace): String {
    val only = place.conversations.firstOrNull()
    if (place.conversations.size != 1 || only == null) return L("nativeConversationsCount", "${place.conversations.size}")
    return only.title.ifEmpty { L("untitledConversation") }
}

@Composable
private fun PlaceSheet(place: ConversationPlace, onDismiss: () -> Unit, onOpen: (Conversation) -> Unit) {
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(place.location.shortAddress ?: title(place))
        LazyColumn(Modifier.fillMaxWidth()) {
            items(place.conversations.sortedByDescending { it.date }, key = { it.id }) { conversation ->
                ConversationRow(
                    conversation,
                    Modifier
                        .plainButton { onOpen(conversation) }
                        .padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.sm),
                    style = ConversationRowStyle.Plain,
                )
            }
        }
    }
}

/** `.fullScreenCover`: a page over everything, on the page color, dismissed by Back. */
@Composable
internal fun FullScreenCover(onDismiss: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(
            Modifier
                .fillMaxSize()
                .background(DS.Palette.background)
                .statusBarsPadding()
                .navigationBarsPadding(),
            content = content,
        )
    }
}
