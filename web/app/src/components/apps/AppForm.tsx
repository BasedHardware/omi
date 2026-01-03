'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { cn } from '@/lib/utils';
import {
  getAppCategories,
  getAppCapabilities,
  getNotificationScopes,
  getPaymentPlans,
  createApp,
  updateApp,
  uploadAppThumbnail,
  generateAppDescription,
  deleteApp,
} from '@/lib/api';
import type {
  App,
  AppCategory,
  AppCapability,
  NotificationScope,
  PaymentPlan,
  CreateAppRequest,
  ThumbnailUploadResponse,
} from '@/types/apps';
import { PageHeader } from '@/components/layout/PageHeader';
import { LayoutGrid } from 'lucide-react';

// Icons
function ImageIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function SparklesIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
    </svg>
  );
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  );
}

function XIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  );
}

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
    </svg>
  );
}

interface AppFormProps {
  mode: 'create' | 'edit';
  app?: App;
}

// Design system constants
const sectionCardClass = 'rounded-2xl p-5 bg-gradient-to-b from-white/[0.03] to-white/[0.01] shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]';
const inputClass = 'w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-bg-quaternary text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-purple-primary/50';
const textareaClass = 'w-full px-4 py-3 rounded-xl resize-none bg-bg-tertiary border border-bg-quaternary text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-purple-primary/50';

export function AppForm({ mode, app }: AppFormProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const thumbnailInputRef = useRef<HTMLInputElement>(null);
  const categoryDropdownRef = useRef<HTMLDivElement>(null);

  // Dropdown states
  const [isCategoryOpen, setIsCategoryOpen] = useState(false);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (categoryDropdownRef.current && !categoryDropdownRef.current.contains(event.target as Node)) {
        setIsCategoryOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Loading states
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingDescription, setIsGeneratingDescription] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Metadata from API
  const [categories, setCategories] = useState<AppCategory[]>([]);
  const [capabilities, setCapabilities] = useState<AppCapability[]>([]);
  const [notificationScopes, setNotificationScopes] = useState<NotificationScope[]>([]);
  const [paymentPlans, setPaymentPlans] = useState<PaymentPlan[]>([]);

  // Form data
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [selectedCapabilities, setSelectedCapabilities] = useState<string[]>([]);

  // Logo
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);

  // Thumbnails
  const [thumbnails, setThumbnails] = useState<{ url: string; id: string }[]>([]);
  const [uploadingThumbnail, setUploadingThumbnail] = useState(false);

  // Prompts
  const [chatPrompt, setChatPrompt] = useState('');
  const [memoryPrompt, setMemoryPrompt] = useState('');
  const [personaPrompt, setPersonaPrompt] = useState('');

  // External integration
  const [triggerEvent, setTriggerEvent] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [setupCompletedUrl, setSetupCompletedUrl] = useState('');
  const [appHomeUrl, setAppHomeUrl] = useState('');

  // Notification scopes
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);

  // Privacy & Payment
  const [isPrivate, setIsPrivate] = useState(true);
  const [isPaid, setIsPaid] = useState(false);
  const [price, setPrice] = useState('');
  const [paymentPlan, setPaymentPlan] = useState('');

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Load metadata
  useEffect(() => {
    async function loadMetadata() {
      try {
        const [cats, caps, scopes, plans] = await Promise.all([
          getAppCategories(),
          getAppCapabilities(),
          getNotificationScopes(),
          getPaymentPlans(),
        ]);
        setCategories(cats);
        setCapabilities(caps);
        setNotificationScopes(scopes);
        setPaymentPlans(plans);
      } catch (err) {
        console.error('Failed to load metadata:', err);
        setError('Failed to load form data');
      } finally {
        setIsLoading(false);
      }
    }
    loadMetadata();
  }, []);

  // Load app data for edit mode
  useEffect(() => {
    if (mode === 'edit' && app) {
      setName(app.name);
      setDescription(app.description);
      setCategory(app.category);
      setSelectedCapabilities(app.capabilities || []);
      setLogoPreview(app.image || null);
      setChatPrompt(app.chat_prompt || '');
      setMemoryPrompt(app.memory_prompt || '');
      setPersonaPrompt(app.persona_prompt || '');
      setIsPrivate(app.private || false);
      setIsPaid(app.is_paid || false);
      setPrice(app.price?.toString() || '');
      setPaymentPlan(app.payment_plan || '');

      if (app.external_integration) {
        setTriggerEvent(app.external_integration.triggers_on || '');
        setWebhookUrl(app.external_integration.webhook_url || '');
        setSetupCompletedUrl(app.external_integration.setup_completed_url || '');
        setAppHomeUrl(app.external_integration.app_home_url || '');
      }

      if (app.thumbnail_urls) {
        setThumbnails(app.thumbnail_urls.map((url, i) => ({ url, id: `existing-${i}` })));
      }
    }
  }, [mode, app]);

  // Capability helpers
  const hasCapability = (cap: string) => selectedCapabilities.includes(cap);
  const hasChat = hasCapability('chat');
  const hasMemories = hasCapability('memories');
  const hasPersona = hasCapability('persona');
  const hasExternalIntegration = hasCapability('external_integration');
  const hasProactiveNotification = hasCapability('proactive_notification');

  const toggleCapability = (capId: string) => {
    setSelectedCapabilities(prev => {
      // Persona is exclusive
      if (capId === 'persona') {
        if (prev.includes('persona')) {
          return prev.filter(c => c !== 'persona');
        }
        return ['persona'];
      }

      // If selecting other capability while persona is selected, remove persona
      if (prev.includes('persona')) {
        return [capId];
      }

      if (prev.includes(capId)) {
        return prev.filter(c => c !== capId);
      }
      return [...prev, capId];
    });
  };

  // Logo handling
  const handleLogoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setLogoFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setLogoPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  // Thumbnail handling
  const handleThumbnailSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingThumbnail(true);
    try {
      const result = await uploadAppThumbnail(file);
      setThumbnails(prev => [...prev, { url: result.thumbnail_url, id: result.thumbnail_id }]);
    } catch (err) {
      console.error('Failed to upload thumbnail:', err);
      setError('Failed to upload screenshot');
    } finally {
      setUploadingThumbnail(false);
      if (thumbnailInputRef.current) {
        thumbnailInputRef.current.value = '';
      }
    }
  };

  const removeThumbnail = (id: string) => {
    setThumbnails(prev => prev.filter(t => t.id !== id));
  };

  // AI description generation
  const handleGenerateDescription = async () => {
    if (!name) {
      setError('Please enter an app name first');
      return;
    }

    setIsGeneratingDescription(true);
    try {
      const generated = await generateAppDescription(name, description);
      setDescription(generated);
    } catch (err) {
      console.error('Failed to generate description:', err);
      setError('Failed to generate description');
    } finally {
      setIsGeneratingDescription(false);
    }
  };

  // Form validation
  const validateForm = (): boolean => {
    if (!name.trim()) {
      setError('App name is required');
      return false;
    }
    if (!description.trim()) {
      setError('App description is required');
      return false;
    }
    if (!category) {
      setError('Please select a category');
      return false;
    }
    if (selectedCapabilities.length === 0) {
      setError('Please select at least one capability');
      return false;
    }
    if (mode === 'create' && !logoFile && !logoPreview) {
      setError('Please upload an app logo');
      return false;
    }
    if (hasChat && !chatPrompt.trim()) {
      setError('Chat prompt is required for chat capability');
      return false;
    }
    if (hasMemories && !memoryPrompt.trim()) {
      setError('Memory prompt is required for memories capability');
      return false;
    }
    if (hasExternalIntegration && !webhookUrl.trim()) {
      setError('Webhook URL is required for external integration');
      return false;
    }
    if (hasProactiveNotification && selectedScopes.length === 0) {
      setError('Please select at least one notification scope');
      return false;
    }
    if (isPaid) {
      if (!price || parseFloat(price) < 1) {
        setError('Price must be at least $1.00');
        return false;
      }
      if (!paymentPlan) {
        setError('Please select a payment plan');
        return false;
      }
    }

    setError(null);
    return true;
  };

  // Submit handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const data: CreateAppRequest = {
        name: name.trim(),
        description: description.trim(),
        category,
        capabilities: selectedCapabilities,
        private: isPrivate,
      };

      if (hasChat) {
        data.chat_prompt = chatPrompt.trim();
      }
      if (hasMemories) {
        data.memory_prompt = memoryPrompt.trim();
      }
      if (hasPersona) {
        data.persona_prompt = personaPrompt.trim();
      }
      if (hasExternalIntegration) {
        data.external_integration = {
          triggers_on: triggerEvent || undefined,
          webhook_url: webhookUrl.trim(),
          setup_completed_url: setupCompletedUrl.trim() || undefined,
          app_home_url: appHomeUrl.trim() || undefined,
        };
      }
      if (hasProactiveNotification) {
        data.proactive_notification_scopes = selectedScopes;
      }
      if (isPaid) {
        data.is_paid = true;
        data.price = parseFloat(price);
        data.payment_plan = paymentPlan;
      }

      if (mode === 'create') {
        const result = await createApp(data, logoFile || undefined);
        router.push(`/apps/${result.app_id}`);
      } else if (app) {
        await updateApp(app.id, data, logoFile || undefined);
        router.push(`/apps/${app.id}`);
      }
    } catch (err) {
      console.error('Failed to save app:', err);
      setError(err instanceof Error ? err.message : 'Failed to save app');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Delete handler
  const handleDelete = async () => {
    if (!app || mode !== 'edit') return;

    const confirmed = window.confirm(
      'Are you sure you want to delete this app? This action cannot be undone.'
    );

    if (!confirmed) return;

    setIsDeleting(true);
    try {
      await deleteApp(app.id);
      router.push('/apps');
    } catch (err) {
      console.error('Failed to delete app:', err);
      setError('Failed to delete app');
    } finally {
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Page Header */}
      <PageHeader title={mode === 'create' ? 'Create App' : 'Edit App'} icon={LayoutGrid} showBackButton />

      {/* Toolbar with Actions */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary bg-bg-secondary">
        <div className="max-w-2xl mx-auto flex items-center justify-end gap-3">
          {mode === 'edit' && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={isDeleting}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium',
                'bg-error/10 text-error',
                'hover:bg-error/20 transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <TrashIcon className="w-4 h-4" />
              {isDeleting ? 'Deleting...' : 'Delete'}
            </button>
          )}
          <button
            type="submit"
            form="app-form"
            disabled={isSubmitting}
            className={cn(
              'flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium',
              'bg-purple-primary text-white',
              'hover:bg-purple-secondary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {isSubmitting
              ? 'Saving...'
              : mode === 'create'
                ? 'Create App'
                : 'Save Changes'}
          </button>
        </div>
      </div>

      <form id="app-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-6 space-y-6">

      {/* Error display */}
      {error && (
        <div className="p-4 bg-error/10 border border-error/20 rounded-xl text-error">
          {error}
        </div>
      )}

      {/* Metadata Section */}
      <section className={cn(sectionCardClass, 'space-y-5')}>
        <h2 className="text-lg font-medium text-text-primary">Basic Info</h2>

        {/* Logo */}
        <div>
          <label className="block text-sm text-text-secondary mb-2">App Logo *</label>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'w-20 h-20 rounded-2xl border border-dashed flex items-center justify-center',
                'transition-colors hover:border-purple-primary/50',
                logoPreview ? 'border-transparent' : 'border-bg-quaternary'
              )}
            >
              {logoPreview ? (
                <Image
                  src={logoPreview}
                  alt="App logo"
                  width={80}
                  height={80}
                  className="rounded-2xl object-cover"
                />
              ) : (
                <ImageIcon className="w-8 h-8 text-text-tertiary" />
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleLogoSelect}
              className="hidden"
            />
            <span className="text-sm text-text-tertiary">
              Click to upload logo image
            </span>
          </div>
        </div>

        {/* Name */}
        <div>
          <label className="block text-sm text-text-secondary mb-2">App Name *</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Awesome App"
            className={inputClass}
          />
        </div>

        {/* Description */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm text-text-secondary">Description *</label>
            <button
              type="button"
              onClick={handleGenerateDescription}
              disabled={isGeneratingDescription || !name}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                'bg-purple-primary/10 text-purple-primary',
                'hover:bg-purple-primary/20 transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <SparklesIcon className="w-4 h-4" />
              {isGeneratingDescription ? 'Generating...' : 'Generate with AI'}
            </button>
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what your app does..."
            rows={4}
            className={textareaClass}
          />
        </div>

        {/* Category */}
        <div>
          <label className="block text-sm text-text-secondary mb-2">Category *</label>
          <div className="relative" ref={categoryDropdownRef}>
            <button
              type="button"
              onClick={() => setIsCategoryOpen(!isCategoryOpen)}
              className={cn(
                'w-full px-4 py-3 pr-10 rounded-xl text-left',
                'border transition-all',
                category
                  ? 'bg-purple-primary/10 border-purple-primary/50 text-white'
                  : 'bg-bg-tertiary border-bg-quaternary text-text-primary',
                'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
              )}
            >
              {category
                ? categories.find(c => c.id === category)?.title || 'Select a category'
                : 'Select a category'}
            </button>
            <ChevronDownIcon className={cn(
              'w-5 h-5 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none transition-all',
              category ? 'text-purple-primary' : 'text-text-tertiary',
              isCategoryOpen && 'rotate-180'
            )} />

            {/* Dropdown menu */}
            {isCategoryOpen && (
              <div className="absolute z-50 w-full mt-2 py-2 rounded-xl bg-bg-secondary border border-bg-quaternary shadow-xl max-h-64 overflow-y-auto">
                {categories.map((cat) => {
                  const isSelected = category === cat.id;
                  return (
                    <button
                      key={cat.id}
                      type="button"
                      onClick={() => {
                        setCategory(cat.id);
                        setIsCategoryOpen(false);
                      }}
                      className={cn(
                        'w-full px-4 py-2.5 text-left transition-colors flex items-center justify-between',
                        isSelected
                          ? 'bg-purple-primary/20 text-white'
                          : 'text-text-primary hover:bg-bg-tertiary'
                      )}
                    >
                      <span>{cat.title}</span>
                      {isSelected && (
                        <svg className="w-4 h-4 text-purple-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Screenshots Section */}
      <section className={cn(sectionCardClass, 'space-y-4')}>
        <h2 className="text-lg font-medium text-text-primary">Screenshots</h2>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {thumbnails.map((thumb) => (
            <div key={thumb.id} className="relative flex-shrink-0">
              <Image
                src={thumb.url}
                alt="Screenshot"
                width={120}
                height={180}
                className="rounded-xl object-cover"
              />
              <button
                type="button"
                onClick={() => removeThumbnail(thumb.id)}
                className="absolute -top-2 -right-2 p-1 bg-error rounded-full"
              >
                <XIcon className="w-3 h-3 text-white" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => thumbnailInputRef.current?.click()}
            disabled={uploadingThumbnail}
            className={cn(
              'flex-shrink-0 w-[120px] h-[180px] rounded-xl',
              'border border-dashed border-bg-quaternary',
              'flex items-center justify-center',
              'hover:border-purple-primary/50 transition-colors',
              'disabled:opacity-50'
            )}
          >
            {uploadingThumbnail ? (
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-purple-primary border-t-transparent" />
            ) : (
              <PlusIcon className="w-6 h-6 text-text-tertiary" />
            )}
          </button>
          <input
            ref={thumbnailInputRef}
            type="file"
            accept="image/*"
            onChange={handleThumbnailSelect}
            className="hidden"
          />
        </div>
      </section>

      {/* Capabilities Section */}
      <section className={cn(sectionCardClass, 'space-y-4')}>
        <h2 className="text-lg font-medium text-text-primary">Capabilities *</h2>
        <p className="text-sm text-text-tertiary">
          Select what your app can do. Persona is exclusive and cannot be combined with other capabilities.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {capabilities.map((cap) => {
            const isSelected = hasCapability(cap.id);
            return (
              <button
                key={cap.id}
                type="button"
                onClick={() => toggleCapability(cap.id)}
                className={cn(
                  'relative px-4 py-4 rounded-xl text-left transition-all',
                  'border flex items-center justify-between',
                  isSelected
                    ? 'bg-purple-primary/10 text-white border-purple-primary/50 ring-1 ring-purple-primary/30'
                    : 'bg-bg-tertiary border-transparent text-text-primary hover:bg-bg-quaternary'
                )}
              >
                <span className={cn(
                  'font-medium',
                  isSelected ? 'text-white' : 'text-text-primary'
                )}>
                  {cap.title}
                </span>
                <div className={cn(
                  'w-5 h-5 rounded-full flex items-center justify-center border-2 transition-all',
                  isSelected
                    ? 'bg-purple-primary border-purple-primary'
                    : 'border-text-quaternary bg-transparent'
                )}>
                  {isSelected && (
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Chat Prompt Section */}
      {hasChat && (
        <section className={cn(sectionCardClass, 'space-y-4')}>
          <h2 className="text-lg font-medium text-text-primary">Chat Prompt *</h2>
          <textarea
            value={chatPrompt}
            onChange={(e) => setChatPrompt(e.target.value)}
            placeholder="You are an awesome app, your job is to respond to the user queries..."
            rows={4}
            className={textareaClass}
          />
        </section>
      )}

      {/* Memory Prompt Section */}
      {hasMemories && (
        <section className={cn(sectionCardClass, 'space-y-4')}>
          <h2 className="text-lg font-medium text-text-primary">Memory Prompt *</h2>
          <textarea
            value={memoryPrompt}
            onChange={(e) => setMemoryPrompt(e.target.value)}
            placeholder="You are an awesome app, you will be given transcript and summary..."
            rows={4}
            className={textareaClass}
          />
        </section>
      )}

      {/* Persona Prompt Section */}
      {hasPersona && (
        <section className={cn(sectionCardClass, 'space-y-4')}>
          <h2 className="text-lg font-medium text-text-primary">Persona Prompt</h2>
          <textarea
            value={personaPrompt}
            onChange={(e) => setPersonaPrompt(e.target.value)}
            placeholder="Define the personality and behavior of your persona..."
            rows={4}
            className={textareaClass}
          />
        </section>
      )}

      {/* External Integration Section */}
      {hasExternalIntegration && (
        <section className={cn(sectionCardClass, 'space-y-4')}>
          <h2 className="text-lg font-medium text-text-primary">External Integration</h2>

          {/* Trigger Event */}
          <div>
            <label className="block text-sm text-text-secondary mb-2">Trigger Event</label>
            <div className="relative">
              <select
                value={triggerEvent}
                onChange={(e) => setTriggerEvent(e.target.value)}
                className={cn(
                  'w-full px-4 py-3 rounded-xl appearance-none',
                  'bg-bg-tertiary border border-bg-quaternary',
                  'text-text-primary',
                  'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                )}
              >
                <option value="">Select a trigger</option>
                <option value="memory_creation">Memory Creation</option>
                <option value="transcript_processed">Transcript Segment Processed</option>
                <option value="audio_bytes">Audio Bytes Streamed</option>
              </select>
              <ChevronDownIcon className="w-5 h-5 absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
            </div>
          </div>

          {/* Webhook URL */}
          <div>
            <label className="block text-sm text-text-secondary mb-2">Webhook URL *</label>
            <input
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://your-api.com/webhook"
              className={inputClass}
            />
          </div>

          {/* Setup Completed URL */}
          <div>
            <label className="block text-sm text-text-secondary mb-2">Setup Completed URL</label>
            <input
              type="url"
              value={setupCompletedUrl}
              onChange={(e) => setSetupCompletedUrl(e.target.value)}
              placeholder="https://your-api.com/setup-complete"
              className={inputClass}
            />
          </div>

          {/* App Home URL */}
          <div>
            <label className="block text-sm text-text-secondary mb-2">App Home URL</label>
            <input
              type="url"
              value={appHomeUrl}
              onChange={(e) => setAppHomeUrl(e.target.value)}
              placeholder="https://your-app.com"
              className={inputClass}
            />
          </div>
        </section>
      )}

      {/* Notification Scopes Section */}
      {hasProactiveNotification && notificationScopes.length > 0 && (
        <section className={cn(sectionCardClass, 'space-y-4')}>
          <h2 className="text-lg font-medium text-text-primary">Notification Scopes *</h2>
          <div className="grid grid-cols-2 gap-3">
            {notificationScopes.map((scope) => {
              const isSelected = selectedScopes.includes(scope.id);
              return (
                <button
                  key={scope.id}
                  type="button"
                  onClick={() => {
                    setSelectedScopes(prev =>
                      prev.includes(scope.id)
                        ? prev.filter(s => s !== scope.id)
                        : [...prev, scope.id]
                    );
                  }}
                  className={cn(
                    'px-4 py-4 rounded-xl text-left transition-all',
                    'border flex items-center justify-between',
                    isSelected
                      ? 'bg-purple-primary/10 text-white border-purple-primary/50 ring-1 ring-purple-primary/30'
                      : 'bg-bg-tertiary border-transparent text-text-primary hover:bg-bg-quaternary'
                  )}
                >
                  <span className={cn(
                    'font-medium',
                    isSelected ? 'text-white' : 'text-text-primary'
                  )}>
                    {scope.title}
                  </span>
                  <div className={cn(
                    'w-5 h-5 rounded-full flex items-center justify-center border-2 transition-all',
                    isSelected
                      ? 'bg-purple-primary border-purple-primary'
                      : 'border-text-quaternary bg-transparent'
                  )}>
                    {isSelected && (
                      <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Privacy & Payment Section */}
      <section className={cn(sectionCardClass, 'space-y-4')}>
        <h2 className="text-lg font-medium text-text-primary">Settings</h2>

        {/* Privacy Toggle */}
        <div className={cn(
          'flex items-center justify-between p-4 rounded-xl transition-all',
          !isPrivate
            ? 'bg-purple-primary/10'
            : 'bg-bg-tertiary'
        )}>
          <div>
            <p className="text-text-primary font-medium">Make Public</p>
            <p className="text-sm text-text-tertiary">
              {isPrivate ? 'Only you can use this app' : 'Anyone can discover your app'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setIsPrivate(!isPrivate)}
            className={cn(
              'relative w-14 h-8 rounded-full transition-all',
              !isPrivate ? 'bg-purple-primary' : 'bg-bg-quaternary'
            )}
          >
            <div
              className={cn(
                'absolute top-1 w-6 h-6 rounded-full bg-white transition-all shadow-md',
                !isPrivate ? 'left-7' : 'left-1'
              )}
            />
          </button>
        </div>

        {/* Paid App Toggle */}
        {paymentPlans.length > 0 && (
          <>
            <div className={cn(
              'flex items-center justify-between p-4 rounded-xl transition-all',
              isPaid
                ? 'bg-purple-primary/10'
                : 'bg-bg-tertiary'
            )}>
              <div>
                <p className="text-text-primary font-medium">Paid App</p>
                <p className="text-sm text-text-tertiary">
                  Charge users for your app
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsPaid(!isPaid)}
                className={cn(
                  'relative w-14 h-8 rounded-full transition-all',
                  isPaid ? 'bg-purple-primary' : 'bg-bg-quaternary'
                )}
              >
                <div
                  className={cn(
                    'absolute top-1 w-6 h-6 rounded-full bg-white transition-all shadow-md',
                    isPaid ? 'left-7' : 'left-1'
                  )}
                />
              </button>
            </div>

            {isPaid && (
              <div className="space-y-4 p-4 bg-bg-tertiary rounded-xl">
                {/* Price */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2">Price (USD) *</label>
                  <div className="relative">
                    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-text-tertiary">$</span>
                    <input
                      type="number"
                      value={price}
                      onChange={(e) => setPrice(e.target.value)}
                      min="1"
                      step="0.01"
                      placeholder="0.00"
                      className={cn(
                        'w-full pl-8 pr-4 py-3 rounded-xl',
                        'bg-bg-secondary border border-bg-quaternary',
                        'text-text-primary placeholder:text-text-tertiary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                    />
                  </div>
                </div>

                {/* Payment Plan */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2">Payment Plan *</label>
                  <div className="flex gap-2">
                    {paymentPlans.map((plan) => {
                      const isSelected = paymentPlan === plan.id;
                      return (
                        <button
                          key={plan.id}
                          type="button"
                          onClick={() => setPaymentPlan(plan.id)}
                          className={cn(
                            'flex-1 px-4 py-3 rounded-xl text-sm font-medium transition-all',
                            'border',
                            isSelected
                              ? 'bg-purple-primary/10 text-white border-purple-primary/50'
                              : 'bg-bg-secondary border-bg-quaternary text-text-secondary hover:bg-bg-quaternary'
                          )}
                        >
                          {plan.title}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* Bottom padding to ensure content isn't cut off */}
      <div className="h-4" />
        </div>
      </form>
    </div>
  );
}
