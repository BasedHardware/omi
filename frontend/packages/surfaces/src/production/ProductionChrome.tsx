import * as React from "react";
import { t } from "@omi-core/i18n";
import {
  commandLabel,
  createProductionCommandRegistry,
  dispatchProductionCommand,
  isApplePlatform,
  type ProductionCommandContext,
  type ProductionCommandId,
} from "./command-registry.js";

type Locale = string;
// Chat, Settings and Listen are real routes (board ruling PR-7) but they are NOT yet
// persistent nav destinations: their shell slots belong to Ink/WindowGlass (PR #11117).
// They remain first-class command-registry destinations so every live route is discoverable
// without a surface author inventing a new chrome slot.
import type { ProductionRoute } from "./command-registry.js";
type ChromeIconName = "home" | "library" | "tasks" | "rewind" | "apps" | "conversations" | "microphone" | "screen" | "settings";
type ThemeSelection = "default" | "system" | "light" | "dark";

type CommandHandler = (event?: KeyboardEvent) => void | Promise<void>;
type ShellIsolationRecord = {
  element: HTMLElement;
  inert: boolean;
  ariaHidden: string | null;
};

const commandRegistry = createProductionCommandRegistry();
const commandPopupRole: "dialog" = "dialog";

function paletteFocusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(
    "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex=\"-1\"])",
  ));
}

function ChromeIcon({ name }: { name: ChromeIconName }): React.JSX.Element {
  const paths: Record<ChromeIconName, React.JSX.Element> = {
    // PR #11117 makes Home the query shell, so its persistent destination is
    // search-shaped rather than a second dashboard/house metaphor.
    home: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
    library: <><path d="M4 4h4v16H4zM10 7h4v13h-4zM16 3h4v17h-4z" /></>,
    tasks: <><path d="m4 7 2 2 3-4M11 7h9M4 14l2 2 3-4M11 14h9" /></>,
    rewind: <><path d="M4 8V3m0 0h5M4 3l4 4" /><path d="M5 13a8 8 0 1 0 2-6" /><path d="M12 7v5l3 2" /></>,
    apps: <><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></>,
    conversations: <><path d="M20 12a7 7 0 0 1-8 7l-4 2 1-4a7 7 0 1 1 11-5Z" /></>,
    microphone: <><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6" /></>,
    screen: <><rect x="3" y="4" width="18" height="13" rx="3" /><path d="M8 21h8M12 17v4" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}

function href(route: ProductionRoute): string {
  const params = new URLSearchParams(location.search);
  // Navigation leaves platform/locale/profile QA context intact, but a route
  // change must not accidentally pin the next screen to a previous fixture or
  // selected detail row.
  params.delete("qa");
  params.delete("state");
  params.delete("conversation");
  params.set("route", route);
  return `?${params.toString()}`;
}

function activeThemeSelection(): ThemeSelection {
  const value = new URLSearchParams(location.search).get("theme");
  return value === "system" || value === "light" || value === "dark" ? value : "default";
}

function ProductionThemeControl({ locale, mobile = false }: { locale: Locale; mobile?: boolean }): React.JSX.Element {
  const navigate = (selection: ThemeSelection): void => {
    const params = new URLSearchParams(location.search);
    if (selection === "default") params.delete("theme");
    else params.set("theme", selection);
    location.search = params.toString();
  };
  return (
    <label className={`theme-mode-control${mobile ? " is-mobile" : ""}`} title={t(locale, "appearance.title")}>
      <ChromeIcon name="settings" />
      <span className="visually-hidden">{t(locale, "appearance.title")}</span>
      <select aria-label={t(locale, "appearance.title")} value={activeThemeSelection()} onChange={(event) => navigate(event.target.value as ThemeSelection)}>
        <option value="default">{t(locale, "appearance.default")}</option>
        <option value="system">{t(locale, "appearance.system")}</option>
        <option value="light">{t(locale, "appearance.light")}</option>
        <option value="dark">{t(locale, "appearance.dark")}</option>
      </select>
    </label>
  );
}

export function ProductionChrome({ locale, active, placement = "top", commandHandlers, commandEnabled }: {
  locale: Locale;
  active: ProductionRoute;
  placement?: "top" | "bottom";
  commandHandlers?: Partial<Record<ProductionCommandId, CommandHandler>>;
  commandEnabled?: Partial<Record<ProductionCommandId, boolean>>;
}): React.JSX.Element {
  const top = placement === "top";
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const paletteTriggerRef = React.useRef<HTMLButtonElement>(null);
  const paletteRef = React.useRef<HTMLDivElement>(null);
  const navRef = React.useRef<HTMLElement>(null);
  const shellIsolationRef = React.useRef<ShellIsolationRecord[]>([]);
  const paletteReturnFocusRef = React.useRef<HTMLElement | null>(null);
  const paletteWasOpenRef = React.useRef(false);
  const navigate = React.useCallback((route: ProductionRoute): void => {
    location.href = href(route);
  }, []);
  const openPalette = React.useCallback((): void => {
    const focused = document.activeElement;
    paletteReturnFocusRef.current = focused instanceof HTMLElement && focused !== document.body
      ? focused
      : paletteTriggerRef.current;
    setPaletteOpen(true);
  }, []);
  const context = React.useMemo<ProductionCommandContext>(() => ({
    activeRoute: active,
    navigate,
    handlers: {
      ...commandHandlers,
      "open-command-palette": openPalette,
      "close-command-palette": () => setPaletteOpen(false),
    },
    enabled: {
      ...commandEnabled,
      "open-command-palette": true,
      "close-command-palette": paletteOpen,
    },
    paletteOpen,
  }), [active, commandEnabled, commandHandlers, navigate, openPalette, paletteOpen]);

  React.useEffect(() => {
    if (!top) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      dispatchProductionCommand(event, commandRegistry, context);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [context, top]);

  const restoreShellIsolation = React.useCallback((): void => {
    const records = shellIsolationRef.current;
    shellIsolationRef.current = [];
    for (const record of records) {
      const inertElement = record.element as HTMLElement & { inert?: boolean };
      inertElement.inert = record.inert;
      if (record.ariaHidden === null) record.element.removeAttribute("aria-hidden");
      else record.element.setAttribute("aria-hidden", record.ariaHidden);
    }
  }, []);

  const isolateShell = React.useCallback((): HTMLElement | null => {
    const shell = navRef.current?.closest<HTMLElement>("[data-production-shell='true']") ?? null;
    if (!shell) return null;
    restoreShellIsolation();
    const backdrop = shell.querySelector<HTMLElement>(".command-palette-backdrop");
    const siblings = Array.from(shell.children).filter((element): element is HTMLElement => (
      element instanceof HTMLElement && element !== backdrop
    ));
    shellIsolationRef.current = siblings.map((element) => {
      const inertElement = element as HTMLElement & { inert?: boolean };
      const record = {
        element,
        inert: Boolean(inertElement.inert),
        ariaHidden: element.getAttribute("aria-hidden"),
      } satisfies ShellIsolationRecord;
      inertElement.inert = true;
      element.setAttribute("aria-hidden", "true");
      return record;
    });
    return shell;
  }, [restoreShellIsolation]);

  React.useEffect(() => {
    if (!paletteOpen) {
      restoreShellIsolation();
      return undefined;
    }
    const shell = isolateShell();
    if (!shell) return undefined;
    const isPaletteTarget = (target: EventTarget | null): boolean => {
      const backdrop = shell.querySelector<HTMLElement>(".command-palette-backdrop");
      return target instanceof HTMLElement && Boolean(backdrop?.contains(target));
    };
    const blockBackgroundEvent = (event: Event): void => {
      if (isPaletteTarget(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
    };
    const redirectBackgroundFocus = (event: FocusEvent): void => {
      if (isPaletteTarget(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      paletteRef.current?.focus();
    };
    const blockedEventTypes = ["click", "pointerdown", "pointerup", "keydown", "keyup", "input", "change", "submit"] as const;
    for (const type of blockedEventTypes) shell.addEventListener(type, blockBackgroundEvent, true);
    shell.addEventListener("focusin", redirectBackgroundFocus, true);
    return () => {
      for (const type of blockedEventTypes) shell.removeEventListener(type, blockBackgroundEvent, true);
      shell.removeEventListener("focusin", redirectBackgroundFocus, true);
      restoreShellIsolation();
    };
  }, [isolateShell, paletteOpen, restoreShellIsolation]);

  React.useEffect(() => {
    if (!paletteOpen && paletteWasOpenRef.current) {
      const target = paletteReturnFocusRef.current;
      if (target?.isConnected) target.focus();
      else paletteTriggerRef.current?.focus();
      paletteReturnFocusRef.current = null;
    }
    if (paletteOpen) paletteRef.current?.focus();
    paletteWasOpenRef.current = paletteOpen;
  }, [paletteOpen]);

  const handlePaletteKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key !== "Tab") return;
    const palette = paletteRef.current;
    if (!palette) return;
    const focusable = paletteFocusableElements(palette);
    if (focusable.length === 0) {
      event.preventDefault();
      palette.focus();
      return;
    }
    const index = focusable.indexOf(document.activeElement as HTMLElement);
    if (event.shiftKey ? index <= 0 : index === -1 || index === focusable.length - 1) {
      event.preventDefault();
      (event.shiftKey ? focusable[focusable.length - 1] : focusable[0])?.focus();
    }
  };

  const invoke = (id: ProductionCommandId): void => {
    const command = commandRegistry.find((candidate) => candidate.id === id);
    if (!command || !command.isEnabled(context)) return;
    void command.invoke(context);
    if (id !== "open-command-palette") setPaletteOpen(false);
  };

  return (
    <>
      <nav ref={navRef} className={`production-nav${top ? "" : " production-nav-bottom"}`} aria-label={t(locale, top ? "nav.primary" : "nav.mobile")}>
        {top ? (
          <div className="nav-desktop">
            <div className="nav-primary">
              <a href={href("home")} aria-current={active === "home" ? "page" : undefined}><ChromeIcon name="home" /><span className="nav-label">{t(locale, "nav.home")}</span></a>
              <a href={href("memories")} aria-current={active === "memories" || active === "conversations" || active === "folders" ? "page" : undefined}><ChromeIcon name="library" /><span className="nav-label">{t(locale, "nav.library")}</span></a>
              <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}><ChromeIcon name="tasks" /><span className="nav-label">{t(locale, "nav.tasks")}</span></a>
            </div>
            <div className="nav-utilities" aria-label={t(locale, "nav.settings")}>
              <button type="button" className="nav-icon-control" disabled aria-disabled="true" aria-label={t(locale, "nav.microphone")} title={t(locale, "nav.microphone")}><ChromeIcon name="microphone" /></button>
              <button type="button" className="nav-icon-control" disabled aria-disabled="true" aria-label={t(locale, "nav.screenCapture")} title={t(locale, "nav.screenCapture")}><ChromeIcon name="screen" /></button>
              <button ref={paletteTriggerRef} type="button" className="command-discovery-trigger" onClick={openPalette} aria-haspopup={commandPopupRole} aria-expanded={paletteOpen} title={t(locale, "tasks.shortcuts")}>
                <span className="nav-label">{t(locale, "tasks.shortcuts")}</span>
                <kbd>{commandLabel(commandRegistry[0]!, isApplePlatform() ? "apple" : "other")}</kbd>
              </button>
              <ProductionThemeControl locale={locale} />
            </div>
          </div>
        ) : null}
        {top ? <div className="mobile-topbar">
          <span className="mobile-brand">{t(locale, "app.name")}</span>
          <ProductionThemeControl locale={locale} mobile />
        </div> : null}
        <div className="nav-mobile">
          <a href={href("home")} aria-current={active === "home" ? "page" : undefined}><ChromeIcon name="home" /><span className="nav-label">{t(locale, "nav.home")}</span></a>
          <a href={href("conversations")} aria-current={active === "conversations" || active === "memories" || active === "folders" ? "page" : undefined}><ChromeIcon name="conversations" /><span className="nav-label">{t(locale, "nav.conversations")}</span></a>
          <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}><ChromeIcon name="tasks" /><span className="nav-label">{t(locale, "nav.tasks")}</span></a>
        </div>
      </nav>
      {top && paletteOpen ? <div className="command-palette-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPaletteOpen(false); }}>
        <section ref={paletteRef} className="command-palette" role="dialog" aria-modal={Boolean(true)} aria-labelledby="production-command-title" tabIndex={-1} onKeyDown={handlePaletteKeyDown}>
          <header className="command-palette-header">
            <h2 id="production-command-title">{t(locale, "tasks.shortcuts")}</h2>
            <button type="button" onClick={() => setPaletteOpen(false)} aria-label={t(locale, "common.close")}>{t(locale, "common.close")}</button>
          </header>
          <p className="command-palette-hint">{t(locale, "shortcuts.openSearch")}<span className="command-hint-separator" aria-hidden="true" />{commandLabel(commandRegistry[0]!, isApplePlatform() ? "apple" : "other")}</p>
          <ul className="command-palette-list">
            {commandRegistry.filter((command) => command.id !== "close-command-palette").map((command) => {
              const enabled = command.isEnabled(context);
              return <li key={command.id}>
                <button type="button" disabled={!enabled} onClick={() => invoke(command.id)}>
                  <span>{t(locale, command.labelKey, undefined as never)}</span>
                  {(command.chord || command.chords) && <kbd>{commandLabel(command, isApplePlatform() ? "apple" : "other")}</kbd>}
                </button>
              </li>;
            })}
          </ul>
        </section>
      </div> : null}
    </>
  );
}

export function ProductionLibrarySegment({ locale, active }: { locale: Locale; active: "memories" | "conversations" }): React.JSX.Element {
  return <>
    <nav className="desktop-library-segment" aria-label={t(locale, "nav.library")}>
      <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
      <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.memories")}</a>
    </nav>
    <nav className="mobile-library-segment" aria-label={t(locale, "nav.library")}>
      <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
      <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.memories")}</a>
    </nav>
  </>;
}
