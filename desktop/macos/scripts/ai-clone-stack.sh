#!/usr/bin/env bash
# Single-command E2E stack runner for the Omi AI Clone.
#
# Starts the entire stack needed to test the AI Clone flow against
# a real Telegram bot:
#   1. Python backend  (port 8080, local)
#   2. Telegram plugin (port 18800, local)
#   3. Desktop app    (built + ad-hoc signed + installed + launched)
#
# A tunnel (ngrok / Cloudflare) is OPTIONAL: when TUNNEL_URL is set
# the plugin exposes it in its discovery file so the desktop sends
# the right URL to Telegram's setWebhook. Without TUNNEL_URL the
# plugin still boots and the desktop auto-discovers it over
# loopback — but the Telegram webhook won't be reachable from
# outside, so Connect will fail at the setWebhook step.
#
# Prereqs (override via env vars; see "Configuration" below):
#   - A worktree at $WORKTREE with the AI Clone code
#   - Python backend .env at $BACKEND_SECRETS_ENV
#   - GCP service account JSON at $GCP_CREDENTIALS_JSON
#   - (optional) Cached Firebase auth dump at $AUTH_DUMP_JSON — the
#     desktop boots signed-in without going through the browser
#   - (optional) Production desktop's .env at $PROD_DOTENV — copied
#     into the test bundle so it has the right API URLs
#
# Usage:
#   WORKTREE=$HOME/code/omi \
#   BACKEND_SECRETS_ENV=$HOME/omi-backend.env \
#   GCP_CREDENTIALS_JSON=$HOME/omi-gcp.json \
#   AUTH_DUMP_JSON=$HOME/omi-auth.json \
#   TUNNEL_URL=https://<your>.ngrok-free.app \
#   PLUGIN_TOKEN=<random-32-bytes> \
#   bash desktop/macos/scripts/ai-clone-stack.sh
#
# Stop everything:
#   kill $(cat $LOGDIR/backend.pid $LOGDIR/plugin.pid 2>/dev/null) 2>/dev/null

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — every value is overridable via env. The defaults match
# the script author's local setup; override WORKTREE at minimum.
# ---------------------------------------------------------------------------
WORKTREE="${WORKTREE:-$HOME/Documents/workspaces/cool-projects/omi-worktrees/feat-ai-clone-prompt-rewrite}"
BACKEND_SECRETS_ENV="${BACKEND_SECRETS_ENV:-/tmp/omi-py-backend/secrets.env}"
GCP_CREDENTIALS_JSON="${GCP_CREDENTIALS_JSON:-/tmp/omi-google-credentials.json}"
AUTH_DUMP_JSON="${AUTH_DUMP_JSON:-/tmp/prod-auth.json}"
PROD_DOTENV="${PROD_DOTENV:-/Applications/omi.app/Contents/Resources/.env}"
LOGDIR="${LOGDIR:-/tmp/omi-e2e}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
PLUGIN_PORT="${PLUGIN_PORT:-18800}"
# User-account (Telethon) plugin port. Distinct from PLUGIN_PORT
# so the bot and user-account plugins can run side-by-side for
# comparison. Set TELEGRAM_USER_ACCOUNT=1 to launch it.
USER_PLUGIN_PORT="${USER_PLUGIN_PORT:-18801}"
# Path to the Telethon session string file. The desktop reads
# the session from Keychain and writes it to this file just
# before launching the plugin; the stack runner then pipes it
# into the plugin's stdin (which is read ONCE then discarded).
# The file is chmod 600 and removed right after the plugin
# starts so the session never sits on disk long-term.
TELEGRAM_USER_SESSION_FILE="${TELEGRAM_USER_SESSION_FILE:-$LOGDIR/telegram-user.session}"
# When TELEGRAM_USER_ACCOUNT=1, the stack runner launches the
# user-account plugin in addition to the bot plugin. Set to 0
# (default) to skip it.
TELEGRAM_USER_ACCOUNT="${TELEGRAM_USER_ACCOUNT:-0}"
APP_NAME="${APP_NAME:-omi-feat-ai-clone-e2e}"
BUNDLE_ID="com.omi.${APP_NAME}"

PLUGIN_TOKEN="${PLUGIN_TOKEN:-local-dev-token-8b555c51c5583388}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-local-dev-webhook-secret}"
TUNNEL_URL="${TUNNEL_URL:-http://127.0.0.1:${PLUGIN_PORT}}"   # loopback-only fallback

# ---------------------------------------------------------------------------
# Sanity check — fail loud with a clear message rather than producing
# a half-built stack.
# ---------------------------------------------------------------------------
[ -d "$WORKTREE" ] || { echo "❌ WORKTREE not found: $WORKTREE"; exit 1; }
[ -f "$BACKEND_SECRETS_ENV" ] || { echo "❌ BACKEND_SECRETS_ENV not found: $BACKEND_SECRETS_ENV"; exit 1; }
[ -f "$GCP_CREDENTIALS_JSON" ] || { echo "❌ GCP_CREDENTIALS_JSON not found: $GCP_CREDENTIALS_JSON"; exit 1; }
[ -f "$WORKTREE/backend/.venv/bin/python" ] || { echo "❌ Python venv missing — run: cd $WORKTREE/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[ -f "$WORKTREE/plugins/omi-telegram-app/.venv/bin/uvicorn" ] || { echo "❌ Plugin venv missing — run: cd $WORKTREE/plugins/omi-telegram-app && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[ "$TELEGRAM_USER_ACCOUNT" = "1" ] && [ ! -f "$WORKTREE/plugins/telegram-user-account/.venv/bin/uvicorn" ] && { echo "❌ User-account plugin venv missing -- run: cd $WORKTREE/plugins/telegram-user-account && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[ "$TELEGRAM_USER_ACCOUNT" = "1" ] && [ ! -f "$TELEGRAM_USER_SESSION_FILE" ] && { echo "❌ TELEGRAM_USER_ACCOUNT=1 but TELEGRAM_USER_SESSION_FILE=$TELEGRAM_USER_SESSION_FILE not found. The desktop writes the session here just before launching; for headless testing, write the session string to this file (chmod 600)."; exit 1; }

mkdir -p "$LOGDIR"

# ---------------------------------------------------------------------------
# 0. Tear down anything from a previous run AND anything holding the
# target ports (a backend from a sibling worktree, say). lsof finds
# the holder regardless of whose PID file it came from.
# ---------------------------------------------------------------------------
for pidf in backend.pid plugin.pid; do
  PID=$(cat "$LOGDIR/$pidf" 2>/dev/null || true)
  [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && { echo "Stopping previous $pidf (pid $PID)"; kill "$PID" 2>/dev/null || true; }
  rm -f "$LOGDIR/$pidf"
done
for port in "$BACKEND_PORT" "$PLUGIN_PORT"; do
  HOLDER=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)
  if [ -n "$HOLDER" ]; then
    CMD=$(ps -o command= -p "$HOLDER" 2>/dev/null || echo unknown)
    echo "Killing port-$port holder pid=$HOLDER ($CMD)"
    kill "$HOLDER" 2>/dev/null || true
  fi
done
pkill -f "Omi Computer" 2>/dev/null || true
sleep 2

# ---------------------------------------------------------------------------
# 1. Python backend on port 8080.
#    secrets.env contains an `export SERVICE_ACCOUNT_JSON="..."` multi-line
#    block. Bash's `source` chokes on the unterminated quote, so we strip
#    that line out and re-assign SERVICE_ACCOUNT_JSON from the raw JSON.
# ---------------------------------------------------------------------------
echo "── [1/3] Starting Python backend on :$BACKEND_PORT ──"
set -a
TMP_ENV=$(mktemp)
sed '/^export SERVICE_ACCOUNT_JSON="/,/^}"$/d' "$BACKEND_SECRETS_ENV" \
  | grep -v 'SERVICE_ACCOUNT_JSON=' \
  | grep -v '^  ' \
  | grep -v '^}$' \
  > "$TMP_ENV" || true
. "$TMP_ENV"
rm -f "$TMP_ENV"
set +a
unset SERVICE_ACCOUNT_JSON
export SERVICE_ACCOUNT_JSON="$(cat "$GCP_CREDENTIALS_JSON")"
cd "$WORKTREE/backend"
PYENV_VERSION=3.11.11 nohup .venv/bin/python -m uvicorn main:app \
  --host 127.0.0.1 --port "$BACKEND_PORT" --log-level info \
  > "$LOGDIR/backend.log" 2>&1 &
echo $! > "$LOGDIR/backend.pid"

# Backend startup is slow: heavy imports (LLM clients, QoS profiles,
# Firestore, Pinecone, Redis). Poll /v1/health for up to 30s.
echo "  waiting for backend health..."
READY=0
for i in $(seq 1 30); do
  sleep 1
  if curl -sS -m 2 "http://127.0.0.1:$BACKEND_PORT/v1/health" 2>/dev/null | grep -q '"status":"ok"'; then
    READY=1
    echo "  ✅ backend up (took ${i}s)"
    break
  fi
done
[ "$READY" = "1" ] || { echo "  ❌ backend never became healthy; check $LOGDIR/backend.log"; exit 1; }

# ---------------------------------------------------------------------------
# 2. Telegram plugin on port 18800.
# ---------------------------------------------------------------------------
echo "── [2/3] Starting Telegram plugin on :$PLUGIN_PORT ──"
cd "$WORKTREE"
PORT="$PLUGIN_PORT" \
STORAGE_DIR="$LOGDIR" \
TELEGRAM_WEBHOOK_SECRET="$WEBHOOK_SECRET" \
AI_CLONE_PLUGIN_TOKEN="$PLUGIN_TOKEN" \
OMI_BASE_URL="http://127.0.0.1:$BACKEND_PORT" \
PUBLIC_BASE_URL="$TUNNEL_URL" \
OMI_DEV_MODE=0 \
  nohup plugins/omi-telegram-app/.venv/bin/uvicorn \
    --app-dir plugins/omi-telegram-app main:app \
    --host 127.0.0.1 --port "$PLUGIN_PORT" --log-level info \
    > "$LOGDIR/plugin.log" 2>&1 &
echo $! > "$LOGDIR/plugin.pid"
sleep 3
curl -sS -m 5 -H "Authorization: Bearer $PLUGIN_TOKEN" "http://127.0.0.1:$PLUGIN_PORT/status" \
  | grep -q "service" \
  && echo "  ✅ plugin up" \
  || { echo "  ❌ plugin failed to start; check $LOGDIR/plugin.log"; exit 1; }

# ---------------------------------------------------------------------------
# 2b. Telegram user-account plugin on port $USER_PLUGIN_PORT.
#     Opt-in: only runs when TELEGRAM_USER_ACCOUNT=1. Authenticates as
#     the user's PERSONAL Telegram account (not a bot) via Telethon.
#     The session string is piped into stdin (read once, then the
#     local variable is overwritten with None in telethon_client.py).
# ---------------------------------------------------------------------------
if [ "$TELEGRAM_USER_ACCOUNT" = "1" ]; then
  echo "── [2b] Starting Telegram user-account plugin on :$USER_PLUGIN_PORT ──"
  cd "$WORKTREE"
  # The user-account plugin writes a DIFFERENT discovery file than
  # the bot plugin: ai-clone-telegram-user.json (per-plugin filename
  # per cubic review on PR #8682). The desktop's PluginDiscovery
  # already reads this filename.
  rm -f "$HOME/.config/omi/ai-clone-telegram-user.json"
  OMI_DEV_MODE=0 \
  nohup plugins/telegram-user-account/.venv/bin/uvicorn \
    --app-dir plugins/telegram-user-account main:app \
    --host 127.0.0.1 --port "$USER_PLUGIN_PORT" --log-level info \
    < "$TELEGRAM_USER_SESSION_FILE" \
    > "$LOGDIR/user-plugin.log" 2>&1 &
  echo $! > "$LOGDIR/user-plugin.pid"
  # Poll /health (no auth) until the plugin is ready.
  READY=0
  for i in $(seq 1 20); do
    sleep 1
    if curl -sS -m 2 "http://127.0.0.1:$USER_PLUGIN_PORT/health" 2>/dev/null | grep -q '"status"'; then
      READY=1
      echo "  ✅ user-account plugin up (took ${i}s)"
      break
    fi
  done
  [ "$READY" = "1" ] || { echo "  ❌ user-account plugin never became healthy; check $LOGDIR/user-plugin.log"; exit 1; }
  # Verify the discovery file was written.
  [ -f "$HOME/.config/omi/ai-clone-telegram-user.json" ] \
    && echo "  ✅ user-account discovery file at ~/.config/omi/ai-clone-telegram-user.json" \
    || echo "  ⚠️  user-account discovery file not written; desktop won't auto-discover"
fi

# ---------------------------------------------------------------------------
# 3. Build + sign + install + launch desktop app.
#    - OMI_SKIP_BACKEND skips the Rust desktop-backend (we point at Python directly).
#    - OMI_SKIP_TUNNEL skips Cloudflare (we already have ngrok via TUNNEL_URL if needed).
#    - run.sh installs the bundle to /Applications/<APP_NAME>.app on its own,
#      but fails at the signing step when there's no Apple Development cert.
#      We take over with ad-hoc signing in that case.
# ---------------------------------------------------------------------------
echo "── [3/3] Building + launching desktop ($APP_NAME) ──"
cd "$WORKTREE/desktop/macos"

# run.sh's first-time-setup check exits 1 if Backend-Rust/.env is
# missing. We're skipping the Rust backend entirely (OMI_SKIP_BACKEND=1)
# so the .env content doesn't matter — just the file's presence.
touch "$WORKTREE/desktop/macos/Backend-Rust/.env"
OMI_APP_NAME="$APP_NAME" \
OMI_SKIP_BACKEND=1 \
OMI_DESKTOP_API_URL="http://127.0.0.1:$BACKEND_PORT" \
OMI_SKIP_TUNNEL=1 \
  nohup ./run.sh > "$LOGDIR/desktop-build.log" 2>&1 &
DESKTOP_PID=$!
echo "$DESKTOP_PID" > "$LOGDIR/desktop.pid"

echo "  waiting for build…"
BUNDLE_DIR="build/$APP_NAME.app"
BUNDLE="$BUNDLE_DIR/Contents/MacOS/Omi Computer"
BUNDLE_READY=0
for i in $(seq 1 30); do
  sleep 6
  if [ -f "$BUNDLE" ]; then
    SIZE=$(stat -f%z "$BUNDLE" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 100000000 ]; then
      BUNDLE_READY=1
      echo "  ✅ bundle ready (size=$SIZE)"
      break
    fi
  fi
done

if [ "$BUNDLE_READY" = "0" ] && ! kill -0 "$DESKTOP_PID" 2>/dev/null; then
  echo "  ❌ run.sh exited before bundle was ready; tail of build log:"
  tail -30 "$LOGDIR/desktop-build.log"
  exit 1
fi

# Take over with ad-hoc signing + manual install when run.sh aborted
# at the signing step (no Apple Development cert in keychain).
APP="$WORKTREE/desktop/macos/build/$APP_NAME.app"
if [ -d "$APP" ]; then
  echo "  ad-hoc signing bundle…"
  codesign --remove-signature "$APP/Contents/Frameworks/Sparkle.framework" 2>/dev/null || true
  codesign --remove-signature "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/Updater.app" 2>/dev/null || true
  codesign --force --sign - "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/Updater.app" 2>/dev/null || true
  codesign --force --sign - "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/Sparkle" 2>/dev/null || true
  codesign --force --sign - "$APP/Contents/Frameworks/Sparkle.framework" 2>/dev/null || true
  for fw in "$APP"/Contents/Frameworks/*.framework; do
    [ -d "$fw" ] && [ "$(basename "$fw")" != "Sparkle.framework" ] && codesign --force --sign - "$fw" 2>/dev/null || true
  done
  for lib in "$APP"/Contents/Frameworks/*.dylib; do
    [ -f "$lib" ] && codesign --force --sign - "$lib" 2>/dev/null || true
  done
  codesign --force --sign - "$APP/Contents/MacOS/Omi Computer" 2>/dev/null || true
  codesign --force --sign - "$APP" 2>/dev/null || true

  # Copy production .env (API URLs + secrets) so the bundle points at
  # the right backend. Skip silently when PROD_DOTENV doesn't exist
  # (the bundle still launches; it just won't be able to talk to prod).
  if [ -f "$PROD_DOTENV" ]; then
    cp "$PROD_DOTENV" "$APP/Contents/Resources/.env" 2>/dev/null || true
  fi

  echo "  installing bundle to /Applications/$APP_NAME.app"
  rm -rf "/Applications/$APP_NAME.app"
  ditto "$APP" "/Applications/$APP_NAME.app"
  LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  $LSREGISTER -u "$APP" 2>/dev/null || true
  $LSREGISTER -f "/Applications/$APP_NAME.app" 2>/dev/null || true
fi

# Seed auth from cached Firebase dump (skip if no dump available —
# the user can sign in manually with the browser).
cd "$WORKTREE"
if [ -f "$AUTH_DUMP_JSON" ] && [ -d "/Applications/$APP_NAME.app" ]; then
  ./desktop/macos/scripts/omi-auth-seed.sh "$BUNDLE_ID" "$AUTH_DUMP_JSON" 2>&1 | tail -2 || true
fi

# Launch.
defaults delete "$BUNDLE_ID" ai_clone_plugin_url 2>/dev/null || true
echo "" > /tmp/omi-dev.log

# Bridge: desktop's PluginDiscovery.filePath still reads the legacy
# single-file path (~/.config/omi/ai-clone-plugin.json) but the new
# per-plugin plugin writes ~/.config/omi/ai-clone-plugin-<plugin_type>.json
# (telegram / whatsapp / imessage). Symlink the telegram discovery to
# the legacy path so the desktop's auto-discovery picks it up. Remove
# this once PluginDiscovery.swift learns the per-plugin filenames.
# (P2 from cubic AI review 4601469127: use $HOME instead of a hard-
# coded absolute path so the script works for any user.)
TUNNEL_DISCOVERY="$HOME/.config/omi/ai-clone-plugin-telegram.json"
LEGACY_DISCOVERY="$HOME/.config/omi/ai-clone-plugin.json"
[ -f "$TUNNEL_DISCOVERY" ] && ln -sf "$TUNNEL_DISCOVERY" "$LEGACY_DISCOVERY"

open "/Applications/$APP_NAME.app"
sleep 10
pgrep -f "Omi Computer" >/dev/null 2>&1 && echo "  ✅ desktop running" || echo "  ❌ desktop crashed; check /tmp/omi-dev.log"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
cat <<EOF

════════════════════════════════════════════════════════════════
  Stack is up. PIDs:
    backend:  $(cat $LOGDIR/backend.pid)  → http://127.0.0.1:$BACKEND_PORT
    plugin:   $(cat $LOGDIR/plugin.pid)  → http://127.0.0.1:$PLUGIN_PORT
    desktop:  /Applications/$APP_NAME.app  (bundle id $BUNDLE_ID)

  Logs:
    backend:  $LOGDIR/backend.log
    plugin:   $LOGDIR/plugin.log
    desktop:  $LOGDIR/desktop-build.log  (build) + /tmp/omi-dev.log (runtime)

  Plugin status:
$(curl -sS -H "Authorization: Bearer $PLUGIN_TOKEN" "http://127.0.0.1:$PLUGIN_PORT/status")

  Discovery log:
$(grep "auto-discover\|AIClone" /tmp/omi-dev.log 2>&1 | head -5)

  Stop everything:
    kill \$(cat $LOGDIR/backend.pid $LOGDIR/plugin.pid 2>/dev/null)
════════════════════════════════════════════════════════════════
EOF