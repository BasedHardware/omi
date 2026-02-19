---
name: local-dev
description: Start local development environment with backend and macOS app
allowed-tools: Bash
---

# Start Local Development Environment

Start the backend server and macOS app for local development.

## Usage

Run `/local-dev` to start both the backend and app, or:
- `/local-dev backend` - start backend only
- `/local-dev app` - build and run the macOS app (debug mode)
- `/local-dev app --clean` - clean build and run (forces Swift recompilation)
- `/local-dev app --release` - build and run in release mode

## Commands

### Backend
```bash
cd backend
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
python3 -c "from dotenv import load_dotenv; load_dotenv(); import subprocess; subprocess.run(['python3', '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'])"
```

### App
```bash
app/scripts/dev-macos.sh $EXTRA_ARGS
```

Where `$EXTRA_ARGS` can be:
- `--clean` - force clean build (removes build cache, ensures Swift recompilation)
- `--release` - build in release mode instead of debug
- `--no-run` - build only, don't launch the app

## Argument Handling

When `$ARGUMENTS` is "backend", only start the backend.
When `$ARGUMENTS` is "app", build and run the macOS app.
When `$ARGUMENTS` starts with "app ", pass remaining args to the script (e.g., "app --clean").
When `$ARGUMENTS` is empty or "all", start both backend and app.
