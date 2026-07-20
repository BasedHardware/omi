#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IOS_DIR="$APP_DIR/ios"
BOUNDARY_HELPER="$IOS_DIR/rayban_dat_plugin_boundary.rb"
STATE_DIR="$APP_DIR/.dart_tool/rayban_dat_build"
DEFAULT_LOCK_BACKUP="$STATE_DIR/default_Podfile.lock"
DEFAULT_GENERATED_XCCONFIG_BACKUP="$STATE_DIR/default_Generated.xcconfig"
DEFAULT_GENERATED_XCCONFIG_ABSENT="$STATE_DIR/default_Generated.xcconfig.absent"
DEFAULT_EXPORT_ENVIRONMENT_BACKUP="$STATE_DIR/default_flutter_export_environment.sh"
DEFAULT_EXPORT_ENVIRONMENT_ABSENT="$STATE_DIR/default_flutter_export_environment.sh.absent"
PODFILE_LOCK="$IOS_DIR/Podfile.lock"
PODS_MANIFEST="$IOS_DIR/Pods/Manifest.lock"
PLUGIN_METADATA="$APP_DIR/.flutter-plugins-dependencies"
PLUGIN_REGISTRANT="$IOS_DIR/Runner/GeneratedPluginRegistrant.m"
GENERATED_XCCONFIG="$IOS_DIR/Flutter/Generated.xcconfig"
FLUTTER_EXPORT_ENVIRONMENT="$IOS_DIR/Flutter/flutter_export_environment.sh"

FLUTTER_BIN="${FLUTTER_BIN:-flutter}"
POD_BIN="${POD_BIN:-pod}"
RUBY_BIN="${RUBY_BIN:-ruby}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/rayban_dat.sh run [flutter run options]
  scripts/rayban_dat.sh build [ios|ipa] [flutter build options]
  scripts/rayban_dat.sh restore

The run/build commands create the dedicated Ray-Ban DAT dependency graph, use
the raybanDat Flutter flavor with OMI_RAYBAN_DAT=true, and restore the standard
mcumgr_flutter CocoaPods graph when Flutter exits. Use restore after an
interrupted transaction that could not run its EXIT cleanup.
USAGE
}

fail() {
  echo "rayban-dat: $*" >&2
  exit 1
}

without_dat_flag() {
  (
    unset OMI_RAYBAN_DAT
    "$@"
  )
}

run_flutter_without_dat() {
  (
    unset OMI_RAYBAN_DAT
    cd "$APP_DIR"
    "$FLUTTER_BIN" "$@"
  )
}

metadata_contains_mcumgr() {
  "$RUBY_BIN" -rjson -e '
    document = JSON.parse(File.binread(ARGV.fetch(0)))
    platform_plugins = document.fetch("plugins").fetch(ARGV.fetch(1))
    exit(platform_plugins.any? { |plugin| plugin["name"] == "mcumgr_flutter" } ? 0 : 1)
  ' "$PLUGIN_METADATA" "$1"
}

assert_non_dat_flutter_environment() {
  local generated_file

  for generated_file in "$GENERATED_XCCONFIG" "$FLUTTER_EXPORT_ENVIRONMENT"; do
    [[ -f "$generated_file" ]] || continue
    if grep -Fq 'FLAVOR=raybanDat' "$generated_file" ||
      grep -Fq 'OMI_RAYBAN_DAT=true' "$generated_file" ||
      grep -Fq 'T01JX1JBWUJBTl9EQVQ9dHJ1ZQ==' "$generated_file"; then
      echo "rayban-dat: DAT flavor leaked into $generated_file" >&2
      return 1
    fi
  done
}

assert_default_generated_state() {
  [[ -f "$PODFILE_LOCK" ]] || {
    echo "rayban-dat: default Podfile.lock is missing" >&2
    return 1
  }
  if [[ "${1:-}" == 'with-pods' ]]; then
    [[ -f "$PODS_MANIFEST" ]] || {
      echo "rayban-dat: default Pods/Manifest.lock is missing" >&2
      return 1
    }
    cmp -s "$PODFILE_LOCK" "$PODS_MANIFEST" || {
      echo "rayban-dat: default Podfile.lock and Pods/Manifest.lock do not match" >&2
      return 1
    }
  fi
  grep -q 'mcumgr_flutter' "$PODFILE_LOCK" || {
    echo "rayban-dat: default Podfile.lock does not contain mcumgr_flutter" >&2
    return 1
  }
  grep -q 'SwiftProtobuf' "$PODFILE_LOCK" || {
    echo "rayban-dat: default Podfile.lock does not contain SwiftProtobuf" >&2
    return 1
  }
  metadata_contains_mcumgr ios || {
    echo "rayban-dat: default Flutter plugin metadata does not contain mcumgr_flutter" >&2
    return 1
  }
  grep -q 'McumgrFlutterPlugin' "$PLUGIN_REGISTRANT" || {
    echo "rayban-dat: default iOS plugin registrant does not contain McumgrFlutterPlugin" >&2
    return 1
  }
  assert_non_dat_flutter_environment
}

assert_dat_generated_state() {
  [[ -f "$PODFILE_LOCK" ]] || {
    echo "rayban-dat: DAT Podfile.lock is missing" >&2
    return 1
  }
  [[ -f "$PODS_MANIFEST" ]] || {
    echo "rayban-dat: DAT Pods/Manifest.lock is missing" >&2
    return 1
  }
  cmp -s "$PODFILE_LOCK" "$PODS_MANIFEST" || {
    echo "rayban-dat: DAT Podfile.lock and Pods/Manifest.lock do not match" >&2
    return 1
  }
  if grep -q 'mcumgr_flutter' "$PODFILE_LOCK"; then
    echo "rayban-dat: DAT Podfile.lock still contains mcumgr_flutter" >&2
    return 1
  fi
  if grep -q 'SwiftProtobuf' "$PODFILE_LOCK"; then
    echo "rayban-dat: DAT Podfile.lock still contains the CocoaPods SwiftProtobuf copy" >&2
    return 1
  fi
  if grep -q 'iOSMcuManagerLibrary' "$PODFILE_LOCK"; then
    echo "rayban-dat: DAT Podfile.lock still contains iOSMcuManagerLibrary" >&2
    return 1
  fi
  if metadata_contains_mcumgr ios; then
    echo "rayban-dat: DAT Flutter plugin metadata still contains the iOS mcumgr_flutter entry" >&2
    return 1
  fi
  if ! metadata_contains_mcumgr android; then
    echo "rayban-dat: DAT transform unexpectedly removed the Android mcumgr_flutter entry" >&2
    return 1
  fi
  if grep -q 'McumgrFlutterPlugin' "$PLUGIN_REGISTRANT"; then
    echo "rayban-dat: DAT iOS plugin registrant still registers McumgrFlutterPlugin" >&2
    return 1
  fi
}

stage_original_lock() {
  if [[ ! -f "$DEFAULT_LOCK_BACKUP" ]]; then
    return 0
  fi

  cp -p "$DEFAULT_LOCK_BACKUP" "$PODFILE_LOCK"
}

verify_original_lock_unchanged() {
  if [[ ! -f "$DEFAULT_LOCK_BACKUP" ]]; then
    return 0
  fi

  if ! cmp -s "$PODFILE_LOCK" "$DEFAULT_LOCK_BACKUP"; then
    echo "rayban-dat: default Podfile.lock changed during pod install" >&2
    return 1
  fi
  if ! cmp -s "$PODS_MANIFEST" "$DEFAULT_LOCK_BACKUP"; then
    echo "rayban-dat: default Pods/Manifest.lock changed during pod install" >&2
    return 1
  fi
}

snapshot_generated_file() {
  local source_file="$1"
  local backup_file="$2"
  local absent_marker="$3"

  rm -f "$backup_file" "$absent_marker"
  if [[ -f "$source_file" ]]; then
    cp -p "$source_file" "$backup_file"
  else
    : >"$absent_marker"
  fi
}

snapshot_flutter_environment() {
  snapshot_generated_file \
    "$GENERATED_XCCONFIG" \
    "$DEFAULT_GENERATED_XCCONFIG_BACKUP" \
    "$DEFAULT_GENERATED_XCCONFIG_ABSENT"
  snapshot_generated_file \
    "$FLUTTER_EXPORT_ENVIRONMENT" \
    "$DEFAULT_EXPORT_ENVIRONMENT_BACKUP" \
    "$DEFAULT_EXPORT_ENVIRONMENT_ABSENT"
}

restore_generated_file() {
  local destination_file="$1"
  local backup_file="$2"
  local absent_marker="$3"

  if [[ -f "$backup_file" && ! -e "$absent_marker" ]]; then
    cp -p "$backup_file" "$destination_file"
    cmp -s "$destination_file" "$backup_file"
    return
  fi
  if [[ -f "$absent_marker" && ! -e "$backup_file" ]]; then
    rm -f "$destination_file"
    return
  fi
  if [[ ! -e "$backup_file" && ! -e "$absent_marker" ]]; then
    return
  fi

  echo "rayban-dat: invalid generated-file recovery state for $destination_file" >&2
  return 1
}

restore_flutter_environment() {
  local restore_failed=0

  restore_generated_file \
    "$GENERATED_XCCONFIG" \
    "$DEFAULT_GENERATED_XCCONFIG_BACKUP" \
    "$DEFAULT_GENERATED_XCCONFIG_ABSENT" || restore_failed=1
  restore_generated_file \
    "$FLUTTER_EXPORT_ENVIRONMENT" \
    "$DEFAULT_EXPORT_ENVIRONMENT_BACKUP" \
    "$DEFAULT_EXPORT_ENVIRONMENT_ABSENT" || restore_failed=1

  return "$restore_failed"
}

clear_wrapper_state() {
  rm -f \
    "$DEFAULT_LOCK_BACKUP" \
    "$DEFAULT_GENERATED_XCCONFIG_BACKUP" \
    "$DEFAULT_GENERATED_XCCONFIG_ABSENT" \
    "$DEFAULT_EXPORT_ENVIRONMENT_BACKUP" \
    "$DEFAULT_EXPORT_ENVIRONMENT_ABSENT"
  if [[ -d "$STATE_DIR" ]] && ! rmdir "$STATE_DIR"; then
    echo "rayban-dat: recovery state contains unexpected files: $STATE_DIR" >&2
    return 1
  fi
}

restore_default_state() {
  local restore_failed=0

  echo "rayban-dat: restoring the default mcumgr_flutter build graph"

  if ! without_dat_flag "$RUBY_BIN" "$BOUNDARY_HELPER" restore; then
    echo "rayban-dat: failed to restore generated Flutter plugin files" >&2
    restore_failed=1
  fi

  if ! run_flutter_without_dat pub get --enforce-lockfile; then
    echo "rayban-dat: failed to regenerate the default Flutter plugin graph" >&2
    restore_failed=1
  fi

  # CocoaPods must resolve the default graph from the exact pre-DAT lock. If
  # the DAT lock were left in place here, it could select newer mcumgr
  # transitive versions and then appear clean after the lockfile was copied.
  if ! stage_original_lock; then
    echo "rayban-dat: failed to stage the original Podfile.lock for CocoaPods" >&2
    restore_failed=1
  fi

  if ! (
    unset OMI_RAYBAN_DAT
    cd "$IOS_DIR"
    "$POD_BIN" install
  ); then
    echo "rayban-dat: failed to reinstall the default CocoaPods graph" >&2
    restore_failed=1
  fi

  if ! verify_original_lock_unchanged; then
    restore_failed=1
  fi

  if ! restore_flutter_environment; then
    echo "rayban-dat: failed to restore Flutter's default flavor environment" >&2
    restore_failed=1
  fi

  if ((restore_failed == 0)) && ! assert_default_generated_state with-pods; then
    restore_failed=1
  fi

  if ((restore_failed == 0)) && ! clear_wrapper_state; then
    restore_failed=1
  fi

  if ((restore_failed == 0)); then
    echo "rayban-dat: default build graph restored"
  else
    echo "rayban-dat: restore incomplete; run scripts/rayban_dat.sh restore" >&2
  fi

  return "$restore_failed"
}

finish_transaction() {
  local action_status="$1"
  local restore_status=0
  trap - EXIT

  restore_default_state || restore_status=$?

  if ((action_status != 0)); then
    exit "$action_status"
  fi
  exit "$restore_status"
}

[[ -f "$BOUNDARY_HELPER" ]] || fail "missing plugin boundary helper: $BOUNDARY_HELPER"

command="${1:-}"
case "$command" in
  run | build | restore)
    shift
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

build_artifact=''
if [[ "$command" == 'build' ]]; then
  if (($# == 0)) || [[ "${1:-}" == -* ]]; then
    build_artifact='ios'
  else
    build_artifact="$1"
    shift
  fi

  case "$build_artifact" in
    ios | ipa) ;;
    *) fail "unsupported build artifact '$build_artifact' (expected ios or ipa)" ;;
  esac
fi

if [[ "$command" == 'restore' ]]; then
  (($# == 0)) || fail 'restore does not accept additional arguments'
  restore_default_state
  exit $?
fi

[[ ! -e "$STATE_DIR" ]] || fail "stale DAT transaction found; run scripts/rayban_dat.sh restore first"

run_flutter_without_dat pub get --enforce-lockfile
assert_default_generated_state

mkdir -p "$STATE_DIR"
cp -p "$PODFILE_LOCK" "$DEFAULT_LOCK_BACKUP"
snapshot_flutter_environment
trap 'finish_transaction "$?"' EXIT

OMI_RAYBAN_DAT=1 "$RUBY_BIN" "$BOUNDARY_HELPER" prepare
(
  export OMI_RAYBAN_DAT=1
  cd "$IOS_DIR"
  "$POD_BIN" install
)
assert_dat_generated_state

if [[ "$command" == 'run' ]]; then
  (
    export OMI_RAYBAN_DAT=1
    cd "$APP_DIR"
    "$FLUTTER_BIN" run \
      --flavor raybanDat \
      --dart-define=OMI_RAYBAN_DAT=true \
      --no-pub \
      "$@"
  )
else
  (
    export OMI_RAYBAN_DAT=1
    cd "$APP_DIR"
    "$FLUTTER_BIN" build "$build_artifact" \
      --flavor raybanDat \
      --dart-define=OMI_RAYBAN_DAT=true \
      --no-pub \
      "$@"
  )
fi
