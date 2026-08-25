'use client';

import { useState, useEffect, useRef } from 'react';
import { ChevronDown, Check, Sparkles, Loader2 } from 'lucide-react';
import Image from 'next/image';
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

  const selectedApp = apps.find(app => app.id === selectedAppId);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger button */}
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg',
          'bg-bg-tertiary hover:bg-bg-quaternary',
          'border border-bg-quaternary',
          'transition-colors',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          isOpen && 'bg-bg-quaternary'
        )}
      >
        {/* Selected app avatar */}
        {selectedApp ? (
          <div className="w-6 h-6 rounded-full overflow-hidden bg-bg-quaternary flex-shrink-0">
            {selectedApp.image ? (
              <Image
                src={selectedApp.image}
                alt={selectedApp.name}
                width={24}
                height={24}
                className="object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-text-tertiary text-xs">
                {selectedApp.name.charAt(0)}
              </div>
            )}
          </div>
        ) : (
          <div className="w-6 h-6 rounded-full bg-purple-primary/20 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-3.5 h-3.5 text-purple-primary" />
          </div>
        )}

        <span className="text-sm text-text-primary max-w-[120px] truncate">
          {selectedApp ? selectedApp.name : 'Omi'}
        </span>

        <ChevronDown className={cn(
          'w-4 h-4 text-text-tertiary transition-transform',
          isOpen && 'rotate-180'
        )} />
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
              'absolute top-full left-0 mt-2 z-50',
              'min-w-[200px] max-w-[280px]',
              'bg-bg-secondary border border-bg-tertiary rounded-xl',
              'shadow-lg overflow-hidden'
            )}
          >
            {isLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-5 h-5 text-text-tertiary animate-spin" />
              </div>
            ) : (
              <div className="py-1 max-h-[300px] overflow-y-auto">
                {/* Default Omi option */}
                <button
                  onClick={() => {
                    onSelectApp(null);
                    setIsOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-2.5',
                    'hover:bg-bg-tertiary transition-colors',
                    !selectedAppId && 'bg-bg-tertiary/50'
                  )}
                >
                  <div className="w-8 h-8 rounded-full bg-purple-primary/20 flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-4 h-4 text-purple-primary" />
                  </div>
                  <div className="flex-1 text-left">
                    <p className="text-sm font-medium text-text-primary">Omi</p>
                    <p className="text-xs text-text-tertiary">Default assistant</p>
                  </div>
                  {!selectedAppId && (
                    <Check className="w-4 h-4 text-purple-primary flex-shrink-0" />
                  )}
                </button>

                {/* Separator if there are apps */}
                {apps.length > 0 && (
                  <div className="border-t border-bg-tertiary my-1" />
                )}

                {/* Chat apps list */}
                {apps.map(app => (
                  <button
                    key={app.id}
                    onClick={() => {
                      onSelectApp(app.id);
                      setIsOpen(false);
                    }}
                    className={cn(
                      'w-full flex items-center gap-3 px-4 py-2.5',
                      'hover:bg-bg-tertiary transition-colors',
                      selectedAppId === app.id && 'bg-bg-tertiary/50'
                    )}
                  >
                    <div className="w-8 h-8 rounded-full overflow-hidden bg-bg-quaternary flex-shrink-0">
                      {app.image ? (
                        <Image
                          src={app.image}
                          alt={app.name}
                          width={32}
                          height={32}
                          className="object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-text-tertiary text-sm">
                          {app.name.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="flex-1 text-left min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">
                        {app.name}
                      </p>
                      {app.description && (
                        <p className="text-xs text-text-tertiary truncate">
                          {app.description}
                        </p>
                      )}
                    </div>
                    {selectedAppId === app.id && (
                      <Check className="w-4 h-4 text-purple-primary flex-shrink-0" />
                    )}
                  </button>
                ))}

                {/* Empty state */}
                {apps.length === 0 && (
                  <div className="px-4 py-3 text-center">
                    <p className="text-sm text-text-tertiary">
                      No chat apps enabled
                    </p>
                    <p className="text-xs text-text-quaternary mt-1">
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
