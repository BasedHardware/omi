# Just Commands - Quick Start

## Install `just` (one time)
```bash
cargo install just
# or on Ubuntu/Debian:
# sudo apt install just
```

## Most Common Commands

### 🚀 Daily Development
```bash
just deploy          # Build debug APK + install to phone (most common!)
just quick           # Same as deploy (alias)
just fresh           # Clean rebuild + install
just nuke            # Nuclear option: kill, uninstall, clean, rebuild, install
```

### 🔨 Build Only
```bash
just build-debug     # Build debug APK
just build-release   # Build release APK
just clean           # Clean build artifacts
```

### 📱 Install & Control
```bash
just install         # Install debug APK to phone
just uninstall       # Remove app from phone
just kill            # Stop the running app
just launch          # Start the app
just restart         # Kill + launch
```

### 📋 Logs
```bash
just logs            # View filtered logs (Flutter, Omi, Webhook)
just logs-clear      # Clear logcat + view fresh logs
just logs-crash      # View crash logs only
```

### 🧪 Testing
```bash
just test            # Run all tests
just test-webhook    # Run webhook tests only
just coverage        # Generate HTML coverage report
```

### ✅ Quality Checks
```bash
just format          # Format code
just analyze         # Run analyzer
just check           # Format + analyze + test
just pre-commit      # Run before committing
```

## Tips

1. **See all commands**: `just` or `just --list`
2. **Most common workflow**: `just deploy`
3. **Change device**: Edit `DEVICE` variable in justfile
4. **Morning routine**: `just morning` (clean, build, install, launch, logs)

## Examples

```bash
# Quick iteration cycle
just deploy          # Build + install
just logs           # View logs in another terminal

# Clean slate testing
just nuke           # Full reset
just logs-clear     # Watch logs

# Before committing
just pre-commit     # Format, analyze, test

# Release build
just release        # Run tests, clean, build release APK
```

That's it! Just type `just deploy` and you're good to go! 🚀
