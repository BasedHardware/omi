'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check,
  Trash2,
  Clock,
  X,
  ChevronDown,
  Copy,
  Download,
  FileJson,
  FileText,
  FileCode,
  CheckSquare,
  Square,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

interface BulkActionBarProps {
  selectedCount: number;
  selectedItems?: ActionItem[];
  onComplete?: () => void;
  onDelete: () => void;
  onSnooze?: (days: number) => void;
  onClear: () => void;
  onCopy?: () => void;
  onExport?: (format: 'csv' | 'json' | 'markdown') => void;
  inline?: boolean;
  onSelectAll?: () => void;
  onDone?: () => void;
  allSelected?: boolean;
  totalCount?: number;
  hideComplete?: boolean;
  hideSnooze?: boolean;
}

type OpenMenu = 'snooze' | 'export' | 'overflow' | null;
type ExportFormat = 'csv' | 'json' | 'markdown';

const menuPanelClass =
  'z-50 rounded-lg border border-bg-tertiary bg-bg-secondary py-1 shadow-lg shadow-black/20';
const menuItemClass =
  'flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary';

const SNOOZE_OPTIONS = [
  { days: 0, label: 'Today' },
  { days: 1, label: 'Tomorrow' },
  { days: 7, label: 'Next week' },
] as const;

const EXPORT_OPTIONS = [
  { format: 'csv' as const, label: 'CSV', Icon: FileText },
  { format: 'json' as const, label: 'JSON', Icon: FileJson },
  { format: 'markdown' as const, label: 'Markdown', Icon: FileCode },
];

function MenuPanel({
  inline,
  align = 'start',
  className,
  role,
  children,
}: {
  inline: boolean;
  align?: 'start' | 'end';
  className?: string;
  role?: string;
  children: ReactNode;
}) {
  return (
    <motion.div
      role={role}
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 5 }}
      transition={{ duration: 0.15 }}
      className={cn(
        inline ? 'absolute top-full mt-2' : 'absolute bottom-full mb-2',
        align === 'end' ? 'right-0' : 'left-0',
        menuPanelClass,
        className,
      )}
    >
      {children}
    </motion.div>
  );
}

function MenuItem({
  children,
  className,
  role,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  role?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role={role}
      onClick={onClick}
      className={cn(menuItemClass, className)}
    >
      {children}
    </button>
  );
}

function MenuLabel({ children }: { children: ReactNode }) {
  return (
    <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-text-quaternary">
      {children}
    </p>
  );
}

function MenuSeparator({ className }: { className?: string }) {
  return <div className={cn('my-1 h-px bg-bg-tertiary', className)} role="separator" />;
}

function SnoozeItems({
  onSnooze,
  onDone,
  menuitem,
}: {
  onSnooze: (days: number) => void;
  onDone: () => void;
  menuitem?: boolean;
}) {
  return (
    <>
      {SNOOZE_OPTIONS.map(({ days, label }) => (
        <MenuItem
          key={days}
          role={menuitem ? 'menuitem' : undefined}
          onClick={() => {
            onSnooze(days);
            onDone();
          }}
        >
          {label}
        </MenuItem>
      ))}
    </>
  );
}

function ExportItems({
  onExport,
  onDone,
  menuitem,
}: {
  onExport: (format: ExportFormat) => void;
  onDone: () => void;
  menuitem?: boolean;
}) {
  return (
    <>
      {EXPORT_OPTIONS.map(({ format, label, Icon }) => (
        <MenuItem
          key={format}
          role={menuitem ? 'menuitem' : undefined}
          onClick={() => {
            onExport(format);
            onDone();
          }}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </MenuItem>
      ))}
    </>
  );
}

export function BulkActionBar({
  selectedCount,
  selectedItems,
  onComplete,
  onDelete,
  onSnooze,
  onClear,
  onCopy,
  onExport,
  inline = false,
  onSelectAll,
  onDone,
  allSelected = false,
  totalCount = 0,
  hideComplete = false,
  hideSnooze = false,
}: BulkActionBarProps) {
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const snoozeRef = useRef<HTMLDivElement>(null);
  const exportRef = useRef<HTMLDivElement>(null);
  const overflowRef = useRef<HTMLDivElement>(null);

  const closeMenu = () => setOpenMenu(null);
  const toggleMenu = (menu: Exclude<OpenMenu, null>) => {
    setOpenMenu((current) => (current === menu ? null : menu));
  };

  useEffect(() => {
    if (!openMenu) return;

    const root =
      openMenu === 'snooze'
        ? snoozeRef.current
        : openMenu === 'export'
          ? exportRef.current
          : overflowRef.current;

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (root?.contains(target)) return;
      closeMenu();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openMenu]);

  if (!inline && selectedCount === 0) return null;

  const content = (
    <>
      {inline && onSelectAll && (
        <>
          <button
            onClick={onSelectAll}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm',
              'transition-colors',
              allSelected
                ? 'bg-white/10 text-white'
                : 'text-text-tertiary hover:text-text-primary hover:bg-bg-quaternary',
            )}
          >
            {allSelected ? (
              <CheckSquare className="w-4 h-4" />
            ) : (
              <Square className="w-4 h-4" />
            )}
            <span>Select All</span>
          </button>
          <div className="w-px h-6 bg-bg-quaternary" />
        </>
      )}

      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-text-primary">
          {selectedCount} selected
        </span>
        {!inline && (
          <button
            onClick={onClear}
            className="p-1 rounded hover:bg-bg-tertiary text-text-quaternary hover:text-text-secondary transition-colors"
            title="Clear selection"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="w-px h-6 bg-bg-tertiary" />

      <div className="flex items-center gap-2">
        {!hideSnooze && onSnooze && (
          <div ref={snoozeRef} className="relative hidden min-[1200px]:block">
            <button
              type="button"
              onClick={() => toggleMenu('snooze')}
              disabled={selectedCount === 0}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'text-text-secondary text-sm',
                'transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              <Clock className="w-4 h-4" />
              <span>Snooze</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            <AnimatePresence>
              {openMenu === 'snooze' && (
                <MenuPanel inline={inline} className="min-w-[120px]">
                  <SnoozeItems onSnooze={onSnooze} onDone={closeMenu} />
                </MenuPanel>
              )}
            </AnimatePresence>
          </div>
        )}

        {!hideComplete && onComplete && (
          <button
            onClick={onComplete}
            disabled={selectedCount === 0}
            className={cn(
              'hidden min-[1430px]:flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-success/20 hover:bg-success/30',
              'text-success text-sm',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            <Check className="w-4 h-4" />
            <span>Complete</span>
          </button>
        )}

        <button
          onClick={onDelete}
          disabled={selectedCount === 0}
          className={cn(
            'hidden min-[1430px]:flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
            'bg-error/20 hover:bg-error/30',
            'text-error text-sm',
            'transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete</span>
        </button>

        {(onCopy || onExport) && (
          <div className="hidden h-6 w-px shrink-0 bg-bg-tertiary min-[1600px]:block" />
        )}

        {onCopy && (
          <button
            onClick={onCopy}
            disabled={selectedCount === 0}
            className={cn(
              'hidden min-[1600px]:flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-bg-tertiary hover:bg-bg-quaternary',
              'text-text-secondary text-sm',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
            title="Copy to clipboard"
          >
            <Copy className="w-4 h-4" />
            <span>Copy</span>
          </button>
        )}

        {onExport && (
          <div ref={exportRef} className="relative hidden min-[1600px]:block">
            <button
              type="button"
              onClick={() => toggleMenu('export')}
              disabled={selectedCount === 0}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'text-text-secondary text-sm',
                'transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              <Download className="w-4 h-4" />
              <span>Export</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            <AnimatePresence>
              {openMenu === 'export' && (
                <MenuPanel inline={inline} align="end" className="min-w-[140px]">
                  <ExportItems onExport={onExport} onDone={closeMenu} />
                </MenuPanel>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      {inline && onDone && (
        <>
          <div className="w-px h-6 bg-bg-tertiary ml-auto" />
          <button
            onClick={onDone}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-white/10 hover:bg-white/20',
              'text-white text-sm font-medium',
              'transition-colors',
            )}
          >
            Done
          </button>
        </>
      )}

      {(onCopy || onExport) && (
        <div ref={overflowRef} className="relative">
          <button
            type="button"
            aria-label="More actions"
            aria-haspopup="menu"
            aria-expanded={openMenu === 'overflow'}
            disabled={selectedCount === 0}
            onClick={() => toggleMenu('overflow')}
            className={cn(
              'flex items-center justify-center rounded-lg p-1.5 min-[1600px]:hidden',
              'bg-bg-tertiary hover:bg-bg-quaternary',
              'text-text-secondary',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
          <AnimatePresence>
            {openMenu === 'overflow' && (
              <MenuPanel
                inline={inline}
                align="end"
                role="menu"
                className="min-w-[140px]"
              >
                {!hideSnooze && onSnooze && (
                  <div className="hidden max-[1199px]:block">
                    <MenuLabel>Snooze</MenuLabel>
                    <SnoozeItems onSnooze={onSnooze} onDone={closeMenu} menuitem />
                    <MenuSeparator />
                  </div>
                )}
                {!hideComplete && onComplete && (
                  <MenuItem
                    role="menuitem"
                    onClick={() => {
                      onComplete();
                      closeMenu();
                    }}
                    className="hidden text-success hover:bg-success/10 max-[1429px]:flex"
                  >
                    <Check className="h-3.5 w-3.5" />
                    Complete
                  </MenuItem>
                )}
                <MenuItem
                  role="menuitem"
                  onClick={() => {
                    onDelete();
                    closeMenu();
                  }}
                  className="hidden text-error hover:bg-error/10 max-[1429px]:flex"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </MenuItem>
                {(onCopy || onExport) && (
                  <MenuSeparator className="hidden max-[1429px]:block" />
                )}
                {onCopy && (
                  <MenuItem
                    role="menuitem"
                    onClick={() => {
                      onCopy();
                      closeMenu();
                    }}
                  >
                    <Copy className="h-3.5 w-3.5" />
                    Copy
                  </MenuItem>
                )}
                {onCopy && onExport && <MenuSeparator />}
                {onExport && (
                  <>
                    <MenuLabel>Export</MenuLabel>
                    <ExportItems onExport={onExport} onDone={closeMenu} menuitem />
                  </>
                )}
              </MenuPanel>
            )}
          </AnimatePresence>
        </div>
      )}
    </>
  );

  if (inline) {
    return (
      <motion.div
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: 'auto' }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.2 }}
        className={cn(
          'flex items-center gap-3 py-2 px-3 rounded-lg',
          'bg-bg-tertiary/50 border border-bg-quaternary',
        )}
      >
        {content}
      </motion.div>
    );
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 100, opacity: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className={cn(
          'fixed bottom-4 left-1/2 -translate-x-1/2',
          'bg-bg-secondary border border-bg-tertiary',
          'rounded-xl shadow-lg shadow-black/30',
          'px-4 py-3',
          'flex items-center gap-4',
          'z-50',
        )}
      >
        {content}
      </motion.div>
    </AnimatePresence>
  );
}
