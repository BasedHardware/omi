'use client';

import { useRef, useEffect, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  Mic,
  Brain,
  Zap,
  Search,
  MessageSquare,
  CalendarClock,
  Network,
  Hand,
  ListChecks,
  Smartphone,
  FileText,
  LayoutGrid,
  FolderOpen,
  Share2,
  ChevronDown,
  ArrowRight,
  Star,
  Play,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

// ─── Data ────────────────────────────────────────────────────────────────────

const featureIcons = {
  capture: [Mic, ListChecks, MessageSquare, Mic, Smartphone, Zap],
  recall: [Search, Brain, CalendarClock, Network, Hand, Zap],
  automate: [ListChecks, Smartphone, FileText, LayoutGrid, FolderOpen, Share2],
};

// ─── Component ───────────────────────────────────────────────────────────────

export function ProductContent() {
  const t = useTranslations('product');
  const heroRef = useRef<HTMLElement>(null);
  const howRef = useRef<HTMLElement>(null);
  const captureRef = useRef<HTMLElement>(null);
  const appsRef = useRef<HTMLElement>(null);
  const faqRef = useRef<HTMLElement>(null);

  const howItWorks = [
    { icon: Mic, title: t('askTitle'), description: t('askDescription') },
    { icon: Brain, title: t('learnTitle'), description: t('learnDescription') },
    { icon: Zap, title: t('doTitle'), description: t('doDescription') },
  ];

  const captureFeatures = [
    t('captureFeature1'), t('captureFeature2'), t('captureFeature3'),
    t('captureFeature4'), t('captureFeature5'), t('captureFeature6'),
  ];
  const recallFeatures = [
    t('recallFeature1'), t('recallFeature2'), t('recallFeature3'),
    t('recallFeature4'), t('recallFeature5'), t('recallFeature6'),
  ];
  const automateFeatures = [
    t('automateFeature1'), t('automateFeature2'), t('automateFeature3'),
    t('automateFeature4'), t('automateFeature5'), t('automateFeature6'),
  ];

  const specs = [
    { label: t('specBattery'), value: t('specBatteryValue') },
    { label: t('specBatteryLife'), value: t('specBatteryLifeValue') },
    { label: t('specDimensions'), value: t('specDimensionsValue') },
    { label: t('specMicrophones'), value: t('specMicrophonesValue') },
    { label: t('specBluetooth'), value: t('specBluetoothValue') },
    { label: t('specWifi'), value: t('specWifiValue') },
    { label: t('specEncryption'), value: t('specEncryptionValue') },
    { label: t('specCharging'), value: t('specChargingValue') },
  ];

  const faqs = [
    { q: t('faq1Q'), a: t('faq1A') },
    { q: t('faq2Q'), a: t('faq2A') },
    { q: t('faq3Q'), a: t('faq3A') },
    { q: t('faq4Q'), a: t('faq4A') },
    { q: t('faq5Q'), a: t('faq5A') },
    { q: t('faq6Q'), a: t('faq6A') },
  ];

  const testimonials = [
    { name: t('testimonial1Name'), role: t('testimonial1Role'), text: t('testimonial1Text') },
    { name: t('testimonial2Name'), role: t('testimonial2Role'), text: t('testimonial2Text') },
    { name: t('testimonial3Name'), role: t('testimonial3Role'), text: t('testimonial3Text') },
  ];

  useEffect(() => {
    const ctx = gsap.context(() => {
      // === Hero: pinned exploded device ===
      const hero = heroRef.current;
      if (hero) {
        const heroTitle = hero.querySelector('.hero-title');
        const heroSub = hero.querySelector('.hero-sub');
        const layers = hero.querySelectorAll('.device-layer');
        const labels = hero.querySelectorAll('.device-label');
        const specCards = hero.querySelectorAll('.spec-card');

        gsap.set(labels, { autoAlpha: 0, x: -10 });
        gsap.set(specCards, { autoAlpha: 0, y: 20 });

        const heroTl = gsap.timeline({
          scrollTrigger: {
            trigger: hero,
            start: 'top top',
            end: '+=250%',
            pin: true,
            scrub: 1,
            anticipatePin: 1,
          },
        });

        heroTl.to({}, { duration: 1 });
        heroTl.to([heroTitle, heroSub], {
          autoAlpha: 0, y: -40, filter: 'blur(6px)', duration: 1, stagger: 0.1,
        });
        heroTl.to(layers[0], { y: -90, duration: 2, ease: 'power2.inOut' }, '<0.3');
        heroTl.to(layers[1], { y: -30, duration: 2, ease: 'power2.inOut' }, '<');
        heroTl.to(layers[2], { y: 30, duration: 2, ease: 'power2.inOut' }, '<');
        heroTl.to(layers[3], { y: 90, duration: 2, ease: 'power2.inOut' }, '<');
        heroTl.to(labels, { autoAlpha: 1, x: 0, duration: 1, stagger: 0.15, ease: 'power2.out' }, '-=1');
        heroTl.to({}, { duration: 3 });
        heroTl.to(layers, { y: 0, duration: 1.5, ease: 'power2.inOut' });
        heroTl.to(labels, { autoAlpha: 0, duration: 0.5 }, '<');
        heroTl.to(specCards, { autoAlpha: 1, y: 0, duration: 0.8, stagger: 0.08, ease: 'power2.out' });
        heroTl.to({}, { duration: 1.5 });
      }

      const howCards = howRef.current?.querySelectorAll('.how-card');
      if (howCards) {
        gsap.fromTo(howCards, { opacity: 0, y: 50, scale: 0.95 }, {
          opacity: 1, y: 0, scale: 1, duration: 0.8, stagger: 0.15, ease: 'power3.out',
          scrollTrigger: { trigger: howRef.current, start: 'top 80%' },
        });
      }

      // Feature headings + items
      document.querySelectorAll('.feat-heading').forEach((el) => {
        gsap.fromTo(el, { opacity: 0, y: 30, filter: 'blur(4px)' }, {
          opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.8,
          scrollTrigger: { trigger: el, start: 'top 85%' },
        });
      });
      document.querySelectorAll('.feat-item').forEach((el) => {
        gsap.fromTo(el, { opacity: 0, y: 25 }, {
          opacity: 1, y: 0, duration: 0.6, ease: 'power2.out',
          scrollTrigger: { trigger: el, start: 'top 90%' },
        });
      });

      // Waveform bars
      const waveformBars = document.querySelectorAll('.waveform-bar');
      if (waveformBars.length) {
        gsap.to(waveformBars, {
          scaleY: () => 0.3 + Math.random() * 0.7,
          duration: 0.4,
          stagger: { each: 0.03, repeat: -1, yoyo: true },
          ease: 'sine.inOut',
          scrollTrigger: { trigger: captureRef.current, start: 'top 70%', toggleActions: 'play pause resume pause' },
        });
      }

      // Transcript lines typing in
      const transcriptAnims = document.querySelectorAll('.transcript-anim');
      if (transcriptAnims.length) {
        gsap.fromTo(transcriptAnims, { opacity: 0, x: -15 }, {
          opacity: 1, x: 0, duration: 0.5, stagger: 0.3, ease: 'power2.out',
          scrollTrigger: { trigger: captureRef.current, start: 'top 60%' },
        });
      }

      // Brain map nodes pop in
      document.querySelectorAll('.brain-node').forEach((el, i) => {
        gsap.fromTo(el, { scale: 0, opacity: 0 }, {
          scale: 1, opacity: 1, duration: 0.5, delay: i * 0.1, ease: 'back.out(1.5)',
          scrollTrigger: { trigger: el.closest('section'), start: 'top 70%' },
        });
      });

      // Flow destinations
      const flowDests = document.querySelectorAll('.flow-dest');
      if (flowDests.length) {
        gsap.fromTo(flowDests, { opacity: 0, y: 15 }, {
          opacity: 1, y: 0, duration: 0.5, stagger: 0.15, ease: 'power2.out',
          scrollTrigger: { trigger: flowDests[0]?.closest('section'), start: 'top 60%' },
        });
      }

      const appsHeading = appsRef.current?.querySelector('.apps-heading');
      if (appsHeading) {
        gsap.fromTo(appsHeading, { opacity: 0, y: 40, scale: 0.95 }, {
          opacity: 1, y: 0, scale: 1, duration: 1,
          scrollTrigger: { trigger: appsRef.current, start: 'top 80%' },
        });
      }

      const faqItems = faqRef.current?.querySelectorAll('.faq-item');
      if (faqItems) {
        gsap.fromTo(faqItems, { opacity: 0, y: 20 }, {
          opacity: 1, y: 0, duration: 0.5, stagger: 0.06, ease: 'power2.out',
          scrollTrigger: { trigger: faqRef.current, start: 'top 80%' },
        });
      }
    });

    return () => ctx.revert();
  }, []);

  return (
    <>
      <Navbar />
      <main className="pt-16">
        {/* Hero — pinned exploded device view */}
        <section ref={heroRef} className="relative h-screen overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand/[0.03] rounded-full blur-[150px]" />

          <div className="hero-title absolute top-[12%] left-1/2 -translate-x-1/2 text-center z-10 w-full px-6">
            <h1 className="font-display font-bold text-4xl md:text-6xl lg:text-7xl mb-4">
              {t('heroTitle', { brandLower: brand.nameLower })}
            </h1>
          </div>
          <p className="hero-sub absolute top-[22%] md:top-[20%] left-1/2 -translate-x-1/2 text-text-tertiary text-lg max-w-xl mx-auto text-center z-10 px-6">
            {t('heroDescription')}
          </p>

          {/* Exploded device — 4 layers stacked */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10" style={{ perspective: '1000px' }}>
            <div className="relative w-56 h-56 md:w-72 md:h-72">
              <div className="device-layer absolute inset-0 flex items-center justify-center">
                <div className="w-full h-full rounded-full bg-gradient-to-b from-[#333] to-[#2a2a2a] border border-white/10 shadow-[0_4px_30px_rgba(0,0,0,0.4)]" />
                <div className="device-label absolute -right-40 md:-right-52 top-1/2 -translate-y-1/2 flex items-center gap-3">
                  <div className="w-8 h-px bg-white/20" />
                  <span className="text-xs text-text-tertiary whitespace-nowrap">{t('aluminumShell')}</span>
                </div>
              </div>
              <div className="device-layer absolute inset-[10%] flex items-center justify-center">
                <div className="w-full h-full rounded-full bg-gradient-to-b from-[#2a2a2a] to-[#222] border border-white/[0.08] flex items-center justify-center">
                  <div className="flex gap-4">
                    <div className="w-3 h-3 rounded-full bg-brand/40 shadow-[0_0_8px_rgba(59,130,246,0.3)]" />
                    <div className="w-3 h-3 rounded-full bg-brand/40 shadow-[0_0_8px_rgba(59,130,246,0.3)]" />
                  </div>
                </div>
                <div className="device-label absolute -right-40 md:-right-52 top-1/2 -translate-y-1/2 flex items-center gap-3">
                  <div className="w-8 h-px bg-brand/40" />
                  <span className="text-xs text-brand whitespace-nowrap">{t('dualMicrophones')}</span>
                </div>
              </div>
              <div className="device-layer absolute inset-[25%] flex items-center justify-center">
                <div className="w-full h-full rounded-full bg-gradient-to-b from-[#252525] to-[#1a1a1a] border border-white/[0.06] flex items-center justify-center">
                  <div className="w-8 h-8 rounded-lg bg-brand/20 border border-brand/30 flex items-center justify-center">
                    <div className="w-3 h-3 rounded-sm bg-brand/50" />
                  </div>
                </div>
                <div className="device-label absolute -left-40 md:-left-52 top-1/2 -translate-y-1/2 flex items-center gap-3 flex-row-reverse">
                  <div className="w-8 h-px bg-white/20" />
                  <span className="text-xs text-text-tertiary whitespace-nowrap">{t('bleChip')}</span>
                </div>
              </div>
              <div className="device-layer absolute inset-[40%] flex items-center justify-center">
                <div className="w-full h-full rounded-full bg-gradient-to-br from-brand/40 to-brand/15 border border-brand/25 shadow-[0_0_40px_rgba(59,130,246,0.2)]" />
                <div className="device-label absolute -left-40 md:-left-52 top-1/2 -translate-y-1/2 flex items-center gap-3 flex-row-reverse">
                  <div className="w-8 h-px bg-brand/40" />
                  <span className="text-xs text-brand whitespace-nowrap">{t('battery150')}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Specs */}
          <div className="absolute bottom-[8%] left-1/2 -translate-x-1/2 z-10 w-full max-w-3xl px-6">
            <div className="grid grid-cols-4 gap-3">
              {specs.map((spec) => (
                <div key={spec.label} className="spec-card rounded-xl border border-white/[0.06] bg-bg-secondary/80 backdrop-blur-sm p-3 text-center">
                  <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-0.5">{spec.label}</div>
                  <div className="font-display font-semibold text-xs">{spec.value}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section ref={howRef} className="py-24 md:py-32 px-6">
          <div className="mx-auto max-w-5xl grid md:grid-cols-3 gap-6">
            {howItWorks.map((item) => (
              <div key={item.title} className="how-card group relative rounded-2xl border border-white/10 bg-bg-secondary p-8 text-center hover:border-brand/30 transition-all duration-500">
                <div className="w-14 h-14 rounded-2xl bg-brand/10 border border-brand/20 flex items-center justify-center mx-auto mb-5 group-hover:scale-110 transition-transform duration-500">
                  <item.icon size={24} className="text-brand" />
                </div>
                <h3 className="font-display font-bold text-xl mb-2">{item.title}</h3>
                <p className="text-text-tertiary text-sm leading-relaxed">{item.description}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Capture Everything */}
        <section ref={captureRef} className="py-24 md:py-32 px-6 overflow-hidden">
          <div className="mx-auto max-w-7xl">
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <div className="feat-item relative aspect-[4/3] rounded-2xl overflow-hidden bg-bg-secondary border border-white/10">
                <div className="absolute inset-0 bg-gradient-to-br from-brand/[0.04] to-transparent" />
                <div className="absolute top-[20%] left-[10%] right-[10%] flex items-end gap-[3px] h-20">
                  {Array.from({ length: 40 }).map((_, i) => (
                    <div key={i} className="waveform-bar flex-1 bg-brand/30 rounded-full" style={{ height: `${20 + Math.sin(i * 0.5) * 30 + Math.random() * 30}%` }} />
                  ))}
                </div>
                <div className="absolute bottom-[15%] left-[10%] right-[10%] space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-[10px] text-red-400 uppercase tracking-wider">Live</span>
                  </div>
                  {[t('transcriptLine1'), t('transcriptLine2'), t('transcriptLine3')].map((line, i) => (
                    <div key={i} className="transcript-anim bg-bg-tertiary/80 rounded-lg px-3 py-2">
                      <span className="text-xs text-text-secondary">{line}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h2 className="feat-heading font-display font-bold text-3xl md:text-4xl mb-8">{t('captureTitle')}</h2>
                <div className="space-y-4">
                  {captureFeatures.map((feat, i) => {
                    const Icon = featureIcons.capture[i];
                    return (
                      <div key={feat} className="feat-item flex items-start gap-3">
                        <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center flex-shrink-0 mt-0.5"><Icon size={15} className="text-brand" /></div>
                        <span className="text-text-secondary text-sm leading-relaxed">{feat}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Recall Instantly */}
        <section className="py-24 md:py-32 px-6 overflow-hidden">
          <div className="mx-auto max-w-7xl">
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <div className="lg:order-2">
                <h2 className="feat-heading font-display font-bold text-3xl md:text-4xl mb-8">{t('recallTitle')}</h2>
                <div className="space-y-4">
                  {recallFeatures.map((feat, i) => {
                    const Icon = featureIcons.recall[i];
                    return (
                      <div key={feat} className="feat-item flex items-start gap-3">
                        <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center flex-shrink-0 mt-0.5"><Icon size={15} className="text-brand" /></div>
                        <span className="text-text-secondary text-sm leading-relaxed">{feat}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="feat-item lg:order-1 relative aspect-[4/3] rounded-2xl overflow-hidden bg-bg-secondary border border-white/10">
                <div className="absolute inset-0 bg-gradient-to-br from-brand/[0.03] to-transparent" />
                <div className="absolute top-[12%] left-[10%] right-[10%]">
                  <div className="bg-bg-tertiary rounded-xl px-4 py-3 flex items-center gap-3 border border-white/[0.06]">
                    <Search size={14} className="text-text-tertiary" />
                    <span className="text-xs text-text-tertiary">{t('searchPlaceholder')}</span>
                    <div className="ml-auto w-5 h-5 rounded bg-brand/20 flex items-center justify-center">
                      <ArrowRight size={10} className="text-brand" />
                    </div>
                  </div>
                </div>
                <div className="absolute inset-0 top-[30%]">
                  {[
                    { x: '20%', y: '15%', label: t('nodeQ4'), size: 'lg', active: true },
                    { x: '55%', y: '8%', label: t('nodeRevenue'), size: 'sm', active: false },
                    { x: '40%', y: '40%', label: t('nodePipeline'), size: 'md', active: true },
                    { x: '10%', y: '50%', label: t('nodeTeamSync'), size: 'sm', active: false },
                    { x: '65%', y: '35%', label: t('nodeForecast'), size: 'sm', active: false },
                    { x: '45%', y: '65%', label: t('nodeActionItems'), size: 'md', active: true },
                  ].map((node, i) => (
                    <div key={i} className="brain-node absolute" style={{ left: node.x, top: node.y }}>
                      {i < 5 && <div className="absolute w-16 h-px bg-white/[0.06] rotate-[30deg] -right-12 top-1/2" />}
                      <div className={`rounded-full flex items-center justify-center ${node.size === 'lg' ? 'w-20 h-20' : node.size === 'md' ? 'w-14 h-14' : 'w-10 h-10'} ${node.active ? 'bg-brand/15 border border-brand/30' : 'bg-white/[0.04] border border-white/[0.06]'}`}>
                        <span className={`text-[9px] font-medium ${node.active ? 'text-brand' : 'text-text-tertiary'}`}>{node.label}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Automate Your Work */}
        <section className="py-24 md:py-32 px-6 overflow-hidden">
          <div className="mx-auto max-w-7xl">
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <div className="feat-item relative aspect-[4/3] rounded-2xl overflow-hidden bg-bg-secondary border border-white/10">
                <div className="absolute inset-0 bg-gradient-to-br from-brand/[0.03] to-transparent" />
                <div className="absolute inset-[10%] flex flex-col justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-brand/15 border border-brand/25 flex items-center justify-center">
                      <Mic size={18} className="text-brand" />
                    </div>
                    <div>
                      <div className="text-xs font-medium text-white">{t('flowMeetingCaptured')}</div>
                      <div className="text-[10px] text-text-tertiary">{t('flowActionItems')}</div>
                    </div>
                  </div>
                  <div className="flex justify-center">
                    <div className="flex flex-col items-center gap-1">
                      <div className="w-px h-6 bg-brand/30" />
                      <div className="w-4 h-4 rounded-full bg-brand/20 border border-brand/30 flex items-center justify-center">
                        <Zap size={8} className="text-brand" />
                      </div>
                      <div className="w-px h-6 bg-brand/30" />
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { name: 'Slack', desc: t('flowSlackDesc') },
                      { name: 'Linear', desc: t('flowLinearDesc') },
                      { name: 'Notion', desc: t('flowNotionDesc') },
                    ].map((dest) => (
                      <div key={dest.name} className="flow-dest rounded-xl bg-bg-tertiary/80 border border-white/[0.06] p-3 text-center">
                        <div className="w-8 h-8 rounded-lg bg-white/[0.06] mx-auto mb-2 flex items-center justify-center">
                          <span className="text-[10px] font-bold text-text-tertiary">{dest.name[0]}</span>
                        </div>
                        <div className="text-[10px] font-medium text-white">{dest.name}</div>
                        <div className="text-[9px] text-text-tertiary">{dest.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div>
                <h2 className="feat-heading font-display font-bold text-3xl md:text-4xl mb-8">{t('automateTitle')}</h2>
                <div className="space-y-4">
                  {automateFeatures.map((feat, i) => {
                    const Icon = featureIcons.automate[i];
                    return (
                      <div key={feat} className="feat-item flex items-start gap-3">
                        <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center flex-shrink-0 mt-0.5"><Icon size={15} className="text-brand" /></div>
                        <span className="text-text-secondary text-sm leading-relaxed">{feat}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Apps */}
        <section ref={appsRef} className="py-24 md:py-32 px-6 text-center">
          <div className="apps-heading">
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4">{t('appsTitle')}</h2>
            <p className="text-text-tertiary text-lg max-w-md mx-auto mb-10">{t('appsDescription')}</p>
            <div className="flex items-center justify-center gap-3 mb-10">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="w-12 h-12 rounded-xl bg-bg-secondary border border-white/10 flex items-center justify-center">
                  <div className="w-6 h-6 rounded-lg bg-brand/[0.15]" />
                </div>
              ))}
            </div>
            <Link href={brand.links.apps} className="inline-flex items-center gap-2 border border-white/10 text-sm font-medium px-7 py-3.5 rounded-full hover:border-white/20 transition-all">
              {t('visitAppStore')} <ArrowRight size={16} />
            </Link>
          </div>
        </section>

        {/* Testimonials */}
        <section className="py-24 px-6">
          <div className="mx-auto max-w-5xl">
            <h2 className="font-display font-bold text-3xl md:text-5xl text-center mb-16">{t('testimonialsTitle')}</h2>
            <div className="grid md:grid-cols-3 gap-6">
              {testimonials.map((item) => (
                <div key={item.name} className="rounded-2xl border border-white/10 bg-bg-secondary p-6">
                  <div className="flex gap-1 mb-4">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star key={i} size={14} className="text-yellow-500 fill-yellow-500" />
                    ))}
                  </div>
                  <p className="text-text-secondary text-sm leading-relaxed mb-5">&ldquo;{item.text}&rdquo;</p>
                  <div>
                    <div className="font-display font-semibold text-sm">{item.name}</div>
                    <div className="text-text-tertiary text-xs">{item.role}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section ref={faqRef} className="py-24 md:py-32 px-6">
          <div className="mx-auto max-w-2xl">
            <h2 className="font-display font-bold text-3xl md:text-5xl text-center mb-16">{t('faqTitle')}</h2>
            <div className="space-y-3">
              {faqs.map((faq) => (
                <FaqItem key={faq.q} question={faq.q} answer={faq.a} />
              ))}
            </div>
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="py-24 px-6 text-center border-t border-white/5">
          <h2 className="font-display font-bold text-3xl md:text-4xl mb-4">{t('bottomCtaTitle')}</h2>
          <p className="text-text-tertiary text-lg max-w-md mx-auto mb-10">{t('bottomCtaDescription')}</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href={brand.links.order} className="flex items-center gap-2 bg-brand hover:bg-brand-dark text-white font-medium text-sm px-8 py-4 rounded-full transition-all hover:shadow-lg hover:shadow-brand/20">
              {t('orderNooto')} <ArrowRight size={16} />
            </Link>
            <Link href={brand.links.tryBrowser} className="text-text-secondary hover:text-white text-sm font-medium border border-white/10 px-8 py-4 rounded-full hover:border-white/20 transition-all">
              {t('tryFreeInBrowser')}
            </Link>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

// ─── FAQ Item ────────────────────────────────────────────────────────────────

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="faq-item border border-white/10 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-white/[0.02] transition-colors"
      >
        <span className="font-display font-medium text-sm">{question}</span>
        <ChevronDown
          size={16}
          className={`text-text-tertiary transition-transform flex-shrink-0 ml-4 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-5 pb-4 text-text-tertiary text-sm leading-relaxed border-t border-white/5 pt-3">
          {answer}
        </div>
      )}
    </div>
  );
}
