# Omi Development Notes

## Known Issues and Solutions

### Sign Language Avatar Not Rendering (Linux/Wayland)

**Issue:**
The skeletal avatar (pose-viewer) would not render on the Sign Language and Sign Test pages.

**Symptoms:**
- Avatar output area remained black/empty.
- Logs showed `EGL_BAD_MATCH` and `Failed to record frame` errors related to Wayland/EGL.
- `AvatarSandbox` (iframe/CDN based) failed to initialize or communicate the pose.

**Cause:**
1. **Sandbox Overhead**: The `AvatarSandbox` used an iframe and CDN, which introduced race conditions and communication overhead.
2. **CSP Restrictions**: The Content Security Policy (CSP) in `index.html` did not allow `data:` URIs for `media-src`, preventing Base64 encoded videos from playing.
3. **Blob URL Issues**: In some Electron/Linux environments, converting Base64 to Blob URLs for videos caused playback failures.

**Solution:**
1. **Component Migration**: Replaced `AvatarSandbox` with `SignAvatar`. `SignAvatar` uses the bundled `pose-viewer` dependency, eliminating the iframe and network dependency.
2. **CSP Update**: Added `data:` to the `media-src` directive in `src/renderer/index.html`.
3. **Direct Data URI Playback**: Modified `SignVideo.tsx` to use `data:` URIs directly instead of converting them to Blob URLs.
4. **Explicit Playback**: Added a `useEffect` to explicitly call `.play()` on the video element using a `ref` to bypass `autoPlay` restrictions.
