package com.friend.ios.features.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.layout
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.hex
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.stores.KnowledgeGraphStore
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Port of `OmiComponents/KnowledgeGraphView.swift`: the memory graph drawn natively. Lines between
 * linked things, a dot and label per node, the user in the middle. Tap a node to light up what it
 * connects to; drag and pinch to look around ([interactive]).
 */
@Composable
fun KnowledgeGraphView(store: KnowledgeGraphStore, modifier: Modifier = Modifier, interactive: Boolean = true) {
    var selected by remember { mutableStateOf<String?>(null) }
    var zoom by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val haptics = rememberHaptics()
    val ink = DS.Palette.ink
    val agent = DS.Palette.agent
    BoxWithConstraints(modifier.fillMaxSize()) {
        val density = LocalDensity.current
        val width = with(density) { maxWidth.toPx() }
        val height = with(density) { maxHeight.toPx() }
        val reach = min(width, height) / 2 - with(density) { 36.dp.toPx() }
        fun point(node: KnowledgeGraphStore.PlacedNode) = Offset(
            width / 2 + offset.x + node.x.toFloat() * reach * zoom,
            height / 2 + offset.y + node.y.toFloat() * reach * zoom,
        )
        val lit = selected?.let { store.neighbors(it) + it }.orEmpty()
        Canvas(
            Modifier
                .fillMaxSize()
                .then(
                    if (interactive) {
                        Modifier.pointerInput(Unit) {
                            detectTransformGestures { _, pan, gestureZoom, _ ->
                                offset += pan
                                zoom = (zoom * gestureZoom).coerceIn(0.5f, 4f)
                            }
                        }
                    } else Modifier,
                )
                .pointerInput(store.nodes, zoom, offset) {
                    detectTapGestures { location ->
                        val nearest = store.nodes.minByOrNull { (point(it) - location).getDistance() }
                        selected = if (nearest == null || (point(nearest) - location).getDistance() >= 28.dp.toPx()) {
                            null
                        } else {
                            haptics.selection()
                            if (selected == nearest.id) null else nearest.id
                        }
                    }
                },
        ) {
            val points = store.nodes.associate { it.id to point(it) }
            for (edge in store.edges) {
                val from = points[edge.source] ?: continue
                val to = points[edge.target] ?: continue
                val highlighted = edge.source in lit && edge.target in lit
                drawLine(ink.copy(alpha = if (highlighted) 0.5f else if (lit.isEmpty()) 0.14f else 0.05f), from, to, strokeWidth = 1.dp.toPx())
            }
            for (node in store.nodes) {
                val center = points[node.id] ?: Offset.Zero
                val radius = (if (node.isUser) 11 else 6).dp.toPx()
                val dimmed = lit.isNotEmpty() && node.id !in lit
                drawCircle(color(node.node.kind, agent).copy(alpha = if (dimmed) 0.25f else 1f), radius, center)
            }
        }
        store.nodes.forEach { node ->
            val p = point(node)
            val dimmed = lit.isNotEmpty() && node.id !in lit
            Text(
                node.node.label,
                style = if (node.isUser) DS.Typography.callout.semibold() else DS.Typography.micro,
                color = ink.copy(alpha = if (dimmed) 0.3f else 0.9f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .widthIn(max = 124.dp) // 110 pt on iOS; the Android text cut runs about 6 % wider
                    .layout { measurable, constraints ->
                        val placeable = measurable.measure(constraints.copy(minWidth = 0, minHeight = 0))
                        layout(placeable.width, placeable.height) {
                            val dy = (if (node.isUser) 20 else 14).dp.roundToPx()
                            placeable.place(IntOffset((p.x - placeable.width / 2f).roundToInt(), (p.y + dy - placeable.height / 2f).roundToInt()))
                        }
                    },
            )
        }
    }
}

/** `KnowledgeGraphView.color(for:)`: the system colors per kind, Omi blue for the user. */
private fun color(kind: String, agent: Color): Color = when (kind) {
    "user" -> agent
    "person" -> hex(0x32ADE6) // .cyan
    "place" -> hex(0x34C759) // .green
    "organization" -> hex(0xFF9500) // .orange
    "thing" -> hex(0xFFCC00) // .yellow
    else -> hex(0x007AFF) // .blue
}
