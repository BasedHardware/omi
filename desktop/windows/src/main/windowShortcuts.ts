// Keyboard shortcuts handled off the main window's before-input-event.
//
// Ctrl+W hides the main window to the tray — the keyboard equivalent of clicking
// the window's close button (which hides, it does not quit; see the 'close'
// handler in index.ts). macOS gets Cmd+W for free from its SwiftUI Window scene;
// Windows has no built-in binding, so we detect it here.
//
// Extracted from the index.ts handler so the modifier guards are testable without
// an Electron app. The guards matter: on some layouts Ctrl+Alt+W is AltGr+W (a
// real character), and a lone keyUp must not fire a second time — so this only
// matches a keyDown of Ctrl+W with neither Alt nor Meta held.
export type KeyboardInput = {
  type: string
  key: string
  control: boolean
  alt: boolean
  meta: boolean
}

export function isHideWindowShortcut(input: KeyboardInput): boolean {
  return (
    input.type === 'keyDown' &&
    input.control &&
    !input.alt &&
    !input.meta &&
    input.key.toLowerCase() === 'w'
  )
}
