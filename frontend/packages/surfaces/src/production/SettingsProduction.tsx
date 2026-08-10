import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { AppearanceSelection, EntitlementState, SettingsSnapshot } from "./settings-merge.js";
import { entitlementNotice, usageLabelArgs } from "./settings-merge.js";
import type { ProductionSettingsStore } from "./ProductionSettingsStore.js";
import { deadLetterView } from "./dead-letter-presentation.js";
import { refreshPhaseNoticeKey } from "./lifecycle-presentation.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge } from "./ProductionPrimitives.js";
import "./settings.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
type SavePhase = "idle" | "saving" | "saved" | "failed";
type AccountPresentation = "loading" | "unavailable" | "signed-out" | "signed-in";
type PlanPresentation = "metered" | "unmetered" | "absent";
type LimitPresentation = "ok" | "reached-upgrade" | "reached-no-upgrade";

function phaseLabel(status: StoreStatus, locale: Locale): string | null {
  const key = refreshPhaseNoticeKey(status.refresh.phase);
  return key === null ? null : t(locale, key);
}

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

  const notice = phaseLabel(status, locale);
  const queueLabel = useMemo(() => {
    const count = status.queue.pendingCount;
    if (!count) return null;
    if (status.queue.phase === "needs-auth") return t(locale, "queue.paused");
    if (status.queue.phase === "retrying") return t(locale, "queue.retrying");
    if (status.queue.phase === "sending") return t(locale, "queue.sending", { count });
    return t(locale, "queue.queuedCount", { count });
  }, [locale, status]);

  const canRouteUpgrade = typeof onUpgrade === "function";
  const phase = status.refresh.phase;
  const identity = snapshot?.identity ?? null;
  const entitlement = snapshot?.entitlement ?? null;
  const account = accountPresentation(phase, snapshot);
  const planNotice = entitlementNotice(entitlement, canRouteUpgrade);
  const usage = usageLabelArgs(entitlement);
  const showAppearance = account !== "unavailable";
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
    try {
      await run(() => store.signOut());
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
    <main className="production-shell settings-production-shell" data-production-shell="true" data-route="settings" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"}>
      <ProductionChrome locale={locale} active="settings" placement="top" />
      <section className="desktop-page-panel">
        <header className="settings-header">
          <div>
            <p className="settings-eyebrow">{t(locale, "nav.settings")}</p>
            <h1>{t(locale, "settings.title")}</h1>
            <p>{t(locale, "settings.subtitle")}</p>
          </div>
          {status.refresh.phase !== "ready" && (
            <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>
              {t(locale, "common.retry")}
            </button>
          )}
        </header>
        {fixture && <ProductionDataSourceBadge source={{ kind: "fixture", fixture }} locale={locale} />}
        <div className="surface-notices" aria-live="polite">
          {notice && account !== "unavailable" && <div className={"status-notice " + status.refresh.phase} role="status">{notice}</div>}
          {queueLabel && <div className={"queue-notice " + status.queue.phase} role="status">{queueLabel}</div>}
          {saveNotice && <div className="settings-save-notice" role="status">{saveNotice}</div>}
          {operationError && <div className="operation-error" role="alert">{operationError}</div>}
        </div>
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
                <p className="settings-signed-in">{t(locale, "settings.signedInAs", { name: identity.displayName })}</p>
                <dl className="settings-identity-details">
                  <div>
                    <dt>{t(locale, "settings.emailLabel")}</dt>
                    <dd>{identity.email}</dd>
                  </div>
                </dl>
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
            ) : (
              <div className="settings-account-panel is-loading" data-settings-account="loading" role="status" aria-busy={true}>
                <p className="settings-state-copy">{t(locale, "common.loading")}</p>
              </div>
            )
          ) : account === "signed-out" ? (
            <div className="settings-account-panel is-signed-out" data-settings-account="signed-out">
              <p className="settings-state-title">{t(locale, "settings.notSignedIn")}</p>
              <p className="settings-state-copy">{t(locale, "settings.signedOutHint")}</p>
              <button type="button" className="settings-sign-in" disabled aria-label={t(locale, "settings.signIn")}>
                {t(locale, "settings.signIn")}
              </button>
            </div>
          ) : (
            <div className="settings-account-panel is-loading" data-settings-account="loading" role="status" aria-busy={true}>
              <p className="settings-state-copy">{t(locale, "common.loading")}</p>
            </div>
          )}
        </section>
        {showAppearance && (
          <section
            className="settings-section settings-appearance-section"
            aria-labelledby="settings-appearance-heading"
            data-appearance-scope="shell-local"
          >
            <h2 id="settings-appearance-heading">{t(locale, "settings.appearanceSection")}</h2>
            <p className="settings-local-note">{t(locale, "settings.appearanceLocalNote")}</p>
            <label className="settings-appearance-control">
              <span>{t(locale, "appearance.title")}</span>
              <select
                aria-label={t(locale, "appearance.title")}
                value={snapshot?.appearance ?? "default"}
                disabled={!snapshot || savePhase === "saving" || account === "loading"}
                onChange={(event) => void changeAppearance(event.target.value as AppearanceSelection)}
              >
                {APPEARANCE_OPTIONS.map((option) => (
                  <option key={option} value={option}>{appearanceLabel(option, locale)}</option>
                ))}
              </select>
            </label>
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
              <div>
                <dt>{t(locale, "settings.planLabel")}</dt>
                <dd>{entitlement.planLabel}</dd>
              </div>
              {usage && (
                <div>
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
