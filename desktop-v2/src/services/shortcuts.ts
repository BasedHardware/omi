import { register, unregister } from "@tauri-apps/plugin-global-shortcut";

export async function registerShortcuts() {
  // Ask Nooto: Cmd+\ on macOS, Ctrl+\ on Windows/Linux
  await register("CommandOrControl+\\", (event) => {
    if (event.state === "Pressed") {
      // TODO: Toggle floating bar or focus chat
      console.log("Ask Nooto shortcut triggered");
    }
  });
}

export async function unregisterShortcuts() {
  await unregister("CommandOrControl+\\");
}
