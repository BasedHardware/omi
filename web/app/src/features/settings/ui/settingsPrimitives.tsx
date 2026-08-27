'use client';

import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Loader2, AlertTriangle, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export function Toggle({
  enabled,
  onChange,
  disabled = false,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={cn(
        'relative w-11 h-6 rounded-full transition-all duration-200 flex-shrink-0',
        enabled
          ? 'bg-text-primary shadow-[0_0_12px_rgba(255,255,255,0.25)]'
          : 'bg-white/[0.08]',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      <div
        className={cn(
          'absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all duration-200 shadow-sm',
          enabled ? 'left-[22px]' : 'left-0.5',
        )}
      />
    </button>
  );
}

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-2xl p-5',
        // Layered background for depth instead of harsh border
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        // Soft shadow stack
        'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-white/[0.04] last:border-0">
      <div className="flex-1 min-w-0 mr-4">
        <p className="text-[15px] text-white/85 font-medium">{label}</p>
        {description && (
          <p className="text-[13px] text-white/40 mt-0.5 leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {children}
    </div>
  );
}

export function Dropdown({
  value,
  options,
  onChange,
  placeholder = 'Select...',
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedOption = options.find((o) => o.value === value);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center justify-between gap-2 px-4 py-2.5 rounded-xl',
          'bg-white/[0.04] ring-1 ring-white/[0.06]',
          'text-white/80 min-w-[160px]',
          'hover:bg-white/[0.06] transition-colors',
        )}
      >
        <span className="truncate text-sm">{selectedOption?.label || placeholder}</span>
        <ChevronDown
          className={cn(
            'w-4 h-4 text-white/40 transition-transform',
            isOpen && 'rotate-180',
          )}
        />
      </button>

      {isOpen && (
        <div
          className={cn(
            'absolute z-50 w-full mt-2 py-1.5 rounded-xl max-h-64 overflow-y-auto',
            'bg-[#1a1a1f]/95 backdrop-blur-xl',
            'shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_10px_30px_-5px_rgba(0,0,0,0.5)]',
          )}
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={cn(
                'w-full px-4 py-2.5 text-left transition-colors flex items-center justify-between text-sm',
                option.value === value
                  ? 'bg-white/[0.08] text-white'
                  : 'text-white/70 hover:bg-white/[0.04] hover:text-white/90',
              )}
            >
              <span>{option.label}</span>
              {option.value === value && (
                <Check className="w-4 h-4 text-text-secondary" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function HourPicker({
  value,
  onChange,
}: {
  value: number;
  onChange: (hour: number) => void;
}) {
  const hours = Array.from({ length: 24 }, (_, i) => {
    const hour = i;
    const period = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return {
      value: hour.toString(),
      label: `${displayHour}:00 ${period}`,
    };
  });

  return (
    <Dropdown
      value={value.toString()}
      options={hours}
      onChange={(v) => onChange(parseInt(v))}
      placeholder="Select time"
    />
  );
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  isDestructive = false,
  isLoading = false,
}: {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDestructive?: boolean;
  isLoading?: boolean;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
      <div className="relative bg-bg-secondary rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl border border-white/[0.06]">
        <div className="flex items-start gap-4 mb-4">
          <div
            className={cn(
              'p-2 rounded-full',
              isDestructive ? 'bg-red-500/10' : 'bg-white/[0.08]',
            )}
          >
            <AlertTriangle
              className={cn(
                'w-6 h-6',
                isDestructive ? 'text-red-400' : 'text-text-secondary',
              )}
            />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
            <p className="text-text-secondary mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className={cn(
              'px-4 py-2 rounded-xl font-medium',
              'bg-bg-tertiary text-text-primary',
              'hover:bg-bg-quaternary transition-colors',
              'disabled:opacity-50',
            )}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={cn(
              'px-4 py-2 rounded-xl font-medium flex items-center gap-2',
              isDestructive
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
              'transition-colors disabled:opacity-50',
            )}
          >
            {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Profile Section
// ============================================================================
