# Moonshine desktop surface

This is a separate desktop/web surface for the spike using the published `@tschk/moonshine` 0.3.7 packages.

This desktop surface deliberately has no fake Bluetooth path. Mobile Omi BLE is implemented in the Lynx Android/iOS shells; desktop Bluetooth remains platform-specific work rather than a simulated adapter.

Commands:

```sh
bun install
bun run typecheck
bun run build
bun run dev
```
