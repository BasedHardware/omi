import Foundation

@MainActor
final class AgentDelegationExecutor {
    static let shared = AgentDelegationExecutor()

    struct ResolvedAgentTask {
        let originalUserText: String
        let brief: String
        let title: String?
        let spokenAck: String?
        let directedProvider: AgentPillsManager.DirectedProvider?
        let harnessOverride: AgentHarnessMode?
        let validateAgainstOriginalUserText: Bool

        init(
            originalUserText: String,
            brief: String,
            title: String?,
            spokenAck: String?,
            directedProvider: AgentPillsManager.DirectedProvider?,
            harnessOverride: AgentHarnessMode? = nil,
            validateAgainstOriginalUserText: Bool = true
        ) {
            self.originalUserText = originalUserText
            self.brief = brief
            self.title = title
            self.spokenAck = spokenAck
            self.directedProvider = directedProvider
            self.harnessOverride = harnessOverride
            self.validateAgainstOriginalUserText = validateAgainstOriginalUserText
        }
    }

    private init() {}

    @discardableResult
    func spawnResolvedDelegation(
        _ task: ResolvedAgentTask,
        model: String,
        fromVoice: Bool
    ) -> AgentPill? {
        guard DelegationBriefValidator.isStructurallyAcceptable(
            brief: task.brief,
            rawIntent: task.validateAgainstOriginalUserText ? task.originalUserText : nil
        ) else {
            log("AgentDelegationExecutor: refused spawn with non-self-contained brief")
            return nil
        }
        return AgentPillsManager.shared.spawnFromUserQuery(
            task.brief,
            model: model,
            fromVoice: fromVoice,
            preFetchedTitle: task.title,
            preFetchedAck: task.spokenAck,
            bridgeHarnessOverride: task.harnessOverride ?? task.directedProvider?.harnessMode
        )
    }
}
