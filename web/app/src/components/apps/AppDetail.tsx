'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
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
import { cn } from '@/lib/utils';
import { getApp, enableApp, disableApp } from '@/lib/api';
import type { App } from '@/types/apps';
import { PageHeader } from '@/components/layout/PageHeader';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface AppDetailProps {
  appId: string;
}

// Capability display info
const CAPABILITY_INFO: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  chat: {
    icon: <MessageSquare className="w-4 h-4" />,
    label: 'Chat',
    color: 'text-blue-400',
  },
  persona: {
    icon: <Brain className="w-4 h-4" />,
    label: 'Persona',
    color: 'text-purple-400',
  },
  memories: {
    icon: <Brain className="w-4 h-4" />,
    label: 'Conversations',
    color: 'text-green-400',
  },
  external_integration: {
    icon: <ExternalLink className="w-4 h-4" />,
    label: 'External Integration',
    color: 'text-orange-400',
  },
  proactive_notification: {
    icon: <Zap className="w-4 h-4" />,
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

  // Check if user owns this app
  const isOwner = user && app?.uid === user.uid;

  useEffect(() => {
    async function loadApp() {
      setIsLoading(true);
      setError(null);
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

  const handleShare = async () => {
    if (!app) return;

    const url = `${window.location.origin}/apps/${app.id}`;
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
        <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
      </div>
    );
  }

  if (error || !app) {
    return (
      <div className="text-center py-12">
        <p className="text-text-tertiary">{error || 'App not found'}</p>
        <Link
          href="/apps"
          className="text-purple-primary hover:underline mt-2 inline-block"
        >
          Back to Apps
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Page Header */}
      <PageHeader title="App Details" icon={LayoutGrid} showBackButton />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 py-6">
          {/* App Hero */}
          <div className="flex flex-col sm:flex-row gap-6 mb-8">
        {/* App icon */}
        <div className="flex-shrink-0 w-24 h-24 sm:w-28 sm:h-28 rounded-2xl overflow-hidden bg-bg-tertiary mx-auto sm:mx-0">
          {app.image ? (
            <Image
              src={app.image}
              alt={app.name}
              width={112}
              height={112}
              className="object-cover w-full h-full"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-text-tertiary text-3xl font-medium">
              {app.name.charAt(0)}
            </div>
          )}
        </div>

        {/* App info */}
        <div className="flex-1 text-center sm:text-left">
          <h1 className="text-2xl font-bold text-text-primary flex items-center justify-center sm:justify-start gap-2">
            {app.name}
            {app.private && <Lock className="w-5 h-5 text-text-quaternary" />}
          </h1>
          <p className="text-text-secondary mt-1">{app.author || 'Unknown author'}</p>

          {/* Stats */}
          <div className="flex items-center justify-center sm:justify-start gap-4 mt-3 text-sm text-text-tertiary">
            {app.rating_avg !== undefined && app.rating_avg > 0 && (
              <span className="flex items-center gap-1">
                <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                {app.rating_avg.toFixed(1)}
                {app.rating_count ? ` (${app.rating_count} reviews)` : ''}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Download className="w-4 h-4" />
              {formatInstalls(app.installs)} installs
            </span>
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-center sm:justify-start gap-3 mt-4">
            <button
              onClick={handleToggle}
              disabled={isToggling}
              className={cn(
                'px-6 py-2.5 rounded-xl font-medium',
                'transition-colors flex items-center gap-2',
                app.enabled
                  ? 'bg-red-500/10 text-red-500 hover:bg-red-500/20'
                  : 'bg-purple-primary text-white hover:bg-purple-secondary',
                'disabled:opacity-50'
              )}
            >
              {isToggling ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : app.enabled ? (
                <>Uninstall</>
              ) : (
                <>
                  <Download className="w-5 h-5" />
                  Install
                </>
              )}
            </button>

            <button
              onClick={handleShare}
              className={cn(
                'p-2.5 rounded-xl',
                'border border-bg-quaternary',
                'text-text-secondary hover:bg-bg-tertiary',
                'transition-colors'
              )}
            >
              <Share2 className="w-5 h-5" />
            </button>

            {isOwner && (
              <button
                onClick={() => router.push(`/apps/${app.id}/edit`)}
                className={cn(
                  'px-4 py-2.5 rounded-xl font-medium',
                  'border border-bg-quaternary',
                  'text-text-secondary hover:bg-bg-tertiary',
                  'transition-colors flex items-center gap-2'
                )}
              >
                <Pencil className="w-4 h-4" />
                Edit
              </button>
            )}

            {app.enabled && app.external_integration?.app_home_url && (
              <a
                href={app.external_integration.app_home_url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  'px-4 py-2.5 rounded-xl font-medium',
                  'border border-bg-quaternary',
                  'text-text-secondary hover:bg-bg-tertiary',
                  'transition-colors flex items-center gap-2'
                )}
              >
                <ExternalLink className="w-4 h-4" />
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
          <p className="text-text-secondary whitespace-pre-wrap">{app.description}</p>
        </Section>

        {/* Thumbnails */}
        {app.thumbnail_urls && app.thumbnail_urls.length > 0 && (
          <Section title="Preview">
            <div className="flex gap-3 overflow-x-auto pb-2">
              {app.thumbnail_urls.map((url, index) => (
                <div
                  key={index}
                  className="flex-shrink-0 w-48 h-32 rounded-lg overflow-hidden bg-bg-tertiary"
                >
                  <Image
                    src={url}
                    alt={`Preview ${index + 1}`}
                    width={192}
                    height={128}
                    className="object-cover w-full h-full"
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
              {app.capabilities.map(cap => {
                const info = CAPABILITY_INFO[cap] || {
                  icon: <Zap className="w-4 h-4" />,
                  label: cap.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                  color: 'text-text-tertiary',
                };
                return (
                  <span
                    key={cap}
                    className={cn(
                      'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg',
                      'bg-bg-tertiary text-sm',
                      info.color
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
            <div className="bg-bg-tertiary rounded-lg p-4">
              <p className="text-sm text-text-secondary whitespace-pre-wrap">{app.chat_prompt}</p>
            </div>
          </Section>
        )}

        {/* Memory prompt */}
        {app.memory_prompt && (
          <Section title="Summary Prompt">
            <div className="bg-bg-tertiary rounded-lg p-4">
              <p className="text-sm text-text-secondary whitespace-pre-wrap">{app.memory_prompt}</p>
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
              {app.external_integration.auth_steps && app.external_integration.auth_steps.length > 0 && (
                <div>
                  <p className="text-sm text-text-tertiary mb-2">Setup Steps:</p>
                  <div className="space-y-2">
                    {app.external_integration.auth_steps.map((step, index) => (
                      <a
                        key={index}
                        href={step.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={cn(
                          'flex items-center gap-2 px-4 py-2 rounded-lg',
                          'bg-bg-tertiary text-text-secondary',
                          'hover:bg-bg-quaternary transition-colors'
                        )}
                      >
                        <span className="w-6 h-6 rounded-full bg-purple-primary/20 text-purple-primary text-sm flex items-center justify-center">
                          {index + 1}
                        </span>
                        {step.name}
                        <ExternalLink className="w-4 h-4 ml-auto" />
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
                <div key={index} className="border-b border-bg-tertiary pb-4 last:border-0">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="flex items-center gap-1">
                      {[...Array(5)].map((_, i) => (
                        <Star
                          key={i}
                          className={cn(
                            'w-4 h-4',
                            i < review.score
                              ? 'fill-yellow-400 text-yellow-400'
                              : 'text-text-quaternary'
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
                    <div className="mt-2 pl-4 border-l-2 border-purple-primary/30">
                      <p className="text-xs text-text-tertiary mb-1">Developer response:</p>
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
            <div className="bg-bg-tertiary rounded-lg p-4">
              <p className="text-lg font-medium text-text-primary">
                ${(app.price / 100).toFixed(2)}
                {app.payment_plan === 'monthly' && '/month'}
              </p>
              {app.is_user_paid && (
                <p className="text-sm text-green-400 mt-1 flex items-center gap-1">
                  <Check className="w-4 h-4" />
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
      <h2 className="text-lg font-semibold text-text-primary mb-3">{title}</h2>
      {children}
    </section>
  );
}
