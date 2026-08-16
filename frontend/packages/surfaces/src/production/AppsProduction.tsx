import { useEffect, type JSX } from "react";
import { t } from "@omi-core/i18n";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionEmptyState, ProductionLifecycleRegion, ProductionPageHeader } from "./ProductionPrimitives.js";

const APPS_READY_PHASE = "ready" as const;
const APPS_EMPTY_KIND = "empty-projection" as const;
const APPS_EMPTY_ICON = "apps" as const;

/**
 * Apps is the catalog of import sources, export destinations, and marketplace
 * apps. Swift reads that catalog from `v2/apps` / `v1/apps`, plus local
 * ImportConnector / MemoryExportDestination lists. This backend serves none of
 * those, so the destination is ready and empty — not unavailable, and not a
 * fabricated list.
 */
export function AppsProduction({
  locale,
  onReady,
}: {
  locale: string;
  onReady?: () => void;
}): JSX.Element {
  useEffect(() => { onReady?.(); }, [onReady]);
  const title = t(locale, "nav.apps");
  return (
    <main
      className="production-shell"
      aria-label={title}
      data-production-shell="true"
      data-route="apps"
      data-surface-state={APPS_READY_PHASE}
      data-qa-fixture="none"
      data-consumer-semantic="apps:visible:0:total:0"
    >
      <ProductionChrome locale={locale} active="apps" placement="top" />
      <section className="desktop-page-panel">
        <ProductionPageHeader
          className="production-header"
          eyebrow={title}
          title={title}
          description={t(locale, "apps.subtitle")}
        />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={APPS_READY_PHASE}
          hasSavedData={false}
          locale={locale}
        />
        <div data-empty-kind={APPS_EMPTY_KIND}>
          <ProductionEmptyState
            icon={APPS_EMPTY_ICON}
            title={t(locale, "apps.emptyTitle")}
            detail={t(locale, "apps.emptyDetail")}
          />
        </div>
      </section>
      <ProductionChrome locale={locale} active="apps" placement="bottom" />
    </main>
  );
}
