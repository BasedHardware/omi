import type { Ref } from "react";
import { t } from "@omi-core/i18n";

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
  return (
    <p className={`data-source-badge tone-${live ? "live" : "fixture"}`} role="status">
      {t(locale, "dataSource.detail", {
        source: t(locale, live ? "dataSource.live" : "dataSource.fixture"),
        detail: live ? source.origin : source.fixture,
      })}
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
      <span className="production-search-icon" aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
      <input
        ref={inputRef}
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onValueChange(event.target.value)}
      />
    </label>
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
    <div className={`production-filter-chips${className ? ` ${className}` : ""}`} aria-label={label}>
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
