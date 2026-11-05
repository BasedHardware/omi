package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ChatMessage
import java.time.Duration
import java.time.Instant

/**
 * Port of `ChatLayout.swift`: how the thread lays out, as in Messages. Pure rules, so they are
 * tested without a screen: long answers in a few bubbles, bubbles of one sender grouped, which
 * extras an answer shows, cards of a kind stacked, whether the list sits at its end, and when the
 * app header collapses.
 */

/**
 * A long answer in a few bubbles: split where a paragraph ends (a blank line), never inside fenced
 * code, a list, a table or a quote, a heading or a line ending in ":" kept with what it introduces.
 * At most [MAX_BUBBLES]; the rest stays in the last one. While an answer streams, finished
 * paragraphs keep their bubbles: only the end grows (a loose list joins its items).
 */
object ChatBubbleSplit {
    const val MAX_BUBBLES = 4

    fun split(text: String): List<String> {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return emptyList()
        val chunks = mutableListOf<List<String>>()
        var current = mutableListOf<String>()
        var insideFence = false
        for (line in trimmed.split("\n")) {
            val bare = line.trim()
            if (bare.startsWith("```")) insideFence = !insideFence
            if (bare.isEmpty() && !insideFence) {
                if (current.isNotEmpty()) chunks.add(current)
                current = mutableListOf()
            } else {
                current.add(line)
            }
        }
        if (current.isNotEmpty()) chunks.add(current)

        val merged = mutableListOf<List<String>>()
        for (chunk in chunks) {
            val previous = merged.lastOrNull()
            if (previous != null && belongTogether(previous, chunk)) {
                merged[merged.size - 1] = previous + "" + chunk
            } else {
                merged.add(chunk)
            }
        }
        val texts = merged.map { it.joinToString("\n") }
        if (texts.size > MAX_BUBBLES) {
            val rest = texts.drop(MAX_BUBBLES - 1).joinToString("\n\n")
            return texts.take(MAX_BUBBLES - 1) + rest
        }
        return texts
    }

    /**
     * Two paragraphs that read as one: a heading or an intro ("Here is what I found:") and what
     * follows, a list or table or quote that goes on (loose list items), or an indented line.
     */
    internal fun belongTogether(first: List<String>, second: List<String>): Boolean {
        val last = first.lastOrNull()?.trim() ?: return false
        val next = second.firstOrNull() ?: return false
        val nextBare = next.trim()
        if (first.all { it.trim().startsWith("#") }) return true
        if (last.endsWith(":")) return true
        if (isListItem(last) && (isListItem(nextBare) || next.startsWith("  "))) return true
        if (last.startsWith("|") && nextBare.startsWith("|")) return true
        if (last.startsWith(">") && nextBare.startsWith(">")) return true
        // An unclosed fence: the code goes on in the next part.
        val fences = first.count { it.trim().startsWith("```") }
        return fences % 2 == 1
    }

    private val bullet = Regex("[*\\-•+–◦]\\s+.+")
    private val numbered = Regex("\\d{1,3}[.)]\\s+.+")

    internal fun isListItem(line: String): Boolean = bullet.matches(line) || numbered.matches(line)
}

/**
 * Bubbles of one sender in a row form a group (a few points apart; more room between groups): only
 * its last bubble carries the tail, and Omi's avatar sits beside it.
 */
object ChatGrouping {
    /**
     * One row of the thread. [sender] null: not a message (a day line, a finished run), which
     * always ends a group.
     */
    data class Item(
        val id: String,
        val sender: ChatMessage.Sender?,
        val date: Instant? = null,
        /** Something stands above its bubbles (steps, cards): it starts a new group. */
        val leadsWithExtras: Boolean = false,
        /** Something stands below its bubbles (sources, a follow-up): the group ends with it. */
        val endsWithExtras: Boolean = false,
    )

    data class Position(val isFirst: Boolean, val isLast: Boolean) {
        companion object {
            val alone = Position(isFirst = true, isLast = true)
        }
    }

    /** Messages further apart than this start a new group. */
    val maxGap: Duration = Duration.ofMinutes(10)

    fun positions(items: List<Item>): Map<String, Position> {
        val result = HashMap<String, Position>()
        items.forEachIndexed { index, item ->
            if (item.sender == null) return@forEachIndexed
            val joinsPrevious = index > 0 && joined(items[index - 1], item)
            val joinsNext = index + 1 < items.size && joined(item, items[index + 1])
            result[item.id] = Position(isFirst = !joinsPrevious, isLast = !joinsNext)
        }
        return result
    }

    internal fun joined(first: Item, second: Item): Boolean {
        val sender = first.sender ?: return false
        if (sender != second.sender || first.endsWithExtras || second.leadsWithExtras) return false
        val start = first.date ?: return true
        val end = second.date ?: return true
        return Duration.between(start, end).abs() <= maxGap
    }
}

/**
 * What shows under an answer. Only the newest answer keeps its source chips and its follow-up
 * question (the follow-up only while nothing is typed); an older one folds its sources into a small
 * "2 sources" line that opens them. "Stop reading" only while that answer is read aloud.
 */
object ChatAnswerExtras {
    sealed interface Sources {
        data object None : Sources
        data object Chips : Sources
        data class Collapsed(val count: Int) : Sources
    }

    data class Shown(val sources: Sources, val followUp: Boolean, val stopReading: Boolean) {
        /** Anything at all below the bubbles. */
        val isEmpty: Boolean get() = sources == Sources.None && !followUp && !stopReading
    }

    /**
     * The answer itself: the newest one, still streaming, failed (no reply came), how many
     * conversations it drew on, whether it has a follow-up question.
     */
    data class Answer(
        val isLatest: Boolean,
        val isStreaming: Boolean = false,
        val failed: Boolean = false,
        val citations: Int = 0,
        val hasFollowUp: Boolean = false,
    )

    fun shown(answer: Answer, draftIsEmpty: Boolean, isSpeaking: Boolean, sourcesExpanded: Boolean = false): Shown {
        val sources = when {
            answer.failed || answer.citations == 0 -> Sources.None
            answer.isLatest || sourcesExpanded -> Sources.Chips
            else -> Sources.Collapsed(answer.citations)
        }
        return Shown(
            sources = sources,
            followUp = answer.isLatest && !answer.isStreaming && !answer.failed && answer.hasFollowUp && draftIsEmpty,
            stopReading = isSpeaking,
        )
    }
}

/** Never two cards of one kind in a row: a run of them becomes one stack (the first card and "n more"). */
object ChatStacking {
    fun <T> stacks(items: List<T>, kind: (T) -> String): List<List<T>> {
        val result = mutableListOf<MutableList<T>>()
        var lastKind: String? = null
        for (item in items) {
            val itemKind = kind(item)
            if (itemKind == lastKind && result.isNotEmpty()) {
                result.last().add(item)
            } else {
                result.add(mutableListOf(item))
            }
            lastKind = itemKind
        }
        return result
    }
}

/** Cards of one kind stack (two connections, three new tasks). */
val ChatCard.kind: String
    get() = when (this) {
        is ChatCard.Connect -> "connect"
        is ChatCard.TaskAdded -> "added"
        is ChatCard.TaskCompleted -> "done"
    }

/**
 * Whether the thread rests at its end, for following new words and the jump-to-latest button. The
 * geometry is believed as soon as it says "at the end"; it only says "not at the end" while the
 * user scrolls (an answer growing or the keyboard coming up never stops the following), and once a
 * scroll comes to rest wherever it ended (also a fling that bounced at the end).
 */
class ChatBottomTracker {
    var isAtBottom: Boolean by mutableStateOf(true)
        private set
    var geometryAtBottom: Boolean = true
        private set
    var isScrolling: Boolean = false
        private set

    fun geometryChanged(atBottom: Boolean) {
        geometryAtBottom = atBottom
        if (atBottom || isScrolling) isAtBottom = atBottom
    }

    fun phaseChanged(isIdle: Boolean) {
        isScrolling = !isIdle
        if (isIdle) isAtBottom = geometryAtBottom
    }

    /** The jump button or a sent question took the list to its end. */
    fun jumpedToBottom() {
        isAtBottom = true
        geometryAtBottom = true
    }

    companion object {
        /** How close to the end still counts as at the end (a line or two of a bubble). */
        const val THRESHOLD: Double = 80.0

        /**
         * At the end while the content's end is within [threshold] of the visible bottom edge
         * (above the composer and keyboard, which [bottomInset] covers).
         */
        fun isAtBottom(offsetY: Double, containerHeight: Double, bottomInset: Double, contentHeight: Double, threshold: Double = THRESHOLD): Boolean =
            offsetY + containerHeight - bottomInset >= contentHeight - threshold
    }
}
