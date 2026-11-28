import OmiComponents
import OmiCore
import OmiService
import SwiftUI

/// Debug launch arguments for screenshots of the chat (inert outside Debug builds):
/// `-omiChatSearch <words>`, `-omiChatFilter approvals|drafts|jobs|files`, `-omiChatDraft <words>`
/// (in the composer, not sent; `\n` for a new line), `-omiChatDemoThread YES` (a made-up exchange on
/// this iPhone only), `-omiChatJumpTo <message id>` (scrolled up to that message, as from a search match),
/// `-omiChatDemoAsks message|contacts` (an "Omi asks" card under the newest answer; answers reach
/// no agent), `-omiChatDemoCards YES` (a connect card, a task card and source chips on the newest
/// answer), `-omiChatDemoBlocks YES` (a made-up exchange carrying one of every content block, plus
/// the task row its task card points at), `-omiChatRunTask <task id or "first">` (Omi takes over
/// that task, for "Running now").
extension ChatScreen {
    func debugLaunch() async {
        #if DEBUG
            if let words = DebugLaunch.string("omiChatSearch") {
                isSearching = true
                query = words
            }
            if let name = DebugLaunch.string("omiChatFilter"), let value = ChatThreadFilter(rawValue: name) {
                isSearching = true
                filter = value
            }
            if let words = DebugLaunch.string("omiChatDraft") {
                draft = words.replacingOccurrences(of: "\\n", with: "\n")
            }
            await debugDemos()
            if let id = DebugLaunch.string("omiChatRunTask") {
                // "first": the newest open task (a fresh test account's ids are not known up front).
                let pick = { tasks.tasks.first { id == "first" ? !$0.isCompleted : $0.id == id } }
                for _ in 0 ..< 50 where pick() == nil {
                    if tasks.tasks.isEmpty { await tasks.load() }
                    try? await Task.sleep(for: .milliseconds(200))
                }
                guard let task = pick() else { return }
                await agent.takeOver(task, conversationTitle: nil)
            }
        #endif
    }

    #if DEBUG
        /// The made-up thread, cards and question (local only), then scrolled to a message.
        private func debugDemos() async {
            let wantsDemo = DebugLaunch.string("omiChatDemoAsks") != nil || DebugLaunch.flag("omiChatDemoBlocks")
                || DebugLaunch.flag("omiChatDemoCards") || DebugLaunch.flag("omiChatDemoThread")
            if wantsDemo {
                for _ in 0 ..< 50 where !chat.hasLoaded {
                    try? await Task.sleep(for: .milliseconds(100))
                }
            }
            if DebugLaunch.flag("omiChatDemoThread") { chat.showDemoThread() }
            if DebugLaunch.flag("omiChatDemoBlocks") {
                // The task card resolves against the real list, so the list comes first: a load
                // after the demo row would take the row with it.
                await tasks.load()
                chat.showDemoBlocks(tasks: tasks)
            }
            if DebugLaunch.flag("omiChatDemoCards") { chat.showDemoCards() }
            if let kind = DebugLaunch.string("omiChatDemoAsks") { chat.showDemoQuestion(Self.demoQuestion(kind)) }
            if let id = DebugLaunch.string("omiChatJumpTo") {
                // Once the thread has settled at its end: scrolled up to that message, as from a search match.
                try? await Task.sleep(for: .seconds(1.5))
                jumpTarget = id
            }
        }

        static func demoQuestion(_ kind: String) -> PendingDeviceTool {
            let anna = DeviceContact(
                id: "demo-anna", name: "Anna Schmidt", phoneNumbers: [.init(label: "mobile", value: "+49 170 1234567")],
                emailAddresses: [], preferredHandle: "+49 170 1234567"
            )
            let annabel = DeviceContact(id: "demo-annabel", name: "Annabel Lee", phoneNumbers: [], emailAddresses: [], preferredHandle: "")
            if kind == "contacts" {
                return PendingDeviceTool(
                    taskID: "", taskTitle: "",
                    request: DeviceToolRequest(id: "demo-chat-call", toolName: "search_contacts", query: "Anna"), matches: [anna, annabel]
                )
            }
            return PendingDeviceTool(
                taskID: "", taskTitle: "",
                request: DeviceToolRequest(
                    id: "demo-chat-call", toolName: "propose_message", recipients: ["Anna Schmidt"],
                    text: "Hi Anna, does Thursday at 7 pm still work for the follow-up?"
                )
            )
        }
    #endif
}
