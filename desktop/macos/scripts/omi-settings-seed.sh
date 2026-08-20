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
        sys.exit(f"Could not export defaults domain {domain}")
    data = plistlib.loads(proc.stdout)
    if data:
        return True, data

    # `defaults export` returns an empty plist with status 0 for both an empty
    # existing domain and a missing domain. Only `defaults domains` preserves
    # that distinction, which decides whether stale target overrides are safe
    # to clear.
    domains = subprocess.run(
        ["defaults", "domains"],
        capture_output=True,
        check=False,
        text=True,
    )
    if domains.returncode != 0:
        sys.exit(f"Could not determine whether defaults domain {domain} exists")
    known_domains = {item.strip() for item in domains.stdout.split(",")}
    return domain in known_domains, data


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


source_exists, source = defaults_export(src)
if not source_exists:
    print(f"No defaults found for {src}; applying target-only dev defaults")

_, target_data = defaults_export(target)
initial_target_keys = set(target_data)
selected = {key: source[key] for key in KEYS if key in source}
keys_to_delete = set()

if source_exists:
    # This is a mirror, not an overlay. A missing source key means the source
    # app is using its compiled default. Remove any stale target override so
    # the named bundle resolves the same effective value after a Swift update.
    for key in KEYS:
        if key not in source and key in target_data:
            target_data.pop(key, None)
            keys_to_delete.add(key)

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
    # These target-only safety keys are intentionally normalized even when the
    # source domain is missing; other curated target preferences are preserved.
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
keys_to_delete.difference_update(target_data)
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
    if key not in target_data and key in initial_target_keys:
        keys_to_delete.add(key)

for key in sorted(keys_to_delete):
    deleted = subprocess.run(
        ["defaults", "delete", target, key],
        capture_output=True,
        check=False,
    )
    if deleted.returncode != 0:
        sys.exit(f"Failed to remove stale setting {key} from {target}")

target_exists, written = defaults_export(target)
if not target_exists:
    sys.exit(f"Seeded defaults domain {target} disappeared before verification")
for key, expected in selected.items():
    if written.get(key) != expected:
        sys.exit(f"Failed to verify seeded setting {key} in {target}")
for key in keys_to_delete:
    if key in written:
        sys.exit(f"Failed to verify removal of stale setting {key} from {target}")

print(f"Seeded {len(selected)} settings and cleared {len(keys_to_delete)} stale settings from {src} -> {target}")
PY
