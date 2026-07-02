import Foundation

/// Task categories the selector reasons about (mirrors agent-selector.ts).
enum AgentTaskCategory: String, CaseIterable {
    case codebaseEdit
    case shellOps
    case research
    case longAutonomous
    case messaging
    case general
}

/// Capability-based "best agent" selector for the desktop.
///
/// This is the Swift-side counterpart of `desktop/macos/agent/src/runtime/agent-selector.ts`
/// (the reserved Scheduler/capability broker from docs/developer/agent-control-plane.mdx). It
/// picks the best CONNECTED agent for a spoken/typed task and returns an ordered fallback chain,
/// so the voice path no longer just defaults to Omi AI. Explicit "use <agent>" requests are handled
/// upstream by `AgentPillsManager.DirectedProvider`; this selector runs only when no agent was named.
///
/// Kept pure and deterministic so it is fully unit-testable without spawning anything. Scores are
/// intentionally identical to the TypeScript selector.
enum AgentSelector {
    /// Capability scores 0...3 per (harness, category). Higher is a better fit.
    ///  - Claude Code (acp) / Codex: strongest at code edits + shell; Codex leads raw shell/exec.
    ///  - Hermes / OpenClaw: multi-channel + long-running/scheduled autonomy + messaging.
    ///  - Omi AI (pi-mono): the always-available general default and safety net.
    private static let scores: [AgentHarnessMode: [AgentTaskCategory: Int]] = [
        .acp: [.codebaseEdit: 3, .shellOps: 2, .research: 2, .longAutonomous: 2, .messaging: 0, .general: 3],
        .codex: [.codebaseEdit: 3, .shellOps: 3, .research: 1, .longAutonomous: 2, .messaging: 0, .general: 2],
        .hermes: [.codebaseEdit: 2, .shellOps: 2, .research: 2, .longAutonomous: 3, .messaging: 3, .general: 2],
        .openclaw: [.codebaseEdit: 2, .shellOps: 2, .research: 2, .longAutonomous: 3, .messaging: 3, .general: 2],
        .piMono: [.codebaseEdit: 2, .shellOps: 2, .research: 2, .longAutonomous: 1, .messaging: 1, .general: 3],
    ]

    /// Deterministic tiebreak order when scores are equal and no user default applies.
    private static let defaultPriority: [AgentHarnessMode] = [.acp, .codex, .hermes, .openclaw, .piMono]

    static func score(_ harness: AgentHarnessMode, for category: AgentTaskCategory) -> Int {
        scores[harness]?[category] ?? 0
    }

    /// Rule-based task classifier. Mirrors the TypeScript classifier's ordering and keywords.
    static func classify(_ taskText: String) -> AgentTaskCategory {
        let t = taskText.lowercased()
        func has(_ words: [String]) -> Bool { words.contains { t.contains($0) } }

        if has([
            "message", "text ", "reply", "respond to", "dm ", "whatsapp", "telegram",
            "imessage", "signal", "slack", "discord",
        ]) {
            return .messaging
        }
        if has([
            "overnight", "keep working", "keep going", "monitor", "every hour", "on a schedule",
            "scheduled", "while i sleep", "long-running", "autonomously", "in the background",
        ]) {
            return .longAutonomous
        }
        if has(["research", "look up", "find out", "search the web", "investigate", "gather info", "summarize the"]) {
            return .research
        }
        if has([
            "run ", "shell", "command", "terminal", "install", "npm ", "pip ", "git ",
            "build ", "compile", "deploy", "docker",
        ]) {
            return .shellOps
        }
        if has([
            "code", "refactor", "implement", "fix the", "bug", "function", "class ", "test",
            "repo", "file", "edit ", "write a", "add a", "feature", "endpoint",
        ]) {
            return .codebaseEdit
        }
        return .general
    }

    /// Rank the available harnesses for a task, best first. Returns an ordered fallback chain.
    /// `available` should include only connected agents; `userDefault` is used only as a tiebreak.
    static func rank(
        brief: String,
        available: [AgentHarnessMode],
        userDefault: AgentHarnessMode? = nil,
        category: AgentTaskCategory? = nil
    ) -> [AgentHarnessMode] {
        let taskCategory = category ?? classify(brief)
        // De-duplicate while preserving determinism.
        var seen = Set<AgentHarnessMode>()
        let unique = available.filter { seen.insert($0).inserted }
        return unique.sorted { a, b in
            let sa = score(a, for: taskCategory)
            let sb = score(b, for: taskCategory)
            if sa != sb { return sa > sb }
            if let userDefault {
                if a == userDefault { return true }
                if b == userDefault { return false }
            }
            let ia = defaultPriority.firstIndex(of: a) ?? Int.max
            let ib = defaultPriority.firstIndex(of: b) ?? Int.max
            return ia < ib
        }
    }

    /// The single best connected agent for a task, or `nil` when nothing is connected
    /// (caller then falls back to the Omi AI default).
    static func best(
        brief: String,
        available: [AgentHarnessMode],
        userDefault: AgentHarnessMode? = nil
    ) -> AgentHarnessMode? {
        rank(brief: brief, available: available, userDefault: userDefault).first
    }
}
