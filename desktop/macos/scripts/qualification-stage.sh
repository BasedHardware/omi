#!/usr/bin/env bash
# Owner-only, per-invocation scratch state for desktop Beta qualification.

qualification_stage_create() {
  local stage_parent="${TMPDIR:-/tmp}"
  local stage
  stage="$(umask 077; mktemp -d "$stage_parent/omi-desktop-qualification.XXXXXXXX")"
  chmod 700 "$stage"
  printf '%s\n' "$stage"
}

qualification_stage_remove() {
  local stage="$1"
  [[ -n "$stage" && -d "$stage" ]] || return 0
  case "$(basename "$stage")" in
    omi-desktop-qualification.????????) ;;
    *)
      echo "qualification stage cleanup refused unexpected path: $stage" >&2
      return 1
      ;;
  esac
  rm -rf -- "$stage"
}
