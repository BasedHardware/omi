"""Shared ownership for the files consumed by desktop E2E flow validation."""

from __future__ import annotations

# Paths are relative to desktop/macos. Keep the flow lint reader and CI impact
# resolver on this single list so an added bridge action cannot skip its flow
# validation route.
ACTION_SOURCE_RELATIVE_PATHS = (
    "Desktop/Sources/DesktopAutomationBridge.swift",
    "Desktop/Sources/FloatingControlBar/RealtimeHubController.swift",
    "Desktop/Sources/Rewind/Core/RewindArtifactGauntlet.swift",
    "Desktop/Sources/DesktopAutomationOpenOmiShortcutQA.swift",
    "Desktop/Sources/ProactiveAssistants/ContextBucketDirectorProbeRegistration.swift",
    "Desktop/Sources/Automation/DesktopAutomationHomeStageActions.swift",
    "Desktop/Sources/MainWindow/Pages/TasksPage.swift",
    "Desktop/Sources/MainWindow/Pages/MemoriesPage.swift",
)

FLOW_LINT_INPUTS = frozenset(
    {
        "desktop/macos/scripts/desktop-core-harness.sh",
        "desktop/macos/scripts/desktop-flow-lint.py",
        "desktop/macos/scripts/desktop_flow_contract.py",
        *(f"desktop/macos/{path}" for path in ACTION_SOURCE_RELATIVE_PATHS),
    }
)
