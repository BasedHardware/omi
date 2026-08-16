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
    "audioRecordingMode",
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


def source_audio_recording_mode(source):
    mode = source.get("audioRecordingMode")
    if mode in {"off", "always", "onlyMeetings"}:
        return mode

    # Preserve intent from bundles created before Audio Recording became the
    # single preference. The old "never" value disabled only system audio, so
    # "always" is the closest equivalent for its still-enabled microphone.
    if source.get("transcriptionEnabled") is False:
        return "off"
    return {
        "always": "always",
        "onlyDuringMeetings": "onlyMeetings",
        "never": "always",
    }.get(source.get("systemAudioCaptureMode"), "onlyMeetings")


source = defaults_export(src)
if not source:
    print(f"No defaults found for {src}; applying target-only dev defaults")

target_data = defaults_export(target)
selected = {key: source[key] for key in KEYS if key in source}

if not env_truthy("OMI_DEV_EAGER_PERMISSIONS"):
    # Named dev bundles reuse auth/onboarding from Omi Dev, but macOS treats
    # each bundle ID as a fresh TCC identity. Keep non-screen services quiet,
    # while leaving screen capture enabled: the runtime checks TCC without
    # requesting it, then starts capture automatically after permission exists.
    selected.update(
        {
            "devLazyPermissionsEnabled": True,
            "screenAnalysisEnabled": True,
            "audioRecordingMode": "off",
        }
    )
    # Never carry over the hidden kill switch from a previous seed or the source.
    target_data.pop("disableSystemAudioCapture", None)
    target_data.pop("screenAnalysisAutoStartFixed_v2", None)
    target_data.pop("screenAnalysisAutoStartFixed_v3", None)
else:
    # Eager mode: fully undo quiet-permission defaults so permission-flow
    # parity testing can exercise the normal startup paths.
    selected.update(
        {
            "devLazyPermissionsEnabled": False,
            # Restore the one user-facing audio preference so a previously
            # quiet-seeded bundle runs the normal startup path.
            "screenAnalysisEnabled": source.get("screenAnalysisEnabled", True),
            "audioRecordingMode": source_audio_recording_mode(source),
        }
    )
    target_data.pop("screenAnalysisAutoStartFixed_v2", None)
    target_data.pop("screenAnalysisAutoStartFixed_v3", None)
    target_data.pop("disableSystemAudioCapture", None)

target_data.update(selected)
with tempfile.NamedTemporaryFile(suffix=".plist") as plist:
    plistlib.dump(target_data, plist)
    plist.flush()
    subprocess.run(["defaults", "import", target, plist.name], check=True)

# Keys removed from target_data above need to be explicitly deleted from the
# target domain — `defaults import` merges and never removes keys.
for key in (
    "disableSystemAudioCapture",
    "screenAnalysisAutoStartFixed_v2",
    "screenAnalysisAutoStartFixed_v3",
    "transcriptionEnabled",
    "systemAudioCaptureMode",
):
    if key not in target_data:
        subprocess.run(["defaults", "delete", target, key], check=False)

print(f"Seeded {len(selected)} settings from {src} -> {target}")
PY
