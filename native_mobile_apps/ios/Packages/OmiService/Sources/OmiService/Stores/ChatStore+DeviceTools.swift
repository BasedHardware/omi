import Foundation
import OmiCore
import OmiNetwork

/// "Omi asks" in the chat: the same device tool round trip as agent runs (`DeviceToolResolver`),
/// for the chat UI to render `pendingDeviceTool`. Nothing runs without the user's tap.
public extension ChatStore {
    /// The user's answer to the pending call.
    func answerDeviceTool(_ choice: DeviceToolChoice) async {
        guard var current = pendingDeviceTool else { return }
        let messageID = pendingDeviceToolMessageID
        // Off the card while the system sheet is up, so a second tap cannot answer twice.
        pendingDeviceTool = nil
        let result: DeviceToolResult? = if let deviceTools {
            await DeviceToolResolver.result(for: &current, choice: choice, performer: deviceTools)
        } else {
            .failure("surface_unavailable", "This device cannot run tools right now.")
        }
        guard let result else {
            // Contacts allowed: the matches show and the user still picks one.
            if isStreaming, pendingDeviceToolMessageID == messageID { pendingDeviceTool = current }
            return
        }
        pendingDeviceToolMessageID = nil
        try? await api.sendDeviceToolResult(callID: current.request.id, result: result)
    }

    /// A `tool:` frame: answered at once when there is nothing to ask, else it waits under the
    /// answer as "Omi asks" (the agent's stream waits meanwhile).
    internal func receive(_ request: DeviceToolRequest, for messageID: String) {
        pendingDeviceToolMessageID = messageID
        Task {
            if let immediate = DeviceToolResolver.immediateResult(for: request, performer: deviceTools) {
                pendingDeviceToolMessageID = nil
                try? await api.sendDeviceToolResult(callID: request.id, result: immediate)
                return
            }
            guard let deviceTools else { return }
            let pending = await DeviceToolResolver.prepare(request, taskID: "", taskTitle: "", performer: deviceTools)
            // The turn may have ended while the phone looked up contacts.
            guard pendingDeviceToolMessageID == messageID, isStreaming else { return }
            pendingDeviceTool = pending
        }
    }

    #if DEBUG
        /// Debug builds: an "Omi asks" card under the newest answer without a turn (screenshots).
        /// Answers reach no agent.
        func showDemoQuestion(_ pending: PendingDeviceTool) {
            pendingDeviceToolMessageID = messages.last { $0.sender == .omi }?.id
            pendingDeviceTool = pending
        }
    #endif
}
