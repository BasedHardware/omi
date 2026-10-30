#if DEBUG
    import Foundation
    import OmiCore

    /// Debug builds: the thread a screenshot needs to show every block card, and the task row the
    /// task card resolves against. In memory for this launch only: nothing is sent, nothing is
    /// stored, and the next load of the real thread replaces it (`-omiChatDemoBlocks YES`).
    public extension ChatStore {
        /// The ids the demo cards point at.
        enum DemoBlock {
            static let task = "demo-block-task"
            static let goal = "demo-block-goal"
            static let memory = "demo-block-memory"
            static let conversation = "demo-block-conversation"
        }

        /// The demo thread. Call it once the real task list has loaded: a task card resolves
        /// against that list, and a later load would take the demo row with it.
        func showDemoBlocks(tasks: TasksStore) {
            seedDemoTask(tasks)
            let start = Date.now.addingTimeInterval(-35 * 60)
            func at(_ minutes: Double) -> Date {
                start.addingTimeInterval(minutes * 60)
            }
            func staged(
                _ id: String, _ minutes: Double, _ blocks: [ChatBlock],
                kind: ChatMessage.Kind = .text, text: String? = nil
            ) -> ChatMessage {
                var message = ChatMessage(
                    id: id, text: text ?? ChatBlockLayout.structuredFallback(blocks),
                    sender: .omi, createdAt: at(minutes)
                )
                message.blocks = blocks
                message.kind = kind
                return message
            }
            messages += [
                staged("demo-blk-1", 0, Self.workBlocks),
                staged("demo-blk-2", 1, [Self.askBlock(answeredBy: nil)]),
                staged("demo-blk-3", 2, [Self.askBlock(answeredBy: "demo-o1")]),
                staged("demo-blk-4", 3, Self.runBlocks),
                staged("demo-blk-5", 4, [Self.discoveryBlock]),
                // The review card draws its own heading, so this turn carries no body of its own.
                staged("demo-blk-6", 5, [Self.reviewBlock], text: ""),
                staged("demo-blk-7", 6, [], kind: .daySummary, text: Self.dayText),
                staged("demo-blk-8", 7, [Self.unknownBlock], text: Self.unknownBlock.fallbackText),
            ]
        }

        private func seedDemoTask(_ tasks: TasksStore) {
            tasks.tasks.insert(
                ActionItem(
                    id: DemoBlock.task, description: "Send Anna the Thursday follow-up", isCompleted: false,
                    dueAt: Date.now.addingTimeInterval(2 * 86400), conversationID: nil, owner: .user,
                    workstreamID: nil, createdAt: Date.now.addingTimeInterval(-3600)
                ),
                at: 0
            )
        }

        // MARK: the blocks

        /// What the answer did: one card per kind that points somewhere.
        static var workBlocks: [ChatBlock] {
            [
                ChatBlock(
                    id: "demo-b-task", kind: .task(taskID: DemoBlock.task),
                    fallbackText: "Task - Send Anna the Thursday follow-up"
                ),
                ChatBlock(
                    id: "demo-b-goal", kind: .goal(goalID: DemoBlock.goal, summary: "Run 10 km"),
                    fallbackText: "Goal - Run 10 km"
                ),
                ChatBlock(
                    id: "demo-b-memory", kind: .memory(memoryID: DemoBlock.memory, summary: "Anna leads the Q4 launch"),
                    fallbackText: "Memory - Anna leads the Q4 launch"
                ),
                ChatBlock(
                    id: "demo-b-conversation",
                    kind: .conversation(
                        conversationID: DemoBlock.conversation, summary: "Q4 roadmap with Anna",
                        actionItems: [
                            .init(description: "Send Anna the draft deck", taskID: DemoBlock.task),
                            .init(description: "Ask Ben for the pricing numbers", taskID: nil),
                        ],
                        isCapture: false
                    ),
                    fallbackText: "Meeting notes ready - Q4 roadmap with Anna"
                ),
                ChatBlock(
                    id: "demo-b-capture",
                    kind: .conversation(
                        conversationID: DemoBlock.conversation, summary: "Walk to the lake, 41 min",
                        actionItems: [], isCapture: true
                    ),
                    fallbackText: "Recording ready - Walk to the lake"
                ),
            ]
        }

        /// Omi's question with the answers it prepared. The third option has no prepared answer:
        /// it is a label, not a button.
        static func askBlock(answeredBy selected: String?) -> ChatBlock {
            ChatBlock(
                id: "demo-b-question",
                kind: .question(ChatQuestion(
                    questionID: "demo-q1", text: "Which slot should I book for the follow-up?",
                    options: [
                        .init(id: "demo-o1", label: "Thursday 7 pm", preparedAnswer: "Book the follow-up for Thursday at 7 pm"),
                        .init(id: "demo-o2", label: "Friday 9 am", preparedAnswer: "Book the follow-up for Friday at 9 am"),
                        .init(id: "demo-o3", label: "Another time", preparedAnswer: ""),
                    ],
                    selectedOptionID: selected
                )),
                fallbackText: "Question - Which slot should I book for the follow-up?"
            )
        }

        /// Three background runs: one still going, one that finished, one that failed.
        static var runBlocks: [ChatBlock] {
            [
                ChatBlock(
                    id: "demo-b-run",
                    kind: .agentRun(title: "Check the flight prices", detail: "Watching BER to LIS for a week", status: .running),
                    fallbackText: "Started - Check the flight prices"
                ),
                ChatBlock(
                    id: "demo-b-done",
                    kind: .agentRun(title: "Book the room", detail: "Booked, confirmation in your mail", status: .completed),
                    fallbackText: "Done - Book the room"
                ),
                ChatBlock(
                    id: "demo-b-failed",
                    kind: .agentRun(title: "Order the poster", detail: "The shop refused the payment method", status: .failed),
                    fallbackText: "Failed - Order the poster"
                ),
            ]
        }

        static var discoveryBlock: ChatBlock {
            ChatBlock(
                id: "demo-b-discovery",
                kind: .discovery(
                    title: "Café Kranzler",
                    summary: "Two doors down from the office, open until 11 pm.",
                    fullText: "Two doors down from the office, open until 11 pm. Quiet in the morning, full after six. "
                        + "They take reservations for groups of five or more."
                ),
                fallbackText: "Discovery - Café Kranzler - Two doors down from the office"
            )
        }

        static var reviewBlock: ChatBlock {
            ChatBlock(
                id: "demo-b-review",
                kind: .memoryReview(ChatMemoryReview(
                    summaryID: "demo-summary", date: "2026-10-12",
                    items: [
                        .init(memoryID: "demo-m1", content: "Anna leads the Q4 launch.", category: "interesting"),
                        .init(memoryID: "demo-m2", content: "Lives in Berlin.", category: "system"),
                        .init(memoryID: "demo-m3", content: "Prefers the 7 pm slot for calls.", category: "system"),
                        .init(memoryID: "demo-m4", content: "A fourth row, which the card drops.", category: "system"),
                    ]
                )),
                fallbackText: ""
            )
        }

        /// A type this client does not draw: it keeps the line the backend synthesized for it.
        static var unknownBlock: ChatBlock {
            ChatBlock(id: "demo-b-unknown", kind: .other(type: "quantumLeap"), fallbackText: "Chat item - Quantum leap - Up")
        }

        static var dayText: String {
            "1. Walked to the lake with Anna\n2. Finished the Q4 deck\n3. Booked the flight to Berlin"
        }
    }
#endif
