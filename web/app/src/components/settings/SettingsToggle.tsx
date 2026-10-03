import { cn } from '@/lib/utils';

export function Toggle({
  enabled,
  onChange,
  disabled = false,
  label,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
  /** Accessible name; screen readers announce this plus the pressed state. */
  label: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={enabled}
      aria-label={label}
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={cn(
        'relative h-6 w-11 flex-shrink-0 rounded-full transition-all duration-200',
        enabled
          ? 'bg-text-primary shadow-[0_0_12px_rgba(255,255,255,0.25)]'
          : 'bg-white/[0.08]',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <div
        className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-all duration-200',
          enabled ? 'left-[22px]' : 'left-0.5',
        )}
      />
    </button>
  );
}
