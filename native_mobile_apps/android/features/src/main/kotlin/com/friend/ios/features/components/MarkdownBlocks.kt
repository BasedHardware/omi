package com.friend.ios.features.components

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold

/**
 * Port of `MarkdownBlocks.swift`: agent answers as Omi shows them. SwiftUI's `Text` renders
 * inline Markdown only, so the block level is done here: headings, bulleted and numbered items,
 * quotes, code and tables. A quote is how the agent hands over a draft, so it gets its own card
 * with a copy button.
 *
 * [style]: the text size (a chat bubble is a little smaller than body). [color]: the ink
 * (`.foregroundStyle`). Selection is off everywhere here (a bubble's long press opens its menu,
 * Copy is in it).
 */
@Composable
fun MarkdownBlocks(text: String, modifier: Modifier = Modifier, style: TextStyle = DS.Typography.body, color: Color = DS.Palette.ink) {
    val blocks = remember(text) { MarkdownBlocks.parse(text) }
    val link = DS.Palette.agent
    val secondary = DS.Palette.inkSecondary
    Column(modifier, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        for (block in blocks) {
            when (block) {
                is MarkdownBlocks.Block.Heading ->
                    Text(inline(block.text, link), style = style.semibold(), color = color, modifier = Modifier.padding(top = DS.Spacing.xs))
                is MarkdownBlocks.Block.Bullet -> Row(Modifier.padding(start = DS.Spacing.lg * block.level), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    // A fixed marker column: wrapped lines hang under the first line's text.
                    Text("•", style = style, color = secondary, modifier = Modifier.width(DS.Spacing.md))
                    Text(inline(block.text, link), style = style, color = color)
                }
                is MarkdownBlocks.Block.Numbered -> Row(Modifier.padding(start = DS.Spacing.lg * block.level), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    Text(
                        block.number + ".", style = style.copy(fontFeatureSettings = "tnum"), color = secondary,
                        modifier = Modifier.widthIn(min = DS.Spacing.lg + DS.Spacing.xs),
                    )
                    Text(inline(block.text, link), style = style, color = color)
                }
                is MarkdownBlocks.Block.Code -> Box(
                    Modifier
                        .fillMaxWidth()
                        .background(DS.Palette.fill, ContinuousRoundedShape(DS.Radius.sm))
                        .horizontalScroll(rememberScrollState())
                        .padding(DS.Spacing.md),
                ) {
                    Text(block.text, style = TextStyles.footnote.copy(fontFamily = FontFamily.Monospace, textGeometricTransform = null), color = DS.Palette.ink, softWrap = false)
                }
                is MarkdownBlocks.Block.Table -> TableBlock(block.rows, link)
                is MarkdownBlocks.Block.Quote -> DraftCard(block.text, link)
                is MarkdownBlocks.Block.Paragraph -> Text(inline(block.text, link), style = style, color = color)
            }
        }
    }
}

object MarkdownBlocks {
    sealed interface Block {
        data class Heading(val text: String) : Block
        data class Bullet(val text: String, val level: Int) : Block
        data class Numbered(val text: String, val number: String, val level: Int) : Block
        data class Quote(val text: String) : Block
        data class Code(val text: String) : Block
        data class Table(val rows: List<List<String>>) : Block
        data class Paragraph(val text: String) : Block
    }

    fun parse(text: String): List<Block> {
        val parser = Parser()
        text.split("\n").forEach(parser::feed)
        return parser.finish()
    }

    private val bulletLine = Regex("""[*\-•+–◦]\s+(.+)""")
    private val numberedLine = Regex("""(\d{1,3})[.)]\s+(.+)""")

    /** Line by line: fenced code and tables first (they keep their lines as written), then text. */
    class Parser {
        val blocks = mutableListOf<Block>()
        private val quote = mutableListOf<String>()
        private val paragraph = mutableListOf<String>()
        private var code: MutableList<String>? = null
        private val table = mutableListOf<List<String>>()

        fun feed(raw: String) {
            val line = raw.trim(' ', '\t')
            val open = code
            when {
                line.startsWith("```") -> if (open != null) {
                    blocks.add(Block.Code(open.joinToString("\n")))
                    code = null
                } else {
                    flush()
                    code = mutableListOf()
                }
                open != null -> open.add(raw)
                line.startsWith("|") -> {
                    if (table.isEmpty()) flush()
                    tableRow(line)?.let { table.add(it) }
                }
                else -> {
                    if (table.isNotEmpty()) flush()
                    text(line, raw.takeWhile { it == ' ' }.length)
                }
            }
        }

        private fun text(line: String, indent: Int) {
            if (line.startsWith(">")) {
                if (paragraph.isNotEmpty()) {
                    blocks.add(Block.Paragraph(paragraph.joinToString("\n")))
                    paragraph.clear()
                }
                quote.add(line.drop(1).trim(' ', '\t'))
                return
            }
            if (line.isEmpty()) return flush()
            val bullet = bulletLine.matchEntire(line)
            val numbered = numberedLine.matchEntire(line)
            when {
                line.startsWith("#") -> {
                    flush()
                    blocks.add(Block.Heading(line.dropWhile { it == '#' }.trim(' ', '\t')))
                }
                // Any marker and any space after it ("-\t", "•  "), else the line reads as a
                // paragraph whose wrapped lines start under the bullet.
                bullet != null -> {
                    flush()
                    blocks.add(Block.Bullet(bullet.groupValues[1], indent / 2))
                }
                numbered != null -> {
                    flush()
                    blocks.add(Block.Numbered(numbered.groupValues[2], numbered.groupValues[1], indent / 3))
                }
                else -> {
                    if (quote.isNotEmpty()) flush()
                    paragraph.add(line)
                }
            }
        }

        fun flush() {
            if (quote.isNotEmpty()) blocks.add(Block.Quote(quote.joinToString("\n")))
            if (paragraph.isNotEmpty()) blocks.add(Block.Paragraph(paragraph.joinToString("\n")))
            if (table.isNotEmpty()) blocks.add(Block.Table(table.toList()))
            quote.clear()
            paragraph.clear()
            table.clear()
        }

        /** An unclosed fence still shows its code (an answer cut short). */
        fun finish(): List<Block> {
            code?.let { blocks.add(Block.Code(it.joinToString("\n"))) }
            code = null
            flush()
            return blocks
        }

        companion object {
            /** The cells of a `| a | b |` row; null for the `|---|:--:|` divider under the header. */
            fun tableRow(line: String): List<String>? {
                val cells = line.split("|").map { it.trim(' ', '\t') }.toMutableList()
                if (cells.firstOrNull()?.isEmpty() == true) cells.removeAt(0)
                if (cells.lastOrNull()?.isEmpty() == true) cells.removeAt(cells.size - 1)
                val divider = cells.all { cell -> cell.isNotEmpty() && cell.all { it == ':' || it == '-' } }
                return if (divider || cells.isEmpty()) null else cells
            }
        }
    }
}

/**
 * SwiftUI's inline Markdown (`Text(LocalizedStringKey(text))`): **bold**, *italic*, `code`,
 * ~~strikethrough~~ and [links](url); whitespace and line breaks are kept.
 */
fun inline(text: String, link: Color): AnnotatedString = buildAnnotatedString { appendInline(text, link) }

private fun AnnotatedString.Builder.appendInline(text: String, link: Color) {
    var i = 0
    val plain = StringBuilder()
    fun flushPlain() {
        if (plain.isNotEmpty()) append(plain.toString())
        plain.clear()
    }
    while (i < text.length) {
        val c = text[i]
        if (c == '\\' && i + 1 < text.length && text[i + 1] in "\\`*_~[]()#") {
            plain.append(text[i + 1])
            i += 2
            continue
        }
        if (c == '`') {
            val end = text.indexOf('`', i + 1)
            if (end > i) {
                flushPlain()
                withStyle(SpanStyle(fontFamily = FontFamily.Monospace)) { append(text.substring(i + 1, end)) }
                i = end + 1
                continue
            }
        }
        if (c == '[') {
            val close = text.indexOf("](", i + 1)
            val end = if (close > i) text.indexOf(')', close + 2) else -1
            if (close > i && end > close && !text.substring(i + 1, close).contains('\n')) {
                flushPlain()
                val url = text.substring(close + 2, end).trim()
                withLink(LinkAnnotation.Url(url, TextLinkStyles(SpanStyle(color = link)))) { appendInline(text.substring(i + 1, close), link) }
                i = end + 1
                continue
            }
        }
        val marker = when {
            text.startsWith("**", i) -> "**"
            text.startsWith("__", i) -> "__"
            text.startsWith("~~", i) -> "~~"
            c == '*' || c == '_' -> c.toString()
            else -> null
        }
        if (marker != null) {
            val end = text.indexOf(marker, i + marker.length)
            val inner = if (end > i + marker.length) text.substring(i + marker.length, end) else null
            // A delimiter run opens only before a non-space and closes only after one (`2 * 3 * 4` stays as typed),
            // and `_` inside a word (snake_case) is not emphasis.
            val wordUnderscore = marker.startsWith("_") && i > 0 && text[i - 1].isLetterOrDigit()
            if (inner != null && !inner.first().isWhitespace() && !inner.last().isWhitespace() && !wordUnderscore) {
                flushPlain()
                val style = when (marker) {
                    "**", "__" -> SpanStyle(fontWeight = FontWeight.SemiBold)
                    "~~" -> SpanStyle(textDecoration = TextDecoration.LineThrough)
                    else -> SpanStyle(fontStyle = FontStyle.Italic)
                }
                withStyle(style) { appendInline(inner, link) }
                i = end + marker.length
                continue
            }
        }
        plain.append(c)
        i++
    }
    flushPlain()
}

/** A Markdown table: the first row bold, columns as wide as their content, sideways scrolling. */
@Composable
private fun TableBlock(rows: List<List<String>>, link: Color) {
    val columns = rows.maxOfOrNull { it.size } ?: 0
    val hairline = DS.Palette.hairline
    Box(
        Modifier
            .background(DS.Palette.fill.copy(alpha = DS.Palette.fill.alpha * 0.5f), ContinuousRoundedShape(DS.Radius.sm))
            .horizontalScroll(rememberScrollState())
            .padding(DS.Spacing.md),
    ) {
        Row {
            for (column in 0 until columns) {
                val last = column == columns - 1
                Column(Modifier.padding(end = if (last) 0.dp else DS.Spacing.md), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    rows.forEachIndexed { index, row ->
                        Text(
                            inline(row.getOrElse(column) { "" }, link),
                            style = if (index == 0) DS.Typography.callout.semibold() else DS.Typography.callout,
                            color = DS.Palette.ink,
                            softWrap = false,
                        )
                        if (index == 0) {
                            Box(
                                Modifier.height(1.dp).fillMaxWidth().drawBehind {
                                    // The header divider runs on through the column gap.
                                    val gap = if (last) 0f else DS.Spacing.md.toPx()
                                    drawRect(hairline, size = Size(size.width + gap, size.height))
                                },
                            )
                        }
                    }
                }
            }
        }
    }
}

/** A draft Omi prepared for the user to send themselves. */
@Composable
private fun DraftCard(text: String, link: Color) {
    var copied by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val agent = DS.Palette.agent
    Column(
        Modifier
            .fillMaxWidth()
            .background(DS.Palette.agentSoft, ContinuousRoundedShape(DS.Radius.md))
            .drawBehind {
                val inset = DS.Spacing.sm.toPx()
                val width = 3.dp.toPx()
                drawRoundRect(agent, Offset(0f, inset), Size(width, size.height - inset * 2), CornerRadius(width / 2))
            }
            .padding(DS.Spacing.md),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        Text(inline(text, link), style = DS.Typography.callout, color = DS.Palette.ink)
        HStack(
            Modifier.plainButton {
                copyToClipboard(context, text)
                haptics.success()
                copied = true
            },
            spacing = DS.Spacing.xs,
        ) {
            SFImage(if (copied) "checkmark" else "doc.on.doc", size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.agent)
            Text(if (copied) L("copied") else L("copy"), style = DS.Typography.caption.semibold(), color = DS.Palette.agent)
        }
    }
}

/** `UIPasteboard.general.string = text`. */
fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager ?: return
    clipboard.setPrimaryClip(ClipData.newPlainText("Omi", text))
}
