import { t } from "@omi-core/i18n";

type Locale = string;
type ProductionRoute = "memories" | "conversations" | "tasks";
type ChromeIconName = "home" | "library" | "tasks" | "rewind" | "apps" | "conversations" | "microphone" | "screen" | "settings";

function ChromeIcon({ name }: { name: ChromeIconName }): React.JSX.Element {
  const paths: Record<ChromeIconName, React.JSX.Element> = {
    home: <><path d="m3 11 9-8 9 8" /><path d="M5 10v10h14V10M9 20v-6h6v6" /></>,
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

export function ProductionChrome({ locale, active, placement = "top" }: {
  locale: Locale;
  active: ProductionRoute;
  placement?: "top" | "bottom";
}): React.JSX.Element {
  const top = placement === "top";
  return (
    <>
      <nav className={`production-nav${top ? "" : " production-nav-bottom"}`} aria-label={t(locale, "nav.library")}>
        {top ? (
          <div className="nav-desktop">
            <div className="nav-primary">
              <span aria-disabled="true"><ChromeIcon name="home" />{t(locale, "nav.home")}</span>
              <a href={href("memories")} aria-current={active === "memories" || active === "conversations" ? "page" : undefined}><ChromeIcon name="library" />{t(locale, "nav.library")}</a>
              <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}><ChromeIcon name="tasks" />{t(locale, "nav.tasks")}</a>
              <span aria-disabled="true"><ChromeIcon name="rewind" />{t(locale, "nav.rewind")}</span>
              <span aria-disabled="true"><ChromeIcon name="apps" />{t(locale, "nav.apps")}</span>
            </div>
            <div className="nav-utilities" aria-label={t(locale, "nav.settings")}>
              <span className="nav-icon-control" aria-disabled="true" title={t(locale, "nav.microphone")}><ChromeIcon name="microphone" /><span className="visually-hidden">{t(locale, "nav.microphone")}</span></span>
              <span className="nav-icon-control" aria-disabled="true" title={t(locale, "nav.screenCapture")}><ChromeIcon name="screen" /><span className="visually-hidden">{t(locale, "nav.screenCapture")}</span></span>
              <span className="nav-icon-control" aria-disabled="true" title={t(locale, "nav.settings")}><ChromeIcon name="settings" /><span className="visually-hidden">{t(locale, "nav.settings")}</span></span>
            </div>
          </div>
        ) : null}
        <div className="nav-mobile">
          <span aria-disabled="true"><ChromeIcon name="home" />{t(locale, "nav.home")}</span>
          <a href={href("conversations")} aria-current={active === "conversations" || active === "memories" ? "page" : undefined}><ChromeIcon name="conversations" />{t(locale, "nav.conversations")}</a>
          <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}><ChromeIcon name="tasks" />{t(locale, "nav.tasks")}</a>
          <span aria-disabled="true"><ChromeIcon name="apps" />{t(locale, "nav.apps")}</span>
        </div>
      </nav>
    </>
  );
}

export function ProductionLibrarySegment({ locale, active }: { locale: Locale; active: "memories" | "conversations" }): React.JSX.Element {
  return <>
    <div className="desktop-library-segment" aria-label={t(locale, "nav.library")}>
      <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
      <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.memories")}</a>
      <span aria-disabled="true">{t(locale, "nav.brainMap")}</span>
    </div>
    <div className="mobile-library-segment" aria-label={t(locale, "nav.library")}>
      <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
      <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.memories")}</a>
    </div>
  </>;
}
