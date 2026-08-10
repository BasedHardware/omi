# Moonshine desktop surface

This is a separate desktop/web surface for the spike using the published `@tschk/moonshine` 0.3.7 packages.

It deliberately shows **Bluetooth not connected**. There is no fake device, recording, or transcript path here. The next implementation seam is a real desktop-native BLE adapter that consumes the shared relay contract.

Commands:

```sh
bun install
bun run typecheck
bun run build
bun run dev
```
