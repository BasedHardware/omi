"""Shared ownership for the files consumed by desktop E2E flow validation."""

from __future__ import annotations

from pathlib import Path

_DESKTOP_MACOS_DIR = Path(__file__).resolve().parent.parent
_SOURCES_DIR = _DESKTOP_MACOS_DIR / "Desktop" / "Sources"


def _bridge_action_sources() -> tuple[str, ...]:
    """Every `DesktopAutomationBridge*.swift`, found rather than listed.

    Naming the base file alone is what let this list go stale: bridge actions moved into
    `DesktopAutomationBridge+Notifications.swift`, nobody added it here, and the lint then
    reported the flows that used them as referencing unknown actions — failing the push gate
    on every branch while the actions themselves were registered correctly all along.

    Discovery is scoped to this one filename prefix on purpose. The registration pattern the
    lint matches (`name: "…"`) is common enough to appear in `APIClient`, `AuthService` and
    `ChatBubble`, so scanning the whole tree would feed the lint action names that are not
    actions. The prefix belongs to the bridge and nothing else.
    """
    return tuple(
        sorted(
            path.relative_to(_DESKTOP_MACOS_DIR).as_posix()
            for path in _SOURCES_DIR.glob("DesktopAutomationBridge*.swift")
        )
    )


# Paths are relative to desktop/macos. Keep the flow lint reader and CI impact
# resolver on this single list so an added bridge action cannot skip its flow
# validation route.
ACTION_SOURCE_RELATIVE_PATHS = _bridge_action_sources() + (
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
