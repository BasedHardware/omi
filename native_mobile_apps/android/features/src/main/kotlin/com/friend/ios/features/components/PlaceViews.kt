package com.friend.ios.features.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ConversationLocation
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.features.conversations.openURL
import java.util.Locale

/**
 * Port of `ConversationPlaceCard` (`PlaceViews.swift`): where a conversation happened: a small map
 * with its pin and the area and city (Flutter `GetGeolocationWidgets`). A tap opens the place in a
 * maps app. The map is OpenStreetMap ([OSMMap]); MapKit has no keyless Android counterpart.
 */
@Composable
fun ConversationPlaceCard(location: ConversationLocation, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    BoxWithConstraints(
        modifier
            .fillMaxWidth()
            .height(140.dp)
            .clip(ContinuousRoundedShape(DS.Radius.card))
            .plainButton { openURL(context, PlaceLinks.maps(location)) },
    ) {
        val zoom = OSMTiles.zoom(800.0, location.latitude, maxWidth)
        OSMMap(location.latitude, location.longitude, zoom, Modifier.matchParentSize()) { project ->
            val point = project(location.latitude, location.longitude)
            // MapKit's Marker: a balloon over the point.
            Box(Modifier.offset(point.x - 14.dp, point.y - 30.dp).size(28.dp).background(DS.Palette.agent, androidx.compose.foundation.shape.CircleShape), contentAlignment = Alignment.Center) {
                SFImage("mappin", size = 13.sp, tint = Color.White)
            }
        }
        Box(Modifier.matchParentSize().background(Brush.verticalGradient(0.5f to Color.Transparent, 1f to Color.Black.copy(alpha = 0.55f))))
        HStack(Modifier.align(Alignment.BottomStart).padding(DS.Spacing.md), spacing = DS.Spacing.xs) {
            SFImage("mappin.and.ellipse", size = 15.sp, tint = Color.White)
            Text(
                location.shortAddress ?: L("unknownLocation"),
                style = DS.Typography.callout.medium(),
                color = Color.White,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

object PlaceLinks {
    /**
     * The place in a maps app. iOS opens Apple Maps (Flutter `MapsUtil.launchMap` prefers it on
     * iOS); the Android equivalent is a `geo:` URI, which any installed maps app handles.
     */
    fun maps(location: ConversationLocation): String {
        val point = String.format(Locale.ROOT, "%f,%f", location.latitude, location.longitude)
        return "geo:$point?q=$point"
    }
}
