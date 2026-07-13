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
        let originSurface: DesktopCoordinatorOriginSurface
        let harnessOverride: AgentHarnessMode?
        let validateAgainstOriginalUserText: Bool

        init(
            originalUserText: String,
            brief: String,
            title: String?,
            spokenAck: String?,
            directedProvider: AgentPillsManager.DirectedProvider?,
            originSurface: DesktopCoordinatorOriginSurface,
            harnessOverride: AgentHarnessMode? = nil,
            validateAgainstOriginalUserText: Bool = true
        ) {
            self.originalUserText = originalUserText
            self.brief = brief
            self.title = title
            self.spokenAck = spokenAck
            self.directedProvider = directedProvider
            self.originSurface = originSurface
            self.harnessOverride = harnessOverride
            self.validateAgainstOriginalUserText = validateAgainstOriginalUserText
        }
    }

    private init() {}

    @discardableResult
    func spawnResolvedDelegation(
        _ task: ResolvedAgentTask,
        model: String,
        fromVoice: Bool,
        producerJournalIntent: AgentPillProducerJournalIntent
    ) async throws -> AgentPill? {
        guard DelegationBriefValidator.isStructurallyAcceptable(
            brief: task.brief,
            rawIntent: task.validateAgainstOriginalUserText ? task.originalUserText : nil
        ) else {
            log("AgentDelegationExecutor: refused spawn with non-self-contained brief")
            return nil
        }
        return try await withCheckedThrowingContinuation { continuation in
            _ = AgentPillsManager.shared.spawn(
                query: task.brief,
                model: model,
                originSurface: task.originSurface,
                fromVoice: fromVoice,
                preFetchedTitle: task.title,
                preFetchedAck: task.spokenAck,
                bridgeHarnessOverride: task.harnessOverride ?? task.directedProvider?.harnessMode,
                producerJournalIntent: producerJournalIntent,
                onAccepted: { result in
                    switch result {
                    case .success(let pill): continuation.resume(returning: pill)
                    case .failure(let error): continuation.resume(throwing: error)
                    }
                }
            )
        }
    }
}
