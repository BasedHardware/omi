"""Shared ownership for the files consumed by desktop E2E flow validation."""

from __future__ import annotations

# Paths are relative to desktop/macos. Keep the flow lint reader and CI impact
# resolver on this single list so an added bridge action cannot skip its flow
# validation route.
ACTION_SOURCE_RELATIVE_PATHS = (
    "Desktop/Sources/DesktopAutomationBridge.swift",
    # The bridge is split across extension files. Each one registers actions the
    # flow lint must be able to see; omitting one makes its actions look unknown
    # and reports a valid flow as broken, which is what happened to
    # notifications-settings.yaml when +Notifications.swift was factored out.
    "Desktop/Sources/DesktopAutomationBridge+Notifications.swift",
    "Desktop/Sources/DesktopAutomationBridge+ChatFirst.swift",
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
