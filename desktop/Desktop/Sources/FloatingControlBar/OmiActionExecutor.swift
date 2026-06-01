import AppKit

@MainActor
final class OmiActionExecutor {
    static let shared = OmiActionExecutor()
    private let driver: OmiActionDriver = CuaActionDriver()
    private var runningTask: Task<Void, Never>?
    private init() {}

    func execute(plan: OmiWorkflowPlan, transcript: String) {
        // Cancel any in-flight plan before starting a new one
        runningTask?.cancel()

        runningTask = Task {
            await runPlan(plan, transcript: transcript)
        }
    }

    func cancel() {
        runningTask?.cancel()
        runningTask = nil
        OmiEscapeMonitor.shared.disarm()
        CursorPTTOverlayManager.shared.cancelExecution()
        OmiPlanWindow.shared.cancelExecution()
        log("OmiActionExecutor: plan cancelled")
    }

    // MARK: - Private

    private func runPlan(_ plan: OmiWorkflowPlan, transcript: String) async {
        let resolved = OmiContextResolver.shared.resolve(plan, transcript: transcript)

        OmiEscapeMonitor.shared.arm { [weak self] in
            Task { @MainActor in self?.cancel() }
        }

        CursorPTTOverlayManager.shared.startExecution()
        OmiPlanWindow.shared.startExecution(
            planDescription: resolved.description,
            steps: resolved.steps.map { $0.stepDescription }
        )
        log("OmiActionExecutor: starting plan '\(resolved.description)' with \(resolved.steps.count) step(s)")

        var failedIndex: Int?
        for (index, step) in resolved.steps.enumerated() {
            guard !Task.isCancelled else { break }

            OmiPlanWindow.shared.updateStep(index: index)
            log("OmiActionExecutor: step \(index + 1)/\(resolved.steps.count) — \(step.stepDescription)")

            do {
                try await executeStep(step)
            } catch {
                log("OmiActionExecutor: step failed — \(error.localizedDescription)")
                failedIndex = index
                break
            }

            // Brief settle between steps — gives the previous action's UI
            // transition (menu open, window switch) time to land.
            if index < resolved.steps.count - 1 {
                try? await Task.sleep(for: .milliseconds(350))
            }
        }

        OmiEscapeMonitor.shared.disarm()
        if !Task.isCancelled {
            if let failedIndex {
                OmiPlanWindow.shared.markStepFailed(index: failedIndex)
            } else {
                OmiPlanWindow.shared.finishExecution()
            }
            CursorPTTOverlayManager.shared.finishExecution()
            log("OmiActionExecutor: plan complete")
        }
        runningTask = nil
    }

    private func executeStep(_ step: OmiWorkflowStep) async throws {
        switch step.action {
        case .click:
            let label = step.target ?? step.value ?? ""
            guard !label.isEmpty else { return }
            guard let result = await OmiElementResolver.shared.resolve(label: label) else {
                throw OmiActionDriverError.elementNotFound(label: label)
            }
            try await driver.click(at: result.point, targetApp: result.app)

        case .type:
            let text = step.value ?? ""
            try await driver.type(text: text, targetApp: nil)

        case .shortcut:
            let keys = step.value ?? ""
            try await driver.pressShortcut(keys, targetApp: nil)

        case .scroll:
            let direction = step.scrollDirection ?? "down"
            let amount = step.scrollAmount ?? 3
            try await driver.scroll(direction: direction, amount: amount, targetApp: nil)

        case .openApp:
            let name = step.value ?? step.target ?? ""
            guard !name.isEmpty else { return }
            try await driver.openApp(named: name)
        }
    }
}
