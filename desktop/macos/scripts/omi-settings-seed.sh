#!/bin/bash
# omi-settings-seed.sh — copy dev-experience preferences into a test bundle.
#
# This intentionally copies a curated allowlist instead of cloning the whole
# UserDefaults domain. Whole-domain copies drag along caches, counters, and
# per-bundle state that make named bundles harder to reason about.
#
# Usage: omi-settings-seed.sh <target-bundle-id> [source-bundle-id]
#   target-bundle-id  e.g. com.omi.omi-fix-rewind  (a named test bundle)
#   source-bundle-id  default: com.omi.desktop-dev   (the "Omi Dev" build)
#
# Set OMI_DEV_EAGER_PERMISSIONS=1 to preserve eager post-onboarding behavior
# for permission-flow parity testing.
set -euo pipefail

TARGET="${1:?usage: omi-settings-seed.sh <target-bundle-id> [source-bundle-id]}"
SRC="${2:-com.omi.desktop-dev}"

python3 - "$SRC" "$TARGET" <<'PY'
import plistlib
import os
import subprocess
import sys
import tempfile

src, target = sys.argv[1], sys.argv[2]

KEYS = [
    # Floating bar, Ask Omi, push-to-talk, voice, and model choices.
    "shortcut_askOmiKey",
    "shortcut_pttKey",
    "shortcut_askOmiEnabled",
    "shortcut_pttEnabled",
    "shortcut_doubleTapForLock",
    "shortcut_solidBackground",
    "shortcut_pttSoundsEnabled",
    "shortcut_pttMuteSystemAudio",
    "shortcut_selectedModel",
    "shortcut_pttTranscriptionMode",
    "shortcut_draggableBarEnabled",
    "shortcut_floatingBarTypedQuestionVoiceAnswersEnabled",
    "shortcut_voicePlaybackSpeed",
    "shortcut_selectedVoiceID",

    # Common desktop settings that make throwaway bundles feel like Omi Dev.
    "fontScale",
    "multiChatEnabled",
    "conversationsCompactView",
    "useLegacyHomeDesign",
    "chatBridgeMode",
    "realtimeOmniProvider",
    "askModeEnabled",
    "claudeMdEnabled",
    "projectClaudeMdEnabled",
    "devModeEnabled",
    "playwrightUseExtension",
    "disabledSkillsJSON",
    "screenAnalysisEnabled",
    "transcriptionEnabled",
    "disableSystemAudioCapture",
    "dashboardWidgetsCollapsed",
    "tasksChatPanelWidth",

    # Rewind capture preferences.
    "rewindRetentionDays",
    "rewindCaptureInterval",
    "rewindExcludedApps",
    "rewindRemovedDefaultApps",
    "rewindDisableContentCache",

    # Task agent preferences.
    "taskAgentEnabled",
    "taskChatAgentEnabled",
    "taskAgentAutoLaunch",
    "taskAgentPromptPrefix",
    "taskAgentDefaultPrompt",
    "taskAgentSkipPermissions",
]


def env_truthy(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def defaults_export(domain):
    proc = subprocess.run(
        ["defaults", "export", domain, "-"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    return plistlib.loads(proc.stdout)


source = defaults_export(src)
if not source:
    print(f"No defaults found for {src}; applying target-only dev defaults")

target_data = defaults_export(target)
selected = {key: source[key] for key in KEYS if key in source}

if not env_truthy("OMI_DEV_EAGER_PERMISSIONS"):
    # Named dev bundles reuse auth/onboarding from Omi Dev, but macOS treats
    # each bundle ID as a fresh TCC identity. Keep startup quiet until the
    # developer explicitly enables a feature that needs a permission.
    selected.update(
        {
            "devLazyPermissionsEnabled": True,
            "screenAnalysisEnabled": False,
            "transcriptionEnabled": False,
            "disableSystemAudioCapture": True,
            "systemAudioCaptureMode": "never",
            # Prevent the main-window startup migration from re-enabling screen
            # analysis immediately after the quiet default is seeded.
            "screenAnalysisAutoStartFixed_v2": True,
        }
    )
else:
    selected["devLazyPermissionsEnabled"] = False

target_data.update(selected)
with tempfile.NamedTemporaryFile(suffix=".plist") as plist:
    plistlib.dump(target_data, plist)
    plist.flush()
    subprocess.run(["defaults", "import", target, plist.name], check=True)

print(f"Seeded {len(selected)} settings from {src} -> {target}")
PY
