package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMessage

/**
 * Port of `ChatBlockLayout.swift`: how a message's `content_blocks` sit against its body. Pure
 * rules, so they are tested without a screen: which blocks draw a card the user can act on, whether
 * those cards replace the body (a turn whose whole text is the fallback synthesized from its
 * blocks) and, when they do, which lines still have to be drawn so nothing on the wire is silently
 * lost.
 *
 * Mirrors Flutter `ChatContentBlockList` and `ServerMessage.textIsStructuredFallback`.
 */
object ChatBlockLayout {
    /**
     * A block with a component of its own. Everything else (text, thinking, tool calls, citations,
     * a type this client does not know) has no card and shows its fallback line only when the cards
     * replace the body, where the body can no longer carry it.
     */
    fun isRenderable(kind: ChatBlock.Kind): Boolean = when (kind) {
        is ChatBlock.Kind.Task,
        is ChatBlock.Kind.Goal,
        is ChatBlock.Kind.Memory,
        is ChatBlock.Kind.Conversation,
        is ChatBlock.Kind.Discovery,
        is ChatBlock.Kind.Question,
        is ChatBlock.Kind.AgentRun,
        is ChatBlock.Kind.MemoryReview,
        -> true

        is ChatBlock.Kind.Text,
        is ChatBlock.Kind.Other,
        -> false
    }

    fun hasRenderable(blocks: List<ChatBlock>): Boolean = blocks.any { isRenderable(it.kind) }

    /**
     * True when the blocks carry the turn's whole content: only then do they replace the body. A
     * review card is chrome (Flutter `MemoryReviewCard`), never a body of its own, so a turn that is
     * nothing but a review card keeps whatever body it came with.
     */
    private fun carriesBody(blocks: List<ChatBlock>): Boolean =
        blocks.any { it.kind !is ChatBlock.Kind.MemoryReview && isRenderable(it.kind) }

    /**
     * The line each block would say as plain text, in order, as one body. This is what a client that
     * cannot draw a block writes into the message text, and so what a body has to match to be
     * nothing but that projection.
     */
    fun structuredFallback(blocks: List<ChatBlock>): String =
        blocks.map { it.fallbackText.trim() }.filter { it.isNotEmpty() }.joinToString("\n")

    /**
     * True when the body carries nothing of its own: it is empty, or exactly the fallback
     * synthesized from the blocks. The cards then replace it instead of repeating it.
     *
     * A day summary keeps its body: it is a list, not a projection of blocks. A message with no body
     * and no renderable block keeps the ordinary path, so a text-only turn is unaffected.
     */
    fun blocksReplaceBody(message: ChatMessage): Boolean {
        if (message.kind == ChatMessage.Kind.DaySummary || !carriesBody(message.blocks)) return false
        val body = normalized(message.text)
        if (body.isEmpty()) return true
        val fallback = normalized(structuredFallback(message.blocks))
        return fallback.isNotEmpty() && body == fallback
    }

    /**
     * The lines the cards cannot draw, so a body-replacing turn still shows them. A renderable block
     * is its card; everything else is its fallback text.
     */
    fun fallbackLines(blocks: List<ChatBlock>): List<String> =
        blocks.filter { !isRenderable(it.kind) }.map { it.fallbackText.trim() }.filter { it.isNotEmpty() }

    private fun normalized(text: String): String {
        val out = StringBuilder()
        var separated = false
        for (character in text) {
            if (character.isWhitespace()) {
                if (out.isNotEmpty()) separated = true
            } else {
                if (separated) {
                    out.append(' ')
                    separated = false
                }
                out.append(character)
            }
        }
        return out.toString()
    }
}

/**
 * Port of `ChatDaySummary`: a day summary is a list of what happened, not prose (Flutter
 * `DaySummaryWidget.splitMessage`). Numbered items lose their numbers ("1. …"), everything else
 * splits at sentence ends.
 */
object ChatDaySummary {
    private val numberedLine = Regex("(?m)^\\d+\\.\\s")
    private val number = Regex("\\d+\\.\\s")

    fun items(text: String): List<String> {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return emptyList()
        if (numberedLine.containsMatchIn(trimmed)) {
            val withoutNumbers = number.replace(trimmed, "")
            return withoutNumbers.split('\n', '.').map { it.trim() }.filter { it.isNotEmpty() }
        }
        return trimmed.split(". ")
            .map { it.trim() }
            .map { if (it.endsWith(".")) it.dropLast(1) else it }
            .filter { it.isNotEmpty() }
    }
}
