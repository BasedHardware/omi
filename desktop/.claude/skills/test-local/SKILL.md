# test-local: Build, Run, and Test Desktop App Locally

Use this skill when the user says "test it", "try it", "run it", or similar — to build, launch, and verify the desktop app using macOS automation.

## CRITICAL: Always use `run.sh` to launch

**NEVER** manually copy binaries into `build/Omi Dev.app` and launch from there. **NEVER** run `open "build/Omi Dev.app"`. The app **MUST** be launched via `./run.sh` (or `./reset-and-run.sh`), which installs to `/Applications/Omi Dev.app` and launches from there. This is required because macOS "Quit & Reopen" (triggered by granting screen recording permission) uses LaunchServices to find the app — if the canonical copy is in `build/`, macOS will launch a stale binary or fail to find it.

## Quick Reference

| Item | Value |
|------|-------|
| Build command | `xcrun swift build -c debug --package-path Desktop` |
| Full run script | `./run.sh` (builds Swift + Rust backend + tunnel + launches app) |
| App name | **Omi Dev** |
| Bundle ID | `com.omi.desktop-dev` |
| App log | `/private/tmp/omi-dev.log` |
| run.sh output | `/private/tmp/run-sh-output.log` |
| Build time | ~2-4 min (swift build), ~3-7 min (full run.sh) |
| Working directory | `desktop/` |

## Workflow

### Step 1: Kill existing instances

Clean up stale processes from previous runs before starting fresh:

```bash
cd /Users/matthewdi/omi/desktop
pkill -f "Omi Dev.app" 2>/dev/null || true
pkill -f "cloudflared.*omi-computer-dev" 2>/dev/null || true
lsof -ti:8080 -sTCP:LISTEN 2>/dev/null | while read pid; do
    if ps -p "$pid" -o command= 2>/dev/null | grep -q "omi-backend\|Backend-Rust\|target/"; then
        kill -9 "$pid" 2>/dev/null || true
    fi
done
```

### Step 2: Build only (catch errors early)

Run the Swift build first to catch compilation errors before committing to the full `run.sh` cycle. This saves 3-5 minutes if there's a typo or missing import.

```bash
cd /Users/matthewdi/omi/desktop && xcrun swift build -c debug --package-path Desktop 2>&1
```

- If the build **fails**, stop here. Fix the errors, then retry this step.
- If the build **succeeds**, proceed to Step 3.

### Step 3: Run `run.sh` in background

`run.sh` is a long-running foreground process (it keeps the Rust backend alive via `wait`). Run it with `nohup` so it survives in the background:

```bash
cd /Users/matthewdi/omi/desktop && nohup ./run.sh > /private/tmp/run-sh-output.log 2>&1 &
RUN_SH_PID=$!
echo "run.sh PID: $RUN_SH_PID"
```

### Step 4: Wait for app to launch

Poll for the app process every 15 seconds, up to 10 minutes. Also check if `run.sh` exited early (build failure, port conflict, etc.):

```bash
for i in $(seq 1 40); do
    if pgrep -f "Omi Dev" > /dev/null 2>&1; then
        echo "App is running!"
        break
    fi
    # Check if run.sh died
    if ! kill -0 $RUN_SH_PID 2>/dev/null; then
        echo "run.sh exited early! Check /private/tmp/run-sh-output.log"
        tail -30 /private/tmp/run-sh-output.log
        break
    fi
    echo "Waiting for app to launch... ($i/40)"
    sleep 15
done
```

### Step 5: Test with `macos-use`

Once the app is running, use the `macos-use` MCP tools to interact with it:

1. **Open and traverse**: Use `macos-use_open_application_and_traverse` with identifier `"Omi Dev"` to get the accessibility tree
2. **Read the traversal file**: Use `Grep` or `Read` on the returned file to find specific UI elements
3. **Interact**: Use `macos-use_click_and_traverse`, `macos-use_type_and_traverse`, `macos-use_scroll_and_traverse` to click buttons, type text, scroll, etc.
4. **Verify**: Check that the expected UI elements, text, or behavior is present in the accessibility tree after interactions

### Step 6: Check logs

If something isn't working as expected:

```bash
# App logs (Swift print statements)
tail -50 /private/tmp/omi-dev.log

# run.sh output (build output, backend logs, errors)
tail -50 /private/tmp/run-sh-output.log
```

### Step 7: Iterate

If the test reveals a bug or the feature doesn't work:

1. Kill the app and processes (Step 1)
2. Fix the code
3. Go back to Step 2 (build only) to verify it compiles
4. Then Step 3 (run.sh) to test again

**IMPORTANT**: Always re-run `./run.sh` for each iteration. Do NOT take shortcuts like manually copying the binary into the app bundle and launching from `build/`. This breaks LaunchServices registration and causes macOS permission restarts to launch stale binaries.

### Step 8: Clean up

When testing is complete and everything works:

```bash
pkill -f "Omi Dev.app" 2>/dev/null || true
pkill -f "cloudflared.*omi-computer-dev" 2>/dev/null || true
lsof -ti:8080 -sTCP:LISTEN 2>/dev/null | while read pid; do
    if ps -p "$pid" -o command= 2>/dev/null | grep -q "omi-backend\|Backend-Rust\|target/"; then
        kill -9 "$pid" 2>/dev/null || true
    fi
done
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `run.sh` exits immediately | Check `/private/tmp/run-sh-output.log` — usually a build error or port 8080 already in use |
| App launches but crashes | Check `/private/tmp/omi-dev.log` and use `crash-report` skill |
| SwiftPM workspace locked | Another `swift build` is running — wait for it or `pkill -f swift-build` |
| Port 8080 in use | `lsof -ti:8080 \| xargs kill -9` then retry |
| Accessibility tree empty | App may still be loading — wait a few seconds and re-traverse |
| macOS permission dialogs | Use `macos-use` to click "Allow" / "OK" on any system dialogs |
