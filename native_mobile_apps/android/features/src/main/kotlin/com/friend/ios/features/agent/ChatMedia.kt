package com.friend.ios.features.agent

import android.graphics.BitmapFactory
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ChatChart
import com.friend.ios.core.models.ChatFile
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.SFImage
import com.friend.ios.design.hex
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold

/**
 * Port of `ChartCard` (`ChatMedia.swift`): a chart an answer draws (Flutter `ChartMessageWidget`):
 * line or bar, a legend once there are several series, the backend's colors when it picks them.
 * Swift Charts has no Compose twin; the marks are drawn on a canvas with the same layout.
 */
@Composable
fun ChartCard(chart: ChatChart, modifier: Modifier = Modifier) {
    val fallback = listOf(DS.Palette.agent, DS.Palette.success, DS.Palette.warning, DS.Palette.live, DS.Palette.inkSecondary)
    val colors = chart.series.mapIndexed { index, series -> series.color?.let(::chartColor) ?: fallback[index % fallback.size] }
    val grid = DS.Palette.hairline
    Column(
        modifier
            // One element for TalkBack, named by its title.
            .then(if (chart.title.isNotEmpty()) Modifier.clearAndSetSemantics { contentDescription = chart.title } else Modifier)
            .fillMaxWidth()
            .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.md))
            .padding(DS.Spacing.md),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        if (chart.title.isNotEmpty()) Text(chart.title, style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
        val labels = chart.series.flatMap { s -> s.points.map { it.label } }.distinct()
        val maxValue = chart.series.flatMap { s -> s.points.map { it.value } }.maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
        Canvas(Modifier.fillMaxWidth().height(160.dp)) {
            val top = if (maxValue <= 0.0) 1.0 else maxValue * 1.1
            for (line in 0..4) {
                val y = size.height * line / 4f
                drawLine(grid, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
            }
            if (labels.isEmpty()) return@Canvas
            val slot = size.width / labels.size
            chart.series.forEachIndexed { index, series ->
                val color = colors[index]
                when (chart.kind) {
                    ChatChart.Kind.Bar -> {
                        val barWidth = slot * 0.7f / chart.series.size
                        series.points.forEach { point ->
                            val x = labels.indexOf(point.label) * slot + slot * 0.15f + index * barWidth
                            val h = (point.value / top * size.height).toFloat().coerceAtLeast(0f)
                            drawRect(color, Offset(x, size.height - h), Size(barWidth, h))
                        }
                    }
                    ChatChart.Kind.Line -> {
                        val path = Path()
                        series.points.forEachIndexed { i, point ->
                            val x = labels.indexOf(point.label) * slot + slot / 2
                            val y = size.height - (point.value / top * size.height).toFloat()
                            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                            drawCircle(color, 3.dp.toPx(), Offset(x, y))
                        }
                        drawPath(path, color, style = Stroke(2.dp.toPx()))
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth()) {
            labels.forEach { Text(it, style = DS.Typography.micro, color = DS.Palette.inkTertiary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f)) }
        }
        if (chart.series.size > 1) {
            Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                chart.series.forEachIndexed { index, series ->
                    HStack(spacing = DS.Spacing.xs) {
                        Box(Modifier.size(8.dp).background(colors[index], CircleShape))
                        Text(series.label, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                }
            }
        }
    }
}

/** `#RRGGBB` to a color, nil for anything else. */
fun chartColor(value: String): Color? {
    val digits = value.trim('#')
    if (digits.length != 6) return null
    return digits.toLongOrNull(16)?.let { hex(it) }
}

/**
 * Photos and files sent with a question: photo thumbnails, documents as a named chip. A tap
 * opens the photo large, or the file's page (ask Omi about it again).
 */
@Composable
fun MessageFiles(files: List<ChatFile>, modifier: Modifier = Modifier, onAsk: ((ChatFile) -> Unit)? = null) {
    var previewed by remember { mutableStateOf<ChatFile?>(null) }
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs, Alignment.End)) {
        Spacer(Modifier.size(48.dp, 1.dp))
        for (file in files) {
            val open = Modifier.plainButton { previewed = file }.semantics { contentDescription = file.name }
            if (file.isImage) {
                AttachmentThumbnail(file.localPreview, file.thumbnailURL, open.size(72.dp).clip(ContinuousRoundedShape(DS.Radius.sm)))
            } else {
                DocumentChip(file.name, open)
            }
        }
    }
    previewed?.let { file -> FilePreviewSheet(file, onDismiss = { previewed = null }) { onAsk?.invoke(file) } }
}

/** A photo from the phone's preview, else the backend thumbnail. */
@Composable
fun AttachmentThumbnail(preview: ByteArray?, url: String? = null, modifier: Modifier = Modifier, fit: Boolean = false) {
    val bitmap = remember(preview) { preview?.let { runCatching { BitmapFactory.decodeByteArray(it, 0, it.size) }.getOrNull() } }
    // `.scaledToFit()` (the preview sheet) or `.scaledToFill()` (thumbnails).
    val scale = if (fit) ContentScale.Fit else ContentScale.Crop
    if (bitmap != null) {
        Image(bitmap.asImageBitmap(), contentDescription = null, contentScale = scale, modifier = modifier)
    } else if (url != null) {
        // The backend thumbnail (Coil), the placeholder while it loads or when it fails.
        coil.compose.SubcomposeAsyncImage(
            model = url,
            contentDescription = null,
            contentScale = scale,
            modifier = modifier,
            loading = { ThumbnailPlaceholder() },
            error = { ThumbnailPlaceholder() },
        )
    } else {
        ThumbnailPlaceholder(modifier)
    }
}

@Composable
private fun ThumbnailPlaceholder(modifier: Modifier = Modifier.fillMaxSize()) {
    Box(modifier.background(DS.Palette.fill), contentAlignment = Alignment.Center) {
        SFImage("photo", tint = DS.Palette.inkTertiary)
    }
}

@Composable
fun DocumentChip(name: String, modifier: Modifier = Modifier) {
    HStack(
        modifier
            .widthIn(max = 180.dp)
            .heightIn(min = 36.dp)
            .background(DS.Palette.fill, ContinuousRoundedShape(DS.Radius.sm))
            .padding(horizontal = DS.Spacing.md),
        spacing = DS.Spacing.xs + 2.dp,
    ) {
        SFImage("doc.text", size = 13.sp, tint = DS.Palette.ink)
        Text(name, style = DS.Typography.caption, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.MiddleEllipsis)
    }
}
