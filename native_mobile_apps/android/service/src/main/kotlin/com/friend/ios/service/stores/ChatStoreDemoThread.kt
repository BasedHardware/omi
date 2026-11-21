package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatEvidence
import com.friend.ios.core.models.ChatMessage
import java.time.Instant

/*
 * Port of the demo part of `ChatStore+Cards.swift`. Debug builds: what a screenshot of the
 * iMessage-style thread needs, on this phone only (never sent, gone on the next load).
 */

/**
 * A made-up exchange appended to the thread: grouped bubbles, a long answer in parts and a card
 * stack, on a test account whose thread is empty (`-omiChatDemoThread YES`).
 */
fun ChatStore.showDemoThread() {
    val start = Instant.now().minusSeconds(20 * 60)
    fun at(minutes: Double): Instant = start.plusMillis((minutes * 60_000).toLong())
    val long = """
        Here is where things stand with the **Q4 roadmap**.

        Anna wants the deck by Thursday; the open points are pricing and the launch date.

        What I would do next:

        - Send Anna the draft deck today
        - Ask Ben for the pricing numbers
        - Book 30 minutes with both on Wednesday

        Want me to draft the message to Anna? [The notes](https://omi.me) have the details.
    """.trimIndent()
    messages = messages + listOf(
        ChatMessage(id = "demo-q1", text = "What did Anna say about the roadmap?", sender = ChatMessage.Sender.User, createdAt = at(0.0)),
        ChatMessage(id = "demo-q2", text = "And what should I do next?", sender = ChatMessage.Sender.User, createdAt = at(0.2)),
        ChatMessage(
            id = "demo-a1", text = long, sender = ChatMessage.Sender.Omi, createdAt = at(0.5),
            references = listOf(ChatMessage.Reference("demo-1", "Q4 roadmap with Anna", "🗺️", at(-180.0))),
        ),
        ChatMessage(id = "demo-q3", text = "Add those as tasks", sender = ChatMessage.Sender.User, createdAt = at(2.0)),
        ChatMessage(id = "demo-a2", text = "Done, three new tasks.", sender = ChatMessage.Sender.Omi, createdAt = at(2.2), steps = listOf("Adding tasks")),
        ChatMessage(id = "demo-q4", text = "Thanks!", sender = ChatMessage.Sender.User, createdAt = at(3.0)),
        ChatMessage(
            id = "demo-a3", text = "Anytime.\n\nI will remind you on Wednesday morning.", sender = ChatMessage.Sender.Omi, createdAt = at(3.1),
            followUp = "Should I also invite Ben to the Wednesday meeting?",
        ),
    )
    add(
        listOf(
            ChatCard.TaskAdded("demo-t1", "Send Anna the draft deck"),
            ChatCard.TaskAdded("demo-t2", "Ask Ben for the pricing numbers"),
            ChatCard.TaskAdded("demo-t3", "Book 30 minutes with Anna and Ben"),
        ),
        messageID = "demo-a2", newest = false,
    )
}

/**
 * A connect card, a task card and source chips on the newest answer, without a turn
 * (`-omiChatDemoCards YES`). Undo on the task card changes nothing real (no such task).
 */
fun ChatStore.showDemoCards() {
    val index = messages.indexOfLast { it.sender == ChatMessage.Sender.Omi }
    if (index < 0) return
    val id = messages[index].id
    add(listOf(ChatCard.Connect("google_calendar"), ChatCard.TaskAdded("demo-task", "Send Anna the Thursday follow-up")), messageID = id, newest = false)
    if (messages[index].references.isNotEmpty()) return
    val start = Instant.now().minusSeconds(3 * 3600)
    messages = messages.toMutableList().also { list ->
        list[index] = list[index].copy(
            references = listOf(
                ChatMessage.Reference("demo-1", "Q4 roadmap with Anna", "🗺️", start),
                ChatMessage.Reference("demo-2", "Standup", "☕️", start.minusSeconds(86_400)),
            ),
            evidence = listOf(
                ChatEvidence(
                    id = "e1", kind = ChatEvidence.Kind.ConversationSegment, state = ChatEvidence.State.Available,
                    conversationID = "demo-1", segmentID = "s4", startMs = 754_000,
                ),
            ),
        )
    }
}
