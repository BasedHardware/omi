/**
 * Companion service — wires `companion:start` / `companion:stop` Tauri events
 * to the Rust commands that show/hide the buddy window and overlay windows,
 * and delegates the AI pipeline to companionAssistant.ts.
 *
 * Call `initCompanion()` once from the main-window root component's useEffect.
 * The overlay windows are also ensured on boot so they exist before the first
 * PTT press.
 */
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { useCompanionStore } from "@/stores/companionStore";
import { useCompanionSettingsStore } from "@/stores/companionSettingsStore";
import { handleCompanionStart, handleCompanionStop } from "@/services/companionAssistant";

let unlisten: UnlistenFn | null = null;
let initialized = false;
/** Monotonic token that guards against StrictMode double-mount listener leaks.
 *  destroyCompanion bumps it; any in-flight initCompanion with a stale token
 *  tears down its own listeners on completion. */
let initToken = 0;

/** Promises for currently-registered companion event listeners, captured
 *  SYNCHRONOUSLY so the HMR dispose hook can always tear them down — even
 *  if Vite fires dispose before `listen()` resolves. Without this the
 *  previous bundle's `companion:start` / `companion:stop` handlers stay
 *  alive on the Rust bridge and fire alongside the new ones, causing
 *  duplicate stop_recording calls and "capture already running" errors. */
const _companionListenPromises: Array<Promise<UnlistenFn>> = [];

export async function initCompanion(): Promise<void> {
  if (initialized) return;
  initialized = true;
  const myToken = ++initToken;

  // Make sure the global PTT rdev listener is actually running. The listener
  // is opt-in (see src-tauri/src/commands/ptt.rs) because starting rdev
  // without Accessibility / Input Monitoring crashes the app. Without this
  // call, Companion's Fn key fires nothing unless the user also happened to
  // trigger the listener via onboarding or the PTT debug panel this session.
  // `ensure_ptt_listener` is idempotent and bails gracefully when permissions
  // aren't granted — safe to call unconditionally.
  try {
    await invoke("ensure_ptt_listener");
  } catch (e) {
    console.warn("[companion] ensure_ptt_listener failed:", e);
  }

  // Push the persisted Companion PTT key to Rust so Fn (or whatever the user
  // picked in Settings) actually triggers companion:start/stop. Without this,
  // the Rust-side default (Fn) is still fine on first run, but changing the
  // key via Settings wouldn't persist across restarts.
  try {
    const companionKey = useCompanionSettingsStore.getState().pttKey;
    await invoke("set_companion_key", { label: companionKey });
  } catch (e) {
    console.warn("[companion] set_companion_key on boot failed:", e);
  }

  // Ensure overlay windows exist before the first PTT press so there's no
  // startup delay when the user first holds the key.
  try {
    await invoke("companion_ensure_overlays");
  } catch (e) {
    console.warn("[companion] ensure_overlays failed:", e);
  }

  const store = useCompanionStore.getState();

  const startPromise = listen("companion:start", async () => {
      // If Companion is disabled in settings, no-op. The PTT listener still
      // fires (it's global) but we skip the AI pipeline entirely.
      if (!useCompanionSettingsStore.getState().companionEnabled) {
        console.log("[companion] companion:start ignored — disabled in settings");
        return;
      }

      // Cancel any in-flight request by bumping the request ID.
      const requestId = store.nextRequestId();
      store.setEnabled(true);

      // CRITICAL: kick off mic recording FIRST, before anything else, so the
      // very first syllable of the user's speech lands on disk. Everything
      // else (buddy window, overlays) happens in parallel. Previously the mic
      // didn't open until ~1s after the keypress because show_buddy was awaited
      // first.
      //
      // Expose the start promise on the module so the stop handler can await
      // it before calling stop_recording. Without this, a quick press-release
      // races start vs stop and the WAV comes out empty.
      pendingStartPromise = handleCompanionStart();

      // Show buddy window in parallel (visual feedback — doesn't block mic).
      Promise.all([invoke("companion_show_buddy"), invoke("companion_ensure_overlays")]).catch(
        (e) => console.warn("[companion] show_buddy failed:", e),
      );

      // Wait for the start pipeline to actually finish so we know the mic is
      // open and the screenshot was captured. The stop handler will also wait
      // on this same promise before stopping.
      await pendingStartPromise;

      // Store the request ID so stop knows which request to honor.
      pendingRequestId = requestId;
    });
  const stopPromise = listen("companion:stop", async () => {
      // If Companion is disabled in settings, no-op (nothing was started).
      if (!useCompanionSettingsStore.getState().companionEnabled) {
        return;
      }

      // Wait for start to finish before stopping. On a very quick press-release
      // this listener can fire before handleCompanionStart has finished
      // opening the mic and capturing the screenshot — stopping mid-setup
      // produces empty WAVs and aborts the Gemini call.
      if (pendingStartPromise) {
        try {
          await pendingStartPromise;
        } catch (e) {
          console.warn("[companion] pending start failed:", e);
        }
      }

      store.setState("thinking");
      store.setEnabled(false);

      const requestId = pendingRequestId;

      // Hand off to the assistant for WAV reading + Gemini call.
      await handleCompanionStop(requestId);

      // Hide the buddy once the answer is available (or on abort).
      const finalState = useCompanionStore.getState().state;
      if (finalState !== "speaking") {
        // If something aborted, hide the buddy.
        try {
          await invoke("companion_hide_buddy");
        } catch (e) {
          console.warn("[companion] hide_buddy failed:", e);
        }
      }
    });

  // Capture the promises synchronously into the module-level array so the
  // HMR dispose hook can tear them down even if it fires before listen()
  // resolves. Then await them so we have the actual unlisteners for the
  // race-cleanup token check below.
  _companionListenPromises.push(startPromise, stopPromise);
  const [unlistenStart, unlistenStop] = await Promise.all([startPromise, stopPromise]);

  // If destroyCompanion fired while we were awaiting listen() registration,
  // our token is stale — tear our listeners down immediately instead of
  // leaving them dangling. Prevents a StrictMode double-mount leak.
  if (myToken !== initToken) {
    unlistenStart();
    unlistenStop();
    return;
  }

  // Subscribe to companion state transitions. Whenever state goes back to
  // `idle` AND no chain is in flight, the interaction is fully done — hide
  // the buddy. This is a belt-and-suspenders cleanup that catches every path:
  // TTS finish, Gemini error, chain end, manual reset. Without it, certain
  // paths leave the orb following the cursor forever.
  const unsubState = useCompanionStore.subscribe((s, prev) => {
    if (prev.state !== "idle" && s.state === "idle" && !s.chain) {
      invoke("companion_hide_buddy").catch(() => {});
    }
  });

  unlisten = () => {
    unlistenStart();
    unlistenStop();
    unsubState();
  };
}

// Vite HMR — when this module reloads, tear down the listeners the *previous*
// instance registered before the new one runs. Without this, every file save
// adds another companion:start/stop listener to the Rust bridge, causing the
// "stop_recording fires twice / capture already running" symptom.
if (import.meta.hot) {
  import.meta.hot.dispose(async () => {
    const results = await Promise.allSettled(_companionListenPromises);
    for (const r of results) {
      if (r.status === "fulfilled") {
        try {
          r.value();
        } catch {
          /* already unsubscribed */
        }
      }
    }
    _companionListenPromises.length = 0;
  });
}

export function destroyCompanion(): void {
  initToken += 1; // invalidate any in-flight initCompanion awaits
  if (unlisten) {
    unlisten();
    unlisten = null;
  }
  initialized = false;
}

// Module-level request ID that the stop handler reads.
// We use this (rather than a store field) to avoid async race with store
// reads between start and stop.
let pendingRequestId = 0;

// Promise for the currently-in-flight handleCompanionStart. The stop handler
// awaits this so a quick press-release doesn't race start vs stop.
let pendingStartPromise: Promise<void> | null = null;
