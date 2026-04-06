#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"missing expected block for {label}")
    return text.replace(old, new, 1)


def patch_onboarding_view(path: Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "  var onComplete: (() -> Void)? = nil\n",
        "  var onComplete: (() -> Void)? = nil\n  var exportStepOverride: Int? = nil\n  var isExportPreview = false\n",
        "onboarding view vars",
    )
    text = replace_once(
        text,
        "        if appState.hasCompletedOnboarding {\n",
        "        if appState.hasCompletedOnboarding && !isExportPreview {\n",
        "completed onboarding guard",
    )
    text = replace_once(
        text,
        """      currentStep = OnboardingFlow.migratedStep(
        currentStep: currentStep,
        hasMigratedVideoStep: hasMigratedOnboardingSteps,
        hasInsertedVoiceShortcutStep: hasInsertedVoiceShortcutStep,
        hasMergedVoiceInputStep: hasMergedVoiceInputStep,
        hasRemovedNotificationStep: hasRemovedNotificationStep,
        hasInsertedFloatingBarShortcutStep: hasInsertedFloatingBarShortcutStep,
        hasMigratedPagedIntro: hasMigratedPagedIntro,
        hasReorderedTrustStep: hasReorderedTrustStep,
        hasInsertedHowDidYouHearStep: hasInsertedHowDidYouHearStep
      )
""",
        """      if let exportStepOverride {
        currentStep = exportStepOverride
      } else {
        currentStep = OnboardingFlow.migratedStep(
          currentStep: currentStep,
          hasMigratedVideoStep: hasMigratedOnboardingSteps,
          hasInsertedVoiceShortcutStep: hasInsertedVoiceShortcutStep,
          hasMergedVoiceInputStep: hasMergedVoiceInputStep,
          hasRemovedNotificationStep: hasRemovedNotificationStep,
          hasInsertedFloatingBarShortcutStep: hasInsertedFloatingBarShortcutStep,
          hasMigratedPagedIntro: hasMigratedPagedIntro,
          hasReorderedTrustStep: hasReorderedTrustStep,
          hasInsertedHowDidYouHearStep: hasInsertedHowDidYouHearStep
        )
      }
""",
        "export step override",
    )
    text = replace_once(
        text,
        "      introCoordinator.prepare(appState: appState)\n",
        "      if !isExportPreview {\n        introCoordinator.prepare(appState: appState)\n      }\n",
        "intro coordinator guard",
    )
    text = replace_once(
        text,
        "    .task {\n      // Pre-warm the ACP bridge before the chat step starts.\n",
        "    .task {\n      guard !isExportPreview else { return }\n      // Pre-warm the ACP bridge before the chat step starts.\n",
        "task guard",
    )
    view_call_replacements = [
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 4, stepName: "ScreenRecording_Skipped")
            currentStep = 5
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 4, stepName: "ScreenRecording_Skipped")
            currentStep = 5
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "screen recording export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 5, stepName: "FullDiskAccess_Skipped")
            currentStep = 6
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 5, stepName: "FullDiskAccess_Skipped")
            currentStep = 6
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "disk access export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 6, stepName: "FileScan_Skipped")
            currentStep = 7
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 6, stepName: "FileScan_Skipped")
            currentStep = 7
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "file scan export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 7, stepName: "Microphone_Skipped")
            currentStep = 8
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 7, stepName: "Microphone_Skipped")
            currentStep = 8
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "microphone export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 8, stepName: "Notifications_Skipped")
            currentStep = 9
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 8, stepName: "Notifications_Skipped")
            currentStep = 9
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "notifications export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 9, stepName: "Accessibility_Skipped")
            currentStep = 10
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 9, stepName: "Accessibility_Skipped")
            currentStep = 10
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "accessibility export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 10, stepName: "Automation_Skipped")
            currentStep = 11
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(step: 10, stepName: "Automation_Skipped")
            currentStep = 11
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "automation export preview arg",
        ),
        (
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 11, stepName: "FloatingBarShortcut_Skipped")
            currentStep = 12
          },
          onForceComplete: handleOnboardingComplete
        )
""",
            """          onSkip: {
            AnalyticsManager.shared.onboardingStepCompleted(
              step: 11, stepName: "FloatingBarShortcut_Skipped")
            currentStep = 12
          },
          onForceComplete: handleOnboardingComplete,
          isExportPreview: isExportPreview
        )
""",
            "floating bar shortcut export preview arg",
        ),
    ]
    for old, new, label in view_call_replacements:
        text = replace_once(text, old, new, label)
    path.write_text(text)


def patch_permission_view(path: Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "  let onContinue: () -> Void\n  let onSkip: () -> Void\n  let onForceComplete: (() -> Void)?\n",
        "  let onContinue: () -> Void\n  let onSkip: () -> Void\n  let onForceComplete: (() -> Void)?\n  var isExportPreview = false\n",
        "permission view vars",
    )
    text = replace_once(
        text,
        '          if permissionType == "full_disk_access", let email = coordinator.userEmail() {\n',
        '          if permissionType == "full_disk_access", !isExportPreview, let email = coordinator.userEmail() {\n',
        "full disk email guard",
    )
    text = replace_once(
        text,
        "      .onReceive(timer) { _ in\n        refreshPermissionState()\n",
        "      .onReceive(timer) { _ in\n        guard !isExportPreview else { return }\n        refreshPermissionState()\n",
        "timer guard",
    )
    text = replace_once(
        text,
        "      .onChange(of: scenePhase) { _, newPhase in\n        guard newPhase == .active else { return }\n",
        "      .onChange(of: scenePhase) { _, newPhase in\n        guard !isExportPreview else { return }\n        guard newPhase == .active else { return }\n",
        "scene phase guard",
    )
    text = replace_once(
        text,
        "      .onChange(of: isGranted) { _, granted in\n        if granted {\n",
        "      .onChange(of: isGranted) { _, granted in\n        guard !isExportPreview else { return }\n        if granted {\n",
        "granted guard",
    )
    text = replace_once(
        text,
        "        coordinator.clearLastActionError()\n        refreshPermissionState()\n",
        "        coordinator.clearLastActionError()\n        guard !isExportPreview else { return }\n        refreshPermissionState()\n",
        "onAppear guard",
    )
    text = replace_once(
        text,
        "  private var isGranted: Bool {\n    coordinator.isPermissionGranted(permissionType, appState: appState)\n  }\n",
        "  private var isGranted: Bool {\n    guard !isExportPreview else { return false }\n    return coordinator.isPermissionGranted(permissionType, appState: appState)\n  }\n",
        "isGranted guard",
    )
    text = replace_once(
        text,
        "  private func refreshPermissionState() {\n    coordinator.refreshPermissions(appState: appState)\n",
        "  private func refreshPermissionState() {\n    guard !isExportPreview else { return }\n    coordinator.refreshPermissions(appState: appState)\n",
        "refresh guard",
    )
    path.write_text(text)


def patch_file_scan_view(path: Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "  let onContinue: () -> Void\n  let onSkip: () -> Void\n  let onForceComplete: (() -> Void)?\n",
        "  let onContinue: () -> Void\n  let onSkip: () -> Void\n  let onForceComplete: (() -> Void)?\n  var isExportPreview = false\n",
        "file scan vars",
    )
    text = replace_once(text, "            Text(coordinator.scanStatusText)\n", "            Text(scanStatusText)\n", "scan status")
    text = replace_once(
        text,
        "            if let snapshot = coordinator.scanSnapshot {\n",
        "            if let snapshot = scanSnapshot {\n",
        "scan snapshot text",
    )
    text = replace_once(
        text,
        "        if coordinator.scanSnapshot != nil {\n",
        "        if scanSnapshot != nil {\n",
        "scan snapshot continue",
    )
    text = replace_once(
        text,
        "      .task {\n        await coordinator.startFileScanIfNeeded(appState: appState)\n",
        "      .task {\n        guard !isExportPreview else { return }\n        await coordinator.startFileScanIfNeeded(appState: appState)\n",
        "file scan task guard",
    )
    text = replace_once(
        text,
        """  private var scanProgress: Double {
    switch coordinator.scanState {
""",
        """  private var scanSnapshot: OnboardingPagedIntroCoordinator.ScanSnapshot? {
    if isExportPreview {
      return .init(
        fileCount: 1_284,
        projectNames: [],
        applications: [],
        technologies: [],
        recentFiles: []
      )
    }
    return coordinator.scanSnapshot
  }

  private var scanStatusText: String {
    isExportPreview ? "Scanning your projects and apps..." : coordinator.scanStatusText
  }

  private var scanProgress: Double {
    if isExportPreview {
      return 0.82
    }
    switch coordinator.scanState {
""",
        "file scan helpers",
    )
    path.write_text(text)


def patch_floating_bar_shortcut_view(path: Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "    var onComplete: () -> Void\n    var onSkip: () -> Void\n    var onForceComplete: (() -> Void)?\n",
        "    var onComplete: () -> Void\n    var onSkip: () -> Void\n    var onForceComplete: (() -> Void)?\n    var isExportPreview = false\n",
        "floating bar vars",
    )
    text = replace_once(
        text,
        "        .onAppear {\n            GlobalShortcutManager.shared.unregisterShortcuts()\n",
        "        .onAppear {\n            guard !isExportPreview else { return }\n            GlobalShortcutManager.shared.unregisterShortcuts()\n",
        "floating bar onAppear guard",
    )
    text = replace_once(
        text,
        "        .onDisappear {\n            removeKeyMonitors()\n",
        "        .onDisappear {\n            guard !isExportPreview else { return }\n            removeKeyMonitors()\n",
        "floating bar onDisappear guard",
    )
    path.write_text(text)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_export_preview_overrides.py <sources-dir>", file=sys.stderr)
        return 1

    sources_dir = Path(sys.argv[1])
    patch_onboarding_view(sources_dir / "OnboardingView.swift")
    patch_permission_view(sources_dir / "OnboardingPermissionStepView.swift")
    patch_file_scan_view(sources_dir / "OnboardingFileScanStepView.swift")
    patch_floating_bar_shortcut_view(sources_dir / "OnboardingFloatingBarShortcutStepView.swift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
