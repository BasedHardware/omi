import type { Ref } from "react";

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
