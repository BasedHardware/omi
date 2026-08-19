import { createBrowserCapabilityAdapter } from "./browser-adapters";
import {
  createSameOriginReadTransport,
  DEMO_CURRENTS,
  loadBackendCurrents,
  type BrowserCurrent,
} from "./data";
import { renderApp, type AppViewState } from "./ui";
import "./styles.css";

type BeforeInstallPromptEvent = Event & {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const appElement = document.querySelector<HTMLDivElement>("#app");
if (appElement === null) throw new Error("PWA app root is missing");
const app: HTMLDivElement = appElement;

const capability = createBrowserCapabilityAdapter();
const dataMode: AppViewState["dataMode"] =
  new URLSearchParams(window.location.search).get("data") === "backend"
    ? "backend"
    : "demo";
const state: AppViewState = {
  capability: capability.snapshot(),
  capabilityNotice: null as string | null,
  currents: (dataMode === "demo" ? [...DEMO_CURRENTS] : []) as BrowserCurrent[],
  dataMode,
  dataStatus: dataMode === "demo" ? ("demo" as const) : ("loading" as const),
  installAvailable: false,
  searchQuery: "",
  unavailable: [] as string[],
};
let installPrompt: BeforeInstallPromptEvent | null = null;

function render(): void {
  app.innerHTML = renderApp(state);
  bindEvents();
}

function bindEvents(): void {
  const searchInput = app.querySelector<HTMLInputElement>(
    "[data-search-input]"
  );
  searchInput?.addEventListener("input", (event) => {
    state.searchQuery = (event.currentTarget as HTMLInputElement).value;
    const selection = state.searchQuery.length;
    render();
    const nextInput = app.querySelector<HTMLInputElement>(
      "[data-search-input]"
    );
    nextInput?.focus();
    nextInput?.setSelectionRange(selection, selection);
  });
  app
    .querySelector<HTMLFormElement>("[data-search-form]")
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      searchInput?.focus();
    });
  app
    .querySelectorAll<HTMLElement>('[data-action="clear-search"]')
    .forEach((button) => {
      button.addEventListener("click", () => {
        state.searchQuery = "";
        render();
        app.querySelector<HTMLInputElement>("[data-search-input]")?.focus();
      });
    });
  app
    .querySelector<HTMLButtonElement>('[data-action="bluetooth"]')
    ?.addEventListener("click", async (event) => {
      const button = event.currentTarget as HTMLButtonElement;
      button.disabled = true;
      const result = await capability.chooseBluetoothDevice();
      state.capability = capability.snapshot();
      state.capabilityNotice = result.ok
        ? "Browser Bluetooth selection recorded. Omi identity is still unverified."
        : result.reason === "cancelled"
        ? "Bluetooth chooser cancelled. No device was added."
        : result.reason === "denied"
        ? "Bluetooth permission was not granted. No device was added."
        : result.reason === "unsupported"
        ? "Web Bluetooth is unavailable in this browser."
        : "The browser Bluetooth check failed. No device was added.";
      render();
    });
  app
    .querySelector<HTMLButtonElement>('[data-action="microphone"]')
    ?.addEventListener("click", async (event) => {
      const button = event.currentTarget as HTMLButtonElement;
      button.disabled = true;
      const result = await capability.checkMicrophone();
      state.capability = capability.snapshot();
      state.capabilityNotice = result.ok
        ? "Microphone probe succeeded and its stream was stopped. Omi capture remains unavailable here."
        : result.reason === "unsupported"
        ? "Microphone capture is unavailable in this browser."
        : result.reason === "denied"
        ? "Microphone permission was not granted."
        : "The microphone probe failed.";
      render();
    });
  app
    .querySelector<HTMLButtonElement>('[data-action="install"]')
    ?.addEventListener("click", async () => {
      if (installPrompt === null) return;
      await installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      state.installAvailable = false;
      render();
    });
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event as BeforeInstallPromptEvent;
  state.installAvailable = true;
  render();
});

window.addEventListener("keydown", (event) => {
  if (
    (event.metaKey || event.ctrlKey) &&
    event.key.toLocaleLowerCase() === "k"
  ) {
    event.preventDefault();
    app.querySelector<HTMLInputElement>("[data-search-input]")?.focus();
  }
  if (event.key === "Escape" && state.searchQuery !== "") {
    state.searchQuery = "";
    render();
  }
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => undefined);
}

render();

if (dataMode === "backend") {
  loadBackendCurrents(createSameOriginReadTransport())
    .then((result) => {
      state.currents = result.items;
      state.unavailable = result.unavailable;
      state.dataStatus =
        result.items.length === 0 && result.unavailable.length > 0
          ? "unavailable"
          : "ready";
      render();
    })
    .catch(() => {
      state.dataStatus = "unavailable";
      state.unavailable = ["Backend reads"];
      render();
    });
}
