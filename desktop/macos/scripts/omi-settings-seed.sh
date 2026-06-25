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
set -euo pipefail

TARGET="${1:?usage: omi-settings-seed.sh <target-bundle-id> [source-bundle-id]}"
SRC="${2:-com.omi.desktop-dev}"

python3 - "$SRC" "$TARGET" <<'PY'
import plistlib
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
    "aiChatWorkingDirectory",
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
    "taskAgentWorkingDirectory",
    "taskAgentPromptPrefix",
    "taskAgentDefaultPrompt",
    "taskAgentSkipPermissions",
]


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
    sys.exit(f"No defaults found for {src}")

target_data = defaults_export(target)
selected = {key: source[key] for key in KEYS if key in source}
if not selected:
    print(f"Seeded 0 settings from {src} -> {target}")
    sys.exit(0)

target_data.update(selected)
with tempfile.NamedTemporaryFile(suffix=".plist") as plist:
    plistlib.dump(target_data, plist)
    plist.flush()
    subprocess.run(["defaults", "import", target, plist.name], check=True)

print(f"Seeded {len(selected)} settings from {src} -> {target}")
PY
