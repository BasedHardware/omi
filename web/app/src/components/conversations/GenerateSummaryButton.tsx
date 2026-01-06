'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Sparkles, Loader2, ChevronDown, X, MessageSquare, Send, ArrowLeft, Lock, Globe, Star } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { getApp, reprocessConversation, testConversationPrompt, createApp, enableApp, generateAppDescriptionAndEmoji, getInstalledApps } from '@/lib/api';
import { auth } from '@/lib/firebase';
import type { App } from '@/types/apps';
import type { Conversation, AppResponse } from '@/types/conversation';

interface GenerateSummaryButtonProps {
  conversationId: string;
  suggestedAppIds: string[];
  existingAppResults: AppResponse[];
  onGenerateComplete?: (conversation: Conversation) => void;
  className?: string;
}

/**
 * Generate a PNG icon from an emoji using canvas
 * Creates a 256x256 image with white background and centered emoji
 * Matches the mobile app's icon generation approach
 */
async function generateEmojiIcon(emoji: string): Promise<File> {
  const size = 256;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('Failed to get canvas context');
  }

  // Draw white background
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, size, size);

  // Draw emoji centered
  ctx.font = '140px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(emoji, size / 2, size / 2);

  // Convert canvas to blob then to File
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        const file = new File([blob], `template_icon_${Date.now()}.png`, { type: 'image/png' });
        resolve(file);
      } else {
        reject(new Error('Failed to create icon blob'));
      }
    }, 'image/png');
  });
}

type ViewMode = 'apps' | 'prompt' | 'result' | 'create' | 'save';

export function GenerateSummaryButton({
  conversationId,
  suggestedAppIds,
  existingAppResults,
  onGenerateComplete,
  className,
}: GenerateSummaryButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('apps');
  const [apps, setApps] = useState<App[]>([]); // Suggested templates
  const [userTemplates, setUserTemplates] = useState<App[]>([]); // User's enabled templates
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customPrompt, setCustomPrompt] = useState('');
  const [promptResult, setPromptResult] = useState<string | null>(null);
  const [testingPrompt, setTestingPrompt] = useState(false);
  const [isMac, setIsMac] = useState(true);
  // Template creation state
  const [templateName, setTemplateName] = useState('');
  const [templatePrompt, setTemplatePrompt] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const promptInputRef = useRef<HTMLTextAreaElement>(null);
  const templateNameInputRef = useRef<HTMLInputElement>(null);

  // Detect OS for keyboard shortcut display
  useEffect(() => {
    setIsMac(navigator.platform.toLowerCase().includes('mac'));
  }, []);

  // Filter out apps that already have summaries
  const existingAppIds = new Set(existingAppResults.map(r => r.app_id));
  const availableAppIds = suggestedAppIds.filter(id => !existingAppIds.has(id));

  // Fetch app details when dropdown opens
  useEffect(() => {
    if (!isOpen) return;

    async function fetchApps() {
      setLoading(true);
      try {
        // Fetch suggested apps and user's installed templates in parallel
        const [suggestedResults, installedResponse] = await Promise.all([
          // Fetch suggested apps
          availableAppIds.length > 0
            ? Promise.all(availableAppIds.map(id => getApp(id).catch(() => null)))
            : Promise.resolve([]),
          // Fetch user's installed apps
          getInstalledApps().catch(() => ({ data: [] })),
        ]);

        // Set suggested apps
        setApps(suggestedResults.filter((app): app is App => app !== null));

        // Filter installed apps to only memory templates, excluding suggested ones
        const suggestedIdSet = new Set(availableAppIds);
        const memoryTemplates = installedResponse.data.filter(
          (app) => app.capabilities?.includes('memories') && !suggestedIdSet.has(app.id)
        );
        setUserTemplates(memoryTemplates);
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
          setTemplateName('');
          setTemplatePrompt('');
          setIsPublic(false);
        }, 200);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Focus template name input when switching to create/save view
  useEffect(() => {
    if ((viewMode === 'create' || viewMode === 'save') && templateNameInputRef.current) {
      templateNameInputRef.current.focus();
    }
  }, [viewMode]);

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
      setTemplateName('');
      setTemplatePrompt('');
      setIsPublic(false);
    }, 200);
  };

  const handleCreateTemplate = async () => {
    if (!templateName.trim() || !templatePrompt.trim() || creatingTemplate) return;

    // Validation
    if (templateName.trim().length < 3) {
      setError('Template name must be at least 3 characters');
      return;
    }
    if (templatePrompt.trim().length < 10) {
      setError('Prompt must be at least 10 characters');
      return;
    }

    setCreatingTemplate(true);
    setError(null);

    try {
      // Generate description and emoji using AI (matches mobile app behavior)
      const { description, emoji } = await generateAppDescriptionAndEmoji(
        templateName.trim(),
        templatePrompt.trim()
      );

      // Generate icon from emoji using canvas
      const iconFile = await generateEmojiIcon(emoji);

      // Create the template app (matching mobile app's payload structure)
      const appData = {
        name: templateName.trim(),
        description: description,
        category: 'conversation-analysis',
        capabilities: ['memories'],
        private: !isPublic,
        is_paid: false,
        price: 0.0,
        memory_prompt: templatePrompt.trim(),
        deleted: false,
        thumbnails: [],
        uid: auth.currentUser?.uid, // Critical: associates app with user
      };

      const { app_id } = await createApp(appData, iconFile);

      // Try to auto-enable the newly created template (non-critical)
      // The app is already owned by the user, so it should work even if enable fails
      try {
        await enableApp(app_id);
      } catch (enableErr) {
        console.warn('Failed to auto-enable template (non-critical):', enableErr);
        // Continue anyway - the app was created successfully
      }

      // Close dropdown and notify parent to refresh
      handleClose();

      // Optionally trigger a summary generation with the new template
      if (onGenerateComplete) {
        const updatedConversation = await reprocessConversation(conversationId, app_id);
        onGenerateComplete(updatedConversation);
      }
    } catch (err) {
      console.error('Failed to create template:', err);
      setError('Failed to create template. Please try again.');
    } finally {
      setCreatingTemplate(false);
    }
  };

  const handleSaveAsTemplate = () => {
    // Pre-fill the template prompt with the tested prompt
    setTemplatePrompt(customPrompt);
    setViewMode('save');
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
          'flex items-center gap-2 px-3 py-1.5 rounded-lg',
          'text-sm font-medium transition-all duration-150',
          'bg-bg-tertiary hover:bg-bg-quaternary',
          'text-text-secondary hover:text-text-primary',
          'border border-bg-quaternary/50',
          (generating || testingPrompt) && 'opacity-50 cursor-not-allowed'
        )}
      >
        {generating || testingPrompt ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{generating ? 'Generating...' : 'Running...'}</span>
          </>
        ) : (
          <>
            <span>Templates</span>
            <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
          </>
        )}
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
              'overflow-y-auto',
              'bg-bg-secondary border border-bg-tertiary rounded-xl',
              'shadow-lg',
              // Compact size only for apps list view
              viewMode === 'apps'
                ? 'w-80 max-h-[400px]'
                : 'w-96 max-h-[520px]'
            )}
          >
            {/* Apps View */}
            {viewMode === 'apps' && (
              <>
                {/* Header */}
                <div className="flex items-center justify-between p-3 border-b border-bg-tertiary">
                  <span className="text-sm font-medium text-text-primary">Generate</span>
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

                {/* Create Custom Template option */}
                <div className="p-2 border-b border-bg-tertiary">
                  <button
                    onClick={() => {
                      setTemplatePrompt('');
                      setTemplateName('');
                      setViewMode('create');
                    }}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg',
                      'text-left transition-all duration-150',
                      'hover:bg-bg-tertiary'
                    )}
                  >
                    <div className="w-10 h-10 rounded-lg bg-purple-primary/20 flex items-center justify-center flex-shrink-0">
                      <Plus className="w-5 h-5 text-purple-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary">
                        Create Custom Template
                      </p>
                      <p className="text-xs text-text-tertiary">
                        Create a reusable summary template
                      </p>
                    </div>
                  </button>

                  {/* Test Custom Prompt option */}
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
                        Try a prompt before saving as template
                      </p>
                    </div>
                  </button>
                </div>

                {/* Loading state */}
                {loading && (
                  <div className="p-4 flex items-center justify-center gap-2 text-text-tertiary">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm">Loading templates...</span>
                  </div>
                )}

                {/* Templates list */}
                {!loading && apps.length > 0 && (
                  <div className="p-2">
                    <p className="px-3 py-1.5 text-xs font-medium text-text-tertiary uppercase tracking-wide">
                      Suggested Templates
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

                {/* User's enabled templates */}
                {!loading && userTemplates.length > 0 && (
                  <div className="p-2 border-t border-bg-tertiary">
                    <p className="px-3 py-1.5 text-xs font-medium text-text-tertiary uppercase tracking-wide">
                      Your Templates
                    </p>
                    {userTemplates.map((app) => (
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

                {/* Empty state for templates */}
                {!loading && !hasApps && userTemplates.length === 0 && (
                  <div className="p-4 text-center text-text-tertiary text-sm">
                    No templates available. Create one above!
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
                <div className="p-4">
                  <textarea
                    ref={promptInputRef}
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder="Enter your custom prompt to extract insights, summaries, action items, or any other information from this conversation..."
                    rows={8}
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
                <div className="p-3 border-t border-bg-tertiary space-y-2">
                  <div className="flex gap-2">
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
                        'bg-bg-tertiary hover:bg-bg-quaternary text-text-secondary hover:text-text-primary'
                      )}
                    >
                      Try Another
                    </button>
                  </div>
                  <button
                    onClick={handleSaveAsTemplate}
                    className={cn(
                      'w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                      'text-sm font-medium transition-colors',
                      'bg-purple-primary hover:bg-purple-secondary text-white'
                    )}
                  >
                    <Star className="w-4 h-4" />
                    Save as Template
                  </button>
                </div>
              </>
            )}

            {/* Create Template View */}
            {viewMode === 'create' && (
              <>
                {/* Header */}
                <div className="flex items-center gap-2 p-3 border-b border-bg-tertiary">
                  <button
                    onClick={() => setViewMode('apps')}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4 text-text-tertiary" />
                  </button>
                  <span className="text-sm font-medium text-text-primary flex-1">Create Template</span>
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

                {/* Form */}
                <div className="p-3 space-y-4">
                  {/* Template Name */}
                  <div>
                    <label className="block text-xs font-medium text-text-tertiary mb-1.5">
                      Template Name
                    </label>
                    <input
                      ref={templateNameInputRef}
                      type="text"
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      placeholder="e.g., Meeting Action Items"
                      className={cn(
                        'w-full p-3 rounded-lg',
                        'bg-bg-tertiary border border-bg-quaternary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                    />
                  </div>

                  {/* Prompt */}
                  <div>
                    <label className="block text-xs font-medium text-text-tertiary mb-1.5">
                      Prompt
                    </label>
                    <textarea
                      value={templatePrompt}
                      onChange={(e) => setTemplatePrompt(e.target.value)}
                      placeholder="e.g., Extract all action items, decisions made, and key takeaways from this conversation..."
                      rows={4}
                      className={cn(
                        'w-full p-3 rounded-lg resize-none',
                        'bg-bg-tertiary border border-bg-quaternary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                    />
                  </div>

                  {/* Public/Private Toggle */}
                  <button
                    onClick={() => setIsPublic(!isPublic)}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg',
                      'text-left transition-all duration-150',
                      'bg-bg-tertiary hover:bg-bg-quaternary'
                    )}
                  >
                    <div className={cn(
                      'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0',
                      isPublic ? 'bg-green-500/20' : 'bg-bg-quaternary'
                    )}>
                      {isPublic ? (
                        <Globe className="w-5 h-5 text-green-400" />
                      ) : (
                        <Lock className="w-5 h-5 text-text-tertiary" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary">
                        {isPublic ? 'Public' : 'Private'}
                      </p>
                      <p className="text-xs text-text-tertiary">
                        {isPublic ? 'Anyone can discover your template' : 'Only you can use this template'}
                      </p>
                    </div>
                  </button>

                  {/* Create Button */}
                  <button
                    onClick={handleCreateTemplate}
                    disabled={!templateName.trim() || !templatePrompt.trim() || creatingTemplate}
                    className={cn(
                      'w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                      'text-sm font-medium transition-all duration-150',
                      'bg-purple-primary hover:bg-purple-secondary text-white',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {creatingTemplate ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Creating...</span>
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        <span>Create Template</span>
                      </>
                    )}
                  </button>
                </div>
              </>
            )}

            {/* Save as Template View (after testing prompt) */}
            {viewMode === 'save' && (
              <>
                {/* Header */}
                <div className="flex items-center gap-2 p-3 border-b border-bg-tertiary">
                  <button
                    onClick={() => setViewMode('result')}
                    className="p-1 rounded-md hover:bg-bg-tertiary transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4 text-text-tertiary" />
                  </button>
                  <span className="text-sm font-medium text-text-primary flex-1">Save as Template</span>
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

                {/* Form */}
                <div className="p-3 space-y-4">
                  {/* Template Name */}
                  <div>
                    <label className="block text-xs font-medium text-text-tertiary mb-1.5">
                      Template Name
                    </label>
                    <input
                      ref={templateNameInputRef}
                      type="text"
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      placeholder="e.g., Meeting Action Items"
                      className={cn(
                        'w-full p-3 rounded-lg',
                        'bg-bg-tertiary border border-bg-quaternary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                    />
                  </div>

                  {/* Prompt (pre-filled, editable) */}
                  <div>
                    <label className="block text-xs font-medium text-text-tertiary mb-1.5">
                      Prompt
                    </label>
                    <textarea
                      value={templatePrompt}
                      onChange={(e) => setTemplatePrompt(e.target.value)}
                      rows={4}
                      className={cn(
                        'w-full p-3 rounded-lg resize-none',
                        'bg-bg-tertiary border border-bg-quaternary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                    />
                  </div>

                  {/* Public/Private Toggle */}
                  <button
                    onClick={() => setIsPublic(!isPublic)}
                    className={cn(
                      'w-full flex items-center gap-3 p-3 rounded-lg',
                      'text-left transition-all duration-150',
                      'bg-bg-tertiary hover:bg-bg-quaternary'
                    )}
                  >
                    <div className={cn(
                      'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0',
                      isPublic ? 'bg-green-500/20' : 'bg-bg-quaternary'
                    )}>
                      {isPublic ? (
                        <Globe className="w-5 h-5 text-green-400" />
                      ) : (
                        <Lock className="w-5 h-5 text-text-tertiary" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary">
                        {isPublic ? 'Public' : 'Private'}
                      </p>
                      <p className="text-xs text-text-tertiary">
                        {isPublic ? 'Anyone can discover your template' : 'Only you can use this template'}
                      </p>
                    </div>
                  </button>

                  {/* Create Button */}
                  <button
                    onClick={handleCreateTemplate}
                    disabled={!templateName.trim() || !templatePrompt.trim() || creatingTemplate}
                    className={cn(
                      'w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                      'text-sm font-medium transition-all duration-150',
                      'bg-purple-primary hover:bg-purple-secondary text-white',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {creatingTemplate ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Creating...</span>
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        <span>Create Template</span>
                      </>
                    )}
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
