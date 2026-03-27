'use client';

import { useRef, useEffect, useState, useMemo } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  Search, Star, Download, ArrowRight, X, Plus,
  Briefcase, MessageSquare, GraduationCap, Brain, Wrench, Heart, Globe, Gamepad2,
  type LucideIcon,
} from 'lucide-react';
import { Link } from '@/i18n/navigation';
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { brand } from '@/lib/config';
import {
  mockApps,
  categories,
  getFeaturedApps,
  getPopularApps,
  getAppsByCategory,
  formatInstalls,
  type App,
  type CategoryMeta,
} from '@/lib/apps-data';

gsap.registerPlugin(ScrollTrigger);

const iconMap: Record<string, LucideIcon> = {
  Briefcase, MessageSquare, GraduationCap, Brain, Wrench, Heart, Globe, Gamepad2,
};

function CategoryIcon({ category, size = 16, className = '' }: { category: string; size?: number; className?: string }) {
  const cat = categories.find((c) => c.slug === category);
  const Icon = cat ? iconMap[cat.iconName] || Briefcase : Briefcase;
  return <Icon size={size} className={className || cat?.color || 'text-brand'} />;
}

export function AppsContent() {
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const heroRef = useRef<HTMLElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const featured = useMemo(() => getFeaturedApps(), []);
  const popular = useMemo(() => getPopularApps(), []);

  const filtered = useMemo(() => {
    let apps = activeCategory ? getAppsByCategory(activeCategory) : mockApps;
    if (query.trim()) {
      const q = query.toLowerCase();
      apps = apps.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q) ||
          a.author.toLowerCase().includes(q),
      );
    }
    return [...apps].sort((a, b) => b.installs - a.installs);
  }, [query, activeCategory]);

  const isFiltering = query.trim() || activeCategory;

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Hero entrance
      const heroEls = heroRef.current?.querySelectorAll('.hero-anim');
      if (heroEls) {
        gsap.fromTo(heroEls, { opacity: 0, y: 30 }, {
          opacity: 1, y: 0, duration: 0.8, stagger: 0.12, ease: 'power3.out',
        });
      }
    });
    return () => ctx.revert();
  }, []);

  // Animate cards when grid changes
  useEffect(() => {
    if (!gridRef.current) return;
    const cards = gridRef.current.querySelectorAll('.app-card');
    gsap.fromTo(cards, { opacity: 0, y: 20, scale: 0.97 }, {
      opacity: 1, y: 0, scale: 1, duration: 0.4, stagger: 0.04, ease: 'power2.out',
    });
  }, [filtered, activeCategory]);

  return (
    <>
      <Navbar />
      <main className="pt-16 min-h-screen">
        {/* Hero */}
        <section ref={heroRef} className="pt-16 pb-8 px-6">
          <div className="mx-auto max-w-6xl">
            <h1 className="hero-anim font-display font-bold text-4xl md:text-5xl lg:text-6xl mb-4">
              {brand.name} <span className="text-brand">App Store</span>
            </h1>
            <p className="hero-anim text-text-tertiary text-lg max-w-xl mb-10">
              Explore apps that turn your conversations into actions across your favorite tools.
            </p>

            {/* Search */}
            <div className="hero-anim relative max-w-xl mb-8">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search apps..."
                className="w-full bg-bg-secondary border border-white/10 rounded-xl pl-11 pr-10 py-3 text-sm text-white placeholder:text-text-tertiary focus:outline-none focus:border-brand/40 transition-colors"
              />
              {query && (
                <button onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-white">
                  <X size={16} />
                </button>
              )}
            </div>

            {/* Category pills */}
            <div className="hero-anim flex gap-2 overflow-x-auto no-scrollbar pb-2">
              <button
                onClick={() => setActiveCategory(null)}
                className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-all ${
                  !activeCategory ? 'bg-brand text-white' : 'bg-white/[0.06] text-text-tertiary hover:text-white hover:bg-white/10'
                }`}
              >
                All
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.slug}
                  onClick={() => setActiveCategory(activeCategory === cat.slug ? null : cat.slug)}
                  className={`flex-shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-all ${
                    activeCategory === cat.slug
                      ? 'bg-brand text-white'
                      : 'bg-white/[0.06] text-text-tertiary hover:text-white hover:bg-white/10'
                  }`}
                >
                  <CategoryIcon category={cat.slug} size={14} /> {cat.name}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Results or default view */}
        <section className="pb-24 px-6">
          <div className="mx-auto max-w-6xl">
            {isFiltering ? (
              <>
                <p className="text-text-tertiary text-sm mb-6">{filtered.length} apps found</p>
                <div ref={gridRef} className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {filtered.map((app) => (
                    <AppCard key={app.id} app={app} />
                  ))}
                </div>
                {filtered.length === 0 && (
                  <div className="text-center py-20">
                    <p className="text-text-tertiary text-sm">No apps match your search.</p>
                  </div>
                )}
              </>
            ) : (
              <>
                {/* Featured */}
                <div className="mb-16">
                  <SectionHeader title="Featured" />
                  <div ref={gridRef} className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {featured.map((app) => (
                      <FeaturedCard key={app.id} app={app} />
                    ))}
                  </div>
                </div>

                {/* Build your own */}
                <div className="mb-16 rounded-2xl border border-brand/20 bg-brand/[0.04] p-8 md:p-10 flex flex-col md:flex-row items-center justify-between gap-6">
                  <div>
                    <h3 className="font-display font-bold text-xl mb-2">Build your own app</h3>
                    <p className="text-text-tertiary text-sm max-w-md">
                      Create apps with prompts or webhooks. No server required for prompt-based apps.
                    </p>
                  </div>
                  <Link
                    href="/docs"
                    className="flex items-center gap-2 bg-brand hover:bg-brand-dark text-white text-sm font-medium px-6 py-3 rounded-full transition-colors flex-shrink-0"
                  >
                    <Plus size={16} /> Start building
                  </Link>
                </div>

                {/* Most Popular */}
                <div className="mb-16">
                  <SectionHeader title="Most Popular" />
                  <div className="space-y-2">
                    {popular.map((app, i) => (
                      <CompactCard key={app.id} app={app} rank={i + 1} />
                    ))}
                  </div>
                </div>

                {/* Category sections */}
                {categories.map((cat) => {
                  const apps = getAppsByCategory(cat.slug);
                  if (apps.length === 0) return null;
                  return (
                    <div key={cat.slug} className="mb-16">
                      <SectionHeader title={cat.name} count={apps.length} icon={<CategoryIcon category={cat.slug} size={20} />} />
                      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {apps.slice(0, 6).map((app) => (
                          <AppCard key={app.id} app={app} />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

// ─── Components ──────────────────────────────────────────────────────────────

function SectionHeader({ title, count, icon }: { title: string; count?: number; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <h2 className="font-display font-bold text-xl md:text-2xl flex items-center gap-2">
        {icon}
        {title}
        {count !== undefined && <span className="text-text-tertiary text-sm font-normal ml-1">({count})</span>}
      </h2>
    </div>
  );
}

function FeaturedCard({ app }: { app: App }) {
  return (
    <Link href={`/apps/${app.id}`} className="app-card group block rounded-2xl border border-white/10 bg-bg-secondary overflow-hidden hover:border-brand/30 transition-all duration-500">
      {/* Image placeholder */}
      <div className="aspect-[16/9] bg-gradient-to-br from-brand/10 via-brand/5 to-transparent flex items-center justify-center">
        <div className="w-16 h-16 rounded-2xl bg-brand/20 border border-brand/30 flex items-center justify-center group-hover:scale-110 transition-transform duration-500">
          <CategoryIcon category={app.category} size={24} />
        </div>
      </div>
      <div className="p-5">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="font-display font-semibold text-base">{app.name}</h3>
          {isNewApp(app) && <NewBadge />}
        </div>
        <p className="text-text-tertiary text-xs mb-1">by {app.author}</p>
        <p className="text-text-secondary text-sm leading-relaxed line-clamp-2 mb-3">{app.description}</p>
        <div className="flex items-center gap-4 text-xs text-text-tertiary">
          <span className="flex items-center gap-1"><Star size={12} className="text-yellow-500 fill-yellow-500" /> {app.ratingAvg}</span>
          <span className="flex items-center gap-1"><Download size={12} /> {formatInstalls(app.installs)}</span>
        </div>
      </div>
    </Link>
  );
}

function AppCard({ app }: { app: App }) {
  return (
    <Link href={`/apps/${app.id}`} className="app-card group flex gap-4 rounded-xl border border-white/[0.06] bg-bg-secondary/50 p-4 hover:border-brand/20 hover:bg-bg-secondary transition-all duration-300">
      <div className="w-12 h-12 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform">
        <CategoryIcon category={app.category} size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h3 className="font-display font-semibold text-sm truncate">{app.name}</h3>
          {isNewApp(app) && <NewBadge />}
        </div>
        <p className="text-text-tertiary text-xs mb-1">by {app.author}</p>
        <p className="text-text-tertiary text-xs line-clamp-1">{app.description}</p>
        <div className="flex items-center gap-3 mt-2 text-[11px] text-text-tertiary">
          <span className="flex items-center gap-1"><Star size={10} className="text-yellow-500 fill-yellow-500" /> {app.ratingAvg}</span>
          <span className="flex items-center gap-1"><Download size={10} /> {formatInstalls(app.installs)}</span>
        </div>
      </div>
    </Link>
  );
}

function CompactCard({ app, rank }: { app: App; rank: number }) {
  return (
    <Link href={`/apps/${app.id}`} className="app-card group flex items-center gap-4 rounded-xl border border-white/[0.04] hover:border-white/10 hover:bg-bg-secondary/50 p-3 transition-all duration-300">
      <span className="font-display font-bold text-lg text-white/10 w-8 text-center flex-shrink-0">{rank}</span>
      <div className="w-10 h-10 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center flex-shrink-0">
        <CategoryIcon category={app.category} size={15} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-display font-semibold text-sm truncate">{app.name}</h3>
          {isNewApp(app) && <NewBadge />}
        </div>
        <p className="text-text-tertiary text-xs truncate">{app.description}</p>
      </div>
      <div className="hidden sm:flex items-center gap-4 text-xs text-text-tertiary flex-shrink-0">
        <span className="flex items-center gap-1"><Star size={11} className="text-yellow-500 fill-yellow-500" /> {app.ratingAvg}</span>
        <span className="flex items-center gap-1"><Download size={11} /> {formatInstalls(app.installs)}</span>
      </div>
      <ArrowRight size={14} className="text-text-tertiary group-hover:text-brand transition-colors flex-shrink-0" />
    </Link>
  );
}

function NewBadge() {
  return (
    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider uppercase bg-brand/15 text-brand flex-shrink-0">
      New
    </span>
  );
}

function isNewApp(app: App): boolean {
  const created = new Date(app.createdAt);
  const now = new Date();
  const diff = now.getTime() - created.getTime();
  return diff < 30 * 24 * 60 * 60 * 1000; // 30 days
}
