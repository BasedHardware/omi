'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  Smartphone,
  Monitor,
  Globe,
  Watch,
  ArrowRight,
  CheckCircle2,
  Cpu,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

export function DownloadContent() {
  const t = useTranslations('download');
  const heroRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);
  const featRef = useRef<HTMLDivElement>(null);

  const platforms = [
    { id: 'ios', name: t('ios'), icon: Smartphone, description: t('iosDesc'), detail: t('iosDetail'), cta: t('iosCta'), href: '#', featured: true },
    { id: 'android', name: t('android'), icon: Smartphone, description: t('androidDesc'), detail: t('androidDetail'), cta: t('androidCta'), href: '#', featured: true },
    { id: 'mac', name: t('mac'), icon: Monitor, description: t('macDesc'), detail: t('macDetail'), cta: t('macCta'), href: '#', featured: true },
    { id: 'web', name: t('web'), icon: Globe, description: t('webDesc'), detail: t('webDetail'), cta: t('webCta'), href: '#', featured: false },
    { id: 'watch', name: t('watch'), icon: Watch, description: t('watchDesc'), detail: t('watchDetail'), cta: t('watchCta'), href: '#', featured: false },
  ];

  const features = [t('feat1'), t('feat2'), t('feat3'), t('feat4'), t('feat5'), t('feat6')];

  useEffect(() => {
    const ctx = gsap.context(() => {
      const heroEls = heroRef.current?.querySelectorAll('.hero-anim');
      if (heroEls) {
        gsap.fromTo(heroEls, { opacity: 0, y: 30 }, {
          opacity: 1, y: 0, duration: 0.8, stagger: 0.1, ease: 'power3.out',
        });
      }

      const cards = cardsRef.current?.querySelectorAll('.platform-card');
      if (cards) {
        gsap.fromTo(cards, { opacity: 0, y: 40, scale: 0.95 }, {
          opacity: 1, y: 0, scale: 1, duration: 0.7, stagger: 0.1, ease: 'power3.out',
          scrollTrigger: { trigger: cardsRef.current, start: 'top 85%' },
        });
      }

      const featItems = featRef.current?.querySelectorAll('.feat-check');
      if (featItems) {
        gsap.fromTo(featItems, { opacity: 0, x: -15 }, {
          opacity: 1, x: 0, duration: 0.4, stagger: 0.08, ease: 'power2.out',
          scrollTrigger: { trigger: featRef.current, start: 'top 80%' },
        });
      }
    });
    return () => ctx.revert();
  }, []);

  return (
    <>
      <Navbar />
      <main className="pt-16 min-h-screen">
        {/* Hero */}
        <section className="pt-20 md:pt-28 pb-16 px-6">
          <div ref={heroRef} className="mx-auto max-w-4xl text-center">
            <h1 className="hero-anim font-display font-bold text-4xl md:text-5xl lg:text-6xl mb-5">
              {t('heroTitle').split(brand.name).map((part, i, arr) => (
                <span key={i}>
                  {part}
                  {i < arr.length - 1 && <span className="text-brand">{brand.name}</span>}
                </span>
              ))}
            </h1>
            <p className="hero-anim text-text-tertiary text-lg max-w-xl mx-auto">
              {t('heroDescription')}
            </p>
          </div>
        </section>

        {/* Featured platforms */}
        <section className="pb-8 px-6">
          <div ref={cardsRef} className="mx-auto max-w-5xl grid md:grid-cols-3 gap-5">
            {platforms.filter((p) => p.featured).map((platform) => (
              <a key={platform.id} href={platform.href} className="platform-card group relative rounded-2xl border border-white/10 bg-bg-secondary overflow-hidden hover:border-brand/30 transition-all duration-500">
                <div className="h-40 bg-gradient-to-br from-brand/[0.08] via-brand/[0.03] to-transparent flex items-center justify-center relative">
                  <div className="absolute inset-0 bg-gradient-to-t from-bg-secondary to-transparent" />
                  <div className="relative w-16 h-16 rounded-2xl bg-brand/15 border border-brand/25 flex items-center justify-center group-hover:scale-110 transition-transform duration-500">
                    <platform.icon size={28} className="text-brand" />
                  </div>
                </div>
                <div className="p-6">
                  <h3 className="font-display font-bold text-xl mb-1">{platform.name}</h3>
                  <p className="text-text-secondary text-sm mb-1">{platform.description}</p>
                  <p className="text-text-tertiary text-xs mb-5">{platform.detail}</p>
                  <div className="flex items-center gap-2 text-brand text-sm font-medium group-hover:gap-3 transition-all">
                    {platform.cta} <ArrowRight size={14} />
                  </div>
                </div>
              </a>
            ))}
          </div>
        </section>

        {/* Secondary platforms */}
        <section className="pb-20 px-6">
          <div className="mx-auto max-w-5xl grid md:grid-cols-2 gap-4">
            {platforms.filter((p) => !p.featured).map((platform) => (
              <a key={platform.id} href={platform.href} className="platform-card group flex items-center gap-5 rounded-2xl border border-white/[0.06] bg-bg-secondary/50 p-5 hover:border-brand/20 hover:bg-bg-secondary transition-all duration-500">
                <div className="w-12 h-12 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform">
                  <platform.icon size={22} className="text-brand" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-display font-semibold text-base">{platform.name}</h3>
                  <p className="text-text-tertiary text-xs">{platform.description} — {platform.detail}</p>
                </div>
                <div className="text-text-tertiary text-xs font-medium group-hover:text-brand transition-colors flex-shrink-0 hidden sm:block">
                  {platform.cta}
                </div>
              </a>
            ))}
          </div>
        </section>

        {/* One account section */}
        <section className="py-24 md:py-32 px-6 border-t border-white/5">
          <div className="mx-auto max-w-5xl grid lg:grid-cols-2 gap-16 items-center">
            {/* Device constellation */}
            <div className="relative aspect-square max-w-md mx-auto w-full">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 rounded-full bg-brand/[0.04] blur-[80px]" />
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-20 h-20 rounded-full bg-gradient-to-b from-[#2a2a2a] to-[#1a1a1a] border border-white/10 flex items-center justify-center shadow-lg">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand/30 to-brand/10 border border-brand/20" />
              </div>
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 rounded-full border border-white/[0.04]" />
              {[
                { icon: Smartphone, label: 'iOS', angle: 0 },
                { icon: Smartphone, label: 'Android', angle: 72 },
                { icon: Monitor, label: 'Mac', angle: 144 },
                { icon: Globe, label: 'Web', angle: 216 },
                { icon: Watch, label: 'Watch', angle: 288 },
              ].map((device) => {
                const rad = (device.angle * Math.PI) / 180;
                const x = Math.cos(rad) * 128;
                const y = Math.sin(rad) * 128;
                return (
                  <div key={device.label} className="absolute top-1/2 left-1/2 flex flex-col items-center gap-1.5" style={{ transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))` }}>
                    <div className="w-10 h-10 rounded-xl bg-bg-secondary border border-white/10 flex items-center justify-center">
                      <device.icon size={16} className="text-brand" />
                    </div>
                    <span className="text-[10px] text-text-tertiary">{device.label}</span>
                  </div>
                );
              })}
            </div>

            {/* Features */}
            <div ref={featRef}>
              <h2 className="font-display font-bold text-3xl md:text-4xl mb-4">{t('oneAccountTitle')}</h2>
              <p className="text-text-tertiary text-lg leading-relaxed mb-8">{t('oneAccountDescription')}</p>
              <div className="space-y-4">
                {features.map((feat) => (
                  <div key={feat} className="feat-check flex items-center gap-3">
                    <CheckCircle2 size={18} className="text-brand flex-shrink-0" />
                    <span className="text-text-secondary text-sm">{feat}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* System requirements */}
        <section className="py-20 px-6 border-t border-white/5">
          <div className="mx-auto max-w-3xl">
            <h2 className="font-display font-bold text-2xl text-center mb-12">{t('sysReqTitle')}</h2>
            <div className="grid sm:grid-cols-2 gap-4">
              {[
                { platform: 'iOS', req: 'iPhone / iPad, iOS 15+' },
                { platform: 'Android', req: 'Android 7.0+, 2GB RAM' },
                { platform: 'macOS', req: 'macOS 13 Ventura+' },
                { platform: 'Web', req: 'Chrome 90+, Safari 15+, Firefox 90+' },
                { platform: 'Apple Watch', req: 'watchOS 9+, Series 5+' },
                { platform: `${brand.name} Pendant`, req: 'Bluetooth 5.1' },
              ].map((item) => (
                <div key={item.platform} className="rounded-xl border border-white/[0.06] bg-bg-secondary/50 p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <Cpu size={13} className="text-brand" />
                    <span className="font-display font-semibold text-sm">{item.platform}</span>
                  </div>
                  <p className="text-text-tertiary text-xs">{item.req}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="py-20 px-6 text-center border-t border-white/5">
          <h2 className="font-display font-bold text-3xl md:text-4xl mb-4">{t('readyTitle')}</h2>
          <p className="text-text-tertiary text-lg max-w-md mx-auto mb-10">{t('readyDescription')}</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a href="#" className="flex items-center gap-2 bg-brand hover:bg-brand-dark text-white font-medium text-sm px-8 py-4 rounded-full transition-all hover:shadow-lg hover:shadow-brand/20">
              {t('downloadNooto')} <ArrowRight size={16} />
            </a>
            <a href="#" className="text-text-secondary hover:text-white text-sm font-medium border border-white/10 px-8 py-4 rounded-full hover:border-white/20 transition-all">
              {t('tryInBrowser')}
            </a>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
