import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { AppearanceSelection, EntitlementState, SettingsSnapshot } from "./settings-merge.js";
import { entitlementNotice, usageLabelArgs } from "./settings-merge.js";
import type { ProductionSettingsStore } from "./ProductionSettingsStore.js";
import { deadLetterView } from "./dead-letter-presentation.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionDisabledControl, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionPageHeader } from "./ProductionPrimitives.js";
import "./settings.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
type SavePhase = "idle" | "saving" | "saved" | "failed";
type AccountPresentation = "loading" | "unavailable" | "signed-out" | "signed-in";
type PlanPresentation = "metered" | "unmetered" | "absent";
type LimitPresentation = "ok" | "reached-upgrade" | "reached-no-upgrade";

const APPEARANCE_OPTIONS: AppearanceSelection[] = ["default", "system", "light", "dark"];

function appearanceLabel(selection: AppearanceSelection, locale: Locale): string {
  switch (selection) {
    case "default": return t(locale, "appearance.default");
    case "system": return t(locale, "appearance.system");
    case "light": return t(locale, "appearance.light");
    case "dark": return t(locale, "appearance.dark");
  }
}

function accountPresentation(
  phase: StoreStatus["refresh"]["phase"],
  snapshot: SettingsSnapshot | null,
): AccountPresentation {
  if (phase === "initial-loading") return "loading";
  if (phase === "unavailable") return "unavailable";
  // Snapshot readiness is separate from refresh phase: a ready store may still
  // be awaiting its first snapshot. Signed-out is only proven once that read
  // has landed with a null identity — never as the missing-data fallback.
  if (snapshot === null) return "loading";
  return snapshot.identity ? "signed-in" : "signed-out";
}

function planPresentation(entitlement: EntitlementState): PlanPresentation {
  return entitlement.limit === null ? "unmetered" : "metered";
}

function limitPresentation(
  entitlement: EntitlementState,
  notice: ReturnType<typeof entitlementNotice>,
): LimitPresentation {
  if (!entitlement.limitReached || !notice.show) return "ok";
  return notice.upgrade === "route" ? "reached-upgrade" : "reached-no-upgrade";
}

export function SettingsProduction({ store, fixture, locale = "en", onReady, onUpgrade }: {
  store: ProductionSettingsStore;
  fixture?: string;
  locale?: Locale;
  onReady?: () => void;
  onUpgrade?: (limitKey: string) => void;
}): React.JSX.Element {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [dead, setDead] = useState<Awaited<ReturnType<ProductionSettingsStore["deadLetters"]>>>([]);
  const [status, setStatus] = useState(store.status());
  const [operationError, setOperationError] = useState<string | null>(null);
  const [savePhase, setSavePhase] = useState<SavePhase>("idle");
  const [signingOut, setSigningOut] = useState(false);
  const [signedOutNotice, setSignedOutNotice] = useState<string | null>(null);
  const appearanceControlId = useId();
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      const [nextSnapshot, nextDead] = await Promise.all([store.snapshot(), store.deadLetters()]);
      setSnapshot(nextSnapshot);
      setDead(nextDead);
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
    }
    setStatus(store.status());
  }, [locale, store]);

  const run = useCallback<RunOperation>(async (operation) => {
    setOperationError(null);
    try {
      await operation();
      await reload();
      return true;
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
      setStatus(store.status());
      return false;
    }
  }, [locale, reload, store]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    const boot = async (): Promise<void> => {
      await reload();
      try {
        await store.refresh();
      } catch {
        setOperationError(t(locale, "lifecycle.error"));
        await reload();
      }
      await reload();
      if (active && !readyRef.current) {
        readyRef.current = true;
        onReadyRef.current?.();
      }
    };
    void boot();
    return () => { active = false; unsubscribe(); };
  }, [locale, reload, store]);

  const canRouteUpgrade = typeof onUpgrade === "function";
  const phase = status.refresh.phase;
  const identity = snapshot?.identity ?? null;
  const identityName = identity?.displayName.trim() ?? "";
  const identityEmail = identity?.email.trim() ?? "";
  const entitlement = snapshot?.entitlement ?? null;
  const account = accountPresentation(phase, snapshot);
  const planNotice = entitlementNotice(entitlement, canRouteUpgrade);
  const usage = usageLabelArgs(entitlement);
  // Appearance is snapshot-backed and must not render under an unproven account
  // presentation (loading) or a blackout — either would claim a selected value
  // before the surface is ready to stand behind it.
  const showAppearance = snapshot !== null && (account === "signed-in" || account === "signed-out");
  const showPlan = account === "signed-in";

  const changeAppearance = async (selection: AppearanceSelection): Promise<void> => {
    if (!snapshot || snapshot.appearance === selection) return;
    setSavePhase("saving");
    const succeeded = await run(() => store.patch({ appearance: selection }));
    setSavePhase(succeeded ? "saved" : "failed");
  };

  const signOut = async (): Promise<void> => {
    if (signingOut) return;
    setSigningOut(true);
    setSignedOutNotice(null);
    try {
      const succeeded = await run(() => store.signOut());
      if (succeeded) setSignedOutNotice(t(locale, "settings.signedOutNotice"));
    } finally {
      setSigningOut(false);
    }
  };

  const saveNotice = savePhase === "saving"
    ? t(locale, "settings.saving")
    : savePhase === "saved"
      ? t(locale, "settings.saved")
      : savePhase === "failed"
        ? t(locale, "settings.saveFailed")
        : null;

  return (
    <main className="production-shell settings-production-shell" data-production-shell="true" data-route="settings" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"} data-consumer-semantic={"settings:sections:account-plan-appearance:appearance-control:" + (showAppearance ? "shown" : "hidden") + ":signout-control:" + (showPlan ? "shown" : "hidden")}>
      <ProductionChrome locale={locale} active="settings" placement="top" />
      <section className="desktop-page-panel">
        <ProductionPageHeader className="settings-header" eyebrow={t(locale, "nav.settings")} title={t(locale, "settings.title")} description={t(locale, "settings.subtitle")} />
        <ProductionDataSourceBadge source={fixture ? { kind: "fixture", fixture } : { kind: "live", origin: "bridge" }} locale={locale} />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={status.refresh.phase}
          hasSavedData={status.refresh.hasSavedData}
          locale={locale}
          queue={status.queue}
          deadLetterCount={dead.length}
          operationError={operationError}
          nextAction={status.refresh.phase !== "ready" ? t(locale, "common.retry") : null}
          retry={status.refresh.phase !== "ready" ? { onRetry: async () => { await run(() => store.refresh()); } } : null}
        />
        <ProductionLiveAnnouncement message={saveNotice ?? signedOutNotice} />
        {(saveNotice || signedOutNotice) && <div className="surface-notices">
          {saveNotice && <div className="settings-save-notice" role="status">{saveNotice}</div>}
          {signedOutNotice && <div className="settings-sign-out-notice" role="status">{signedOutNotice}</div>}
        </div>}
        <section className="settings-section" aria-labelledby="settings-account-heading">
          <h2 id="settings-account-heading">{t(locale, "settings.accountSection")}</h2>
          {account === "loading" ? (
            <div className="settings-account-panel is-loading" data-settings-account="loading" role="status" aria-busy={true}>
              <p className="settings-state-copy">{t(locale, "common.loading")}</p>
            </div>
          ) : account === "unavailable" ? (
            <div className="settings-account-panel is-unavailable" data-settings-account="unavailable" role="status">
              <p className="settings-state-title">{t(locale, "settings.unavailableTitle")}</p>
              <p className="settings-state-copy">{t(locale, "settings.unavailableBody")}</p>
              <button
                type="button"
                className="settings-retry"
                onClick={() => void run(() => store.refresh())}
                aria-label={t(locale, "common.retry")}
              >
                {t(locale, "common.retry")}
              </button>
            </div>
          ) : account === "signed-in" ? (
            identity ? (
              <div className="settings-account-panel" data-settings-account="signed-in">
                <div className="settings-row settings-account-row">
                  <div className="settings-row-copy">
                    <p className="settings-signed-in">
                      {identityName
                        ? t(locale, "settings.signedInAs", { name: identityName })
                        : t(locale, "settings.signedIn")}
                    </p>
                    {identityEmail && (
                      <dl className="settings-identity-details">
                        <div>
                          <dt>{t(locale, "settings.emailLabel")}</dt>
                          <dd>{identityEmail}</dd>
                        </div>
                      </dl>
                    )}
                  </div>
                  <button
                    type="button"
                    className="settings-sign-out"
                    disabled={signingOut}
                    aria-busy={signingOut || undefined}
                    onClick={() => void signOut()}
                    aria-label={signingOut ? t(locale, "settings.signingOut") : t(locale, "settings.signOut")}
                  >
                    {signingOut ? t(locale, "settings.signingOut") : t(locale, "settings.signOut")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="settings-account-panel is-loading" data-settings-account="loading" role="status" aria-busy={true}>
                <p className="settings-state-copy">{t(locale, "common.loading")}</p>
              </div>
            )
          ) : account === "signed-out" ? (
            <div className="settings-account-panel is-signed-out" data-settings-account="signed-out">
              <p className="settings-state-title">{t(locale, "settings.notSignedIn")}</p>
              <p className="settings-state-copy">{t(locale, "settings.signedOutHint")}</p>
              <ProductionDisabledControl
                label={t(locale, "settings.signIn")}
                explanation={t(locale, "settings.signInUnavailable")}
                className="settings-sign-in"
                focusable={true}
              />
              <p className="settings-disabled-explanation">{t(locale, "settings.signInUnavailable")}</p>
            </div>
          ) : (
            <div className="settings-account-panel is-loading" data-settings-account="loading" role="status" aria-busy={true}>
              <p className="settings-state-copy">{t(locale, "common.loading")}</p>
            </div>
          )}
        </section>
        {showAppearance && snapshot && (
          <section
            className="settings-section settings-appearance-section"
            aria-labelledby="settings-appearance-heading"
            data-appearance-scope="shell-local"
          >
            <h2 id="settings-appearance-heading">{t(locale, "settings.appearanceSection")}</h2>
            <div className="settings-row settings-appearance-row">
              <label className="settings-row-copy" htmlFor={appearanceControlId}>
                <span className="settings-row-title">{t(locale, "appearance.title")}</span>
                <span className="settings-row-description">{t(locale, "settings.appearanceLocalNote")}</span>
              </label>
              <span className="settings-select-wrap">
                <select
                  id={appearanceControlId}
                  aria-label={t(locale, "appearance.title")}
                  value={snapshot.appearance}
                  disabled={savePhase === "saving"}
                  onChange={(event) => void changeAppearance(event.target.value as AppearanceSelection)}
                >
                  {APPEARANCE_OPTIONS.map((option) => (
                    <option key={option} value={option}>{appearanceLabel(option, locale)}</option>
                  ))}
                </select>
              </span>
            </div>
          </section>
        )}
        {showPlan && entitlement && (
          <section
            className="settings-section"
            aria-labelledby="settings-plan-heading"
            data-settings-plan={planPresentation(entitlement)}
            data-settings-limit={limitPresentation(entitlement, planNotice)}
          >
            <h2 id="settings-plan-heading">{t(locale, "settings.planSection")}</h2>
            <dl className="settings-plan-details">
              <div className="settings-row settings-fact-row">
                <dt>{t(locale, "settings.planLabel")}</dt>
                <dd>{entitlement.planLabel}</dd>
              </div>
              {usage && (
                <div className="settings-row settings-fact-row">
                  <dt>{t(locale, "settings.usageLabel")}</dt>
                  <dd>
                    {usage.limit !== undefined
                      ? t(locale, "settings.usageOf", { used: usage.used, limit: usage.limit })
                      : t(locale, "settings.usageUnmetered", { used: usage.used })}
                  </dd>
                </div>
              )}
            </dl>
            {planNotice.show && (
              <div className={"settings-limit-notice is-" + limitPresentation(entitlement, planNotice)} role="status">
                <p className="settings-limit-title">{t(locale, "settings.limitReachedTitle")}</p>
                {planNotice.upgrade === "route" && (
                  <button
                    type="button"
                    className="settings-upgrade"
                    onClick={() => onUpgrade?.(entitlement.limitKey)}
                    aria-label={t(locale, "settings.upgrade")}
                  >
                    {t(locale, "settings.upgrade")}
                  </button>
                )}
                {planNotice.upgrade === "unavailable" && (
                  <p className="settings-upgrade-unavailable">{t(locale, "settings.upgradeUnavailable")}</p>
                )}
              </div>
            )}
          </section>
        )}
        {showPlan && !entitlement && (
          <section
            className="settings-section settings-plan-absent"
            aria-labelledby="settings-plan-heading"
            data-settings-plan="absent"
          >
            <h2 id="settings-plan-heading">{t(locale, "settings.planSection")}</h2>
            <p className="settings-state-title">{t(locale, "settings.entitlementAbsentTitle")}</p>
            <p className="settings-state-copy">{t(locale, "settings.entitlementAbsentBody")}</p>
          </section>
        )}
        {dead.length > 0 && (
          <section className="dead-letter-panel" aria-label={t(locale, "dead.title")}>
            <h2>{t(locale, "dead.title")}</h2>
            {dead.map(deadLetterView).map((view) => (
              <div className="dead-letter" key={view.opId}>
                <span>{t(locale, view.messageKey)}</span>
                {view.savedEdit !== null && <pre className="dead-letter-payload">{view.savedEdit}</pre>}
                {/* Discard only — a retry would resubmit an envelope the
                    account-epoch fence refuses forever. See
                    dead-letter-presentation.ts. */}
                <button type="button" onClick={() => void run(() => store.discardDeadLetter(view.opId))}>
                  {t(locale, "dead.remove")}
                </button>
              </div>
            ))}
          </section>
        )}
      </section>
      <ProductionChrome locale={locale} active="settings" placement="bottom" />
    </main>
  );
}
