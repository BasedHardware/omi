import { t } from "@omi-core/i18n";

type Locale = string;
type ProductionRoute = "memories" | "conversations" | "tasks";
type ChromeIconName = "home" | "library" | "tasks" | "rewind" | "apps" | "conversations";

function ChromeIcon({ name }: { name: ChromeIconName }): React.JSX.Element {
  const paths: Record<ChromeIconName, React.JSX.Element> = {
    home: <><path d="m3 11 9-8 9 8" /><path d="M5 10v10h14V10M9 20v-6h6v6" /></>,
    library: <><path d="M4 4h4v16H4zM10 7h4v13h-4zM16 3h4v17h-4z" /></>,
    tasks: <><path d="m4 7 2 2 3-4M11 7h9M4 14l2 2 3-4M11 14h9" /></>,
    rewind: <><path d="M4 8V3m0 0h5M4 3l4 4" /><path d="M5 13a8 8 0 1 0 2-6" /><path d="M12 7v5l3 2" /></>,
    apps: <><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></>,
    conversations: <><path d="M20 12a7 7 0 0 1-8 7l-4 2 1-4a7 7 0 1 1 11-5Z" /></>,
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
          </div>
        ) : null}
        <div className="nav-mobile">
          <span aria-disabled="true"><ChromeIcon name="home" />{t(locale, "nav.home")}</span>
          <a href={href("conversations")} aria-current={active === "conversations" || active === "memories" ? "page" : undefined}><ChromeIcon name="conversations" />{t(locale, "nav.conversations")}</a>
          <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}><ChromeIcon name="tasks" />{t(locale, "nav.tasks")}</a>
          <span aria-disabled="true"><ChromeIcon name="apps" />{t(locale, "nav.apps")}</span>
        </div>
      </nav>
      {top && active !== "tasks" && <>
        <div className="desktop-library-segment" aria-label={t(locale, "nav.library")}>
          <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
          <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.memories")}</a>
          <span>{t(locale, "nav.brainMap")}</span>
        </div>
        <div className="mobile-library-segment" aria-label={t(locale, "nav.library")}>
          <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
          <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.memories")}</a>
        </div>
      </>}
    </>
  );
}
