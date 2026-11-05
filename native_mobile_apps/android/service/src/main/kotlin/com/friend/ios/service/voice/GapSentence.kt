package com.friend.ios.service.voice

import java.text.Normalizer

/**
 * Port of `GapSentence.swift`. A sentence to say out loud with blanks the user fills in ("My name
 * is ___ and I spend most of my time ___."), matched against what was heard: the fixed words get
 * checked off, the blanks fill with the user's own words. Matching is fuzzy (recognizers mishear,
 * people paraphrase) and works for any language that separates words with spaces.
 */
data class GapSentence(val parts: List<Part>) {
    /** One word of the template as shown, or a blank. */
    sealed interface Part {
        data class Word(val text: String) : Part
        data object Blank : Part
    }

    /** What was said, laid over the template. */
    data class Match(val pieces: List<Piece>) {
        sealed interface Piece {
            data class Word(val text: String, val heard: Boolean) : Piece
            /** The user's words in this blank; empty while not said yet. */
            data class Blank(val text: String) : Piece
        }

        val fixedTotal: Int get() = pieces.count { it is Piece.Word }
        val fixedHeard: Int get() = pieces.count { it is Piece.Word && it.heard }
        val blanks: List<String> get() = pieces.mapNotNull { (it as? Piece.Blank)?.text }

        /**
         * Most fixed words heard (recognizers drop the odd short word) and every blank has at
         * least one word. A sentence that is only a blank needs a few words.
         */
        val isComplete: Boolean
            get() {
                val filled = blanks.all { it.isNotEmpty() }
                if (fixedTotal <= 0) return blanks.sumOf { wordCount(it) } >= FREE_WORDS
                return filled && fixedHeard * 10 >= fixedTotal * 6
            }

        /** 0...1: how much of the sentence is there. */
        val progress: Double
            get() {
                if (isComplete) return 1.0
                val total = fixedTotal + blanks.size
                if (total <= 0) return 0.0
                if (fixedTotal == 0) {
                    val words = blanks.sumOf { wordCount(it) }
                    return minOf(1.0, words.toDouble() / FREE_WORDS)
                }
                return (fixedHeard + blanks.count { it.isNotEmpty() }).toDouble() / total
            }
    }

    private sealed interface Item {
        val part: Int
        data class Token(val text: String, override val part: Int) : Item
        data class Blank(override val part: Int) : Item
    }

    private sealed interface Step {
        data class Match(val item: Int, val token: Int) : Step
        data class Fill(val item: Int, val token: Int) : Step
    }

    private sealed interface Move {
        data object None : Move
        data object Match : Move
        data object Substitute : Move
        data object Delete : Move
        data object Insert : Move
        data class Blank(val count: Int) : Move
    }

    /**
     * Aligns the spoken words to the template (an edit distance where blanks take any number of
     * words for free), then reads off which fixed words were heard and what fills each blank.
     */
    fun match(spoken: String): Match {
        val items = mutableListOf<Item>()
        parts.forEachIndexed { index, part ->
            when (part) {
                is Part.Word -> items += tokens(part.text).map { Item.Token(it, index) }
                Part.Blank -> items += Item.Blank(index)
            }
        }
        // Tokens of what was said, each pointing back to the word it came from ("I'm" -> i, am).
        val said = mutableListOf<Pair<String, Int>>()
        val words = spoken.split(WHITESPACE).filter { it.isNotEmpty() }.takeLast(MAXIMUM_WORDS)
        val shown = words.map { it.trim { c -> isPunctuation(c) } }
        words.forEachIndexed { index, word -> said += tokens(word).map { it to index } }
        val path = align(items, said.map { it.first })

        val heard = HashSet<Int>()
        val fills = HashMap<Int, MutableList<Int>>()
        for (step in path) {
            when (step) {
                is Step.Match -> (items[step.item] as? Item.Token)?.let { heard += it.part }
                is Step.Fill -> (items[step.item] as? Item.Blank)?.let { blank ->
                    val list = fills.getOrPut(blank.part) { mutableListOf() }
                    if (list.lastOrNull() != said[step.token].second) list += said[step.token].second
                }
            }
        }
        val pieces = parts.mapIndexed { index, part ->
            when (part) {
                is Part.Word -> Match.Piece.Word(part.text, index in heard)
                Part.Blank -> Match.Piece.Blank(fills[index].orEmpty().map { shown[it] }.filter { it.isNotEmpty() }.joinToString(" "))
            }
        }
        return Match(pieces)
    }

    /**
     * Costs: a fuzzy match 0, a word not said or said differently 2-3, an extra word 2, words
     * inside a blank 0. Ties go to the path with more matched words, then to words in the
     * earlier blank (a name said so far belongs in the first gap, not the last).
     */
    private fun align(items: List<Item>, tokens: List<String>): List<Step> {
        val rows = items.size
        val columns = tokens.size
        val infinity = Long.MAX_VALUE / 4
        val unit = 100_000L
        val matched = 1000L
        val ordinals = HashMap<Int, Int>()
        items.forEachIndexed { index, item -> if (item is Item.Blank) ordinals[index] = ordinals.size }
        val cost = Array(rows + 1) { LongArray(columns + 1) { infinity } }
        val move = Array(rows + 1) { Array<Move>(columns + 1) { Move.None } }
        cost[0][0] = 0
        for (row in 0..rows) {
            for (column in 0..columns) {
                if (cost[row][column] >= infinity) continue
                val here = cost[row][column]
                fun relax(toRow: Int, toColumn: Int, value: Long, how: Move) {
                    if (value < cost[toRow][toColumn]) {
                        cost[toRow][toColumn] = value
                        move[toRow][toColumn] = how
                    }
                }
                if (column < columns) relax(row, column + 1, here + 2 * unit, Move.Insert)
                if (row >= rows) continue
                when (val item = items[row]) {
                    is Item.Token -> {
                        relax(row + 1, column, here + 2 * unit, Move.Delete)
                        if (column < columns) {
                            if (similar(item.text, tokens[column])) {
                                relax(row + 1, column + 1, here - matched, Move.Match)
                            } else {
                                relax(row + 1, column + 1, here + 3 * unit, Move.Substitute)
                            }
                        }
                    }
                    is Item.Blank -> {
                        val ordinal = ordinals[row] ?: 0
                        for (end in column..columns) relax(row + 1, end, here + (end - column).toLong() * ordinal, Move.Blank(end - column))
                    }
                }
            }
        }
        return backtrack(move, rows, columns)
    }

    private fun backtrack(move: Array<Array<Move>>, rows: Int, columns: Int): List<Step> {
        val steps = mutableListOf<Step>()
        var row = rows
        var column = columns
        while (row > 0 || column > 0) {
            when (val how = move[row][column]) {
                Move.Match -> {
                    steps += Step.Match(row - 1, column - 1)
                    row -= 1; column -= 1
                }
                Move.Substitute -> { row -= 1; column -= 1 }
                Move.Delete -> row -= 1
                Move.Insert -> column -= 1
                is Move.Blank -> {
                    for (token in (column - how.count until column).reversed()) steps += Step.Fill(row - 1, token)
                    row -= 1; column -= how.count
                }
                Move.None -> return steps.reversed()
            }
        }
        return steps.reversed()
    }

    companion object {
        /** `___` (two or more underscores) marks a blank. */
        operator fun invoke(template: String): GapSentence {
            val parts = mutableListOf<Part>()
            val pieces = template.split("__")
            var previousWasBlank = false
            pieces.forEachIndexed { index, piece ->
                val text = piece.trim('_')
                // "___." leaves the period behind: glue punctuation to the blank (nothing to say).
                for (word in text.split(WHITESPACE)) {
                    if (word.isEmpty() || tokens(word).isEmpty()) continue
                    parts += Part.Word(word)
                    previousWasBlank = false
                }
                if (index < pieces.size - 1 && !previousWasBlank) {
                    parts += Part.Blank
                    previousWasBlank = true
                }
            }
            return GapSentence(parts)
        }

        /** A sentence that is only a blank: "say anything". */
        val free: GapSentence by lazy { GapSentence("___") }

        const val FREE_WORDS = 3
        const val MAXIMUM_WORDS = 60
        private val WHITESPACE = Regex("\\s+")

        internal fun wordCount(text: String): Int = text.split(' ').count { it.isNotEmpty() }

        private fun isPunctuation(c: Char): Boolean = when (Character.getType(c).toByte()) {
            Character.CONNECTOR_PUNCTUATION, Character.DASH_PUNCTUATION, Character.START_PUNCTUATION,
            Character.END_PUNCTUATION, Character.INITIAL_QUOTE_PUNCTUATION, Character.FINAL_QUOTE_PUNCTUATION,
            Character.OTHER_PUNCTUATION -> true
            else -> false
        }

        /** Lowercased, accents and sharp s folded, English contractions spelled out, punctuation gone. */
        fun tokens(word: String): List<String> {
            var text = word.lowercase().replace('’', '\'').replace("ß", "ss")
            text = Normalizer.normalize(text, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")
            for ((short, long) in listOf("n't" to " not", "'m" to " am", "'re" to " are", "'ve" to " have", "'ll" to " will", "'d" to " would")) {
                text = text.replace(short, long)
            }
            val kept = buildString { text.forEach { append(if (it.isLetterOrDigit() || it == ' ') it else ' ') } }
            return kept.split(' ').filter { it.isNotEmpty() }
        }

        /**
         * Same word, allowing for how recognizers and people bend it: short words exactly, longer
         * ones within a letter or two, and different endings ("arbeite" / "arbeiten").
         */
        fun similar(lhs: String, rhs: String): Boolean {
            if (lhs == rhs) return true
            val shorter = minOf(lhs.length, rhs.length)
            val longer = maxOf(lhs.length, rhs.length)
            if (shorter <= 2) return false
            if (shorter >= 4 && (lhs.startsWith(rhs) || rhs.startsWith(lhs))) return true
            val allowed = if (longer <= 4) 1 else if (longer <= 7) 2 else 3
            return longer - shorter <= allowed && distance(lhs, rhs) <= allowed
        }

        fun distance(lhs: String, rhs: String): Int {
            var previous = IntArray(rhs.length + 1) { it }
            lhs.forEachIndexed { row, left ->
                val current = IntArray(rhs.length + 1)
                current[0] = row + 1
                rhs.forEachIndexed { column, right ->
                    current[column + 1] = minOf(previous[column + 1] + 1, current[column] + 1, previous[column] + if (left == right) 0 else 1)
                }
                previous = current
            }
            return previous[rhs.length]
        }
    }
}

/**
 * The voice sample's progress follows the sentences: each finished one is a full step, the one
 * being spoken fills its step only part of the way until it is done.
 */
object VoiceProgress {
    fun fraction(completed: Int, total: Int, current: Double): Double {
        if (total <= 0) return 0.0
        if (completed >= total) return 1.0
        return (completed + minOf(0.9, maxOf(0.0, current))) / total
    }
}
