'use client';

import { useState, useEffect } from 'react';
import Image from '@tschk/moonshine-next/image';
import Link from '@tschk/moonshine-next/link';
import { useRouter } from '@tschk/moonshine-next/navigation';
import {
  ArrowLeft,
  Star,
  Download,
  Loader2,
  Check,
  Lock,
  MessageSquare,
  ExternalLink,
  Zap,
  Brain,
  Share2,
  Pencil,
  LayoutGrid,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn, urlWithUidParam } from '@/lib/utils';
import { getApp, enableApp, disableApp, reEnableApp } from '@/lib/api';
import type { App } from '@/types/apps';
import { AppDisabledNotice } from '@/components/apps/AppDisabledNotice';
import { PageHeader } from '@/components/layout/PageHeader';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface AppDetailProps {
  appId: string;
}

// Capability display info
const CAPABILITY_INFO: Record<
  string,
  { icon: React.ReactNode; label: string; color: string }
> = {
  chat: {
    icon: <MessageSquare className="h-4 w-4" />,
    label: 'Chat',
    color: 'text-blue-400',
  },
  persona: {
    icon: <Brain className="h-4 w-4" />,
    label: 'Persona',
    color: 'text-text-secondary',
  },
  memories: {
    icon: <Brain className="h-4 w-4" />,
    label: 'Conversations',
    color: 'text-green-400',
  },
  external_integration: {
    icon: <ExternalLink className="h-4 w-4" />,
    label: 'External Integration',
    color: 'text-orange-400',
  },
  proactive_notification: {
    icon: <Zap className="h-4 w-4" />,
    label: 'Proactive Notifications',
    color: 'text-yellow-400',
  },
};

export function AppDetail({ appId }: AppDetailProps) {
  const router = useRouter();
  const { user } = useAuth();
  const [app, setApp] = useState<App | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isToggling, setIsToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isReEnabling, setIsReEnabling] = useState(false);
  const [reEnableError, setReEnableError] = useState<string | null>(null);

  // Check if user owns this app
  const isOwner = user && app?.uid === user.uid;

  useEffect(() => {
    async function loadApp() {
      setIsLoading(true);
      setError(null);
      setReEnableError(null);
      try {
        const appData = await getApp(appId);
        setApp(appData);
      } catch (err) {
        console.error('Failed to load app:', err);
        setError('Failed to load app details');
      } finally {
        setIsLoading(false);
      }
    }
    loadApp();
  }, [appId]);

  const handleToggle = async () => {
    if (!app) return;

    setIsToggling(true);
    try {
      if (app.enabled) {
        await disableApp(app.id);
        MixpanelManager.track('App Disabled', { app_id: app.id });
        setApp({ ...app, enabled: false });
      } else {
        await enableApp(app.id);
        MixpanelManager.track('App Enabled', { app_id: app.id });
        setApp({ ...app, enabled: true });
      }
    } catch (err) {
      console.error('Failed to toggle app:', err);
    } finally {
      setIsToggling(false);
    }
  };

  const handleReEnable = async () => {
    if (!app) return;

    setIsReEnabling(true);
    setReEnableError(null);
    try {
      await reEnableApp(app.id);
      MixpanelManager.track('App Re-enabled', { app_id: app.id });
      setApp({
        ...app,
        disabled: false,
        disabled_reason: undefined,
        disabled_at: undefined,
        disabled_error: undefined,
      });
    } catch (err) {
      setReEnableError(
        err instanceof Error ? err.message : 'Failed to re-enable this app',
      );
    } finally {
      setIsReEnabling(false);
    }
  };

  const handleShare = async () => {
    if (!app) return;

    const url = `${window.location.origin}/connectors/${app.id}`;
    if (navigator.share) {
      try {
        await navigator.share({
          title: app.name,
          text: app.description,
          url,
        });
      } catch {
        // User cancelled or share failed
      }
    } else {
      await navigator.clipboard.writeText(url);
      // Could show a toast here
    }
  };

  const formatInstalls = (count?: number): string => {
    if (!count) return '0';
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
    return count.toString();
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-text-primary" />
      </div>
    );
  }

  if (error || !app) {
    return (
      <div className="py-12 text-center">
        <p className="text-text-tertiary">{error || 'App not found'}</p>
        <Link
          href="/connectors"
          className="mt-2 inline-block text-text-primary hover:underline"
        >
          Back to Apps
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Page Header */}
      <PageHeader title="App Details" icon={LayoutGrid} showBackButton />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4 py-6">
          {app.disabled && (
            <AppDisabledNotice
              app={app}
              isOwner={!!isOwner}
              onReEnable={handleReEnable}
              isReEnabling={isReEnabling}
              error={reEnableError}
            />
          )}

          {/* App Hero */}
          <div className="mb-8 flex flex-col gap-6 sm:flex-row">
            {/* App icon */}
            <div className="mx-auto h-24 w-24 flex-shrink-0 overflow-hidden rounded-2xl bg-bg-tertiary sm:mx-0 sm:h-28 sm:w-28">
              {app.image ? (
                <Image
                  src={app.image}
                  alt={app.name}
                  width={112}
                  height={112}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-3xl font-medium text-text-tertiary">
                  {app.name.charAt(0)}
                </div>
              )}
            </div>

            {/* App info */}
            <div className="flex-1 text-center sm:text-left">
              <h1 className="flex items-center justify-center gap-2 text-2xl font-bold text-text-primary sm:justify-start">
                {app.name}
                {app.private && <Lock className="h-5 w-5 text-text-quaternary" />}
              </h1>
              <p className="mt-1 text-text-secondary">{app.author || 'Unknown author'}</p>

              {/* Stats */}
              <div className="mt-3 flex items-center justify-center gap-4 text-sm text-text-tertiary sm:justify-start">
                {app.rating_avg !== undefined && app.rating_avg > 0 && (
                  <span className="flex items-center gap-1">
                    <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                    {app.rating_avg.toFixed(1)}
                    {app.rating_count ? ` (${app.rating_count} reviews)` : ''}
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <Download className="h-4 w-4" />
                  {formatInstalls(app.installs)} installs
                </span>
              </div>

              {/* Action buttons */}
              <div className="mt-4 flex items-center justify-center gap-3 sm:justify-start">
                <button
                  onClick={handleToggle}
                  disabled={
                    isToggling || isReEnabling || (!!app.disabled && !app.enabled)
                  }
                  title={
                    app.disabled && !app.enabled
                      ? 'This app is disabled and cannot be installed'
                      : undefined
                  }
                  className={cn(
                    'rounded-xl px-6 py-2.5 font-medium',
                    'flex items-center gap-2 transition-colors',
                    app.enabled
                      ? 'bg-red-500/10 text-red-500 hover:bg-red-500/20'
                      : 'bg-white text-black hover:bg-white/90',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                  )}
                >
                  {isToggling ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : app.enabled ? (
                    <>Uninstall</>
                  ) : (
                    <>
                      <Download className="h-5 w-5" />
                      Install
                    </>
                  )}
                </button>

                <button
                  onClick={handleShare}
                  className={cn(
                    'rounded-xl p-2.5',
                    'border border-bg-quaternary',
                    'text-text-secondary hover:bg-bg-tertiary',
                    'transition-colors',
                  )}
                >
                  <Share2 className="h-5 w-5" />
                </button>

                {isOwner && (
                  <button
                    onClick={() => router.push(`/connectors/${app.id}/edit`)}
                    className={cn(
                      'rounded-xl px-4 py-2.5 font-medium',
                      'border border-bg-quaternary',
                      'text-text-secondary hover:bg-bg-tertiary',
                      'flex items-center gap-2 transition-colors',
                    )}
                  >
                    <Pencil className="h-4 w-4" />
                    Edit
                  </button>
                )}

                {app.enabled && app.external_integration?.app_home_url && (
                  <a
                    href={app.external_integration.app_home_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                      'rounded-xl px-4 py-2.5 font-medium',
                      'border border-bg-quaternary',
                      'text-text-secondary hover:bg-bg-tertiary',
                      'flex items-center gap-2 transition-colors',
                    )}
                  >
                    <ExternalLink className="h-4 w-4" />
                    Open App
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Content sections */}
          <div className="space-y-8">
            {/* About */}
            <Section title="About">
              <p className="whitespace-pre-wrap text-text-secondary">{app.description}</p>
            </Section>

            {/* Thumbnails */}
            {app.thumbnail_urls && app.thumbnail_urls.length > 0 && (
              <Section title="Preview">
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {app.thumbnail_urls.map((url, index) => (
                    <div
                      key={index}
                      className="h-32 w-48 flex-shrink-0 overflow-hidden rounded-lg bg-bg-tertiary"
                    >
                      <Image
                        src={url}
                        alt={`Preview ${index + 1}`}
                        width={192}
                        height={128}
                        className="h-full w-full object-cover"
                      />
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Capabilities */}
            {app.capabilities && app.capabilities.length > 0 && (
              <Section title="Capabilities">
                <div className="flex flex-wrap gap-2">
                  {app.capabilities.map((cap) => {
                    const info = CAPABILITY_INFO[cap] || {
                      icon: <Zap className="h-4 w-4" />,
                      label: cap
                        .replace(/_/g, ' ')
                        .replace(/\b\w/g, (l) => l.toUpperCase()),
                      color: 'text-text-tertiary',
                    };
                    return (
                      <span
                        key={cap}
                        className={cn(
                          'inline-flex items-center gap-2 rounded-lg px-3 py-1.5',
                          'bg-bg-tertiary text-sm',
                          info.color,
                        )}
                      >
                        {info.icon}
                        {info.label}
                      </span>
                    );
                  })}
                </div>
              </Section>
            )}

            {/* Chat prompt */}
            {app.chat_prompt && (
              <Section title="Chat Personality">
                <div className="rounded-lg bg-bg-tertiary p-4">
                  <p className="whitespace-pre-wrap text-sm text-text-secondary">
                    {app.chat_prompt}
                  </p>
                </div>
              </Section>
            )}

            {/* Memory prompt */}
            {app.memory_prompt && (
              <Section title="Summary Prompt">
                <div className="rounded-lg bg-bg-tertiary p-4">
                  <p className="whitespace-pre-wrap text-sm text-text-secondary">
                    {app.memory_prompt}
                  </p>
                </div>
              </Section>
            )}

            {/* External integration info */}
            {app.external_integration && (
              <Section title="Integration">
                <div className="space-y-3">
                  {app.external_integration.triggers_on && (
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text-tertiary">Triggers on:</span>
                      <span className="text-sm text-text-secondary">
                        {app.external_integration.triggers_on === 'memory_creation'
                          ? 'Conversation Creation'
                          : app.external_integration.triggers_on}
                      </span>
                    </div>
                  )}
                  {app.external_integration.auth_steps &&
                    app.external_integration.auth_steps.length > 0 && (
                      <div>
                        <p className="mb-2 text-sm text-text-tertiary">Setup Steps:</p>
                        <div className="space-y-2">
                          {app.external_integration.auth_steps.map((step, index) => (
                            <a
                              key={index}
                              href={user ? urlWithUidParam(step.url, user.uid) : step.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={cn(
                                'flex items-center gap-2 rounded-lg px-4 py-2',
                                'bg-bg-tertiary text-text-secondary',
                                'transition-colors hover:bg-bg-quaternary',
                              )}
                            >
                              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/20 text-sm text-text-primary">
                                {index + 1}
                              </span>
                              {step.name}
                              <ExternalLink className="ml-auto h-4 w-4" />
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                </div>
              </Section>
            )}

            {/* Reviews */}
            {app.reviews && app.reviews.length > 0 && (
              <Section title={`Reviews (${app.reviews.length})`}>
                <div className="space-y-4">
                  {app.reviews.slice(0, 5).map((review, index) => (
                    <div
                      key={index}
                      className="border-b border-bg-tertiary pb-4 last:border-0"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <div className="flex items-center gap-1">
                          {[...Array(5)].map((_, i) => (
                            <Star
                              key={i}
                              className={cn(
                                'h-4 w-4',
                                i < review.score
                                  ? 'fill-yellow-400 text-yellow-400'
                                  : 'text-text-quaternary',
                              )}
                            />
                          ))}
                        </div>
                        <span className="text-sm text-text-tertiary">
                          {review.username || 'Anonymous'}
                        </span>
                      </div>
                      {review.review && (
                        <p className="text-sm text-text-secondary">{review.review}</p>
                      )}
                      {review.response && (
                        <div className="mt-2 border-l-2 border-white/30 pl-4">
                          <p className="mb-1 text-xs text-text-tertiary">
                            Developer response:
                          </p>
                          <p className="text-sm text-text-secondary">{review.response}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Pricing */}
            {app.is_paid && app.price !== undefined && (
              <Section title="Pricing">
                <div className="rounded-lg bg-bg-tertiary p-4">
                  <p className="text-lg font-medium text-text-primary">
                    ${(app.price / 100).toFixed(2)}
                    {app.payment_plan === 'monthly' && '/month'}
                  </p>
                  {app.is_user_paid && (
                    <p className="mt-1 flex items-center gap-1 text-sm text-green-400">
                      <Check className="h-4 w-4" />
                      Subscribed
                    </p>
                  )}
                </div>
              </Section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-text-primary">{title}</h2>
      {children}
    </section>
  );
}
