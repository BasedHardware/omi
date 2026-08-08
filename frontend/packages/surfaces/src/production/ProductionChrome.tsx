import { t } from "@omi-core/i18n";

type Locale = string;
type ProductionRoute = "memories" | "conversations" | "tasks";

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
              <span>{t(locale, "nav.home")}</span>
              <a href={href("memories")} aria-current={active === "memories" ? "page" : undefined}>{t(locale, "nav.library")}</a>
              <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}>{t(locale, "nav.tasks")}</a>
              <span>{t(locale, "nav.rewind")}</span>
              <span>{t(locale, "nav.apps")}</span>
            </div>
          </div>
        ) : null}
        <div className="nav-mobile">
          <span>{t(locale, "nav.home")}</span>
          <a href={href("conversations")} aria-current={active === "conversations" ? "page" : undefined}>{t(locale, "nav.conversations")}</a>
          <a href={href("tasks")} aria-current={active === "tasks" ? "page" : undefined}>{t(locale, "nav.tasks")}</a>
          <span>{t(locale, "nav.apps")}</span>
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
