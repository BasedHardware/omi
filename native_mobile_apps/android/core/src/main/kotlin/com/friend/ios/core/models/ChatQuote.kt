package com.friend.ios.core.models

/**
 * Port of `ChatQuote.swift`. A reply to an earlier message travels as a short quote line in front
 * of the question ("> Omi: …", a blank line, then the question), so the agent reads what it
 * refers to and any device shows it. The chat draws the quote above the question instead of as text.
 */
data class ChatQuote(
    /** "Omi" or "Me": who wrote the quoted message. */
    val speaker: String,
    val snippet: String,
) {
    /** Whether the quoted message is one of Omi's. */
    val quotesOmi: Boolean get() = speaker == OMI_SPEAKER

    /** `text` with this quote in front, as it is sent. */
    fun prefixing(text: String): String = "> $speaker: $snippet\n\n$text"

    /** The quote a message starts with (if any) and the rest of its text. */
    data class Split(val quote: ChatQuote?, val body: String)

    companion object {
        const val OMI_SPEAKER = "Omi"
        const val USER_SPEAKER = "Me"
        /** Longer messages are cut to about this many characters in the quote. */
        const val MAX_LENGTH = 200

        /** The quote for replying to [message]: one line, cut at a word near [MAX_LENGTH]. */
        fun replyingTo(message: ChatMessage): ChatQuote {
            val body = split(message.text).body
            val words = body.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
            var snippet = words
            if (words.length > MAX_LENGTH) {
                val cut = words.take(MAX_LENGTH)
                val space = cut.lastIndexOf(' ')
                val trimmed = if (space >= 0) cut.substring(0, space) else cut
                snippet = trimmed.trim { it.isWhitespace() || isPunctuation(it) } + "…"
            }
            return ChatQuote(if (message.sender == ChatMessage.Sender.Omi) OMI_SPEAKER else USER_SPEAKER, snippet)
        }

        fun split(text: String): Split {
            if (!text.startsWith("> ")) return Split(null, text)
            val end = text.indexOf("\n\n")
            if (end < 0) return Split(null, text)
            val line = text.substring(2, end)
            val colon = line.indexOf(": ")
            if (line.contains('\n') || colon < 0) return Split(null, text)
            val speaker = line.substring(0, colon)
            if (speaker != OMI_SPEAKER && speaker != USER_SPEAKER) return Split(null, text)
            val body = text.substring(end + 2).trim()
            if (body.isEmpty()) return Split(null, text)
            return Split(ChatQuote(speaker, line.substring(colon + 2)), body)
        }

        private fun isPunctuation(c: Char): Boolean = when (Character.getType(c).toByte()) {
            Character.CONNECTOR_PUNCTUATION, Character.DASH_PUNCTUATION, Character.START_PUNCTUATION, Character.END_PUNCTUATION,
            Character.INITIAL_QUOTE_PUNCTUATION, Character.FINAL_QUOTE_PUNCTUATION, Character.OTHER_PUNCTUATION,
            -> true
            else -> false
        }
    }
}
