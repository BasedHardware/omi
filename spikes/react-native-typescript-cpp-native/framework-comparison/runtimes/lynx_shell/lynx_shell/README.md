# Lynx Omi relay spike

A small Lynx mobile shell with a separate Moonshine desktop surface. Mobile BLE uses the platform Omi GATT adapters; desktop BLE remains a separate follow-up surface.

## Ownership

- **Lynx:** UI, layout, scroll behavior, native-module dispatch, and template loading.
- **Android/iOS shell:** lifecycle, template provider, bundle packaging, permissions, and platform BLE/audio adapters.
- **Shared C++:** packet normalization and bounded protocol operations.
- **TypeScript:** UI and the typed native facade; it does not own BLE or recording lifetime.

The UI starts disconnected and only displays devices returned by real platform scans. No fake devices, recordings, transcripts, or packet controls are exposed.

## Lynx documentation audit

Audited against the current Lynx website source at commit `221d32bcb6296eb765bca0ea313592cc21e79ee5`.

- Scrolling uses the documented `<scroll-view>` container. Lynx documentation explicitly says `view` does not scroll.
- The page uses `scroll-orientation="vertical"`, the documented replacement for `scroll-y`/`scroll-x`.
- The header uses documented `sticky` behavior as a direct child of `scroll-view`, with `flatten: false` for Android.
- The app keeps one child layout model and avoids `<list>` because this page is a short, bounded surface. Lynx recommends `<list>` only for large or virtualized data.
- Template provider registration and one packaged `main.lynx.bundle` path are wired on Android and iOS.
- The native packet seam uses a byte-safe base64 contract.
- Android uses `BluetoothLeScanner`/`BluetoothGatt`; iOS uses `CoreBluetooth`.
- Omi filtering uses service `19b10000-e8f2-537e-4f6c-d104768a1214`; the audio notify characteristic is `19b10001-e8f2-537e-4f6c-d104768a1214`.

The installed Lynx TypeScript declarations do not currently type the documented `sticky` attribute, so the two documented runtime attributes are passed through a narrow local attribute spread. This keeps the rest of the app type-safe and records the version mismatch explicitly.

## Verification

```sh
bun run test
bun run build

cd desktop
bun install
bun run typecheck
bun run build
```

The desktop surface uses the published `@tschk/moonshine` 0.3.7 packages and pins TypeScript to 5.9.3, the newest compiler API release that currently works with Moonshine and Rspeedy. TypeScript 7.0.2 is latest published, but both toolchains fail at runtime because their compiler API calls were removed.
