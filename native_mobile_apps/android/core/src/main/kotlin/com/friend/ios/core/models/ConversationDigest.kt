package com.friend.ios.core.models

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * Port of `ConversationDigest.swift`: the short form of a conversation: the summary's first
 * sentences (the detail page leads with them, "More" shows the rest) and a clean Markdown export
 * for the user's own AI.
 */
object ConversationDigest {
    /** `(text, isShortened)`. */
    data class Lead(val text: String, val isShortened: Boolean)

    /**
     * The opening of a summary as plain text: headings, bullets and emphasis dropped, at most
     * [sentences] sentences and about [characters] characters. `isShortened` says whether the
     * summary has more than that (the page then offers "More").
     */
    fun lead(markdown: String, sentences: Int = 3, characters: Int = 280): Lead {
        val paragraphs = plainParagraphs(markdown)
        val all = paragraphs.joinToString(" ")
        if (all.isEmpty()) return Lead("", false)
        val kept = mutableListOf<String>()
        var length = 0
        for (sentence in split(all)) {
            if (kept.size == sentences) break
            // Always keep the first sentence; later ones only while they fit.
            if (kept.isNotEmpty() && length + sentence.length + 1 > characters) break
            kept += sentence
            length += sentence.length + 1
        }
        var text = kept.joinToString(" ")
        if (text.length > characters + 40) {
            // One very long first sentence: cut at a word.
            val cut = text.take(characters)
            val space = cut.lastIndexOf(' ')
            text = (if (space >= 0) cut.substring(0, space) else cut) + "…"
        }
        val rest = all.length - text.length
        // A summary that is a heading list ("## Decisions") is shortened even when its prose fits.
        return Lead(text, rest > 1 || markdown.contains("\n#") || markdown.startsWith("#"))
    }

    /**
     * The conversation as Markdown for another AI: title, date, summary, action items, the
     * transcript with timestamps, and the link.
     */
    fun markdown(export: Export, labels: Labels, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
        val parts = mutableListOf("# ${export.title}")
        val format = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL, FormatStyle.SHORT).withLocale(locale)
        var `when` = runCatching { format.format(export.date.atZone(zone)) }.getOrElse {
            DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT).withLocale(locale).format(export.date.atZone(zone))
        }
        export.duration?.let { `when` += " · ${maxOf(1, Math.round(it / 60).toInt())} min" }
        parts += `when`
        val summary = export.summary.trim()
        if (summary.isNotEmpty()) parts += "## ${labels.summary}\n\n${demoteHeadings(summary)}"
        if (export.actionItems.isNotEmpty()) {
            val items = export.actionItems.joinToString("\n") { "- [${if (it.isDone) "x" else " "}] ${it.text}" }
            parts += "## ${labels.actionItems}\n\n$items"
        }
        if (export.transcript.isNotEmpty()) {
            val lines = export.transcript.joinToString("\n") { "[${timestamp(it.start)}] **${it.speaker}:** ${it.text}" }
            parts += "## ${labels.transcript}\n\n$lines"
        }
        export.link?.let { parts += "${labels.link}: $it" }
        return parts.joinToString("\n\n") + "\n"
    }

    /** What goes into the export. */
    data class Export(
        val title: String,
        val date: Instant,
        /** Seconds. */
        val duration: Double?,
        val summary: String,
        val actionItems: List<ActionItemLine>,
        val transcript: List<ConversationDetail.Line>,
        val link: String?,
    )

    data class ActionItemLine(val text: String, val isDone: Boolean = false)

    data class Labels(val summary: String, val actionItems: String, val transcript: String, val link: String)

    /**
     * Where a task came from in this conversation, in one line: the transcript words its
     * extraction cited, else the extraction's context ("Anna asked for it before Friday"), else null.
     */
    fun quote(forTask: String, detail: ConversationDetail): String? {
        val source = detail.actionItemSources[normalized(forTask)] ?: return null
        val cited = source.segmentIDs.toSet()
        val words = detail.transcript.filter { line -> line.segmentID?.let { it in cited } ?: false }.map { it.text }
        if (words.isNotEmpty()) return words.joinToString(" ")
        val context = source.context.trim()
        return context.ifEmpty { null }
    }

    /** Task descriptions as keys: case, spacing and a final period do not matter. */
    fun normalized(description: String): String {
        var text = description.lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (text.endsWith(".")) text = text.dropLast(1)
        return text
    }

    /**
     * Consecutive lines of one speaker as one paragraph (a transcript reads like a document, not a
     * chat), but never a wall: a long turn breaks into paragraphs of about [maxCharacters]. A
     * paragraph's id is its first line's.
     */
    fun paragraphs(lines: List<ConversationDetail.Line>, maxCharacters: Int = 420): List<Paragraph> {
        val result = mutableListOf<Paragraph>()
        for (line in lines) {
            val current = result.lastOrNull()
            val last = current?.lines?.lastOrNull()
            if (current != null && last != null && sameSpeaker(last, line) && current.characterCount + line.text.length <= maxCharacters) {
                result[result.lastIndex] = current.copy(lines = current.lines + line)
            } else {
                val continues = result.lastOrNull()?.lines?.lastOrNull()?.let { sameSpeaker(it, line) } ?: false
                result += Paragraph(listOf(line), continuesTurn = continues)
            }
        }
        return result
    }

    data class Paragraph(
        val lines: List<ConversationDetail.Line>,
        /** The same speaker went on from the paragraph before (the page shows just the time). */
        val continuesTurn: Boolean = false,
    ) {
        val id: Int get() = lines[0].id
        val first: ConversationDetail.Line get() = lines[0]
        internal val characterCount: Int get() = lines.sumOf { it.text.length + 1 }

        fun contains(lineID: Int): Boolean = lines.any { it.id == lineID }
    }

    /**
     * The transcript in chapters, so it can be scanned: the notes' sections (each cites its
     * segments) when they cover enough of it, else blocks of [blockSize] paragraphs. A chapter's id
     * is its first paragraph's.
     */
    fun chapters(lines: List<ConversationDetail.Line>, sections: List<ConversationDetail.Chapter>, blockSize: Int = 6): List<Chapter> {
        val paragraphs = paragraphs(lines)
        if (paragraphs.isEmpty()) return emptyList()
        val sectionOf = HashMap<String, Int>()
        sections.forEachIndexed { index, section ->
            for (id in section.segmentIDs) if (sectionOf[id] == null) sectionOf[id] = index
        }
        val cited = lines.count { line -> line.segmentID?.let { sectionOf[it] != null } ?: false }
        // Notes that cite little of the transcript would leave most of it under the wrong heading.
        if (sections.size <= 1 || cited.toDouble() < lines.size * 0.3) {
            return paragraphs.chunked(blockSize).map { Chapter(null, it) }
        }
        val result = mutableListOf<Chapter>()
        var currentSection: Int? = null
        for (paragraph in paragraphs) {
            val own = paragraph.lines.firstNotNullOfOrNull { line -> line.segmentID?.let { sectionOf[it] } }
            val section = own ?: currentSection
            val last = result.lastOrNull()
            if (last != null && section == currentSection && last.paragraphs.isNotEmpty()) {
                result[result.lastIndex] = last.copy(paragraphs = last.paragraphs + paragraph)
            } else {
                result += Chapter(section?.let { sections[it].heading }, listOf(paragraph))
            }
            currentSection = section
        }
        return result
    }

    data class Chapter(
        /** The notes' heading; null for a plain block (the page shows its time). */
        val title: String?,
        val paragraphs: List<Paragraph>,
    ) {
        val id: Int get() = paragraphs[0].id

        /** Seconds. */
        val start: Double get() = paragraphs[0].first.start

        fun contains(lineID: Int): Boolean = paragraphs.any { it.contains(lineID) }
    }

    internal fun sameSpeaker(lhs: ConversationDetail.Line, rhs: ConversationDetail.Line): Boolean {
        if (lhs.isUser || rhs.isUser) return lhs.isUser == rhs.isUser
        val left = lhs.personID ?: lhs.speakerID?.toString()
        val right = rhs.personID ?: rhs.speakerID?.toString()
        if (left != null && right != null) return left == right
        return lhs.speaker == rhs.speaker
    }

    /** "4:05", "1:02:09". */
    fun timestamp(seconds: Double): String {
        val total = maxOf(0, Math.floor(seconds).toInt())
        val hours = total / 3600
        val minutes = total / 60 % 60
        val rest = total % 60
        return if (hours > 0) String.format(Locale.ROOT, "%d:%02d:%02d", hours, minutes, rest) else String.format(Locale.ROOT, "%d:%02d", minutes, rest)
    }

    // Helpers

    /** Paragraph text without Markdown: headings are dropped (they are labels, not prose). */
    internal fun plainParagraphs(markdown: String): List<String> = markdown
        .split(Regex("\\r\\n|\\r|\\n"))
        .map { it.trim() }
        .filter { it.isNotEmpty() && !it.startsWith("#") && it != "---" }
        .map { raw ->
            var line = raw
            for (marker in listOf("- ", "* ", "• ", "> ")) if (line.startsWith(marker)) line = line.drop(marker.length)
            Regex("^\\d+\\.\\s").find(line)?.let { line = line.removeRange(it.range) }
            line = line.replace("**", "").replace("__", "")
            // A bullet without a period still ends a thought.
            val last = line.lastOrNull()
            if (last != null && last !in ".!?…:") line += "."
            line
        }

    /** Sentences, split after ". ", "! ", "? " (abbreviations like "e.g." are rare in summaries). */
    internal fun split(text: String): List<String> {
        val sentences = mutableListOf<String>()
        val current = StringBuilder()
        text.forEachIndexed { index, character ->
            current.append(character)
            val next = if (index + 1 < text.length) text[index + 1] else ' '
            if (character in ".!?…" && next == ' ') {
                val sentence = current.toString().trim()
                if (sentence.isNotEmpty()) sentences += sentence
                current.clear()
            }
        }
        val tail = current.toString().trim()
        if (tail.isNotEmpty()) sentences += tail
        return sentences
    }

    /** Summary headings one level under the export's "## Summary". */
    internal fun demoteHeadings(markdown: String): String =
        markdown.split("\n").joinToString("\n") { if (it.startsWith("#")) "#$it" else it }
}
