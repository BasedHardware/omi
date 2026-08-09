import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { AppearanceSelection, SettingsSnapshot } from "./settings-merge.js";
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
  const entitlement = snapshot?.entitlement ?? null;
  const planNotice = entitlementNotice(entitlement, canRouteUpgrade);
  const usage = usageLabelArgs(entitlement);

  const changeAppearance = async (selection: AppearanceSelection): Promise<void> => {
    if (!snapshot || snapshot.appearance === selection) return;
    setSavePhase("saving");
    const succeeded = await run(() => store.patch({ appearance: selection }));
    setSavePhase(succeeded ? "saved" : "failed");
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
          {notice && <div className={"status-notice " + status.refresh.phase} role="status">{notice}</div>}
          {queueLabel && <div className={"queue-notice " + status.queue.phase} role="status">{queueLabel}</div>}
          {saveNotice && <div className="settings-save-notice" role="status">{saveNotice}</div>}
          {operationError && <div className="operation-error" role="alert">{operationError}</div>}
        </div>
        <section className="settings-section" aria-labelledby="settings-account-heading">
          <h2 id="settings-account-heading">{t(locale, "settings.accountSection")}</h2>
          {snapshot?.identity ? (
            <div className="settings-account-panel">
              <p className="settings-signed-in">{t(locale, "settings.signedInAs", { name: snapshot.identity.displayName })}</p>
              <dl className="settings-identity-details">
                <div>
                  <dt>{t(locale, "settings.emailLabel")}</dt>
                  <dd>{snapshot.identity.email}</dd>
                </div>
              </dl>
              <button type="button" className="settings-sign-out" onClick={() => void run(() => store.signOut())} aria-label={t(locale, "settings.signOut")}>
                {t(locale, "settings.signOut")}
              </button>
            </div>
          ) : status.refresh.phase === "ready" ? (
            <div className="settings-account-panel">
              <p>{t(locale, "settings.notSignedIn")}</p>
              <button type="button" className="settings-sign-in" disabled aria-label={t(locale, "settings.signIn")}>
                {t(locale, "settings.signIn")}
              </button>
            </div>
          ) : (
            <p className="settings-empty-copy">{t(locale, "settings.identityUnavailable")}</p>
          )}
        </section>
        <section className="settings-section" aria-labelledby="settings-appearance-heading">
          <h2 id="settings-appearance-heading">{t(locale, "settings.appearanceSection")}</h2>
          <label className="settings-appearance-control">
            <span>{t(locale, "appearance.title")}</span>
            <select
              aria-label={t(locale, "appearance.title")}
              value={snapshot?.appearance ?? "default"}
              disabled={!snapshot || savePhase === "saving"}
              onChange={(event) => void changeAppearance(event.target.value as AppearanceSelection)}
            >
              {APPEARANCE_OPTIONS.map((option) => (
                <option key={option} value={option}>{appearanceLabel(option, locale)}</option>
              ))}
            </select>
          </label>
        </section>
        {entitlement && (
          <section className="settings-section" aria-labelledby="settings-plan-heading">
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
              <div className="settings-limit-notice" role="status">
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
