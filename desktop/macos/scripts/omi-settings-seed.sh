#!/bin/bash
# omi-settings-seed.sh — copy dev-experience preferences into a test bundle.
#
# This intentionally copies a curated allowlist instead of cloning the whole
# UserDefaults domain. Whole-domain copies drag along caches, counters, and
# per-bundle state that make named bundles harder to reason about.
#
# Usage: omi-settings-seed.sh <target-bundle-id> [source-bundle-id]
#   target-bundle-id  e.g. com.omi.omi-fix-rewind  (a named test bundle)
#   source-bundle-id  optional explicit authority; when omitted, the source
#     resolves to OMI_SETTINGS_SEED_SOURCE if set (fail-closed when that
#     domain is missing), else the production app com.omi.computer-macos
#     when its defaults domain exists, else com.omi.desktop-dev.
#   OMI_SETTINGS_SEED_PRODUCTION_DOMAIN overrides which bundle id counts as
#     "production" for that auto-resolution (tests use it to stay isolated:
#     `defaults` state is uid-wide, not home-isolated).
#
# The settings authority is a single domain per run: the mirror below never
# merges sources, so a key absent from the resolved authority still means
# "delete the target override" (both sides resolve the compiled default).
#
# Set OMI_DEV_EAGER_PERMISSIONS=1 to preserve eager post-onboarding behavior
# for permission-flow parity testing.
set -euo pipefail

TARGET="${1:?usage: omi-settings-seed.sh <target-bundle-id> [source-bundle-id]}"

domain_exists() {
    # No `grep -q`: it exits on first match, the still-writing upstream stages
    # die on SIGPIPE, and `set -o pipefail` turns that into a false negative
    # against the ~1MB `defaults domains` stream. Plain grep consumes all
    # input, so every stage exits cleanly.
    defaults domains 2>/dev/null \
        | tr ',' '\n' \
        | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
        | grep -Fx -- "$1" >/dev/null
}

PRODUCTION_DOMAIN="${OMI_SETTINGS_SEED_PRODUCTION_DOMAIN:-com.omi.computer-macos}"

if [ -n "${OMI_SETTINGS_SEED_SOURCE:-}" ]; then
    if ! domain_exists "$OMI_SETTINGS_SEED_SOURCE"; then
        echo "ERROR: OMI_SETTINGS_SEED_SOURCE=$OMI_SETTINGS_SEED_SOURCE has no defaults domain." >&2
        echo "Point it at an installed Omi app (e.g. com.omi.computer-macos or com.omi.desktop-dev)." >&2
        exit 1
    fi
    SRC="$OMI_SETTINGS_SEED_SOURCE"
elif [ -n "${2:-}" ]; then
    SRC="$2"
elif domain_exists "$PRODUCTION_DOMAIN"; then
    SRC="$PRODUCTION_DOMAIN"
else
    SRC="com.omi.desktop-dev"
fi

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

# A present-but-stale authority is the silent-failure shape this seed exists
# to prevent: every mirrored bundle would ship compiled hotkey defaults that
# collide with other apps. Name the effective default instead of staying quiet.
HOTKEY_COMPILED_DEFAULTS = {
    "shortcut_askOmiKey": "Ask Omi ⌘O",
    "shortcut_pttKey": "push-to-talk ⌥",
}
missing_hotkeys = [key for key in HOTKEY_COMPILED_DEFAULTS if key not in source]
if source_exists and missing_hotkeys:
    defaults_named = ", ".join(
        f"{HOTKEY_COMPILED_DEFAULTS[key]}" for key in missing_hotkeys
    )
    print(
        f"Warning: {src} has no override for {', '.join(missing_hotkeys)}; "
        f"{target} will use the compiled default ({defaults_named}).\n"
        f"  Set the shortcut in that app (Settings → Shortcuts), mirror a different app with"
        f" OMI_SETTINGS_SEED_SOURCE=<bundle-id>, or use OMI_SKIP_SETTINGS_SEED=1 for"
        f" bundle-local shortcut testing.\n"
        f"  While the source app runs it holds those hotkey registrations; quit it to"
        f" exercise the bundle's own registration.",
        file=sys.stderr,
    )

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
