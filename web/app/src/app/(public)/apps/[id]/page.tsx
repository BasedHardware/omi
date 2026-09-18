'use client';

import { useEffect, useState } from 'react';
import { useParams } from '@tschk/moonshine-next/navigation';
import {
  findAppById,
  getAppsV2,
  transformToPlugin,
  type V2AppData,
} from '@/lib/api/public';
import { CompactPluginCard } from '@/components/marketplace/plugin-card/CompactPluginCard';
import { CategoryBreadcrumb } from '@/components/marketplace/CategoryBreadcrumb';
import { BreadcrumbJsonLd, SoftwareAppJsonLd } from '@/components/seo/JsonLd';
import { Calendar, User, FolderOpen, Puzzle, ArrowRight, DollarSign } from 'lucide-react';
import Image from '@tschk/moonshine-next/image';
import Link from '@tschk/moonshine-next/link';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

/**
 * moonshine emits its own `<head>` and has no per-route metadata hook — its own
 * adopt check rejects `generateMetadata` with "Moonshine emits its own <head>",
 * and both `renderPage` and `renderSpaShell` in `@tschk/moonshine-react` build
 * a head of module preloads only. These routes also compile to `spa` mode, so
 * nothing about them is server-rendered. Writing the tags from the client after
 * the app loads is therefore the whole of what this runtime allows; crawlers
 * that execute JS pick them up, ones that do not see only the shell.
 */
export function applyAppDetailMetadata(app: {
  id: string;
  name: string;
  description: string;
  category: string;
  image?: string;
}): () => void {
  if (typeof document === 'undefined') return () => {};
  const previousTitle = document.title;
  const restorers: Array<() => void> = [];
  const title = `${app.name} - ${formatCategoryName(app.category)} App`;
  const description = `${app.description} Available on Omi, the AI-powered wearable platform.`;
  document.title = title;
  const url = `${window.location.origin}/apps/${app.id}`;

  const setMeta = (selector: string, attr: string, key: string, content: string) => {
    let el = document.head.querySelector<HTMLMetaElement>(selector);
    const existed = Boolean(el);
    const previousContent = el?.getAttribute('content');
    if (!el) {
      el = document.createElement('meta');
      el.setAttribute(attr, key);
      document.head.appendChild(el);
    }
    el.setAttribute('content', content);
    restorers.push(() => {
      if (!existed) {
        el?.remove();
      } else if (previousContent == null) {
        el?.removeAttribute('content');
      } else {
        el?.setAttribute('content', previousContent);
      }
    });
  };

  setMeta('meta[name="description"]', 'name', 'description', description);
  setMeta('meta[property="og:title"]', 'property', 'og:title', title);
  setMeta(
    'meta[property="og:description"]',
    'property',
    'og:description',
    app.description,
  );
  setMeta('meta[property="og:url"]', 'property', 'og:url', url);
  if (app.image) {
    setMeta('meta[property="og:image"]', 'property', 'og:image', app.image);
  }
  setMeta('meta[name="twitter:card"]', 'name', 'twitter:card', 'summary_large_image');
  setMeta('meta[name="twitter:title"]', 'name', 'twitter:title', title);
  setMeta(
    'meta[name="twitter:description"]',
    'name',
    'twitter:description',
    app.description,
  );
  if (app.image) {
    setMeta('meta[name="twitter:image"]', 'name', 'twitter:image', app.image);
  }

  let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  const canonicalExisted = Boolean(canonical);
  const previousCanonical = canonical?.getAttribute('href');
  if (!canonical) {
    canonical = document.createElement('link');
    canonical.rel = 'canonical';
    document.head.appendChild(canonical);
  }
  canonical.href = url;
  restorers.push(() => {
    if (!canonicalExisted) {
      canonical?.remove();
    } else if (previousCanonical == null) {
      canonical?.removeAttribute('href');
    } else {
      canonical?.setAttribute('href', previousCanonical);
    }
  });

  return () => {
    document.title = previousTitle;
    for (const restore of restorers.reverse()) restore();
  };
}

// Helper function to format category name
const formatCategoryName = (category: string): string => {
  return category
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

// Helper function to format date
function formatDate(dateString: string | null | undefined): string | null {
  if (!dateString) return null;
  const date = new Date(dateString);
  // Check for invalid date or Unix epoch (which indicates null/invalid data)
  if (isNaN(date.getTime()) || date.getTime() === 0) return null;
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export default function PluginDetailPage() {
  const { id = '' } = useParams();
  const [plugin, setPlugin] = useState<Awaited<ReturnType<typeof findAppById>>>(null);
  const [relatedApps, setRelatedApps] = useState<ReturnType<typeof transformToPlugin>[]>(
    [],
  );
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    let restoreMetadata: (() => void) | undefined;
    // Get v2 apps to find related ones
    Promise.all([findAppById(id), getAppsV2(true)]).then(([app, response]) => {
      if (!active) return;
      setPlugin(app);
      if (app) {
        restoreMetadata = applyAppDetailMetadata(app);
        // Flatten all apps from groups
        const rawPlugins: V2AppData[] = response.groups.flatMap((group) => group.data);
        // Get related apps based on category
        setRelatedApps(
          rawPlugins
            .map(transformToPlugin)
            .filter(
              (candidate) =>
                candidate.category === app.category && candidate.id !== app.id,
            )
            .slice(0, 6),
        );
      }
      setLoaded(true);
    });
    return () => {
      active = false;
      restoreMetadata?.();
    };
  }, [id]);

  if (!loaded) return <div className="min-h-screen bg-[#0B0F17]" />;
  // An unknown id used to be a 404. moonshine's `notFound()` throws, and a
  // client route has no boundary to catch it, so the reachable equivalent is a
  // rendered not-found state with a way back to the marketplace.
  if (!plugin) {
    return (
      <div
        data-testid="app-not-found"
        className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#0B0F17] px-6 text-center"
      >
        <h1 className="text-3xl font-bold text-white">App not found</h1>
        <p className="text-gray-400">We couldn&apos;t find an app with the id “{id}”.</p>
        <Link
          href="/apps"
          className="rounded-xl bg-[#6C8EEF] px-6 py-3 text-base font-medium text-white transition-all hover:bg-[#5A7DE8]"
        >
          Browse the App Store
        </Link>
      </div>
    );
  }

  const categoryName = formatCategoryName(plugin.category);
  const capabilities = plugin.capabilities || [];

  return (
    <div className="relative flex min-h-screen flex-col bg-[#0B0F17]">
      <BreadcrumbJsonLd
        items={[
          { name: 'Apps', url: '/apps' },
          { name: categoryName, url: `/apps/category/${plugin.category}` },
          { name: plugin.name, url: `/apps/${plugin.id}` },
        ]}
      />
      <SoftwareAppJsonLd
        name={plugin.name}
        description={plugin.description}
        image={plugin.image}
        author={plugin.author}
        category={categoryName}
        ratingValue={plugin.rating_avg}
        ratingCount={plugin.rating_count}
        price={plugin.is_paid ? plugin.price : 0}
        url={`/apps/${plugin.id}`}
      />
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-12 z-40 bg-[#0B0F17]">
        <div className="border-b border-white/5 shadow-lg">
          <div className="container mx-auto px-6 py-4">
            <CategoryBreadcrumb category={plugin.category} />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-0 mt-[7rem] flex-grow">
        <div className="container mx-auto px-6 pt-8">
          {/* Hero Section */}
          <section className="grid grid-cols-1 gap-12 lg:grid-cols-5">
            {/* Image Column */}
            <div className="lg:col-span-2">
              <div className="relative aspect-square overflow-hidden rounded-2xl bg-[#1A1F2E]">
                <Image
                  src={plugin.image || '/logo.png'}
                  alt={plugin.name}
                  className="h-full w-full object-cover transition-transform duration-300 hover:scale-105"
                  width={500}
                  height={500}
                />
              </div>
            </div>

            {/* Content Column */}
            <div className="lg:col-span-3">
              <div className="flex h-full flex-col justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <h1 className="text-4xl font-bold text-white">{plugin.name}</h1>
                    {plugin.is_paid && (
                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500/15 px-3 py-1.5 text-sm font-semibold text-amber-400">
                        <DollarSign className="h-4 w-4" />
                        {plugin.price?.toFixed(2)}
                        {plugin.payment_plan === 'monthly_recurring' ? '/mo' : ''}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-xl text-gray-400">by {plugin.author}</p>

                  {/* Stats Section */}
                  <div className="mt-8 flex items-center gap-4">
                    <div className="flex items-center">
                      <span className="text-3xl font-bold text-yellow-400">
                        {plugin.rating_avg?.toFixed(1)}
                      </span>
                      <div className="ml-2 flex flex-col">
                        <span className="text-yellow-400">★</span>
                        <span className="text-sm text-gray-400">
                          ({plugin.rating_count} reviews)
                        </span>
                      </div>
                    </div>
                    <div className="h-8 w-px bg-white/5" />
                    <div className="flex items-center">
                      <span className="text-3xl font-bold text-[#6C8EEF]">
                        {plugin.installs.toLocaleString()}
                      </span>
                      <span className="ml-2 text-sm text-gray-400">downloads</span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="mt-8">
                    <Link
                      href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group inline-flex items-center justify-center rounded-xl bg-[#6C8EEF] px-6 py-3 text-base font-medium text-white transition-all hover:bg-[#5A7DE8]"
                    >
                      <span className="flex items-center">
                        Try it now
                        <ArrowRight className="ml-2 h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
                      </span>
                    </Link>
                    <div className="mt-4 flex items-center gap-4">
                      <a
                        href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="transition-transform duration-300 hover:scale-105"
                      >
                        <Image
                          src="/app-store-badge.svg"
                          alt="Download on the App Store"
                          className="h-10"
                          width={120}
                          height={40}
                        />
                      </a>
                      <a
                        href="https://play.google.com/store/apps/details?id=com.friend.ios"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="transition-transform duration-300 hover:scale-105"
                      >
                        <Image
                          src="/google-play-badge.png"
                          alt="Get it on Google Play"
                          className="h-[60px] w-auto"
                          width={646}
                          height={250}
                        />
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* About Section */}
          <section className="mt-16">
            <h2 className="text-2xl font-bold text-white">About</h2>
            <div className="mt-4">
              <p className="text-lg leading-relaxed text-gray-300">
                {plugin.description}
              </p>
            </div>
          </section>

          {/* Additional Details Section */}
          <section className="mt-16">
            <h2 className="mb-6 text-2xl font-bold text-white">Additional Details</h2>
            <div className="grid gap-8 sm:grid-cols-2">
              {plugin.is_paid && (
                <div>
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-5 w-5 text-amber-400" />
                    <div className="text-sm font-medium text-gray-400">Pricing</div>
                  </div>
                  <div className="mt-1 pl-7">
                    <span className="text-base font-semibold text-amber-400">
                      ${plugin.price?.toFixed(2)}
                      {plugin.payment_plan === 'monthly_recurring' ? '/month' : ''}
                    </span>
                    <span className="ml-2 text-sm text-gray-400">
                      {plugin.payment_plan === 'monthly_recurring'
                        ? '(Monthly subscription)'
                        : plugin.payment_plan === 'one_time'
                          ? '(One-time purchase)'
                          : '(Paid)'}
                    </span>
                  </div>
                </div>
              )}
              {formatDate(plugin.created_at) && (
                <div>
                  <div className="flex items-center gap-2">
                    <Calendar className="h-5 w-5 text-gray-400" />
                    <div className="text-sm font-medium text-gray-400">Created</div>
                  </div>
                  <div className="mt-1 pl-7 text-base text-white">
                    {formatDate(plugin.created_at)}
                  </div>
                </div>
              )}
              <div>
                <div className="flex items-center gap-2">
                  <User className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Creator</div>
                </div>
                <div className="mt-1 pl-7 text-base text-white">{plugin.author}</div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Category</div>
                </div>
                <div className="mt-1 pl-7 text-base text-white">{categoryName}</div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <Puzzle className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Capabilities</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 pl-7">
                  {capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="rounded-full bg-[#1A1F2E] px-3 py-1 text-sm text-white"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Related Apps Section */}
          {relatedApps.length > 0 && (
            <section className="mt-16 pb-12">
              <h2 className="mb-8 text-2xl font-bold text-white">
                More {categoryName} Apps
              </h2>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {relatedApps.map((app, index) => (
                  <CompactPluginCard key={app.id} plugin={app} index={index + 1} />
                ))}
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

registerMoonshineRoute('/apps/:id', PluginDetailPage, 'public');
