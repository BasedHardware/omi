# Screen Recording Setup Guide

## How Screen Recording Works

Omi uses Electron's `getUserMedia` API with `chromeMediaSource: 'desktop'` to capture screen content. On Linux/NixOS with Wayland, this requires PipeWire support (already enabled in the app via `WebRTCPipeWireCapturer`).

## Linux/NixOS Setup

### 1. Install Required Packages

```nix
# In your configuration.nix or shell.nix
environment.systemPackages = with pkgs; [
  # Required for screen capture
  pipewire
  xdg-desktop-portal
  xdg-desktop-portal-wlr  # For Wayland
  
  # Required for OCR (optional but recommended)
  tesseract
  
  # Required for audio
  ffmpeg
];
```

### 2. Enable PipeWire

Make sure PipeWire is running:
```bash
systemctl --user start pipewire
systemctl --user start pipewire-pulse
```

### 3. Grant Screen Capture Permissions

The app auto-grants `display-capture` permissions on Linux (see `src/main/index.ts:279-293`). However, your desktop environment may still prompt for permission.

**GNOME/KDE on Wayland:**
- The first time you record, a portal dialog should appear
- Select "Share" or "Allow" to grant screen access

**If the portal dialog doesn't appear:**
```bash
# Restart the portal
systemctl --user restart xdg-desktop-portal
```

### 4. Verify Screen Capture Works

1. Launch the app: `appimage-run dist/omi-windows-1.0.0.AppImage`
2. Go to Settings → Enable "Rewind" (background screen capture)
3. Check the console for `[rewind]` log messages indicating frames are being captured

## Troubleshooting

### "Permission denied" or blank screen

**Cause:** Desktop portal not granting screen capture access.

**Fix:**
```bash
# Check if portal is running
systemctl --user status xdg-desktop-portal

# Restart it
systemctl --user restart xdg-desktop-portal

# For NixOS, ensure the portal config is correct
mkdir -p ~/.config/xdg-desktop-portal
cat > ~/.config/xdg-desktop-portal/portals.conf << EOF
[preferred]
default=wlr
EOF
```

### No OCR text (screen content not read)

**Cause:** Tesseract not installed or `win-ocr-helper.exe` not available (Windows-only).

**Fix:**
```bash
# Install Tesseract
nix-env -iA nixpkgs.tesseract

# Verify installation
tesseract --version
```

### Screen capture works but frames are black

**Cause:** GPU acceleration issues or window composition.

**Fix:**
```bash
# Try disabling GPU acceleration
appimage-run dist/omi-windows-1.0.0.AppImage --disable-gpu

# Or set the ozone platform hint
appimage-run dist/omi-windows-1.0.0.AppImage --ozone-platform-hint=auto
```

### App crashes on screen capture start

**Cause:** PipeWire not running or incompatible.

**Fix:**
```bash
# Check PipeWire status
pw-cli info 0

# Restart PipeWire
systemctl --user restart pipewire
```

## Recording Modes

### 1. Always-On Rewind (Background Capture)
- Runs continuously while the app is open
- Captures screen frames every ~1 second
- OCR text extracted for search and context
- Controlled via Settings → Rewind toggle

### 2. User-Initiated Recording
- Click the microphone icon to start
- Choose "Mic only" or "Screen + Mic"
- For screen mode, select a window or screen
- Transcript saved when you stop recording

### 3. Voice Agent
- Full STT + LLM + TTS pipeline
- Captures mic audio, processes through Deepgram
- Transcripts auto-saved with summaries

## Permissions Summary

| Permission | Where | Auto-Granted? |
|------------|-------|---------------|
| `media` | Main process | Yes |
| `microphone` | Main process | Yes |
| `display-capture` | Main process | Yes |
| Desktop portal | OS level | No (user must approve first time) |

## Architecture

```
Renderer: getUserMedia({ chromeMediaSource: 'desktop' })
    ↓
Hidden <video> element (1x1px)
    ↓ (every ~1s)
Canvas drawImage → toBlob(JPEG) → IPC to main
    ↓
Main process: ingestRewindFrame()
    ↓
1. Get foreground window info (Linux: stub)
2. Dedup check
3. Write JPEG to disk
4. OCR via Tesseract (Linux) or win-ocr-helper (Windows)
5. Store in SQLite
```
