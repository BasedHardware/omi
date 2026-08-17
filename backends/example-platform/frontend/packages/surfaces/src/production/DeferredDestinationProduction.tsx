import * as React from "react";
import { t } from "@omi-core/i18n";
import type { ProductionRoute } from "./command-registry.js";
import { ProductionChrome, ProductionLibrarySegment } from "./ProductionChrome.js";
import { ProductionEmptyState, ProductionLifecycleRegion, ProductionPageHeader } from "./ProductionPrimitives.js";

export type DeferredProductionDestination = Extract<ProductionRoute, "brain-map">;

/**
 * A shipped navigation destination whose rewrite data contract is not wired
 * yet. Keeping this state explicit preserves reachability without fabricating a
 * product surface or silently routing the user somewhere else.
 *
 * Apps used to live here. That claim was checked: the catalog sources do not
 * exist on this backend, so Apps now renders an honest empty catalog instead of
 * three unavailable notices. Brain Map remains deferred.
 */
export function DeferredDestinationProduction({
  destination,
  locale,
  onReady,
}: {
  destination: DeferredProductionDestination;
  locale: string;
  onReady?: () => void;
}): React.JSX.Element {
  React.useEffect(() => { onReady?.(); }, [onReady]);
  const title = t(locale, "nav.brainMap");
  const unavailablePhase = "unavailable" as const;
  return (
    <main
      className="production-shell"
      data-production-shell="true"
      data-route={destination}
      data-surface-state="unavailable"
      data-qa-fixture="none"
    >
      <ProductionChrome locale={locale} active={destination} placement="top" />
      <section className="desktop-page-panel">
        <ProductionLibrarySegment locale={locale} active="brain-map" />
        <ProductionPageHeader
          className="production-header"
          eyebrow={title}
          title={title}
        />
        <ProductionEmptyState
          icon="library"
          title={t(locale, "destination.unavailable")}
          detail={t(locale, "destination.waitForSource")}
        />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={unavailablePhase}
          hasSavedData={false}
          locale={locale}
          nextAction={t(locale, "destination.waitForSource")}
        />
      </section>
      <ProductionChrome locale={locale} active={destination} placement="bottom" />
    </main>
  );
}
