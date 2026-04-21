import { useState, type ComponentType, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

interface Props {
  icon: ComponentType<{
    className?: string;
    size?: number;
    style?: React.CSSProperties;
  }>;
  label: string;
  count: number;
  /** Short preview shown at the right when collapsed. */
  preview?: string;
  /** Optional color accent for the icon. */
  accent?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * Collapsible group header + body. Generalized from Memories'
 * ThemedSection so Insights (and future lists) can share the look.
 */
export function GroupedSection({
  icon: Icon,
  label,
  count,
  preview,
  accent,
  defaultOpen = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  if (count === 0) return null;

  return (
    <div className="themed-section">
      <button
        type="button"
        className="themed-section-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="themed-section-head">
          <Icon
            className="themed-section-icon"
            style={accent ? { color: accent } : undefined}
          />
          <span className="themed-section-label">{label}</span>
          <span className="themed-section-count">{count}</span>
        </div>
        <div className="themed-section-right">
          {!open && preview && (
            <span className="themed-section-preview">{preview}</span>
          )}
          <ChevronDown
            className={
              open
                ? "themed-section-chevron themed-section-chevron-open"
                : "themed-section-chevron"
            }
          />
        </div>
      </button>
      {open && <div className="themed-section-body">{children}</div>}
    </div>
  );
}
