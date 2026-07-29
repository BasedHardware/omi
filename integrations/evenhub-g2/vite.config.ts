import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    // The glasses load this app over the LAN from the phone, so the dev server
    // must bind to all interfaces — Vite's default is localhost-only and the
    // phone would get a connection refused.
    host: true,
    port: 5173,
    // Fail loudly instead of silently moving to 5174, which would leave the
    // generated QR code pointing at a dead port.
    strictPort: true,
    // The phone connects by raw LAN IP; allow it explicitly so Vite's host
    // check can't reject the request.
    allowedHosts: true,
  },
})
