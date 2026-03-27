'use client';

import {
  Star, Download, Calendar, User, Folder, ArrowLeft,
  Briefcase, MessageSquare, GraduationCap, Brain, Wrench, Heart, Globe, Gamepad2,
  type LucideIcon,
} from 'lucide-react';
import { Link } from '@/i18n/navigation';
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { getAppById, getAppsByCategory, getCategoryBySlug, formatInstalls, categories } from '@/lib/apps-data';

const iconMap: Record<string, LucideIcon> = {
  Briefcase, MessageSquare, GraduationCap, Brain, Wrench, Heart, Globe, Gamepad2,
};

function getCatIcon(category: string, size = 16) {
  const cat = categories.find((c) => c.slug === category);
  const Icon = cat ? iconMap[cat.iconName] || Briefcase : Briefcase;
  return <Icon size={size} className={cat?.color || 'text-brand'} />;
}

export function AppDetailContent({ appId }: { appId: string }) {
  const app = getAppById(appId);

  if (!app) {
    return (
      <>
        <Navbar />
        <main className="pt-16 min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h1 className="font-display font-bold text-2xl mb-2">App not found</h1>
            <Link href="/apps" className="text-brand text-sm hover:underline">Back to App Store</Link>
          </div>
        </main>
        <Footer />
      </>
    );
  }

  const category = getCategoryBySlug(app.category);
  const related = getAppsByCategory(app.category).filter((a) => a.id !== app.id).slice(0, 3);

  return (
    <>
      <Navbar />
      <main className="pt-16 min-h-screen">
        <div className="mx-auto max-w-5xl px-6 py-12">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-sm text-text-tertiary mb-8">
            <Link href="/apps" className="hover:text-white transition-colors flex items-center gap-1">
              <ArrowLeft size={14} /> App Store
            </Link>
            <span>/</span>
            <span className="text-text-secondary">{app.name}</span>
          </div>

          {/* Hero */}
          <div className="grid md:grid-cols-[1fr_1.5fr] gap-12 mb-16">
            <div className="aspect-square rounded-2xl bg-gradient-to-br from-brand/10 via-brand/5 to-transparent border border-white/10 flex items-center justify-center">
              <div className="w-24 h-24 rounded-3xl bg-brand/20 border border-brand/30 flex items-center justify-center">
                {getCatIcon(app.category, 36)}
              </div>
            </div>

            <div>
              <h1 className="font-display font-bold text-3xl md:text-4xl mb-2">{app.name}</h1>
              <p className="text-text-tertiary text-sm mb-4">by {app.author}</p>

              <div className="flex items-center gap-4 mb-6">
                <div className="flex items-center gap-1">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Star key={i} size={18} className={i < Math.round(app.ratingAvg) ? 'text-yellow-500 fill-yellow-500' : 'text-white/10'} />
                  ))}
                  <span className="text-sm text-text-secondary ml-2">{app.ratingAvg}</span>
                  <span className="text-xs text-text-tertiary">({app.ratingCount})</span>
                </div>
                <div className="flex items-center gap-1 text-sm text-text-tertiary">
                  <Download size={14} /> {formatInstalls(app.installs)}
                </div>
              </div>

              <p className="text-text-secondary leading-relaxed mb-8">{app.description}</p>

              <button className="bg-brand hover:bg-brand-dark text-white font-medium text-sm px-8 py-3.5 rounded-full transition-colors">
                Install App
              </button>
            </div>
          </div>

          {/* Details */}
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-4 mb-16">
            <DetailCard icon={Calendar} label="Created" value={new Date(app.createdAt).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} />
            <DetailCard icon={User} label="Author" value={app.author} />
            <DetailCard icon={Folder} label="Category" value={category?.name || app.category} />
            <DetailCard icon={Star} label="Rating" value={`${app.ratingAvg} (${app.ratingCount} reviews)`} />
          </div>

          {/* Capabilities */}
          <div className="mb-16">
            <h2 className="font-display font-bold text-xl mb-4">Capabilities</h2>
            <div className="flex flex-wrap gap-2">
              {app.capabilities.map((cap) => (
                <span key={cap} className="px-3 py-1.5 rounded-lg bg-white/[0.06] border border-white/[0.06] text-xs text-text-secondary">
                  {cap.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>

          {/* Related */}
          {related.length > 0 && (
            <div>
              <h2 className="font-display font-bold text-xl mb-6">More {category?.name} Apps</h2>
              <div className="grid sm:grid-cols-3 gap-4">
                {related.map((r) => (
                  <Link key={r.id} href={`/apps/${r.id}`} className="group flex gap-3 rounded-xl border border-white/[0.06] bg-bg-secondary/50 p-4 hover:border-brand/20 transition-all">
                    <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center flex-shrink-0">
                      {getCatIcon(r.category, 16)}
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-display font-semibold text-sm truncate">{r.name}</h3>
                      <p className="text-text-tertiary text-xs truncate">{r.description}</p>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}

function DetailCard({ icon: Icon, label, value }: { icon: typeof Calendar; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-bg-secondary/50 p-4">
      <div className="flex items-center gap-2 text-text-tertiary text-xs mb-1">
        <Icon size={13} /> {label}
      </div>
      <div className="font-display font-medium text-sm">{value}</div>
    </div>
  );
}
