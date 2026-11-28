package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMemoryReview
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ChatQuestion
import java.time.Instant

/*
 * Port of `ChatStore+DemoBlocks.swift`. Debug builds: the thread a screenshot needs to show every
 * block card, and the task row the task card resolves against. In memory for this launch only:
 * nothing is sent, nothing is stored, and the next load of the real thread replaces it
 * (`-omiChatDemoBlocks YES`).
 */

/** The ids the demo cards point at. */
object DemoBlock {
    const val task = "demo-block-task"
    const val goal = "demo-block-goal"
    const val memory = "demo-block-memory"
    const val conversation = "demo-block-conversation"
}

/**
 * The demo thread. Call it once the real task list has loaded: a task card resolves against that
 * list, and a later load would take the demo row with it.
 */
fun ChatStore.showDemoBlocks(tasks: TasksStore) {
    seedDemoTask(tasks)
    val start = Instant.now().minusSeconds(35 * 60)
    fun at(minutes: Double): Instant = start.plusSeconds((minutes * 60).toLong())
    fun staged(
        id: String,
        minutes: Double,
        blocks: List<ChatBlock>,
        kind: ChatMessage.Kind = ChatMessage.Kind.Text,
        text: String? = null,
    ): ChatMessage = ChatMessage(
        id = id,
        text = text ?: ChatBlockLayout.structuredFallback(blocks),
        sender = ChatMessage.Sender.Omi,
        createdAt = at(minutes),
        blocks = blocks,
        kind = kind,
    )
    messages = messages + listOf(
        staged("demo-blk-1", 0.0, ChatStoreDemoBlocks.workBlocks),
        staged("demo-blk-2", 1.0, listOf(ChatStoreDemoBlocks.askBlock(answeredBy = null))),
        staged("demo-blk-3", 2.0, listOf(ChatStoreDemoBlocks.askBlock(answeredBy = "demo-o1"))),
        staged("demo-blk-4", 3.0, ChatStoreDemoBlocks.runBlocks),
        staged("demo-blk-5", 4.0, listOf(ChatStoreDemoBlocks.discoveryBlock)),
        // The review card draws its own heading, so this turn carries no body of its own.
        staged("demo-blk-6", 5.0, listOf(ChatStoreDemoBlocks.reviewBlock), text = ""),
        staged("demo-blk-7", 6.0, emptyList(), kind = ChatMessage.Kind.DaySummary, text = ChatStoreDemoBlocks.dayText),
        staged("demo-blk-8", 7.0, listOf(ChatStoreDemoBlocks.unknownBlock), text = ChatStoreDemoBlocks.unknownBlock.fallbackText),
    )
}

private fun ChatStore.seedDemoTask(tasks: TasksStore) {
    tasks.tasks = listOf(
        ActionItem(
            id = DemoBlock.task,
            description = "Send Anna the Thursday follow-up",
            isCompleted = false,
            dueAt = Instant.now().plusSeconds(2 * 86400),
            conversationID = null,
            owner = ActionItem.Owner.User,
            workstreamID = null,
            createdAt = Instant.now().minusSeconds(3600),
        ),
    ) + tasks.tasks
}

/** The demo blocks, one per kind that points somewhere. */
object ChatStoreDemoBlocks {
    /** What the answer did: one card per kind that points somewhere. */
    val workBlocks: List<ChatBlock> = listOf(
        ChatBlock(
            id = "demo-b-task", kind = ChatBlock.Kind.Task(DemoBlock.task),
            fallbackText = "Task - Send Anna the Thursday follow-up",
        ),
        ChatBlock(
            id = "demo-b-goal", kind = ChatBlock.Kind.Goal(DemoBlock.goal, "Run 10 km"),
            fallbackText = "Goal - Run 10 km",
        ),
        ChatBlock(
            id = "demo-b-memory", kind = ChatBlock.Kind.Memory(DemoBlock.memory, "Anna leads the Q4 launch"),
            fallbackText = "Memory - Anna leads the Q4 launch",
        ),
        ChatBlock(
            id = "demo-b-conversation",
            kind = ChatBlock.Kind.Conversation(
                conversationID = DemoBlock.conversation, summary = "Q4 roadmap with Anna",
                actionItems = listOf(
                    ChatBlock.ActionItemHint("Send Anna the draft deck", DemoBlock.task),
                    ChatBlock.ActionItemHint("Ask Ben for the pricing numbers", null),
                ),
                isCapture = false,
            ),
            fallbackText = "Meeting notes ready - Q4 roadmap with Anna",
        ),
        ChatBlock(
            id = "demo-b-capture",
            kind = ChatBlock.Kind.Conversation(
                conversationID = DemoBlock.conversation, summary = "Walk to the lake, 41 min",
                actionItems = emptyList(), isCapture = true,
            ),
            fallbackText = "Recording ready - Walk to the lake",
        ),
    )

    /**
     * Omi's question with the answers it prepared. The third option has no prepared answer: it is a
     * label, not a button.
     */
    fun askBlock(answeredBy: String?): ChatBlock = ChatBlock(
        id = "demo-b-question",
        kind = ChatBlock.Kind.Question(
            ChatQuestion(
                questionID = "demo-q1", text = "Which slot should I book for the follow-up?",
                options = listOf(
                    ChatQuestion.Option("demo-o1", "Thursday 7 pm", "Book the follow-up for Thursday at 7 pm"),
                    ChatQuestion.Option("demo-o2", "Friday 9 am", "Book the follow-up for Friday at 9 am"),
                    ChatQuestion.Option("demo-o3", "Another time", ""),
                ),
                selectedOptionID = answeredBy,
            ),
        ),
        fallbackText = "Question - Which slot should I book for the follow-up?",
    )

    /** Three background runs: one still going, one that finished, one that failed. */
    val runBlocks: List<ChatBlock> = listOf(
        ChatBlock(
            id = "demo-b-run",
            kind = ChatBlock.Kind.AgentRun("Check the flight prices", "Watching BER to LIS for a week", ChatBlock.AgentRunStatus.Running),
            fallbackText = "Started - Check the flight prices",
        ),
        ChatBlock(
            id = "demo-b-done",
            kind = ChatBlock.Kind.AgentRun("Book the room", "Booked, confirmation in your mail", ChatBlock.AgentRunStatus.Completed),
            fallbackText = "Done - Book the room",
        ),
        ChatBlock(
            id = "demo-b-failed",
            kind = ChatBlock.Kind.AgentRun("Order the poster", "The shop refused the payment method", ChatBlock.AgentRunStatus.Failed),
            fallbackText = "Failed - Order the poster",
        ),
    )

    val discoveryBlock: ChatBlock = ChatBlock(
        id = "demo-b-discovery",
        kind = ChatBlock.Kind.Discovery(
            title = "Café Kranzler",
            summary = "Two doors down from the office, open until 11 pm.",
            fullText = "Two doors down from the office, open until 11 pm. Quiet in the morning, full after six. " +
                "They take reservations for groups of five or more.",
        ),
        fallbackText = "Discovery - Café Kranzler - Two doors down from the office",
    )

    val reviewBlock: ChatBlock = ChatBlock(
        id = "demo-b-review",
        kind = ChatBlock.Kind.MemoryReview(
            ChatMemoryReview(
                summaryID = "demo-summary", date = "2026-10-12",
                allItems = listOf(
                    ChatMemoryReview.Item("demo-m1", "Anna leads the Q4 launch.", "interesting"),
                    ChatMemoryReview.Item("demo-m2", "Lives in Berlin.", "system"),
                    ChatMemoryReview.Item("demo-m3", "Prefers the 7 pm slot for calls.", "system"),
                    ChatMemoryReview.Item("demo-m4", "A fourth row, which the card drops.", "system"),
                ),
            ),
        ),
        fallbackText = "",
    )

    /** A type this client does not draw: it keeps the line the backend synthesized for it. */
    val unknownBlock: ChatBlock = ChatBlock(
        id = "demo-b-unknown", kind = ChatBlock.Kind.Other("quantumLeap"), fallbackText = "Chat item - Quantum leap - Up",
    )

    val dayText: String = "1. Walked to the lake with Anna\n2. Finished the Q4 deck\n3. Booked the flight to Berlin"
}
