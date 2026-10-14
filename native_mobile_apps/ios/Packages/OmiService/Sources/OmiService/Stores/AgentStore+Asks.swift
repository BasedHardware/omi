import Foundation
import OmiCore
import OmiNetwork

/// "Omi asks": device tool calls during a run (`DeviceToolResolver`). The agent's stream waits
/// while the user decides; nothing is sent, shared or allowed without their tap.
public extension AgentStore {
    /// A `tool:` frame: answered at once when there is nothing to ask (malformed, unsupported),
    /// else it waits for the user as "Omi asks". The agent's stream waits meanwhile.
    internal func ask(_ request: DeviceToolRequest, for task: ActionItem) async {
        log?.add(.info, "agent", "run \(task.id) asks \(request.toolName) call \(request.id)")
        if let immediate = DeviceToolResolver.immediateResult(for: request, performer: deviceTools) {
            await post(immediate, for: request)
            return
        }
        guard let deviceTools else { return }
        let pending = await DeviceToolResolver.prepare(request, taskID: task.id, taskTitle: task.description, performer: deviceTools)
        deviceToolRequests[task.id] = pending
        runs[task.id]?.lastProgressAt = now()
        onDeviceToolRequest?(pending)
    }

    /// The user's tap on "Omi asks". Nothing is sent, shared or allowed without it; a message
    /// only opens the system composer, where the user sends it themselves.
    func answer(_ pending: PendingDeviceTool, _ choice: DeviceToolChoice) async {
        guard var current = deviceToolRequests[pending.taskID], current.id == pending.id else { return }
        // Off the card while the system sheet is up, so a second tap cannot answer twice.
        deviceToolRequests[pending.taskID] = nil
        let result: DeviceToolResult? = if let deviceTools {
            await DeviceToolResolver.result(for: &current, choice: choice, performer: deviceTools)
        } else {
            .failure("surface_unavailable", "This device cannot run tools right now.")
        }
        guard let result else {
            // Contacts allowed: the matches show and the user still picks one.
            if runs[pending.taskID]?.isActive == true { deviceToolRequests[pending.taskID] = current }
            return
        }
        await post(result, for: current.request)
    }

    private func post(_ result: DeviceToolResult, for request: DeviceToolRequest) async {
        do {
            try await api.sendDeviceToolResult(callID: request.id, result: result)
            log?.add(.info, "agent", "tool \(request.toolName) call \(request.id): ok=\(result.ok) \(result.status ?? result.reason ?? "")")
        } catch {
            // The agent stopped waiting (timeout or the turn ended); it answers without it.
            log?.add(.warning, "agent", "tool \(request.toolName) call \(request.id) result not taken: \(error)")
        }
    }

    #if DEBUG
        /// Debug builds: an "Omi asks" card without a run (screenshots). Answers reach no agent.
        func showDemoQuestion(_ pending: PendingDeviceTool) {
            deviceToolRequests[pending.taskID] = pending
        }
    #endif
}
