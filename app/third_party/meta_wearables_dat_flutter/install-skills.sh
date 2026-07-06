#!/bin/bash
# Copyright (c) iSee Labs and affiliates.
# Released under the MIT license; see LICENSE in the repo root.

# Install meta_wearables_dat_flutter AI development config into your project.
# Usage:
#   ./install-skills.sh             # Interactive menu (when run with a tty)
#   ./install-skills.sh claude      # Claude Code only
#   ./install-skills.sh copilot     # GitHub Copilot only
#   ./install-skills.sh cursor      # Cursor only
#   ./install-skills.sh agents      # AGENTS.md only
#   ./install-skills.sh all         # All tools
#   curl -sL ...install-skills.sh | bash   # Defaults to "all" (no tty)

set -euo pipefail

REPO="iSee-Labs/meta-wearables-dat-flutter"
BRANCH="main"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"
EXTRACT_DIR="meta-wearables-dat-flutter-${BRANCH}"

safe_cleanup() {
  if [ -z "${EXTRACT_DIR:-}" ]; then
    echo "Warning: EXTRACT_DIR is empty, skipping cleanup." >&2
    return 0
  fi
  if [[ ! "$EXTRACT_DIR" =~ ^meta-wearables-dat-flutter- ]]; then
    echo "Warning: EXTRACT_DIR does not match expected pattern, skipping cleanup." >&2
    return 0
  fi
  if [ -d "$EXTRACT_DIR" ]; then
    rm -rf "$EXTRACT_DIR"
  fi
}
trap safe_cleanup EXIT

download_archive() {
  if [ ! -d "${EXTRACT_DIR}" ]; then
    curl -sL "$ARCHIVE_URL" | tar xz 2>/dev/null
  fi
}

install_claude() {
  echo "Installing Claude Code config for meta_wearables_dat_flutter..."
  download_archive
  if [ -d "${EXTRACT_DIR}/.claude" ]; then
    mkdir -p .claude
    cp -R "${EXTRACT_DIR}/.claude/." .claude/
    echo "Installed .claude/ with $(find .claude -name '*.md' | wc -l | tr -d ' ') files."
  else
    echo "Error: Failed to download .claude/ config." >&2
    return 1
  fi
}

install_copilot() {
  echo "Installing GitHub Copilot config for meta_wearables_dat_flutter..."
  download_archive
  if [ -d "${EXTRACT_DIR}/.github" ]; then
    mkdir -p .github
    cp -R "${EXTRACT_DIR}/.github/." .github/
    echo "Installed .github/copilot-instructions.md."
  else
    echo "Error: Failed to download .github/ config." >&2
    return 1
  fi
}

install_cursor() {
  echo "Installing Cursor config for meta_wearables_dat_flutter..."
  download_archive
  if [ -d "${EXTRACT_DIR}/.cursor" ]; then
    mkdir -p .cursor
    cp -R "${EXTRACT_DIR}/.cursor/." .cursor/
    echo "Installed .cursor/rules/ with $(find .cursor -name '*.mdc' | wc -l | tr -d ' ') files."
  else
    echo "Error: Failed to download .cursor/ config." >&2
    return 1
  fi
}

install_agents() {
  echo "Installing AGENTS.md..."
  download_archive
  if [ -f "${EXTRACT_DIR}/AGENTS.md" ]; then
    cp "${EXTRACT_DIR}/AGENTS.md" AGENTS.md
    echo "Installed AGENTS.md"
  else
    echo "Error: Failed to download AGENTS.md." >&2
    return 1
  fi
}

install_all() {
  local failed=0
  install_claude  || failed=1
  install_copilot || failed=1
  install_cursor  || failed=1
  install_agents  || failed=1
  if [ "$failed" -eq 1 ]; then
    return 1
  fi
}

show_menu() {
  echo ""
  echo "meta_wearables_dat_flutter AI Config Installer"
  echo "=============================================="
  echo ""
  echo "Which tool do you want to install config for?"
  echo ""
  echo "  1) Claude Code    (.claude/)"
  echo "  2) GitHub Copilot (.github/)"
  echo "  3) Cursor         (.cursor/)"
  echo "  4) AGENTS.md      (universal — Codex, Gemini CLI, Devin, Windsurf, etc.)"
  echo "  5) All tools"
  echo "  6) Cancel"
  echo ""
  read -rp "Enter choice [1-6]: " choice
  case "$choice" in
    1) install_claude ;;
    2) install_copilot ;;
    3) install_cursor ;;
    4) install_agents ;;
    5) install_all ;;
    6) echo "Cancelled." ; exit 0 ;;
    *) echo "Invalid choice." >&2 ; exit 1 ;;
  esac
}

# Main
TOOL="${1:-}"

if [ -n "$TOOL" ]; then
  case "$TOOL" in
    claude)  install_claude ;;
    copilot) install_copilot ;;
    cursor)  install_cursor ;;
    agents)  install_agents ;;
    all)     install_all ;;
    *)       echo "Unknown tool: $TOOL. Use: claude, copilot, cursor, agents, or all." >&2 ; exit 1 ;;
  esac
elif [ -t 0 ]; then
  show_menu
else
  install_all
fi

echo ""
echo "Your AI assistant will auto-discover the config when you open this project."
