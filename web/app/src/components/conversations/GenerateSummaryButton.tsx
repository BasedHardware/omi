'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Sparkles, Loader2, ChevronDown, X, MessageSquare, Send, ArrowLeft } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { getApp, reprocessConversation, testConversationPrompt } from '@/lib/api';
import type { App } from '@/types/apps';
import type { Conversation, AppResponse } from '@/types/conversation';

interface GenerateSummaryButtonProps {
  conversationId: string;
  suggestedAppIds: string[];
  existingAppResults: AppResponse[];
  onGenerateComplete?: (conversation: Conversation) => void;
  className?: string;
}

type ViewMode = 'apps' | 'prompt' | 'result';

export function GenerateSummaryButton({
  conversationId,
  suggestedAppIds,
  existingAppResults,
  onGenerateComplete,
  className,
}: GenerateSummaryButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('apps');
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customPrompt, setCustomPrompt] = useState('');
  const [promptResult, setPromptResult] = useState<string | null>(null);
  const [testingPrompt, setTestingPrompt] = useState(false);
  const [isMac, setIsMac] = useState(true);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const promptInputRef = useRef<HTMLTextAreaElement>(null);

  // Detect OS for keyboard shortcut display
  useEffect(() => {
    setIsMac(navigator.platform.toLowerCase().includes('mac'));
  }, []);

  // Filter out apps that already have summaries
  const existingAppIds = new Set(existingAppResults.map(r => r.app_id));
  const availableAppIds = suggestedAppIds.filter(id => !existingAppIds.has(id));

  // Fetch app details when dropdown opens
  useEffect(() => {
    if (!isOpen || availableAppIds.length === 0) return;

    async function fetchApps() {
      setLoading(true);
      try {
        const appPromises = availableAppIds.map(id => getApp(id).catch(() => null));
        const results = await Promise.all(appPromises);
        setApps(results.filter((app): app is App => app !== null));
      } catch (err) {
        console.error('Failed to fetch apps:', err);
      } finally {
        setLoading(false);
      }
    }

    fetchApps();
  }, [isOpen, availableAppIds.join(',')]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        // Reset state when closing
        setTimeout(() => {
          setViewMode('apps');
          setCustomPrompt('');
          setPromptResult(null);
          setError(null);
        }, 200);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Focus prompt input when switching to prompt view
  useEffect(() => {
    if (viewMode === 'prompt' && promptInputRef.current) {
      promptInputRef.current.focus();
    }
  }, [viewMode]);

  const handleTestPrompt = async () => {
    if (!customPrompt.trim() || testingPrompt) return;

    setTestingPrompt(true);
    setError(null);

    try {
      const result = await testConversationPrompt(conversationId, customPrompt.trim());
      setPromptResult(result);
      setViewMode('result');
    } catch (err) {
      console.error('Failed to test prompt:', err);
      setError('Failed to run prompt. Please try again.');
    } finally {
      setTestingPrompt(false);
    }
  };

  const handleClose = () => {
    setIsOpen(false);
    // Reset state after animation
    setTimeout(() => {
      setViewMode('apps');
      setCustomPrompt('');
      setPromptResult(null);
      setError(null);
    }, 200);
  };

  const handleGenerateSummary = async (appId: string) => {
    setGenerating(appId);
    setError(null);

    try {
      const updatedConversation = await reprocessConversation(conversationId, appId);
      onGenerateComplete?.(updatedConversation);
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to generate summary:', err);
      setError('Failed to generate summary. Please try again.');
    } finally {
      setGenerating(null);
    }
  };

  // Always show button (for test prompt even if no apps)
  const hasApps = availableAppIds.length > 0;

  return (
    <div ref={dropdownRef} className={cn('relative', className)}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={!!generating || testingPrompt}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-lg',
          'text-sm font-medium transition-all duration-150',
          'bg-bg-tertiary hover:bg-bg-quaternary',
          'text-text-secondary hover:text-text-primary',
          'border border-bg-quaternary/50',
          (generating || testingPrompt) && 'opacity-50 cursor-not-allowed'
        )}
      >
        {generating || testingPrompt ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Plus className="w-4 h-4" />
        )}
        <span>{generating ? 'Generating...' : testingPrompt ? 'Running...' : 'Generate'}</span>
        {!generating && !testingPrompt && <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />}
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'absolute top-full right-0 mt-2 z-50',
              'w-80 max-h-[400px] overflow-y-auto',
              'bg-bg-secondary border border-bg-tertiary rounded-xl',
              'shadow-lg'
            )}
          >
            {/* Apps View */}
            {viewMode === 'apps' && (
              <>
                {/* Header */}
                <div className="flex items-center justify-between p-3 border-b border-bg-tertiary">
                  <span className="text-sm font-medium text-text-primary">Generate Summary</span>
                  <button
                    onClick={handleClose}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <X className="w-4 h-4 text-text-tertiary" />
                  </button>
                </div>

                {/* Error message */}
                {error && (
                  <div className="p-3 bg-error/10 border-b border-error/20 text-error text-sm">
                    {error}
                  </div>
                )}

                {/* Test Custom Prompt option */}
                <div className="p-2 border-b border-bg-tertiary">
                  <button
                    onClick={() => setViewMode('prompt')}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg',
                      'text-left transition-all duration-150',
                      'hover:bg-bg-tertiary'
                    )}
                  >
                    <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="w-5 h-5 text-blue-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary">
                        Test Custom Prompt
                      </p>
                      <p className="text-xs text-text-tertiary">
                        Run a custom prompt on this conversation
                      </p>
                    </div>
                  </button>
                </div>

                {/* Loading state */}
                {loading && (
                  <div className="p-4 flex items-center justify-center gap-2 text-text-tertiary">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm">Loading apps...</span>
                  </div>
                )}

                {/* Apps list */}
                {!loading && apps.length > 0 && (
                  <div className="p-2">
                    <p className="px-3 py-1.5 text-xs font-medium text-text-tertiary uppercase tracking-wide">
                      Apps
                    </p>
                    {apps.map((app) => (
                      <button
                        key={app.id}
                        onClick={() => handleGenerateSummary(app.id)}
                        disabled={!!generating}
                        className={cn(
                          'w-full flex items-center gap-3 p-3 rounded-lg',
                          'text-left transition-all duration-150',
                          'hover:bg-bg-tertiary',
                          generating === app.id && 'bg-purple-primary/10',
                          generating && generating !== app.id && 'opacity-50'
                        )}
                      >
                        {app.image ? (
                          <img
                            src={app.image}
                            alt={app.name}
                            className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-lg bg-purple-primary/20 flex items-center justify-center flex-shrink-0">
                            <Sparkles className="w-5 h-5 text-purple-primary" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-text-primary truncate">
                            {app.name}
                          </p>
                          {app.description && (
                            <p className="text-xs text-text-tertiary truncate">
                              {app.description}
                            </p>
                          )}
                        </div>
                        {generating === app.id && (
                          <Loader2 className="w-4 h-4 animate-spin text-purple-primary flex-shrink-0" />
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {/* Empty state for apps */}
                {!loading && !hasApps && (
                  <div className="p-4 text-center text-text-tertiary text-sm">
                    No additional apps available
                  </div>
                )}
              </>
            )}

            {/* Prompt Input View */}
            {viewMode === 'prompt' && (
              <>
                {/* Header */}
                <div className="flex items-center gap-2 p-3 border-b border-bg-tertiary">
                  <button
                    onClick={() => setViewMode('apps')}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4 text-text-tertiary" />
                  </button>
                  <span className="text-sm font-medium text-text-primary flex-1">Test Custom Prompt</span>
                  <button
                    onClick={handleClose}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <X className="w-4 h-4 text-text-tertiary" />
                  </button>
                </div>

                {/* Error message */}
                {error && (
                  <div className="p-3 bg-error/10 border-b border-error/20 text-error text-sm">
                    {error}
                  </div>
                )}

                {/* Prompt input */}
                <div className="p-3">
                  <textarea
                    ref={promptInputRef}
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder="Enter your custom prompt..."
                    rows={4}
                    className={cn(
                      'w-full p-3 rounded-lg resize-none',
                      'bg-bg-tertiary border border-bg-quaternary',
                      'text-sm text-text-primary placeholder:text-text-quaternary',
                      'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                    )}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        handleTestPrompt();
                      }
                    }}
                  />
                  <p className="mt-2 text-xs text-text-quaternary">
                    Press {isMac ? '⌘' : 'Ctrl'}+Enter to run
                  </p>
                  <button
                    onClick={handleTestPrompt}
                    disabled={!customPrompt.trim() || testingPrompt}
                    className={cn(
                      'w-full mt-3 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                      'text-sm font-medium transition-all duration-150',
                      'bg-purple-primary hover:bg-purple-secondary text-white',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {testingPrompt ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Running...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        <span>Run Prompt</span>
                      </>
                    )}
                  </button>
                </div>
              </>
            )}

            {/* Result View */}
            {viewMode === 'result' && promptResult && (
              <>
                {/* Header */}
                <div className="flex items-center gap-2 p-3 border-b border-bg-tertiary">
                  <button
                    onClick={() => {
                      setViewMode('prompt');
                      setPromptResult(null);
                    }}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4 text-text-tertiary" />
                  </button>
                  <span className="text-sm font-medium text-text-primary flex-1">Result</span>
                  <button
                    onClick={handleClose}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <X className="w-4 h-4 text-text-tertiary" />
                  </button>
                </div>

                {/* Result content */}
                <div className="p-3 max-h-64 overflow-y-auto">
                  <div className="p-3 rounded-lg bg-bg-tertiary border border-bg-quaternary">
                    <div className="text-sm text-text-secondary prose prose-sm prose-invert max-w-none">
                      <ReactMarkdown>{promptResult}</ReactMarkdown>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="p-3 border-t border-bg-tertiary flex gap-2">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(promptResult);
                    }}
                    className={cn(
                      'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg',
                      'text-sm font-medium transition-colors',
                      'bg-bg-tertiary hover:bg-bg-quaternary text-text-secondary hover:text-text-primary'
                    )}
                  >
                    Copy Result
                  </button>
                  <button
                    onClick={() => {
                      setViewMode('prompt');
                      setPromptResult(null);
                    }}
                    className={cn(
                      'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg',
                      'text-sm font-medium transition-colors',
                      'bg-purple-primary hover:bg-purple-secondary text-white'
                    )}
                  >
                    Try Another
                  </button>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
