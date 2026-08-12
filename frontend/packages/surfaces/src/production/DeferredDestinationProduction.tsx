import * as React from "react";
import { t } from "@omi-core/i18n";
import type { ProductionRoute } from "./command-registry.js";
import { ProductionChrome, ProductionLibrarySegment } from "./ProductionChrome.js";
import { ProductionLifecycleRegion, ProductionPageHeader } from "./ProductionPrimitives.js";

export type DeferredProductionDestination = Extract<ProductionRoute, "apps" | "rewind" | "brain-map">;

const titleKey = (destination: DeferredProductionDestination): "nav.apps" | "nav.rewind" | "nav.brainMap" => {
  if (destination === "apps") return "nav.apps";
  if (destination === "rewind") return "nav.rewind";
  return "nav.brainMap";
};

/**
 * A shipped navigation destination whose rewrite data contract is not connected
 * yet. Keeping this state explicit preserves reachability without fabricating a
 * product surface or silently routing the user somewhere else.
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
  const title = t(locale, titleKey(destination), undefined as never);
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
        {destination === "brain-map"
          ? <ProductionLibrarySegment locale={locale} active="brain-map" />
          : null}
        <ProductionPageHeader
          className="production-header"
          eyebrow={title}
          title={title}
          description={t(locale, "destination.unavailable", undefined as never)}
        />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={unavailablePhase}
          hasSavedData={false}
          locale={locale}
          nextAction={t(locale, "destination.waitForSource", undefined as never)}
        />
      </section>
      <ProductionChrome locale={locale} active={destination} placement="bottom" />
    </main>
  );
}
