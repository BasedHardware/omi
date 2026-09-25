'use client';

import { useState, useEffect, useRef } from 'react';
import { ChevronDown, Check, Sparkles, Loader2 } from 'lucide-react';
import Image from '@tschk/moonshine-next/image';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import { getChatApps, type App } from '@/lib/api';

interface AppSelectorProps {
  selectedAppId: string | null;
  onSelectApp: (appId: string | null) => void;
  disabled?: boolean;
}

export function AppSelector({ selectedAppId, onSelectApp, disabled }: AppSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [apps, setApps] = useState<App[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Load chat apps
  useEffect(() => {
    async function loadApps() {
      try {
        const chatApps = await getChatApps();
        setApps(chatApps);
      } catch (err) {
        console.error('Failed to load chat apps:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadApps();
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedApp = apps.find((app) => app.id === selectedAppId);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger button */}
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={cn(
          'flex items-center gap-2 rounded-lg px-3 py-2',
          'bg-bg-tertiary hover:bg-bg-quaternary',
          'border border-bg-quaternary',
          'transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          isOpen && 'bg-bg-quaternary',
        )}
      >
        {/* Selected app avatar */}
        {selectedApp ? (
          <div className="h-6 w-6 flex-shrink-0 overflow-hidden rounded-full bg-bg-quaternary">
            {selectedApp.image ? (
              <Image
                src={selectedApp.image}
                alt={selectedApp.name}
                width={24}
                height={24}
                className="object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-xs text-text-tertiary">
                {selectedApp.name.charAt(0)}
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-white/[0.14]">
            <Sparkles className="h-3.5 w-3.5 text-text-primary" />
          </div>
        )}

        <span className="max-w-[120px] truncate text-sm text-text-primary">
          {selectedApp ? selectedApp.name : 'Omi'}
        </span>

        <ChevronDown
          className={cn(
            'h-4 w-4 text-text-tertiary transition-transform',
            isOpen && 'rotate-180',
          )}
        />
      </button>

      {/* Dropdown menu */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'absolute left-0 top-full z-50 mt-2',
              'min-w-[200px] max-w-[280px]',
              'rounded-xl border border-bg-tertiary bg-bg-secondary',
              'overflow-hidden shadow-lg',
            )}
          >
            {isLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-text-tertiary" />
              </div>
            ) : (
              <div className="max-h-[300px] overflow-y-auto py-1">
                {/* Default Omi option */}
                <button
                  onClick={() => {
                    onSelectApp(null);
                    setIsOpen(false);
                  }}
                  className={cn(
                    'flex w-full items-center gap-3 px-4 py-2.5',
                    'transition-colors hover:bg-bg-tertiary',
                    !selectedAppId && 'bg-bg-tertiary/50',
                  )}
                >
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-white/[0.14]">
                    <Sparkles className="h-4 w-4 text-text-primary" />
                  </div>
                  <div className="flex-1 text-left">
                    <p className="text-sm font-medium text-text-primary">Omi</p>
                    <p className="text-xs text-text-tertiary">Default assistant</p>
                  </div>
                  {!selectedAppId && (
                    <Check className="h-4 w-4 flex-shrink-0 text-text-primary" />
                  )}
                </button>

                {/* Separator if there are apps */}
                {apps.length > 0 && <div className="my-1 border-t border-bg-tertiary" />}

                {/* Chat apps list */}
                {apps.map((app) => (
                  <button
                    key={app.id}
                    onClick={() => {
                      onSelectApp(app.id);
                      setIsOpen(false);
                    }}
                    className={cn(
                      'flex w-full items-center gap-3 px-4 py-2.5',
                      'transition-colors hover:bg-bg-tertiary',
                      selectedAppId === app.id && 'bg-bg-tertiary/50',
                    )}
                  >
                    <div className="h-8 w-8 flex-shrink-0 overflow-hidden rounded-full bg-bg-quaternary">
                      {app.image ? (
                        <Image
                          src={app.image}
                          alt={app.name}
                          width={32}
                          height={32}
                          className="object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-sm text-text-tertiary">
                          {app.name.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1 text-left">
                      <p className="truncate text-sm font-medium text-text-primary">
                        {app.name}
                      </p>
                      {app.description && (
                        <p className="truncate text-xs text-text-tertiary">
                          {app.description}
                        </p>
                      )}
                    </div>
                    {selectedAppId === app.id && (
                      <Check className="h-4 w-4 flex-shrink-0 text-text-primary" />
                    )}
                  </button>
                ))}

                {/* Empty state */}
                {apps.length === 0 && (
                  <div className="px-4 py-3 text-center">
                    <p className="text-sm text-text-tertiary">No chat apps enabled</p>
                    <p className="mt-1 text-xs text-text-quaternary">
                      Enable apps in the Apps section
                    </p>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
