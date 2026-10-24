package com.friend.ios.design

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Outline
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import kotlin.math.min

/**
 * `RoundedRectangle(cornerRadius:style: .continuous)`: Apple's squircle corner. The curve reaches
 * 1.528665 x radius along each edge (the UIBezierPath control points), so it reads softer than a
 * circular arc of the same radius.
 */
class ContinuousRoundedShape(private val radius: Dp) : Shape {
    override fun createOutline(size: Size, layoutDirection: LayoutDirection, density: Density): Outline {
        val limit = min(size.width, size.height) / 2f / 1.52866483f
        val r = min(with(density) { radius.toPx() }, limit)
        if (r <= 0f) return Outline.Rectangle(size.toRect())
        val w = size.width
        val h = size.height
        val path = Path().apply {
            moveTo(1.52866483f * r, 0f)
            lineTo(w - 1.52866471f * r, 0f)
            corner(this, Offset(w, 0f), r, dx = -1f, dy = 1f, horizontalFirst = true)
            lineTo(w, h - 1.52866471f * r)
            corner(this, Offset(w, h), r, dx = -1f, dy = -1f, horizontalFirst = false)
            lineTo(1.52866483f * r, h)
            corner(this, Offset(0f, h), r, dx = 1f, dy = -1f, horizontalFirst = true)
            lineTo(0f, 1.52866483f * r)
            corner(this, Offset(0f, 0f), r, dx = 1f, dy = 1f, horizontalFirst = false)
            close()
        }
        return Outline.Generic(path)
    }

    /**
     * One corner at [c]. [dx]/[dy] point from the corner into the rect. When [horizontalFirst] the
     * path arrives along a horizontal edge and leaves along a vertical one.
     */
    private fun corner(path: Path, c: Offset, r: Float, dx: Float, dy: Float, horizontalFirst: Boolean) {
        // Control points for a corner entered along x, in units of r (from the corner).
        val pts = arrayOf(
            floatArrayOf(1.08849323f, 0f), floatArrayOf(0.86840689f, 0f), floatArrayOf(0.66993427f, 0.06549600f),
            floatArrayOf(0.63149399f, 0.07491100f),
            floatArrayOf(0.37282392f, 0.16905899f), floatArrayOf(0.16905899f, 0.37282401f), floatArrayOf(0.07491176f, 0.63149399f),
            floatArrayOf(0.06549600f, 0.66993427f),
            floatArrayOf(0f, 0.86840701f), floatArrayOf(0f, 1.08849299f), floatArrayOf(0f, 1.52866483f),
        )
        fun p(i: Int): Offset {
            val (a, b) = pts[i].let { if (horizontalFirst) it[0] to it[1] else it[1] to it[0] }
            return Offset(c.x + dx * a * r, c.y + dy * b * r)
        }
        // Mirroring across the diagonal turns an x-first corner into a y-first one with the same
        // travel order: cubic, line, cubic, line, cubic.
        val seq = pts.indices.map { p(it) }
        path.cubicTo(seq[0].x, seq[0].y, seq[1].x, seq[1].y, seq[2].x, seq[2].y)
        path.lineTo(seq[3].x, seq[3].y)
        path.cubicTo(seq[4].x, seq[4].y, seq[5].x, seq[5].y, seq[6].x, seq[6].y)
        path.lineTo(seq[7].x, seq[7].y)
        path.cubicTo(seq[8].x, seq[8].y, seq[9].x, seq[9].y, seq[10].x, seq[10].y)
    }

    override fun equals(other: Any?) = other is ContinuousRoundedShape && other.radius == radius
    override fun hashCode() = radius.hashCode()
}

private fun Size.toRect() = androidx.compose.ui.geometry.Rect(0f, 0f, width, height)
