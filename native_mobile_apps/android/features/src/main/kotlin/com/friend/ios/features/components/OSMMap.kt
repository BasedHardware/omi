package com.friend.ios.features.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.friend.ios.design.DS
import com.friend.ios.design.TextStyles
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.log2
import kotlin.math.tan

/**
 * The map behind `ConversationMapScreen` and `ConversationPlaceCard`. iOS draws MapKit; Google Maps
 * on Android needs an API key, so this is a static OpenStreetMap raster view (Web Mercator tiles,
 * fitted once, no panning). The attribution is required by the OSM tile usage policy.
 */
object OSMTiles {
    /** Shown at this size (a 256 px tile, upscaled so street names stay readable). */
    val tileSize: Dp = 200.dp
    const val maxZoom = 18
    private const val userAgent = "Omi-Android/1.0 (com.friend.ios; conversation map)"

    /** Tile units (0 ... 2^zoom) of a longitude / latitude. */
    fun x(longitude: Double, zoom: Int): Double = (longitude + 180) / 360 * (1 shl zoom)

    fun y(latitude: Double, zoom: Int): Double {
        val rad = latitude.coerceIn(-85.0511, 85.0511) * PI / 180
        return (1 - ln(tan(rad) + 1 / cos(rad)) / PI) / 2 * (1 shl zoom)
    }

    /** The deepest zoom at which the span fits into [width] x [height]. */
    fun fittingZoom(south: Double, north: Double, west: Double, east: Double, width: Dp, height: Dp): Int {
        for (zoom in maxZoom downTo 1) {
            val w = (x(east, zoom) - x(west, zoom)) * tileSize.value
            val h = (y(south, zoom) - y(north, zoom)) * tileSize.value
            if (w <= width.value && h <= height.value) return zoom
        }
        return 1
    }

    /** The zoom showing about [meters] across [width] at [latitude] (MapKit's `latitudinalMeters`). */
    fun zoom(meters: Double, latitude: Double, width: Dp): Int {
        val metersPerTile = meters / (width.value / tileSize.value)
        val zoom = log2(40_075_016.686 * cos(latitude * PI / 180) / metersPerTile)
        return zoom.toInt().coerceIn(1, maxZoom)
    }

    internal fun request(context: android.content.Context, zoom: Int, x: Int, y: Int) = ImageRequest.Builder(context)
        .data("https://tile.openstreetmap.org/$zoom/$x/$y.png")
        .addHeader("User-Agent", userAgent)
        .crossfade(true)
        .build()
}

/**
 * Tiles around ([latitude], [longitude]) at [zoom], filling the box. [overlay] gets a projection
 * from a coordinate to its offset in the box (for pins).
 */
@Composable
fun OSMMap(
    latitude: Double,
    longitude: Double,
    zoom: Int,
    modifier: Modifier = Modifier,
    overlay: @Composable BoxScope.(project: (Double, Double) -> DpOffset) -> Unit = {},
) {
    val context = LocalContext.current
    BoxWithConstraints(modifier.clipToBounds().background(DS.Palette.card)) {
        val size = OSMTiles.tileSize
        val centerX = OSMTiles.x(longitude, zoom)
        val centerY = OSMTiles.y(latitude, zoom)
        val width = maxWidth
        val height = maxHeight
        // Tile units at the top-left corner.
        val left = centerX - width.value / 2 / size.value
        val top = centerY - height.value / 2 / size.value
        val count = 1 shl zoom
        val firstX = floor(left).toInt()
        val firstY = floor(top).toInt()
        val lastX = floor(left + width.value / size.value).toInt()
        val lastY = floor(top + height.value / size.value).toInt()
        for (tileY in firstY..lastY) {
            if (tileY !in 0 until count) continue
            for (tileX in firstX..lastX) {
                val wrapped = ((tileX % count) + count) % count
                AsyncImage(
                    model = OSMTiles.request(context, zoom, wrapped, tileY),
                    contentDescription = null,
                    contentScale = ContentScale.FillBounds,
                    modifier = Modifier
                        .offset(((tileX - left) * size.value).dp, ((tileY - top) * size.value).dp)
                        .size(size),
                )
            }
        }
        overlay { lat, lon ->
            DpOffset(((OSMTiles.x(lon, zoom) - left) * size.value).dp, ((OSMTiles.y(lat, zoom) - top) * size.value).dp)
        }
        Text(
            "© OpenStreetMap",
            style = TextStyles.system(9),
            color = DS.Palette.inkSecondary,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .background(DS.Palette.background.copy(alpha = 0.7f))
                .padding(horizontal = 4.dp, vertical = 1.dp),
        )
    }
}
