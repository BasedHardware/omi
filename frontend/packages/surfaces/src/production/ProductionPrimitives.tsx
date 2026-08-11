import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";
import type { RefreshPhase } from "@omi-core/domain";
import { t } from "@omi-core/i18n";
import type { QueueStatus } from "@omi-core/sync";
import { refreshPhaseNoticeKey } from "./lifecycle-presentation.js";
import { ProductionIcon, type ProductionIconName } from "./ProductionIcon.js";

/**
 * Where the rows on this surface came from.
 *
 * Deliberately NOT `.qa-label`, which `styles.css` sets to `display: none` at desktop
 * width — that is exactly how a fixture render gets mistaken for a real signed-in one, and
 * that confusion has cost this project before. This badge is visible at every width, in
 * both colour modes, and its fixture copy says the data is not the reader's account.
 *
 * `source` is required wherever this is used, so no surface can render rows without
 * declaring their origin.
 */
export type SurfaceDataSource =
  | { readonly kind: "fixture"; readonly fixture: string }
  | { readonly kind: "live"; readonly origin: string };

export function ProductionDataSourceBadge({ source, locale }: {
  source: SurfaceDataSource;
  locale: string;
}): React.JSX.Element {
  const live = source.kind === "live";
  const detail = live
    ? t(locale, "dataSource.live")
    : t(locale, "dataSource.detail", {
        source: t(locale, "dataSource.fixture"),
        detail: source.fixture,
      });
  return (
    <p
      className={`data-source-badge tone-${live ? "live" : "fixture"}`}
      data-source-kind={source.kind}
      data-source-origin={live ? source.origin : undefined}
      aria-label={detail}
      role="status"
    >
      {detail}
    </p>
  );
}

export function ProductionSearchField({
  label,
  placeholder,
  value,
  onValueChange,
  className = "",
  inputRef,
}: {
  label: string;
  placeholder: string;
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
  inputRef?: Ref<HTMLInputElement>;
}): React.JSX.Element {
  return (
    <label className={`production-search-field is-compact${className ? ` ${className}` : ""}`}>
      <ProductionIcon name="search" className="production-search-icon" size={17} />
      <span className="visually-hidden">{label}</span>
      <input
        ref={inputRef}
        type="search"
        aria-label={label}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onValueChange(event.target.value)}
      />
    </label>
  );
}

/**
 * The shared lifecycle contract. `phase` and `hasSavedData` come from a
 * store's truthful refresh snapshot; every other value is an explicit
 * capability or observation supplied by the caller, never inferred here.
 */
export type ProductionLifecycleRegionProps = {
  phase: RefreshPhase;
  hasSavedData: boolean;
  locale: string;
  queue?: QueueStatus | null;
  deadLetterCount?: number;
  lastSuccessAgeMs?: number | null;
  retry?: { readonly onRetry: () => void | Promise<void>; readonly label?: string } | null;
  operationError?: string | null;
  nextAction?: string | null;
  className?: string;
  children?: ReactNode;
};

function ageLabel(locale: string, ageMs: number): string {
  if (!Number.isFinite(ageMs) || ageMs < 60_000) return t(locale, "lifecycle.justNow");
  const minutes = Math.floor(ageMs / 60_000);
  if (minutes < 60) return t(locale, "lifecycle.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t(locale, "lifecycle.hoursAgo", { count: hours });
  return t(locale, "lifecycle.daysAgo", { count: Math.floor(hours / 24) });
}

/**
 * Action-required errors are assertive only on a new message. Keeping the
 * text visible while dropping `role=alert` on an unchanged rerender prevents
 * a store subscription from repeatedly interrupting a screen-reader user.
 */
export function ProductionOperationError({ error }: { error: string | null | undefined }): React.JSX.Element | null {
  const previousErrorRef = useRef<string | null>(null);
  const fresh = Boolean(error && error !== previousErrorRef.current);
  useEffect(() => {
    previousErrorRef.current = error ?? null;
  }, [error]);
  if (!error) return null;
  return (
    <div className="production-operation-error" role={fresh ? "alert" : undefined} aria-live={fresh ? "assertive" : undefined}>
      {error}
    </div>
  );
}

/**
 * One lifecycle region for loading, stale/saved, unavailable, queue and
 * action-error copy. Lists and result counts must remain outside this region;
 * this region is the only status surface that may announce lifecycle changes.
 */
export function ProductionLifecycleRegion({
  phase,
  hasSavedData,
  locale,
  queue,
  deadLetterCount = 0,
  lastSuccessAgeMs,
  retry,
  operationError,
  nextAction,
  className = "",
  children,
}: ProductionLifecycleRegionProps): React.JSX.Element {
  const noticeKey = refreshPhaseNoticeKey(phase);
  const loading = phase === "initial-loading" || phase === "refreshing";
  const activeQueue = queue && queue.phase !== "idle" ? queue : null;
  const queueLabel = activeQueue
    ? activeQueue.phase === "needs-auth"
      ? t(locale, "queue.paused")
      : activeQueue.phase === "retrying"
        ? t(locale, "queue.retrying")
        : activeQueue.phase === "sending"
          ? t(locale, "queue.sending", { count: activeQueue.pendingCount })
          : t(locale, "queue.queuedCount", { count: activeQueue.pendingCount })
    : null;
  const lifecycleSummary = [
    noticeKey ? t(locale, noticeKey) : null,
    phase === "ready" && hasSavedData && lastSuccessAgeMs != null
      ? t(locale, "lifecycle.lastSuccess", { age: ageLabel(locale, lastSuccessAgeMs) })
      : null,
    phase === "saved-but-refresh-failed" && hasSavedData ? t(locale, "lifecycle.savedData") : null,
    queueLabel,
    deadLetterCount > 0 ? t(locale, "lifecycle.deadLetters", { count: deadLetterCount }) : null,
    nextAction ? t(locale, "lifecycle.nextAction", { action: nextAction }) : null,
  ].filter((part): part is string => Boolean(part)).join(" · ");
  return (
    <section
      className={`production-lifecycle-region${className ? ` ${className}` : ""}`}
      data-phase={phase}
      data-has-saved-data={hasSavedData ? "true" : "false"}
      aria-label={t(locale, "lifecycle.region")}
      aria-busy={loading ? "true" : undefined}
    >
      {lifecycleSummary && <p className="production-lifecycle-summary visually-hidden" role="status" aria-live="polite" aria-atomic={atomicLiveRegion}>{lifecycleSummary}</p>}
      {noticeKey && <p className={`status-notice ${phase}`}>{t(locale, noticeKey)}</p>}
      {phase === "ready" && hasSavedData && lastSuccessAgeMs != null && (
        <p className="lifecycle-last-success">
          {t(locale, "lifecycle.lastSuccess", { age: ageLabel(locale, lastSuccessAgeMs) })}
        </p>
      )}
      {phase === "saved-but-refresh-failed" && hasSavedData && (
        <p className="lifecycle-saved-data">{t(locale, "lifecycle.savedData")}</p>
      )}
      {queueLabel && <p className={`queue-notice ${activeQueue?.phase ?? "idle"}`}>{queueLabel}</p>}
      {deadLetterCount > 0 && (
        <p className="lifecycle-dead-letters">
          {t(locale, "lifecycle.deadLetters", { count: deadLetterCount })}
        </p>
      )}
      {nextAction && <p className="lifecycle-next-action">{t(locale, "lifecycle.nextAction", { action: nextAction })}</p>}
      {retry && <button type="button" className="lifecycle-retry" aria-label={retry.label ?? t(locale, "common.retry")} onClick={() => void retry.onRetry()}>{retry.label ?? t(locale, "common.retry")}</button>}
      <ProductionOperationError error={operationError} />
      {children}
    </section>
  );
}

export type ProductionAnnouncementScheduler = {
  setTimeout: (callback: () => void, delayMs: number) => unknown;
  clearTimeout: (handle: unknown) => void;
};

const defaultAnnouncementScheduler: ProductionAnnouncementScheduler = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof globalThis.setTimeout>),
};
const atomicLiveRegion = true;

export type ProductionLiveAnnouncementProps = {
  message: string | null | undefined;
  delayMs?: number;
  className?: string;
  scheduler?: ProductionAnnouncementScheduler;
};

/** A debounced, deduplicated live region for counts/stream terminal states. */
export function ProductionLiveAnnouncement({ message, delayMs = 250, className = "", scheduler = defaultAnnouncementScheduler }: ProductionLiveAnnouncementProps): React.JSX.Element {
  const [announced, setAnnounced] = useState("");
  const lastMessageRef = useRef<string | null>(null);
  useEffect(() => {
    const next = message?.trim() || null;
    if (next === lastMessageRef.current) return undefined;
    lastMessageRef.current = next;
    if (next === null) {
      setAnnounced("");
      return undefined;
    }
    const timer = scheduler.setTimeout(() => setAnnounced(next), Math.max(0, delayMs));
    return () => scheduler.clearTimeout(timer);
  }, [delayMs, message, scheduler]);
  return (
    <div
      className={`production-live-announcement visually-hidden${className ? ` ${className}` : ""}`}
      data-live-region="true"
      role="status"
      aria-live="polite"
      aria-atomic={atomicLiveRegion}
    >
      {announced}
    </div>
  );
}

export type ProductionDisabledControlProps = {
  label: string;
  explanation: string;
  children?: ReactNode;
  as?: "button" | "span";
  focusable?: boolean;
  title?: string;
  className?: string;
  onClick?: () => void;
};

/**
 * Disabled controls remain named and explained. A disabled span is a custom
 * control (not a silent decoration), and is only tabbable when the caller
 * explicitly asks for a focusable explanation target.
 */
export function ProductionDisabledControl({
  label,
  explanation,
  children,
  as = "button",
  focusable = false,
  title,
  className = "",
  onClick,
}: ProductionDisabledControlProps): React.JSX.Element {
  const descriptionId = `disabled-control-${useId().replaceAll(":", "")}`;
  const common = {
    className: `production-disabled-control${className ? ` ${className}` : ""}`,
    "aria-label": label,
    "aria-describedby": descriptionId,
    "aria-disabled": "true" as const,
    title: title ?? explanation,
  };
  const content = children ?? label;
  const customControl = as === "span" || focusable;
  return (
    <span className="production-disabled-control-wrap">
      {customControl ? (
        <span
          {...common}
          role="button"
          tabIndex={focusable ? 0 : -1}
          onClick={(event) => { event.preventDefault(); }}
        >{as === "button" ? <span aria-hidden="true">{content}</span> : content}</span>
      ) : (
        <button {...common} type="button" disabled onClick={onClick}>{content}</button>
      )}
      <span id={descriptionId} className="visually-hidden">{explanation}</span>
    </span>
  );
}

export type ProductionFilterOption<Value extends string> = {
  value: Value;
  label: string;
  disabled?: boolean;
};

export function ProductionFilterChips<Value extends string>({
  label,
  value,
  options,
  onValueChange,
  className = "",
}: {
  label: string;
  value: Value;
  options: readonly ProductionFilterOption<Value>[];
  onValueChange: (value: Value) => void;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={`production-filter-chips${className ? ` ${className}` : ""}`} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          disabled={option.disabled}
          onClick={() => onValueChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function ProductionPageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <header className={`production-page-header${className ? ` ${className}` : ""}`}>
      <div className="production-page-heading">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="production-page-description">{description}</p>}
      </div>
      {actions && <div className="production-page-actions">{actions}</div>}
    </header>
  );
}

export function ProductionSection({
  title,
  description,
  actions,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}): React.JSX.Element {
  const titleId = `production-section-${useId().replaceAll(":", "")}`;
  return (
    <section className={`production-section${className ? ` ${className}` : ""}`} aria-labelledby={titleId}>
      <header className="production-section-header">
        <div>
          <h2 id={titleId}>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="production-section-actions">{actions}</div>}
      </header>
      <div className="production-section-content">{children}</div>
    </section>
  );
}

export function ProductionIconButton({
  icon,
  label,
  tone = "neutral",
  disabled = false,
  onClick,
}: {
  icon: ProductionIconName;
  label: string;
  tone?: "neutral" | "primary" | "danger";
  disabled?: boolean;
  onClick?: () => void;
}): React.JSX.Element {
  return (
    <button
      type="button"
      className={`production-icon-button tone-${tone}`}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      <ProductionIcon name={icon} />
    </button>
  );
}

export function ProductionNotice({
  tone,
  title,
  detail,
  action,
}: {
  tone: "info" | "success" | "warning" | "error";
  title: string;
  detail?: string;
  action?: ReactNode;
}): React.JSX.Element {
  const icon: ProductionIconName = tone === "success" ? "check" : tone === "warning" || tone === "error" ? "alert" : "inbox";
  return (
    <aside className={`production-notice tone-${tone}`}>
      <ProductionIcon name={icon} />
      <div className="production-notice-copy">
        <strong>{title}</strong>
        {detail && <p>{detail}</p>}
      </div>
      {action && <div className="production-notice-action">{action}</div>}
    </aside>
  );
}

export function ProductionEmptyState({
  icon = "inbox",
  title,
  detail,
  action,
}: {
  icon?: ProductionIconName;
  title: string;
  detail: string;
  action?: ReactNode;
}): React.JSX.Element {
  return (
    <section className="production-empty-state">
      <span className="production-empty-state-icon"><ProductionIcon name={icon} size={24} /></span>
      <h2>{title}</h2>
      <p>{detail}</p>
      {action && <div className="production-empty-state-action">{action}</div>}
    </section>
  );
}
